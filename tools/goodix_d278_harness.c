/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "goodix_d278_harness.h"

#include "goodix_fpi_usb_backend.h"
#include "goodix_usb_router.h"

#include <openssl/crypto.h>
#include <string.h>

#define D278_GENERATION 1u
#define D278_EP_IN 0x81u
#define D278_EP_OUT 0x01u
#define D278_RECEIVE_SIZE 32768u

GoodixTargetMaterial *
goodix_d278_prepare_target_material (
  const gchar                      *manifest_path,
  const gchar                      *transport_path,
  const gchar                      *config90_path,
  const gchar                      *dll_path,
  const GoodixTargetMaterialPolicy *material_policy,
  const GoodixD190PePolicy         *pe_policy,
  GoodixTargetMaterialAudit        *audit,
  GoodixSecureSessionMaterial      *view,
  GoodixD278PreflightFailure       *failure,
  GError                          **error)
{
  GoodixTargetMaterial *owner = NULL;
  guint8 seed_a[GOODIX_D190_PE_SEED_LENGTH] = { 0 };
  guint8 seed_b[GOODIX_D190_PE_SEED_LENGTH] = { 0 };

  g_return_val_if_fail (failure != NULL, NULL);
  failure->failure_stage = "NONE";
  failure->failure_class = "NONE";
  owner = goodix_target_material_load (manifest_path, transport_path,
                                       config90_path, material_policy, audit,
                                       error);
  if (owner == NULL)
    {
      failure->failure_stage = "TARGET_MATERIAL_LOAD";
      failure->failure_class = goodix_target_material_error_class (
        error != NULL ? *error : NULL);
      goto out;
    }
  if (!goodix_d190_pe_extract_with_policy (dll_path, pe_policy, seed_a, seed_b,
                                            error))
    {
      failure->failure_stage = "CANONICAL_PE";
      failure->failure_class = "CANONICAL_PE_OR_DLL";
      goto fail;
    }
  if (!goodix_target_material_bind (owner, seed_a, seed_b, error))
    {
      failure->failure_stage = "E4_BIND";
      failure->failure_class = goodix_target_material_error_class (
        error != NULL ? *error : NULL);
      goto fail;
    }
  if (!goodix_target_material_get_secure_session_material (owner, view, error))
    {
      failure->failure_stage = "MATERIAL_EXPORT";
      failure->failure_class = "MATERIAL_EXPORT_OR_STATE";
      goto fail;
    }
  goto out;

fail:
  goodix_target_material_free (owner);
  owner = NULL;
out:
  goodix_d190_pe_cleanse_seed (seed_a);
  goodix_d190_pe_cleanse_seed (seed_b);
  return owner;
}

typedef struct
{
  GoodixD278Watchdog *watchdog;
  guint64 generation;
  guint64 serial;
} WatchdogToken;

struct _GoodixD278Watchdog
{
  gboolean deterministic;
  gboolean invalidated;
  guint source_id;
  guint64 generation;
  guint64 serial;
  GoodixSecurePhase phase;
  GoodixD278WatchdogTimeoutFunc timeout;
  gpointer user_data;
};

struct _GoodixD278Harness
{
  GoodixUsbRouter *router;
  GoodixFpiUsbBackend *backend;
  GoodixSecureSession *session;
  GCancellable *cancellable;
  GMainLoop *loop;
  GoodixSecureSessionMaterial material;
  GoodixSecureSessionAudit session_audit;
  GoodixTlsAudit tls_audit;
  GoodixD278Watchdog *watchdog;
  GoodixD278Telemetry *telemetry;
  GoodixD278SyntheticSubmitFunc submit;
  GoodixD278SyntheticPacingFunc pacing;
  gpointer user_data;
  GString *phase_trace;
  guint64 generation;
  GoodixSecurePhase last_phase;
  gboolean synthetic;
  gboolean started;
  gboolean terminal;
  gboolean sealed;
};

static gboolean
watchdog_token_dispatch (WatchdogToken *token)
{
  GoodixD278Watchdog *watchdog = token->watchdog;

  if (watchdog->invalidated || token->generation != watchdog->generation ||
      token->serial != watchdog->serial)
    return FALSE;
  watchdog->source_id = 0;
  watchdog->invalidated = TRUE;
  if (watchdog->timeout != NULL)
    watchdog->timeout (watchdog->phase, watchdog->generation,
                       watchdog->user_data);
  return TRUE;
}

