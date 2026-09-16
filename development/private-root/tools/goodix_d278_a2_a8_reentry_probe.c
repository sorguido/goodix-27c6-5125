/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Dedicated D278/10 same-open-epoch exact A2 -> exact A8 discriminator. */
#include "goodix_d278_a2_a8_reentry_probe.h"

#include "goodix_a0_protocol.h"

#include <string.h>

typedef enum
{
  STAGE_READY,
  STAGE_WAIT_A2_OUT,
  STAGE_WAIT_A2_ACK,
  STAGE_WAIT_A2_TYPED,
  STAGE_WAIT_A8_OUT,
  STAGE_WAIT_A8_ACK,
  STAGE_WAIT_A8_TYPED,
  STAGE_TERMINAL,
} ProbeStage;

struct _GoodixD278A2A8ReentryProbe
{
  GoodixD278A2A8SubmitFunc submit_func;
  gpointer submit_data;
  GoodixD278A2A8Audit audit;
  ProbeStage stage;
  guint64 generation;
  GoodixD278A2A8Direction outstanding_direction;
  guint8 expected_a2_typed_sha256[32];
  gsize exact_out_length;
  gboolean outstanding;
  gboolean succeeded;
};

static const guint8 expected_app12509[] = "GF_ST411SEC_APP_12509";

static GQuark
probe_error_quark (void)
{
  return g_quark_from_static_string ("goodix-d278-a2-a8-reentry-probe-error");
}

static void
finish_terminal (GoodixD278A2A8ReentryProbe *probe,
                 const gchar                *completion_class,
                 const gchar                *error_class,
                 gboolean                    succeeded)
{
  probe->stage = STAGE_TERMINAL;
  probe->outstanding = FALSE;
  probe->succeeded = succeeded;
  probe->audit.completion_class = completion_class;
  probe->audit.error_class = error_class;
  probe->audit.reentry_result_class =
    succeeded ? "SAME_SESSION_A2_A8_APP12509_STRICT_MATCH" :
                "SAME_SESSION_A2_A8_NOT_PROVEN";
  probe->audit.backend_drained = TRUE;
  probe->audit.cleanup_completed = TRUE;
}

static gboolean
digest_matches (const guint8 *data,
                gsize         length,
                const guint8  expected[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  guint8 actual[32];
  gsize actual_length = sizeof actual;

  if (length > G_MAXSSIZE)
    return FALSE;
  g_checksum_update (checksum, data, (gssize) length);
  g_checksum_get_digest (checksum, actual, &actual_length);
  return actual_length == sizeof actual &&
         memcmp (actual, expected, sizeof actual) == 0;
}

GBytes *
goodix_d278_10_build_exact_a2_frame (GError **error)
{
  static const guint8 body[] = { 0x01, 0x14 };

  return goodix_a0_build_frame (0xa2, 0xa2, body, sizeof body, error);
}

GBytes *
goodix_d278_10_build_exact_a8_frame (GError **error)
{
  static const guint8 body[] = { 0x00, 0x00 };

  return goodix_a0_build_frame (0xa8, 0xa8, body, sizeof body, error);
}

static gboolean
submit_receive (GoodixD278A2A8ReentryProbe *probe,
                ProbeStage                  next_stage,
                guint                       timeout_ms)
{
  g_autoptr(GError) error = NULL;

  probe->stage = next_stage;
  probe->outstanding = TRUE;
  probe->outstanding_direction = GOODIX_D278_10_TRANSFER_IN;
  probe->audit.physical_in_submit_count++;
  if (!probe->submit_func (probe, GOODIX_D278_10_TRANSFER_IN,
                           probe->generation, NULL, timeout_ms,
                           probe->submit_data, &error))
    {
      probe->audit.physical_in_submit_count--;
      finish_terminal (probe, "SUBMIT_ERROR", "IN_SUBMIT_FAILED", FALSE);
      return FALSE;
    }
  return TRUE;
}

static gboolean
submit_a8 (GoodixD278A2A8ReentryProbe *probe)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) frame = NULL;

  if (probe->audit.a8_submit_count != 0 ||
      probe->audit.a2_sensor_only_submit_count != 1 ||
      probe->audit.a2_ack_count != 1 ||
      probe->audit.a2_typed_response_count != 1 ||
      probe->audit.goodix_command_count != 1 ||
      probe->audit.out_submit_count != 1)
    {
      probe->audit.prohibited_second_command_count++;
      finish_terminal (probe, "COMMAND_BUDGET_VIOLATION",
                       "A8_CAUSAL_GATE_OR_BUDGET_FAILED", FALSE);
      return FALSE;
    }
  frame = goodix_d278_10_build_exact_a8_frame (&error);
  if (frame == NULL)
    {
      finish_terminal (probe, "BUILD_ERROR", "A8_BUILD_FAILED", FALSE);
      return FALSE;
    }
  probe->stage = STAGE_WAIT_A8_OUT;
  probe->outstanding = TRUE;
  probe->outstanding_direction = GOODIX_D278_10_TRANSFER_OUT;
  probe->exact_out_length = g_bytes_get_size (frame);
  probe->audit.goodix_command_count++;
  probe->audit.out_submit_count++;
  probe->audit.a8_submit_count++;
  if (!probe->submit_func (probe, GOODIX_D278_10_TRANSFER_OUT,
                           probe->generation, frame,
                           GOODIX_D278_10_OUT_TIMEOUT_MS,
                           probe->submit_data, &error))
    {
      finish_terminal (probe, "SUBMIT_ERROR", "A8_OUT_SUBMIT_FAILED", FALSE);
      return FALSE;
    }
  return TRUE;
}

