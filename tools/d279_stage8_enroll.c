/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Minimal operator client for one Goodix 27c6:5125 stage-8 early-terminal enrollment action.
 *
 * This process uses libfprint's public action API plus one read-only,
 * sanitized Goodix audit accessor.  It performs no retry, no second action
 * and no template serialization.  The compiled and runtime authorization
 * gates are checked before fp_context_new(), so a normal/offline build cannot
 * enumerate USB devices.
 */
#define FP_COMPONENT "d279-stage8-enroll"

#include <libfprint/fprint.h>
#include "goodix_fpimage_device.h"

#include <glib-unix.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#ifndef D279_57_APPROVED_BASELINE
#define D279_57_APPROVED_BASELINE "UNAPPROVED_FOR_LIVE"
#endif

#define D279_57_OPERATION "D279_57_STAGE8_EARLY_TERMINAL_ENROLLMENT"
#define D279_57_AUTHORIZATION "D279_57_ONE_STAGE8_ENROLLMENT_NO_RETRY"
#define D279_57_DRIVER "goodix_27c6_5125"
#define D279_57_ENROLL_STAGES 8
#define D279_57_HOST_DEADLINE_SECONDS 600u

typedef struct
{
  GCancellable *cancellable;
  guint          completed_stages;
  guint          progress_error_count;
  gboolean       deadline_expired;
  gboolean       signal_received;
} RunState;

static const gchar *
bool_text (gboolean value)
{
  return value ? "true" : "false";
}

