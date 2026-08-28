/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * D277/01 test-only native A8 probe.
 *
 * The executable has one sensor-reaching mode and one immutable command.  It
 * is not a libfprint driver and is never installed or registered.  The A8
 * protocol contract below comes from the neutral D277 prompt and the
 * canonical project manual; no GPL runtime implementation was consulted.
 */
#include <gio/gio.h>
#include <glib.h>
#include <string.h>

#include "goodix_fpi_usb_backend.h"
#include "goodix_usb_router.h"

#ifdef D277_LIVE_BINDING
#include <gusb.h>
#include "fpi-device.h"
#endif

#define D277_VID 0x27c6u
#define D277_PID 0x5125u
#define D277_INTERFACE 0u
#define D277_EP_OUT 0x01u
#define D277_EP_IN 0x81u
#define D277_RECEIVE_SIZE 64u
#define D277_A8_TIMEOUT_MS 1000u
#define D277_GENERATION 1u

static const guint8 a8_request[] = {
  0xa0, 0x06, 0x00, 0xa6, 0xa8, 0x03, 0x00, 0x00, 0x00, 0xff
};
static const guint8 expected_firmware[] = "GF_ST411SEC_APP_12509";

typedef struct
{
  GoodixUsbRouter *router;
  GoodixFpiUsbBackend *backend;
  GCancellable *cancellable;
  GMainLoop *loop;
  guint idle_source;
  guint timeout_source;
  guint target_vid;
  guint target_pid;
  guint out_command_count;
  guint logical_ack_count;
  guint typed_response_count;
  guint in_submit_count;
  guint in_completion_count;
  guint retry_count;
  guint reopen_count;
  guint reset_count;
  guint device_cancel_command_count;
  guint secret_count;
  guint tls_count;
  guint finger_wait_count;
  guint image_count;
  guint persistent_write_count;
  gboolean firmware_match;
  gboolean terminal_requested;
  gboolean drained;
  gboolean success;
  gchar *failure_class;
  guint8 unexpected_outer_type;
  guint8 unexpected_control;
  gsize last_observed_length;
} D277Probe;

typedef struct
{
  guint in_submits;
  guint out_submits;
  guint max_in_outstanding;
  guint in_outstanding;
  GBytes *last_out;
} SyntheticUsb;

static void probe_request_terminal (D277Probe *probe);

static void
probe_fail (D277Probe *probe, const gchar *failure_class)
{
  if (probe->failure_class == NULL)
    probe->failure_class = g_strdup (failure_class);
  probe->success = FALSE;
  probe_request_terminal (probe);
}

static gboolean
validate_outer_and_inner (GBytes *frame,
                          guint8 *control,
                          const guint8 **body,
                          gsize *body_length,
                          gsize *frame_length)
{
  const guint8 *bytes;
  gsize length;
  guint outer_length;
  guint inner_length;
  guint checksum = 0;
  gsize i;

  bytes = g_bytes_get_data (frame, &length);
  if (frame_length != NULL)
    *frame_length = length;
  if (length < 8 || bytes[0] != 0xa0)
    return FALSE;
  outer_length = (guint) bytes[1] | ((guint) bytes[2] << 8);
  if ((gsize) outer_length + 4 != length ||
      bytes[3] != (guint8) (bytes[0] + bytes[1] + bytes[2]))
    return FALSE;
  inner_length = (guint) bytes[5] | ((guint) bytes[6] << 8);
  if (inner_length < 1 || outer_length != inner_length + 3)
    return FALSE;
  for (i = 4; i < length; i++)
    checksum = (checksum + bytes[i]) & 0xffu;
  if (checksum != 0xaau)
    return FALSE;
  *control = bytes[4];
  *body = bytes + 7;
  *body_length = (gsize) inner_length - 1;
  return TRUE;
}

