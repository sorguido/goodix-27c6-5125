/* SPDX-License-Identifier: GPL-2.0-or-later */
/* D278/10 live-capable, ordinary-build-unapproved A2 -> A8 launcher. */
#include <string.h>

#include <gio/gio.h>
#include <glib.h>

#include "goodix_a0_protocol.h"
#include "goodix_d278_a2_a8_reentry_probe.h"

#define D278_10_VID 0x27c6u
#define D278_10_PID 0x5125u
#define D278_10_INTERFACE 0u
#define D278_10_EP_OUT 0x01u
#define D278_10_EP_IN 0x81u
#define D278_10_GENERATION 1u

#ifndef D278_10_APPROVED_BASELINE
#define D278_10_APPROVED_BASELINE "UNAPPROVED_FOR_LIVE"
#endif

#define D278_10_AUTHORIZATION_TOKEN \
  "D278_10_ONE_SAME_SESSION_A2_THEN_A8_NO_RETRY"
#define D278_10_OPERATION_NAME "D278_10_SAME_SESSION_A2_A8_REENTRY_PROBE"

static const guint8 target_a2_typed_sha256[32] = {
  0x39, 0xe4, 0x69, 0xce, 0x5a, 0x5b, 0xa3, 0x13,
  0x6c, 0x4a, 0x44, 0x38, 0x1f, 0x2e, 0x41, 0x83,
  0xdc, 0xa2, 0x75, 0x25, 0x7a, 0xdf, 0xcf, 0x3c,
  0x00, 0x25, 0x09, 0x4f, 0x05, 0xc0, 0x22, 0xf5,
};

typedef struct
{
  GoodixD278A2A8ReentryProbe *probe;
  GoodixD278A2A8Direction direction;
  guint64 generation;
  GBytes *out_frame;
} SelfTestSubmit;

static void
digest (const guint8 *data,
        gsize         length,
        guint8        result[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  gsize result_length = 32;

  g_assert_cmpuint (length, <=, G_MAXSSIZE);
  g_checksum_update (checksum, data, (gssize) length);
  g_checksum_get_digest (checksum, result, &result_length);
  g_assert_cmpuint (result_length, ==, 32);
}

static gboolean
self_test_submit (GoodixD278A2A8ReentryProbe *probe,
                  GoodixD278A2A8Direction direction,
                  guint64 generation,
                  GBytes *bytes,
                  guint timeout_ms,
                  gpointer user_data,
                  GError **error)
{
  SelfTestSubmit *submit = user_data;

  (void) timeout_ms;
  (void) error;
  submit->probe = probe;
  submit->direction = direction;
  submit->generation = generation;
  if (direction == GOODIX_D278_10_TRANSFER_OUT)
    {
      g_clear_pointer (&submit->out_frame, g_bytes_unref);
      submit->out_frame = g_bytes_ref (bytes);
    }
  return TRUE;
}

static void
self_test_complete_frame (SelfTestSubmit *submit,
                          GBytes         *frame)
{
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);

  goodix_d278_a2_a8_reentry_probe_complete (
    submit->probe, submit->direction, submit->generation, data, length, NULL);
}

