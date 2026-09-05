/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Strict inbound-only binding from decrypted post-TLS events to enrollment. */
#include "goodix_enrollment_post_tls_events.h"

typedef enum
{
  GOODIX_ENROLLMENT_POST_TLS_ERROR_ARGUMENT,
  GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
  GOODIX_ENROLLMENT_POST_TLS_ERROR_FRAME,
  GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
} GoodixEnrollmentPostTlsError;

#define GOODIX_ENROLLMENT_POST_TLS_ERROR \
  (goodix_enrollment_post_tls_error_quark ())

struct _GoodixEnrollmentPostTlsEvents
{
  GoodixEnrollmentLifecycleAdapter *lifecycle;
  GoodixEnrollmentPostTlsEventsAudit internal_audit;
  GoodixEnrollmentPostTlsEventsAudit *audit;
  gboolean failed;
};

static GQuark
goodix_enrollment_post_tls_error_quark (void)
{
  return g_quark_from_static_string ("goodix-enrollment-post-tls-events-error");
}

static gboolean
events_fail (GoodixEnrollmentPostTlsEvents *events,
             GoodixEnrollmentPostTlsError   code,
             const gchar                   *message,
             GError                       **error)
{
  if (events != NULL && !events->failed)
    {
      events->failed = TRUE;
      events->audit->failed = TRUE;
      events->audit->rejected_inbound_count++;
    }
  if (error == NULL || *error == NULL)
    g_set_error_literal (error, GOODIX_ENROLLMENT_POST_TLS_ERROR, code,
                         message);
  return FALSE;
}

GoodixEnrollmentPostTlsEvents *
goodix_enrollment_post_tls_events_new (
  const GoodixEnrollmentModelConfig  *config,
  GoodixEnrollmentImageFunc           image_ready,
  GoodixEnrollmentTimestampFunc       timestamp_ready,
  gpointer                            user_data,
  GoodixEnrollmentPostTlsEventsAudit *audit,
  GError                            **error)
{
  GoodixEnrollmentPostTlsEvents *events;

  events = g_new0 (GoodixEnrollmentPostTlsEvents, 1);
  events->audit = audit != NULL ? audit : &events->internal_audit;
  *events->audit = (GoodixEnrollmentPostTlsEventsAudit) { 0 };
  events->lifecycle = goodix_enrollment_lifecycle_adapter_new (
    config, image_ready, timestamp_ready, user_data,
    &events->audit->lifecycle, error);
  if (events->lifecycle == NULL)
    {
      g_free (events);
      return NULL;
    }
  return events;
}

void
goodix_enrollment_post_tls_events_free (GoodixEnrollmentPostTlsEvents *events)
{
  if (events == NULL)
    return;
  goodix_enrollment_lifecycle_adapter_free (events->lifecycle);
  g_free (events);
}

static gboolean
expected_ack_echo (GoodixEnrollmentEvent expected,
                   guint8               *echo)
{
  switch (expected)
    {
    case GOODIX_ENROLLMENT_EVENT_ACK_20: *echo = 0x20; return TRUE;
    case GOODIX_ENROLLMENT_EVENT_ACK_22: *echo = 0x22; return TRUE;
    case GOODIX_ENROLLMENT_EVENT_ACK_32: *echo = 0x32; return TRUE;
    case GOODIX_ENROLLMENT_EVENT_ACK_34: *echo = 0x34; return TRUE;
    case GOODIX_ENROLLMENT_EVENT_ACK_36: *echo = 0x36; return TRUE;
    case GOODIX_ENROLLMENT_EVENT_ACK_50: *echo = 0x50; return TRUE;
    case GOODIX_ENROLLMENT_EVENT_NONE:
    case GOODIX_ENROLLMENT_EVENT_IRQ2:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_22:
    case GOODIX_ENROLLMENT_EVENT_PRIMARY_B0:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_34:
    case GOODIX_ENROLLMENT_EVENT_IRQ0200:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_20:
    case GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_32:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_50:
    case GOODIX_ENROLLMENT_EVENT_NAV:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_36:
    case GOODIX_ENROLLMENT_EVENT_IRQ0100:
      return FALSE;
    }
  return FALSE;
}

static gboolean
parse_nav_no_check (GBytes *frame)
{
  const guint8 *data;
  gsize length;
  guint16 outer_length;
  guint16 inner_length;

  if (frame == NULL)
    return FALSE;
  data = g_bytes_get_data (frame, &length);
  if (length != 2417u || data[0] != 0xa0 || data[4] != 0x50)
    return FALSE;
  outer_length = (guint16) ((guint16) data[1] |
                            ((guint16) data[2] << 8));
  inner_length = (guint16) ((guint16) data[5] |
                            ((guint16) data[6] << 8));
  return outer_length == 2413u && inner_length == 2410u &&
         data[3] == (guint8) (data[0] + data[1] + data[2]) &&
         data[7] == 0x50 && data[8] == 0x01 && data[length - 1u] == 0x88;
}

static gboolean
parse_irq (const GoodixA0Message *message,
           guint8                 expected_control,
           guint16                expected_irq,
           guint16                expected_flags,
           const guint8         **raw)
{
  const guint8 *body;
  gsize length;
  guint16 irq;
  guint16 flags;

  if (message->control != expected_control)
    return FALSE;
  body = g_bytes_get_data (message->body, &length);
  if (length != 16u)
    return FALSE;
  irq = (guint16) ((guint16) body[0] | ((guint16) body[1] << 8));
  flags = (guint16) ((guint16) body[2] | ((guint16) body[3] << 8));
  if (irq != expected_irq || flags != expected_flags)
    return FALSE;
  *raw = body + 4u;
  return TRUE;
}

