/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <string.h>

#include "goodix_d278_precommand_observer.h"

typedef struct
{
  GoodixD278PrecommandObserver *observer;
  guint64 generation;
  guint submit_count;
  GoodixD278PrecommandDirection direction;
} SyntheticSubmit;

static gboolean
synthetic_submit (GoodixD278PrecommandObserver  *observer,
                  GoodixD278PrecommandDirection  direction,
                  guint64                        generation,
                  gpointer                       user_data,
                  GError                       **error)
{
  SyntheticSubmit *submit = user_data;

  if (!goodix_d278_precommand_observer_guard_direction (observer, direction,
                                                         error))
    return FALSE;
  submit->observer = observer;
  submit->generation = generation;
  submit->direction = direction;
  submit->submit_count++;
  return TRUE;
}

static GoodixD278PrecommandObserver *
start_observer (SyntheticSubmit *submit)
{
  g_autoptr(GError) error = NULL;
  GoodixD278PrecommandObserver *observer;

  observer = goodix_d278_precommand_observer_new (synthetic_submit, submit);
  g_assert_true (goodix_d278_precommand_observer_start (observer, 7, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (submit->submit_count, ==, 1);
  g_assert_cmpint (submit->direction, ==,
                   GOODIX_D278_PRECOMMAND_TRANSFER_IN);
  return observer;
}

static GBytes *
make_a0 (guint8 control, const guint8 *body, gsize body_length)
{
  g_autoptr(GByteArray) frame = NULL;
  guint16 inner_length = (guint16) (body_length + 1u);
  guint16 outer_length = (guint16) (body_length + 4u);
  guint8 header[7];
  guint sum;
  guint8 checksum;

  header[0] = 0xa0;
  header[1] = (guint8) outer_length;
  header[2] = (guint8) (outer_length >> 8);
  header[3] = (guint8) (header[0] + header[1] + header[2]);
  header[4] = control;
  header[5] = (guint8) inner_length;
  header[6] = (guint8) (inner_length >> 8);
  sum = (guint) control + (guint) header[5] + (guint) header[6];
  for (gsize i = 0; i < body_length; i++)
    sum += body[i];
  checksum = (guint8) (0xaau - sum);

  frame = g_byte_array_sized_new ((guint) body_length + 8u);
  g_byte_array_append (frame, header, sizeof header);
  if (body_length != 0)
    g_byte_array_append (frame, body, (guint) body_length);
  g_byte_array_append (frame, &checksum, 1);
  return g_byte_array_free_to_bytes (g_steal_pointer (&frame));
}

static void
complete_bytes (SyntheticSubmit *submit, GBytes *bytes)
{
  gsize length;
  const guint8 *data = g_bytes_get_data (bytes, &length);

  goodix_d278_precommand_observer_complete (submit->observer,
                                             submit->generation,
                                             data, length, NULL);
}

static void
assert_zero_out_single_terminal (GoodixD278PrecommandObserver *observer)
{
  const GoodixD278PrecommandAudit *audit =
    goodix_d278_precommand_observer_get_audit (observer);

  g_assert_true (goodix_d278_precommand_observer_is_terminal (observer));
  g_assert_cmpuint (audit->physical_in_submit_count, ==, 1);
  g_assert_cmpuint (audit->physical_in_completion_count, ==, 1);
  g_assert_cmpuint (audit->out_submit_count, ==, 0);
  g_assert_cmpuint (audit->goodix_command_count, ==, 0);
  g_assert_cmpuint (audit->secure_session_start_count, ==, 0);
  g_assert_cmpuint (audit->tls_handshake_count, ==, 0);
  g_assert_cmpuint (audit->retry_count, ==, 0);
  g_assert_cmpuint (audit->reopen_count, ==, 0);
  g_assert_cmpuint (audit->device_reset_count, ==, 0);
  g_assert_cmpuint (audit->clear_halt_count, ==, 0);
  g_assert_cmpuint (audit->persistent_device_write_count, ==, 0);
  g_assert_true (audit->backend_drained);
  g_assert_true (audit->cleanup_completed);
}

static void
test_timeout_no_data (void)
{
  SyntheticSubmit submit = { 0 };
  g_autoptr(GError) timeout = NULL;
  GoodixD278PrecommandObserver *observer = start_observer (&submit);
  const GoodixD278PrecommandAudit *audit;

  g_set_error_literal (&timeout, G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
                       "synthetic timeout");
  goodix_d278_precommand_observer_complete (observer, submit.generation,
                                             NULL, 0, timeout);
  audit = goodix_d278_precommand_observer_get_audit (observer);
  g_assert_cmpstr (audit->completion_class, ==,
                   "TIMEOUT_NO_COMPLETE_DATA");
  g_assert_cmpuint (audit->timeout_count, ==, 1);
  assert_zero_out_single_terminal (observer);
  goodix_d278_precommand_observer_free (observer);
}

static void
test_ack_shaped (void)
{
  const guint8 body[] = { 0xa8, 0x07 };
  SyntheticSubmit submit = { 0 };
  g_autoptr(GBytes) frame = make_a0 (0xb0, body, sizeof body);
  GoodixD278PrecommandObserver *observer = start_observer (&submit);
  const GoodixD278PrecommandAudit *audit;

  complete_bytes (&submit, frame);
  audit = goodix_d278_precommand_observer_get_audit (observer);
  g_assert_cmpstr (audit->frame_class, ==, "A0_ACK_SHAPED_COMPLETE");
  g_assert_cmpint (audit->observed_ack_echo, ==, 0xa8);
  g_assert_cmpint (audit->observed_ack_status, ==, 0x07);
  assert_zero_out_single_terminal (observer);
  goodix_d278_precommand_observer_free (observer);
}

static void
test_typed_shaped (void)
{
  const guint8 body[] = { 'S', 'Y', 'N', 'T', 'H' };
  SyntheticSubmit submit = { 0 };
  g_autoptr(GBytes) frame = make_a0 (0xa8, body, sizeof body);
  GoodixD278PrecommandObserver *observer = start_observer (&submit);
  const GoodixD278PrecommandAudit *audit;

  complete_bytes (&submit, frame);
  audit = goodix_d278_precommand_observer_get_audit (observer);
  g_assert_cmpstr (audit->frame_class, ==, "A0_TYPED_SHAPED_COMPLETE");
  g_assert_cmpint (audit->observed_control, ==, 0xa8);
  g_assert_cmpint (audit->observed_body_length, ==, 5);
  assert_zero_out_single_terminal (observer);
  goodix_d278_precommand_observer_free (observer);
}

static void
test_e4_body41_shape (void)
{
  guint8 body[41] = { 0 };
  SyntheticSubmit submit = { 0 };
  g_autoptr(GBytes) frame = NULL;
  GoodixD278PrecommandObserver *observer;
  const GoodixD278PrecommandAudit *audit;

  memcpy (body, "SYNTHETIC", 9);
  frame = make_a0 (0xe4, body, sizeof body);
  observer = start_observer (&submit);
  complete_bytes (&submit, frame);
  audit = goodix_d278_precommand_observer_get_audit (observer);
  g_assert_cmpstr (audit->frame_class, ==,
                   "A0_E4_BODY41_SHAPED_COMPLETE");
  g_assert_cmpint (audit->observed_body_length, ==, 41);
  assert_zero_out_single_terminal (observer);
  goodix_d278_precommand_observer_free (observer);
}

static void
test_partial (void)
{
  const guint8 body[] = { 0xa8, 0x01 };
  SyntheticSubmit submit = { 0 };
  g_autoptr(GBytes) frame = make_a0 (0xb0, body, sizeof body);
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);
  GoodixD278PrecommandObserver *observer = start_observer (&submit);
  const GoodixD278PrecommandAudit *audit;

  g_assert_cmpuint (length, >, 5);
  goodix_d278_precommand_observer_complete (observer, submit.generation,
                                             data, 5, NULL);
  audit = goodix_d278_precommand_observer_get_audit (observer);
  g_assert_cmpstr (audit->frame_class, ==, "PARTIAL_FRAME");
  g_assert_true (audit->frame_partial);
  assert_zero_out_single_terminal (observer);
  goodix_d278_precommand_observer_free (observer);
}

static void
test_extra_or_concatenated (void)
{
  const guint8 body[] = { 0xa8, 0x01 };
  SyntheticSubmit submit = { 0 };
  g_autoptr(GBytes) frame = make_a0 (0xb0, body, sizeof body);
  g_autoptr(GByteArray) doubled = g_byte_array_new ();
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);
  GoodixD278PrecommandObserver *observer = start_observer (&submit);
  const GoodixD278PrecommandAudit *audit;

  g_byte_array_append (doubled, data, (guint) length);
  g_byte_array_append (doubled, data, (guint) length);
  goodix_d278_precommand_observer_complete (observer, submit.generation,
                                             doubled->data, doubled->len, NULL);
  audit = goodix_d278_precommand_observer_get_audit (observer);
  g_assert_cmpstr (audit->frame_class, ==, "EXTRA_OR_CONCATENATED_DATA");
  g_assert_true (audit->extra_or_concatenated_data);
  assert_zero_out_single_terminal (observer);
  goodix_d278_precommand_observer_free (observer);
}