static gboolean
print_production_audit (FpDevice *device)
{
  GoodixProductionEnrollmentAudit audit = { 0 };
  guint known_persistent_family_count;
  gboolean boundary_pass;

  goodix_fpimage_device_get_production_enrollment_audit (
    (GoodixFpImageDevice *) device, &audit);
  known_persistent_family_count =
    audit.secure.persistent_write_count +
    audit.post_tls.persistent_device_write_count +
    audit.enrollment_binding.transaction.frame.persistent_family_count;

  g_print ("PRODUCTION_AUDIT_AVAILABLE=true\n");
  g_print ("AUDIT_CONTEXT_CLOSED=%s\n", bool_text (audit.context_closed));
  g_print ("AUDIT_ACTION_CONSUMED=%s\n",
           bool_text (audit.production_action_consumed));
  g_print ("AUDIT_PRE_SESSION_RESULT=%d\n",
           (gint) audit.pre_session_rx_sync.pre_session_rx_result);
  g_print ("AUDIT_PRE_SESSION_COMPLETION_COUNT=%" G_GUINT64_FORMAT "\n",
           audit.pre_session_rx_sync.pre_session_rx_discarded_completion_count);
  g_print ("AUDIT_PRE_SESSION_BYTE_COUNT=%" G_GUINT64_FORMAT "\n",
           audit.pre_session_rx_sync.pre_session_rx_discarded_byte_count);
  g_print ("AUDIT_PRE_SESSION_HOST_TIMEOUT_COUNT=%" G_GUINT64_FORMAT "\n",
           audit.pre_session_rx_sync.pre_session_rx_timeout_count);
  g_print ("AUDIT_USB_REAL_SUBMIT_COUNT=%" G_GUINT64_FORMAT "\n",
           audit.usb_real_submit_count);
  g_print ("AUDIT_USB_OUT_SUBMIT_COUNT=%" G_GUINT64_FORMAT "\n",
           audit.usb_out_submit_count);
  g_print ("AUDIT_USB_IN_COMPLETION_COUNT=%" G_GUINT64_FORMAT "\n",
           audit.usb_in_completion_count);
  g_print ("AUDIT_USB_OUT_COMPLETION_COUNT=%" G_GUINT64_FORMAT "\n",
           audit.usb_out_completion_count);
  g_print ("AUDIT_USB_MAX_IN_OUTSTANDING=%u\n",
           audit.usb_max_in_outstanding_count);
  g_print ("AUDIT_USB_MAX_OUT_OUTSTANDING=%u\n",
           audit.usb_max_out_outstanding_count);
  g_print ("AUDIT_USB_OUTSTANDING_AT_SNAPSHOT=%u\n",
           audit.usb_outstanding_count);
  g_print ("AUDIT_USB_OUT_OUTSTANDING_AT_SNAPSHOT=%u\n",
           audit.usb_out_outstanding_count);
  g_print ("AUDIT_USB_BACKEND_DRAINED=%s\n",
           bool_text (audit.usb_backend_drained));
  g_print ("AUDIT_USB_INTERFACE_CLAIMED_AT_SNAPSHOT=%s\n",
           bool_text (audit.usb_interface_claimed));
  g_print ("AUDIT_RUNTIME_MATERIAL_PRESENT_AT_SNAPSHOT=%s\n",
           bool_text (audit.runtime_material_present));
  g_print ("AUDIT_RUNTIME_OWNER_FREE_COUNT=%u\n",
           audit.runtime_material.owner_free_count);
  g_print ("AUDIT_RUNTIME_DESCRIPTOR_CLEANSED=%s\n",
           bool_text (audit.runtime_material.descriptor_cleansed));
  g_print ("AUDIT_RUNTIME_FDT_SEED_CLEANSED=%s\n",
           bool_text (audit.runtime_material.fdt_seed_cleansed));
  g_print ("AUDIT_RUNTIME_HANDOFF_VIEWS_CLEARED=%s\n",
           bool_text (audit.runtime_handoff_views_cleared));
  g_print ("AUDIT_SECURE_COMMAND_COUNT=%u\n", audit.secure.command_count);
  g_print ("AUDIT_SECURE_ACK_COUNT=%u\n", audit.secure.ack_count);
  g_print ("AUDIT_SECURE_TYPED_RESPONSE_COUNT=%u\n",
           audit.secure.typed_response_count);
  g_print ("AUDIT_SECURE_RETRY_COUNT=%u\n", audit.secure.retry_count);
  g_print ("AUDIT_SECURE_REOPEN_COUNT=%u\n",
           audit.secure.transport_reopen_count);
  g_print ("AUDIT_SECURE_DEVICE_RESET_COUNT=%u\n",
           audit.secure.device_reset_count);
  g_print ("AUDIT_SECURE_CLEAR_HALT_COUNT=%u\n",
           audit.secure.clear_halt_count);
  g_print ("AUDIT_SECURE_PROTOCOL_FAILURE_RECORDED=%s\n",
           bool_text (audit.secure.protocol_failure_recorded));
  g_print ("AUDIT_SECURE_PROTOCOL_FAILURE_PHASE=%d\n",
           (gint) audit.secure.protocol_failure_phase);
  g_print ("AUDIT_SECURE_PROTOCOL_FAILURE_KIND=%d\n",
           (gint) audit.secure.protocol_failure_kind);
  g_print ("AUDIT_TLS_HANDSHAKE_COUNT=%u\n", audit.tls.handshake_count);
  g_print ("AUDIT_TLS_TERMINAL_COMPLETION_COUNT=%u\n",
           audit.tls.terminal_completion_count);
  g_print ("AUDIT_TLS_SECRET_ZEROIZED=%s\n",
           bool_text (audit.tls.project_secret_zeroized));
  g_print ("AUDIT_POST_TLS_COMMAND_COUNT=%u\n",
           audit.post_tls.command_count);
  g_print ("AUDIT_POST_TLS_ACK_COUNT=%u\n", audit.post_tls.ack_count);
  g_print ("AUDIT_POST_TLS_RETRY_COUNT=%u\n", audit.post_tls.retry_count);
  g_print ("AUDIT_POST_TLS_REOPEN_COUNT=%u\n", audit.post_tls.reopen_count);
  g_print ("AUDIT_POST_TLS_DEVICE_RESET_COUNT=%u\n",
           audit.post_tls.device_reset_count);
  g_print ("AUDIT_POST_TLS_CLEAR_HALT_COUNT=%u\n",
           audit.post_tls.clear_halt_count);
  g_print ("AUDIT_ENROLL_EVENT_SUBMIT_COUNT=%u\n",
           audit.enrollment_events.submit_count);
  g_print ("AUDIT_ENROLL_EVENT_ACK_COUNT=%u\n",
           audit.enrollment_events.ack_count);
  g_print ("AUDIT_ENROLL_EVENT_PRIMARY_B0_COUNT=%u\n",
           audit.enrollment_events.primary_b0_count);
  g_print ("AUDIT_ENROLL_EVENT_AUXILIARY_B0_COUNT=%u\n",
           audit.enrollment_events.auxiliary_b0_count);
  g_print ("AUDIT_ENROLL_EVENT_RETRY_COUNT=%u\n",
           audit.enrollment_events.retry_count);
  g_print ("AUDIT_ENROLL_BINDING_BACKEND_SUBMIT_ATTEMPT_COUNT=%u\n",
           audit.enrollment_binding.backend_submit_attempt_count);
  g_print ("AUDIT_ENROLL_BINDING_BACKEND_COMPLETION_COUNT=%u\n",
           audit.enrollment_binding.backend_completion_count);
  g_print ("AUDIT_ENROLL_BINDING_CANCELLATION_COUNT=%u\n",
           audit.enrollment_binding.cancellation_count);
  g_print ("AUDIT_ENROLL_BINDING_RETRY_COUNT=%u\n",
           audit.enrollment_binding.retry_count);
  g_print ("AUDIT_ENROLL_CONFIGURED_STAGE_COUNT=%u\n",
           audit.enrollment_events.lifecycle.plan.pipeline.protocol.configured_required_stage_count);
  g_print ("AUDIT_ENROLL_OBSERVED_PRIMARY_STAGE_COUNT=%u\n",
           audit.enrollment_events.lifecycle.plan.pipeline.protocol.observed_primary_stage_count);
  g_print ("AUDIT_ENROLL_COMPLETED_STAGE_COUNT=%u\n",
           audit.enrollment_events.lifecycle.plan.pipeline.protocol.completed_stage_count);
  g_print ("AUDIT_ENROLL_TERMINAL_TRANSITION_COUNT=%u\n",
           audit.enrollment_events.lifecycle.plan.pipeline.protocol.terminal_transition_count);
  g_print ("AUDIT_ENROLL_INTER_STAGE_REARM_COUNT=%u\n",
           audit.enrollment_events.lifecycle.plan.inter_stage_rearm_count);
  g_print ("AUDIT_ENROLL_COMMAND_32_COUNT=%u\n",
           audit.enrollment_events.lifecycle.plan.command_32_count);
  g_print ("AUDIT_ENROLL_REAL_USB_SUBMIT_COUNT=%u\n",
           audit.enrollment_binding.transaction.real_usb_submit_count);
  g_print ("AUDIT_KNOWN_PERSISTENT_FAMILY_OBSERVED_COUNT=%u\n",
           known_persistent_family_count);
  g_print ("SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false\n");

  boundary_pass =
    audit.context_closed && audit.usb_backend_drained &&
    !audit.usb_interface_claimed && !audit.runtime_material_present &&
    audit.enrollment_events.lifecycle.plan.pipeline.protocol.configured_required_stage_count ==
      D279_57_ENROLL_STAGES &&
    audit.enrollment_events.lifecycle.plan.pipeline.protocol.observed_primary_stage_count ==
      D279_57_ENROLL_STAGES &&
    audit.enrollment_events.lifecycle.plan.pipeline.protocol.completed_stage_count ==
      D279_57_ENROLL_STAGES &&
    audit.enrollment_events.lifecycle.plan.pipeline.protocol.terminal_transition_count == 1u &&
    audit.enrollment_events.lifecycle.plan.inter_stage_rearm_count ==
      D279_57_ENROLL_STAGES - 1u &&
    audit.enrollment_events.lifecycle.plan.command_32_count ==
      D279_57_ENROLL_STAGES &&
    audit.enrollment_events.primary_b0_count == D279_57_ENROLL_STAGES &&
    audit.enrollment_events.retry_count == 0u &&
    audit.enrollment_binding.retry_count == 0u &&
    known_persistent_family_count == 0u;
  g_print ("D279_57_STAGE8_TERMINAL_AUDIT_PASS=%s\n",
           bool_text (boundary_pass));
  g_print ("D279_57_REUSABILITY_PROVEN=false\n");
  return boundary_pass;
}