static gboolean
watchdog_timeout_cb (gpointer user_data)
{
  watchdog_token_dispatch (user_data);
  return G_SOURCE_REMOVE;
}

guint
goodix_d278_watchdog_timeout_for_phase (GoodixSecurePhase phase)
{
  static const guint bounds[] = {
    1000, 1000, 1000, 1000, 500, 750, 1000, 500,
    250, 250, 250, 250, 1000, 1000, 3000
  };

  return (guint) phase < G_N_ELEMENTS (bounds) ? bounds[phase] : 0;
}

GoodixD278Watchdog *
goodix_d278_watchdog_new (gboolean                      deterministic_test_mode,
                          GoodixD278WatchdogTimeoutFunc timeout,
                          gpointer                      user_data)
{
  GoodixD278Watchdog *watchdog = g_new0 (GoodixD278Watchdog, 1);
  watchdog->deterministic = deterministic_test_mode;
  watchdog->timeout = timeout;
  watchdog->user_data = user_data;
  watchdog->phase = GOODIX_SECURE_PHASE_TERMINAL;
  return watchdog;
}

void
goodix_d278_watchdog_progress (GoodixD278Watchdog *watchdog,
                               GoodixSecurePhase   phase,
                               guint64             generation)
{
  guint timeout_ms;

  g_return_if_fail (watchdog != NULL);
  if (watchdog->invalidated || generation == 0 ||
      phase >= GOODIX_SECURE_PHASE_STOP)
    return;
  if (watchdog->generation == generation && watchdog->phase == phase &&
      watchdog->serial != 0)
    return;
  if (watchdog->source_id != 0 && !watchdog->deterministic)
    g_source_remove (watchdog->source_id);
  watchdog->source_id = 0;
  watchdog->generation = generation;
  watchdog->phase = phase;
  watchdog->serial++;
  timeout_ms = goodix_d278_watchdog_timeout_for_phase (phase);
  if (timeout_ms == 0)
    {
      watchdog->invalidated = TRUE;
      return;
    }
  if (watchdog->deterministic)
    watchdog->source_id = 1;
  else
    {
      WatchdogToken *token = g_new0 (WatchdogToken, 1);
      token->watchdog = watchdog;
      token->generation = generation;
      token->serial = watchdog->serial;
      watchdog->source_id = g_timeout_add_full (
        G_PRIORITY_DEFAULT, timeout_ms, watchdog_timeout_cb, token, g_free);
    }
}

void
goodix_d278_watchdog_invalidate (GoodixD278Watchdog *watchdog)
{
  if (watchdog == NULL || watchdog->invalidated)
    return;
  watchdog->invalidated = TRUE;
  if (watchdog->source_id != 0 && !watchdog->deterministic)
    g_source_remove (watchdog->source_id);
  watchdog->source_id = 0;
  watchdog->serial++;
}

void
goodix_d278_watchdog_free (GoodixD278Watchdog *watchdog)
{
  if (watchdog == NULL)
    return;
  goodix_d278_watchdog_invalidate (watchdog);
  g_free (watchdog);
}

guint64
goodix_d278_watchdog_get_serial (const GoodixD278Watchdog *watchdog)
{
  return watchdog != NULL ? watchdog->serial : 0;
}

void
goodix_d278_watchdog_fire_for_test (GoodixD278Watchdog *watchdog,
                                    guint64             generation,
                                    guint64             serial)
{
  WatchdogToken token = { watchdog, generation, serial };

  g_return_if_fail (watchdog != NULL && watchdog->deterministic);
  watchdog_token_dispatch (&token);
}

void
goodix_d278_telemetry_init (GoodixD278Telemetry *telemetry,
                            gboolean             live_mode)
{
  g_return_if_fail (telemetry != NULL);
  memset (telemetry, 0, sizeof *telemetry);
  g_strlcpy (telemetry->result, "pending", sizeof telemetry->result);
  g_strlcpy (telemetry->failure_class, "none",
             sizeof telemetry->failure_class);
  g_strlcpy (telemetry->protocol_failure_kind, "none",
             sizeof telemetry->protocol_failure_kind);
  g_strlcpy (telemetry->reentry_recovery_a2_result_class, "NOT_STARTED",
             sizeof telemetry->reentry_recovery_a2_result_class);
  telemetry->reached_phase = GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2;
  telemetry->protocol_failure_phase = GOODIX_SECURE_PHASE_TERMINAL;
  telemetry->observed_outer_type = -1;
  telemetry->observed_a0_control = -1;
  telemetry->observed_ack_echo = -1;
  telemetry->observed_ack_status = -1;
  telemetry->observed_body_length = -1;
  telemetry->current_live_authorized = live_mode;
}