static void
test_receive_error (void)
{
  SyntheticSubmit submit = { 0 };
  g_autoptr(GError) receive_error = NULL;
  GoodixD278PrecommandObserver *observer = start_observer (&submit);
  const GoodixD278PrecommandAudit *audit;

  g_set_error_literal (&receive_error, G_IO_ERROR, G_IO_ERROR_FAILED,
                       "synthetic receive error");
  goodix_d278_precommand_observer_complete (observer, submit.generation,
                                             NULL, 0, receive_error);
  audit = goodix_d278_precommand_observer_get_audit (observer);
  g_assert_cmpstr (audit->completion_class, ==, "RECEIVE_ERROR");
  assert_zero_out_single_terminal (observer);
  goodix_d278_precommand_observer_free (observer);
}

static void
test_stale_generation_callback (void)
{
  SyntheticSubmit submit = { 0 };
  g_autoptr(GError) timeout = NULL;
  GoodixD278PrecommandObserver *observer = start_observer (&submit);
  const GoodixD278PrecommandAudit *audit;

  g_set_error_literal (&timeout, G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
                       "synthetic timeout");
  goodix_d278_precommand_observer_complete (observer, submit.generation,
                                             NULL, 0, timeout);
  goodix_d278_precommand_observer_complete (observer, submit.generation + 1u,
                                             NULL, 0, NULL);
  audit = goodix_d278_precommand_observer_get_audit (observer);
  g_assert_cmpuint (audit->stale_callback_count, ==, 1);
  assert_zero_out_single_terminal (observer);
  goodix_d278_precommand_observer_free (observer);
}

