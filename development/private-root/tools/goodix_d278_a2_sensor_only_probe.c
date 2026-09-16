/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * D278/09 dedicated exact A2 {01 14} sensor-only one-shot probe.
 *
 * The only command builder call is the canonical A0 codec invocation below.
 * The state machine permits one OUT, one ACK IN and one typed A2 IN.  Every
 * timeout, mismatch, transport error, duplicate or stale path is terminal and
 * cannot submit another command.
 */
#include "goodix_d278_a2_sensor_only_probe.h"

#include "goodix_a0_protocol.h"

#include <string.h>

typedef enum
{
  PROBE_STAGE_READY,
  PROBE_STAGE_WAIT_OUT,
  PROBE_STAGE_WAIT_ACK,
  PROBE_STAGE_WAIT_TYPED,
  PROBE_STAGE_TERMINAL,
} ProbeStage;

struct _GoodixD278A2SensorOnlyProbe
{
  GoodixD278A2SubmitFunc submit_func;
  gpointer submit_data;
  GoodixD278A2ProbeAudit audit;
  ProbeStage stage;
  guint64 generation;
  GoodixD278A2Direction outstanding_direction;
  guint8 expected_typed_sha256[32];
  gsize exact_out_length;
  gboolean outstanding;
  gboolean succeeded;
};

static GQuark
probe_error_quark (void)
{
  return g_quark_from_static_string ("goodix-d278-a2-sensor-only-probe-error");
}

