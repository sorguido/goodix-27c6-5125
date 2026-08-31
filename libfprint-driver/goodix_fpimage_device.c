/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Host-only FpImageDevice shell for the Goodix 27c6:5125 boundary.
 *
 * This file implements the first production-shaped slice of the libfprint
 * device glue with an in-memory fake backend and the production-shaped USB
 * router, TLS server, USB backend and secure-session integration.  It still
 * contains no fprintd, persistent-write or real sensor execution path.
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

#include "fpi-device.h"
#include "fpi-image-device.h"
#include "fp-device.h"
#include "fp-image-device-private.h"

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
  GoodixTlsPlaintextFunc     tls_plaintext;
  gpointer                   tls_user_data;
  guint                      a0_delivery_count;

  FpiImageDeviceState        last_framework_state;

  GError                  *terminal_error;
};

struct _GoodixFpImageDevice
{
  FpImageDevice parent_instance;
  GoodixDeviceContext *ctx;
};

G_DEFINE_TYPE (GoodixFpImageDevice, goodix_fpimage_device, FP_TYPE_IMAGE_DEVICE)

static void goodix_device_context_set_terminal_fence (GoodixDeviceContext *ctx);
static void goodix_device_context_set_poisoned (GoodixDeviceContext *ctx,
                                                const GError        *error);
