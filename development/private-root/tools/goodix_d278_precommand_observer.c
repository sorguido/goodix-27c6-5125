/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "goodix_d278_precommand_observer.h"

struct _GoodixD278PrecommandObserver
{
  GoodixD278PrecommandSubmitFunc submit_func;
  gpointer submit_data;
  GoodixD278PrecommandAudit audit;
  gboolean started;
  gboolean outstanding;
  gboolean terminal;
};

static GQuark
observer_error_quark (void)
{
  return g_quark_from_static_string ("goodix-d278-precommand-observer-error");
}

static guint16
read_le16 (const guint8 *bytes)
{
  return (guint16) bytes[0] | ((guint16) bytes[1] << 8);
}

static gboolean
outer_tag_valid (const guint8 *data)
{
  return data[3] == (guint8) (data[0] + data[1] + data[2]);
}

static gboolean
a0_checksum_valid (const guint8 *data,
                   gsize         length)
{
  guint sum = 0;

  for (gsize i = 4; i < length; i++)
    sum = (sum + data[i]) & 0xffu;
  return sum == 0xaau;
}

static void
classify_single_completion (GoodixD278PrecommandObserver *observer,
                            const guint8                 *data,
                            gsize                         length)
{
  GoodixD278PrecommandAudit *audit = &observer->audit;
  guint16 outer_length;
  gsize expected_length;

  audit->received_byte_count = length;
  audit->completion_class = length == 0 ? "NO_DATA_COMPLETION" : "DATA";
  if (length == 0)
    {
      audit->frame_class = "NO_DATA";
      return;
    }
  if (data == NULL)
    {
      audit->completion_class = "RECEIVE_ERROR";
      audit->error_class = "MISSING_DATA_POINTER";
      audit->frame_class = "UNCLASSIFIABLE_DATA";
      return;
    }

  audit->observed_outer_type = data[0];
  if (length < 4)
    {
      audit->frame_class = "PARTIAL_OUTER_HEADER";
      audit->frame_partial = TRUE;
      return;
    }

  outer_length = read_le16 (data + 1);
  expected_length = (gsize) outer_length + 4u;
  if (expected_length > length)
    {
      audit->frame_class = "PARTIAL_FRAME";
      audit->frame_partial = TRUE;
      return;
    }
  if (expected_length < length)
    {
      audit->frame_class = "EXTRA_OR_CONCATENATED_DATA";
      audit->extra_or_concatenated_data = TRUE;
      return;
    }
  if (data[0] != 0xa0 && data[0] != 0xb0)
    {
      audit->frame_class = "UNEXPECTED_OUTER_TYPE";
      return;
    }
  if (!outer_tag_valid (data))
    {
      audit->frame_class = "OUTER_TAG_ERROR";
      return;
    }

  if (data[0] == 0xb0)
    {
      if (outer_length < 5)
        {
          audit->frame_class = "MALFORMED_B0_LENGTH";
          return;
        }
      audit->frame_class = "B0_COMPLETE";
      audit->frame_complete = TRUE;
      audit->observed_body_length = (gint) outer_length;
      return;
    }

  if (length < 8 || outer_length < 4)
    {
      audit->frame_class = "MALFORMED_A0_LENGTH";
      return;
    }
  {
    guint16 inner_length = read_le16 (data + 5);
    gsize body_length;

    audit->observed_control = data[4];
    if (inner_length == 0 || (gsize) inner_length + 3u != outer_length)
      {
        audit->frame_class = "MALFORMED_A0_INNER_LENGTH";
        return;
      }
    body_length = (gsize) inner_length - 1u;
    audit->observed_body_length = (gint) body_length;
    if (!a0_checksum_valid (data, length))
      {
        audit->frame_class = "A0_CHECKSUM_ERROR";
        return;
      }

    audit->frame_complete = TRUE;
    if (data[4] == 0xb0 && body_length == 2)
      {
        audit->frame_class = "A0_ACK_SHAPED_COMPLETE";
        audit->observed_ack_echo = data[7];
        audit->observed_ack_status = data[8];
      }
    else if (data[4] == 0xe4 && body_length == 41)
      audit->frame_class = "A0_E4_BODY41_SHAPED_COMPLETE";
    else
      audit->frame_class = "A0_TYPED_SHAPED_COMPLETE";
  }
}

