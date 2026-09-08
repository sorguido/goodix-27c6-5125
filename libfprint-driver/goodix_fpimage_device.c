/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * FpImageDevice glue for the Goodix 27c6:5125 boundary.
 *
 * This file implements the first production-shaped slice of the libfprint
 * device glue with an in-memory fake backend and the production USB router,
 * TLS server, USB backend, secure-session and one-shot enrollment integration.
 * It contains no fprintd or persistent-write path.
 *
 * Architecture source: analysis/D276/D276_01_libfprint_device_architecture.md
 * API source: repository-local libfprint 1.94.5 (LGPL).
 */
#include "goodix_fpimage_device.h"

#include "goodix_fpimage_pipeline.h"
#include "goodix_u16_to_fpimage.h"
#include "goodix_usb_router.h"
#include "goodix_tls_server.h"
#include "goodix_fpi_usb_backend.h"
#include "goodix_secure_session.h"
#include "goodix_post_tls_lifecycle.h"
#include "goodix_runtime_material.h"
#include "goodix_enrollment_fpi_usb_binding.h"

#include "fpi-device.h"
#include "fpi-image-device.h"
#include "fp-device.h"
#include "fp-image-device-private.h"
#include <gusb.h>
#include <openssl/crypto.h>

#include <string.h>

struct _GoodixInMemoryBackend
{
  guint   arm_count;
  guint   disarm_count;
  guint   rearm_count;
  guint   total_command_count;
  gchar  *last_command;
};

struct _GoodixDeviceContext
{
  GoodixFpImageDevice     *device;
  GoodixDeviceContextState state;

  guint64                  generation_seq;
  guint64                  generation;

  gboolean                 terminal_fence;
  gboolean                 poisoned;
  GCancellable            *activation_cancellable;
  GCancellable            *usb_cancellable;
  gulong                   cancel_handler_id;
  gboolean                 activation_completed;

  gboolean                 release_tail_complete;
  gboolean                 fresh_down_table;
  guint64                  rearm_issued_generation;
  gboolean                 deactivation_held;
  gboolean                 deactivation_pending;
  gboolean                 deactivation_nonquiescent;

  const GoodixBackendVTable *backend_vtable;
  gpointer                   backend_user_data;
  GoodixInMemoryBackend      backend;
  GoodixUsbRouter           *usb_router;
  GoodixTlsServer           *tls_server;
  GoodixFpiUsbBackend       *fpi_usb_backend;
  GoodixSecureSession       *secure_session;
  GoodixPostTlsLifecycle    *post_tls_lifecycle;
  GoodixEnrollmentFpiUsbBinding *enrollment_binding;
  GoodixEnrollmentPostTlsEvents *pending_enrollment_events;
  GoodixEnrollmentAuxiliaryB0Func enrollment_auxiliary;
  gpointer                   enrollment_auxiliary_data;
  GoodixEnrollmentFpiUsbBindingAudit *enrollment_binding_audit;
  GoodixTlsPlaintextFunc     tls_plaintext;
  gpointer                   tls_user_data;
  guint                      a0_delivery_count;
  gboolean                   operator_epoch;
  GoodixPreSessionRxSyncAudit pre_session_rx_sync_audit;
  gint64                      pre_session_rx_sync_started_us;
  guint64                     pre_session_rx_sync_out_count_at_pass;
  GoodixPreSessionRxSyncClockFunc pre_session_rx_sync_clock;
  gpointer                    pre_session_rx_sync_clock_data;
  GoodixDeviceContextSecurePhaseObserver phase_observer;
  gpointer                   phase_observer_data;

  GoodixRuntimeMaterial     *runtime_material;
  GoodixSecureSessionMaterial runtime_secure_view;
  guint8                     runtime_fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH];
  GoodixRuntimeMaterialAudit runtime_material_audit;
  GoodixSecureSessionAudit    runtime_secure_audit;
  GoodixTlsAudit              runtime_tls_audit;
  GoodixPostTlsAudit          runtime_post_tls_audit;
  GoodixEnrollmentPostTlsEventsAudit runtime_enrollment_events_audit;
  GoodixEnrollmentFpiUsbBindingAudit runtime_enrollment_binding_audit;
  guint                      runtime_enrollment_auxiliary_count;
  gboolean                   production_action_consumed;
#ifdef GOODIX_ENABLE_TEST_SEAMS
  GoodixRuntimeMaterialReleaseSeam runtime_material_release;
  gpointer                   runtime_material_release_data;
#endif
  gboolean                   runtime_handoff_views_cleared;
  gboolean                   usb_interface_claimed;
#ifdef GOODIX_LIBFPRINT_SIGFM
  uint16_t                   sigfm_baseline[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  gboolean                   sigfm_baseline_valid;
#endif

  FpiImageDeviceState        last_framework_state;

  GError                  *terminal_error;
};

typedef struct
{
  GoodixDeviceContext *ctx;
  GoodixProductionEnrollmentAudit last_production_audit;
  gboolean last_production_audit_valid;
#ifdef GOODIX_ENABLE_TEST_SEAMS
  GoodixRuntimeMaterialAcquireSeam acquire_material;
  GoodixRuntimeMaterialReleaseSeam release_material;
  GoodixUsbInterfaceSeam claim_interface;
  GoodixUsbInterfaceSeam release_interface;
  gpointer production_seam_data;
#endif
} GoodixFpImageDevicePrivate;

typedef struct _GoodixUsbFpImageDevice
{
  GoodixFpImageDevice parent_instance;
} GoodixUsbFpImageDevice;

typedef struct _GoodixUsbFpImageDeviceClass
{
  GoodixFpImageDeviceClass parent_class;
} GoodixUsbFpImageDeviceClass;

#define GOODIX_TYPE_USB_FPIMAGE_DEVICE (goodix_usb_fpimage_device_get_type ())
GType goodix_usb_fpimage_device_get_type (void) G_GNUC_CONST;

G_DEFINE_TYPE_WITH_PRIVATE (GoodixFpImageDevice, goodix_fpimage_device,
                            FP_TYPE_IMAGE_DEVICE)
G_DEFINE_TYPE (GoodixUsbFpImageDevice, goodix_usb_fpimage_device,
               GOODIX_TYPE_FPIMAGE_DEVICE)

static const FpIdEntry goodix_usb_id_table[] = {
  { .vid = 0x27c6, .pid = 0x5125 },
  { .vid = 0, .pid = 0, .driver_data = 0 },
};

static GoodixDeviceContext *
goodix_fpimage_device_peek_context (GoodixFpImageDevice *self)
{
  GoodixFpImageDevicePrivate *priv =
    goodix_fpimage_device_get_instance_private (self);

  return priv->ctx;
}

static void
goodix_fpimage_device_set_context (GoodixFpImageDevice *self,
                                   GoodixDeviceContext *ctx)
{
  GoodixFpImageDevicePrivate *priv =
    goodix_fpimage_device_get_instance_private (self);

  priv->ctx = ctx;
}

static void goodix_device_context_set_terminal_fence (GoodixDeviceContext *ctx);
static void goodix_device_context_set_poisoned (GoodixDeviceContext *ctx,
                                                const GError        *error);
static void emit_terminal (GoodixDeviceContext *ctx, GError *error);
static gboolean
goodix_fpimage_device_is_production_usb (GoodixFpImageDevice *self);
static void default_release_runtime_material (GoodixRuntimeMaterial *owner,
                                              gpointer user_data);

static void
context_protocol_failure (GoodixDeviceContext *ctx,
                          const GError        *error)
{
  g_autoptr(GError) local_error = NULL;

  if (ctx->terminal_fence)
    {
      goodix_device_context_set_poisoned (ctx, error);
      return;
    }
  local_error = error != NULL ? g_error_copy (error) :
    g_error_new_literal (FP_DEVICE_ERROR, FP_DEVICE_ERROR_PROTO,
                         "Goodix production protocol failed closed");
  goodix_device_context_set_terminal_fence (ctx);
  goodix_device_context_set_poisoned (ctx, local_error);
  if (!ctx->operator_epoch &&
      (ctx->state == GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING ||
       ctx->state == GOODIX_DEVICE_CONTEXT_STATE_ACTIVE))
    emit_terminal (ctx, g_steal_pointer (&local_error));
}

static gint64
pre_session_rx_sync_now (GoodixDeviceContext *ctx)
{
  if (ctx->pre_session_rx_sync_clock != NULL)
    return ctx->pre_session_rx_sync_clock (
      ctx->pre_session_rx_sync_clock_data);
  return g_get_monotonic_time ();
}

static void
pre_session_rx_sync_update_elapsed (GoodixDeviceContext *ctx)
{
  gint64 elapsed = pre_session_rx_sync_now (ctx) -
                   ctx->pre_session_rx_sync_started_us;

  if (elapsed < 0)
    elapsed = 0;
  ctx->pre_session_rx_sync_audit.pre_session_rx_elapsed_ms =
    (guint64) elapsed / 1000u;
}

static void
pre_session_rx_sync_fail (GoodixDeviceContext *ctx,
                          const GError        *error)
{
  g_autoptr(GError) end_error = NULL;

  pre_session_rx_sync_update_elapsed (ctx);
  ctx->pre_session_rx_sync_audit.pre_session_rx_sync_completed = TRUE;
  ctx->pre_session_rx_sync_audit.pre_session_rx_result =
    GOODIX_PRE_SESSION_RX_SYNC_FAIL_CLOSED;
  if (goodix_fpi_usb_backend_pre_session_sync_is_active (
        ctx->fpi_usb_backend) &&
      goodix_fpi_usb_backend_is_drained (ctx->fpi_usb_backend))
    (void) goodix_fpi_usb_backend_end_pre_session_sync (
      ctx->fpi_usb_backend, ctx->generation, &end_error);
  context_protocol_failure (ctx, error != NULL ? error : end_error);
}
static void
context_usb_drained (GoodixFpiUsbBackend *backend,
                     gpointer             user_data)
{
  GoodixDeviceContext *ctx = user_data;
  (void) backend;
  if (ctx->deactivation_pending && !ctx->deactivation_held)
    goodix_device_context_complete_deactivation (ctx);
}

/* Production real-USB IN completions call goodix_fpi_usb_backend_complete_receive()
 * only; this callback ensures the same receive re-arm logic that the synthetic
 * test seam used is also reached on the real backend path. */
static void
context_usb_in_completed (GoodixFpiUsbBackend *backend,
                          guint64              submit_generation,
                          const GError        *error,
                          gpointer             user_data)
{
  GoodixDeviceContext *ctx = user_data;

  (void) backend;
  (void) submit_generation;
  (void) error;

  if (ctx->terminal_fence)
    return;

  if (((ctx->post_tls_lifecycle != NULL &&
        goodix_post_tls_lifecycle_needs_receive (ctx->post_tls_lifecycle)) ||
       (ctx->secure_session != NULL &&
        goodix_secure_session_needs_receive (ctx->secure_session)) ||
       (ctx->enrollment_binding != NULL &&
        goodix_enrollment_fpi_usb_binding_needs_receive (
          ctx->enrollment_binding))) &&
      goodix_fpi_usb_backend_get_outstanding (ctx->fpi_usb_backend) == 0)
    {
      g_autoptr(GError) arm_error = NULL;
      if (!goodix_device_context_arm_receive (ctx, &arm_error))
        context_protocol_failure (ctx, arm_error);
    }
}

static guint16
production_timestamp (void)
{
  return (guint16) ((guint64) (g_get_monotonic_time () / 1000) & 0xffffu);
}

