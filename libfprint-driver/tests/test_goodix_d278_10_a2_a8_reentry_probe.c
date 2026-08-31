/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <string.h>

#include "goodix_a0_protocol.h"
#include "goodix_d278_a2_a8_reentry_probe.h"

typedef struct
{
  GoodixD278A2A8ReentryProbe *probe;
  GoodixD278A2A8Direction direction;
  guint64 generation;
  guint timeout_ms;
  guint submit_count;
  guint out_count;
  GBytes *out_frame;
  guint8 a2_typed_body[3];
  guint8 expected_a2_hash[32];
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
synthetic_submit (GoodixD278A2A8ReentryProbe *probe,
                  GoodixD278A2A8Direction     direction,
                  guint64                     generation,
                  GBytes                     *bytes,
                  guint                       timeout_ms,
                  gpointer                    user_data,
                  GError                    **error)
{
  Fixture *fixture = user_data;

  (void) error;
  fixture->probe = probe;
  fixture->direction = direction;
  fixture->generation = generation;
  fixture->timeout_ms = timeout_ms;
  fixture->submit_count++;
  if (direction == GOODIX_D278_10_TRANSFER_OUT)
    {
      fixture->out_count++;
      g_clear_pointer (&fixture->out_frame, g_bytes_unref);
      fixture->out_frame = g_bytes_ref (bytes);
    }
  else
    g_assert_null (bytes);
  return TRUE;
}

static Fixture *
fixture_start (void)
{
  static const guint8 expected_a2[] = {
    0xa0, 0x06, 0x00, 0xa6, 0xa2, 0x03, 0x00, 0x01, 0x14, 0xf0,
  };
  g_autoptr(GError) error = NULL;
  Fixture *fixture = g_new0 (Fixture, 1);
  gsize length;
  const guint8 *data;

  fixture->a2_typed_body[0] = 1;
  fixture->a2_typed_body[1] = 2;
  fixture->a2_typed_body[2] = 3;
  digest (fixture->a2_typed_body, sizeof fixture->a2_typed_body,
          fixture->expected_a2_hash);
  fixture->probe = goodix_d278_a2_a8_reentry_probe_new (
    fixture->expected_a2_hash, synthetic_submit, fixture);
  g_assert_true (goodix_d278_a2_a8_reentry_probe_start (fixture->probe, 10,
                                                         &error));
  g_assert_no_error (error);
  g_assert_cmpint (fixture->direction, ==, GOODIX_D278_10_TRANSFER_OUT);
  data = g_bytes_get_data (fixture->out_frame, &length);
  g_assert_cmpuint (length, ==, sizeof expected_a2);
  g_assert_true (memcmp (data, expected_a2, sizeof expected_a2) == 0);
  return fixture;
}

static void
fixture_free (Fixture *fixture)
{
  if (fixture == NULL)
    return;
  g_clear_pointer (&fixture->out_frame, g_bytes_unref);
  goodix_d278_a2_a8_reentry_probe_free (fixture->probe);
  g_free (fixture);
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
  return frame;
}

static void
complete_out (Fixture *fixture)
{
  gsize length = g_bytes_get_size (fixture->out_frame);

  g_assert_cmpint (fixture->direction, ==, GOODIX_D278_10_TRANSFER_OUT);
  goodix_d278_a2_a8_reentry_probe_complete (
    fixture->probe, GOODIX_D278_10_TRANSFER_OUT, fixture->generation,
    NULL, length, NULL);
}

static void
complete_frame (Fixture *fixture,
                GBytes  *frame)
{
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);

  g_assert_cmpint (fixture->direction, ==, GOODIX_D278_10_TRANSFER_IN);
  goodix_d278_a2_a8_reentry_probe_complete (
    fixture->probe, GOODIX_D278_10_TRANSFER_IN, fixture->generation,
    data, length, NULL);
}

static void
complete_timeout (Fixture *fixture)
{
  g_autoptr(GError) timeout = NULL;

  g_set_error_literal (&timeout, G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
                       "synthetic bounded timeout");
  goodix_d278_a2_a8_reentry_probe_complete (
    fixture->probe, GOODIX_D278_10_TRANSFER_IN, fixture->generation,
    NULL, 0, timeout);
}

static void
complete_ack (Fixture *fixture,
              guint8   echo,
              guint8   status)
{
  const guint8 body[] = { echo, status };
  g_autoptr(GBytes) frame = make_a0 (0xb0, body, sizeof body);

  complete_frame (fixture, frame);
}

static void
complete_a2_success (Fixture *fixture)
{
  g_autoptr(GBytes) typed = NULL;

  complete_out (fixture);
  complete_ack (fixture, 0xa2, 0x07);
  typed = make_a0 (0xa2, fixture->a2_typed_body,
                   sizeof fixture->a2_typed_body);
  complete_frame (fixture, typed);
  g_assert_cmpuint (fixture->out_count, ==, 2);
  g_assert_cmpint (fixture->direction, ==, GOODIX_D278_10_TRANSFER_OUT);
}

