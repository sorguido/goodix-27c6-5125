/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <string.h>

#include "goodix_a0_protocol.h"
#include "goodix_d278_a2_sensor_only_probe.h"

typedef struct
{
  GoodixD278A2SensorOnlyProbe *probe;
  GoodixD278A2Direction direction;
  guint64 generation;
  guint timeout_ms;
  guint submit_count;
  GBytes *out_frame;
  guint8 typed_body[3];
  guint8 expected_hash[32];
} Fixture;

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
synthetic_submit (GoodixD278A2SensorOnlyProbe *probe,
                  GoodixD278A2Direction        direction,
                  guint64                      generation,
                  GBytes                      *bytes,
                  guint                        timeout_ms,
                  gpointer                     user_data,
                  GError                     **error)
{
  Fixture *fixture = user_data;

  (void) error;
  fixture->probe = probe;
  fixture->direction = direction;
  fixture->generation = generation;
  fixture->timeout_ms = timeout_ms;
  fixture->submit_count++;
  if (direction == GOODIX_D278_A2_TRANSFER_OUT)
    fixture->out_frame = g_bytes_ref (bytes);
  else
    g_assert_null (bytes);
  return TRUE;
}

static Fixture *
fixture_start (void)
{
  static const guint8 expected_out[] = {
    0xa0, 0x06, 0x00, 0xa6, 0xa2, 0x03, 0x00, 0x01, 0x14, 0xf0,
  };
  g_autoptr(GError) error = NULL;
  Fixture *fixture = g_new0 (Fixture, 1);
  gsize length;
  const guint8 *data;

  fixture->typed_body[0] = 1;
  fixture->typed_body[1] = 2;
  fixture->typed_body[2] = 3;
  digest (fixture->typed_body, sizeof fixture->typed_body,
          fixture->expected_hash);
  fixture->probe = goodix_d278_a2_sensor_only_probe_new (
    fixture->expected_hash, synthetic_submit, fixture);
  g_assert_true (goodix_d278_a2_sensor_only_probe_start (fixture->probe, 9,
                                                          &error));
  g_assert_no_error (error);
  g_assert_cmpuint (fixture->submit_count, ==, 1);
  g_assert_cmpint (fixture->direction, ==, GOODIX_D278_A2_TRANSFER_OUT);
  g_assert_cmpuint (fixture->timeout_ms, ==, GOODIX_D278_09_OUT_TIMEOUT_MS);
  data = g_bytes_get_data (fixture->out_frame, &length);
  g_assert_cmpuint (length, ==, sizeof expected_out);
  g_assert_true (memcmp (data, expected_out, sizeof expected_out) == 0);
  return fixture;
}

static void
fixture_free (Fixture *fixture)
{
  if (fixture == NULL)
    return;
  g_clear_pointer (&fixture->out_frame, g_bytes_unref);
  goodix_d278_a2_sensor_only_probe_free (fixture->probe);
  g_free (fixture);
}

static void
complete_out (Fixture *fixture)
{
  gsize length = g_bytes_get_size (fixture->out_frame);

  goodix_d278_a2_sensor_only_probe_complete (
    fixture->probe, GOODIX_D278_A2_TRANSFER_OUT, fixture->generation,
    NULL, length, NULL);
  g_assert_cmpint (fixture->direction, ==, GOODIX_D278_A2_TRANSFER_IN);
  g_assert_cmpuint (fixture->timeout_ms, ==, GOODIX_D278_09_ACK_TIMEOUT_MS);
}

static GBytes *
make_a0 (guint8        control,
         const guint8 *body,
         gsize         body_length)
{
  g_autoptr(GError) error = NULL;
  GBytes *frame = goodix_a0_build_frame (control, control, body, body_length,
                                         &error);

  g_assert_no_error (error);
  g_assert_nonnull (frame);
  return frame;
}

static void
complete_frame (Fixture *fixture,
                GBytes  *frame)
{
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);

  goodix_d278_a2_sensor_only_probe_complete (
    fixture->probe, GOODIX_D278_A2_TRANSFER_IN, fixture->generation,
    data, length, NULL);
}

static void
complete_valid_ack (Fixture *fixture)
{
  static const guint8 ack_body[] = { 0xa2, 0x01 };
  g_autoptr(GBytes) ack = make_a0 (0xb0, ack_body, sizeof ack_body);

  complete_frame (fixture, ack);
  g_assert_cmpuint (fixture->timeout_ms, ==,
                    GOODIX_D278_09_TYPED_TIMEOUT_MS);
}

