/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Strict inbound-only binding from decrypted post-TLS events to enrollment. */
#include "goodix_enrollment_post_tls_events.h"

#include <string.h>

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
  GoodixEnrollmentAuxiliaryB0Func auxiliary_ready;
  GoodixEnrollmentContactFunc contact;
  gpointer contact_data;
  gpointer user_data;
  GByteArray *b0_pending;
  gboolean failed;
};

static void
clear_pending (GByteArray *pending)
{
  if (pending == NULL)
    return;
  for (gsize i = 0u; i < pending->len; i++)
    ((volatile guint8 *) pending->data)[i] = 0;
  g_byte_array_set_size (pending, 0u);
}

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
      clear_pending (events->b0_pending);
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
  GoodixEnrollmentAuxiliaryB0Func     auxiliary_ready,
  gpointer                            user_data,
  GoodixEnrollmentPostTlsEventsAudit *audit,
  GError                            **error)
{
  GoodixEnrollmentPostTlsEvents *events;

  if (auxiliary_ready == NULL)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_POST_TLS_ERROR,
                           GOODIX_ENROLLMENT_POST_TLS_ERROR_ARGUMENT,
                           "auxiliary B0 callback is required");
      return NULL;
    }
  events = g_new0 (GoodixEnrollmentPostTlsEvents, 1);
  events->audit = audit != NULL ? audit : &events->internal_audit;
  *events->audit = (GoodixEnrollmentPostTlsEventsAudit) { 0 };
  events->auxiliary_ready = auxiliary_ready;
  events->user_data = user_data;
  events->b0_pending = g_byte_array_sized_new (
    GOODIX_ENROLLMENT_B0_MAX_PLAINTEXT_LENGTH);
  events->lifecycle = goodix_enrollment_lifecycle_adapter_new (
    config, image_ready, timestamp_ready, user_data,
    &events->audit->lifecycle, error);
  if (events->lifecycle == NULL)
    {
      g_byte_array_unref (events->b0_pending);
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
  clear_pending (events->b0_pending);
  g_byte_array_unref (events->b0_pending);
  goodix_enrollment_lifecycle_adapter_free (events->lifecycle);
  g_free (events);
}

gboolean
goodix_enrollment_post_tls_events_set_contact_callback (
  GoodixEnrollmentPostTlsEvents *events,
  GoodixEnrollmentContactFunc    contact,
  gpointer                       user_data,
  GError                       **error)
{
  if (events == NULL || contact == NULL || events->contact != NULL ||
      events->audit->parsed_a0_count != 0u || events->b0_pending->len != 0u ||
      events->failed)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "contact callback must be configured once before input",
                        error);
  events->contact = contact;
  events->contact_data = user_data;
  return TRUE;
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
           GoodixFdtFlagsContext  flags_context,
           guint16               *touch_flags,
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
  if (irq != expected_irq ||
      !goodix_fdt_irq_flags_valid (flags_context, flags))
    return FALSE;
  *touch_flags = flags;
  *raw = body + 4u;
  return TRUE;
}