static gboolean
is_full_sha (const gchar *value)
{
  if (value == NULL || strlen (value) != 40u)
    return FALSE;
  for (gsize i = 0; i < 40u; i++)
    if (!g_ascii_isxdigit (value[i]))
      return FALSE;
  return TRUE;
}

static gboolean
live_gate_valid (const gchar **reason)
{
  const gchar *runtime_baseline = g_getenv ("D279_57_APPROVED_LIVE_SHA");
  const gchar *runtime_operation = g_getenv ("D279_57_OPERATION");
  const gchar *authorization = g_getenv ("D279_57_OPERATOR_AUTHORIZATION");
  const gchar *grant_id = g_getenv ("D279_57_GRANT_ID");

  if (!is_full_sha (D279_57_APPROVED_BASELINE))
    {
      *reason = "compiled_baseline_unapproved";
      return FALSE;
    }
  if (!is_full_sha (runtime_baseline) ||
      !g_str_equal (runtime_baseline, D279_57_APPROVED_BASELINE))
    {
      *reason = "runtime_baseline_mismatch";
      return FALSE;
    }
  if (runtime_operation == NULL ||
      !g_str_equal (runtime_operation, D279_57_OPERATION))
    {
      *reason = "runtime_operation_mismatch";
      return FALSE;
    }
  if (authorization == NULL ||
      !g_str_equal (authorization, D279_57_AUTHORIZATION))
    {
      *reason = "authorization_missing_or_invalid";
      return FALSE;
    }
  if (grant_id == NULL ||
      strlen (grant_id) != strlen ("d27957-") + 40u ||
      !g_str_has_prefix (grant_id, "d27957-") ||
      !g_str_has_suffix (grant_id, D279_57_APPROVED_BASELINE))
    {
      *reason = "grant_id_mismatch";
      return FALSE;
    }
  if (geteuid () != 0)
    {
      *reason = "live_requires_root";
      return FALSE;
    }

  *reason = "none";
  return TRUE;
}

