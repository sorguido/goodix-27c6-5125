/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * D280/01 operator client: one enrollment followed by one identify across a
 * real close/open boundary.  The only object carried between epochs is an
 * FP3 blob in a root-owned 0600 file selected by the fail-closed runner.
 *
 * Authorization is checked before fp_context_new().  There are no retries,
 * no storage actions and no sensor-side persistence commands.
 */
#define FP_COMPONENT "d280-ephemeral-template-reuse"

#include <libfprint/fprint.h>
#include "goodix_fpimage_device.h"

#include <errno.h>
#include <fcntl.h>
#include <glib-unix.h>
#include <linux/magic.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <unistd.h>

#ifndef D280_01_APPROVED_BASELINE
#define D280_01_APPROVED_BASELINE "UNAPPROVED_FOR_LIVE"
#endif

#define D280_01_OPERATION \
  "D280_01_ENROLL_FP3_CLOSE_OPEN_IDENTIFY_EPHEMERAL"
#define D280_01_AUTHORIZATION \
  "D280_01_ONE_ENROLL_ONE_IDENTIFY_NO_RETRY_EPHEMERAL_FP3"
#define D280_01_DRIVER "goodix_27c6_5125"
#define D280_01_ENROLL_STAGES 8u
#define D280_01_HOST_DEADLINE_SECONDS 1000u
#define D280_01_TEMPLATE_PREFIX "/run/goodix-d280-01/"
#define D280_01_TEMPLATE_SUFFIX "/template.fp3"
#define D280_01_TEMPLATE_MAX_BYTES (16u * 1024u * 1024u)

typedef enum
{
  RUN_PHASE_ENROLL,
  RUN_PHASE_IDENTIFY,
} RunPhase;

typedef struct
{
  GCancellable *cancellable;
  RunPhase phase;
  guint completed_stages;
  guint progress_error_count;
  guint release_ready_prompt_count;
  guint reposition_prompt_count;
  guint identify_match_callback_count;
  guint identify_no_match_callback_count;
  guint identify_retry_callback_count;
  guint action_attempt_count;
  guint enroll_action_attempt_count;
  guint identify_action_attempt_count;
  guint open_attempt_count;
  guint open_success_count;
  guint reopen_count;
  guint close_attempt_count;
  guint close_success_count;
  FpFingerStatusFlags last_finger_status;
  gboolean deadline_expired;
  gboolean signal_received;
} RunState;

static const gchar *
bool_text (gboolean value)
{
  return value ? "true" : "false";
}

static void
secure_clear (gpointer data, gsize length)
{
  volatile guint8 *bytes = data;

  while (bytes != NULL && length > 0u)
    {
      *bytes++ = 0u;
      length--;
    }
}

static gboolean
is_full_sha (const gchar *value)
{
  if (value == NULL || strlen (value) != 40u)
    return FALSE;
  for (gsize i = 0u; i < 40u; i++)
    if (!g_ascii_isxdigit (value[i]))
      return FALSE;
  return TRUE;
}

static gboolean
template_path_valid (const gchar *path)
{
  gsize path_length;

  if (path == NULL || !g_path_is_absolute (path) ||
      !g_str_has_prefix (path, D280_01_TEMPLATE_PREFIX) ||
      !g_str_has_suffix (path, D280_01_TEMPLATE_SUFFIX) ||
      strstr (path, "/../") != NULL || strstr (path, "/./") != NULL)
    return FALSE;
  path_length = strlen (path);
  return path_length > strlen (D280_01_TEMPLATE_PREFIX) +
                       strlen (D280_01_TEMPLATE_SUFFIX);
}

