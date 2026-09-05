/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_OUTBOUND_TRANSACTION_H
#define GOODIX_ENROLLMENT_OUTBOUND_TRANSACTION_H

#include "goodix_enrollment_outbound_frame.h"
#include "goodix_enrollment_post_tls_events.h"

G_BEGIN_DECLS

typedef struct _GoodixEnrollmentOutboundTransaction
  GoodixEnrollmentOutboundTransaction;

/* Host-testable sink seam. @frame is transfer-none and remains valid until
 * complete_out. No production USB backend is referenced by this contract. */
typedef gboolean (*GoodixEnrollmentFrameSinkFunc) (
  guint64    generation,
  GBytes    *frame,
  gpointer   user_data,
  GError   **error);

typedef struct
{
  GoodixEnrollmentOutboundFrameAudit frame;
  guint sink_call_count;
  guint positive_completion_count;
  guint committed_after_completion_count;
  guint rejected_operation_count;
  guint stale_generation_count;
  guint transport_error_count;
  guint retry_count;
  guint real_usb_submit_count;
  gboolean failed;
} GoodixEnrollmentOutboundTransactionAudit;

GoodixEnrollmentOutboundTransaction *
goodix_enrollment_outbound_transaction_new (
  GoodixEnrollmentPostTlsEvents              *events,
  guint64                                     generation,
  GoodixEnrollmentFrameSinkFunc               sink,
  gpointer                                    user_data,
  GoodixEnrollmentOutboundTransactionAudit   *audit,
  GError                                    **error);
void goodix_enrollment_outbound_transaction_free (
  GoodixEnrollmentOutboundTransaction *transaction);

gboolean goodix_enrollment_outbound_transaction_submit_next (
  GoodixEnrollmentOutboundTransaction *transaction,
  GError                             **error);
gboolean goodix_enrollment_outbound_transaction_complete_out (
  GoodixEnrollmentOutboundTransaction *transaction,
  guint64                              generation,
  const GError                        *completion_error,
  GError                             **error);

gboolean goodix_enrollment_outbound_transaction_handle_a0 (
  GoodixEnrollmentOutboundTransaction *transaction,
  GBytes                              *frame,
  GError                             **error);
gboolean goodix_enrollment_outbound_transaction_handle_plaintext_chunk (
  GoodixEnrollmentOutboundTransaction *transaction,
  GBytes                              *chunk,
  GError                             **error);

gboolean goodix_enrollment_outbound_transaction_has_pending (
  const GoodixEnrollmentOutboundTransaction *transaction);
gboolean goodix_enrollment_outbound_transaction_is_complete (
  const GoodixEnrollmentOutboundTransaction *transaction);
gboolean goodix_enrollment_outbound_transaction_is_failed (
  const GoodixEnrollmentOutboundTransaction *transaction);

G_END_DECLS

#endif