GoodixD278PrecommandObserver *
goodix_d278_precommand_observer_new (GoodixD278PrecommandSubmitFunc submit_func,
                                     gpointer                       submit_data)
{
  GoodixD278PrecommandObserver *observer;

  g_return_val_if_fail (submit_func != NULL, NULL);
  observer = g_new0 (GoodixD278PrecommandObserver, 1);
  observer->submit_func = submit_func;
  observer->submit_data = submit_data;
  observer->audit.identity_preflight_result = "NOT_RUN";
  observer->audit.completion_class = "NOT_COMPLETED";
  observer->audit.error_class = "NONE";
  observer->audit.frame_class = "NOT_OBSERVED";
  observer->audit.observed_outer_type = -1;
  observer->audit.observed_control = -1;
  observer->audit.observed_ack_echo = -1;
  observer->audit.observed_ack_status = -1;
  observer->audit.observed_body_length = -1;
  observer->audit.backend_drained = TRUE;
  return observer;
}

void
goodix_d278_precommand_observer_free (GoodixD278PrecommandObserver *observer)
{
  if (observer == NULL)
    return;
  g_return_if_fail (!observer->outstanding);
  g_free (observer);
}

gboolean
goodix_d278_precommand_observer_guard_direction (
  GoodixD278PrecommandObserver  *observer,
  GoodixD278PrecommandDirection  direction,
  GError                       **error)
{
  g_return_val_if_fail (observer != NULL, FALSE);
  if (direction == GOODIX_D278_PRECOMMAND_TRANSFER_IN)
    return TRUE;

  observer->audit.prohibited_out_attempt_count++;
  g_set_error_literal (error, observer_error_quark (), 3,
                       "bulk-OUT is structurally forbidden");
  return FALSE;
}

gboolean
goodix_d278_precommand_observer_start (GoodixD278PrecommandObserver *observer,
                                       guint64                       generation,
                                       GError                      **error)
{
  g_return_val_if_fail (observer != NULL, FALSE);
  if (observer->started || observer->terminal || generation == 0)
    {
      g_set_error_literal (error, observer_error_quark (), 1,
                           "observer is single-shot or generation is invalid");
      return FALSE;
    }
  if (!goodix_d278_precommand_observer_guard_direction (
        observer, GOODIX_D278_PRECOMMAND_TRANSFER_IN, error))
    return FALSE;

  observer->started = TRUE;
  observer->outstanding = TRUE;
  observer->audit.backend_drained = FALSE;
  observer->audit.observation_generation = generation;
  observer->audit.physical_in_submit_count = 1;
  if (!observer->submit_func (observer, GOODIX_D278_PRECOMMAND_TRANSFER_IN,
                              generation, observer->submit_data, error))
    {
      observer->outstanding = FALSE;
      observer->terminal = TRUE;
      observer->audit.physical_in_submit_count = 0;
      observer->audit.completion_class = "SUBMIT_ERROR";
      observer->audit.error_class = "IN_SUBMIT_FAILED";
      observer->audit.backend_drained = TRUE;
      observer->audit.cleanup_completed = TRUE;
      return FALSE;
    }
  return TRUE;
}

void
goodix_d278_precommand_observer_complete (GoodixD278PrecommandObserver *observer,
                                          guint64 submit_generation,
                                          const guint8 *data,
                                          gsize length,
                                          const GError *error)
{
  g_return_if_fail (observer != NULL);
  if (!observer->outstanding ||
      submit_generation != observer->audit.observation_generation)
    {
      observer->audit.stale_callback_count++;
      return;
    }

  observer->outstanding = FALSE;
  observer->audit.physical_in_completion_count = 1;
  if (error != NULL)
    {
      if (g_error_matches (error, G_IO_ERROR, G_IO_ERROR_TIMED_OUT))
        {
          observer->audit.completion_class = "TIMEOUT_NO_COMPLETE_DATA";
          observer->audit.error_class = "TIMEOUT";
          observer->audit.timeout_count = 1;
        }
      else if (g_error_matches (error, G_IO_ERROR, G_IO_ERROR_CANCELLED))
        {
          observer->audit.completion_class = "CANCELLED_NO_COMPLETE_DATA";
          observer->audit.error_class = "CANCELLED";
          observer->audit.cancel_count = 1;
        }
      else
        {
          observer->audit.completion_class = "RECEIVE_ERROR";
          observer->audit.error_class = "RECEIVE_ERROR";
        }
    }
  else
    classify_single_completion (observer, data, length);

  observer->terminal = TRUE;
  observer->audit.backend_drained = TRUE;
  observer->audit.cleanup_completed = TRUE;
}