static gboolean
production_enrollment_auxiliary (GBytes   *plaintext,
                                 gpointer  user_data,
                                 GError  **error)
{
  GoodixDeviceContext *ctx = user_data;

  if (ctx == NULL || ctx->terminal_fence || plaintext == NULL)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "production auxiliary enrollment B0 is fenced");
      return FALSE;
    }

  /* This target-observed message advances the graph, but its biometric and
   * application semantics remain unknown.  Keep it opaque in production. */
  ctx->runtime_enrollment_auxiliary_count++;
  return TRUE;
}

static void
production_activation_start_secure_graph (GoodixDeviceContext *ctx)
{
  GoodixPostTlsMaterial post_material = { 0 };
  GoodixEnrollmentModelConfig enrollment_config = {
    .required_stage_count = GOODIX_TARGET_LOCAL_ENROLL_STAGES,
    .defer_terminal_stage_delivery = TRUE,
  };
  g_autoptr(GError) error = NULL;
  FpiDeviceAction action;
  gboolean enrollment_action;

  if (ctx->state != GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING ||
      ctx->terminal_fence || ctx->operator_epoch ||
      ctx->runtime_material == NULL || !ctx->usb_interface_claimed)
    return;

  action = fpi_device_get_current_action (FP_DEVICE (ctx->device));
  enrollment_action = action == FPI_DEVICE_ACTION_ENROLL;

  memcpy (post_material.initial_fdt_table, ctx->runtime_fdt_seed,
          sizeof post_material.initial_fdt_table);
  post_material.af_timestamp = production_timestamp ();
  post_material.first_arm_timestamp = production_timestamp ();
  post_material.second_arm_timestamp = production_timestamp ();
  post_material.capture_profile =
    action == FPI_DEVICE_ACTION_IDENTIFY ?
      GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION :
      GOODIX_POST_TLS_CAPTURE_PROFILE_TWO_ACQUISITION;
  if (!goodix_device_context_configure_post_tls_lifecycle (
        ctx, &post_material, &ctx->runtime_post_tls_audit, &error) ||
      (enrollment_action &&
       !goodix_device_context_configure_enrollment_graph (
         ctx, &enrollment_config, production_enrollment_auxiliary, ctx,
         &ctx->runtime_enrollment_events_audit,
         &ctx->runtime_enrollment_binding_audit, &error)) ||
      !goodix_device_context_start_secure_session (
        ctx, &ctx->runtime_secure_view, NULL, NULL,
        &ctx->runtime_secure_audit, &ctx->runtime_tls_audit, &error))
    {
      OPENSSL_cleanse (&ctx->runtime_secure_view,
                       sizeof ctx->runtime_secure_view);
      OPENSSL_cleanse (ctx->runtime_fdt_seed,
                       sizeof ctx->runtime_fdt_seed);
      ctx->runtime_handoff_views_cleared = TRUE;
      context_protocol_failure (ctx, error);
      return;
    }

  /* Both consumers now own the data they need.  The runtime-material owner
   * remains alive until img_close, but no borrowed secret/FDT view is kept in
   * the glue after the handoff. */
  OPENSSL_cleanse (&ctx->runtime_secure_view,
                   sizeof ctx->runtime_secure_view);
  OPENSSL_cleanse (ctx->runtime_fdt_seed, sizeof ctx->runtime_fdt_seed);
#ifdef GOODIX_LIBFPRINT_SIGFM
  OPENSSL_cleanse (ctx->sigfm_baseline, sizeof ctx->sigfm_baseline);
  ctx->sigfm_baseline_valid = FALSE;
#endif
  ctx->runtime_handoff_views_cleared = TRUE;
  goodix_device_context_emit_arm_complete (ctx, NULL);
}

static void
context_pre_session_sync_completed (GoodixFpiUsbBackend *backend,
                                    guint64 submit_generation,
                                    const guint8 *data,
                                    gsize length,
                                    const GError *error,
                                    gpointer user_data)
{
  GoodixDeviceContext *ctx = user_data;
  GoodixPreSessionRxSyncAudit *audit = &ctx->pre_session_rx_sync_audit;
  g_autoptr(GError) local_error = NULL;

  (void) backend;
  pre_session_rx_sync_update_elapsed (ctx);
  audit->pre_session_rx_max_outstanding = MAX (
    audit->pre_session_rx_max_outstanding,
    goodix_fpi_usb_backend_get_max_outstanding (ctx->fpi_usb_backend));
  if (submit_generation != ctx->generation ||
      audit->pre_session_rx_result != GOODIX_PRE_SESSION_RX_SYNC_ACTIVE)
    return;

  if (audit->pre_session_rx_elapsed_ms >
      GOODIX_PRE_SESSION_RX_MAX_TOTAL_MS)
    {
      local_error = g_error_new_literal (
        G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
        "pre-session RX sync total-time bound exceeded");
      pre_session_rx_sync_fail (ctx, local_error);
      return;
    }

  if (error != NULL)
    {
      if (g_error_matches (error, G_USB_DEVICE_ERROR,
                           G_USB_DEVICE_ERROR_TIMED_OUT) && length == 0 &&
          goodix_fpi_usb_backend_is_drained (ctx->fpi_usb_backend))
        {
          audit->pre_session_rx_timeout_count++;
          audit->pre_session_rx_quiet_boundary = TRUE;
          if (!goodix_fpi_usb_backend_end_pre_session_sync (
                ctx->fpi_usb_backend, ctx->generation, &local_error))
            {
              pre_session_rx_sync_fail (ctx, local_error);
              return;
            }
          audit->pre_session_rx_sync_completed = TRUE;
          audit->pre_session_rx_result = GOODIX_PRE_SESSION_RX_SYNC_PASS;
          ctx->pre_session_rx_sync_out_count_at_pass =
            goodix_fpi_usb_backend_get_out_submit_count (
              ctx->fpi_usb_backend);
          if (!ctx->operator_epoch)
            production_activation_start_secure_graph (ctx);
          return;
        }
      audit->pre_session_rx_non_timeout_error_count++;
      pre_session_rx_sync_fail (ctx, error);
      return;
    }

  if (length == 0 || data == NULL)
    {
      local_error = g_error_new_literal (
        G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
        "pre-session RX sync completed without timeout or data");
      pre_session_rx_sync_fail (ctx, local_error);
      return;
    }

  audit->pre_session_rx_discarded_completion_count++;
  audit->pre_session_rx_discarded_byte_count += length;
  if (audit->pre_session_rx_discarded_completion_count >
        GOODIX_PRE_SESSION_RX_MAX_COMPLETIONS ||
      audit->pre_session_rx_discarded_byte_count >
        GOODIX_PRE_SESSION_RX_MAX_BYTES ||
      audit->pre_session_rx_elapsed_ms > GOODIX_PRE_SESSION_RX_MAX_TOTAL_MS ||
      audit->pre_session_rx_elapsed_ms +
        GOODIX_PRE_SESSION_RX_QUIET_TIMEOUT_MS >
        GOODIX_PRE_SESSION_RX_MAX_TOTAL_MS)
    {
      local_error = g_error_new_literal (
        G_IO_ERROR, G_IO_ERROR_NO_SPACE,
        "pre-session RX sync hard bound exceeded");
      pre_session_rx_sync_fail (ctx, local_error);
      return;
    }

  if (!goodix_fpi_usb_backend_arm_pre_session_sync_receive (
        ctx->fpi_usb_backend, ctx->generation,
        GOODIX_PRE_SESSION_RX_QUIET_TIMEOUT_MS, &local_error))
    pre_session_rx_sync_fail (ctx, local_error);
}

GoodixUsbRouter *
goodix_device_context_get_usb_router (GoodixDeviceContext *ctx)
{
  g_return_val_if_fail (ctx != NULL, NULL);
  return ctx->usb_router;
}

GoodixTlsServer *goodix_device_context_get_tls_server (GoodixDeviceContext *ctx)
{
  if (ctx == NULL)
    return NULL;
  return ctx->secure_session != NULL ?
    goodix_secure_session_get_tls_server (ctx->secure_session) : ctx->tls_server;
}
GoodixFpiUsbBackend *goodix_device_context_get_fpi_usb_backend (GoodixDeviceContext *ctx) { return ctx ? ctx->fpi_usb_backend : NULL; }

gboolean
goodix_device_context_adopt_dormant_enrollment_binding (
  GoodixDeviceContext           *ctx,
  GoodixEnrollmentFpiUsbBinding *binding,
  GError                       **error)
{
  if (ctx == NULL || binding == NULL || !ctx->operator_epoch ||
      ctx->terminal_fence || ctx->generation == 0u ||
      ctx->enrollment_binding != NULL || ctx->secure_session != NULL ||
      ctx->post_tls_lifecycle != NULL || ctx->tls_server != NULL ||
      goodix_enrollment_fpi_usb_binding_is_failed (binding) ||
      goodix_enrollment_fpi_usb_binding_get_backend (binding) !=
        ctx->fpi_usb_backend ||
      goodix_enrollment_fpi_usb_binding_get_generation (binding) !=
        ctx->generation)
    {
      g_set_error_literal (
        error, G_IO_ERROR, G_IO_ERROR_CLOSED,
        "dormant enrollment binding ownership preconditions failed");
      return FALSE;
    }
  ctx->enrollment_binding = binding;
  return TRUE;
}

gboolean
goodix_device_context_has_dormant_enrollment_binding (
  GoodixDeviceContext *ctx)
{
  return ctx != NULL && ctx->enrollment_binding != NULL;
}

static void context_a0_consumer (guint8 type, GBytes *frame, gpointer user_data)
{
  GoodixDeviceContext *ctx = user_data;
  if (type != 0xa0 || ctx->terminal_fence)
    return;
  ctx->a0_delivery_count++;
  if (ctx->enrollment_binding != NULL)
    {
      g_autoptr(GError) error = NULL;

      if (!goodix_enrollment_fpi_usb_binding_handle_a0 (
            ctx->enrollment_binding, frame, &error))
        context_protocol_failure (ctx, error);
    }
  else if (ctx->post_tls_lifecycle != NULL &&
      goodix_post_tls_lifecycle_get_phase (ctx->post_tls_lifecycle) !=
        GOODIX_POST_TLS_PHASE_NOT_STARTED)
    goodix_post_tls_lifecycle_handle_a0 (ctx->post_tls_lifecycle, frame);
  else if (ctx->secure_session != NULL)
    goodix_secure_session_handle_a0 (ctx->secure_session, frame);
}
static void context_b0_consumer (guint8 type, GBytes *frame, gpointer user_data)
{
  GoodixDeviceContext *ctx=user_data; gsize n; const guint8 *p; g_autoptr(GError) error=NULL;
  if(type!=0xb0||ctx->terminal_fence)return;
  if(ctx->secure_session!=NULL){goodix_secure_session_handle_b0(ctx->secure_session,frame);return;}
  /* Host-only decrypted-plaintext injection. Production always retains the
   * secure-session branch above, so TLS records cannot bypass authentication. */
  if((ctx->operator_epoch||
      !goodix_fpimage_device_is_production_usb(ctx->device))&&
     ctx->enrollment_binding!=NULL){
    g_autoptr(GBytes) plaintext=NULL;
    p=g_bytes_get_data(frame,&n);
    if(n<=4){context_protocol_failure(ctx,NULL);return;}
    plaintext=g_bytes_new_from_bytes(frame,4u,n-4u);
    if(!goodix_enrollment_fpi_usb_binding_handle_plaintext_chunk(
         ctx->enrollment_binding,plaintext,&error))
      context_protocol_failure(ctx,error);
    return;
  }
  if(!ctx->tls_server)return;
  p=g_bytes_get_data(frame,&n);
  if(n<=4||!goodix_tls_server_push(ctx->tls_server,p+4,n-4,&error))
    { goodix_device_context_set_terminal_fence(ctx); goodix_device_context_set_poisoned(ctx,error); }
}
static void context_tls_output (GBytes *record, gpointer user_data)
{
  GoodixDeviceContext *ctx=user_data; gsize n; const guint8 *p=g_bytes_get_data(record,&n); g_autoptr(GByteArray) frame=NULL; g_autoptr(GBytes) bytes=NULL; g_autoptr(GError) error=NULL; guint8 h[4];
  if(ctx->terminal_fence||n>G_MAXUINT16)return;
  h[0]=0xb0;h[1]=(guint8)n;h[2]=(guint8)(n>>8);h[3]=(guint8)(h[0]+h[1]+h[2]);
  frame=g_byte_array_sized_new((guint)n+4);g_byte_array_append(frame,h,4);g_byte_array_append(frame,p,(guint)n);bytes=g_byte_array_free_to_bytes(g_steal_pointer(&frame));
  if(!goodix_fpi_usb_backend_submit_out(ctx->fpi_usb_backend,ctx->generation,bytes,&error)){goodix_device_context_set_terminal_fence(ctx);goodix_device_context_set_poisoned(ctx,error);}
}
static void context_tls_plaintext (GBytes *bytes, gpointer user_data)
{ GoodixDeviceContext *ctx=user_data; if(!ctx->terminal_fence&&ctx->tls_plaintext)ctx->tls_plaintext(bytes,ctx->tls_user_data); }