static void
a0_consumer (guint8 outer_type, GBytes *frame, gpointer user_data)
{
  D277Probe *probe = user_data;
  const guint8 *body = NULL;
  gsize body_length = 0;
  guint8 control = 0;

  probe->last_observed_length = g_bytes_get_size (frame);
  if (outer_type != 0xa0 ||
      !validate_outer_and_inner (frame, &control, &body, &body_length, NULL))
    {
      probe->unexpected_outer_type = outer_type;
      probe_fail (probe, "MALFORMED_A0_FRAME");
      return;
    }

  if (probe->typed_response_count != 0)
    {
      probe->unexpected_control = control;
      probe_fail (probe, "EXTRA_LOGICAL_FRAME");
      return;
    }

  if (probe->logical_ack_count == 0)
    {
      if (control != 0xb0 || body_length != 2 || body[0] != 0xa8 ||
          (body[1] != 0x01 && body[1] != 0x07))
        {
          probe->unexpected_control = control;
          probe_fail (probe, "UNEXPECTED_A8_ACK");
          return;
        }
      probe->logical_ack_count = 1;
      probe_request_terminal (probe);
      return;
    }

  if (control != 0xa8 || body_length != sizeof expected_firmware ||
      memcmp (body, expected_firmware, sizeof expected_firmware) != 0)
    {
      probe->unexpected_control = control;
      probe_fail (probe, "WRONG_OR_MALFORMED_A8_FIRMWARE_RESPONSE");
      return;
    }
  probe->typed_response_count = 1;
  probe->firmware_match = TRUE;
  probe_request_terminal (probe);
}

static void
b0_consumer (guint8 outer_type, GBytes *frame, gpointer user_data)
{
  D277Probe *probe = user_data;
  probe->unexpected_outer_type = outer_type;
  probe->last_observed_length = g_bytes_get_size (frame);
  probe_fail (probe, "UNEXPECTED_B0_TRAFFIC");
}

static void
backend_drained (GoodixFpiUsbBackend *backend, gpointer user_data)
{
  D277Probe *probe = user_data;
  (void) backend;
  probe->drained = TRUE;
  if (probe->loop != NULL)
    g_main_loop_quit (probe->loop);
}

static gboolean
terminal_idle_cb (gpointer user_data)
{
  D277Probe *probe = user_data;
  GError *error = NULL;
  probe->idle_source = 0;

  if (probe->failure_class != NULL || probe->typed_response_count == 1)
    {
      if (probe->failure_class == NULL &&
          !goodix_usb_router_finalize (probe->router, &error))
        {
          probe->failure_class = g_strdup ("TRAILING_OR_TRUNCATED_A0_STREAM");
          g_clear_error (&error);
        }
      probe->success = probe->failure_class == NULL &&
                       probe->logical_ack_count == 1 &&
                       probe->typed_response_count == 1 &&
                       probe->firmware_match;
      if (probe->timeout_source != 0)
        {
          g_source_remove (probe->timeout_source);
          probe->timeout_source = 0;
        }
      goodix_fpi_usb_backend_cancel (probe->backend);
      return G_SOURCE_REMOVE;
    }

  /* Parsing of the entire completion has now finished.  Only arm another IN
   * if the ACK was not followed by its typed response in the same completion.
   */
  if (probe->logical_ack_count == 1 &&
      goodix_fpi_usb_backend_get_outstanding (probe->backend) == 0)
    {
      if (!goodix_fpi_usb_backend_arm_receive (probe->backend,
                                                D277_GENERATION, &error))
        {
          g_clear_error (&error);
          probe_fail (probe, "SECOND_SEQUENTIAL_IN_ARM_FAILED");
        }
    }
  return G_SOURCE_REMOVE;
}

static void
probe_request_terminal (D277Probe *probe)
{
  if (probe->idle_source == 0)
    probe->idle_source = g_idle_add (terminal_idle_cb, probe);
}

static gboolean
timeout_cb (gpointer user_data)
{
  D277Probe *probe = user_data;
  probe->timeout_source = 0;
  if (probe->failure_class == NULL)
    probe->failure_class = g_strdup ("A8_TIMEOUT_1000MS");
  probe->success = FALSE;
  goodix_fpi_usb_backend_cancel (probe->backend);
  return G_SOURCE_REMOVE;
}