static gboolean
live_gate_valid (const gchar **reason)
{
  const gchar *runtime_baseline = g_getenv ("D280_01_APPROVED_LIVE_SHA");
  const gchar *runtime_operation = g_getenv ("D280_01_OPERATION");
  const gchar *authorization = g_getenv ("D280_01_OPERATOR_AUTHORIZATION");
  const gchar *grant_id = g_getenv ("D280_01_GRANT_ID");
  const gchar *template_path = g_getenv ("D280_01_TEMPLATE_PATH");

  if (!is_full_sha (D280_01_APPROVED_BASELINE))
    {
      *reason = "compiled_baseline_unapproved";
      return FALSE;
    }
  if (!is_full_sha (runtime_baseline) ||
      !g_str_equal (runtime_baseline, D280_01_APPROVED_BASELINE))
    {
      *reason = "runtime_baseline_mismatch";
      return FALSE;
    }
  if (runtime_operation == NULL ||
      !g_str_equal (runtime_operation, D280_01_OPERATION))
    {
      *reason = "runtime_operation_mismatch";
      return FALSE;
    }
  if (authorization == NULL ||
      !g_str_equal (authorization, D280_01_AUTHORIZATION))
    {
      *reason = "authorization_missing_or_invalid";
      return FALSE;
    }
  if (grant_id == NULL ||
      strlen (grant_id) != strlen ("d28001-") + 40u ||
      !g_str_has_prefix (grant_id, "d28001-") ||
      !g_str_has_suffix (grant_id, D280_01_APPROVED_BASELINE))
    {
      *reason = "grant_id_mismatch";
      return FALSE;
    }
  if (!template_path_valid (template_path))
    {
      *reason = "template_path_invalid";
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
write_all (gint fd, const guint8 *bytes, gsize length, GError **error)
{
  gsize offset = 0u;

  while (offset < length)
    {
      ssize_t written = write (fd, bytes + offset, length - offset);
      if (written < 0 && errno == EINTR)
        continue;
      if (written <= 0)
        {
          g_set_error (error, G_FILE_ERROR, g_file_error_from_errno (errno),
                       "scrittura FP3 fallita: %s", g_strerror (errno));
          return FALSE;
        }
      offset += (gsize) written;
    }
  return TRUE;
}

static gboolean
fd_is_tmpfs (gint fd, GError **error)
{
  struct statfs filesystem = { 0 };

  if (fstatfs (fd, &filesystem) != 0)
    {
      g_set_error (error, G_FILE_ERROR, g_file_error_from_errno (errno),
                   "verifica tmpfs fallita: %s", g_strerror (errno));
      return FALSE;
    }
  if ((guint64) filesystem.f_type != (guint64) TMPFS_MAGIC)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
                           "il file FP3 non risiede su tmpfs");
      return FALSE;
    }
  return TRUE;
}

static gboolean
persist_template (const gchar  *path,
                  const guint8 *bytes,
                  gsize         length,
                  GError      **error)
{
  struct stat st = { 0 };
  gint fd;
  gboolean ok = FALSE;

  if (length == 0u || length > D280_01_TEMPLATE_MAX_BYTES)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                           "dimensione FP3 fuori limite");
      return FALSE;
    }
  fd = open (path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
             S_IRUSR | S_IWUSR);
  if (fd < 0)
    {
      g_set_error (error, G_FILE_ERROR, g_file_error_from_errno (errno),
                   "creazione FP3 esclusiva fallita: %s", g_strerror (errno));
      return FALSE;
    }
  if (fd_is_tmpfs (fd, error))
    {
      if (fstat (fd, &st) != 0 || !S_ISREG (st.st_mode) || st.st_uid != 0 ||
          (st.st_mode & 0777) != 0600)
        g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                             "policy file FP3 non rispettata");
      else if (write_all (fd, bytes, length, error) && fsync (fd) == 0)
        ok = TRUE;
      else if (error != NULL && *error == NULL)
        g_set_error (error, G_FILE_ERROR, g_file_error_from_errno (errno),
                     "fsync FP3 fallita: %s", g_strerror (errno));
    }
  if (close (fd) != 0 && ok)
    {
      g_set_error (error, G_FILE_ERROR, g_file_error_from_errno (errno),
                   "close FP3 fallita: %s", g_strerror (errno));
      ok = FALSE;
    }
  if (!ok && unlink (path) != 0 && errno != ENOENT)
    g_printerr ("FP3_PARTIAL_WRITE_CLEANUP_REMOVED=false\n");
  return ok;
}

static gboolean
load_template (const gchar *path, guint8 **bytes, gsize *length,
               GError **error)
{
  struct stat st = { 0 };
  guint8 *buffer = NULL;
  gsize offset = 0u;
  gint fd;
  gboolean ok = FALSE;

  *bytes = NULL;
  *length = 0u;
  fd = open (path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (fd < 0)
    {
      g_set_error (error, G_FILE_ERROR, g_file_error_from_errno (errno),
                   "apertura FP3 fallita: %s", g_strerror (errno));
      return FALSE;
    }
  if (!fd_is_tmpfs (fd, error))
    goto out;
  if (fstat (fd, &st) != 0 || !S_ISREG (st.st_mode) || st.st_uid != 0 ||
      (st.st_mode & 0777) != 0600 || st.st_size <= 0 ||
      (guint64) st.st_size > D280_01_TEMPLATE_MAX_BYTES)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                           "file FP3 non conforme alla policy");
      goto out;
    }
  buffer = g_malloc ((gsize) st.st_size);
  while (offset < (gsize) st.st_size)
    {
      ssize_t count = read (fd, buffer + offset, (gsize) st.st_size - offset);
      if (count < 0 && errno == EINTR)
        continue;
      if (count <= 0)
        {
          g_set_error (error, G_FILE_ERROR, g_file_error_from_errno (errno),
                       "lettura FP3 incompleta: %s", g_strerror (errno));
          goto out;
        }
      offset += (gsize) count;
    }
  {
    guint8 trailing;
    ssize_t count;
    do
      count = read (fd, &trailing, 1u);
    while (count < 0 && errno == EINTR);
    if (count != 0)
      {
        g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                             "file FP3 mutato durante la lettura");
        goto out;
      }
  }
  *bytes = g_steal_pointer (&buffer);
  *length = (gsize) st.st_size;
  ok = TRUE;