static void
assert_terminal_budget (Fixture *fixture,
                        guint    expected_a8)
{
  const GoodixD278A2A8Audit *a =
    goodix_d278_a2_a8_reentry_probe_get_audit (fixture->probe);

  g_assert_true (goodix_d278_a2_a8_reentry_probe_is_terminal (fixture->probe));
  g_assert_cmpuint (a->goodix_command_count, <=, 2);
  g_assert_cmpuint (a->out_submit_count, <=, 2);
  g_assert_cmpuint (a->a2_sensor_only_submit_count, ==, 1);
  g_assert_cmpuint (a->a8_submit_count, ==, expected_a8);
  g_assert_cmpuint (a->physical_in_submit_count, <=, 4);
  g_assert_cmpuint (a->physical_in_completion_count, <=, 4);
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
test_happy_path (void)
{
  static const guint8 app[] = "GF_ST411SEC_APP_12509";
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) typed = NULL;
  const GoodixD278A2A8Audit *a;
  static const guint8 expected_a8[] = {
    0xa0, 0x06, 0x00, 0xa6, 0xa8, 0x03, 0x00, 0x00, 0x00, 0xff,
  };
  gsize length;
  const guint8 *data;

  complete_a2_success (fixture);
  data = g_bytes_get_data (fixture->out_frame, &length);
  g_assert_cmpuint (length, ==, sizeof expected_a8);
  g_assert_true (memcmp (data, expected_a8, sizeof expected_a8) == 0);
  complete_out (fixture);
  complete_ack (fixture, 0xa8, 0x01);
  typed = make_a0 (0xa8, app, sizeof app);
  complete_frame (fixture, typed);
  a = goodix_d278_a2_a8_reentry_probe_get_audit (fixture->probe);
  g_assert_true (goodix_d278_a2_a8_reentry_probe_succeeded (fixture->probe));
  g_assert_cmpuint (a->goodix_command_count, ==, 2);
  g_assert_cmpuint (a->a2_ack_count, ==, 1);
  g_assert_cmpuint (a->a2_typed_response_count, ==, 1);
  g_assert_cmpuint (a->a8_ack_count, ==, 1);
  g_assert_cmpuint (a->a8_typed_response_count, ==, 1);
  g_assert_cmpint (a->a2_ack_status, ==, 0x07);
  g_assert_true (a->a8_app12509_pin_match);
  assert_terminal_budget (fixture, 1);
  fixture_free (fixture);
}

static void
test_a2_ack_timeout (void)
{
  Fixture *fixture = fixture_start ();
  complete_out (fixture);
  complete_timeout (fixture);
  assert_terminal_budget (fixture, 0);
  fixture_free (fixture);
}

static void
test_a2_ack_mismatch (void)
{
  Fixture *fixture = fixture_start ();
  complete_out (fixture);
  complete_ack (fixture, 0xa2, 0x02);
  assert_terminal_budget (fixture, 0);
  fixture_free (fixture);
}

static void
test_a2_typed_timeout (void)
{
  Fixture *fixture = fixture_start ();
  complete_out (fixture);
  complete_ack (fixture, 0xa2, 0x01);
  complete_timeout (fixture);
  assert_terminal_budget (fixture, 0);
  fixture_free (fixture);
}

static void
test_a2_typed_mismatch (void)
{
  static const guint8 wrong[] = { 9, 9, 9 };
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) typed = NULL;

  complete_out (fixture);
  complete_ack (fixture, 0xa2, 0x01);
  typed = make_a0 (0xa2, wrong, sizeof wrong);
  complete_frame (fixture, typed);
  assert_terminal_budget (fixture, 0);
  fixture_free (fixture);
}

static void
test_unexpected_e4_during_a2 (void)
{
  guint8 body[41] = { 0 };
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) frame = make_a0 (0xe4, body, sizeof body);

  complete_out (fixture);
  complete_frame (fixture, frame);
  assert_terminal_budget (fixture, 0);
  fixture_free (fixture);
}

static void
test_a8_ack_timeout (void)
{
  Fixture *fixture = fixture_start ();
  complete_a2_success (fixture);
  complete_out (fixture);
  complete_timeout (fixture);
  assert_terminal_budget (fixture, 1);
  fixture_free (fixture);
}

static void
test_a8_ack_mismatch (void)
{
  Fixture *fixture = fixture_start ();
  complete_a2_success (fixture);
  complete_out (fixture);
  complete_ack (fixture, 0xa8, 0x02);
  assert_terminal_budget (fixture, 1);
  fixture_free (fixture);
}