gboolean
goodix_enrollment_post_tls_events_handle_a0 (
  GoodixEnrollmentPostTlsEvents *events,
  GBytes                        *frame,
  GError                       **error)
{
  GoodixEnrollmentEvent expected;
  GoodixA0Message message = { 0 };
  const guint8 *data;
  const guint8 *body;
  const guint8 *raw = NULL;
  gsize frame_length;
  gsize body_length;
  guint8 echo = 0u;
  gboolean accepted = FALSE;

  if (events == NULL || frame == NULL)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_ARGUMENT,
                        "post-TLS event adapter or frame is absent", error);
  if (events->failed)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "post-TLS event adapter is terminal", error);
  expected = goodix_enrollment_lifecycle_adapter_get_expected_event (
    events->lifecycle);
  if (expected == GOODIX_ENROLLMENT_EVENT_NAV)
    {
      if (!parse_nav_no_check (frame))
        return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_FRAME,
                            "OEM NAV no-check frame mismatch", error);
      accepted = goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, expected, NULL, 0u, NULL, 0u, error);
      if (accepted)
        {
          events->audit->parsed_a0_count++;
          events->audit->nav_count++;
        }
      goto out;
    }

  data = g_bytes_get_data (frame, &frame_length);
  if (frame_length < 5u ||
      !goodix_a0_parse_frame (frame, data[4], &message, error))
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_FRAME,
                        "decrypted A0 frame is malformed", error);
  events->audit->parsed_a0_count++;
  body = g_bytes_get_data (message.body, &body_length);

  if (expected_ack_echo (expected, &echo))
    {
      if (message.control != 0xb0 || body_length != 2u ||
          body[0] != echo || body[1] != 0x01)
        goto out;
      accepted = goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, expected, NULL, 0u, NULL, 0u, error);
      if (accepted)
        events->audit->ack_count++;
    }
  else if (expected == GOODIX_ENROLLMENT_EVENT_IRQ2 &&
           parse_irq (&message, 0x32, 0x0002, 0x003f, &raw))
    {
      accepted = goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, expected, NULL, 0u, raw, 12u, error);
      if (accepted)
        events->audit->irq2_count++;
    }
  else if (expected == GOODIX_ENROLLMENT_EVENT_IRQ0100 &&
           parse_irq (&message, 0x36, 0x0100, 0x0000, &raw))
    {
      accepted = goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, expected, NULL, 0u, NULL, 0u, error);
      if (accepted)
        events->audit->irq0100_count++;
    }
  else if (expected == GOODIX_ENROLLMENT_EVENT_IRQ0200 &&
           parse_irq (&message, 0x34, 0x0200, 0x0000, &raw))
    {
      accepted = goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, expected, NULL, 0u, raw, 12u, error);
      if (accepted)
        events->audit->irq0200_count++;
    }

out:
  goodix_a0_message_clear (&message);
  if (!accepted)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
                        "A0 frame does not match the expected enrollment event",
                        error);
  return TRUE;
}

gboolean
goodix_enrollment_post_tls_events_handle_primary_samples (
  GoodixEnrollmentPostTlsEvents *events,
  const uint16_t                *samples,
  size_t                         sample_count,
  GError                       **error)
{
  if (events == NULL || events->failed)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "post-TLS event adapter is absent or terminal", error);
  if (!goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, GOODIX_ENROLLMENT_EVENT_PRIMARY_B0,
        samples, sample_count, NULL, 0u, error))
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
                        "primary B0 samples are unexpected", error);
  events->audit->primary_b0_count++;
  return TRUE;
}

gboolean
goodix_enrollment_post_tls_events_handle_auxiliary_b0 (
  GoodixEnrollmentPostTlsEvents *events,
  GError                       **error)
{
  if (events == NULL || events->failed)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "post-TLS event adapter is absent or terminal", error);
  if (!goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0,
        NULL, 0u, NULL, 0u, error))
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
                        "auxiliary B0 is unexpected", error);
  events->audit->auxiliary_b0_count++;
  return TRUE;
}

gboolean
goodix_enrollment_post_tls_events_prepare (
  GoodixEnrollmentPostTlsEvents    *events,
  GoodixEnrollmentPreparedCommand *prepared,
  GError                          **error)
{
  if (events == NULL || events->failed)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "post-TLS event adapter is absent or terminal", error);
  if (!goodix_enrollment_lifecycle_adapter_prepare (
        events->lifecycle, prepared, error))
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
                        "enrollment command preparation failed", error);
  return TRUE;
}

gboolean
goodix_enrollment_post_tls_events_commit (
  GoodixEnrollmentPostTlsEvents *events,
  GoodixEnrollmentEvent          command_event,
  GError                       **error)
{
  if (events == NULL || events->failed)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "post-TLS event adapter is absent or terminal", error);
  if (!goodix_enrollment_lifecycle_adapter_commit (
        events->lifecycle, command_event, error))
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
                        "enrollment command commit failed", error);
  return TRUE;
}

GoodixEnrollmentEvent
goodix_enrollment_post_tls_events_get_expected_event (
  const GoodixEnrollmentPostTlsEvents *events)
{
  return events != NULL && !events->failed ?
    goodix_enrollment_lifecycle_adapter_get_expected_event (events->lifecycle) :
    GOODIX_ENROLLMENT_EVENT_NONE;
}

gboolean
goodix_enrollment_post_tls_events_is_complete (
  const GoodixEnrollmentPostTlsEvents *events)
{
  return events != NULL && !events->failed &&
    goodix_enrollment_lifecycle_adapter_is_complete (events->lifecycle);
}

gboolean
goodix_enrollment_post_tls_events_is_failed (
  const GoodixEnrollmentPostTlsEvents *events)
{
  return events == NULL || events->failed ||
    goodix_enrollment_lifecycle_adapter_is_failed (events->lifecycle);
}