/* --- Backend command recording --- */

static void
backend_record_command (GoodixDeviceContext *ctx, const gchar *name)
{
  GoodixInMemoryBackend *backend = &ctx->backend;

  backend->total_command_count++;
  g_free (backend->last_command);
  backend->last_command = g_strdup (name);
}

static void
backend_arm (GoodixDeviceContext *ctx, gpointer user_data)
{
  (void) user_data;
  ctx->backend.arm_count++;
  backend_record_command (ctx, "arm");
}

static void
backend_disarm (GoodixDeviceContext *ctx, gpointer user_data)
{
  (void) user_data;
  ctx->backend.disarm_count++;
  backend_record_command (ctx, "disarm");
}

static void
backend_rearm (GoodixDeviceContext *ctx, gpointer user_data)
{
  (void) user_data;
  ctx->backend.rearm_count++;
  backend_record_command (ctx, "rearm");
}

static const GoodixBackendVTable goodix_in_memory_backend_vtable = {
  .arm    = backend_arm,
  .disarm = backend_disarm,
  .rearm  = backend_rearm,
};

/* --- Context lifecycle --- */

static GoodixDeviceContext *
goodix_device_context_new (GoodixFpImageDevice *device)
{
  GoodixDeviceContext *ctx;

  ctx = g_new0 (GoodixDeviceContext, 1);
  ctx->device = device;
  ctx->state = GOODIX_DEVICE_CONTEXT_STATE_CLOSED;
  ctx->backend_vtable = &goodix_in_memory_backend_vtable;
  ctx->backend_user_data = &ctx->backend;
  ctx->usb_router = goodix_usb_router_new (context_a0_consumer, context_b0_consumer, ctx);
  ctx->fpi_usb_backend = goodix_fpi_usb_backend_new (FP_DEVICE (device), ctx->usb_router, 0x81, 0x01, 32768);
  goodix_fpi_usb_backend_set_drained_callback (ctx->fpi_usb_backend,
                                               context_usb_drained, ctx);
  goodix_fpi_usb_backend_set_in_completed_callback (ctx->fpi_usb_backend,
                                                    context_usb_in_completed,
                                                    ctx);
  goodix_fpi_usb_backend_set_sync_completed_callback (
    ctx->fpi_usb_backend, context_pre_session_sync_completed, ctx);

  return ctx;
}

static void
goodix_device_context_collect_production_enrollment_audit (
  GoodixDeviceContext              *ctx,
  GoodixProductionEnrollmentAudit *audit,
  gboolean                         context_closed)
{
  g_return_if_fail (ctx != NULL);
  g_return_if_fail (audit != NULL);

  *audit = (GoodixProductionEnrollmentAudit) {
    .production_action_consumed = ctx->production_action_consumed,
    .auxiliary_b0_observed_count = ctx->runtime_enrollment_auxiliary_count,
    .pre_session_rx_sync = ctx->pre_session_rx_sync_audit,
    .runtime_material = ctx->runtime_material_audit,
    .secure = ctx->runtime_secure_audit,
    .tls = ctx->runtime_tls_audit,
    .post_tls = ctx->runtime_post_tls_audit,
    .enrollment_events = ctx->runtime_enrollment_events_audit,
    .enrollment_binding = ctx->runtime_enrollment_binding_audit,
    .usb_real_submit_count = goodix_fpi_usb_backend_get_real_submit_count (
      ctx->fpi_usb_backend),
    .usb_out_submit_count = goodix_fpi_usb_backend_get_out_submit_count (
      ctx->fpi_usb_backend),
    .usb_in_completion_count = goodix_fpi_usb_backend_get_in_completion_count (
      ctx->fpi_usb_backend),
    .usb_out_completion_count = goodix_fpi_usb_backend_get_out_completion_count (
      ctx->fpi_usb_backend),
    .usb_outstanding_count = goodix_fpi_usb_backend_get_outstanding (
      ctx->fpi_usb_backend),
    .usb_out_outstanding_count = goodix_fpi_usb_backend_get_out_outstanding (
      ctx->fpi_usb_backend),
    .usb_max_in_outstanding_count = goodix_fpi_usb_backend_get_max_outstanding (
      ctx->fpi_usb_backend),
    .usb_max_out_outstanding_count =
      goodix_fpi_usb_backend_get_max_out_outstanding (ctx->fpi_usb_backend),
    .usb_interface_claimed = ctx->usb_interface_claimed,
    .usb_backend_drained = goodix_fpi_usb_backend_is_drained (
      ctx->fpi_usb_backend),
    .runtime_material_present = ctx->runtime_material != NULL,
    .runtime_handoff_views_cleared = ctx->runtime_handoff_views_cleared,
    .context_closed = context_closed,
  };
}

static void
goodix_device_context_free (GoodixDeviceContext              *ctx,
                            GoodixProductionEnrollmentAudit *final_audit)
{
  if (ctx == NULL)
    return;

  g_return_if_fail (goodix_fpi_usb_backend_is_drained (
                      ctx->fpi_usb_backend));
  g_return_if_fail (ctx->enrollment_binding == NULL ||
                    goodix_enrollment_fpi_usb_binding_can_free (
                      ctx->enrollment_binding));

  g_clear_object (&ctx->activation_cancellable);
  g_clear_object (&ctx->usb_cancellable);
  g_clear_error (&ctx->terminal_error);
  g_free (ctx->backend.last_command);
  goodix_post_tls_lifecycle_free (ctx->post_tls_lifecycle);
  goodix_secure_session_free (ctx->secure_session);
  goodix_tls_server_free (ctx->tls_server);
  goodix_enrollment_fpi_usb_binding_free (ctx->enrollment_binding);
  goodix_enrollment_post_tls_events_free (ctx->pending_enrollment_events);
  OPENSSL_cleanse (&ctx->runtime_secure_view,
                   sizeof ctx->runtime_secure_view);
  OPENSSL_cleanse (ctx->runtime_fdt_seed, sizeof ctx->runtime_fdt_seed);
#ifdef GOODIX_LIBFPRINT_SIGFM
  OPENSSL_cleanse (ctx->sigfm_baseline, sizeof ctx->sigfm_baseline);
  ctx->sigfm_baseline_valid = FALSE;
#endif
  if (ctx->runtime_material != NULL)
    {
#ifdef GOODIX_ENABLE_TEST_SEAMS
      g_assert (ctx->runtime_material_release != NULL);
      ctx->runtime_material_release (ctx->runtime_material,
                                     ctx->runtime_material_release_data);
#else
      default_release_runtime_material (ctx->runtime_material, NULL);
#endif
      ctx->runtime_material = NULL;
    }
  if (final_audit != NULL)
    goodix_device_context_collect_production_enrollment_audit (
      ctx, final_audit, TRUE);
  goodix_fpi_usb_backend_free (ctx->fpi_usb_backend);
  goodix_usb_router_free (ctx->usb_router);
  g_free (ctx);
}

static gboolean
default_acquire_runtime_material (
  GoodixRuntimeMaterial       **owner,
  GoodixSecureSessionMaterial  *secure_view,
  guint8                        fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GoodixRuntimeMaterialAudit   *audit,
  gpointer                      user_data,
  GError                      **error)
{
  GoodixRuntimeMaterialPaths paths;
  GoodixRuntimeMaterialPolicy policy;

  (void) user_data;
  goodix_runtime_material_paths_production (&paths);
  goodix_runtime_material_policy_production (&policy);
  *owner = goodix_runtime_material_load (&paths, &policy, audit, error);
  if (*owner == NULL)
    return FALSE;
  if (!goodix_runtime_material_get_secure_view (*owner, secure_view, error) ||
      !goodix_runtime_material_get_fdt_seed (*owner, fdt_seed, error))
    {
      goodix_runtime_material_free (*owner);
      *owner = NULL;
      OPENSSL_cleanse (secure_view, sizeof *secure_view);
      OPENSSL_cleanse (fdt_seed, GOODIX_RUNTIME_FDT_SEED_LENGTH);
      return FALSE;
    }
  return TRUE;
}

static void
default_release_runtime_material (GoodixRuntimeMaterial *owner,
                                  gpointer               user_data)
{
  (void) user_data;
  goodix_runtime_material_free (owner);
}

static gboolean
default_claim_interface (GUsbDevice *usb_device,
                         guint8      interface_number,
                         gpointer    user_data,
                         GError    **error)
{
  (void) user_data;
  return g_usb_device_claim_interface (
    usb_device, interface_number, G_USB_DEVICE_CLAIM_INTERFACE_NONE, error);
}

static gboolean
default_release_interface (GUsbDevice *usb_device,
                           guint8      interface_number,
                           gpointer    user_data,
                           GError    **error)
{
  (void) user_data;
  return g_usb_device_release_interface (
    usb_device, interface_number, G_USB_DEVICE_CLAIM_INTERFACE_NONE, error);
}

static gboolean
goodix_fpimage_device_is_production_usb (GoodixFpImageDevice *self)
{
  return FP_DEVICE_GET_CLASS (self)->type == FP_DEVICE_TYPE_USB;
}

static gboolean
goodix_fpimage_device_release_claim (GoodixFpImageDevice *self,
                                     GError             **error)
{
  GoodixFpImageDevicePrivate *priv =
    goodix_fpimage_device_get_instance_private (self);
  GoodixDeviceContext *ctx = priv->ctx;
#ifdef GOODIX_ENABLE_TEST_SEAMS
  GoodixUsbInterfaceSeam release_interface;
#endif

  if (ctx == NULL || !ctx->usb_interface_claimed)
    return TRUE;
#ifdef GOODIX_ENABLE_TEST_SEAMS
  release_interface = priv->release_interface != NULL ?
    priv->release_interface : default_release_interface;
  if (!release_interface (fpi_device_get_usb_device (FP_DEVICE (self)), 0,
                          priv->production_seam_data, error))
    return FALSE;
#else
  if (!default_release_interface (
        fpi_device_get_usb_device (FP_DEVICE (self)), 0, NULL, error))
    return FALSE;
#endif
  ctx->usb_interface_claimed = FALSE;
  return TRUE;
}

