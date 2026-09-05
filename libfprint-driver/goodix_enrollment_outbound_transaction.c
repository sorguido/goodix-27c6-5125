/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Host-only completion-gated transaction over an abstract frame sink. */
#include "goodix_enrollment_outbound_transaction.h"

typedef enum
{
  GOODIX_ENROLLMENT_TRANSACTION_ERROR_ARGUMENT,
  GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
  GOODIX_ENROLLMENT_TRANSACTION_ERROR_TRANSPORT,
  GOODIX_ENROLLMENT_TRANSACTION_ERROR_GENERATION,
} GoodixEnrollmentTransactionError;

#define GOODIX_ENROLLMENT_TRANSACTION_ERROR \
  (goodix_enrollment_transaction_error_quark ())

struct _GoodixEnrollmentOutboundTransaction
{
  GoodixEnrollmentPostTlsEvents *events;
  guint64 generation;
  GoodixEnrollmentFrameSinkFunc sink;
  gpointer user_data;
  GoodixEnrollmentOutboundTransactionAudit internal_audit;
  GoodixEnrollmentOutboundTransactionAudit *audit;
  GoodixEnrollmentPreparedCommand prepared;
  GBytes *pending_frame;
  gboolean pending;
  gboolean failed;
};

static GQuark
goodix_enrollment_transaction_error_quark (void)
{
  return g_quark_from_static_string (
    "goodix-enrollment-outbound-transaction-error");
}

static void
clear_pending (GoodixEnrollmentOutboundTransaction *transaction)
{
  g_clear_pointer (&transaction->pending_frame, g_bytes_unref);
  goodix_enrollment_prepared_command_clear (&transaction->prepared);
  transaction->pending = FALSE;
}

static gboolean
transaction_fail (GoodixEnrollmentOutboundTransaction *transaction,
                  GoodixEnrollmentTransactionError      code,
                  const gchar                          *message,
                  GError                              **error)
{
  if (transaction != NULL && !transaction->failed)
    {
      transaction->failed = TRUE;
      transaction->audit->failed = TRUE;
      transaction->audit->rejected_operation_count++;
      clear_pending (transaction);
    }
  if (error == NULL || *error == NULL)
    g_set_error_literal (error, GOODIX_ENROLLMENT_TRANSACTION_ERROR, code,
                         message);
  return FALSE;
}

GoodixEnrollmentOutboundTransaction *
goodix_enrollment_outbound_transaction_new (
  GoodixEnrollmentPostTlsEvents            *events,
  guint64                                   generation,
  GoodixEnrollmentFrameSinkFunc             sink,
  gpointer                                  user_data,
  GoodixEnrollmentOutboundTransactionAudit *audit,
  GError                                  **error)
{
  GoodixEnrollmentOutboundTransaction *transaction;

  if (events == NULL || generation == 0u || sink == NULL)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_TRANSACTION_ERROR,
                           GOODIX_ENROLLMENT_TRANSACTION_ERROR_ARGUMENT,
                           "outbound transaction requires events, generation and sink");
      return NULL;
    }
  transaction = g_new0 (GoodixEnrollmentOutboundTransaction, 1);
  transaction->events = events;
  transaction->generation = generation;
  transaction->sink = sink;
  transaction->user_data = user_data;
  transaction->audit = audit != NULL ? audit : &transaction->internal_audit;
  *transaction->audit = (GoodixEnrollmentOutboundTransactionAudit) { 0 };
  return transaction;
}

void
goodix_enrollment_outbound_transaction_free (
  GoodixEnrollmentOutboundTransaction *transaction)
{
  if (transaction == NULL)
    return;
  clear_pending (transaction);
  g_free (transaction);
}

gboolean
goodix_enrollment_outbound_transaction_submit_next (
  GoodixEnrollmentOutboundTransaction *transaction,
  GError                             **error)
{
  if (transaction == NULL)
    return transaction_fail (
      NULL, GOODIX_ENROLLMENT_TRANSACTION_ERROR_ARGUMENT,
      "outbound transaction is absent", error);
  if (transaction->failed || transaction->pending ||
      goodix_enrollment_post_tls_events_is_complete (transaction->events))
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
      "outbound transaction is terminal or already pending", error);
  if (!goodix_enrollment_post_tls_events_prepare (
        transaction->events, &transaction->prepared, error))
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
      "no enrollment command is ready", error);
  transaction->pending_frame = goodix_enrollment_outbound_frame_build (
    &transaction->prepared, &transaction->audit->frame, error);
  if (transaction->pending_frame == NULL)
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
      "prepared enrollment command could not be serialized", error);

  transaction->pending = TRUE;
  transaction->audit->sink_call_count++;
  if (!transaction->sink (transaction->generation,
                          transaction->pending_frame,
                          transaction->user_data, error))
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_TRANSPORT,
      "synthetic enrollment frame sink rejected OUT", error);
  return TRUE;
}