static gboolean
parse_exact_a0 (const guint8    *data,
                gsize            length,
                GoodixA0Message *message)
{
  g_autoptr(GBytes) frame = NULL;
  g_autoptr(GError) error = NULL;

  if (data == NULL || length < 5 || data[0] != 0xa0)
    return FALSE;
  frame = g_bytes_new (data, length);
  return goodix_a0_parse_frame (frame, data[4], message, &error);
}

static gboolean
handle_ack (GoodixD278A2A8ReentryProbe *probe,
            const guint8               *data,
            gsize                       length,
            guint8                      expected_echo,
            gboolean                    a2_phase)
{
  GoodixA0Message message = { 0 };
  gsize body_length = 0;
  const guint8 *body;

  if (!parse_exact_a0 (data, length, &message))
    goto mismatch;
  body = g_bytes_get_data (message.body, &body_length);
  if (message.control == 0xb0 && body_length == 2)
    {
      if (a2_phase)
        {
          probe->audit.a2_ack_echo = body[0];
          probe->audit.a2_ack_status = body[1];
        }
      else
        {
          probe->audit.a8_ack_echo = body[0];
          probe->audit.a8_ack_status = body[1];
        }
    }
  if (message.control != 0xb0 || body_length != 2 ||
      body[0] != expected_echo || (body[1] != 0x01 && body[1] != 0x07))
    {
      goodix_a0_message_clear (&message);
      goto mismatch;
    }
  if (a2_phase)
    probe->audit.a2_ack_count = 1;
  else
    probe->audit.a8_ack_count = 1;
  goodix_a0_message_clear (&message);
  return TRUE;

mismatch:
  probe->audit.unexpected_frame_count++;
  finish_terminal (probe, a2_phase ? "A2_ACK_MISMATCH" : "A8_ACK_MISMATCH",
                   a2_phase ? "STRICT_A2_ACK_MISMATCH" :
                              "STRICT_A8_ACK_MISMATCH", FALSE);
  return FALSE;
}