static gboolean
exact_a8_guard (guint out_count,
                guint target_vid,
                guint target_pid,
                const guint8 *bytes,
                gsize length,
                GError **error)
{
  if (out_count != 0)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                           "second OUT is structurally forbidden");
      return FALSE;
    }
  if (target_vid != D277_VID || target_pid != D277_PID ||
      length != sizeof a8_request || bytes == NULL ||
      memcmp (bytes, a8_request, sizeof a8_request) != 0)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                           "wire guard rejected non-exact A8 target/frame");
      return FALSE;
    }
  return TRUE;
}

static D277Probe *
probe_new (FpDevice *device, guint target_vid, guint target_pid)
{
  D277Probe *probe = g_new0 (D277Probe, 1);
  probe->target_vid = target_vid;
  probe->target_pid = target_pid;
  probe->cancellable = g_cancellable_new ();
  probe->router = goodix_usb_router_new (a0_consumer, b0_consumer, probe);
  probe->backend = goodix_fpi_usb_backend_new (device, probe->router,
                                               D277_EP_IN, D277_EP_OUT,
                                               D277_RECEIVE_SIZE);
  goodix_fpi_usb_backend_set_drained_callback (probe->backend,
                                               backend_drained, probe);
  return probe;
}

static void
probe_free (D277Probe *probe)
{
  if (probe == NULL)
    return;
  if (probe->idle_source != 0)
    g_source_remove (probe->idle_source);
  if (probe->timeout_source != 0)
    g_source_remove (probe->timeout_source);
  g_assert_true (goodix_fpi_usb_backend_can_free (probe->backend));
  goodix_fpi_usb_backend_free (probe->backend);
  goodix_usb_router_free (probe->router);
  g_clear_object (&probe->cancellable);
  g_clear_pointer (&probe->loop, g_main_loop_unref);
  g_clear_pointer (&probe->failure_class, g_free);
  g_free (probe);
}

static gboolean
probe_start (D277Probe *probe, gboolean live_timeout, GError **error)
{
  g_autoptr(GBytes) request = NULL;

  if (!exact_a8_guard (probe->out_command_count, probe->target_vid,
                       probe->target_pid, a8_request, sizeof a8_request,
                       error))
    return FALSE;
  goodix_usb_router_begin_generation (probe->router, D277_GENERATION);
  if (!goodix_fpi_usb_backend_begin_generation (probe->backend,
                                                 D277_GENERATION,
                                                 probe->cancellable, error))
    return FALSE;
  if (live_timeout)
    probe->timeout_source = g_timeout_add (D277_A8_TIMEOUT_MS,
                                           timeout_cb, probe);
  if (!goodix_fpi_usb_backend_arm_receive (probe->backend,
                                           D277_GENERATION, error))
    return FALSE;
  request = g_bytes_new_static (a8_request, sizeof a8_request);
  if (!goodix_fpi_usb_backend_submit_out (probe->backend,
                                          D277_GENERATION, request, error))
    {
      goodix_fpi_usb_backend_cancel (probe->backend);
      return FALSE;
    }
  probe->out_command_count = 1;
  return TRUE;
}

static void
synthetic_submit (GoodixFpiUsbBackend *backend,
                  GoodixUsbDirection direction,
                  guint64 generation,
                  GBytes *bytes,
                  gpointer user_data)
{
  SyntheticUsb *usb = user_data;
  (void) backend;
  g_assert_cmpuint (generation, ==, D277_GENERATION);
  if (direction == GOODIX_USB_TRANSFER_IN)
    {
      usb->in_submits++;
      usb->in_outstanding++;
      usb->max_in_outstanding = MAX (usb->max_in_outstanding,
                                     usb->in_outstanding);
    }
  else
    {
      usb->out_submits++;
      g_clear_pointer (&usb->last_out, g_bytes_unref);
      usb->last_out = g_bytes_ref (bytes);
    }
}