gboolean
goodix_d278_precommand_observer_is_terminal (
  const GoodixD278PrecommandObserver *observer)
{
  return observer != NULL && observer->terminal;
}

const GoodixD278PrecommandAudit *
goodix_d278_precommand_observer_get_audit (
  const GoodixD278PrecommandObserver *observer)
{
  return observer != NULL ? &observer->audit : NULL;
}

GoodixD278PrecommandAudit *
goodix_d278_precommand_observer_get_mutable_audit (
  GoodixD278PrecommandObserver *observer)
{
  return observer != NULL ? &observer->audit : NULL;
}

gchar *
goodix_d278_precommand_observer_audit_to_json (
  const GoodixD278PrecommandObserver *observer)
{
  const GoodixD278PrecommandAudit *audit;

  g_return_val_if_fail (observer != NULL, NULL);
  audit = &observer->audit;
  return g_strdup_printf (
    "{\"identity_preflight_result\":\"%s\","
    "\"usb_open_count\":%u,\"usb_claim_count\":%u,"
    "\"usb_release_count\":%u,\"usb_close_count\":%u,"
    "\"observation_generation\":%" G_GUINT64_FORMAT ","
    "\"physical_in_submit_count\":%u,"
    "\"physical_in_completion_count\":%u,"
    "\"received_byte_count\":%zu,"
    "\"out_submit_count\":%u,\"goodix_command_count\":%u,"
    "\"secure_session_start_count\":%u,\"tls_handshake_count\":%u,"
    "\"completion_class\":\"%s\",\"timeout_count\":%u,"
    "\"cancel_count\":%u,\"error_class\":\"%s\","
    "\"frame_class\":\"%s\",\"frame_complete\":%s,"
    "\"frame_partial\":%s,\"extra_or_concatenated_data\":%s,"
    "\"observed_outer_type\":%d,\"observed_control\":%d,"
    "\"observed_ack_echo\":%d,\"observed_ack_status\":%d,"
    "\"observed_body_length\":%d,\"retry_count\":%u,"
    "\"reopen_count\":%u,\"device_reset_count\":%u,"
    "\"clear_halt_count\":%u,\"persistent_device_write_count\":%u,"
    "\"stale_callback_count\":%u,"
    "\"prohibited_out_attempt_count\":%u,\"backend_drained\":%s,"
    "\"cleanup_completed\":%s}",
    audit->identity_preflight_result, audit->usb_open_count,
    audit->usb_claim_count, audit->usb_release_count, audit->usb_close_count,
    audit->observation_generation, audit->physical_in_submit_count,
    audit->physical_in_completion_count, audit->received_byte_count,
    audit->out_submit_count, audit->goodix_command_count,
    audit->secure_session_start_count, audit->tls_handshake_count,
    audit->completion_class, audit->timeout_count, audit->cancel_count,
    audit->error_class, audit->frame_class,
    audit->frame_complete ? "true" : "false",
    audit->frame_partial ? "true" : "false",
    audit->extra_or_concatenated_data ? "true" : "false",
    audit->observed_outer_type, audit->observed_control,
    audit->observed_ack_echo, audit->observed_ack_status,
    audit->observed_body_length, audit->retry_count, audit->reopen_count,
    audit->device_reset_count, audit->clear_halt_count,
    audit->persistent_device_write_count, audit->stale_callback_count,
    audit->prohibited_out_attempt_count,
    audit->backend_drained ? "true" : "false",
    audit->cleanup_completed ? "true" : "false");
}