static void
goodix_fpimage_device_discard_context (GoodixFpImageDevice *self)
{
  GoodixFpImageDevicePrivate *priv =
    goodix_fpimage_device_get_instance_private (self);
  GoodixDeviceContext *ctx = goodix_fpimage_device_peek_context (self);

  if (ctx != NULL)
    {
      goodix_device_context_free (ctx, &priv->last_production_audit);
      priv->last_production_audit_valid = TRUE;
    }
  goodix_fpimage_device_set_context (self, NULL);
}

static void
goodix_device_context_set_state (GoodixDeviceContext      *ctx,
                                 GoodixDeviceContextState  state)
{
  ctx->state = state;
}

static void
goodix_device_context_set_poisoned (GoodixDeviceContext *ctx,
                                    const GError        *error)
{
  ctx->poisoned = TRUE;
  if (error != NULL && ctx->terminal_error == NULL)
    ctx->terminal_error = g_error_copy (error);
}

static void
goodix_device_context_set_terminal_fence (GoodixDeviceContext *ctx)
{
  ctx->terminal_fence = TRUE;
  goodix_enrollment_fpi_usb_binding_cancel (
    ctx->enrollment_binding, "GoodixDeviceContext terminal fence");
  if (ctx->secure_session != NULL &&
      goodix_secure_session_get_phase (ctx->secure_session) !=
        GOODIX_SECURE_PHASE_STOP &&
      goodix_secure_session_get_phase (ctx->secure_session) !=
        GOODIX_SECURE_PHASE_TERMINAL)
    goodix_secure_session_cancel (ctx->secure_session,
                                  "GoodixDeviceContext terminal fence");
  if (ctx->post_tls_lifecycle != NULL &&
      goodix_post_tls_lifecycle_get_phase (ctx->post_tls_lifecycle) !=
        GOODIX_POST_TLS_PHASE_STOP &&
      goodix_post_tls_lifecycle_get_phase (ctx->post_tls_lifecycle) !=
        GOODIX_POST_TLS_PHASE_TERMINAL)
    goodix_post_tls_lifecycle_cancel (ctx->post_tls_lifecycle,
                                      "GoodixDeviceContext terminal fence");
  goodix_tls_server_cancel (ctx->tls_server);
  goodix_fpi_usb_backend_cancel (ctx->fpi_usb_backend);
}

static void
goodix_device_context_disconnect_cancel_handler (GoodixDeviceContext *ctx)
{
  if (ctx->cancel_handler_id != 0 && ctx->activation_cancellable != NULL)
    {
      g_cancellable_disconnect (ctx->activation_cancellable,
                                ctx->cancel_handler_id);
      ctx->cancel_handler_id = 0;
    }
}

static void on_activation_cancellable_cancelled (GCancellable *cancellable,
                                                 gpointer      user_data);

static gboolean
goodix_device_context_is_stale_or_fenced (GoodixDeviceContext *ctx)
{
  return ctx->terminal_fence || ctx->generation == 0;
}

static void
goodix_device_context_maybe_rearm (GoodixDeviceContext *ctx)
{
  if (goodix_device_context_is_stale_or_fenced (ctx))
    return;

  if (!ctx->release_tail_complete || !ctx->fresh_down_table)
    return;

  if (ctx->last_framework_state != FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON)
    return;

  if (ctx->post_tls_lifecycle != NULL &&
      goodix_post_tls_lifecycle_get_phase (ctx->post_tls_lifecycle) !=
        GOODIX_POST_TLS_PHASE_NOT_STARTED)
    {
      goodix_post_tls_lifecycle_set_framework_await_finger_on (
        ctx->post_tls_lifecycle, ctx->generation, TRUE);
      return;
    }

  if (ctx->rearm_issued_generation == ctx->generation)
    return;

  ctx->rearm_issued_generation = ctx->generation;
  ctx->backend_vtable->rearm (ctx, ctx->backend_user_data);
}

/* --- libfprint vfunc implementations --- */

static gboolean
complete_activation_cancel_idle (gpointer user_data)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (user_data);
  GoodixDeviceContext *ctx = goodix_fpimage_device_peek_context (self);
  g_autoptr(GError) error = NULL;

  if (ctx == NULL ||
      ctx->state != GOODIX_DEVICE_CONTEXT_STATE_INACTIVE ||
      !ctx->activation_completed ||
      ctx->activation_cancellable == NULL)
    return G_SOURCE_REMOVE;

  if (g_cancellable_set_error_if_cancelled (ctx->activation_cancellable,
                                             &error))
    fpi_image_device_activate_complete (FP_IMAGE_DEVICE (self),
                                        g_steal_pointer (&error));

  return G_SOURCE_REMOVE;
}

static void
on_activation_cancellable_cancelled (GCancellable *cancellable,
                                     gpointer      user_data)
{
  GoodixDeviceContext *ctx = user_data;

  (void) cancellable;

  if (ctx->state != GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING ||
      ctx->activation_completed)
    return;

  /* Do not complete the libfprint action from inside the cancellable
   * dispatch.  clear_device_cancel_action() disconnects both the internal
   * and external cancellables; doing that synchronously here can deadlock
   * against the still-running external cancellation callback. */
  ctx->cancel_handler_id = 0;
  goodix_device_context_set_terminal_fence (ctx);
  ctx->generation = 0;
  /* The backend arm and USB begin_generation have already been reached; the
   * device-side quiescence is unproven, so the remaining open epoch must stay
   * poisoned.  The state is still INACTIVE here so that the activate completion
   * idle can deliver G_IO_ERROR_CANCELLED exactly once. */
  goodix_device_context_set_poisoned (ctx, NULL);
  goodix_device_context_set_state (ctx,
                                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
  ctx->activation_completed = TRUE;

  g_idle_add_full (G_PRIORITY_DEFAULT,
                   complete_activation_cancel_idle,
                   g_object_ref (ctx->device),
                   g_object_unref);
}

static gboolean
open_complete_idle (gpointer user_data)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (user_data);
  GoodixDeviceContext *ctx = goodix_fpimage_device_peek_context (self);
  g_autoptr(GError) error = NULL;
  GCancellable *cancellable;

  cancellable = fpi_device_get_cancellable (FP_DEVICE (self));
  if (g_cancellable_set_error_if_cancelled (cancellable, &error))
    {
      goodix_fpimage_device_discard_context (self);
      fpi_image_device_open_complete (FP_IMAGE_DEVICE (self),
                                      g_steal_pointer (&error));
    }
  else
    {
      goodix_device_context_set_state (ctx,
                                       GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
      fpi_image_device_open_complete (FP_IMAGE_DEVICE (self), NULL);
    }

  g_object_unref (self);
  return G_SOURCE_REMOVE;
}

static void
goodix_fpimage_device_img_open (FpImageDevice *dev)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (dev);
  GoodixFpImageDevicePrivate *priv =
    goodix_fpimage_device_get_instance_private (self);
  GoodixDeviceContext *ctx = priv->ctx;
#ifdef GOODIX_ENABLE_TEST_SEAMS
  GoodixRuntimeMaterialAcquireSeam acquire_material;
  GoodixUsbInterfaceSeam claim_interface;
#endif
  GCancellable *cancellable;
  g_autoptr(GError) error = NULL;

  if (ctx == NULL)
    {
      ctx = goodix_device_context_new (self);
      goodix_fpimage_device_set_context (self, ctx);
      goodix_device_context_set_state (ctx,
                                       GOODIX_DEVICE_CONTEXT_STATE_OPENING);
    }

  g_assert (ctx != NULL);
  g_assert (ctx->state == GOODIX_DEVICE_CONTEXT_STATE_OPENING);

  goodix_device_context_set_state (ctx,
                                   GOODIX_DEVICE_CONTEXT_STATE_OPENING);
  if (!goodix_fpimage_device_is_production_usb (self))
    {
      g_object_ref (self);
      g_idle_add (open_complete_idle, self);
      return;
    }

  cancellable = fpi_device_get_cancellable (FP_DEVICE (self));
  if (g_cancellable_set_error_if_cancelled (cancellable, &error))
    goto fail;

#ifdef GOODIX_ENABLE_TEST_SEAMS
  acquire_material = priv->acquire_material != NULL ?
    priv->acquire_material : default_acquire_runtime_material;
  ctx->runtime_material_release = priv->release_material != NULL ?
    priv->release_material : default_release_runtime_material;
  ctx->runtime_material_release_data = priv->production_seam_data;
  if (!acquire_material (&ctx->runtime_material,
                         &ctx->runtime_secure_view,
                         ctx->runtime_fdt_seed,
                         &ctx->runtime_material_audit,
                         priv->production_seam_data, &error) ||
      ctx->runtime_material == NULL)
#else
  if (!default_acquire_runtime_material (&ctx->runtime_material,
                                         &ctx->runtime_secure_view,
                                         ctx->runtime_fdt_seed,
                                         &ctx->runtime_material_audit,
                                         NULL, &error) ||
      ctx->runtime_material == NULL)
#endif
    {
      if (error == NULL)
        error = g_error_new_literal (
          G_IO_ERROR, G_IO_ERROR_FAILED,
          "production runtime material acquisition failed closed");
      goto fail;
    }
  if (g_cancellable_set_error_if_cancelled (cancellable, &error))
    goto fail;

#ifdef GOODIX_ENABLE_TEST_SEAMS
  claim_interface = priv->claim_interface != NULL ?
    priv->claim_interface : default_claim_interface;
  if (!claim_interface (fpi_device_get_usb_device (FP_DEVICE (self)), 0,
                        priv->production_seam_data, &error))
    goto fail;
#else
  if (!default_claim_interface (
        fpi_device_get_usb_device (FP_DEVICE (self)), 0, NULL, &error))
    goto fail;
#endif
  ctx->usb_interface_claimed = TRUE;
  if (g_cancellable_set_error_if_cancelled (cancellable, &error))
    goto fail;

  goodix_device_context_set_state (ctx,
                                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
  fpi_image_device_open_complete (dev, NULL);
  return;

fail:
  if (ctx->usb_interface_claimed)
    {
      g_autoptr(GError) release_error = NULL;

      if (!goodix_fpimage_device_release_claim (self, &release_error) &&
          error == NULL)
        error = g_steal_pointer (&release_error);
    }
  goodix_fpimage_device_discard_context (self);
  fpi_image_device_open_complete (dev, g_steal_pointer (&error));
}

static void
goodix_fpimage_device_img_close (FpImageDevice *dev)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (dev);
  GoodixDeviceContext *ctx = goodix_fpimage_device_peek_context (self);
  g_autoptr(GError) error = NULL;

  g_assert (ctx != NULL);
  g_assert (ctx->state != GOODIX_DEVICE_CONTEXT_STATE_CLOSING);

  goodix_device_context_set_terminal_fence (ctx);
  goodix_device_context_set_state (ctx,
                                   GOODIX_DEVICE_CONTEXT_STATE_CLOSING);

  if (ctx->usb_interface_claimed)
    (void) goodix_fpimage_device_release_claim (self, &error);
  goodix_fpimage_device_discard_context (self);

  fpi_image_device_close_complete (dev, g_steal_pointer (&error));
}