static void
complete_timeout (Fixture *fixture)
{
  g_autoptr(GError) timeout = NULL;

  g_set_error_literal (&timeout, G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
                       "synthetic bounded timeout");
  goodix_d278_a2_sensor_only_probe_complete (
    fixture->probe, GOODIX_D278_A2_TRANSFER_IN, fixture->generation,
    NULL, 0, timeout);
}

static void
assert_one_command_terminal (Fixture *fixture)
{
  const GoodixD278A2ProbeAudit *a =
    goodix_d278_a2_sensor_only_probe_get_audit (fixture->probe);

  g_assert_true (goodix_d278_a2_sensor_only_probe_is_terminal (
    fixture->probe));
  g_assert_cmpuint (a->goodix_command_count, ==, 1);
  g_assert_cmpuint (a->out_submit_count, ==, 1);
  g_assert_cmpuint (a->a2_sensor_only_submit_count, ==, 1);
  g_assert_cmpuint (a->physical_in_submit_count, <=, 2);
  g_assert_cmpuint (a->physical_in_completion_count, <=, 2);
  g_assert_cmpuint (a->retry_count, ==, 0);
  g_assert_cmpuint (a->reopen_count, ==, 0);
  g_assert_cmpuint (a->device_reset_count, ==, 0);
  g_assert_cmpuint (a->clear_halt_count, ==, 0);
  g_assert_cmpuint (a->persistent_device_write_count, ==, 0);
  g_assert_cmpuint (a->tls_handshake_count, ==, 0);
  g_assert_true (a->backend_drained);
  g_assert_true (a->cleanup_completed);
}

static void
test_exact_happy_path (void)
{
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) typed = NULL;
  const GoodixD278A2ProbeAudit *a;

  complete_out (fixture);
  complete_valid_ack (fixture);
  typed = make_a0 (0xa2, fixture->typed_body, sizeof fixture->typed_body);
  complete_frame (fixture, typed);
  a = goodix_d278_a2_sensor_only_probe_get_audit (fixture->probe);
  g_assert_true (goodix_d278_a2_sensor_only_probe_succeeded (fixture->probe));
  g_assert_cmpuint (a->physical_in_submit_count, ==, 2);
  g_assert_cmpuint (a->physical_in_completion_count, ==, 2);
  g_assert_cmpuint (a->ack_count, ==, 1);
  g_assert_cmpuint (a->typed_response_count, ==, 1);
  g_assert_cmpint (a->ack_echo, ==, 0xa2);
  g_assert_cmpint (a->ack_status, ==, 0x01);
  g_assert_cmpint (a->typed_control, ==, 0xa2);
  g_assert_cmpint (a->typed_body_length, ==, 3);
  g_assert_cmpstr (a->typed_result_class, ==, "STRICT_MATCH");
  assert_one_command_terminal (fixture);
  fixture_free (fixture);
}

static void
test_ack_timeout (void)
{
  Fixture *fixture = fixture_start ();
  const GoodixD278A2ProbeAudit *a;

  complete_out (fixture);
  complete_timeout (fixture);
  a = goodix_d278_a2_sensor_only_probe_get_audit (fixture->probe);
  g_assert_cmpuint (a->timeout_count, ==, 1);
  g_assert_cmpuint (a->physical_in_submit_count, ==, 1);
  g_assert_cmpstr (a->current_context_result, ==,
                   "A2_CURRENT_CONTEXT_AMBIGUOUS_OR_REJECTED");
  assert_one_command_terminal (fixture);
  fixture_free (fixture);
}

static void
test_ack_mismatch (void)
{
  static const guint8 bad_ack_body[] = { 0xa2, 0x02 };
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) bad_ack = NULL;
  const GoodixD278A2ProbeAudit *a;

  complete_out (fixture);
  bad_ack = make_a0 (0xb0, bad_ack_body, sizeof bad_ack_body);
  complete_frame (fixture, bad_ack);
  a = goodix_d278_a2_sensor_only_probe_get_audit (fixture->probe);
  g_assert_cmpstr (a->completion_class, ==, "ACK_MISMATCH");
  g_assert_cmpuint (a->physical_in_submit_count, ==, 1);
  assert_one_command_terminal (fixture);
  fixture_free (fixture);
}

static void
test_typed_timeout_after_ack (void)
{
  Fixture *fixture = fixture_start ();
  const GoodixD278A2ProbeAudit *a;

  complete_out (fixture);
  complete_valid_ack (fixture);
  complete_timeout (fixture);
  a = goodix_d278_a2_sensor_only_probe_get_audit (fixture->probe);
  g_assert_cmpuint (a->ack_count, ==, 1);
  g_assert_cmpuint (a->typed_response_count, ==, 0);
  g_assert_cmpuint (a->timeout_count, ==, 1);
  assert_one_command_terminal (fixture);
  fixture_free (fixture);
}