static void
set_failure (GoodixD278Harness *harness,
             const gchar       *failure_class)
{
  if (g_str_equal (harness->telemetry->failure_class, "none"))
    g_strlcpy (harness->telemetry->failure_class, failure_class,
               sizeof harness->telemetry->failure_class);
  g_strlcpy (harness->telemetry->result, "fail",
             sizeof harness->telemetry->result);
}

static void
watchdog_expired (GoodixSecurePhase phase,
                  guint64           generation,
                  gpointer          user_data)
{
  GoodixD278Harness *harness = user_data;
  g_autofree gchar *failure = NULL;

  if (harness->terminal || generation != harness->generation)
    return;
  failure = g_strdup_printf ("PHASE_TIMEOUT_%s",
                             goodix_secure_phase_name (phase));
  set_failure (harness, failure);
  harness->terminal = TRUE;
  goodix_secure_session_cancel (harness->session, failure);
}

static void
phase_changed (GoodixSecureSession *session,
               GoodixSecurePhase    phase,
               guint64              generation,
               gpointer             user_data)
{
  GoodixD278Harness *harness = user_data;
  g_autoptr(GError) arm_error = NULL;

  (void) session;
  if (generation != harness->generation)
    return;
  if (harness->phase_trace->len == 0 || phase != harness->last_phase)
    {
      if (harness->phase_trace->len != 0)
        g_string_append_c (harness->phase_trace, ',');
      g_string_append (harness->phase_trace, goodix_secure_phase_name (phase));
      harness->last_phase = phase;
      harness->telemetry->reached_phase = phase;
    }
  if (phase < GOODIX_SECURE_PHASE_STOP)
    {
      goodix_d278_watchdog_progress (harness->watchdog, phase, generation);
      if (goodix_fpi_usb_backend_get_outstanding (harness->backend) == 0 &&
          !goodix_fpi_usb_backend_arm_receive (harness->backend, generation,
                                                &arm_error))
        {
          set_failure (harness, "SEQUENTIAL_IN_ARM_FAILED");
          goodix_secure_session_cancel (session,
                                        "sequential receive arm failed");
          return;
        }
    }
  else
    goodix_d278_watchdog_invalidate (harness->watchdog);
  if (phase == GOODIX_SECURE_PHASE_STOP)
    {
      g_strlcpy (harness->telemetry->result, "pass",
                 sizeof harness->telemetry->result);
      harness->terminal = TRUE;
      goodix_fpi_usb_backend_cancel (harness->backend);
    }
  else if (phase == GOODIX_SECURE_PHASE_TERMINAL)
    harness->terminal = TRUE;
}

static void
session_terminal (GoodixSecureSession *session,
                  const GError        *error,
                  gpointer             user_data)
{
  GoodixD278Harness *harness = user_data;

  (void) session;
  if (g_str_equal (harness->telemetry->failure_class, "none"))
    set_failure (harness,
                 error != NULL ? "SECURE_SESSION_TERMINAL" :
                                 "SECURE_SESSION_CANCELLED");
  harness->terminal = TRUE;
  goodix_d278_watchdog_invalidate (harness->watchdog);
}

static void
a0_consumer (guint8   type,
             GBytes  *frame,
             gpointer user_data)
{
  GoodixD278Harness *harness = user_data;

  if (type == 0xa0 && !harness->terminal)
    goodix_secure_session_handle_a0 (harness->session, frame);
}

static void
b0_consumer (guint8   type,
             GBytes  *frame,
             gpointer user_data)
{
  GoodixD278Harness *harness = user_data;

  if (type == 0xb0 && !harness->terminal)
    goodix_secure_session_handle_b0 (harness->session, frame);
}

static void
synthetic_submit (GoodixFpiUsbBackend *backend,
                  GoodixUsbDirection   direction,
                  guint64              generation,
                  GBytes              *bytes,
                  gpointer             user_data)
{
  GoodixD278Harness *harness = user_data;

  (void) backend;
  if (direction == GOODIX_USB_TRANSFER_IN)
    harness->telemetry->synthetic_in_submit_count++;
  else
    harness->telemetry->synthetic_out_submit_count++;
  if (harness->submit != NULL)
    harness->submit (harness, direction, generation, bytes,
                     harness->user_data);
}

