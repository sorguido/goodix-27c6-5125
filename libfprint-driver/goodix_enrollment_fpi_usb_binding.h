/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_FPI_USB_BINDING_H
#define GOODIX_ENROLLMENT_FPI_USB_BINDING_H

#include "goodix_enrollment_outbound_transaction.h"
#include "goodix_fpi_usb_backend.h"

G_BEGIN_DECLS

typedef struct _GoodixEnrollmentFpiUsbBinding GoodixEnrollmentFpiUsbBinding;
typedef gboolean (*GoodixEnrollmentFpiUsbReadyFunc) (
  GoodixEnrollmentFpiUsbBinding *binding,
  gpointer                       user_data,
  GError                       **error);

typedef struct
{
  GoodixEnrollmentOutboundTransactionAudit transaction;
  guint backend_submit_attempt_count;
  guint backend_completion_count;
  guint backend_completion_error_count;
  guint graph_ready_submit_count;
  guint cancellation_count;
  guint retry_count;
  gboolean terminal;
} GoodixEnrollmentFpiUsbBindingAudit;

/* Dormant production-shaped binding. The caller must have begun @generation
 * on @backend. On success the binding takes ownership of @events; on failure
 * ownership stays with the caller. Construction submits nothing. The
 * production FpImageDevice enrollment activation gate remains the authority
 * that prevents reachability. */
GoodixEnrollmentFpiUsbBinding *goodix_enrollment_fpi_usb_binding_new (
  GoodixEnrollmentPostTlsEvents       *events,
  GoodixFpiUsbBackend                 *backend,
  guint64                              generation,
  GoodixEnrollmentFpiUsbBindingAudit  *audit,
  GError                             **error);

/* Free only after the backend OUT count is drained. */
void goodix_enrollment_fpi_usb_binding_free (
  GoodixEnrollmentFpiUsbBinding *binding);
gboolean goodix_enrollment_fpi_usb_binding_set_ready_callback (
  GoodixEnrollmentFpiUsbBinding  *binding,
  GoodixEnrollmentFpiUsbReadyFunc ready,
  gpointer                        user_data,
  GError                        **error);

gboolean goodix_enrollment_fpi_usb_binding_submit_next (
  GoodixEnrollmentFpiUsbBinding *binding,
  GError                       **error);
/* Accepted inbound events automatically submit exactly one next command when
 * the parametric graph moves to a command slot.  Fragmentary/plain inbound
 * slots are no-ops; transport completion remains the only commit gate. */
gboolean goodix_enrollment_fpi_usb_binding_handle_a0 (
  GoodixEnrollmentFpiUsbBinding *binding,
  GBytes                        *frame,
  GError                       **error);
gboolean goodix_enrollment_fpi_usb_binding_handle_plaintext_chunk (
  GoodixEnrollmentFpiUsbBinding *binding,
  GBytes                        *chunk,
  GError                       **error);
void goodix_enrollment_fpi_usb_binding_cancel (
  GoodixEnrollmentFpiUsbBinding *binding,
  const gchar                   *reason);
gboolean goodix_enrollment_fpi_usb_binding_can_free (
  const GoodixEnrollmentFpiUsbBinding *binding);
GoodixFpiUsbBackend *goodix_enrollment_fpi_usb_binding_get_backend (
  const GoodixEnrollmentFpiUsbBinding *binding);
guint64 goodix_enrollment_fpi_usb_binding_get_generation (
  const GoodixEnrollmentFpiUsbBinding *binding);

gboolean goodix_enrollment_fpi_usb_binding_has_pending (
  const GoodixEnrollmentFpiUsbBinding *binding);
gboolean goodix_enrollment_fpi_usb_binding_needs_receive (
  const GoodixEnrollmentFpiUsbBinding *binding);
gboolean goodix_enrollment_fpi_usb_binding_is_complete (
  const GoodixEnrollmentFpiUsbBinding *binding);
gboolean goodix_enrollment_fpi_usb_binding_is_failed (
  const GoodixEnrollmentFpiUsbBinding *binding);
const GError *goodix_enrollment_fpi_usb_binding_get_error (
  const GoodixEnrollmentFpiUsbBinding *binding);

G_END_DECLS

#endif