static void
finish_terminal (GoodixD278A2SensorOnlyProbe *probe,
                 const gchar                 *completion_class,
                 const gchar                 *error_class,
                 gboolean                     succeeded)
{
  probe->stage = PROBE_STAGE_TERMINAL;
  probe->outstanding = FALSE;
  probe->succeeded = succeeded;
  probe->audit.completion_class = completion_class;
  probe->audit.error_class = error_class;
  probe->audit.current_context_result =
    succeeded ? "A2_SENSOR_ONLY_ACCEPTED_IN_CURRENT_CONTEXT" :
                "A2_CURRENT_CONTEXT_AMBIGUOUS_OR_REJECTED";
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
goodix_d278_a2_sensor_only_build_exact_frame (GError **error)
{
  static const guint8 exact_sensor_only_body[] = { 0x01, 0x14 };

  return goodix_a0_build_frame (0xa2, 0xa2, exact_sensor_only_body,
                                sizeof exact_sensor_only_body, error);
}

static gboolean
submit_receive (GoodixD278A2SensorOnlyProbe *probe,
                ProbeStage                   next_stage,
                guint                        timeout_ms)
{
  g_autoptr(GError) error = NULL;

  probe->stage = next_stage;
  probe->outstanding = TRUE;
  probe->outstanding_direction = GOODIX_D278_A2_TRANSFER_IN;
  probe->audit.physical_in_submit_count++;
  if (!probe->submit_func (probe, GOODIX_D278_A2_TRANSFER_IN,
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

static void
handle_ack (GoodixD278A2SensorOnlyProbe *probe,
            const guint8                *data,
            gsize                        length)
{
  GoodixA0Message message = { 0 };
  gsize body_length = 0;
  const guint8 *body;

  if (!parse_exact_a0 (data, length, &message))
    {
      probe->audit.unexpected_frame_count++;
      finish_terminal (probe, "ACK_MISMATCH", "MALFORMED_OR_NON_A0_ACK",
                       FALSE);
      return;
    }
  body = g_bytes_get_data (message.body, &body_length);
  if (message.control == 0xb0 && body_length == 2)
    {
      probe->audit.ack_echo = body[0];
      probe->audit.ack_status = body[1];
    }
  if (message.control != 0xb0 || body_length != 2 || body[0] != 0xa2 ||
      (body[1] != 0x01 && body[1] != 0x07))
    {
      probe->audit.unexpected_frame_count++;
      goodix_a0_message_clear (&message);
      finish_terminal (probe, "ACK_MISMATCH", "STRICT_A2_ACK_MISMATCH",
                       FALSE);
      return;
    }

  probe->audit.ack_count = 1;
  goodix_a0_message_clear (&message);
  (void) submit_receive (probe, PROBE_STAGE_WAIT_TYPED,
                         GOODIX_D278_09_TYPED_TIMEOUT_MS);
}

static void
handle_typed (GoodixD278A2SensorOnlyProbe *probe,
              const guint8                *data,
              gsize                        length)
{
  GoodixA0Message message = { 0 };
  gsize body_length = 0;
  const guint8 *body;

  if (!parse_exact_a0 (data, length, &message))
    {
      probe->audit.typed_result_class = "MALFORMED";
      probe->audit.unexpected_frame_count++;
      finish_terminal (probe, "TYPED_MISMATCH",
                       "MALFORMED_OR_NON_A0_TYPED", FALSE);
      return;
    }
  body = g_bytes_get_data (message.body, &body_length);
  probe->audit.typed_control = message.control;
  probe->audit.typed_body_length =
    body_length <= G_MAXINT ? (gint) body_length : -1;
  if (message.control != 0xa2 || body_length != 3 ||
      !digest_matches (body, body_length, probe->expected_typed_sha256))
    {
      probe->audit.typed_result_class = "MISMATCH";
      probe->audit.unexpected_frame_count++;
      goodix_a0_message_clear (&message);
      finish_terminal (probe, "TYPED_MISMATCH",
                       "STRICT_A2_TYPED_MISMATCH", FALSE);
      return;
    }

  probe->audit.typed_response_count = 1;
  probe->audit.typed_result_class = "STRICT_MATCH";
  goodix_a0_message_clear (&message);
  finish_terminal (probe, "A2_ACCEPTED", "NONE", TRUE);
}

GoodixD278A2SensorOnlyProbe *
goodix_d278_a2_sensor_only_probe_new (
  const guint8             expected_typed_sha256[32],
  GoodixD278A2SubmitFunc   submit_func,
  gpointer                 submit_data)
{
  GoodixD278A2SensorOnlyProbe *probe;

  g_return_val_if_fail (expected_typed_sha256 != NULL, NULL);
  g_return_val_if_fail (submit_func != NULL, NULL);
  probe = g_new0 (GoodixD278A2SensorOnlyProbe, 1);
  probe->submit_func = submit_func;
  probe->submit_data = submit_data;
  probe->stage = PROBE_STAGE_READY;
  memcpy (probe->expected_typed_sha256, expected_typed_sha256,
          sizeof probe->expected_typed_sha256);
  probe->audit.approved_baseline = "UNAPPROVED_FOR_LIVE";
  probe->audit.identity_preflight_result = "NOT_RUN";
  probe->audit.ack_echo = -1;
  probe->audit.ack_status = -1;
  probe->audit.typed_control = -1;
  probe->audit.typed_body_length = -1;
  probe->audit.typed_result_class = "NOT_OBSERVED";
  probe->audit.completion_class = "NOT_COMPLETED";
  probe->audit.error_class = "NONE";
  probe->audit.current_context_result = "NOT_OBSERVED";
  probe->audit.backend_drained = TRUE;
  return probe;
}

void
goodix_d278_a2_sensor_only_probe_free (GoodixD278A2SensorOnlyProbe *probe)
{
  if (probe == NULL)
    return;
  g_return_if_fail (!probe->outstanding);
  memset (probe->expected_typed_sha256, 0,
          sizeof probe->expected_typed_sha256);
  g_free (probe);
}

gboolean
goodix_d278_a2_sensor_only_probe_start (GoodixD278A2SensorOnlyProbe *probe,
                                        guint64 generation,
                                        GError **error)
{
  g_autoptr(GBytes) frame = NULL;

  g_return_val_if_fail (probe != NULL, FALSE);
  if (probe->stage != PROBE_STAGE_READY || generation == 0)
    {
      probe->audit.prohibited_second_command_count++;
      g_set_error_literal (error, probe_error_quark (), 1,
                           "A2 probe is single-command and single-shot");
      return FALSE;
    }
  frame = goodix_d278_a2_sensor_only_build_exact_frame (error);
  if (frame == NULL)
    return FALSE;

  probe->generation = generation;
  probe->exact_out_length = g_bytes_get_size (frame);
  probe->stage = PROBE_STAGE_WAIT_OUT;
  probe->outstanding = TRUE;
  probe->outstanding_direction = GOODIX_D278_A2_TRANSFER_OUT;
  probe->audit.backend_drained = FALSE;
  probe->audit.cleanup_completed = FALSE;
  probe->audit.goodix_command_count = 1;
  probe->audit.out_submit_count = 1;
  probe->audit.a2_sensor_only_submit_count = 1;
  if (!probe->submit_func (probe, GOODIX_D278_A2_TRANSFER_OUT, generation,
                           frame, GOODIX_D278_09_OUT_TIMEOUT_MS,
                           probe->submit_data, error))
    {
      probe->audit.out_submit_count = 0;
      probe->audit.a2_sensor_only_submit_count = 0;
      finish_terminal (probe, "SUBMIT_ERROR", "A2_OUT_SUBMIT_FAILED", FALSE);
      return FALSE;
    }
  return TRUE;
}

void
goodix_d278_a2_sensor_only_probe_complete (
  GoodixD278A2SensorOnlyProbe *probe,
  GoodixD278A2Direction        direction,
  guint64                      submit_generation,
  const guint8                *data,
  gsize                        length,
  const GError                *error)
{
  g_return_if_fail (probe != NULL);
  if (!probe->outstanding || submit_generation != probe->generation ||
      direction != probe->outstanding_direction)
    {
      probe->audit.stale_callback_count++;
      return;
    }

  probe->outstanding = FALSE;
  if (direction == GOODIX_D278_A2_TRANSFER_IN)
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
    case PROBE_STAGE_WAIT_OUT:
      if (length != probe->exact_out_length)
        {
          finish_terminal (probe, "OUT_MISMATCH", "PARTIAL_A2_OUT", FALSE);
          return;
        }
      (void) submit_receive (probe, PROBE_STAGE_WAIT_ACK,
                             GOODIX_D278_09_ACK_TIMEOUT_MS);
      return;
    case PROBE_STAGE_WAIT_ACK:
      handle_ack (probe, data, length);
      return;
    case PROBE_STAGE_WAIT_TYPED:
      handle_typed (probe, data, length);
      return;
    default:
      probe->audit.stale_callback_count++;
      return;
    }
}

gboolean
goodix_d278_a2_sensor_only_probe_is_terminal (
  const GoodixD278A2SensorOnlyProbe *probe)
{
  return probe != NULL && probe->stage == PROBE_STAGE_TERMINAL;
}

gboolean
goodix_d278_a2_sensor_only_probe_succeeded (
  const GoodixD278A2SensorOnlyProbe *probe)
{
  return probe != NULL && probe->succeeded;
}

const GoodixD278A2ProbeAudit *
goodix_d278_a2_sensor_only_probe_get_audit (
  const GoodixD278A2SensorOnlyProbe *probe)
{
  return probe != NULL ? &probe->audit : NULL;
}

GoodixD278A2ProbeAudit *
goodix_d278_a2_sensor_only_probe_get_mutable_audit (
  GoodixD278A2SensorOnlyProbe *probe)
{
  return probe != NULL ? &probe->audit : NULL;
}

gchar *
goodix_d278_a2_sensor_only_probe_audit_to_json (
  const GoodixD278A2SensorOnlyProbe *probe)
{
  const GoodixD278A2ProbeAudit *a;

  g_return_val_if_fail (probe != NULL, NULL);
  a = &probe->audit;
  return g_strdup_printf (
    "{\"approved_baseline\":\"%s\","
    "\"identity_preflight_result\":\"%s\","
    "\"usb_open_count\":%u,\"usb_claim_count\":%u,"
    "\"usb_release_count\":%u,\"usb_close_count\":%u,"
    "\"goodix_command_count\":%u,\"out_submit_count\":%u,"
    "\"a2_sensor_only_submit_count\":%u,"
    "\"physical_in_submit_count\":%u,"
    "\"physical_in_completion_count\":%u,"
    "\"ack_count\":%u,\"typed_response_count\":%u,"
    "\"ack_echo\":%d,\"ack_status\":%d,"
    "\"typed_control\":%d,\"typed_body_length\":%d,"
    "\"typed_result_class\":\"%s\","
    "\"timeout_count\":%u,\"retry_count\":%u,"
    "\"reopen_count\":%u,\"device_reset_count\":%u,"
    "\"clear_halt_count\":%u,\"persistent_device_write_count\":%u,"
    "\"tls_handshake_count\":%u,\"unexpected_frame_count\":%u,"
    "\"stale_callback_count\":%u,"
    "\"prohibited_second_command_count\":%u,"
    "\"completion_class\":\"%s\",\"error_class\":\"%s\","
    "\"current_context_result\":\"%s\","
    "\"backend_drained\":%s,\"cleanup_completed\":%s}",
    a->approved_baseline, a->identity_preflight_result,
    a->usb_open_count, a->usb_claim_count, a->usb_release_count,
    a->usb_close_count, a->goodix_command_count, a->out_submit_count,
    a->a2_sensor_only_submit_count, a->physical_in_submit_count,
    a->physical_in_completion_count, a->ack_count,
    a->typed_response_count, a->ack_echo, a->ack_status,
    a->typed_control, a->typed_body_length, a->typed_result_class,
    a->timeout_count, a->retry_count, a->reopen_count,
    a->device_reset_count, a->clear_halt_count,
    a->persistent_device_write_count, a->tls_handshake_count,
    a->unexpected_frame_count, a->stale_callback_count,
    a->prohibited_second_command_count, a->completion_class,
    a->error_class, a->current_context_result,
    a->backend_drained ? "true" : "false",
    a->cleanup_completed ? "true" : "false");
}