static int
run_self_test (void)
{
  static const guint8 a2_typed_body[] = { 1, 2, 3 };
  static const guint8 a2_ack_body[] = { 0xa2, 0x07 };
  static const guint8 a8_ack_body[] = { 0xa8, 0x01 };
  static const guint8 app12509[] = "GF_ST411SEC_APP_12509";
  guint8 expected_hash[32];
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) a2_ack = NULL;
  g_autoptr(GBytes) a2_typed = NULL;
  g_autoptr(GBytes) a8_ack = NULL;
  g_autoptr(GBytes) a8_typed = NULL;
  g_autofree gchar *json = NULL;
  SelfTestSubmit submit = { 0 };
  GoodixD278A2A8ReentryProbe *probe;
  GoodixD278A2A8Audit *audit;
  gsize out_length;
  int result = 1;

  digest (a2_typed_body, sizeof a2_typed_body, expected_hash);
  probe = goodix_d278_a2_a8_reentry_probe_new (expected_hash,
                                                self_test_submit, &submit);
  if (!goodix_d278_a2_a8_reentry_probe_start (probe, D278_10_GENERATION,
                                               &error))
    goto out;
  out_length = g_bytes_get_size (submit.out_frame);
  goodix_d278_a2_a8_reentry_probe_complete (
    probe, submit.direction, submit.generation, NULL, out_length, NULL);
  a2_ack = goodix_a0_build_frame (0xb0, 0xb0, a2_ack_body,
                                   sizeof a2_ack_body, &error);
  if (a2_ack == NULL)
    goto out;
  self_test_complete_frame (&submit, a2_ack);
  a2_typed = goodix_a0_build_frame (0xa2, 0xa2, a2_typed_body,
                                     sizeof a2_typed_body, &error);
  if (a2_typed == NULL)
    goto out;
  self_test_complete_frame (&submit, a2_typed);
  out_length = g_bytes_get_size (submit.out_frame);
  goodix_d278_a2_a8_reentry_probe_complete (
    probe, submit.direction, submit.generation, NULL, out_length, NULL);
  a8_ack = goodix_a0_build_frame (0xb0, 0xb0, a8_ack_body,
                                   sizeof a8_ack_body, &error);
  if (a8_ack == NULL)
    goto out;
  self_test_complete_frame (&submit, a8_ack);
  a8_typed = goodix_a0_build_frame (0xa8, 0xa8, app12509,
                                     sizeof app12509, &error);
  if (a8_typed == NULL)
    goto out;
  self_test_complete_frame (&submit, a8_typed);

  audit = goodix_d278_a2_a8_reentry_probe_get_mutable_audit (probe);
  audit->identity_preflight_result = "HOST_ONLY_SYNTHETIC_NO_USB";
  json = goodix_d278_a2_a8_reentry_probe_audit_to_json (probe);
  g_print ("%s\n", json);
  if (goodix_d278_a2_a8_reentry_probe_succeeded (probe) &&
      audit->goodix_command_count == 2 && audit->out_submit_count == 2 &&
      audit->a2_sensor_only_submit_count == 1 &&
      audit->a2_ack_count == 1 && audit->a2_typed_response_count == 1 &&
      audit->a8_submit_count == 1 && audit->a8_ack_count == 1 &&
      audit->a8_typed_response_count == 1 &&
      audit->a8_app12509_pin_match &&
      audit->physical_in_submit_count == 4 &&
      audit->physical_in_completion_count == 4 &&
      audit->retry_count == 0 && audit->tls_handshake_count == 0 &&
      audit->backend_drained && audit->cleanup_completed)
    result = 0;

out:
  g_clear_pointer (&submit.out_frame, g_bytes_unref);
  goodix_d278_a2_a8_reentry_probe_free (probe);
  return result;
}

#ifdef D278_10_LIVE_BINDING
#include <gusb.h>
#include <glib-unix.h>

typedef struct
{
  GUsbDevice *target;
  GCancellable *cancellable;
} LiveSubmit;

typedef struct
{
  GoodixD278A2A8ReentryProbe *probe;
  GoodixD278A2A8Direction direction;
  guint64 generation;
  GUsbDevice *target;
  guint8 *buffer;
} LiveTransfer;

static void
live_transfer_complete (GObject      *source_object,
                        GAsyncResult *result,
                        gpointer      user_data)
{
  LiveTransfer *transfer = user_data;
  g_autoptr(GError) error = NULL;
  g_autoptr(GError) translated = NULL;
  const GError *completion_error = NULL;
  gssize actual_length;
  gsize length = 0;

  (void) source_object;
  actual_length = g_usb_device_bulk_transfer_finish (transfer->target,
                                                      result, &error);
  if (actual_length >= 0)
    length = (gsize) actual_length;
  else if (g_error_matches (error, G_USB_DEVICE_ERROR,
                            G_USB_DEVICE_ERROR_TIMED_OUT))
    {
      g_set_error_literal (&translated, G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
                           "bounded Goodix transfer timed out");
      completion_error = translated;
    }
  else if (g_error_matches (error, G_USB_DEVICE_ERROR,
                            G_USB_DEVICE_ERROR_CANCELLED))
    {
      g_set_error_literal (&translated, G_IO_ERROR, G_IO_ERROR_CANCELLED,
                           "bounded Goodix transfer was cancelled");
      completion_error = translated;
    }
  else
    completion_error = error;

  goodix_d278_a2_a8_reentry_probe_complete (
    transfer->probe, transfer->direction, transfer->generation,
    transfer->direction == GOODIX_D278_10_TRANSFER_IN ? transfer->buffer : NULL,
    length, completion_error);
  g_free (transfer->buffer);
  g_free (transfer);
}