static void
test_typed_shape_or_value_mismatch (void)
{
  static const guint8 wrong_typed[] = { 9, 9, 9 };
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) typed = NULL;
  const GoodixD278A2ProbeAudit *a;

  complete_out (fixture);
  complete_valid_ack (fixture);
  typed = make_a0 (0xa2, wrong_typed, sizeof wrong_typed);
  complete_frame (fixture, typed);
  a = goodix_d278_a2_sensor_only_probe_get_audit (fixture->probe);
  g_assert_cmpstr (a->completion_class, ==, "TYPED_MISMATCH");
  g_assert_cmpstr (a->typed_result_class, ==, "MISMATCH");
  g_assert_cmpuint (a->typed_response_count, ==, 0);
  assert_one_command_terminal (fixture);
  fixture_free (fixture);
}

static void
test_unexpected_e4_frame (void)
{
  guint8 e4_body[41] = { 0 };
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) e4 = make_a0 (0xe4, e4_body, sizeof e4_body);
  const GoodixD278A2ProbeAudit *a;

  complete_out (fixture);
  complete_frame (fixture, e4);
  a = goodix_d278_a2_sensor_only_probe_get_audit (fixture->probe);
  g_assert_cmpuint (a->unexpected_frame_count, ==, 1);
  g_assert_cmpuint (a->physical_in_submit_count, ==, 1);
  assert_one_command_terminal (fixture);
  fixture_free (fixture);
}

static void
test_unexpected_a8_frame (void)
{
  static const guint8 a8_body[] = "GF_ST411SEC_APP_12509";
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) a8 = make_a0 (0xa8, a8_body, sizeof a8_body);
  const GoodixD278A2ProbeAudit *a;

  complete_out (fixture);
  complete_frame (fixture, a8);
  a = goodix_d278_a2_sensor_only_probe_get_audit (fixture->probe);
  g_assert_cmpuint (a->unexpected_frame_count, ==, 1);
  g_assert_cmpuint (a->physical_in_submit_count, ==, 1);
  assert_one_command_terminal (fixture);
  fixture_free (fixture);
}

static void
test_stale_callback_cannot_continue (void)
{
  Fixture *fixture = fixture_start ();
  const GoodixD278A2ProbeAudit *a;
  guint submits;

  complete_out (fixture);
  complete_timeout (fixture);
  submits = fixture->submit_count;
  goodix_d278_a2_sensor_only_probe_complete (
    fixture->probe, GOODIX_D278_A2_TRANSFER_IN, fixture->generation + 1u,
    NULL, 0, NULL);
  a = goodix_d278_a2_sensor_only_probe_get_audit (fixture->probe);
  g_assert_cmpuint (a->stale_callback_count, ==, 1);
  g_assert_cmpuint (fixture->submit_count, ==, submits);
  assert_one_command_terminal (fixture);
  fixture_free (fixture);
}

static void
test_second_command_attempt_fails_closed (void)
{
  Fixture *fixture = fixture_start ();
  g_autoptr(GError) error = NULL;
  const GoodixD278A2ProbeAudit *a;

  /* Attempt the second start while the one permitted OUT is still active.
   * It must not create a second submit; the original attempt is then closed
   * through its ordinary bounded receive/timeout path. */
  g_assert_false (goodix_d278_a2_sensor_only_probe_start (fixture->probe, 10,
                                                           &error));
  g_assert_nonnull (error);
  a = goodix_d278_a2_sensor_only_probe_get_audit (fixture->probe);
  g_assert_cmpuint (a->prohibited_second_command_count, ==, 1);
  g_assert_cmpuint (a->goodix_command_count, ==, 1);
  g_assert_cmpuint (a->out_submit_count, ==, 1);
  g_assert_cmpuint (fixture->submit_count, ==, 1);
  complete_out (fixture);
  complete_timeout (fixture);
  assert_one_command_terminal (fixture);
  fixture_free (fixture);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d278-09/exact-happy-path", test_exact_happy_path);
  g_test_add_func ("/d278-09/ack-timeout", test_ack_timeout);
  g_test_add_func ("/d278-09/ack-mismatch", test_ack_mismatch);
  g_test_add_func ("/d278-09/typed-timeout", test_typed_timeout_after_ack);
  g_test_add_func ("/d278-09/typed-mismatch", test_typed_shape_or_value_mismatch);
  g_test_add_func ("/d278-09/unexpected-e4", test_unexpected_e4_frame);
  g_test_add_func ("/d278-09/unexpected-a8", test_unexpected_a8_frame);
  g_test_add_func ("/d278-09/stale-callback", test_stale_callback_cannot_continue);
  g_test_add_func ("/d278-09/second-command", test_second_command_attempt_fails_closed);
  return g_test_run ();
}