static void
handle_a2_typed (GoodixD278A2A8ReentryProbe *probe,
                 const guint8               *data,
                 gsize                       length)
{
  GoodixA0Message message = { 0 };
  gsize body_length = 0;
  const guint8 *body;

  if (!parse_exact_a0 (data, length, &message))
    goto mismatch;
  body = g_bytes_get_data (message.body, &body_length);
  if (message.control != 0xa2 || body_length != 3 ||
      !digest_matches (body, body_length, probe->expected_a2_typed_sha256))
    {
      goodix_a0_message_clear (&message);
      goto mismatch;
    }
  probe->audit.a2_typed_response_count = 1;
  probe->audit.a2_typed_result_class = "STRICT_MATCH";
  goodix_a0_message_clear (&message);
  (void) submit_a8 (probe);
  return;

mismatch:
  probe->audit.a2_typed_result_class = "MISMATCH";
  probe->audit.unexpected_frame_count++;
  finish_terminal (probe, "A2_TYPED_MISMATCH", "STRICT_A2_TYPED_MISMATCH",
                   FALSE);
}

static void
handle_a8_typed (GoodixD278A2A8ReentryProbe *probe,
                 const guint8               *data,
                 gsize                       length)
{
  GoodixA0Message message = { 0 };
  gsize body_length = 0;
  const guint8 *body;

  if (!parse_exact_a0 (data, length, &message))
    goto mismatch;
  body = g_bytes_get_data (message.body, &body_length);
  if (message.control != 0xa8 || body_length != sizeof expected_app12509 ||
      memcmp (body, expected_app12509, sizeof expected_app12509) != 0)
    {
      goodix_a0_message_clear (&message);
      goto mismatch;
    }
  probe->audit.a8_typed_response_count = 1;
  probe->audit.a8_typed_result_class = "STRICT_MATCH";
  probe->audit.a8_app12509_pin_match = TRUE;
  goodix_a0_message_clear (&message);
  finish_terminal (probe, "A2_A8_REENTRY_ACCEPTED", "NONE", TRUE);
  return;

mismatch:
  probe->audit.a8_typed_result_class = "MISMATCH";
  probe->audit.unexpected_frame_count++;
  finish_terminal (probe, "A8_TYPED_MISMATCH",
                   "STRICT_A8_APP12509_TYPED_MISMATCH", FALSE);
}

GoodixD278A2A8ReentryProbe *
goodix_d278_a2_a8_reentry_probe_new (
  const guint8             expected_a2_typed_sha256[32],
  GoodixD278A2A8SubmitFunc submit_func,
  gpointer                 submit_data)
{
  GoodixD278A2A8ReentryProbe *probe;

  g_return_val_if_fail (expected_a2_typed_sha256 != NULL, NULL);
  g_return_val_if_fail (submit_func != NULL, NULL);
  probe = g_new0 (GoodixD278A2A8ReentryProbe, 1);
  probe->submit_func = submit_func;
  probe->submit_data = submit_data;
  probe->stage = STAGE_READY;
  memcpy (probe->expected_a2_typed_sha256, expected_a2_typed_sha256, 32);
  probe->audit.approved_baseline = "UNAPPROVED_FOR_LIVE";
  probe->audit.identity_preflight_result = "NOT_RUN";
  probe->audit.a2_ack_echo = -1;
  probe->audit.a2_ack_status = -1;
  probe->audit.a8_ack_echo = -1;
  probe->audit.a8_ack_status = -1;
  probe->audit.a2_typed_result_class = "NOT_OBSERVED";
  probe->audit.a8_typed_result_class = "NOT_OBSERVED";
  probe->audit.completion_class = "NOT_COMPLETED";
  probe->audit.error_class = "NONE";
  probe->audit.reentry_result_class = "NOT_OBSERVED";
  probe->audit.backend_drained = TRUE;
  return probe;
}

void
goodix_d278_a2_a8_reentry_probe_free (GoodixD278A2A8ReentryProbe *probe)
{
  if (probe == NULL)
    return;
  g_return_if_fail (!probe->outstanding);
  memset (probe->expected_a2_typed_sha256, 0,
          sizeof probe->expected_a2_typed_sha256);
  g_free (probe);
}