static gboolean
deadline_cb (gpointer user_data)
{
  RunState *state = user_data;

  state->deadline_expired = TRUE;
  g_print ("LIMITE_HOST_RAGGIUNTO=true\n");
  g_print ("NOTA_OPERATORE=Il limite e solo host-side; non prova timeout o quiescenza del sensore.\n");
  g_cancellable_cancel (state->cancellable);
  return G_SOURCE_REMOVE;
}

static gboolean
signal_cb (gpointer user_data)
{
  RunState *state = user_data;

  state->signal_received = TRUE;
  g_print ("INTERRUZIONE_OPERATORE_RICEVUTA=true\n");
  g_print ("NOTA_OPERATORE=La cancellazione non prova quiescenza device-side; non ripetere la run.\n");
  g_cancellable_cancel (state->cancellable);
  return G_SOURCE_CONTINUE;
}

static void
enroll_progress_cb (FpDevice *device,
                    gint      completed_stages,
                    FpPrint  *print,
                    gpointer  user_data,
                    GError   *error)
{
  RunState *state = user_data;

  (void) device;
  (void) print;
  if (error != NULL)
    {
      state->progress_error_count++;
      g_print ("ERRORE_STAGE=%s\n", error->message);
      g_print ("STOP_NO_RETRY=true\n");
      g_cancellable_cancel (state->cancellable);
      return;
    }
  if (completed_stages <= 0 ||
      (guint) completed_stages != state->completed_stages + 1u)
    {
      state->progress_error_count++;
      g_print ("ERRORE_STAGE=progresso enrollment non monotono\n");
      g_print ("STOP_NO_RETRY=true\n");
      g_cancellable_cancel (state->cancellable);
      return;
    }

  state->completed_stages = (guint) completed_stages;
  g_print ("STAGE_COMPLETATO=%u/%u\n", state->completed_stages,
           D279_57_ENROLL_STAGES);
  if (state->completed_stages < D279_57_ENROLL_STAGES)
    {
      g_print ("AZIONE_OPERATORE=TOGLI IL DITO; attendi un istante e riposiziona lo stesso dito.\n");
    }
}