static void
goodix_fpimage_device_activate (FpImageDevice *dev)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (dev);
  GoodixDeviceContext *ctx = goodix_fpimage_device_peek_context (self);

  g_assert (ctx != NULL);
  g_assert (ctx->state == GOODIX_DEVICE_CONTEXT_STATE_INACTIVE ||
            ctx->state == GOODIX_DEVICE_CONTEXT_STATE_ACTIVE ||
            ctx->state == GOODIX_DEVICE_CONTEXT_STATE_POISONED);

  g_autoptr(GError) error = NULL;

  /* A non-quiescent terminal poisons the complete open epoch.  Re-entry is
   * forbidden until img_close destroys the context; activation must not clear
   * the fence, allocate a generation or reach either backend while poisoned. */
  if (ctx->poisoned)
    {
      if (ctx->terminal_error != NULL)
        error = g_error_copy (ctx->terminal_error);
      else
        error = g_error_new_literal (
          FP_DEVICE_ERROR, FP_DEVICE_ERROR_PROTO,
          "Goodix protocol session is poisoned until device close");
      fpi_image_device_activate_complete (dev, g_steal_pointer (&error));
      return;
    }

  if (goodix_fpimage_device_is_production_usb (self) &&
      fpi_device_get_current_action (FP_DEVICE (self)) !=
        FPI_DEVICE_ACTION_ENROLL &&
      fpi_device_get_current_action (FP_DEVICE (self)) !=
        FPI_DEVICE_ACTION_IDENTIFY)
    {
      error = g_error_new_literal (
        FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED,
        "Goodix production boundary permits enrollment and identify only");
      fpi_image_device_activate_complete (dev, g_steal_pointer (&error));
      return;
    }

  /* The first production action consumes this complete open epoch, including
   * an activation that later fails.  No retry or second action can reuse
   * potentially ambiguous device-side state: img_close/img_open is required. */
  if (goodix_fpimage_device_is_production_usb (self) &&
      ctx->production_action_consumed)
    {
      error = g_error_new_literal (
        FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED,
        "Goodix production open epoch already consumed; close/reopen required");
      fpi_image_device_activate_complete (dev, g_steal_pointer (&error));
      return;
    }
  if (goodix_fpimage_device_is_production_usb (self))
    ctx->production_action_consumed = TRUE;

  /* New activation -> new generation, reset per-activation gates. */
  ctx->generation_seq++;
  ctx->generation = ctx->generation_seq;
  ctx->release_tail_complete = FALSE;
  ctx->fresh_down_table = FALSE;
  ctx->rearm_issued_generation = 0;
  ctx->terminal_fence = FALSE;
  ctx->activation_completed = FALSE;
  g_clear_object (&ctx->activation_cancellable);
  ctx->activation_cancellable = g_object_ref (
    fpi_device_get_cancellable (FP_DEVICE (self)));
  g_clear_object (&ctx->usb_cancellable);
  ctx->usb_cancellable = g_cancellable_new ();
  if (!goodix_fpi_usb_backend_begin_generation (ctx->fpi_usb_backend,
                                                ctx->generation,
                                                ctx->usb_cancellable, &error))
    {
      ctx->terminal_fence = TRUE;
      ctx->poisoned = TRUE;
      ctx->generation = 0;
      goodix_device_context_set_state (ctx,
                                       GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
      fpi_image_device_activate_complete (dev, g_steal_pointer (&error));
      return;
    }
  goodix_usb_router_begin_generation (ctx->usb_router, ctx->generation);
  ctx->cancel_handler_id =
    g_cancellable_connect (ctx->activation_cancellable,
                           G_CALLBACK (on_activation_cancellable_cancelled),
                           ctx, NULL);

  goodix_device_context_set_state (ctx, GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING);
  if (goodix_fpimage_device_is_production_usb (self))
    {
      if (ctx->runtime_material == NULL || !ctx->usb_interface_claimed)
        {
          error = g_error_new_literal (
            FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_OPEN,
            "Goodix production activation lacks its open-epoch resources");
          context_protocol_failure (ctx, error);
          return;
        }
      if (!goodix_device_context_begin_pre_session_rx_sync (ctx, &error) &&
          ctx->state == GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING)
        context_protocol_failure (ctx, error);
      return;
    }
  ctx->backend_vtable->arm (ctx, ctx->backend_user_data);
}

static void
goodix_fpimage_device_change_state (FpImageDevice      *dev,
                                    FpiImageDeviceState  state)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (dev);
  GoodixDeviceContext *ctx = goodix_fpimage_device_peek_context (self);

  if (ctx == NULL)
    return;

  ctx->last_framework_state = state;

  if (state == FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON)
    goodix_device_context_maybe_rearm (ctx);
}

static void
goodix_fpimage_device_deactivate (FpImageDevice *dev)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (dev);
  GoodixDeviceContext *ctx = goodix_fpimage_device_peek_context (self);

  g_assert (ctx != NULL);

  if (ctx->state == GOODIX_DEVICE_CONTEXT_STATE_DEACTIVATING)
    return;

  goodix_device_context_set_state (ctx,
                                   GOODIX_DEVICE_CONTEXT_STATE_DEACTIVATING);
  ctx->deactivation_pending = TRUE;
  goodix_device_context_disconnect_cancel_handler (ctx);
  goodix_device_context_set_terminal_fence (ctx);
  ctx->backend_vtable->disarm (ctx, ctx->backend_user_data);

  /* Host callbacks are fenced, but arbitrary device-side quiescence remains
   * unproven.  Never advertise this cancellation path as safely inactive. */
  ctx->generation = 0;
  ctx->deactivation_nonquiescent =
    fpi_device_action_is_cancelled (FP_DEVICE (ctx->device));

  if (ctx->deactivation_pending && !ctx->deactivation_held &&
      goodix_fpi_usb_backend_is_drained (ctx->fpi_usb_backend))
    goodix_device_context_complete_deactivation (ctx);
}

static void
goodix_fpimage_device_finalize (GObject *object)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (object);
  GoodixDeviceContext *ctx = goodix_fpimage_device_peek_context (self);
  g_autoptr(GError) error = NULL;

  if (ctx != NULL && ctx->usb_interface_claimed)
    (void) goodix_fpimage_device_release_claim (self, &error);
  goodix_fpimage_device_discard_context (self);

  G_OBJECT_CLASS (goodix_fpimage_device_parent_class)->finalize (object);
}

static void
goodix_fpimage_device_class_init (GoodixFpImageDeviceClass *klass)
{
  GObjectClass      *object_class = G_OBJECT_CLASS (klass);
  FpDeviceClass     *device_class = FP_DEVICE_CLASS (klass);
  FpImageDeviceClass *img_class   = FP_IMAGE_DEVICE_CLASS (klass);

  object_class->finalize = goodix_fpimage_device_finalize;

  device_class->id        = "goodix_27c6_5125_host_only";
  device_class->full_name = "Goodix 27c6:5125 host-only shell";
  device_class->type      = FP_DEVICE_TYPE_VIRTUAL;
  device_class->scan_type = FP_SCAN_TYPE_PRESS;
  device_class->nr_enroll_stages = GOODIX_TARGET_LOCAL_ENROLL_STAGES;

  img_class->img_open     = goodix_fpimage_device_img_open;
  img_class->img_close    = goodix_fpimage_device_img_close;
  img_class->activate     = goodix_fpimage_device_activate;
  img_class->change_state = goodix_fpimage_device_change_state;
  img_class->deactivate   = goodix_fpimage_device_deactivate;
  img_class->img_width    = (gint) GOODIX_CANONICAL_IMAGE_WIDTH;
  img_class->img_height   = (gint) GOODIX_CANONICAL_IMAGE_HEIGHT;
#if defined(GOODIX_LIBFPRINT_SIGFM) || \
    !defined(GOODIX_LIBFPRINT_1_94_100_NBIS)
  img_class->algorithm    = FPI_DEVICE_ALGO_SIGFM;
#endif

  fpi_device_class_auto_initialize_features (device_class);
}

static void
goodix_fpimage_device_init (GoodixFpImageDevice *self)
{
  GoodixDeviceContext *ctx = goodix_device_context_new (self);

  goodix_fpimage_device_set_context (self, ctx);
  goodix_device_context_set_state (ctx,
                                   GOODIX_DEVICE_CONTEXT_STATE_OPENING);
}

static void
goodix_usb_fpimage_device_class_init (GoodixUsbFpImageDeviceClass *klass)
{
  FpDeviceClass *device_class = FP_DEVICE_CLASS (klass);

  /* fp_device_set_property() consults the final instance class before
   * constructed() copies the transport type into private state. */
  device_class->id        = "goodix_27c6_5125";
  device_class->full_name = "Goodix 27c6:5125 Fingerprint Sensor";
  device_class->type      = FP_DEVICE_TYPE_USB;
  device_class->scan_type = FP_SCAN_TYPE_PRESS;
  device_class->id_table  = goodix_usb_id_table;
}

static void
goodix_usb_fpimage_device_init (GoodixUsbFpImageDevice *self)
{
  (void) self;
}

/* Standard libfprint registry entry point.  The registered production type is
 * the USB-typed subclass; both it and the host-only constructor below reuse
 * the exact same GoodixDeviceContext implementation. */
GType
fpi_device_goodix_27c6_5125_get_type (void)
{
  return goodix_usb_fpimage_device_get_type ();
}

/* --- Public constructor --- */

GoodixFpImageDevice *
goodix_fpimage_device_new (void)
{
  return g_object_new (GOODIX_TYPE_FPIMAGE_DEVICE, NULL);
}

GoodixFpImageDevice *
goodix_fpimage_device_new_for_usb (GUsbDevice *usb_device)
{
  g_return_val_if_fail (usb_device != NULL, NULL);
  return g_object_new (GOODIX_TYPE_USB_FPIMAGE_DEVICE,
                       "fpi-usb-device", usb_device,
                       "fpi-driver-data", (guint64) 0,
                       NULL);
}

GoodixDeviceContext *
goodix_fpimage_device_get_context (GoodixFpImageDevice *dev)
{
  g_return_val_if_fail (GOODIX_IS_FPIMAGE_DEVICE (dev), NULL);
  return goodix_fpimage_device_peek_context (dev);
}

#ifdef GOODIX_ENABLE_TEST_SEAMS
void
goodix_fpimage_device_set_production_open_seams (
  GoodixFpImageDevice               *dev,
  GoodixRuntimeMaterialAcquireSeam   acquire_material,
  GoodixRuntimeMaterialReleaseSeam   release_material,
  GoodixUsbInterfaceSeam             claim_interface,
  GoodixUsbInterfaceSeam             release_interface,
  gpointer                           user_data)
{
  GoodixFpImageDevicePrivate *priv;

  g_return_if_fail (GOODIX_IS_FPIMAGE_DEVICE (dev));
  g_return_if_fail (goodix_fpimage_device_is_production_usb (dev));
  g_return_if_fail ((acquire_material == NULL) ==
                    (release_material == NULL));
  g_return_if_fail ((claim_interface == NULL) ==
                    (release_interface == NULL));
  priv = goodix_fpimage_device_get_instance_private (dev);
  g_return_if_fail (priv->ctx == NULL ||
                    (priv->ctx->state == GOODIX_DEVICE_CONTEXT_STATE_OPENING &&
                     priv->ctx->runtime_material == NULL &&
                     !priv->ctx->usb_interface_claimed));
  priv->acquire_material = acquire_material;
  priv->release_material = release_material;
  priv->claim_interface = claim_interface;
  priv->release_interface = release_interface;
  priv->production_seam_data = user_data;
}
#endif

gboolean
goodix_device_context_has_runtime_material (GoodixDeviceContext *ctx)
{
  return ctx != NULL && ctx->runtime_material != NULL;
}

gboolean
goodix_device_context_has_usb_claim (GoodixDeviceContext *ctx)
{
  return ctx != NULL && ctx->usb_interface_claimed;
}