out:
  if (buffer != NULL)
    {
      secure_clear (buffer, (gsize) MAX (st.st_size, 0));
      g_free (buffer);
    }
  if (close (fd) != 0 && ok)
    {
      g_set_error (error, G_FILE_ERROR, g_file_error_from_errno (errno),
                   "close FP3 lettura fallita: %s", g_strerror (errno));
      secure_clear (*bytes, *length);
      g_clear_pointer (bytes, g_free);
      *length = 0u;
      ok = FALSE;
    }
  return ok;
}

static guint
known_persistent_family_count (const GoodixProductionEnrollmentAudit *audit)
{
  return audit->secure.persistent_write_count +
         audit->post_tls.persistent_device_write_count +
         audit->enrollment_binding.transaction.frame.persistent_family_count;
}

static gboolean
common_audit_pass (const GoodixProductionEnrollmentAudit *audit)
{
  return audit->context_closed && audit->production_action_consumed &&
         audit->usb_backend_drained && !audit->usb_interface_claimed &&
         audit->usb_outstanding_count == 0u &&
         audit->usb_out_outstanding_count == 0u &&
         !audit->runtime_material_present &&
         audit->runtime_handoff_views_cleared &&
         audit->runtime_material.owner_free_count == 1u &&
         audit->runtime_material.descriptor_cleansed &&
         audit->runtime_material.fdt_seed_cleansed &&
         audit->tls.handshake_count == 1u &&
         audit->tls.terminal_completion_count == 0u &&
         audit->tls.project_secret_zeroized &&
         audit->secure.retry_count == 0u &&
         audit->secure.transport_reopen_count == 0u &&
         audit->secure.device_reset_count == 0u &&
         audit->secure.clear_halt_count == 0u &&
         audit->post_tls.retry_count == 0u &&
         audit->post_tls.reopen_count == 0u &&
         audit->post_tls.device_reset_count == 0u &&
         audit->post_tls.clear_halt_count == 0u &&
         known_persistent_family_count (audit) == 0u;
}

static gboolean
enroll_audit_pass (const GoodixProductionEnrollmentAudit *audit)
{
  return common_audit_pass (audit) &&
         audit->enrollment_events.lifecycle.plan.pipeline.protocol.configured_required_stage_count ==
           D280_01_ENROLL_STAGES &&
         audit->enrollment_events.lifecycle.plan.pipeline.protocol.observed_primary_stage_count ==
           D280_01_ENROLL_STAGES &&
         audit->enrollment_events.lifecycle.plan.pipeline.protocol.completed_stage_count ==
           D280_01_ENROLL_STAGES &&
         audit->enrollment_events.lifecycle.plan.pipeline.protocol.terminal_transition_count == 1u &&
         audit->enrollment_events.lifecycle.plan.inter_stage_rearm_count ==
           D280_01_ENROLL_STAGES - 1u &&
         audit->enrollment_events.lifecycle.plan.command_32_count ==
           D280_01_ENROLL_STAGES &&
         audit->enrollment_events.rejected_inbound_count == 0u &&
         audit->enrollment_events.retry_count == 0u &&
         audit->enrollment_binding.retry_count == 0u &&
         audit->terminal_enroll_completion_hold_count == 1u &&
         audit->terminal_enroll_completion_release_count == 1u &&
         audit->terminal_enroll_completion_abort_count == 0u &&
         !audit->terminal_enroll_completion_held;
}

static gboolean
identify_audit_pass (const GoodixProductionEnrollmentAudit *audit)
{
  /* GOODIX_POST_TLS_PHASE_TERMINAL is the lifecycle failure state.  A
   * successful single-acquisition profile reaches GOODIX_POST_TLS_PHASE_STOP
   * and records that completion in single_acquisition_terminal_count without
   * setting post_tls.terminal. */
  return common_audit_pass (audit) &&
         audit->post_tls.first_image_pipeline_count == 1u &&
         audit->post_tls.release_tail_complete_count == 1u &&
         audit->post_tls.single_acquisition_terminal_count == 1u &&
         audit->post_tls.rearm_0x32_count == 0u &&
         audit->post_tls.second_image_pipeline_count == 0u &&
         audit->post_tls.third_cycle_command_count == 0u &&
         !audit->post_tls.terminal &&
         audit->post_tls.backend_drained &&
         audit->post_tls.terminal_cleanup_completed;
}

