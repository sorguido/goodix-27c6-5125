/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Minimal operator client for one Goodix 27c6:5125 enrollment action.
 *
 * This process deliberately uses only libfprint's public API.  It performs no
 * retry, no second action and no template serialization.  The compiled and
 * runtime authorization gates are checked before fp_context_new(), so a
 * normal/offline build cannot enumerate USB devices.
 */
#define FP_COMPONENT "d279-one-shot-enroll"

#include <libfprint/fprint.h>

#include <glib-unix.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#ifndef D279_29_APPROVED_BASELINE
#define D279_29_APPROVED_BASELINE "UNAPPROVED_FOR_LIVE"
#endif

#define D279_29_OPERATION "D279_29_ONE_SHOT_ENROLLMENT"
#define D279_29_AUTHORIZATION "D279_29_ONE_ENROLLMENT_ACTION_NO_RETRY"
#define D279_29_DRIVER "goodix_27c6_5125"
#define D279_29_ENROLL_STAGES 21
#define D279_29_HOST_DEADLINE_SECONDS 600u

typedef struct
{
  GCancellable *cancellable;
  guint          completed_stages;
  guint          progress_error_count;
  gboolean       deadline_expired;
  gboolean       signal_received;
} RunState;

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
  const gchar *runtime_baseline = g_getenv ("D279_29_APPROVED_LIVE_SHA");
  const gchar *runtime_operation = g_getenv ("D279_29_OPERATION");
  const gchar *authorization = g_getenv ("D279_29_OPERATOR_AUTHORIZATION");
  const gchar *grant_id = g_getenv ("D279_29_GRANT_ID");

  if (!is_full_sha (D279_29_APPROVED_BASELINE))
    {
      *reason = "compiled_baseline_unapproved";
      return FALSE;
    }
  if (!is_full_sha (runtime_baseline) ||
      !g_str_equal (runtime_baseline, D279_29_APPROVED_BASELINE))
    {
      *reason = "runtime_baseline_mismatch";
      return FALSE;
    }
  if (runtime_operation == NULL ||
      !g_str_equal (runtime_operation, D279_29_OPERATION))
    {
      *reason = "runtime_operation_mismatch";
      return FALSE;
    }
  if (authorization == NULL ||
      !g_str_equal (authorization, D279_29_AUTHORIZATION))
    {
      *reason = "authorization_missing_or_invalid";
      return FALSE;
    }
  if (grant_id == NULL ||
      strlen (grant_id) != strlen ("d27929-") + 40u ||
      !g_str_has_prefix (grant_id, "d27929-") ||
      !g_str_has_suffix (grant_id, D279_29_APPROVED_BASELINE))
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
           D279_29_ENROLL_STAGES);
  if (state->completed_stages < D279_29_ENROLL_STAGES)
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

      if (g_strcmp0 (fp_device_get_driver (candidate), D279_29_DRIVER) == 0)
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
  FpDevice *device;
  RunState state = { .cancellable = cancellable };
  guint target_count = 0u;
  guint deadline_source;
  guint sigint_source;
  guint sigterm_source;
  gboolean opened = FALSE;
  gboolean close_ok = FALSE;
  int result = 1;

  deadline_source = g_timeout_add_seconds (D279_29_HOST_DEADLINE_SECONDS,
                                           deadline_cb, &state);
  sigint_source = g_unix_signal_add (SIGINT, signal_cb, &state);
  sigterm_source = g_unix_signal_add (SIGTERM, signal_cb, &state);

  g_print ("LIVE_RUN_STARTED=true\n");
  g_print ("ACTION_ALLOWLIST=ENROLL_ONLY\n");
  g_print ("HOST_DEADLINE_SECONDS=%u\n", D279_29_HOST_DEADLINE_SECONDS);
  g_print ("DEVICE_SIDE_TIMEOUT_OR_QUIESCENCE_INFERRED=false\n");
  g_print ("REAL_USB_ENUMERATION_ATTEMPTED=true\n");
  context = fp_context_new ();
  devices = fp_context_get_devices (context);
  device = select_exact_target (devices, &target_count);
  g_print ("TARGET_DRIVER_MATCH_COUNT=%u\n", target_count);
  if (device == NULL)
    {
      g_printerr ("ERRORE=Serve esattamente un dispositivo gestito da %s.\n",
                  D279_29_DRIVER);
      goto out;
    }
  if (fp_device_get_nr_enroll_stages (device) != D279_29_ENROLL_STAGES)
    {
      g_printerr ("ERRORE=Il driver non dichiara esattamente 21 stage.\n");
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
  if (state.completed_stages != D279_29_ENROLL_STAGES)
    {
      g_printerr ("ENROLLMENT_SUCCEEDED=false\n");
      g_printerr ("ERRORE_ENROLLMENT=completion senza 21 progressi\n");
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