static void
pacing_scheduled (GoodixSecureSession *session,
                  guint64              generation,
                  guint                delay_ms,
                  gpointer             user_data)
{
  GoodixD278Harness *harness = user_data;

  (void) session;
  if (harness->pacing != NULL)
    harness->pacing (harness, generation, delay_ms, harness->user_data);
}

static void
backend_drained (GoodixFpiUsbBackend *backend,
                 gpointer             user_data)
{
  GoodixD278Harness *harness = user_data;

  (void) backend;
  harness->telemetry->backend_drained = TRUE;
  harness->telemetry->terminal_cleanup_completed = harness->terminal;
  if (harness->loop != NULL)
    g_main_loop_quit (harness->loop);
}

static void
in_completed (GoodixFpiUsbBackend *backend,
              guint64              generation,
              const GError        *error,
              gpointer             user_data)
{
  GoodixD278Harness *harness = user_data;
  g_autoptr(GError) arm_error = NULL;

  (void) error;
  if (generation != harness->generation || harness->terminal ||
      !goodix_secure_session_needs_receive (harness->session) ||
      goodix_fpi_usb_backend_get_outstanding (backend) != 0)
    return;
  if (!goodix_fpi_usb_backend_arm_receive (backend, generation, &arm_error))
    {
      set_failure (harness, "SEQUENTIAL_IN_ARM_FAILED");
      goodix_secure_session_cancel (harness->session,
                                    "sequential receive arm failed");
    }
}

GoodixD278Harness *
goodix_d278_harness_new (FpDevice                           *device,
                         const GoodixSecureSessionMaterial *material,
                         gboolean                            synthetic_transport,
                         gboolean                            deterministic_watchdog,
                         GoodixD278SyntheticSubmitFunc       submit,
                         GoodixD278SyntheticPacingFunc       pacing,
                         gpointer                            user_data,
                         GoodixD278Telemetry                *telemetry,
                         GError                            **error)
{
  GoodixD278Harness *harness;

  if (material == NULL || telemetry == NULL ||
      (!synthetic_transport && device == NULL))
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                           "D278 harness argument is invalid");
      return NULL;
    }
  harness = g_new0 (GoodixD278Harness, 1);
  harness->material = *material;
  harness->synthetic = synthetic_transport;
  harness->submit = submit;
  harness->pacing = pacing;
  harness->user_data = user_data;
  harness->telemetry = telemetry;
  harness->generation = D278_GENERATION;
  harness->last_phase = GOODIX_SECURE_PHASE_TERMINAL;
  harness->phase_trace = g_string_new ("");
  harness->cancellable = g_cancellable_new ();
  harness->loop = g_main_loop_new (NULL, FALSE);
  harness->router = goodix_usb_router_new (a0_consumer, b0_consumer, harness);
  harness->backend = goodix_fpi_usb_backend_new (device, harness->router,
                                                 D278_EP_IN, D278_EP_OUT,
                                                 D278_RECEIVE_SIZE);
  if (synthetic_transport)
    goodix_fpi_usb_backend_set_async_submit_seam (harness->backend,
                                                   synthetic_submit, harness);
  goodix_fpi_usb_backend_set_drained_callback (harness->backend,
                                                backend_drained, harness);
  goodix_fpi_usb_backend_set_in_completed_callback (harness->backend,
                                                     in_completed, harness);
  harness->watchdog = goodix_d278_watchdog_new (deterministic_watchdog,
                                                 watchdog_expired, harness);
  return harness;
}

