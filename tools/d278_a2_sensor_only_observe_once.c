/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * D278/09 exact sensor-only A2 risk probe launcher.
 *
 * The default build is live-unapproved.  Authorization is checked before a
 * GUsb context exists.  The live path has one OUT endpoint and one IN endpoint
 * but no secure-session, TLS, PSK/store, retry, reopen, reset or clear-halt.
 */
#include <string.h>

#include <gio/gio.h>
#include <glib.h>

#include "goodix_a0_protocol.h"
#include "goodix_d278_a2_sensor_only_probe.h"

#define D278_09_VID 0x27c6u
#define D278_09_PID 0x5125u
#define D278_09_INTERFACE 0u
#define D278_09_EP_OUT 0x01u
#define D278_09_EP_IN 0x81u
#define D278_09_GENERATION 1u

#ifndef D278_09_APPROVED_BASELINE
#define D278_09_APPROVED_BASELINE "UNAPPROVED_FOR_LIVE"
#endif

#define D278_09_AUTHORIZATION_TOKEN \
  "D278_09_ONE_A2_SENSOR_ONLY_EXACT_01_14_NO_RETRY"
#define D278_09_OPERATION_NAME "D278_09_A2_SENSOR_ONLY_RISK_PROBE"

static const guint8 target_a2_typed_sha256[32] = {
  0x39, 0xe4, 0x69, 0xce, 0x5a, 0x5b, 0xa3, 0x13,
  0x6c, 0x4a, 0x44, 0x38, 0x1f, 0x2e, 0x41, 0x83,
  0xdc, 0xa2, 0x75, 0x25, 0x7a, 0xdf, 0xcf, 0x3c,
  0x00, 0x25, 0x09, 0x4f, 0x05, 0xc0, 0x22, 0xf5,
};

typedef struct
{
  GoodixD278A2SensorOnlyProbe *probe;
  GoodixD278A2Direction direction;
  guint64 generation;
  guint timeout_ms;
  GBytes *out_frame;
  guint submit_count;
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
self_test_submit (GoodixD278A2SensorOnlyProbe *probe,
                  GoodixD278A2Direction        direction,
                  guint64                      generation,
                  GBytes                      *bytes,
                  guint                        timeout_ms,
                  gpointer                     user_data,
                  GError                     **error)
{
  SelfTestSubmit *submit = user_data;

  (void) error;
  submit->probe = probe;
  submit->direction = direction;
  submit->generation = generation;
  submit->timeout_ms = timeout_ms;
  submit->submit_count++;
  if (direction == GOODIX_D278_A2_TRANSFER_OUT)
    submit->out_frame = g_bytes_ref (bytes);
  return TRUE;
}

static void
self_test_complete_frame (SelfTestSubmit *submit,
                          GBytes         *frame)
{
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);

  goodix_d278_a2_sensor_only_probe_complete (
    submit->probe, submit->direction, submit->generation, data, length, NULL);
}