static void
test_out_attempt_fails_closed (void)
{
  SyntheticSubmit submit = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixD278PrecommandObserver *observer =
    goodix_d278_precommand_observer_new (synthetic_submit, &submit);
  const GoodixD278PrecommandAudit *audit;

  g_assert_false (goodix_d278_precommand_observer_guard_direction (
    observer, GOODIX_D278_PRECOMMAND_TRANSFER_OUT, &error));
  g_assert_nonnull (error);
  audit = goodix_d278_precommand_observer_get_audit (observer);
  g_assert_cmpuint (audit->prohibited_out_attempt_count, ==, 1);
  g_assert_cmpuint (audit->out_submit_count, ==, 0);
  goodix_d278_precommand_observer_free (observer);
}

static void
test_single_shot_reuse (void)
{
  SyntheticSubmit submit = { 0 };
  g_autoptr(GError) timeout = NULL;
  g_autoptr(GError) reuse_error = NULL;
  GoodixD278PrecommandObserver *observer = start_observer (&submit);
  const GoodixD278PrecommandAudit *audit;

  g_set_error_literal (&timeout, G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
                       "synthetic timeout");
  goodix_d278_precommand_observer_complete (observer, submit.generation,
                                             NULL, 0, timeout);
  g_assert_false (goodix_d278_precommand_observer_start (observer, 8,
                                                          &reuse_error));
  g_assert_nonnull (reuse_error);
  audit = goodix_d278_precommand_observer_get_audit (observer);
  g_assert_cmpuint (submit.submit_count, ==, 1);
  g_assert_cmpuint (audit->physical_in_submit_count, ==, 1);
  assert_zero_out_single_terminal (observer);
  goodix_d278_precommand_observer_free (observer);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d278-06/timeout-no-data", test_timeout_no_data);
  g_test_add_func ("/d278-06/a0-ack-shaped", test_ack_shaped);
  g_test_add_func ("/d278-06/a0-typed-shaped", test_typed_shaped);
  g_test_add_func ("/d278-06/e4-body41-shaped", test_e4_body41_shape);
  g_test_add_func ("/d278-06/partial", test_partial);
  g_test_add_func ("/d278-06/extra-concatenated", test_extra_or_concatenated);
  g_test_add_func ("/d278-06/receive-error", test_receive_error);
  g_test_add_func ("/d278-06/stale-generation", test_stale_generation_callback);
  g_test_add_func ("/d278-06/out-attempt", test_out_attempt_fails_closed);
  g_test_add_func ("/d278-06/single-shot-reuse", test_single_shot_reuse);
  return g_test_run ();
}