static void
print_epoch_audit (const gchar *prefix,
                   const GoodixProductionEnrollmentAudit *audit,
                   gboolean pass)
{
  g_print ("%s_CONTEXT_CLOSED=%s\n", prefix, bool_text (audit->context_closed));
  g_print ("%s_USB_REAL_SUBMIT_COUNT=%" G_GUINT64_FORMAT "\n", prefix,
           audit->usb_real_submit_count);
  g_print ("%s_USB_OUT_SUBMIT_COUNT=%" G_GUINT64_FORMAT "\n", prefix,
           audit->usb_out_submit_count);
  g_print ("%s_USB_IN_COMPLETION_COUNT=%" G_GUINT64_FORMAT "\n", prefix,
           audit->usb_in_completion_count);
  g_print ("%s_USB_OUT_COMPLETION_COUNT=%" G_GUINT64_FORMAT "\n", prefix,
           audit->usb_out_completion_count);
  g_print ("%s_USB_OUTSTANDING_AT_SNAPSHOT=%u\n", prefix,
           audit->usb_outstanding_count);
  g_print ("%s_USB_OUT_OUTSTANDING_AT_SNAPSHOT=%u\n", prefix,
           audit->usb_out_outstanding_count);
  g_print ("%s_USB_BACKEND_DRAINED=%s\n", prefix,
           bool_text (audit->usb_backend_drained));
  g_print ("%s_PRODUCTION_ACTION_CONSUMED=%s\n", prefix,
           bool_text (audit->production_action_consumed));
  g_print ("%s_USB_INTERFACE_CLAIMED=%s\n", prefix,
           bool_text (audit->usb_interface_claimed));
  g_print ("%s_RUNTIME_MATERIAL_PRESENT=%s\n", prefix,
           bool_text (audit->runtime_material_present));
  g_print ("%s_RUNTIME_HANDOFF_VIEWS_CLEARED=%s\n", prefix,
           bool_text (audit->runtime_handoff_views_cleared));
  g_print ("%s_RUNTIME_OWNER_FREE_COUNT=%u\n", prefix,
           audit->runtime_material.owner_free_count);
  g_print ("%s_RUNTIME_DESCRIPTOR_CLEANSED=%s\n", prefix,
           bool_text (audit->runtime_material.descriptor_cleansed));
  g_print ("%s_RUNTIME_FDT_SEED_CLEANSED=%s\n", prefix,
           bool_text (audit->runtime_material.fdt_seed_cleansed));
  g_print ("%s_TLS_HANDSHAKE_COUNT=%u\n", prefix,
           audit->tls.handshake_count);
  g_print ("%s_TLS_TERMINAL_COMPLETION_COUNT=%u\n", prefix,
           audit->tls.terminal_completion_count);
  g_print ("%s_TLS_PROJECT_SECRET_ZEROIZED=%s\n", prefix,
           bool_text (audit->tls.project_secret_zeroized));
  g_print ("%s_SECURE_RETRY_COUNT=%u\n", prefix, audit->secure.retry_count);
  g_print ("%s_SECURE_REOPEN_COUNT=%u\n", prefix,
           audit->secure.transport_reopen_count);
  g_print ("%s_SECURE_DEVICE_RESET_COUNT=%u\n", prefix,
           audit->secure.device_reset_count);
  g_print ("%s_SECURE_CLEAR_HALT_COUNT=%u\n", prefix,
           audit->secure.clear_halt_count);
  g_print ("%s_POST_TLS_RETRY_COUNT=%u\n", prefix, audit->post_tls.retry_count);
  g_print ("%s_POST_TLS_REOPEN_COUNT=%u\n", prefix,
           audit->post_tls.reopen_count);
  g_print ("%s_POST_TLS_DEVICE_RESET_COUNT=%u\n", prefix,
           audit->post_tls.device_reset_count);
  g_print ("%s_POST_TLS_CLEAR_HALT_COUNT=%u\n", prefix,
           audit->post_tls.clear_halt_count);
  g_print ("%s_KNOWN_PERSISTENT_FAMILY_COUNT=%u\n", prefix,
           known_persistent_family_count (audit));
  g_print ("%s_FIRST_IMAGE_PIPELINE_COUNT=%u\n", prefix,
           audit->post_tls.first_image_pipeline_count);
  g_print ("%s_RELEASE_TAIL_COMPLETE_COUNT=%u\n", prefix,
           audit->post_tls.release_tail_complete_count);
  g_print ("%s_SINGLE_ACQUISITION_TERMINAL_COUNT=%u\n", prefix,
           audit->post_tls.single_acquisition_terminal_count);
  g_print ("%s_REARM_0X32_COUNT=%u\n", prefix,
           audit->post_tls.rearm_0x32_count);
  g_print ("%s_SECOND_IMAGE_PIPELINE_COUNT=%u\n", prefix,
           audit->post_tls.second_image_pipeline_count);
  g_print ("%s_THIRD_CYCLE_COMMAND_COUNT=%u\n", prefix,
           audit->post_tls.third_cycle_command_count);
  g_print ("%s_POST_TLS_ERROR_TERMINAL=%s\n", prefix,
           bool_text (audit->post_tls.terminal));
  g_print ("%s_POST_TLS_BACKEND_DRAINED=%s\n", prefix,
           bool_text (audit->post_tls.backend_drained));
  g_print ("%s_POST_TLS_CLEANUP_COMPLETED=%s\n", prefix,
           bool_text (audit->post_tls.terminal_cleanup_completed));
  g_print ("%s_ENROLL_COMPLETED_STAGE_COUNT=%u\n", prefix,
           audit->enrollment_events.lifecycle.plan.pipeline.protocol.completed_stage_count);
  g_print ("%s_ENROLL_TERMINAL_TRANSITION_COUNT=%u\n", prefix,
           audit->enrollment_events.lifecycle.plan.pipeline.protocol.terminal_transition_count);
  g_print ("%s_ENROLL_INTER_STAGE_REARM_COUNT=%u\n", prefix,
           audit->enrollment_events.lifecycle.plan.inter_stage_rearm_count);
  g_print ("%s_ENROLL_COMMAND_32_COUNT=%u\n", prefix,
           audit->enrollment_events.lifecycle.plan.command_32_count);
  g_print ("%s_ENROLL_REJECTED_INBOUND_COUNT=%u\n", prefix,
           audit->enrollment_events.rejected_inbound_count);
  g_print ("%s_ENROLL_TERMINAL_HOLD_COUNT=%u\n", prefix,
           audit->terminal_enroll_completion_hold_count);
  g_print ("%s_ENROLL_TERMINAL_RELEASE_COUNT=%u\n", prefix,
           audit->terminal_enroll_completion_release_count);
  g_print ("%s_AUDIT_PASS=%s\n", prefix, bool_text (pass));
}