static int
run_self_test (void)
{
  static const guint8 typed_body[] = { 1, 2, 3 };
  static const guint8 ack_body[] = { 0xa2, 0x01 };
  static const guint8 expected_out[] = {
    0xa0, 0x06, 0x00, 0xa6, 0xa2, 0x03, 0x00, 0x01, 0x14, 0xf0,
  };
  guint8 expected_hash[32];
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GBytes) typed = NULL;
  g_autofree gchar *json = NULL;
  SelfTestSubmit submit = { 0 };
  GoodixD278A2SensorOnlyProbe *probe;
  GoodixD278A2ProbeAudit *audit;
  gsize out_length;
  const guint8 *out_data;
  int result = 1;

  digest (typed_body, sizeof typed_body, expected_hash);
  probe = goodix_d278_a2_sensor_only_probe_new (expected_hash,
                                                 self_test_submit, &submit);
  if (!goodix_d278_a2_sensor_only_probe_start (probe, D278_09_GENERATION,
                                                &error))
    goto out;
  out_data = g_bytes_get_data (submit.out_frame, &out_length);
  if (out_length != sizeof expected_out ||
      memcmp (out_data, expected_out, sizeof expected_out) != 0)
    goto out;
  goodix_d278_a2_sensor_only_probe_complete (
    probe, GOODIX_D278_A2_TRANSFER_OUT, submit.generation,
    NULL, out_length, NULL);
  ack = goodix_a0_build_frame (0xb0, 0xb0, ack_body, sizeof ack_body, &error);
  if (ack == NULL)
    goto out;
  self_test_complete_frame (&submit, ack);
  typed = goodix_a0_build_frame (0xa2, 0xa2, typed_body,
                                 sizeof typed_body, &error);
  if (typed == NULL)
    goto out;
  self_test_complete_frame (&submit, typed);

  audit = goodix_d278_a2_sensor_only_probe_get_mutable_audit (probe);
  audit->identity_preflight_result = "HOST_ONLY_SYNTHETIC_NO_USB";
  json = goodix_d278_a2_sensor_only_probe_audit_to_json (probe);
  g_print ("%s\n", json);
  if (goodix_d278_a2_sensor_only_probe_succeeded (probe) &&
      audit->goodix_command_count == 1 && audit->out_submit_count == 1 &&
      audit->a2_sensor_only_submit_count == 1 &&
      audit->physical_in_submit_count == 2 &&
      audit->physical_in_completion_count == 2 &&
      audit->ack_count == 1 && audit->typed_response_count == 1 &&
      audit->retry_count == 0 && audit->tls_handshake_count == 0 &&
      audit->backend_drained && audit->cleanup_completed)
    result = 0;

out:
  g_clear_pointer (&submit.out_frame, g_bytes_unref);
  goodix_d278_a2_sensor_only_probe_free (probe);
  return result;
}

#ifdef D278_09_LIVE_BINDING
#include <gusb.h>
#include <glib-unix.h>

typedef struct
{
  GUsbDevice *target;
  GCancellable *cancellable;
} LiveSubmit;

typedef struct
{
  GoodixD278A2SensorOnlyProbe *probe;
  GoodixD278A2Direction direction;
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

  goodix_d278_a2_sensor_only_probe_complete (
    transfer->probe, transfer->direction, transfer->generation,
    transfer->direction == GOODIX_D278_A2_TRANSFER_IN ? transfer->buffer : NULL,
    length, completion_error);
  g_free (transfer->buffer);
  g_free (transfer);
}

static gboolean
live_submit (GoodixD278A2SensorOnlyProbe *probe,
             GoodixD278A2Direction        direction,
             guint64                      generation,
             GBytes                      *bytes,
             guint                        timeout_ms,
             gpointer                     user_data,
             GError                     **error)
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
  if (direction == GOODIX_D278_A2_TRANSFER_OUT)
    {
      data = g_bytes_get_data (bytes, &length);
      transfer->buffer = g_memdup2 (data, length);
      endpoint = D278_09_EP_OUT;
    }
  else
    {
      length = GOODIX_D278_09_RECEIVE_SIZE;
      transfer->buffer = g_malloc0 (length);
      endpoint = D278_09_EP_IN;
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
    g_getenv ("D278_09_APPROVED_LIVE_BASELINE_SHA");
  const gchar *authorization =
    g_getenv ("D278_09_OPERATOR_AUTHORIZATION");
  const gchar *operation = g_getenv ("D278_09_OPERATION");

  if (g_str_equal (D278_09_APPROVED_BASELINE, "UNAPPROVED_FOR_LIVE") ||
      !is_full_sha (D278_09_APPROVED_BASELINE))
    return FALSE;
  return runtime_sha != NULL && authorization != NULL && operation != NULL &&
         is_full_sha (runtime_sha) &&
         g_str_equal (runtime_sha, D278_09_APPROVED_BASELINE) &&
         g_str_equal (authorization, D278_09_AUTHORIZATION_TOKEN) &&
         g_str_equal (operation, D278_09_OPERATION_NAME);
}