gboolean
goodix_device_context_runtime_handoff_views_cleared (GoodixDeviceContext *ctx)
{
  return ctx != NULL && ctx->runtime_handoff_views_cleared;
}

void
goodix_device_context_get_production_enrollment_audit (
  GoodixDeviceContext              *ctx,
  GoodixProductionEnrollmentAudit *audit)
{
  g_return_if_fail (ctx != NULL);
  g_return_if_fail (audit != NULL);

  goodix_device_context_collect_production_enrollment_audit (
    ctx, audit, FALSE);
}

void
goodix_fpimage_device_get_production_enrollment_audit (
  GoodixFpImageDevice             *dev,
  GoodixProductionEnrollmentAudit *audit)
{
  GoodixFpImageDevicePrivate *priv;

  g_return_if_fail (GOODIX_IS_FPIMAGE_DEVICE (dev));
  g_return_if_fail (audit != NULL);

  priv = goodix_fpimage_device_get_instance_private (dev);
  if (priv->ctx != NULL)
    {
      goodix_device_context_collect_production_enrollment_audit (
        priv->ctx, audit, FALSE);
      return;
    }
  if (priv->last_production_audit_valid)
    {
      *audit = priv->last_production_audit;
      return;
    }
  *audit = (GoodixProductionEnrollmentAudit) { 0 };
}

gboolean
goodix_device_context_configure_tls (GoodixDeviceContext *ctx,
                                               const guint8 *psk,
                                               gsize psk_length,
                                               GoodixTlsPlaintextFunc plaintext,
                                               gpointer user_data,
                                               GoodixTlsAudit *audit,
                                               GError **error)
{
  g_return_val_if_fail (ctx != NULL && ctx->tls_server == NULL &&
                        ctx->secure_session == NULL, FALSE);
  ctx->tls_plaintext = plaintext;
  ctx->tls_user_data = user_data;
  ctx->tls_server = goodix_tls_server_new (psk, psk_length, context_tls_output,
                                           context_tls_plaintext, ctx, audit,
                                           error);
  return ctx->tls_server != NULL;
}

static void
context_secure_terminal (GoodixSecureSession *session,
                         const GError        *error,
                         gpointer             user_data)
{
  GoodixDeviceContext *ctx = user_data;

  (void) session;
  context_protocol_failure (ctx, error);
}

static gboolean
context_post_tls_image (GoodixPostTlsLifecycle *lifecycle,
                        guint                   acquisition_index,
                        const uint16_t          samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT],
                        gpointer                user_data,
                        GError                **error)
{
  GoodixDeviceContext *ctx = user_data;

  (void) lifecycle;
  (void) acquisition_index;
  if (ctx->operator_epoch)
    {
      GoodixFpImagePipeline *pipeline = NULL;
      GoodixFpImagePipelineResult result;

      result = goodix_fpimage_pipeline_new (
        samples, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT, &pipeline);
      if (result != GOODIX_FPIMAGE_PIPELINE_OK)
        {
          g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                       "FpImage pipeline failed with result %u", result);
          return FALSE;
        }
      goodix_fpimage_pipeline_free (pipeline);
      return TRUE;
    }
#ifdef GOODIX_LIBFPRINT_SIGFM
  {
    uint16_t baseline[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
    GoodixFpImagePipeline *pipeline = NULL;
    GoodixFpImagePipelineResult result;
    FpImage *image;

    if (!goodix_post_tls_lifecycle_copy_baseline (lifecycle, baseline))
      {
        g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                             "SIGFM capture has no session baseline");
        return FALSE;
      }
    result = goodix_fpimage_pipeline_new_sigfm (
      baseline, G_N_ELEMENTS (baseline), samples,
      GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT, &pipeline);
    OPENSSL_cleanse (baseline, sizeof baseline);
    if (result != GOODIX_FPIMAGE_PIPELINE_OK)
      {
        g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                     "SIGFM FpImage pipeline failed with result %u", result);
        return FALSE;
      }
    image = goodix_fpimage_pipeline_get_image (pipeline);
    fpi_image_device_image_captured (FP_IMAGE_DEVICE (ctx->device),
                                     g_object_ref (image));
    goodix_fpimage_pipeline_free (pipeline);
  }
#else
  goodix_device_context_emit_image_ready (
    ctx, samples, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
#endif
  if (ctx->terminal_fence)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                           "FpImage pipeline or framework delivery failed");
      return FALSE;
    }
  return TRUE;
}

static void
context_post_tls_finger_down (GoodixPostTlsLifecycle *lifecycle,
                              gpointer                user_data)
{
  GoodixDeviceContext *ctx = user_data;

  (void) lifecycle;
  if (!ctx->operator_epoch)
    goodix_device_context_emit_finger_down (ctx);
}

static void
context_post_tls_release_tail (GoodixPostTlsLifecycle *lifecycle,
                               gpointer                user_data)
{
  GoodixDeviceContext *ctx = user_data;

  (void) lifecycle;
  ctx->fresh_down_table = TRUE;
  if (ctx->operator_epoch)
    ctx->release_tail_complete = TRUE;
  else
    goodix_device_context_emit_release_tail_complete (ctx);
}

static void
context_post_tls_finger_up (GoodixPostTlsLifecycle *lifecycle,
                            gpointer                user_data)
{
  GoodixDeviceContext *ctx = user_data;

  (void) lifecycle;
  if (!ctx->operator_epoch)
    goodix_device_context_emit_finger_up_ready (ctx);
}

static void
context_post_tls_terminal (GoodixPostTlsLifecycle *lifecycle,
                           const GError           *error,
                           gpointer                user_data)
{
  GoodixDeviceContext *ctx = user_data;

  (void) lifecycle;
  context_protocol_failure (ctx, error);
}

static void
context_post_tls_plaintext (GBytes   *bytes,
                            gpointer  user_data)
{
  GoodixDeviceContext *ctx = user_data;

  if (ctx->terminal_fence)
    return;
  if (ctx->enrollment_binding != NULL)
    {
      g_autoptr(GError) error = NULL;

      if (!goodix_enrollment_fpi_usb_binding_handle_plaintext_chunk (
            ctx->enrollment_binding, bytes, &error))
        context_protocol_failure (ctx, error);
    }
  else if (ctx->post_tls_lifecycle != NULL)
    goodix_post_tls_lifecycle_handle_plaintext (ctx->post_tls_lifecycle, bytes);
}

static gboolean
context_enrollment_image (GoodixEnrollmentPipeline *pipeline,
                          guint                     stage_index,
                          FpImage                  *image,
                          gpointer                  user_data,
                          GError                  **error)
{
  GoodixDeviceContext *ctx = user_data;

  (void) pipeline;
  (void) stage_index;
  if (ctx->terminal_fence || image == NULL)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "enrollment image reached a fenced context");
      return FALSE;
    }
  if (!ctx->operator_epoch)
    {
#ifdef GOODIX_LIBFPRINT_SIGFM
      GoodixFpImagePipeline *sigfm_pipeline = NULL;
      GoodixFpImagePipelineResult result;
      const uint16_t *samples;
      size_t sample_count = 0u;

      samples = goodix_enrollment_pipeline_get_pending_source_samples (
        pipeline, &sample_count);
      if (!ctx->sigfm_baseline_valid || samples == NULL)
        {
          g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                               "SIGFM enrollment image lacks baseline or source raster");
          return FALSE;
        }
      result = goodix_fpimage_pipeline_new_sigfm (
        ctx->sigfm_baseline, G_N_ELEMENTS (ctx->sigfm_baseline),
        samples, sample_count, &sigfm_pipeline);
      if (result != GOODIX_FPIMAGE_PIPELINE_OK)
        {
          g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                       "SIGFM enrollment preprocessing failed: %u", result);
          return FALSE;
        }
      fpi_image_device_image_captured (
        FP_IMAGE_DEVICE (ctx->device),
        g_object_ref (goodix_fpimage_pipeline_get_image (sigfm_pipeline)));
      goodix_fpimage_pipeline_free (sigfm_pipeline);
#else
      fpi_image_device_image_captured (FP_IMAGE_DEVICE (ctx->device),
                                       g_object_ref (image));
#endif
    }
  return !ctx->terminal_fence;
}

static gboolean
context_enrollment_timestamp (guint                           stage_index,
                              GoodixEnrollmentCommandPurpose  purpose,
                              guint16                        *timestamp,
                              gpointer                        user_data,
                              GError                        **error)
{
  GoodixDeviceContext *ctx = user_data;

  (void) stage_index;
  (void) purpose;
  if (ctx->terminal_fence || timestamp == NULL)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "enrollment timestamp reached a fenced context");
      return FALSE;
    }
  *timestamp = production_timestamp ();
  return TRUE;
}

static gboolean
context_enrollment_auxiliary (GBytes   *plaintext,
                              gpointer  user_data,
                              GError  **error)
{
  GoodixDeviceContext *ctx = user_data;

  if (ctx->terminal_fence || ctx->enrollment_auxiliary == NULL)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "auxiliary enrollment B0 has no active consumer");
      return FALSE;
    }
  return ctx->enrollment_auxiliary (
    plaintext, ctx->enrollment_auxiliary_data, error);
}

static gboolean
context_enrollment_contact (guint      stage_index,
                            gboolean   present,
                            gpointer   user_data,
                            GError   **error)
{
  GoodixDeviceContext *ctx = user_data;

  (void) stage_index;
  if (ctx->terminal_fence)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "enrollment contact reached a fenced context");
      return FALSE;
    }
  if (present)
    {
      if (!ctx->operator_epoch)
        goodix_device_context_emit_finger_down (ctx);
    }
  else
    {
      ctx->fresh_down_table = TRUE;
      ctx->release_tail_complete = TRUE;
      if (!ctx->operator_epoch)
        goodix_device_context_emit_finger_up_ready (ctx);
    }
  return !ctx->terminal_fence;
}

static gboolean
context_enrollment_ready (GoodixEnrollmentFpiUsbBinding *binding,
                          gpointer                       user_data,
                          GError                       **error)
{
  GoodixDeviceContext *ctx = user_data;

  if (ctx->terminal_fence || binding != ctx->enrollment_binding ||
      !goodix_enrollment_fpi_usb_binding_needs_receive (binding))
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "enrollment receive continuation is not current");
      return FALSE;
    }
  return goodix_device_context_arm_receive (ctx, error);
}

static gboolean
context_enrollment_first_arm_handoff (GoodixPostTlsLifecycle *lifecycle,
                                      GoodixFpiUsbBackend    *backend,
                                      guint64                 generation,
                                      gpointer                user_data,
                                      GError                **error)
{
  GoodixDeviceContext *ctx = user_data;
  GoodixEnrollmentFpiUsbBinding *binding;

  if (ctx->terminal_fence || lifecycle != ctx->post_tls_lifecycle ||
      backend != ctx->fpi_usb_backend || generation != ctx->generation ||
      ctx->pending_enrollment_events == NULL ||
      ctx->enrollment_binding != NULL ||
      !goodix_fpi_usb_backend_is_drained (backend))
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "enrollment first-arm handoff preconditions failed");
      return FALSE;
    }
#ifdef GOODIX_LIBFPRINT_SIGFM
  if (!goodix_post_tls_lifecycle_copy_baseline (
        lifecycle, ctx->sigfm_baseline))
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                           "enrollment handoff has no decoded SIGFM baseline");
      return FALSE;
    }
  ctx->sigfm_baseline_valid = TRUE;