static void
test_a8_typed_timeout (void)
{
  Fixture *fixture = fixture_start ();
  complete_a2_success (fixture);
  complete_out (fixture);
  complete_ack (fixture, 0xa8, 0x07);
  complete_timeout (fixture);
  assert_terminal_budget (fixture, 1);
  fixture_free (fixture);
}

static void
test_a8_wrong_app_pin (void)
{
  static const guint8 wrong[] = "GF_ST411SEC_APP_12510";
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) typed = NULL;

  complete_a2_success (fixture);
  complete_out (fixture);
  complete_ack (fixture, 0xa8, 0x01);
  typed = make_a0 (0xa8, wrong, sizeof wrong);
  complete_frame (fixture, typed);
  g_assert_false (goodix_d278_a2_a8_reentry_probe_get_audit (
                    fixture->probe)->a8_app12509_pin_match);
  assert_terminal_budget (fixture, 1);
  fixture_free (fixture);
}

static void
test_stale_callback_cannot_advance (void)
{
  Fixture *fixture = fixture_start ();
  guint submits;

  complete_out (fixture);
  submits = fixture->submit_count;
  goodix_d278_a2_a8_reentry_probe_complete (
    fixture->probe, GOODIX_D278_10_TRANSFER_IN, fixture->generation + 1,
    NULL, 0, NULL);
  g_assert_cmpuint (fixture->submit_count, ==, submits);
  complete_timeout (fixture);
  assert_terminal_budget (fixture, 0);
  fixture_free (fixture);
}

static void
test_second_a2_prohibited (void)
{
  Fixture *fixture = fixture_start ();
  g_autoptr(GError) error = NULL;

  g_assert_false (goodix_d278_a2_a8_reentry_probe_start (fixture->probe, 11,
                                                          &error));
  g_assert_nonnull (error);
  g_assert_cmpuint (fixture->out_count, ==, 1);
  complete_out (fixture);
  complete_timeout (fixture);
  assert_terminal_budget (fixture, 0);
  fixture_free (fixture);
}

static void
test_second_a8_prohibited (void)
{
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) duplicate_typed = NULL;
  guint submits;
  gsize length;
  const guint8 *data;

  complete_a2_success (fixture);
  duplicate_typed = make_a0 (0xa2, fixture->a2_typed_body,
                             sizeof fixture->a2_typed_body);
  data = g_bytes_get_data (duplicate_typed, &length);
  submits = fixture->submit_count;
  /* A duplicated completion capable of reaching submit_a8 in the old phase
   * is now stale because the sole A8 OUT owns the token. */
  goodix_d278_a2_a8_reentry_probe_complete (
    fixture->probe, GOODIX_D278_10_TRANSFER_IN, fixture->generation,
    data, length, NULL);
  g_assert_cmpuint (fixture->submit_count, ==, submits);
  g_assert_cmpuint (fixture->out_count, ==, 2);
  complete_out (fixture);
  complete_timeout (fixture);
  assert_terminal_budget (fixture, 1);
  fixture_free (fixture);
}

static void
test_a8_typed_wrong_control (void)
{
  static const guint8 app[] = "GF_ST411SEC_APP_12509";
  Fixture *fixture = fixture_start ();
  g_autoptr(GBytes) typed = NULL;

  complete_a2_success (fixture);
  complete_out (fixture);
  complete_ack (fixture, 0xa8, 0x01);
  typed = make_a0 (0xa2, app, sizeof app);
  complete_frame (fixture, typed);
  assert_terminal_budget (fixture, 1);
  fixture_free (fixture);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d278-10/happy-path", test_happy_path);
  g_test_add_func ("/d278-10/a2-ack-timeout", test_a2_ack_timeout);
  g_test_add_func ("/d278-10/a2-ack-mismatch", test_a2_ack_mismatch);
  g_test_add_func ("/d278-10/a2-typed-timeout", test_a2_typed_timeout);
  g_test_add_func ("/d278-10/a2-typed-mismatch", test_a2_typed_mismatch);
  g_test_add_func ("/d278-10/unexpected-e4-during-a2",
                   test_unexpected_e4_during_a2);
  g_test_add_func ("/d278-10/a8-ack-timeout", test_a8_ack_timeout);
  g_test_add_func ("/d278-10/a8-ack-mismatch", test_a8_ack_mismatch);
  g_test_add_func ("/d278-10/a8-typed-timeout", test_a8_typed_timeout);
  g_test_add_func ("/d278-10/a8-wrong-app-pin", test_a8_wrong_app_pin);
  g_test_add_func ("/d278-10/stale-callback", test_stale_callback_cannot_advance);
  g_test_add_func ("/d278-10/second-a2", test_second_a2_prohibited);
  g_test_add_func ("/d278-10/second-a8", test_second_a8_prohibited);
  g_test_add_func ("/d278-10/a8-wrong-control", test_a8_typed_wrong_control);
  return g_test_run ();
}