static GByteArray *
build_frame (guint8 outer_type, guint8 control,
             const guint8 *body, gsize body_length)
{
  GByteArray *frame = g_byte_array_new ();
  guint inner_length = (guint) body_length + 1;
  guint outer_length = inner_length + 3;
  guint checksum;
  guint8 byte;
  gsize i;

  byte = outer_type;
  g_byte_array_append (frame, &byte, 1);
  byte = (guint8) outer_length;
  g_byte_array_append (frame, &byte, 1);
  byte = (guint8) (outer_length >> 8);
  g_byte_array_append (frame, &byte, 1);
  byte = (guint8) (outer_type + (outer_length & 0xffu) +
                   ((outer_length >> 8) & 0xffu));
  g_byte_array_append (frame, &byte, 1);
  g_byte_array_append (frame, &control, 1);
  byte = (guint8) inner_length;
  g_byte_array_append (frame, &byte, 1);
  byte = (guint8) (inner_length >> 8);
  g_byte_array_append (frame, &byte, 1);
  if (body_length != 0)
    g_byte_array_append (frame, body, (guint) body_length);
  checksum = control + (inner_length & 0xffu) +
             ((inner_length >> 8) & 0xffu);
  for (i = 0; i < body_length; i++)
    checksum += body[i];
  byte = (guint8) (0xaau - (checksum & 0xffu));
  g_byte_array_append (frame, &byte, 1);
  return frame;
}

static void
drain_default_context (void)
{
  while (g_main_context_iteration (NULL, FALSE))
    ;
}

static void
synthetic_complete_out (D277Probe *probe)
{
  goodix_fpi_usb_backend_complete_out (probe->backend, D277_GENERATION, NULL);
}

static void
synthetic_complete_in (D277Probe *probe, SyntheticUsb *usb,
                       const guint8 *data, gsize length,
                       const GError *error)
{
  g_assert_cmpuint (usb->in_outstanding, ==, 1);
  usb->in_outstanding--;
  probe->in_completion_count++;
  goodix_fpi_usb_backend_complete_receive (probe->backend, D277_GENERATION,
                                            data, length, error);
  drain_default_context ();
}

static void
test_exact_guard_and_second_out (void)
{
  g_autoptr(GError) error = NULL;
  guint8 wrong[sizeof a8_request];
  memcpy (wrong, a8_request, sizeof wrong);
  wrong[4] = 0xe8;
  g_assert_true (exact_a8_guard (0, D277_VID, D277_PID,
                                 a8_request, sizeof a8_request, &error));
  g_assert_no_error (error);
  g_assert_false (exact_a8_guard (1, D277_VID, D277_PID,
                                  a8_request, sizeof a8_request, &error));
  g_clear_error (&error);
  g_assert_false (exact_a8_guard (0, D277_VID, D277_PID,
                                  wrong, sizeof wrong, &error));
}

static void
test_ack_and_response_one_receive (void)
{
  const guint8 ack_body[] = { 0xa8, 0x01 };
  g_autoptr(GByteArray) ack = build_frame (0xa0, 0xb0,
                                           ack_body, sizeof ack_body);
  g_autoptr(GByteArray) response = build_frame (0xa0, 0xa8,
                                                 expected_firmware,
                                                 sizeof expected_firmware);
  g_autoptr(GByteArray) both = g_byte_array_new ();
  g_autoptr(GError) error = NULL;
  SyntheticUsb usb = { 0 };
  D277Probe *probe = probe_new (NULL, D277_VID, D277_PID);
  goodix_fpi_usb_backend_set_async_submit_seam (probe->backend,
                                                 synthetic_submit, &usb);
  g_assert_true (probe_start (probe, FALSE, &error));
  synthetic_complete_out (probe);
  g_byte_array_append (both, ack->data, ack->len);
  g_byte_array_append (both, response->data, response->len);
  synthetic_complete_in (probe, &usb, both->data, both->len, NULL);
  g_assert_true (probe->success);
  g_assert_true (probe->drained);
  g_assert_cmpuint (usb.in_submits, ==, 1);
  g_assert_cmpuint (usb.out_submits, ==, 1);
  g_assert_cmpuint (usb.max_in_outstanding, ==, 1);
  g_assert_cmpuint (probe->logical_ack_count, ==, 1);
  g_assert_cmpuint (probe->typed_response_count, ==, 1);
  g_clear_pointer (&usb.last_out, g_bytes_unref);
  probe_free (probe);
}