static gboolean
live_submit (GoodixD278A2A8ReentryProbe *probe,
             GoodixD278A2A8Direction direction,
             guint64 generation,
             GBytes *bytes,
             guint timeout_ms,
             gpointer user_data,
             GError **error)
{
  LiveSubmit *submit = user_data;
  LiveTransfer *transfer;
  gsize length;
  const guint8 *data;
  guint8 endpoint;

  if (submit->target == NULL || submit->cancellable == NULL)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                           "live USB binding is incomplete");
      return FALSE;
    }
  transfer = g_new0 (LiveTransfer, 1);
  transfer->probe = probe;
  transfer->direction = direction;
  transfer->generation = generation;
  transfer->target = submit->target;
  if (direction == GOODIX_D278_10_TRANSFER_OUT)
    {
      data = g_bytes_get_data (bytes, &length);
      transfer->buffer = g_memdup2 (data, length);
      endpoint = D278_10_EP_OUT;
    }
  else
    {
      length = GOODIX_D278_10_RECEIVE_SIZE;
      transfer->buffer = g_malloc0 (length);
      endpoint = D278_10_EP_IN;
    }
  g_usb_device_bulk_transfer_async (submit->target, endpoint,
                                    transfer->buffer, length, timeout_ms,
                                    submit->cancellable,
                                    live_transfer_complete, transfer);
  return TRUE;
}

static gboolean
is_full_sha (const gchar *value)
{
  if (value == NULL || strlen (value) != 40)
    return FALSE;
  for (guint i = 0; i < 40; i++)
    if (!g_ascii_isxdigit (value[i]))
      return FALSE;
  return TRUE;
}

static gboolean
live_authorization_gate (void)
{
  const gchar *runtime_sha =
    g_getenv ("D278_10_APPROVED_LIVE_BASELINE_SHA");
  const gchar *authorization =
    g_getenv ("D278_10_OPERATOR_AUTHORIZATION");
  const gchar *operation = g_getenv ("D278_10_OPERATION");

  if (g_str_equal (D278_10_APPROVED_BASELINE, "UNAPPROVED_FOR_LIVE") ||
      !is_full_sha (D278_10_APPROVED_BASELINE))
    return FALSE;
  return runtime_sha != NULL && authorization != NULL && operation != NULL &&
         is_full_sha (runtime_sha) &&
         g_str_equal (runtime_sha, D278_10_APPROVED_BASELINE) &&
         g_str_equal (authorization, D278_10_AUTHORIZATION_TOKEN) &&
         g_str_equal (operation, D278_10_OPERATION_NAME);
}

static gboolean
cancel_on_signal (gpointer user_data)
{
  g_cancellable_cancel (G_CANCELLABLE (user_data));
  return G_SOURCE_CONTINUE;
}

static void
record_host_failure (GoodixD278A2A8Audit *audit,
                     const gchar         *error_class)
{
  audit->completion_class = "HOST_BOUNDARY_ERROR";
  audit->error_class = error_class;
  audit->reentry_result_class = "NOT_OBSERVED";
}