static gboolean
deadline_cb (gpointer user_data)
{
  RunState *state = user_data;
  state->deadline_expired = TRUE;
  g_print ("LIMITE_HOST_RAGGIUNTO=true\n");
  g_print ("NOTA_OPERATORE=Il limite e solo host-side; non prova quiescenza del sensore.\n");
  g_cancellable_cancel (state->cancellable);
  return G_SOURCE_REMOVE;
}

static gboolean
signal_cb (gpointer user_data)
{
  RunState *state = user_data;
  state->signal_received = TRUE;
  g_print ("INTERRUZIONE_OPERATORE_RICEVUTA=true\n");
  g_cancellable_cancel (state->cancellable);
  return G_SOURCE_CONTINUE;
}

static void
finger_status_changed (GObject *object, GParamSpec *pspec, gpointer user_data)
{
  RunState *state = user_data;
  FpFingerStatusFlags status = fp_device_get_finger_status (FP_DEVICE (object));
  gboolean release_ready = (status & FP_FINGER_STATUS_PRESENT) != 0 &&
                           (status & FP_FINGER_STATUS_NEEDED) == 0;
  gboolean was_release_ready =
    (state->last_finger_status & FP_FINGER_STATUS_PRESENT) != 0 &&
    (state->last_finger_status & FP_FINGER_STATUS_NEEDED) == 0;

  (void) pspec;
  if (release_ready && !was_release_ready)
    {
      state->release_ready_prompt_count++;
      g_print ("RILASCIO_FISICO_PRONTO=%u\n", state->release_ready_prompt_count);
      g_print ("AZIONE_OPERATORE=ORA TOGLI IL DITO.\n");
    }
  else if (state->phase == RUN_PHASE_ENROLL &&
           (status & FP_FINGER_STATUS_NEEDED) != 0 &&
           (status & FP_FINGER_STATUS_PRESENT) == 0 &&
           state->completed_stages > 0u &&
           (state->last_finger_status & FP_FINGER_STATUS_NEEDED) == 0)
    {
      state->reposition_prompt_count++;
      g_print ("RIPOSIZIONAMENTO_RICHIESTO=%u\n", state->reposition_prompt_count);
      g_print ("AZIONE_OPERATORE=RIPOSIZIONA LO STESSO DITO in una zona diversa.\n");
    }
  state->last_finger_status = status;
}

static void
enroll_progress_cb (FpDevice *device, gint completed_stages, FpPrint *print,
                    gpointer user_data, GError *error)
{
  RunState *state = user_data;
  (void) device;
  (void) print;

  if (error != NULL || completed_stages <= 0 ||
      (guint) completed_stages != state->completed_stages + 1u)
    {
      state->progress_error_count++;
      g_print ("ERRORE_STAGE=%s\n", error != NULL ? error->message :
               "progresso enrollment non monotono");
      g_print ("STOP_NO_RETRY=true\n");
      g_cancellable_cancel (state->cancellable);
      return;
    }
  state->completed_stages = (guint) completed_stages;
  g_print ("STAGE_COMPLETATO=%u/%u\n", state->completed_stages,
           D280_01_ENROLL_STAGES);
}