static void
context_usb_drained (GoodixFpiUsbBackend *backend,
                     gpointer             user_data)
{
  GoodixDeviceContext *ctx = user_data;
  (void) backend;
  if (ctx->deactivation_pending && !ctx->deactivation_held)
    goodix_device_context_complete_deactivation (ctx);
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

static void context_a0_consumer (guint8 type, GBytes *frame, gpointer user_data)
{
  GoodixDeviceContext *ctx = user_data;
  if (type != 0xa0 || ctx->terminal_fence)
    return;
  ctx->a0_delivery_count++;
  if (ctx->post_tls_lifecycle != NULL &&
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

  return ctx;
}

static void
goodix_device_context_free (GoodixDeviceContext *ctx)
{
  if (ctx == NULL)
    return;

  g_clear_object (&ctx->activation_cancellable);
  g_clear_object (&ctx->usb_cancellable);
  g_clear_error (&ctx->terminal_error);
  g_free (ctx->backend.last_command);
  goodix_post_tls_lifecycle_free (ctx->post_tls_lifecycle);
  goodix_secure_session_free (ctx->secure_session);
  goodix_tls_server_free (ctx->tls_server);
  g_return_if_fail (goodix_fpi_usb_backend_is_drained (ctx->fpi_usb_backend));
  goodix_fpi_usb_backend_free (ctx->fpi_usb_backend);
  goodix_usb_router_free (ctx->usb_router);
  g_free (ctx);
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
  if (ctx->secure_session != NULL)
    goodix_secure_session_cancel (ctx->secure_session,
                                  "GoodixDeviceContext terminal fence");
  if (ctx->post_tls_lifecycle != NULL)
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
  GoodixDeviceContext *ctx = self->ctx;
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
  GoodixDeviceContext *ctx = self->ctx;
  g_autoptr(GError) error = NULL;
  GCancellable *cancellable;

  cancellable = fpi_device_get_cancellable (FP_DEVICE (self));
  if (g_cancellable_set_error_if_cancelled (cancellable, &error))
    {
      goodix_device_context_set_state (ctx,
                                       GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
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

  g_assert (self->ctx != NULL);
  g_assert (self->ctx->state == GOODIX_DEVICE_CONTEXT_STATE_OPENING);

  goodix_device_context_set_state (self->ctx,
                                   GOODIX_DEVICE_CONTEXT_STATE_OPENING);
  g_object_ref (self);
  g_idle_add (open_complete_idle, self);
}

static void
goodix_fpimage_device_img_close (FpImageDevice *dev)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (dev);

  g_assert (self->ctx != NULL);
  g_assert (self->ctx->state != GOODIX_DEVICE_CONTEXT_STATE_CLOSING);

  goodix_device_context_set_terminal_fence (self->ctx);
  goodix_device_context_set_state (self->ctx,
                                   GOODIX_DEVICE_CONTEXT_STATE_CLOSING);

  goodix_device_context_free (self->ctx);
  self->ctx = NULL;

  fpi_image_device_close_complete (dev, NULL);
}

static void
goodix_fpimage_device_activate (FpImageDevice *dev)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (dev);
  GoodixDeviceContext *ctx = self->ctx;

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
  ctx->backend_vtable->arm (ctx, ctx->backend_user_data);
}

static void
goodix_fpimage_device_change_state (FpImageDevice      *dev,
                                    FpiImageDeviceState  state)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (dev);
  GoodixDeviceContext *ctx = self->ctx;

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
  GoodixDeviceContext *ctx = self->ctx;

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

  goodix_device_context_free (self->ctx);
  self->ctx = NULL;

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

  img_class->img_open     = goodix_fpimage_device_img_open;
  img_class->img_close    = goodix_fpimage_device_img_close;
  img_class->activate     = goodix_fpimage_device_activate;
  img_class->change_state = goodix_fpimage_device_change_state;
  img_class->deactivate   = goodix_fpimage_device_deactivate;
  img_class->img_width    = (gint) GOODIX_CANONICAL_IMAGE_WIDTH;
  img_class->img_height   = (gint) GOODIX_CANONICAL_IMAGE_HEIGHT;
  img_class->algorithm    = FPI_DEVICE_ALGO_SIGFM;

  fpi_device_class_auto_initialize_features (device_class);
}

static void
goodix_fpimage_device_init (GoodixFpImageDevice *self)
{
  self->ctx = goodix_device_context_new (self);
  goodix_device_context_set_state (self->ctx,
                                   GOODIX_DEVICE_CONTEXT_STATE_OPENING);
}

/* --- Public constructor --- */

GoodixFpImageDevice *
goodix_fpimage_device_new (void)
{
  return g_object_new (GOODIX_TYPE_FPIMAGE_DEVICE, NULL);
}

GoodixDeviceContext *
goodix_fpimage_device_get_context (GoodixFpImageDevice *dev)
{
  g_return_val_if_fail (GOODIX_IS_FPIMAGE_DEVICE (dev), NULL);
  return dev->ctx;
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
  ctx->terminal_fence = TRUE;
  goodix_device_context_set_poisoned (ctx, error);
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
  goodix_device_context_emit_image_ready (
    ctx, samples, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
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
  (void) lifecycle;
  goodix_device_context_emit_finger_down (user_data);
}

static void
context_post_tls_release_tail (GoodixPostTlsLifecycle *lifecycle,
                               gpointer                user_data)
{
  GoodixDeviceContext *ctx = user_data;

  (void) lifecycle;
  ctx->fresh_down_table = TRUE;
  goodix_device_context_emit_release_tail_complete (ctx);
}

static void
context_post_tls_finger_up (GoodixPostTlsLifecycle *lifecycle,
                            gpointer                user_data)
{
  (void) lifecycle;
  goodix_device_context_emit_finger_up_ready (user_data);
}

static void
context_post_tls_terminal (GoodixPostTlsLifecycle *lifecycle,
                           const GError           *error,
                           gpointer                user_data)
{
  GoodixDeviceContext *ctx = user_data;

  (void) lifecycle;
  ctx->terminal_fence = TRUE;
  goodix_device_context_set_poisoned (ctx, error);
}

static void
context_post_tls_plaintext (GBytes   *bytes,
                            gpointer  user_data)
{
  GoodixDeviceContext *ctx = user_data;

  if (!ctx->terminal_fence && ctx->post_tls_lifecycle != NULL)
    goodix_post_tls_lifecycle_handle_plaintext (ctx->post_tls_lifecycle, bytes);
}

static void
context_secure_phase (GoodixSecureSession *session,
                      GoodixSecurePhase    phase,
                      guint64              generation,
                      gpointer             user_data)
{
  GoodixDeviceContext *ctx = user_data;
  g_autoptr(GError) error = NULL;

  if (phase != GOODIX_SECURE_PHASE_STOP || generation != ctx->generation ||
      ctx->terminal_fence || ctx->post_tls_lifecycle == NULL)
    return;
  goodix_secure_session_set_post_tls_plaintext_callback (
    session, context_post_tls_plaintext, ctx);
  if (!goodix_secure_session_handoff_backend (session, &error) ||
      !goodix_post_tls_lifecycle_start (ctx->post_tls_lifecycle, &error))
    {
      goodix_device_context_set_terminal_fence (ctx);
      goodix_device_context_set_poisoned (ctx, error);
    }
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
      ctx->generation == 0 || ctx->terminal_fence)
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

gboolean
goodix_device_context_arm_receive (GoodixDeviceContext *ctx, GError **error)
{
  g_return_val_if_fail (ctx != NULL, FALSE);
  return goodix_fpi_usb_backend_arm_receive (ctx->fpi_usb_backend,
                                             ctx->generation, error);
}

void
goodix_device_context_complete_receive (GoodixDeviceContext *ctx,
                                         guint64 submit_generation,
                                         const guint8 *data, gsize length,
                                         const GError *error)
{
  g_return_if_fail (ctx != NULL);
  goodix_fpi_usb_backend_complete_receive (ctx->fpi_usb_backend,
                                           submit_generation, data, length,
                                           error);
  if (((ctx->post_tls_lifecycle != NULL &&
        goodix_post_tls_lifecycle_needs_receive (ctx->post_tls_lifecycle)) ||
       (ctx->secure_session != NULL &&
        goodix_secure_session_needs_receive (ctx->secure_session))) &&
      goodix_fpi_usb_backend_get_outstanding (ctx->fpi_usb_backend) == 0)
    {
      g_autoptr(GError) arm_error = NULL;
      if (!goodix_device_context_arm_receive (ctx, &arm_error))
        {
          goodix_device_context_set_terminal_fence (ctx);
          goodix_device_context_set_poisoned (ctx, arm_error);
        }
    }
}

void
goodix_device_context_set_post_tls_await_finger_on (GoodixDeviceContext *ctx,
                                                    gboolean             awaiting)
{
  g_return_if_fail (ctx != NULL);
  if (ctx->post_tls_lifecycle != NULL)
    goodix_post_tls_lifecycle_set_framework_await_finger_on (
      ctx->post_tls_lifecycle, ctx->generation, awaiting);
}

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