#endif
  binding = goodix_enrollment_fpi_usb_binding_new (
    ctx->pending_enrollment_events, backend, generation,
    ctx->enrollment_binding_audit, error);
  if (binding == NULL)
    return FALSE;
  ctx->pending_enrollment_events = NULL;
  ctx->enrollment_binding = binding;
  return goodix_enrollment_fpi_usb_binding_set_ready_callback (
    binding, context_enrollment_ready, ctx, error);
}

static void
context_secure_phase (GoodixSecureSession *session,
                      GoodixSecurePhase    phase,
                      guint64              generation,
                      gpointer             user_data)
{
  GoodixDeviceContext *ctx = user_data;
  g_autoptr(GError) error = NULL;

  if (generation == ctx->generation && ctx->phase_observer != NULL)
    ctx->phase_observer (phase, generation, ctx->phase_observer_data);
  if (phase != GOODIX_SECURE_PHASE_STOP || generation != ctx->generation ||
      ctx->terminal_fence || ctx->post_tls_lifecycle == NULL)
    return;
  goodix_secure_session_set_post_tls_plaintext_callback (
    session, context_post_tls_plaintext, ctx);
  if (!goodix_secure_session_handoff_backend (session, &error) ||
      !goodix_post_tls_lifecycle_start (ctx->post_tls_lifecycle, &error))
    context_protocol_failure (ctx, error);
}

gboolean
goodix_device_context_configure_post_tls_lifecycle (
  GoodixDeviceContext         *ctx,
  const GoodixPostTlsMaterial *material,
  GoodixPostTlsAudit          *audit,
  GError                     **error)
{
  if (ctx == NULL || material == NULL || ctx->generation == 0 ||
      ctx->terminal_fence || ctx->post_tls_lifecycle != NULL ||
      ctx->secure_session != NULL)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "GoodixDeviceContext cannot configure post-TLS lifecycle");
      return FALSE;
    }
  ctx->post_tls_lifecycle = goodix_post_tls_lifecycle_new (
    ctx->fpi_usb_backend, ctx->generation, material, context_post_tls_image,
    context_post_tls_finger_down, context_post_tls_release_tail,
    context_post_tls_finger_up, context_post_tls_terminal, ctx, audit, error);
  return ctx->post_tls_lifecycle != NULL;
}

gboolean
goodix_device_context_configure_enrollment_graph (
  GoodixDeviceContext                *ctx,
  const GoodixEnrollmentModelConfig  *config,
  GoodixEnrollmentAuxiliaryB0Func     auxiliary_ready,
  gpointer                            auxiliary_data,
  GoodixEnrollmentPostTlsEventsAudit *events_audit,
  GoodixEnrollmentFpiUsbBindingAudit *binding_audit,
  GError                            **error)
{
  GoodixEnrollmentPostTlsEvents *events;

  if (ctx == NULL || config == NULL || auxiliary_ready == NULL ||
      ctx->generation == 0u || ctx->terminal_fence ||
      ctx->post_tls_lifecycle == NULL ||
      goodix_post_tls_lifecycle_get_phase (ctx->post_tls_lifecycle) !=
        GOODIX_POST_TLS_PHASE_NOT_STARTED ||
      ctx->secure_session != NULL || ctx->pending_enrollment_events != NULL ||
      ctx->enrollment_binding != NULL)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "GoodixDeviceContext cannot configure enrollment graph");
      return FALSE;
    }
  events = goodix_enrollment_post_tls_events_new (
    config, context_enrollment_image, context_enrollment_timestamp,
    context_enrollment_auxiliary, ctx, events_audit, error);
  if (events == NULL)
    return FALSE;
  if (!goodix_enrollment_post_tls_events_set_contact_callback (
        events, context_enrollment_contact, ctx, error) ||
      !goodix_post_tls_lifecycle_set_first_arm_handoff (
        ctx->post_tls_lifecycle, context_enrollment_first_arm_handoff, error))
    {
      goodix_enrollment_post_tls_events_free (events);
      return FALSE;
    }
  ctx->pending_enrollment_events = events;
  ctx->enrollment_auxiliary = auxiliary_ready;
  ctx->enrollment_auxiliary_data = auxiliary_data;
  ctx->enrollment_binding_audit = binding_audit;
  return TRUE;
}

gboolean
goodix_device_context_has_pending_enrollment_graph (GoodixDeviceContext *ctx)
{
  return ctx != NULL && ctx->pending_enrollment_events != NULL;
}

gboolean
goodix_device_context_start_secure_session (
  GoodixDeviceContext               *ctx,
  const GoodixSecureSessionMaterial *material,
  GoodixSecureSessionScheduleFunc    schedule,
  gpointer                           schedule_data,
  GoodixSecureSessionAudit          *audit,
  GoodixTlsAudit                    *tls_audit,
  GError                           **error)
{
  if (ctx == NULL || ctx->secure_session != NULL || ctx->tls_server != NULL ||
      ctx->generation == 0 || ctx->terminal_fence ||
      ((ctx->operator_epoch ||
        goodix_fpimage_device_is_production_usb (ctx->device)) &&
       ctx->pre_session_rx_sync_audit.pre_session_rx_result !=
         GOODIX_PRE_SESSION_RX_SYNC_PASS))
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "GoodixDeviceContext cannot start secure session");
      return FALSE;
    }
  ctx->secure_session = goodix_secure_session_new (
    ctx->fpi_usb_backend, ctx->generation, material, schedule, schedule_data,
    context_secure_terminal, ctx, audit, tls_audit, error);
  if (ctx->secure_session == NULL)
    return FALSE;
  if (ctx->post_tls_lifecycle != NULL)
    goodix_secure_session_set_phase_callback (ctx->secure_session,
                                              context_secure_phase, ctx);
  if (!goodix_secure_session_start (ctx->secure_session, error) ||
      !goodix_device_context_arm_receive (ctx, error))
    {
      goodix_secure_session_cancel (ctx->secure_session,
                                    "secure-session start/receive failed");
      return FALSE;
    }
  return TRUE;
}

GoodixSecureSession *
goodix_device_context_get_secure_session (GoodixDeviceContext *ctx)
{
  return ctx != NULL ? ctx->secure_session : NULL;
}

GoodixPostTlsLifecycle *
goodix_device_context_get_post_tls_lifecycle (GoodixDeviceContext *ctx)
{
  return ctx != NULL ? ctx->post_tls_lifecycle : NULL;
}

#ifdef GOODIX_ENABLE_TEST_SEAMS
void
goodix_device_context_set_usb_submit_seam (GoodixDeviceContext *ctx,
                                            GoodixUsbSubmitSeam seam,
                                            gpointer user_data)
{
  g_return_if_fail (ctx != NULL);
  goodix_fpi_usb_backend_set_submit_seam (ctx->fpi_usb_backend, seam, user_data);
}

void
goodix_device_context_set_async_usb_submit_seam (GoodixDeviceContext *ctx,
                                                  GoodixUsbSubmitSeam seam,
                                                  gpointer user_data)
{
  g_return_if_fail (ctx != NULL);
  goodix_fpi_usb_backend_set_async_submit_seam (ctx->fpi_usb_backend, seam,
                                                user_data);
}
#endif

gboolean
goodix_device_context_arm_receive (GoodixDeviceContext *ctx, GError **error)
{
  g_return_val_if_fail (ctx != NULL, FALSE);
  return goodix_fpi_usb_backend_arm_receive (ctx->fpi_usb_backend,
                                             ctx->generation, error);
}

#ifdef GOODIX_ENABLE_TEST_SEAMS
void
goodix_device_context_complete_receive (GoodixDeviceContext *ctx,
                                         guint64 submit_generation,
                                         const guint8 *data, gsize length,
                                         const GError *error)
{
  g_return_if_fail (ctx != NULL);
  /* Host/test injection seam.  The real backend completion path invokes the
   * registered in-completed callback, which performs receive re-arming so that
   * both synthetic and production IN completions share one follow-up policy. */
  goodix_fpi_usb_backend_complete_receive (ctx->fpi_usb_backend,
                                           submit_generation, data, length,
                                           error);
}
#endif

void
goodix_device_context_set_post_tls_await_finger_on (GoodixDeviceContext *ctx,
                                                    gboolean             awaiting)
{
  g_return_if_fail (ctx != NULL);
  if (ctx->post_tls_lifecycle != NULL)
    goodix_post_tls_lifecycle_set_framework_await_finger_on (
      ctx->post_tls_lifecycle, ctx->generation, awaiting);
}

void
goodix_device_context_set_secure_phase_observer (
  GoodixDeviceContext                    *ctx,
  GoodixDeviceContextSecurePhaseObserver  observer,
  gpointer                                user_data)
{
  g_return_if_fail (ctx != NULL);
  ctx->phase_observer = observer;
  ctx->phase_observer_data = user_data;
}

#ifdef GOODIX_ENABLE_TEST_SEAMS
gboolean
goodix_device_context_begin_operator_epoch (GoodixDeviceContext *ctx,
                                             GCancellable        *cancellable,
                                             GError             **error)
{
  if (ctx == NULL || cancellable == NULL || ctx->operator_epoch ||
      ctx->generation != 0 || ctx->secure_session != NULL ||
      ctx->post_tls_lifecycle != NULL || ctx->poisoned)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "Goodix operator epoch cannot begin");
      return FALSE;
    }

  ctx->generation_seq++;
  if (ctx->generation_seq == 0)
    ctx->generation_seq++;
  ctx->generation = ctx->generation_seq;
  ctx->terminal_fence = FALSE;
  ctx->operator_epoch = TRUE;
  memset (&ctx->pre_session_rx_sync_audit, 0,
          sizeof ctx->pre_session_rx_sync_audit);
  ctx->pre_session_rx_sync_out_count_at_pass = 0;
  g_set_object (&ctx->usb_cancellable, cancellable);
  if (!goodix_fpi_usb_backend_begin_generation (ctx->fpi_usb_backend,
                                                ctx->generation,
                                                ctx->usb_cancellable, error))
    {
      ctx->operator_epoch = FALSE;
      ctx->generation = 0;
      return FALSE;
    }
  goodix_usb_router_begin_generation (ctx->usb_router, ctx->generation);
  goodix_device_context_set_state (ctx, GOODIX_DEVICE_CONTEXT_STATE_ACTIVE);
  return TRUE;
}
#endif

gboolean
goodix_device_context_begin_pre_session_rx_sync (GoodixDeviceContext *ctx,
                                                  GError **error)
{
  g_autoptr(GError) local_error = NULL;

  if (ctx == NULL ||
      (!ctx->operator_epoch &&
       !(goodix_fpimage_device_is_production_usb (ctx->device) &&
         ctx->state == GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING)) ||
      ctx->generation == 0 ||
      ctx->terminal_fence || ctx->secure_session != NULL ||
      ctx->pre_session_rx_sync_audit.pre_session_rx_result !=
        GOODIX_PRE_SESSION_RX_SYNC_NOT_STARTED)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "pre-session RX sync cannot begin");
      return FALSE;
    }

  memset (&ctx->pre_session_rx_sync_audit, 0,
          sizeof ctx->pre_session_rx_sync_audit);
  ctx->pre_session_rx_sync_audit.pre_session_rx_sync_started = TRUE;
  ctx->pre_session_rx_sync_audit.pre_session_rx_result =
    GOODIX_PRE_SESSION_RX_SYNC_ACTIVE;
  ctx->pre_session_rx_sync_started_us = pre_session_rx_sync_now (ctx);
  if (!goodix_fpi_usb_backend_begin_pre_session_sync (
        ctx->fpi_usb_backend, ctx->generation, &local_error) ||
      !goodix_fpi_usb_backend_arm_pre_session_sync_receive (
        ctx->fpi_usb_backend, ctx->generation,
        GOODIX_PRE_SESSION_RX_QUIET_TIMEOUT_MS, &local_error))
    {
      pre_session_rx_sync_fail (ctx, local_error);
      g_propagate_error (error, g_steal_pointer (&local_error));
      return FALSE;
    }
  ctx->pre_session_rx_sync_audit.pre_session_rx_max_outstanding =
    goodix_fpi_usb_backend_get_outstanding (ctx->fpi_usb_backend);
  return TRUE;
}