static void
test_split_over_receives (void)
{
  const guint8 ack_body[] = { 0xa8, 0x07 };
  g_autoptr(GByteArray) ack = build_frame (0xa0, 0xb0,
                                           ack_body, sizeof ack_body);
  g_autoptr(GByteArray) response = build_frame (0xa0, 0xa8,
                                                 expected_firmware,
                                                 sizeof expected_firmware);
  g_autoptr(GByteArray) first = g_byte_array_new ();
  g_autoptr(GError) error = NULL;
  SyntheticUsb usb = { 0 };
  D277Probe *probe = probe_new (NULL, D277_VID, D277_PID);
  goodix_fpi_usb_backend_set_async_submit_seam (probe->backend,
                                                 synthetic_submit, &usb);
  g_assert_true (probe_start (probe, FALSE, &error));
  synthetic_complete_out (probe);
  g_byte_array_append (first, ack->data, ack->len);
  g_byte_array_append (first, response->data, 5);
  synthetic_complete_in (probe, &usb, first->data, first->len, NULL);
  g_assert_cmpuint (usb.in_submits, ==, 2);
  synthetic_complete_in (probe, &usb, response->data + 5,
                          response->len - 5, NULL);
  g_assert_true (probe->success);
  g_assert_cmpuint (usb.in_submits, ==, 2);
  g_assert_cmpuint (usb.max_in_outstanding, ==, 1);
  g_clear_pointer (&usb.last_out, g_bytes_unref);
  probe_free (probe);
}

static void
test_wrong_firmware_fails (void)
{
  const guint8 ack_body[] = { 0xa8, 0x01 };
  guint8 wrong_firmware[sizeof expected_firmware];
  g_autoptr(GByteArray) ack = build_frame (0xa0, 0xb0,
                                           ack_body, sizeof ack_body);
  g_autoptr(GByteArray) response = NULL;
  g_autoptr(GByteArray) both = g_byte_array_new ();
  g_autoptr(GError) error = NULL;
  SyntheticUsb usb = { 0 };
  D277Probe *probe;
  memcpy (wrong_firmware, expected_firmware, sizeof wrong_firmware);
  wrong_firmware[sizeof wrong_firmware - 2] = '8';
  response = build_frame (0xa0, 0xa8, wrong_firmware,
                          sizeof wrong_firmware);
  probe = probe_new (NULL, D277_VID, D277_PID);
  goodix_fpi_usb_backend_set_async_submit_seam (probe->backend,
                                                 synthetic_submit, &usb);
  g_assert_true (probe_start (probe, FALSE, &error));
  synthetic_complete_out (probe);
  g_byte_array_append (both, ack->data, ack->len);
  g_byte_array_append (both, response->data, response->len);
  synthetic_complete_in (probe, &usb, both->data, both->len, NULL);
  g_assert_false (probe->success);
  g_assert_cmpstr (probe->failure_class, ==,
                   "WRONG_OR_MALFORMED_A8_FIRMWARE_RESPONSE");
  g_clear_pointer (&usb.last_out, g_bytes_unref);
  probe_free (probe);
}

static void
test_b0_fails (void)
{
  const guint8 payload[] = { 0x16 };
  g_autoptr(GByteArray) frame = build_frame (0xb0, 0x00,
                                             payload, sizeof payload);
  g_autoptr(GError) error = NULL;
  SyntheticUsb usb = { 0 };
  D277Probe *probe = probe_new (NULL, D277_VID, D277_PID);
  goodix_fpi_usb_backend_set_async_submit_seam (probe->backend,
                                                 synthetic_submit, &usb);
  g_assert_true (probe_start (probe, FALSE, &error));
  synthetic_complete_out (probe);
  synthetic_complete_in (probe, &usb, frame->data, frame->len, NULL);
  g_assert_false (probe->success);
  g_assert_cmpstr (probe->failure_class, ==, "UNEXPECTED_B0_TRAFFIC");
  g_clear_pointer (&usb.last_out, g_bytes_unref);
  probe_free (probe);
}