static int
run_live_once (void)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GUsbContext) usb_context = NULL;
  g_autoptr(GPtrArray) devices = NULL;
  g_autoptr(GCancellable) cancellable = NULL;
  g_autofree gchar *json = NULL;
  GoodixD278A2A8ReentryProbe *probe = NULL;
  GoodixD278A2A8Audit *audit;
  LiveSubmit submit = { 0 };
  GUsbDevice *target = NULL;
  guint matches = 0;
  guint interrupt_source = 0;
  guint terminate_source = 0;
  gboolean opened = FALSE;
  gboolean claimed = FALSE;
  int return_code = 1;

  /* This gate precedes GUsb context creation and enumeration. */
  if (!live_authorization_gate ())
    {
      g_printerr ("LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED\n");
      return 3;
    }

  cancellable = g_cancellable_new ();
  submit.cancellable = cancellable;
  probe = goodix_d278_a2_a8_reentry_probe_new (target_a2_typed_sha256,
                                                live_submit, &submit);
  audit = goodix_d278_a2_a8_reentry_probe_get_mutable_audit (probe);
  audit->approved_baseline = D278_10_APPROVED_BASELINE;
  audit->identity_preflight_result = "HOST_DESCRIPTOR_GATE_NOT_COMPLETED";

  usb_context = g_usb_context_new (&error);
  if (usb_context == NULL || !g_usb_context_enumerate (usb_context, &error))
    {
      record_host_failure (audit, "USB_ENUMERATION_FAILED");
      goto cleanup;
    }
  devices = g_usb_context_get_devices (usb_context);
  for (guint i = 0; i < devices->len; i++)
    {
      GUsbDevice *candidate = g_ptr_array_index (devices, i);
      if (g_usb_device_get_vid (candidate) == D278_10_VID &&
          g_usb_device_get_pid (candidate) == D278_10_PID)
        {
          target = candidate;
          matches++;
        }
    }
  if (matches != 1)
    {
      audit->identity_preflight_result = "EXACT_ONE_27C6_5125_REQUIRED";
      record_host_failure (audit, "TARGET_COUNT_NOT_ONE");
      goto cleanup;
    }
  audit->identity_preflight_result =
    "EXACT_ONE_27C6_5125_PRIOR_D277_02_APP12509_AND_D278_09_A2_PROOF";
  submit.target = target;

  if (!g_usb_device_open (target, &error))
    {
      record_host_failure (audit, "USB_OPEN_FAILED");
      goto cleanup;
    }
  opened = TRUE;
  audit->usb_open_count = 1;
  if (!g_usb_device_claim_interface (target, D278_10_INTERFACE,
                                      G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                      &error))
    {
      record_host_failure (audit, "USB_CLAIM_FAILED");
      goto cleanup;
    }
  claimed = TRUE;
  audit->usb_claim_count = 1;
  interrupt_source = g_unix_signal_add (SIGINT, cancel_on_signal, cancellable);
  terminate_source = g_unix_signal_add (SIGTERM, cancel_on_signal, cancellable);
  if (!goodix_d278_a2_a8_reentry_probe_start (probe, D278_10_GENERATION,
                                               &error))
    goto cleanup;
  while (!goodix_d278_a2_a8_reentry_probe_is_terminal (probe))
    g_main_context_iteration (NULL, TRUE);

cleanup:
  if (interrupt_source != 0)
    g_source_remove (interrupt_source);
  if (terminate_source != 0)
    g_source_remove (terminate_source);
  if (claimed)
    {
      g_clear_error (&error);
      if (g_usb_device_release_interface (target, D278_10_INTERFACE,
                                           G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                           &error))
        audit->usb_release_count = 1;
      else
        audit->error_class = "USB_RELEASE_FAILED";
    }
  if (opened)
    {
      g_clear_error (&error);
      if (g_usb_device_close (target, &error))
        audit->usb_close_count = 1;
      else
        audit->error_class = "USB_CLOSE_FAILED";
    }
  audit->cleanup_completed =
    audit->backend_drained && (!claimed || audit->usb_release_count == 1) &&
    (!opened || audit->usb_close_count == 1);
  json = goodix_d278_a2_a8_reentry_probe_audit_to_json (probe);
  g_print ("%s\n", json);
  if (goodix_d278_a2_a8_reentry_probe_succeeded (probe) &&
      audit->cleanup_completed && audit->goodix_command_count == 2 &&
      audit->out_submit_count == 2 &&
      audit->a2_sensor_only_submit_count == 1 &&
      audit->a8_submit_count == 1 && audit->physical_in_submit_count == 4 &&
      audit->physical_in_completion_count == 4 && audit->retry_count == 0)
    return_code = 0;
  goodix_d278_a2_a8_reentry_probe_free (probe);
  return return_code;
}
#endif

int
main (int argc, char **argv)
{
  if (argc == 2 && g_str_equal (argv[1], "--self-test"))
    return run_self_test ();
#ifdef D278_10_LIVE_BINDING
  if (argc == 2 &&
      g_str_equal (argv[1], "--live-same-session-a2-a8-observe-once"))
    return run_live_once ();
#endif
  g_printerr ("usage: %s --self-test\n", argv[0]);
  return 2;
}