gboolean
goodix_d278_harness_start (GoodixD278Harness *harness,
                           GError            **error)
{
  if (harness == NULL || harness->started)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                           "D278 harness cannot start twice");
      return FALSE;
    }
  /* One start attempt is the entire authorization epoch, including failure. */
  harness->started = TRUE;
  goodix_usb_router_begin_generation (harness->router, harness->generation);
  if (!goodix_fpi_usb_backend_begin_generation (harness->backend,
                                                 harness->generation,
                                                 harness->cancellable, error))
    {
      OPENSSL_cleanse (&harness->material, sizeof harness->material);
      set_failure (harness, "GENERATION_BEGIN_FAILED");
      harness->terminal = TRUE;
      goodix_d278_watchdog_invalidate (harness->watchdog);
      goodix_fpi_usb_backend_cancel (harness->backend);
      return FALSE;
    }
  harness->session = goodix_secure_session_new (
    harness->backend, harness->generation, &harness->material,
    harness->synthetic ? pacing_scheduled : NULL,
    harness, session_terminal, harness, &harness->session_audit,
    &harness->tls_audit, error);
  /* GoodixSecureSession and GoodixTlsServer synchronously copied every byte
   * they retain.  Drop all borrowed external material pointers now. */
  OPENSSL_cleanse (&harness->material, sizeof harness->material);
  if (harness->session == NULL)
    {
      set_failure (harness, "SECURE_SESSION_CONSTRUCTION_FAILED");
      harness->terminal = TRUE;
      goodix_d278_watchdog_invalidate (harness->watchdog);
      goodix_fpi_usb_backend_cancel (harness->backend);
      return FALSE;
    }
  goodix_secure_session_set_phase_callback (harness->session, phase_changed,
                                             harness);
  if (!goodix_fpi_usb_backend_arm_receive (harness->backend,
                                            harness->generation, error) ||
      !goodix_secure_session_start (harness->session, error))
    {
      goodix_secure_session_cancel (harness->session,
                                    "D278 harness start failed");
      return FALSE;
    }
  return TRUE;
}

void
goodix_d278_harness_complete_receive (GoodixD278Harness *harness,
                                      guint64            generation,
                                      const guint8      *data,
                                      gsize              length,
                                      const GError      *error)
{
  g_return_if_fail (harness != NULL && harness->synthetic);
  goodix_fpi_usb_backend_complete_receive (harness->backend, generation,
                                           data, length, error);
}

void
goodix_d278_harness_complete_out (GoodixD278Harness *harness,
                                  guint64            generation,
                                  const GError      *error)
{
  g_return_if_fail (harness != NULL && harness->synthetic);
  goodix_fpi_usb_backend_complete_out (harness->backend, generation, error);
}

void
goodix_d278_harness_pacing_ready (GoodixD278Harness *harness,
                                  guint64            generation)
{
  g_return_if_fail (harness != NULL && harness->synthetic);
  goodix_secure_session_pacing_ready (harness->session, generation);
}

void
goodix_d278_harness_cancel (GoodixD278Harness *harness,
                            const gchar       *failure_class)
{
  if (harness == NULL || harness->terminal)
    return;
  set_failure (harness, failure_class != NULL ? failure_class : "CANCELLED");
  harness->terminal = TRUE;
  goodix_d278_watchdog_invalidate (harness->watchdog);
  if (harness->session != NULL)
    goodix_secure_session_cancel (harness->session, failure_class);
  else
    goodix_fpi_usb_backend_cancel (harness->backend);
}

void
goodix_d278_harness_force_synthetic_drain (GoodixD278Harness *harness)
{
  g_autoptr(GError) cancelled = NULL;

  g_return_if_fail (harness != NULL && harness->synthetic);
  g_set_error_literal (&cancelled, G_IO_ERROR, G_IO_ERROR_CANCELLED,
                       "synthetic host I/O cancellation");
  if (goodix_fpi_usb_backend_get_outstanding (harness->backend) != 0)
    goodix_fpi_usb_backend_complete_receive (harness->backend,
                                             harness->generation, NULL, 0,
                                             cancelled);
  if (goodix_fpi_usb_backend_get_out_outstanding (harness->backend) != 0)
    goodix_fpi_usb_backend_complete_out (harness->backend,
                                         harness->generation, cancelled);
}

void
goodix_d278_harness_run_main_loop (GoodixD278Harness *harness)
{
  g_return_if_fail (harness != NULL && !harness->synthetic);
  if (!goodix_fpi_usb_backend_is_drained (harness->backend))
    g_main_loop_run (harness->loop);
}

