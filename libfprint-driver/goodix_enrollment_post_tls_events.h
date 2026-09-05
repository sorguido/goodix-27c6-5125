/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_POST_TLS_EVENTS_H
#define GOODIX_ENROLLMENT_POST_TLS_EVENTS_H

#include "goodix_a0_protocol.h"
#include "goodix_enrollment_lifecycle_adapter.h"
#include "goodix_image_decoder.h"

G_BEGIN_DECLS

#define GOODIX_ENROLLMENT_B0_MAX_PLAINTEXT_LENGTH 8192u

typedef struct _GoodixEnrollmentPostTlsEvents GoodixEnrollmentPostTlsEvents;

/* @plaintext is transfer-none and valid for the callback duration.  The
 * callback deliberately receives the complete auxiliary message unchanged;
 * its quality/template/NBIS semantics are not interpreted here. */
typedef gboolean (*GoodixEnrollmentAuxiliaryB0Func) (
  GBytes    *plaintext,
  gpointer   user_data,
  GError   **error);

typedef struct
{
  GoodixEnrollmentLifecycleAdapterAudit lifecycle;
  guint parsed_a0_count;
  guint ack_count;
  guint irq2_count;
  guint irq0100_count;
  guint irq0200_count;
  guint nav_count;
  guint primary_b0_count;
  guint auxiliary_b0_count;
  guint plaintext_chunk_count;
  guint completed_b0_message_count;
  guint primary_b0_decode_count;
  guint auxiliary_b0_delivery_count;
  guint rejected_inbound_count;
  guint retry_count;
  guint a0_frame_build_count;
  guint submit_count;
  gboolean failed;
} GoodixEnrollmentPostTlsEventsAudit;

GoodixEnrollmentPostTlsEvents *goodix_enrollment_post_tls_events_new (
  const GoodixEnrollmentModelConfig  *config,
  GoodixEnrollmentImageFunc           image_ready,
  GoodixEnrollmentTimestampFunc       timestamp_ready,
  GoodixEnrollmentAuxiliaryB0Func     auxiliary_ready,
  gpointer                            user_data,
  GoodixEnrollmentPostTlsEventsAudit *audit,
  GError                            **error);
void goodix_enrollment_post_tls_events_free (
  GoodixEnrollmentPostTlsEvents *events);

/* Accepts one complete decrypted A0 application frame. It maps only the exact
 * ACK, IRQ and OEM NAV shape expected by the lifecycle's current state. */
gboolean goodix_enrollment_post_tls_events_handle_a0 (
  GoodixEnrollmentPostTlsEvents *events,
  GBytes                        *frame,
  GError                       **error);

/* B0 framing/reassembly and image decoding remain caller responsibilities.
 * The auxiliary B0 is recorded as opaque and its application semantics stay
 * undetermined. */
gboolean goodix_enrollment_post_tls_events_handle_primary_samples (
  GoodixEnrollmentPostTlsEvents *events,
  const uint16_t                *samples,
  size_t                         sample_count,
  GError                       **error);
gboolean goodix_enrollment_post_tls_events_handle_auxiliary_b0 (
  GoodixEnrollmentPostTlsEvents *events,
  GError                       **error);

/* Reassembles one declared-length B0 plaintext message within a strict bound.
 * Primary messages retain the decoder's exact 7693-byte contract; auxiliary
 * messages are delivered unchanged to @auxiliary_ready. */
gboolean goodix_enrollment_post_tls_events_handle_plaintext_chunk (
  GoodixEnrollmentPostTlsEvents *events,
  GBytes                        *chunk,
  GError                       **error);

gboolean goodix_enrollment_post_tls_events_prepare (
  GoodixEnrollmentPostTlsEvents     *events,
  GoodixEnrollmentPreparedCommand  *prepared,
  GError                          **error);
gboolean goodix_enrollment_post_tls_events_commit (
  GoodixEnrollmentPostTlsEvents *events,
  GoodixEnrollmentEvent          command_event,
  GError                       **error);
GoodixEnrollmentEvent goodix_enrollment_post_tls_events_get_expected_event (
  const GoodixEnrollmentPostTlsEvents *events);
gboolean goodix_enrollment_post_tls_events_is_complete (
  const GoodixEnrollmentPostTlsEvents *events);
gboolean goodix_enrollment_post_tls_events_is_failed (
  const GoodixEnrollmentPostTlsEvents *events);

G_END_DECLS

#endif