static void
record_a0_mismatch (GoodixEnrollmentPostTlsEvents *events,
                    GoodixEnrollmentEvent          expected,
                    const GoodixA0Message          *message)
{
  const guint8 *body;
  gsize length;

  events->audit->last_mismatch_expected_event = expected;
  events->audit->last_mismatch_observed_control = message->control;
  events->audit->last_mismatch_observed_irq_classified = FALSE;
  events->audit->last_mismatch_observed_irq = 0u;
  events->audit->last_mismatch_observed_irq_flags = 0u;
  body = g_bytes_get_data (message->body, &length);
  if (length == 16u &&
      (message->control == 0x32 || message->control == 0x34 ||
       message->control == 0x36))
    {
      events->audit->last_mismatch_observed_irq_classified = TRUE;
      events->audit->last_mismatch_observed_irq = (guint16) (
        (guint16) body[0] | ((guint16) body[1] << 8));
      events->audit->last_mismatch_observed_irq_flags = (guint16) (
        (guint16) body[2] | ((guint16) body[3] << 8));
    }
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
  guint16 touch_flags = 0u;
  gboolean accepted = FALSE;
  gboolean frame_matches_expected = FALSE;

  if (events == NULL || frame == NULL)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_ARGUMENT,
                        "post-TLS event adapter or frame is absent", error);
  if (events->failed || events->b0_pending->len != 0u)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "post-TLS event adapter is terminal", error);
  expected = goodix_enrollment_lifecycle_adapter_get_expected_event (
    events->lifecycle);
  if (expected == GOODIX_ENROLLMENT_EVENT_NAV)
    {
      if (!parse_nav_no_check (frame))
        return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_FRAME,
                            "OEM NAV no-check frame mismatch", error);
      frame_matches_expected = TRUE;
      accepted = goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, expected, NULL, 0u, NULL, 0u, 0u, error);
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
      frame_matches_expected = TRUE;
      accepted = goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, expected, NULL, 0u, NULL, 0u, 0u, error);
      if (accepted)
        events->audit->ack_count++;
    }
  else if (expected == GOODIX_ENROLLMENT_EVENT_IRQ2 &&
           parse_irq (&message, 0x32, 0x0002,
                      GOODIX_FDT_FLAGS_FINGER_DOWN, &touch_flags, &raw))
    {
      frame_matches_expected = TRUE;
      accepted = goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, expected, NULL, 0u, raw, 12u, touch_flags, error);
      if (accepted)
        {
          events->audit->irq2_count++;
          if (events->contact != NULL &&
              !events->contact (events->audit->irq2_count, TRUE,
                                events->contact_data, error))
            accepted = FALSE;
          else if (events->contact != NULL)
            events->audit->finger_down_delivery_count++;
        }
    }
  else if (expected == GOODIX_ENROLLMENT_EVENT_IRQ0100 &&
           parse_irq (&message, 0x36, 0x0100,
                      GOODIX_FDT_FLAGS_CONTACT_SAMPLE, &touch_flags, &raw))
    {
      frame_matches_expected = TRUE;
      accepted = goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, expected, NULL, 0u, NULL, 0u, 0u, error);
      if (accepted)
        events->audit->irq0100_count++;
    }
  else if (expected == GOODIX_ENROLLMENT_EVENT_IRQ0200 &&
           parse_irq (&message, 0x34, 0x0200,
                      GOODIX_FDT_FLAGS_FINGER_UP, &touch_flags, &raw))
    {
      frame_matches_expected = TRUE;
      accepted = goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, expected, NULL, 0u, raw, 12u, touch_flags, error);
      if (accepted)
        {
          events->audit->irq0200_count++;
          if (events->contact != NULL &&
              !events->contact (events->audit->irq0200_count, FALSE,
                                events->contact_data, error))
            accepted = FALSE;
          else if (events->contact != NULL)
            events->audit->finger_up_delivery_count++;
        }
    }

out:
  if (!accepted && !frame_matches_expected)
    {
      record_a0_mismatch (events, expected, &message);
      if (error != NULL && *error == NULL)
        {
          if (events->audit->last_mismatch_observed_irq_classified)
            g_set_error (
              error, GOODIX_ENROLLMENT_POST_TLS_ERROR,
              GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
              "A0 mismatch: expected %s, observed control 0x%02x IRQ 0x%04x flags 0x%04x",
              goodix_enrollment_event_name (expected), message.control,
              events->audit->last_mismatch_observed_irq,
              events->audit->last_mismatch_observed_irq_flags);
          else
            g_set_error (
              error, GOODIX_ENROLLMENT_POST_TLS_ERROR,
              GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
              "A0 mismatch: expected %s, observed control 0x%02x (not classified as IRQ)",
              goodix_enrollment_event_name (expected), message.control);
        }
    }
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
  if (events == NULL || events->failed || events->b0_pending->len != 0u)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "post-TLS event adapter is absent or terminal", error);
  if (!goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, GOODIX_ENROLLMENT_EVENT_PRIMARY_B0,
        samples, sample_count, NULL, 0u, 0u, error))
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
  if (events == NULL || events->failed || events->b0_pending->len != 0u)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "post-TLS event adapter is absent or terminal", error);
  if (!goodix_enrollment_lifecycle_adapter_observe (
        events->lifecycle, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0,
        NULL, 0u, NULL, 0u, 0u, error))
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
                        "auxiliary B0 is unexpected", error);
  events->audit->auxiliary_b0_count++;
  return TRUE;
}