gboolean
goodix_d278_a2_a8_reentry_probe_start (GoodixD278A2A8ReentryProbe *probe,
                                       guint64 generation,
                                       GError **error)
{
  g_autoptr(GBytes) frame = NULL;

  g_return_val_if_fail (probe != NULL, FALSE);
  if (probe->stage != STAGE_READY || generation == 0)
    {
      probe->audit.prohibited_second_command_count++;
      g_set_error_literal (error, probe_error_quark (), 1,
                           "D278/10 probe is single-shot");
      return FALSE;
    }
  frame = goodix_d278_10_build_exact_a2_frame (error);
  if (frame == NULL)
    return FALSE;
  probe->generation = generation;
  probe->exact_out_length = g_bytes_get_size (frame);
  probe->stage = STAGE_WAIT_A2_OUT;
  probe->outstanding = TRUE;
  probe->outstanding_direction = GOODIX_D278_10_TRANSFER_OUT;
  probe->audit.backend_drained = FALSE;
  probe->audit.cleanup_completed = FALSE;
  probe->audit.goodix_command_count = 1;
  probe->audit.out_submit_count = 1;
  probe->audit.a2_sensor_only_submit_count = 1;
  if (!probe->submit_func (probe, GOODIX_D278_10_TRANSFER_OUT, generation,
                           frame, GOODIX_D278_10_OUT_TIMEOUT_MS,
                           probe->submit_data, error))
    {
      finish_terminal (probe, "SUBMIT_ERROR", "A2_OUT_SUBMIT_FAILED", FALSE);
      return FALSE;
    }
  return TRUE;
}

void
goodix_d278_a2_a8_reentry_probe_complete (
  GoodixD278A2A8ReentryProbe *probe,
  GoodixD278A2A8Direction direction,
  guint64 submit_generation,
  const guint8 *data,
  gsize length,
  const GError *error)
{
  g_return_if_fail (probe != NULL);
  if (!probe->outstanding || submit_generation != probe->generation ||
      direction != probe->outstanding_direction)
    {
      probe->audit.stale_callback_count++;
      return;
    }
  probe->outstanding = FALSE;
  if (direction == GOODIX_D278_10_TRANSFER_IN)
    probe->audit.physical_in_completion_count++;
  if (error != NULL)
    {
      if (g_error_matches (error, G_IO_ERROR, G_IO_ERROR_TIMED_OUT))
        {
          probe->audit.timeout_count++;
          finish_terminal (probe, "TIMEOUT", "BOUNDED_PHASE_TIMEOUT", FALSE);
        }
      else
        finish_terminal (probe, "TRANSPORT_ERROR", "TRANSFER_ERROR", FALSE);
      return;
    }

  switch (probe->stage)
    {
    case STAGE_WAIT_A2_OUT:
      if (length != probe->exact_out_length)
        finish_terminal (probe, "OUT_MISMATCH", "PARTIAL_A2_OUT", FALSE);
      else
        (void) submit_receive (probe, STAGE_WAIT_A2_ACK,
                               GOODIX_D278_10_ACK_TIMEOUT_MS);
      return;
    case STAGE_WAIT_A2_ACK:
      if (handle_ack (probe, data, length, 0xa2, TRUE))
        (void) submit_receive (probe, STAGE_WAIT_A2_TYPED,
                               GOODIX_D278_10_TYPED_TIMEOUT_MS);
      return;
    case STAGE_WAIT_A2_TYPED:
      handle_a2_typed (probe, data, length);
      return;
    case STAGE_WAIT_A8_OUT:
      if (length != probe->exact_out_length)
        finish_terminal (probe, "OUT_MISMATCH", "PARTIAL_A8_OUT", FALSE);
      else
        (void) submit_receive (probe, STAGE_WAIT_A8_ACK,
                               GOODIX_D278_10_ACK_TIMEOUT_MS);
      return;
    case STAGE_WAIT_A8_ACK:
      if (handle_ack (probe, data, length, 0xa8, FALSE))
        (void) submit_receive (probe, STAGE_WAIT_A8_TYPED,
                               GOODIX_D278_10_TYPED_TIMEOUT_MS);
      return;
    case STAGE_WAIT_A8_TYPED:
      handle_a8_typed (probe, data, length);
      return;
    default:
      probe->audit.stale_callback_count++;
      return;
    }
}