static void
test_one_in_and_timeout_drain (void)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GError) cancelled = NULL;
  SyntheticUsb usb = { 0 };
  D277Probe *probe = probe_new (NULL, D277_VID, D277_PID);
  goodix_fpi_usb_backend_set_async_submit_seam (probe->backend,
                                                 synthetic_submit, &usb);
  g_assert_true (probe_start (probe, FALSE, &error));
  g_assert_false (goodix_fpi_usb_backend_arm_receive (probe->backend,
                                                       D277_GENERATION,
                                                       &error));
  g_clear_error (&error);
  timeout_cb (probe);
  cancelled = g_error_new_literal (G_IO_ERROR, G_IO_ERROR_CANCELLED,
                                   "synthetic cancellation");
  synthetic_complete_in (probe, &usb, NULL, 0, cancelled);
  goodix_fpi_usb_backend_complete_out (probe->backend, D277_GENERATION,
                                       cancelled);
  g_assert_true (probe->drained);
  g_assert_cmpuint (usb.in_submits, ==, 1);
  g_assert_cmpuint (usb.out_submits, ==, 1);
  g_assert_cmpuint (probe->out_command_count, ==, 1);
  g_assert_cmpuint (probe->retry_count, ==, 0);
  g_assert_cmpuint (probe->reopen_count, ==, 0);
  g_assert_cmpuint (probe->reset_count, ==, 0);
  g_clear_pointer (&usb.last_out, g_bytes_unref);
  probe_free (probe);
}

static int
run_self_tests (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d277/a8/exact-guard-second-out", test_exact_guard_and_second_out);
  g_test_add_func ("/d277/a8/ack-response-one-receive", test_ack_and_response_one_receive);
  g_test_add_func ("/d277/a8/split-over-receives", test_split_over_receives);
  g_test_add_func ("/d277/a8/wrong-firmware", test_wrong_firmware_fails);
  g_test_add_func ("/d277/a8/b0-fail-closed", test_b0_fails);
  g_test_add_func ("/d277/a8/one-in-timeout-drain", test_one_in_and_timeout_drain);
  return g_test_run ();
}

#ifdef D277_LIVE_BINDING
typedef struct _D277HarnessDevice D277HarnessDevice;
typedef struct _D277HarnessDeviceClass D277HarnessDeviceClass;
struct _D277HarnessDevice { FpDevice parent_instance; };
struct _D277HarnessDeviceClass { FpDeviceClass parent_class; };
GType d277_harness_device_get_type (void);

G_DEFINE_TYPE (D277HarnessDevice, d277_harness_device, FP_TYPE_DEVICE)

static const FpIdEntry d277_id_table[] = {
  { .vid = D277_VID, .pid = D277_PID },
  { .vid = 0, .pid = 0 }
};

static void
d277_harness_device_class_init (D277HarnessDeviceClass *klass)
{
  FpDeviceClass *device_class = FP_DEVICE_CLASS (klass);
  device_class->id = "d277_native_a8_harness_only";
  device_class->full_name = "D277 native A8 harness-only binding";
  device_class->type = FP_DEVICE_TYPE_USB;
  device_class->id_table = d277_id_table;
  device_class->features = FP_DEVICE_FEATURE_CAPTURE;
  device_class->scan_type = FP_SCAN_TYPE_PRESS;
  device_class->temp_hot_seconds = -1;
}

static void d277_harness_device_init (D277HarnessDevice *self) { (void) self; }