static void
refresh_telemetry (GoodixD278Harness   *harness,
                   GoodixD278Telemetry *telemetry)
{
  guint64 real = goodix_fpi_usb_backend_get_real_submit_count (harness->backend);
  guint64 outs = goodix_fpi_usb_backend_get_out_submit_count (harness->backend);

  telemetry->real_usb_submit_count = real;
  if (harness->synthetic)
    {
      telemetry->physical_in_submit_count = telemetry->synthetic_in_submit_count;
      telemetry->physical_out_submit_count = telemetry->synthetic_out_submit_count;
    }
  else
    {
      telemetry->physical_out_submit_count = outs;
      telemetry->physical_in_submit_count = real >= outs ? real - outs : 0;
    }
  telemetry->physical_in_completion_count =
    goodix_fpi_usb_backend_get_in_completion_count (harness->backend);
  telemetry->physical_out_completion_count =
    goodix_fpi_usb_backend_get_out_completion_count (harness->backend);
  telemetry->max_outstanding_bulk_in =
    goodix_fpi_usb_backend_get_max_outstanding (harness->backend);
  telemetry->max_outstanding_bulk_out =
    goodix_fpi_usb_backend_get_max_out_outstanding (harness->backend);
  telemetry->command_count = harness->session_audit.command_count;
  telemetry->ack_count = harness->session_audit.ack_count;
  telemetry->typed_response_count = harness->session_audit.typed_response_count;
  telemetry->reentry_recovery_a2_submit_count =
    harness->session_audit.reentry_recovery_a2_submit_count;
  telemetry->reentry_recovery_a2_ack_count =
    harness->session_audit.reentry_recovery_a2_ack_count;
  telemetry->reentry_recovery_a2_typed_count =
    harness->session_audit.reentry_recovery_a2_typed_count;
  g_strlcpy (telemetry->reentry_recovery_a2_result_class,
             goodix_reentry_recovery_a2_result_class_name (
               harness->session_audit.reentry_recovery_a2_result_class),
             sizeof telemetry->reentry_recovery_a2_result_class);
  telemetry->a8_submit_count = harness->session_audit.a8_submit_count;
  telemetry->a8_ack_count = harness->session_audit.a8_ack_count;
  telemetry->a8_typed_count = harness->session_audit.a8_typed_count;
  telemetry->a8_app12509_pin_match =
    harness->session_audit.a8_app12509_pin_match;
  telemetry->e4_submit_count = harness->session_audit.e4_submit_count;
  telemetry->oem_cold_start_a2_1_submit_count =
    harness->session_audit.oem_cold_start_a2_1_submit_count;
  telemetry->oem_cold_start_a2_2_submit_count =
    harness->session_audit.oem_cold_start_a2_2_submit_count;
  telemetry->tls_established = harness->session_audit.tls_established;
  telemetry->retry_count = harness->session_audit.retry_count;
  telemetry->transport_reopen_count = harness->session_audit.transport_reopen_count;
  telemetry->device_reset_count = harness->session_audit.device_reset_count;
  telemetry->clear_halt_count = harness->session_audit.clear_halt_count;
  telemetry->persistent_device_write_count =
    harness->session_audit.persistent_write_count;
  telemetry->d4_reachable = harness->session_audit.d4_reachable;
  if (harness->session_audit.protocol_failure_recorded &&
      g_str_equal (telemetry->protocol_failure_kind, "none"))
    {
      telemetry->protocol_failure_phase =
        harness->session_audit.protocol_failure_phase;
      g_strlcpy (telemetry->protocol_failure_kind,
                 goodix_protocol_failure_kind_name (
                   harness->session_audit.protocol_failure_kind),
                 sizeof telemetry->protocol_failure_kind);
      telemetry->observed_outer_type =
        harness->session_audit.observed_outer_type;
      telemetry->observed_a0_control =
        harness->session_audit.observed_a0_control;
      telemetry->observed_ack_echo =
        harness->session_audit.observed_ack_echo;
      telemetry->observed_ack_status =
        harness->session_audit.observed_ack_status;
      telemetry->observed_body_length =
        harness->session_audit.observed_body_length;
    }
  telemetry->tls_handshake_count = harness->tls_audit.handshake_count;
  telemetry->secret_handoff_count = harness->tls_audit.secret_handoff_count;
  telemetry->application_data_count = harness->tls_audit.plaintext_delivery_count;
  telemetry->backend_drained =
    goodix_fpi_usb_backend_is_drained (harness->backend);
  telemetry->terminal_cleanup_completed = telemetry->backend_drained &&
                                           harness->terminal;
}