gboolean
goodix_enrollment_outbound_transaction_complete_out (
  GoodixEnrollmentOutboundTransaction *transaction,
  guint64                              generation,
  const GError                        *completion_error,
  GError                             **error)
{
  GoodixEnrollmentEvent event;

  if (transaction == NULL)
    return transaction_fail (
      NULL, GOODIX_ENROLLMENT_TRANSACTION_ERROR_ARGUMENT,
      "outbound transaction is absent", error);
  if (transaction->failed || !transaction->pending)
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
      "no enrollment OUT is pending", error);
  if (generation != transaction->generation)
    {
      transaction->audit->stale_generation_count++;
      return transaction_fail (
        transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_GENERATION,
        "enrollment OUT completion generation mismatch", error);
    }
  if (completion_error != NULL)
    {
      transaction->audit->transport_error_count++;
      if (error != NULL && *error == NULL)
        *error = g_error_copy (completion_error);
      return transaction_fail (
        transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_TRANSPORT,
        "enrollment OUT completion reported an error", error);
    }

  event = transaction->prepared.intent.event;
  transaction->audit->positive_completion_count++;
  if (!goodix_enrollment_post_tls_events_commit (
        transaction->events, event, error))
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
      "completion-gated command commit failed", error);
  transaction->audit->committed_after_completion_count++;
  clear_pending (transaction);
  return TRUE;
}

void
goodix_enrollment_outbound_transaction_cancel (
  GoodixEnrollmentOutboundTransaction *transaction,
  const gchar                         *reason)
{
  if (transaction == NULL || transaction->failed)
    return;
  (void) transaction_fail (
    transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
    reason != NULL ? reason : "enrollment OUT transaction cancelled", NULL);
}

gboolean
goodix_enrollment_outbound_transaction_handle_a0 (
  GoodixEnrollmentOutboundTransaction *transaction,
  GBytes                              *frame,
  GError                             **error)
{
  if (transaction == NULL || frame == NULL)
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_ARGUMENT,
      "outbound transaction or inbound A0 is absent", error);
  if (transaction->failed || transaction->pending)
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
      "inbound A0 arrived while OUT is pending or terminal", error);
  if (!goodix_enrollment_post_tls_events_handle_a0 (
        transaction->events, frame, error))
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
      "inbound enrollment A0 was rejected", error);
  return TRUE;
}

gboolean
goodix_enrollment_outbound_transaction_handle_plaintext_chunk (
  GoodixEnrollmentOutboundTransaction *transaction,
  GBytes                              *chunk,
  GError                             **error)
{
  if (transaction == NULL || chunk == NULL)
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_ARGUMENT,
      "outbound transaction or plaintext chunk is absent", error);
  if (transaction->failed || transaction->pending)
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
      "plaintext arrived while OUT is pending or terminal", error);
  if (!goodix_enrollment_post_tls_events_handle_plaintext_chunk (
        transaction->events, chunk, error))
    return transaction_fail (
      transaction, GOODIX_ENROLLMENT_TRANSACTION_ERROR_STATE,
      "inbound enrollment plaintext was rejected", error);
  return TRUE;
}

gboolean
goodix_enrollment_outbound_transaction_has_pending (
  const GoodixEnrollmentOutboundTransaction *transaction)
{
  return transaction != NULL && !transaction->failed && transaction->pending;
}

gboolean
goodix_enrollment_outbound_transaction_is_complete (
  const GoodixEnrollmentOutboundTransaction *transaction)
{
  return transaction != NULL && !transaction->failed && !transaction->pending &&
         goodix_enrollment_post_tls_events_is_complete (transaction->events);
}

gboolean
goodix_enrollment_outbound_transaction_is_failed (
  const GoodixEnrollmentOutboundTransaction *transaction)
{
  return transaction == NULL || transaction->failed ||
         goodix_enrollment_post_tls_events_is_failed (transaction->events);
}