static FpDevice *
select_exact_target (GPtrArray *devices, guint *target_count)
{
  FpDevice *selected = NULL;

  *target_count = 0u;
  if (devices == NULL)
    return NULL;
  for (guint i = 0u; i < devices->len; i++)
    {
      FpDevice *candidate = g_ptr_array_index (devices, i);

      if (g_strcmp0 (fp_device_get_driver (candidate), D279_57_DRIVER) == 0)
        {
          (*target_count)++;
          selected = candidate;
        }
    }
  return *target_count == 1u ? selected : NULL;
}

static int
run_once (void)
{
  g_autoptr(FpContext) context = NULL;
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(FpPrint) template_print = NULL;
  g_autoptr(FpPrint) enrolled_print = NULL;
  g_autoptr(GError) action_error = NULL;
  g_autoptr(GError) close_error = NULL;
  GPtrArray *devices;
  FpDevice *device = NULL;
  RunState state = { .cancellable = cancellable };
  guint target_count = 0u;
  guint deadline_source;
  guint sigint_source;
  guint sigterm_source;
  gboolean opened = FALSE;
  gboolean close_ok = FALSE;
  int result = 1;

  deadline_source = g_timeout_add_seconds (D279_57_HOST_DEADLINE_SECONDS,
                                           deadline_cb, &state);
  sigint_source = g_unix_signal_add (SIGINT, signal_cb, &state);
  sigterm_source = g_unix_signal_add (SIGTERM, signal_cb, &state);

  g_print ("LIVE_RUN_STARTED=true\n");
  g_print ("ACTION_ALLOWLIST=ENROLL_ONLY\n");
  g_print ("HOST_DEADLINE_SECONDS=%u\n", D279_57_HOST_DEADLINE_SECONDS);
  g_print ("DEVICE_SIDE_TIMEOUT_OR_QUIESCENCE_INFERRED=false\n");
  g_print ("REAL_USB_ENUMERATION_ATTEMPTED=true\n");
  context = fp_context_new ();
  devices = fp_context_get_devices (context);
  device = select_exact_target (devices, &target_count);
  g_print ("TARGET_DRIVER_MATCH_COUNT=%u\n", target_count);
  if (device == NULL)
    {
      g_printerr ("ERRORE=Serve esattamente un dispositivo gestito da %s.\n",
                  D279_57_DRIVER);
      goto out;
    }
  if (fp_device_get_nr_enroll_stages (device) != D279_57_ENROLL_STAGES)
    {
      g_printerr ("ERRORE=Il driver non dichiara esattamente 8 stage.\n");
      goto out;
    }

  g_print ("DISPOSITIVO=%s\n", fp_device_get_name (device));
  g_print ("OPEN_ATTEMPT_COUNT=1\n");
  if (!fp_device_open_sync (device, cancellable, &action_error))
    {
      g_printerr ("ERRORE_OPEN=%s\n", action_error->message);
      goto out;
    }
  opened = TRUE;
  g_print ("OPEN_SUCCEEDED=true\n");

  template_print = fp_print_new (device);
  fp_print_set_finger (template_print, FP_FINGER_RIGHT_INDEX);
  g_print ("AZIONE_OPERATORE=METTI L'INDICE DESTRO SUL SENSORE; usa sempre lo stesso dito.\n");
  g_print ("ACTION_ATTEMPT_COUNT=1\n");
  enrolled_print = fp_device_enroll_sync (device,
                                          g_steal_pointer (&template_print),
                                          cancellable,
                                          enroll_progress_cb, &state,
                                          &action_error);
  if (enrolled_print == NULL)
    {
      g_printerr ("ENROLLMENT_SUCCEEDED=false\n");
      g_printerr ("ERRORE_ENROLLMENT=%s\n",
                  action_error != NULL ? action_error->message : "sconosciuto");
      goto close;
    }
  if (state.completed_stages != D279_57_ENROLL_STAGES)
    {
      g_printerr ("ENROLLMENT_SUCCEEDED=false\n");
      g_printerr ("ERRORE_ENROLLMENT=completion senza 8 progressi\n");
      goto close;
    }

  g_print ("ENROLLMENT_SUCCEEDED=true\n");
  g_print ("BIOMETRIC_TEMPLATE_SAVED=false\n");
  result = 0;

close:
  g_print ("CLOSE_ATTEMPT_COUNT=1\n");
  close_ok = fp_device_close_sync (device, NULL, &close_error);
  g_print ("CLOSE_SUCCEEDED=%s\n", close_ok ? "true" : "false");
  if (!close_ok)
    {
      g_printerr ("ERRORE_CLOSE=%s\n", close_error->message);
      result = 1;
    }
  opened = FALSE;

out:
  if (opened)
    {
      g_print ("CLOSE_ATTEMPT_COUNT=1\n");
      close_ok = fp_device_close_sync (device, NULL, &close_error);
      g_print ("CLOSE_SUCCEEDED=%s\n", close_ok ? "true" : "false");
      if (!close_ok)
        g_printerr ("ERRORE_CLOSE=%s\n", close_error->message);
    }
  if (device != NULL && !print_production_audit (device))
    result = 1;
  if (deadline_source != 0u &&
      g_main_context_find_source_by_id (NULL, deadline_source) != NULL)
    g_source_remove (deadline_source);
  if (sigint_source != 0u &&
      g_main_context_find_source_by_id (NULL, sigint_source) != NULL)
    g_source_remove (sigint_source);
  if (sigterm_source != 0u &&
      g_main_context_find_source_by_id (NULL, sigterm_source) != NULL)
    g_source_remove (sigterm_source);

  g_print ("COMPLETED_STAGE_COUNT=%u\n", state.completed_stages);
  g_print ("PROGRESS_ERROR_COUNT=%u\n", state.progress_error_count);
  g_print ("OPERATOR_RETRY_COUNT=0\n");
  g_print ("SECOND_ACTION_COUNT=0\n");
  g_print ("REOPEN_COUNT=0\n");
  g_print ("HOST_DEADLINE_EXPIRED=%s\n",
           state.deadline_expired ? "true" : "false");
  g_print ("OPERATOR_SIGNAL_RECEIVED=%s\n",
           state.signal_received ? "true" : "false");
  g_print ("DEVICE_SIDE_TIMEOUT_OR_QUIESCENCE_INFERRED=false\n");
  if (result != 0)
    g_print ("NOTA_OPERATORE=Run terminata senza successo: non ripetere e considera ignoto lo stato device-side.\n");
  return result;
}