static gchar *
telemetry_to_json (const GoodixD278Telemetry *telemetry,
                   const gchar               *phase_trace,
                   gboolean                   zeroized)
{
  return g_strdup_printf (
    "{\"result\":\"%s\",\"failure_class\":\"%s\","
    "\"reached_phase\":\"%s\",\"phase_trace\":\"%s\","
    "\"current_live_authorized\":%s,\"live_authorization_consumed\":%s,"
    "\"usb_open_attempt_count\":%u,\"usb_open_count\":%u,"
    "\"usb_claim_count\":%u,\"usb_release_count\":%u,\"usb_close_count\":%u,"
    "\"real_usb_submit_count\":%" G_GUINT64_FORMAT ","
    "\"physical_in_submit_count\":%" G_GUINT64_FORMAT ","
    "\"physical_in_completion_count\":%" G_GUINT64_FORMAT ","
    "\"physical_out_submit_count\":%" G_GUINT64_FORMAT ","
    "\"physical_out_completion_count\":%" G_GUINT64_FORMAT ","
    "\"max_outstanding_bulk_in\":%u,\"max_outstanding_bulk_out\":%u,"
    "\"command_count\":%u,\"ack_count\":%u,\"typed_response_count\":%u,"
    "\"reentry_recovery_a2_submit_count\":%u,"
    "\"reentry_recovery_a2_ack_count\":%u,"
    "\"reentry_recovery_a2_typed_count\":%u,"
    "\"reentry_recovery_a2_result_class\":\"%s\","
    "\"reentry_recovery_a2_oem_equivalence\":false,"
    "\"reentry_recovery_a2_project_policy\":true,"
    "\"a8_submit_count\":%u,\"a8_ack_count\":%u,\"a8_typed_count\":%u,"
    "\"a8_app12509_pin_match\":%s,"
    "\"e4_submit_count\":%u,"
    "\"oem_cold_start_a2_1_submit_count\":%u,"
    "\"oem_cold_start_a2_2_submit_count\":%u,"
    "\"protocol_failure_phase\":\"%s\","
    "\"protocol_failure_kind\":\"%s\","
    "\"observed_outer_type\":%d,\"observed_a0_control\":%d,"
    "\"observed_ack_echo\":%d,\"observed_ack_status\":%d,"
    "\"observed_body_length\":%" G_GSSIZE_FORMAT ","
    "\"e4_binding_match\":%s,\"tls_handshake_count\":%u,"
    "\"tls_established\":%s,\"secret_handoff_count\":%u,"
    "\"project_secret_zeroized\":%s,\"retry_count\":%u,"
    "\"transport_reopen_count\":%u,\"reopen_count\":%u,"
    "\"device_reset_count\":%u,\"clear_halt_count\":%u,"
    "\"persistent_device_write_count\":%u,\"d4_reachable\":%s,"
    "\"application_data_count\":%u,\"finger_wait_count\":%u,"
    "\"image_count\":%u,\"backend_drained\":%s,"
    "\"terminal_cleanup_completed\":%s,\"real_usb_access\":%u,"
    "\"synthetic_in_submit_count\":%u,\"synthetic_out_submit_count\":%u}",
    telemetry->result, telemetry->failure_class,
    goodix_secure_phase_name (telemetry->reached_phase),
    phase_trace,
    telemetry->current_live_authorized ? "true" : "false",
    telemetry->live_authorization_consumed ? "true" : "false",
    telemetry->usb_open_attempt_count, telemetry->usb_open_count,
    telemetry->usb_claim_count, telemetry->usb_release_count,
    telemetry->usb_close_count, telemetry->real_usb_submit_count,
    telemetry->physical_in_submit_count,
    telemetry->physical_in_completion_count,
    telemetry->physical_out_submit_count,
    telemetry->physical_out_completion_count,
    telemetry->max_outstanding_bulk_in,
    telemetry->max_outstanding_bulk_out,
    telemetry->command_count, telemetry->ack_count,
    telemetry->typed_response_count,
    telemetry->reentry_recovery_a2_submit_count,
    telemetry->reentry_recovery_a2_ack_count,
    telemetry->reentry_recovery_a2_typed_count,
    telemetry->reentry_recovery_a2_result_class,
    telemetry->a8_submit_count, telemetry->a8_ack_count,
    telemetry->a8_typed_count,
    telemetry->a8_app12509_pin_match ? "true" : "false",
    telemetry->e4_submit_count,
    telemetry->oem_cold_start_a2_1_submit_count,
    telemetry->oem_cold_start_a2_2_submit_count,
    g_str_equal (telemetry->protocol_failure_kind, "none") ? "none" :
      goodix_secure_phase_name (telemetry->protocol_failure_phase),
    telemetry->protocol_failure_kind,
    telemetry->observed_outer_type, telemetry->observed_a0_control,
    telemetry->observed_ack_echo, telemetry->observed_ack_status,
    telemetry->observed_body_length,
    telemetry->e4_binding_match ? "true" : "false",
    telemetry->tls_handshake_count,
    telemetry->tls_established ? "true" : "false",
    telemetry->secret_handoff_count,
    zeroized ? "true" : "false",
    telemetry->retry_count, telemetry->transport_reopen_count,
    telemetry->transport_reopen_count, telemetry->device_reset_count,
    telemetry->clear_halt_count, telemetry->persistent_device_write_count,
    telemetry->d4_reachable ? "true" : "false",
    telemetry->application_data_count, telemetry->finger_wait_count,
    telemetry->image_count,
    telemetry->backend_drained ? "true" : "false",
    telemetry->terminal_cleanup_completed ? "true" : "false",
    telemetry->usb_open_attempt_count, telemetry->synthetic_in_submit_count,
    telemetry->synthetic_out_submit_count);
}