static gboolean
cancel_on_signal (gpointer user_data)
{
  g_cancellable_cancel (G_CANCELLABLE (user_data));
  return G_SOURCE_CONTINUE;
}

static void
record_host_failure (GoodixD278A2ProbeAudit *audit,
                     const gchar            *error_class)
{
  audit->completion_class = "HOST_BOUNDARY_ERROR";
  audit->error_class = error_class;
  audit->current_context_result = "NOT_OBSERVED";
}

static int
run_live_once (void)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GUsbContext) usb_context = NULL;
  g_autoptr(GPtrArray) devices = NULL;
  g_autoptr(GCancellable) cancellable = NULL;
  g_autofree gchar *json = NULL;
  GoodixD278A2SensorOnlyProbe *probe = NULL;
  GoodixD278A2ProbeAudit *audit;
  LiveSubmit submit = { 0 };
  GUsbDevice *target = NULL;
  guint matches = 0;
  guint interrupt_source = 0;
  guint terminate_source = 0;
  gboolean opened = FALSE;
  gboolean claimed = FALSE;
  int return_code = 1;

  /* Host-only closure and every ordinary build stop here, before context
   * creation or enumeration.  A future review must compile a full approved
   * SHA and the operator must repeat that exact SHA plus both exact tokens. */
  if (!live_authorization_gate ())
    {
      g_printerr ("LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED\n");
      return 3;
    }

  cancellable = g_cancellable_new ();
  submit.cancellable = cancellable;
  probe = goodix_d278_a2_sensor_only_probe_new (target_a2_typed_sha256,
                                                 live_submit, &submit);
  audit = goodix_d278_a2_sensor_only_probe_get_mutable_audit (probe);
  audit->approved_baseline = D278_09_APPROVED_BASELINE;
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
      if (g_usb_device_get_vid (candidate) == D278_09_VID &&
          g_usb_device_get_pid (candidate) == D278_09_PID)
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
    "EXACT_ONE_27C6_5125_PRIOR_D277_02_APP12509_AND_EXACT_A2_PROOF_NO_CURRENT_A8";
  submit.target = target;

  if (!g_usb_device_open (target, &error))
    {
      record_host_failure (audit, "USB_OPEN_FAILED");
      goto cleanup;
    }
  opened = TRUE;
  audit->usb_open_count = 1;
  if (!g_usb_device_claim_interface (target, D278_09_INTERFACE,
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
  if (!goodix_d278_a2_sensor_only_probe_start (probe, D278_09_GENERATION,
                                                &error))
    goto cleanup;
  while (!goodix_d278_a2_sensor_only_probe_is_terminal (probe))
    g_main_context_iteration (NULL, TRUE);

cleanup:
  if (interrupt_source != 0)
    g_source_remove (interrupt_source);
  if (terminate_source != 0)
    g_source_remove (terminate_source);
  if (claimed)
    {
      g_clear_error (&error);
      if (g_usb_device_release_interface (target, D278_09_INTERFACE,
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
  json = goodix_d278_a2_sensor_only_probe_audit_to_json (probe);
  g_print ("%s\n", json);
  if (goodix_d278_a2_sensor_only_probe_succeeded (probe) &&
      audit->cleanup_completed && audit->goodix_command_count == 1 &&
      audit->out_submit_count == 1 &&
      audit->a2_sensor_only_submit_count == 1 &&
      audit->physical_in_submit_count == 2 &&
      audit->physical_in_completion_count == 2 &&
      audit->retry_count == 0)
    return_code = 0;
  goodix_d278_a2_sensor_only_probe_free (probe);
  return return_code;
}
#endif

int
main (int argc, char **argv)
{
  if (argc == 2 && g_str_equal (argv[1], "--self-test"))
    return run_self_test ();
#ifdef D278_09_LIVE_BINDING
  if (argc == 2 &&
      g_str_equal (argv[1], "--live-a2-sensor-only-observe-once"))
    return run_live_once ();
#endif
  g_printerr ("usage: %s --self-test\n", argv[0]);
  return 2;
}