static void
identify_match_cb (FpDevice *device, FpPrint *match, FpPrint *print,
                   gpointer user_data, GError *error)
{
  RunState *state = user_data;
  (void) device;
  (void) print;

  if (error != NULL)
    {
      state->identify_retry_callback_count++;
      g_print ("IDENTIFY_RETRY_CALLBACK=%s\n", error->message);
      g_cancellable_cancel (state->cancellable);
    }
  else if (match != NULL)
    state->identify_match_callback_count++;
  else
    state->identify_no_match_callback_count++;
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
      if (g_strcmp0 (fp_device_get_driver (candidate), D280_01_DRIVER) == 0)
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
  const gchar *template_path = g_getenv ("D280_01_TEMPLATE_PATH");
  g_autoptr(FpContext) context = NULL;
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(FpPrint) template_print = NULL;
  g_autoptr(FpPrint) enrolled_print = NULL;
  g_autoptr(FpPrint) restored_print = NULL;
  g_autoptr(FpPrint) identify_match = NULL;
  g_autoptr(FpPrint) identify_scan = NULL;
  g_autoptr(GPtrArray) gallery = NULL;
  g_autoptr(GError) error = NULL;
  g_autoptr(GError) close_error = NULL;
  GoodixProductionEnrollmentAudit epoch1 = { 0 };
  GoodixProductionEnrollmentAudit epoch2 = { 0 };
  g_autofree guint8 *serialized = NULL;
  g_autofree guint8 *loaded = NULL;
  gsize serialized_length = 0u;
  gsize loaded_length = 0u;
  GPtrArray *devices;
  FpDevice *device = NULL;
  RunState state = { .cancellable = cancellable, .phase = RUN_PHASE_ENROLL };
  guint target_count = 0u;
  guint deadline_source = 0u;
  guint sigint_source = 0u;
  guint sigterm_source = 0u;
  gulong finger_status_handler = 0u;
  gboolean opened = FALSE;
  gboolean template_created = FALSE;
  gboolean epoch1_pass = FALSE;
  gboolean epoch2_pass = FALSE;
  gboolean identify_ok = FALSE;
  int result = 1;

  deadline_source = g_timeout_add_seconds (D280_01_HOST_DEADLINE_SECONDS,
                                           deadline_cb, &state);
  sigint_source = g_unix_signal_add (SIGINT, signal_cb, &state);
  sigterm_source = g_unix_signal_add (SIGTERM, signal_cb, &state);
  g_print ("LIVE_RUN_STARTED=true\n");
  g_print ("ACTION_ALLOWLIST=ENROLL_THEN_IDENTIFY\n");
  g_print ("ACTION_ATTEMPT_MAX=2\n");
  g_print ("OPEN_ATTEMPT_MAX=2\n");
  g_print ("HOST_DEADLINE_SECONDS=%u\n", D280_01_HOST_DEADLINE_SECONDS);
  g_print ("REAL_USB_ENUMERATION_ATTEMPTED=true\n");
  context = fp_context_new ();
  devices = fp_context_get_devices (context);
  device = select_exact_target (devices, &target_count);
  g_print ("TARGET_DRIVER_MATCH_COUNT=%u\n", target_count);
  if (device == NULL ||
      fp_device_get_nr_enroll_stages (device) != (gint) D280_01_ENROLL_STAGES)
    {
      g_printerr ("ERRORE=Serve esattamente un target Goodix con 8 stage.\n");
      goto out;
    }

  g_print ("OPEN_ATTEMPT_COUNT=1\n");
  state.open_attempt_count++;
  if (!fp_device_open_sync (device, cancellable, &error))
    {
      g_printerr ("ERRORE_OPEN_EPOCH1=%s\n", error->message);
      goto out;
    }
  opened = TRUE;
  state.open_success_count++;
  finger_status_handler = g_signal_connect (
    device, "notify::finger-status", G_CALLBACK (finger_status_changed), &state);
  template_print = fp_print_new (device);
  fp_print_set_finger (template_print, FP_FINGER_RIGHT_INDEX);
  state.last_finger_status = fp_device_get_finger_status (device);
  g_print ("AZIONE_OPERATORE=METTI L'INDICE DESTRO SUL SENSORE; usa sempre lo stesso dito.\n");
  g_print ("ENROLL_ACTION_ATTEMPT_COUNT=1\n");
  state.action_attempt_count++;
  state.enroll_action_attempt_count++;
  enrolled_print = fp_device_enroll_sync (
    device, g_steal_pointer (&template_print), cancellable,
    enroll_progress_cb, &state, &error);
  if (enrolled_print == NULL || state.deadline_expired || state.signal_received ||
      state.completed_stages != D280_01_ENROLL_STAGES ||
      state.release_ready_prompt_count != D280_01_ENROLL_STAGES ||
      state.reposition_prompt_count != D280_01_ENROLL_STAGES - 1u)
    {
      g_printerr ("ENROLLMENT_SUCCEEDED=false\n");
      if (error != NULL)
        g_printerr ("ERRORE_ENROLLMENT=%s\n", error->message);
      goto close_epoch1;
    }
  g_print ("ENROLLMENT_SUCCEEDED=true\n");
  if (!fp_print_serialize (enrolled_print, &serialized, &serialized_length,
                           &error) ||
      !persist_template (template_path, serialized, serialized_length, &error))
    {
      g_printerr ("FP3_EPHEMERAL_WRITE_SUCCEEDED=false\n");
      g_printerr ("ERRORE_FP3=%s\n", error->message);
      goto close_epoch1;
    }
  template_created = TRUE;
  g_print ("FP3_EPHEMERAL_WRITE_SUCCEEDED=true\n");
  secure_clear (serialized, serialized_length);
  g_clear_pointer (&serialized, g_free);
  serialized_length = 0u;
  g_clear_object (&enrolled_print);

close_epoch1:
  g_print ("CLOSE_EPOCH1_ATTEMPT_COUNT=1\n");
  state.close_attempt_count++;
  if (!fp_device_close_sync (device, NULL, &close_error))
    {
      g_printerr ("CLOSE_EPOCH1_SUCCEEDED=false\n");
      g_printerr ("ERRORE_CLOSE_EPOCH1=%s\n", close_error->message);
      opened = FALSE;
      goto out;
    }
  opened = FALSE;
  state.close_success_count++;
  g_print ("CLOSE_EPOCH1_SUCCEEDED=true\n");
  goodix_fpimage_device_get_production_enrollment_audit (
    (GoodixFpImageDevice *) device, &epoch1);
  epoch1_pass = enroll_audit_pass (&epoch1);
  print_epoch_audit ("EPOCH1_ENROLL", &epoch1, epoch1_pass);
  if (!epoch1_pass || !template_created)
    goto out;

  g_clear_error (&error);
  g_clear_error (&close_error);
  g_print ("OPEN_ATTEMPT_COUNT=2\n");
  state.open_attempt_count++;
  state.reopen_count++;
  if (!fp_device_open_sync (device, cancellable, &error))
    {
      g_printerr ("ERRORE_OPEN_EPOCH2=%s\n", error->message);
      goto out;
    }
  opened = TRUE;
  state.open_success_count++;
  if (!load_template (template_path, &loaded, &loaded_length, &error))
    {
      g_printerr ("FP3_EPHEMERAL_READ_SUCCEEDED=false\n");
      g_printerr ("ERRORE_FP3=%s\n", error->message);
      goto close_epoch2;
    }
  g_print ("FP3_EPHEMERAL_READ_SUCCEEDED=true\n");
  restored_print = fp_print_deserialize (loaded, loaded_length, &error);
  secure_clear (loaded, loaded_length);
  g_clear_pointer (&loaded, g_free);
  loaded_length = 0u;
  if (unlink (template_path) != 0)
    {
      g_printerr ("FP3_REMOVED_BEFORE_IDENTIFY=false\n");
      g_printerr ("ERRORE_UNLINK_FP3=%s\n", g_strerror (errno));
      goto close_epoch2;
    }
  template_created = FALSE;
  g_print ("FP3_REMOVED_BEFORE_IDENTIFY=true\n");
  if (restored_print == NULL ||
      !fp_print_compatible (restored_print, device))
    {
      g_printerr ("FP3_DESERIALIZE_COMPATIBLE=false\n");
      if (error != NULL)
        g_printerr ("ERRORE_DESERIALIZE=%s\n", error->message);
      goto close_epoch2;
    }
  g_print ("FP3_DESERIALIZE_COMPATIBLE=true\n");
  gallery = g_ptr_array_new_with_free_func (g_object_unref);
  g_ptr_array_add (gallery, g_object_ref (restored_print));
  state.phase = RUN_PHASE_IDENTIFY;
  state.last_finger_status = fp_device_get_finger_status (device);
  g_print ("AZIONE_OPERATORE=METTI DI NUOVO LO STESSO INDICE DESTRO per una sola identify.\n");
  g_print ("IDENTIFY_ACTION_ATTEMPT_COUNT=1\n");
  state.action_attempt_count++;
  state.identify_action_attempt_count++;
  identify_ok = fp_device_identify_sync (
    device, gallery, cancellable, identify_match_cb, &state,
    &identify_match, &identify_scan, &error);
  if (!identify_ok || identify_match == NULL ||
      state.identify_match_callback_count != 1u ||
      state.identify_no_match_callback_count != 0u ||
      state.identify_retry_callback_count != 0u)
    {
      g_printerr ("IDENTIFY_MATCH_SUCCEEDED=false\n");
      if (error != NULL)
        g_printerr ("ERRORE_IDENTIFY=%s\n", error->message);
    }
  else
    g_print ("IDENTIFY_MATCH_SUCCEEDED=true\n");

close_epoch2:
  g_clear_error (&close_error);
  g_print ("CLOSE_EPOCH2_ATTEMPT_COUNT=1\n");
  state.close_attempt_count++;
  if (!fp_device_close_sync (device, NULL, &close_error))
    {
      g_printerr ("CLOSE_EPOCH2_SUCCEEDED=false\n");
      g_printerr ("ERRORE_CLOSE_EPOCH2=%s\n", close_error->message);
      opened = FALSE;
      goto out;
    }
  opened = FALSE;
  state.close_success_count++;
  g_print ("CLOSE_EPOCH2_SUCCEEDED=true\n");
  goodix_fpimage_device_get_production_enrollment_audit (
    (GoodixFpImageDevice *) device, &epoch2);
  epoch2_pass = identify_audit_pass (&epoch2);
  print_epoch_audit ("EPOCH2_IDENTIFY", &epoch2, epoch2_pass);
  if (identify_ok && identify_match != NULL && epoch2_pass &&
      !state.deadline_expired && !state.signal_received &&
      state.identify_match_callback_count == 1u &&
      state.identify_no_match_callback_count == 0u &&
      state.identify_retry_callback_count == 0u)
    result = 0;

out:
  if (opened)
    {
      g_clear_error (&close_error);
      g_print ("FAILURE_CLOSE_ATTEMPTED=true\n");
      state.close_attempt_count++;
      if (!fp_device_close_sync (device, NULL, &close_error))
        g_printerr ("ERRORE_FAILURE_CLOSE=%s\n", close_error->message);
      else
        state.close_success_count++;
    }
  if (template_created)
    {
      if (unlink (template_path) == 0 || errno == ENOENT)
        {
          template_created = FALSE;
          g_print ("FP3_FAILURE_CLEANUP_REMOVED=true\n");
        }
      else
        g_printerr ("FP3_FAILURE_CLEANUP_REMOVED=false\n");
    }
  if (serialized != NULL)
    secure_clear (serialized, serialized_length);
  if (loaded != NULL)
    secure_clear (loaded, loaded_length);
  if (device != NULL && finger_status_handler != 0u)
    g_signal_handler_disconnect (device, finger_status_handler);
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
  g_print ("IDENTIFY_MATCH_CALLBACK_COUNT=%u\n",
           state.identify_match_callback_count);
  g_print ("IDENTIFY_NO_MATCH_CALLBACK_COUNT=%u\n",
           state.identify_no_match_callback_count);
  g_print ("IDENTIFY_RETRY_CALLBACK_COUNT=%u\n",
           state.identify_retry_callback_count);
  g_print ("D280_01_RUNTIME_COUNTERS_BEGIN=true\n");
  g_print ("D280_01_OBSERVED_ACTION_ATTEMPT_COUNT=%u\n",
           state.action_attempt_count);
  g_print ("D280_01_OBSERVED_ENROLL_ACTION_ATTEMPT_COUNT=%u\n",
           state.enroll_action_attempt_count);
  g_print ("D280_01_OBSERVED_IDENTIFY_ACTION_ATTEMPT_COUNT=%u\n",
           state.identify_action_attempt_count);
  g_print ("D280_01_OBSERVED_OPEN_ATTEMPT_COUNT=%u\n",
           state.open_attempt_count);
  g_print ("D280_01_OBSERVED_OPEN_SUCCESS_COUNT=%u\n",
           state.open_success_count);
  g_print ("D280_01_OBSERVED_REOPEN_COUNT=%u\n", state.reopen_count);
  g_print ("D280_01_OBSERVED_CLOSE_ATTEMPT_COUNT=%u\n",
           state.close_attempt_count);
  g_print ("D280_01_OBSERVED_CLOSE_SUCCESS_COUNT=%u\n",
           state.close_success_count);
  g_print ("D280_01_RUNTIME_COUNTERS_END=true\n");
  g_print ("OPERATOR_RETRY_COUNT=0\n");
  g_print ("KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0\n");
  g_print ("SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false\n");
  g_print ("HOST_DEADLINE_EXPIRED=%s\n", bool_text (state.deadline_expired));
  g_print ("OPERATOR_SIGNAL_RECEIVED=%s\n", bool_text (state.signal_received));
  g_print ("D280_01_EPHEMERAL_TEMPLATE_REUSE_PASS=%s\n",
           bool_text (result == 0));
  if (result != 0)
    g_print ("NOTA_OPERATORE=Run terminata senza successo: non ripetere; conserva solo log e summary.\n");
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