gchar *
goodix_d278_telemetry_to_json (GoodixD278Harness   *harness,
                               GoodixD278Telemetry *telemetry)
{
  g_return_val_if_fail (harness != NULL && telemetry != NULL, NULL);
  if (!harness->sealed)
    refresh_telemetry (harness, telemetry);
  return telemetry_to_json (telemetry, harness->phase_trace->str,
                            harness->sealed &&
                            telemetry->project_secret_zeroized);
}

gchar *
goodix_d278_boundary_telemetry_to_json (
  const GoodixD278Telemetry *telemetry)
{
  g_return_val_if_fail (telemetry != NULL, NULL);
  return telemetry_to_json (telemetry, "",
                            telemetry->project_secret_zeroized);
}

void
goodix_d278_harness_seal (GoodixD278Harness *harness)
{
  if (harness == NULL || harness->sealed)
    return;
  g_return_if_fail (goodix_fpi_usb_backend_is_drained (harness->backend));
  refresh_telemetry (harness, harness->telemetry);
  goodix_d278_watchdog_free (harness->watchdog);
  harness->watchdog = NULL;
  goodix_fpi_usb_backend_set_in_completed_callback (harness->backend,
                                                     NULL, NULL);
  goodix_fpi_usb_backend_set_drained_callback (harness->backend, NULL, NULL);
  goodix_secure_session_free (harness->session);
  harness->session = NULL;
  OPENSSL_cleanse (&harness->material, sizeof harness->material);
  harness->telemetry->project_secret_zeroized =
    harness->telemetry->project_secret_zeroized &&
    harness->tls_audit.project_secret_zeroized &&
    harness->session_audit.project_material_zeroized;
  goodix_fpi_usb_backend_free (harness->backend);
  harness->backend = NULL;
  goodix_usb_router_free (harness->router);
  harness->router = NULL;
  harness->sealed = TRUE;
}

void
goodix_d278_harness_free (GoodixD278Harness *harness)
{
  if (harness == NULL)
    return;
  if (!harness->sealed &&
      !goodix_fpi_usb_backend_is_drained (harness->backend))
    {
      g_critical ("D278 harness must be drained before free");
      return;
    }
  goodix_d278_harness_seal (harness);
  g_clear_object (&harness->cancellable);
  g_clear_pointer (&harness->loop, g_main_loop_unref);
  g_string_free (harness->phase_trace, TRUE);
  g_free (harness);
}

GoodixSecureSession *goodix_d278_harness_get_session (GoodixD278Harness *h)
{ return h != NULL ? h->session : NULL; }
GoodixFpiUsbBackend *goodix_d278_harness_get_backend (GoodixD278Harness *h)
{ return h != NULL ? h->backend : NULL; }
GoodixD278Watchdog *goodix_d278_harness_get_watchdog (GoodixD278Harness *h)
{ return h != NULL ? h->watchdog : NULL; }
const GoodixSecureSessionAudit *goodix_d278_harness_get_session_audit (
  GoodixD278Harness *h)
{ return h != NULL ? &h->session_audit : NULL; }
guint64 goodix_d278_harness_get_generation (GoodixD278Harness *h)
{ return h != NULL ? h->generation : 0; }
const gchar *goodix_d278_harness_get_phase_trace (GoodixD278Harness *h)
{ return h != NULL ? h->phase_trace->str : ""; }
gboolean goodix_d278_harness_is_terminal (GoodixD278Harness *h)
{ return h == NULL || h->terminal; }