gboolean
goodix_d278_a2_a8_reentry_probe_is_terminal (
  const GoodixD278A2A8ReentryProbe *probe)
{
  return probe != NULL && probe->stage == STAGE_TERMINAL;
}

gboolean
goodix_d278_a2_a8_reentry_probe_succeeded (
  const GoodixD278A2A8ReentryProbe *probe)
{
  return probe != NULL && probe->succeeded;
}

const GoodixD278A2A8Audit *
goodix_d278_a2_a8_reentry_probe_get_audit (
  const GoodixD278A2A8ReentryProbe *probe)
{
  return probe != NULL ? &probe->audit : NULL;
}

GoodixD278A2A8Audit *
goodix_d278_a2_a8_reentry_probe_get_mutable_audit (
  GoodixD278A2A8ReentryProbe *probe)
{
  return probe != NULL ? &probe->audit : NULL;
}

gchar *
goodix_d278_a2_a8_reentry_probe_audit_to_json (
  const GoodixD278A2A8ReentryProbe *probe)
{
  const GoodixD278A2A8Audit *a;

  g_return_val_if_fail (probe != NULL, NULL);
  a = &probe->audit;
  return g_strdup_printf (
    "{\"approved_baseline\":\"%s\",\"identity_preflight_result\":\"%s\","
    "\"usb_open_count\":%u,\"usb_claim_count\":%u,"
    "\"usb_release_count\":%u,\"usb_close_count\":%u,"
    "\"goodix_command_count\":%u,\"out_submit_count\":%u,"
    "\"a2_sensor_only_submit_count\":%u,\"a2_ack_count\":%u,"
    "\"a2_typed_response_count\":%u,\"a2_ack_echo\":%d,"
    "\"a2_ack_status\":%d,\"a2_typed_result_class\":\"%s\","
    "\"a8_submit_count\":%u,\"a8_ack_count\":%u,"
    "\"a8_typed_response_count\":%u,\"a8_ack_echo\":%d,"
    "\"a8_ack_status\":%d,\"a8_typed_result_class\":\"%s\","
    "\"a8_app12509_pin_match\":%s,"
    "\"physical_in_submit_count\":%u,"
    "\"physical_in_completion_count\":%u,"
    "\"timeout_count\":%u,\"retry_count\":%u,\"reopen_count\":%u,"
    "\"device_reset_count\":%u,\"clear_halt_count\":%u,"
    "\"persistent_device_write_count\":%u,\"tls_handshake_count\":%u,"
    "\"unexpected_frame_count\":%u,\"stale_callback_count\":%u,"
    "\"prohibited_second_command_count\":%u,"
    "\"completion_class\":\"%s\",\"error_class\":\"%s\","
    "\"reentry_result_class\":\"%s\","
    "\"backend_drained\":%s,\"cleanup_completed\":%s}",
    a->approved_baseline, a->identity_preflight_result,
    a->usb_open_count, a->usb_claim_count, a->usb_release_count,
    a->usb_close_count, a->goodix_command_count, a->out_submit_count,
    a->a2_sensor_only_submit_count, a->a2_ack_count,
    a->a2_typed_response_count, a->a2_ack_echo, a->a2_ack_status,
    a->a2_typed_result_class, a->a8_submit_count, a->a8_ack_count,
    a->a8_typed_response_count, a->a8_ack_echo, a->a8_ack_status,
    a->a8_typed_result_class, a->a8_app12509_pin_match ? "true" : "false",
    a->physical_in_submit_count, a->physical_in_completion_count,
    a->timeout_count, a->retry_count, a->reopen_count,
    a->device_reset_count, a->clear_halt_count,
    a->persistent_device_write_count, a->tls_handshake_count,
    a->unexpected_frame_count, a->stale_callback_count,
    a->prohibited_second_command_count, a->completion_class,
    a->error_class, a->reentry_result_class,
    a->backend_drained ? "true" : "false",
    a->cleanup_completed ? "true" : "false");
}