int
main (int argc, char **argv)
{
  const gchar *reason = NULL;

  setvbuf (stdout, NULL, _IOLBF, 0);
  setvbuf (stderr, NULL, _IOLBF, 0);

  if (argc == 2 && g_str_equal (argv[1], "--gate-self-test"))
    {
      if (live_gate_valid (&reason))
        {
          g_printerr ("GATE_SELF_TEST=UNEXPECTEDLY_LIVE_ENABLED\n");
          return 1;
        }
      g_print ("GATE_SELF_TEST=PASS_REFUSED_BEFORE_USB\n");
      g_print ("GATE_REFUSAL_REASON=%s\n", reason);
      g_print ("REAL_USB_ENUMERATION_ATTEMPTED=false\n");
      g_print ("LIVE_EXECUTION_PERFORMED=false\n");
      return 0;
    }

  if (argc != 2 || !g_str_equal (argv[1], "--run-once"))
    {
      g_printerr ("Uso: %s --run-once\n", argv[0]);
      return 2;
    }
  if (!live_gate_valid (&reason))
    {
      g_printerr ("LIVE_GATE_REFUSED=true\n");
      g_printerr ("LIVE_GATE_REFUSAL_REASON=%s\n", reason);
      g_printerr ("REAL_USB_ENUMERATION_ATTEMPTED=false\n");
      g_printerr ("LIVE_EXECUTION_PERFORMED=false\n");
      return 3;
    }

  return run_once ();
}