GoodixPreSessionRxSyncResult
goodix_device_context_get_pre_session_rx_sync_result (GoodixDeviceContext *ctx)
{
  return ctx != NULL ? ctx->pre_session_rx_sync_audit.pre_session_rx_result :
    GOODIX_PRE_SESSION_RX_SYNC_FAIL_CLOSED;
}

void
goodix_device_context_get_pre_session_rx_sync_audit (
  GoodixDeviceContext         *ctx,
  GoodixPreSessionRxSyncAudit *audit)
{
  g_return_if_fail (ctx != NULL && audit != NULL);
  *audit = ctx->pre_session_rx_sync_audit;
  audit->first_protocol_out_after_rx_sync =
    audit->pre_session_rx_result == GOODIX_PRE_SESSION_RX_SYNC_PASS &&
    goodix_fpi_usb_backend_get_out_submit_count (ctx->fpi_usb_backend) >
      ctx->pre_session_rx_sync_out_count_at_pass;
}

const gchar *
goodix_pre_session_rx_sync_result_name (GoodixPreSessionRxSyncResult result)
{
  static const gchar *const names[] = {
    "NOT_STARTED", "ACTIVE", "PASS", "FAIL_CLOSED"
  };

  return (guint) result < G_N_ELEMENTS (names) ? names[result] : "INVALID";
}

#ifdef GOODIX_ENABLE_TEST_SEAMS
void
goodix_device_context_set_pre_session_rx_sync_clock (
  GoodixDeviceContext             *ctx,
  GoodixPreSessionRxSyncClockFunc  clock_func,
  gpointer                         user_data)
{
  g_return_if_fail (ctx != NULL);
  g_return_if_fail (
    ctx->pre_session_rx_sync_audit.pre_session_rx_result !=
      GOODIX_PRE_SESSION_RX_SYNC_ACTIVE);
  ctx->pre_session_rx_sync_clock = clock_func;
  ctx->pre_session_rx_sync_clock_data = user_data;
}

void
goodix_device_context_stop_operator_epoch (GoodixDeviceContext *ctx)
{
  if (ctx == NULL || !ctx->operator_epoch)
    return;
  goodix_device_context_set_terminal_fence (ctx);
  ctx->operator_epoch = FALSE;
  ctx->generation = 0;
  goodix_device_context_set_state (ctx, GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
}

gboolean
goodix_device_context_operator_epoch_is_drained (GoodixDeviceContext *ctx)
{
  return ctx != NULL && goodix_fpi_usb_backend_is_drained (
                          ctx->fpi_usb_backend);
}
#endif

/* --- Context accessors --- */

GoodixDeviceContextState
goodix_device_context_get_state (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->state : GOODIX_DEVICE_CONTEXT_STATE_CLOSED;
}

guint64
goodix_device_context_get_generation (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->generation : 0;
}

gboolean
goodix_device_context_get_terminal_fence (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->terminal_fence : TRUE;
}

gboolean
goodix_device_context_get_release_tail_complete (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->release_tail_complete : FALSE;
}

gboolean
goodix_device_context_get_fresh_down_table (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->fresh_down_table : FALSE;
}

gboolean
goodix_device_context_get_poisoned (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->poisoned : FALSE;
}

const GError *
goodix_device_context_get_terminal_error (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->terminal_error : NULL;
}

guint
goodix_device_context_get_backend_command_count (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->backend.total_command_count : 0;
}

guint
goodix_in_memory_backend_get_arm_count (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->backend.arm_count : 0;
}

guint
goodix_in_memory_backend_get_disarm_count (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->backend.disarm_count : 0;
}

guint
goodix_in_memory_backend_get_rearm_count (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->backend.rearm_count : 0;
}

const gchar *
goodix_in_memory_backend_get_last_command (GoodixDeviceContext *ctx)
{
  return ctx ? ctx->backend.last_command : NULL;
}

void
goodix_device_context_set_fresh_down_table (GoodixDeviceContext *ctx,
                                            gboolean             fresh)
{
  g_return_if_fail (ctx != NULL);
  ctx->fresh_down_table = !!fresh;
  goodix_device_context_maybe_rearm (ctx);
}

void
goodix_device_context_set_deactivation_held (GoodixDeviceContext *ctx,
                                              gboolean             held)
{
  g_return_if_fail (ctx != NULL);
  ctx->deactivation_held = !!held;
}

void
goodix_device_context_complete_deactivation (GoodixDeviceContext *ctx)
{
  g_return_if_fail (ctx != NULL);
  g_return_if_fail (ctx->deactivation_pending);
  g_return_if_fail (ctx->state == GOODIX_DEVICE_CONTEXT_STATE_DEACTIVATING);
  if (!goodix_fpi_usb_backend_is_drained (ctx->fpi_usb_backend))
    return;

  ctx->deactivation_pending = FALSE;
  if (ctx->deactivation_nonquiescent)
    {
      ctx->poisoned = TRUE;
      goodix_device_context_set_state (ctx,
                                       GOODIX_DEVICE_CONTEXT_STATE_POISONED);
    }
  else
    goodix_device_context_set_state (ctx,
                                     GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
  fpi_image_device_deactivate_complete (FP_IMAGE_DEVICE (ctx->device), NULL);
}

/* --- Fake backend event injection --- */

static void
emit_terminal (GoodixDeviceContext *ctx, GError *error)
{
  goodix_device_context_disconnect_cancel_handler (ctx);
  goodix_device_context_set_terminal_fence (ctx);
  goodix_device_context_set_poisoned (ctx, error);
  ctx->generation = 0;

  if (ctx->state == GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING)
    {
      goodix_device_context_set_state (ctx,
                                       GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (ctx->device), error);
    }
  else
    {
      goodix_device_context_set_state (ctx,
                                       GOODIX_DEVICE_CONTEXT_STATE_POISONED);
      fpi_image_device_session_error (FP_IMAGE_DEVICE (ctx->device), error);
    }
}

void
goodix_device_context_emit_arm_complete (GoodixDeviceContext *ctx,
                                         GError              *error)
{
  g_return_if_fail (ctx != NULL);

  if (goodix_device_context_is_stale_or_fenced (ctx))
    return;

  if (ctx->state != GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING)
    return;

  if (error != NULL)
    {
      emit_terminal (ctx, g_error_copy (error));
      return;
    }

  goodix_device_context_disconnect_cancel_handler (ctx);
  ctx->activation_completed = TRUE;
  goodix_device_context_set_state (ctx, GOODIX_DEVICE_CONTEXT_STATE_ACTIVE);
  fpi_image_device_activate_complete (FP_IMAGE_DEVICE (ctx->device), NULL);
}

void
goodix_device_context_emit_finger_down (GoodixDeviceContext *ctx)
{
  goodix_device_context_emit_finger_down_for_generation (
    ctx, ctx != NULL ? ctx->generation : 0);
}

void
goodix_device_context_emit_finger_down_for_generation (GoodixDeviceContext *ctx,
                                                       guint64 generation)
{
  g_return_if_fail (ctx != NULL);

  if (goodix_device_context_is_stale_or_fenced (ctx) ||
      generation != ctx->generation)
    return;

  fpi_image_device_report_finger_status (FP_IMAGE_DEVICE (ctx->device), TRUE);
}

void
goodix_device_context_emit_image_ready (GoodixDeviceContext *ctx,
                                        const uint16_t      *samples,
                                        size_t               sample_count)
{
  GoodixFpImagePipeline *pipeline = NULL;
  GoodixFpImagePipelineResult result;
  FpImage *image;

  g_return_if_fail (ctx != NULL);

  if (goodix_device_context_is_stale_or_fenced (ctx))
    return;

  result = goodix_fpimage_pipeline_new (samples, sample_count, &pipeline);
  if (result != GOODIX_FPIMAGE_PIPELINE_OK)
    {
      g_autoptr(GError) error = NULL;
      error = g_error_new (FP_DEVICE_ERROR, FP_DEVICE_ERROR_DATA_INVALID,
                           "Goodix fake image pipeline failed: %d", result);
      emit_terminal (ctx, g_steal_pointer (&error));
      return;
    }

  image = goodix_fpimage_pipeline_get_image (pipeline);
  g_assert (image != NULL);

  /* Transfer an independent reference to FpImageDevice; the pipeline keeps its own. */
  fpi_image_device_image_captured (FP_IMAGE_DEVICE (ctx->device),
                                   g_object_ref (image));

  goodix_fpimage_pipeline_free (pipeline);
}

#ifdef GOODIX_LIBFPRINT_SIGFM
void
goodix_device_context_emit_sigfm_image_ready (GoodixDeviceContext *ctx,
                                              const uint16_t      *baseline,
                                              const uint16_t      *samples,
                                              size_t               sample_count)
{
  GoodixFpImagePipeline *pipeline = NULL;
  GoodixFpImagePipelineResult result;

  g_return_if_fail (ctx != NULL);
  if (goodix_device_context_is_stale_or_fenced (ctx))
    return;
  result = goodix_fpimage_pipeline_new_sigfm (
    baseline, sample_count, samples, sample_count, &pipeline);
  if (result != GOODIX_FPIMAGE_PIPELINE_OK)
    {
      emit_terminal (ctx, g_error_new (
        FP_DEVICE_ERROR, FP_DEVICE_ERROR_DATA_INVALID,
        "Goodix SIGFM image pipeline failed: %d", result));
      return;
    }
  fpi_image_device_image_captured (
    FP_IMAGE_DEVICE (ctx->device),
    g_object_ref (goodix_fpimage_pipeline_get_image (pipeline)));
  goodix_fpimage_pipeline_free (pipeline);
}
#endif

void
goodix_device_context_emit_release_tail_complete (GoodixDeviceContext *ctx)
{
  g_return_if_fail (ctx != NULL);

  if (goodix_device_context_is_stale_or_fenced (ctx))
    return;

  ctx->release_tail_complete = TRUE;
}

void
goodix_device_context_emit_finger_up_ready (GoodixDeviceContext *ctx)
{
  g_return_if_fail (ctx != NULL);

  if (goodix_device_context_is_stale_or_fenced (ctx))
    return;

  /* Release tail must complete before libfprint sees finger-off. */
  if (!ctx->release_tail_complete)
    return;

  fpi_image_device_report_finger_status (FP_IMAGE_DEVICE (ctx->device), FALSE);
}

void
goodix_device_context_emit_cancelled (GoodixDeviceContext *ctx)
{
  g_return_if_fail (ctx != NULL);

  if (goodix_device_context_is_stale_or_fenced (ctx))
    return;

  /* Cancellation is modelled as a terminal fence, not a device-side command. */
  goodix_device_context_set_terminal_fence (ctx);
  ctx->generation = 0;
}

void
goodix_device_context_emit_terminal_error (GoodixDeviceContext *ctx,
                                           GError              *error)
{
  g_return_if_fail (ctx != NULL);
  g_return_if_fail (error != NULL);

  if (goodix_device_context_is_stale_or_fenced (ctx))
    return;

  emit_terminal (ctx, g_error_copy (error));
}