static void
print_live_json (D277Probe *probe, guint bus, guint address, guint port,
                 guint open_attempt_count, guint open_count,
                 guint claim_count, guint release_count,
                 guint close_count, gboolean authorization_consumed)
{
  const gchar *failure = probe->failure_class != NULL ?
                         probe->failure_class : "none";
  guint64 real_submits = goodix_fpi_usb_backend_get_real_submit_count (probe->backend);
  guint64 out_submits = goodix_fpi_usb_backend_get_out_submit_count (probe->backend);
  guint64 in_submits = real_submits >= out_submits ? real_submits - out_submits : 0;
  guint64 in_callbacks = in_submits - goodix_fpi_usb_backend_get_outstanding (probe->backend);

  g_print ("{\"result\":\"%s\",\"failure_class\":\"%s\","
           "\"live_authorization_consumed\":%s,\"live_authorized\":false,"
           "\"target_vid\":\"27c6\",\"target_pid\":\"5125\","
           "\"target_bus\":%u,\"target_address\":%u,\"target_port\":%u,"
           "\"a8_tx_hex\":\"a00600a6a803000000ff\","
           "\"usb_open_attempt_count\":%u,\"usb_open_count\":%u,"
           "\"usb_claim_count\":%u,\"a8_command_submit_count\":%u,"
           "\"bulk_in_submit_count\":%" G_GUINT64_FORMAT ","
           "\"bulk_in_completion_or_cancel_callback_count\":%" G_GUINT64_FORMAT ","
           "\"a8_logical_ack_count\":%u,\"a8_typed_response_count\":%u,"
           "\"a8_firmware_match\":%s,\"a8_firmware\":\"%s\","
           "\"max_outstanding_bulk_in\":%u,\"second_reader_api_path\":\"ABSENT\","
           "\"retry_count\":%u,\"transport_reopen_count\":%u,"
           "\"device_reset_count\":%u,\"device_side_cancel_command_count\":%u,"
           "\"secret_materialization_count\":%u,\"tls_handshake_count\":%u,"
           "\"finger_wait_count\":%u,\"image_count\":%u,"
           "\"persistent_device_write_count\":%u,\"host_cache_write_count\":0,"
           "\"usb_release_count\":%u,\"usb_close_count\":%u,"
           "\"terminal_cleanup_completed\":%s}\n",
           probe->success ? "pass" : "fail", failure,
           authorization_consumed ? "true" : "false",
           bus, address, port, open_attempt_count, open_count, claim_count,
           probe->out_command_count, in_submits, in_callbacks,
           probe->logical_ack_count, probe->typed_response_count,
           probe->firmware_match ? "true" : "false",
           probe->firmware_match ? "GF_ST411SEC_APP_12509" : "",
           goodix_fpi_usb_backend_get_max_outstanding (probe->backend),
           probe->retry_count, probe->reopen_count, probe->reset_count,
           probe->device_cancel_command_count, probe->secret_count,
           probe->tls_count, probe->finger_wait_count, probe->image_count,
           probe->persistent_write_count, release_count, close_count,
           probe->drained ? "true" : "false");
}

static int
run_preflight_enumeration (void)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GUsbContext) usb_context = g_usb_context_new (&error);
  g_autoptr(GPtrArray) devices = NULL;
  guint matches = 0;
  guint i;

  if (usb_context == NULL || !g_usb_context_enumerate (usb_context, &error))
    {
      g_printerr ("BLOCKED_ENVIRONMENT: USB enumeration failed: %s\n",
                  error != NULL ? error->message : "unknown");
      return 2;
    }
  devices = g_usb_context_get_devices (usb_context);
  for (i = 0; i < devices->len; i++)
    {
      GUsbDevice *candidate = g_ptr_array_index (devices, i);
      if (g_usb_device_get_vid (candidate) == D277_VID &&
          g_usb_device_get_pid (candidate) == D277_PID)
        {
          matches++;
          g_print ("TARGET_BUS=%u TARGET_ADDRESS=%u TARGET_PORT=%u\n",
                   g_usb_device_get_bus (candidate),
                   g_usb_device_get_address (candidate),
                   g_usb_device_get_port_number (candidate));
        }
    }
  g_print ("TARGET_MATCH_COUNT=%u\n", matches);
  return matches == 1 ? 0 : 2;
}