gboolean
goodix_enrollment_post_tls_events_handle_plaintext_chunk (
  GoodixEnrollmentPostTlsEvents *events,
  GBytes                        *chunk,
  GError                       **error)
{
  GoodixEnrollmentEvent expected;
  const guint8 *data;
  gsize length;
  guint16 declared_length;
  gsize expected_length;
  g_autoptr(GBytes) complete = NULL;
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  GoodixImageDecodeAudit decode_audit;
  gboolean accepted;

  if (events == NULL || chunk == NULL)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_ARGUMENT,
                        "post-TLS event adapter or plaintext chunk is absent",
                        error);
  if (events->failed)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "post-TLS event adapter is terminal", error);
  expected = goodix_enrollment_post_tls_events_get_expected_event (events);
  if (expected != GOODIX_ENROLLMENT_EVENT_PRIMARY_B0 &&
      expected != GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_STATE,
                        "plaintext arrived outside an enrollment B0 slot",
                        error);
  data = g_bytes_get_data (chunk, &length);
  if (length == 0u ||
      length > GOODIX_ENROLLMENT_B0_MAX_PLAINTEXT_LENGTH ||
      events->b0_pending->len >
        GOODIX_ENROLLMENT_B0_MAX_PLAINTEXT_LENGTH - length)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_FRAME,
                        "B0 plaintext reassembly exceeds its bound", error);
  g_byte_array_append (events->b0_pending, data, (guint) length);
  events->audit->plaintext_chunk_count++;
  if (events->b0_pending->len < 3u)
    return TRUE;
  declared_length = (guint16) (
    (guint16) events->b0_pending->data[1] |
    ((guint16) events->b0_pending->data[2] << 8));
  expected_length = (gsize) declared_length + 3u;
  if (declared_length == 0u ||
      expected_length > GOODIX_ENROLLMENT_B0_MAX_PLAINTEXT_LENGTH ||
      (expected == GOODIX_ENROLLMENT_EVENT_PRIMARY_B0 &&
       expected_length != GOODIX_IMAGE_PLAINTEXT_LENGTH) ||
      events->b0_pending->len > expected_length)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_FRAME,
                        "B0 plaintext declared length is invalid", error);
  if (events->b0_pending->len < expected_length)
    return TRUE;

  complete = g_bytes_new (events->b0_pending->data,
                          events->b0_pending->len);
  events->audit->completed_b0_message_count++;
  if (expected == GOODIX_ENROLLMENT_EVENT_PRIMARY_B0)
    {
      if (!goodix_image_decode_plaintext (complete, samples, &decode_audit,
                                          error))
        {
          clear_pending (events->b0_pending);
          memset (samples, 0, sizeof samples);
          return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_FRAME,
                              "primary B0 image decode failed", error);
        }
      events->audit->primary_b0_decode_count++;
      /* The complete message is independently owned by @complete. */
      clear_pending (events->b0_pending);
      accepted = goodix_enrollment_post_tls_events_handle_primary_samples (
        events, samples, G_N_ELEMENTS (samples), error);
      memset (samples, 0, sizeof samples);
    }
  else
    {
      accepted = events->auxiliary_ready (complete, events->user_data, error);
      if (accepted)
        {
          events->audit->auxiliary_b0_delivery_count++;
          /* Clear before the lower-level typed call, whose direct API rejects
           * partially assembled plaintext. */
          clear_pending (events->b0_pending);
          accepted = goodix_enrollment_post_tls_events_handle_auxiliary_b0 (
            events, error);
          return accepted || events_fail (
            events, GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
            "auxiliary B0 lifecycle delivery failed", error);
        }
    }
  clear_pending (events->b0_pending);
  if (!accepted)
    return events_fail (events, GOODIX_ENROLLMENT_POST_TLS_ERROR_EVENT,
                        "complete B0 delivery failed", error);
  return TRUE;
}

gboolean
goodix_enrollment_post_tls_events_prepare (
  GoodixEnrollmentPostTlsEvents    *events,
  GoodixEnrollmentPreparedCommand *prepared,
  GError                          **error)
{
  if (events == NULL || events->failed || events->b0_pending->len != 0u)
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
  if (events == NULL || events->failed || events->b0_pending->len != 0u)
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