static int
run_live_once (void)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GUsbContext) usb_context = NULL;
  g_autoptr(GPtrArray) devices = NULL;
  GUsbDevice *target = NULL;
  g_autoptr(FpDevice) fp_device = NULL;
  D277Probe *probe = NULL;
  guint matches = 0;
  guint bus = 0, address = 0, port = 0;
  guint open_attempt_count = 0, open_count = 0, claim_count = 0;
  guint release_count = 0, close_count = 0;
  gboolean authorization_consumed = FALSE;
  gboolean claimed = FALSE, opened = FALSE;
  guint i;
  int rc = 1;

  usb_context = g_usb_context_new (&error);
  if (usb_context == NULL || !g_usb_context_enumerate (usb_context, &error))
    {
      g_printerr ("BLOCKED_ENVIRONMENT: USB enumeration failed: %s\n",
                  error != NULL ? error->message : "unknown");
      return 2;
    }
  devices = g_usb_context_get_devices (usb_context);
  for (i = 0; i < devices->len; i++)
    {
      GUsbDevice *candidate = g_ptr_array_index (devices, i);
      if (g_usb_device_get_vid (candidate) == D277_VID &&
          g_usb_device_get_pid (candidate) == D277_PID)
        {
          target = candidate;
          matches++;
        }
    }
  if (matches != 1)
    {
      g_printerr ("BLOCKED_TARGET_CARDINALITY: matching devices=%u\n", matches);
      return 2;
    }
  bus = g_usb_device_get_bus (target);
  address = g_usb_device_get_address (target);
  port = g_usb_device_get_port_number (target);
  fp_device = g_object_new (d277_harness_device_get_type (),
                            "fpi-usb-device", target,
                            "fpi-driver-data", (guint64) 0, NULL);
  probe = probe_new (fp_device, D277_VID, D277_PID);

  /* The one authorization is conservatively consumed by the first open
   * attempt, including a permission/claim failure after target selection.
   */
  authorization_consumed = TRUE;
  open_attempt_count = 1;
  if (!g_usb_device_open (target, &error))
    {
      probe->failure_class = g_strdup ("USB_OPEN_FAILED");
      probe->drained = TRUE;
      goto cleanup;
    }
  opened = TRUE;
  open_count = 1;
  if (!g_usb_device_claim_interface (target, D277_INTERFACE,
                                     G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                     &error))
    {
      probe->failure_class = g_strdup ("USB_CLAIM_FAILED");
      probe->drained = TRUE;
      goto cleanup;
    }
  claimed = TRUE;
  claim_count = 1;
  probe->loop = g_main_loop_new (NULL, FALSE);
  if (!probe_start (probe, TRUE, &error))
    {
      probe->failure_class = g_strdup ("A8_START_FAILED");
      if (!goodix_fpi_usb_backend_is_drained (probe->backend))
        goodix_fpi_usb_backend_cancel (probe->backend);
    }
  else
    g_main_loop_run (probe->loop);

cleanup:
  if (claimed)
    {
      g_autoptr(GError) release_error = NULL;
      if (g_usb_device_release_interface (target, D277_INTERFACE,
                                          G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                          &release_error))
        release_count = 1;
      else if (probe->failure_class == NULL)
        probe->failure_class = g_strdup ("USB_RELEASE_FAILED");
    }
  if (opened)
    {
      g_autoptr(GError) close_error = NULL;
      if (g_usb_device_close (target, &close_error))
        close_count = 1;
      else if (probe->failure_class == NULL)
        probe->failure_class = g_strdup ("USB_CLOSE_FAILED");
    }
  probe->success = probe->success && release_count == 1 && close_count == 1;
  print_live_json (probe, bus, address, port, open_attempt_count, open_count,
                   claim_count, release_count, close_count,
                   authorization_consumed);
  rc = probe->success ? 0 : 1;
  probe_free (probe);
  return rc;
}
#endif

int
main (int argc, char **argv)
{
  if (argc == 2 && g_str_equal (argv[1], "--self-test"))
    return run_self_tests (argc, argv);
#ifdef D277_LIVE_BINDING
  if (argc == 2 && g_str_equal (argv[1], "--preflight-enumerate-only"))
    return run_preflight_enumeration ();
  if (argc == 2 && g_str_equal (argv[1], "--live-exact-a8"))
    return run_live_once ();
#endif
  g_printerr ("usage: %s --self-test%s\n", argv[0],
#ifdef D277_LIVE_BINDING
              " | --preflight-enumerate-only | --live-exact-a8"
#else
              ""
#endif
             );
  return 2;
}
