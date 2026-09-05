/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Dormant binding from completion-gated enrollment OUT to FpiUsbBackend. */
#include "goodix_enrollment_fpi_usb_binding.h"

typedef enum
{
  GOODIX_ENROLLMENT_USB_BINDING_ERROR_ARGUMENT,
  GOODIX_ENROLLMENT_USB_BINDING_ERROR_STATE,
} GoodixEnrollmentUsbBindingError;

#define GOODIX_ENROLLMENT_USB_BINDING_ERROR \
  (goodix_enrollment_usb_binding_error_quark ())

struct _GoodixEnrollmentFpiUsbBinding
{
  GoodixFpiUsbBackend *backend;
  guint64 generation;
  GoodixEnrollmentPostTlsEvents *events;
  GoodixEnrollmentOutboundTransaction *transaction;
  GoodixEnrollmentFpiUsbBindingAudit internal_audit;
  GoodixEnrollmentFpiUsbBindingAudit *audit;
  GoodixEnrollmentFpiUsbReadyFunc ready;
  gpointer ready_data;
  GError *terminal_error;
};

static GQuark
goodix_enrollment_usb_binding_error_quark (void)
{
  return g_quark_from_static_string ("goodix-enrollment-fpi-usb-binding-error");
}

static gboolean
binding_fail (GoodixEnrollmentFpiUsbBinding *binding,
              const gchar                  *message,
              GError                      **error)
{
  if (binding != NULL && binding->terminal_error == NULL)
    {
      binding->terminal_error = g_error_new_literal (
        GOODIX_ENROLLMENT_USB_BINDING_ERROR,
        GOODIX_ENROLLMENT_USB_BINDING_ERROR_STATE, message);
      binding->audit->terminal = TRUE;
    }
  if (error != NULL && *error == NULL)
    *error = binding != NULL && binding->terminal_error != NULL ?
      g_error_copy (binding->terminal_error) :
      g_error_new_literal (GOODIX_ENROLLMENT_USB_BINDING_ERROR,
                           GOODIX_ENROLLMENT_USB_BINDING_ERROR_ARGUMENT,
                           message);
  return FALSE;
}

static gboolean
backend_sink (guint64    generation,
              GBytes    *frame,
              gpointer   user_data,
              GError   **error)
{
  GoodixEnrollmentFpiUsbBinding *binding = user_data;

  binding->audit->backend_submit_attempt_count++;
  return goodix_fpi_usb_backend_submit_out (binding->backend, generation,
                                             frame, error);
}

static void
backend_out_complete (GoodixFpiUsbBackend *backend,
                      guint64               generation,
                      const GError         *completion_error,
                      gpointer              user_data)
{
  GoodixEnrollmentFpiUsbBinding *binding = user_data;
  g_autoptr(GError) error = NULL;

  (void) backend;
  binding->audit->backend_completion_count++;
  if (completion_error != NULL)
    binding->audit->backend_completion_error_count++;
  if (!goodix_enrollment_outbound_transaction_complete_out (
        binding->transaction, generation, completion_error, &error) &&
      binding->terminal_error == NULL)
    {
      binding->terminal_error = g_steal_pointer (&error);
      if (binding->terminal_error == NULL)
        binding->terminal_error = g_error_new_literal (
          GOODIX_ENROLLMENT_USB_BINDING_ERROR,
          GOODIX_ENROLLMENT_USB_BINDING_ERROR_STATE,
          "enrollment backend completion failed");
      binding->audit->terminal = TRUE;
    }
  else if (binding->terminal_error == NULL &&
           !goodix_enrollment_outbound_transaction_is_complete (
             binding->transaction) && binding->ready != NULL &&
           !binding->ready (binding, binding->ready_data, &error))
    {
      binding->terminal_error = g_steal_pointer (&error);
      if (binding->terminal_error == NULL)
        binding->terminal_error = g_error_new_literal (
          GOODIX_ENROLLMENT_USB_BINDING_ERROR,
          GOODIX_ENROLLMENT_USB_BINDING_ERROR_STATE,
          "enrollment receive continuation failed");
      binding->audit->terminal = TRUE;
    }
}

static gboolean
expected_event_is_command (GoodixEnrollmentEvent event)
{
  switch (event)
    {
    case GOODIX_ENROLLMENT_EVENT_COMMAND_20:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_22:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_32:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_34:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_36:
    case GOODIX_ENROLLMENT_EVENT_COMMAND_50:
      return TRUE;
    case GOODIX_ENROLLMENT_EVENT_NONE:
    case GOODIX_ENROLLMENT_EVENT_IRQ2:
    case GOODIX_ENROLLMENT_EVENT_ACK_20:
    case GOODIX_ENROLLMENT_EVENT_ACK_22:
    case GOODIX_ENROLLMENT_EVENT_ACK_32:
    case GOODIX_ENROLLMENT_EVENT_ACK_34:
    case GOODIX_ENROLLMENT_EVENT_ACK_36:
    case GOODIX_ENROLLMENT_EVENT_ACK_50:
    case GOODIX_ENROLLMENT_EVENT_PRIMARY_B0:
    case GOODIX_ENROLLMENT_EVENT_IRQ0200:
    case GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0:
    case GOODIX_ENROLLMENT_EVENT_NAV:
    case GOODIX_ENROLLMENT_EVENT_IRQ0100:
      return FALSE;
    }
  return FALSE;
}

static gboolean
submit_if_graph_ready (GoodixEnrollmentFpiUsbBinding *binding,
                       GError                       **error)
{
  GoodixEnrollmentEvent expected;

  if (binding->terminal_error != NULL ||
      goodix_enrollment_outbound_transaction_has_pending (
        binding->transaction) ||
      goodix_enrollment_outbound_transaction_is_complete (
        binding->transaction))
    return binding->terminal_error == NULL;
  expected = goodix_enrollment_post_tls_events_get_expected_event (
    binding->events);
  if (!expected_event_is_command (expected))
    return TRUE;
  if (!goodix_enrollment_fpi_usb_binding_submit_next (binding, error))
    return FALSE;
  binding->audit->graph_ready_submit_count++;
  return TRUE;
}

GoodixEnrollmentFpiUsbBinding *
goodix_enrollment_fpi_usb_binding_new (
  GoodixEnrollmentPostTlsEvents      *events,
  GoodixFpiUsbBackend                *backend,
  guint64                             generation,
  GoodixEnrollmentFpiUsbBindingAudit *audit,
  GError                            **error)
{
  GoodixEnrollmentFpiUsbBinding *binding;

  if (events == NULL || backend == NULL || generation == 0u)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_USB_BINDING_ERROR,
                           GOODIX_ENROLLMENT_USB_BINDING_ERROR_ARGUMENT,
                           "enrollment USB binding arguments are incomplete");
      return NULL;
    }
  binding = g_new0 (GoodixEnrollmentFpiUsbBinding, 1);
  binding->backend = backend;
  binding->generation = generation;
  binding->audit = audit != NULL ? audit : &binding->internal_audit;
  *binding->audit = (GoodixEnrollmentFpiUsbBindingAudit) { 0 };
  binding->transaction = goodix_enrollment_outbound_transaction_new (
    events, generation, backend_sink, binding, &binding->audit->transaction,
    error);
  if (binding->transaction == NULL)
    {
      g_free (binding);
      return NULL;
    }
  binding->events = events;
  goodix_fpi_usb_backend_set_out_completed_callback (
    backend, backend_out_complete, binding);
  return binding;
}

void
goodix_enrollment_fpi_usb_binding_free (GoodixEnrollmentFpiUsbBinding *binding)
{
  if (binding == NULL)
    return;
  g_return_if_fail (goodix_enrollment_fpi_usb_binding_can_free (binding));
  goodix_fpi_usb_backend_set_out_completed_callback (binding->backend,
                                                      NULL, NULL);
  goodix_enrollment_outbound_transaction_free (binding->transaction);
  goodix_enrollment_post_tls_events_free (binding->events);
  g_clear_error (&binding->terminal_error);
  g_free (binding);
}

gboolean
goodix_enrollment_fpi_usb_binding_set_ready_callback (
  GoodixEnrollmentFpiUsbBinding  *binding,
  GoodixEnrollmentFpiUsbReadyFunc ready,
  gpointer                        user_data,
  GError                        **error)
{
  if (binding == NULL || ready == NULL || binding->ready != NULL ||
      binding->terminal_error != NULL ||
      binding->audit->backend_submit_attempt_count != 0u ||
      binding->audit->transaction.positive_completion_count != 0u)
    return binding_fail (
      binding, "enrollment ready callback must be configured before input",
      error);
  binding->ready = ready;
  binding->ready_data = user_data;
  return TRUE;
}

gboolean
goodix_enrollment_fpi_usb_binding_submit_next (
  GoodixEnrollmentFpiUsbBinding *binding,
  GError                       **error)
{
  if (binding == NULL || binding->terminal_error != NULL)
    return binding_fail (binding, "enrollment USB binding is absent or terminal",
                         error);
  if (!goodix_enrollment_outbound_transaction_submit_next (
        binding->transaction, error))
    return binding_fail (binding, "enrollment USB OUT submission failed", error);
  return TRUE;
}

void
goodix_enrollment_fpi_usb_binding_cancel (
  GoodixEnrollmentFpiUsbBinding *binding,
  const gchar                   *reason)
{
  const gchar *message;

  if (binding == NULL || binding->terminal_error != NULL)
    return;
  message = reason != NULL ? reason : "enrollment USB binding cancelled";
  binding->audit->cancellation_count++;
  goodix_fpi_usb_backend_cancel (binding->backend);
  goodix_enrollment_outbound_transaction_cancel (binding->transaction,
                                                   message);
  (void) binding_fail (binding, message, NULL);
}

gboolean
goodix_enrollment_fpi_usb_binding_can_free (
  const GoodixEnrollmentFpiUsbBinding *binding)
{
  return binding != NULL &&
         goodix_fpi_usb_backend_get_out_outstanding (binding->backend) == 0u;
}

GoodixFpiUsbBackend *
goodix_enrollment_fpi_usb_binding_get_backend (
  const GoodixEnrollmentFpiUsbBinding *binding)
{
  return binding != NULL ? binding->backend : NULL;
}

guint64
goodix_enrollment_fpi_usb_binding_get_generation (
  const GoodixEnrollmentFpiUsbBinding *binding)
{
  return binding != NULL ? binding->generation : 0u;
}

gboolean
goodix_enrollment_fpi_usb_binding_handle_a0 (
  GoodixEnrollmentFpiUsbBinding *binding,
  GBytes                        *frame,
  GError                       **error)
{
  if (binding == NULL || binding->terminal_error != NULL)
    return binding_fail (binding, "enrollment USB binding is absent or terminal",
                         error);
  if (!goodix_enrollment_outbound_transaction_handle_a0 (
        binding->transaction, frame, error))
    return binding_fail (binding, "enrollment inbound A0 failed", error);
  return submit_if_graph_ready (binding, error);
}

gboolean
goodix_enrollment_fpi_usb_binding_handle_plaintext_chunk (
  GoodixEnrollmentFpiUsbBinding *binding,
  GBytes                        *chunk,
  GError                       **error)
{
  if (binding == NULL || binding->terminal_error != NULL)
    return binding_fail (binding, "enrollment USB binding is absent or terminal",
                         error);
  if (!goodix_enrollment_outbound_transaction_handle_plaintext_chunk (
        binding->transaction, chunk, error))
    return binding_fail (binding, "enrollment plaintext failed", error);
  return submit_if_graph_ready (binding, error);
}

gboolean
goodix_enrollment_fpi_usb_binding_has_pending (
  const GoodixEnrollmentFpiUsbBinding *binding)
{
  return binding != NULL && binding->terminal_error == NULL &&
         goodix_enrollment_outbound_transaction_has_pending (
           binding->transaction);
}

gboolean
goodix_enrollment_fpi_usb_binding_needs_receive (
  const GoodixEnrollmentFpiUsbBinding *binding)
{
  return binding != NULL && binding->terminal_error == NULL &&
         !goodix_enrollment_outbound_transaction_has_pending (
           binding->transaction) &&
         !goodix_enrollment_outbound_transaction_is_complete (
           binding->transaction) &&
         !expected_event_is_command (
           goodix_enrollment_post_tls_events_get_expected_event (
             binding->events));
}

gboolean
goodix_enrollment_fpi_usb_binding_is_complete (
  const GoodixEnrollmentFpiUsbBinding *binding)
{
  return binding != NULL && binding->terminal_error == NULL &&
         goodix_enrollment_outbound_transaction_is_complete (
           binding->transaction);
}

gboolean
goodix_enrollment_fpi_usb_binding_is_failed (
  const GoodixEnrollmentFpiUsbBinding *binding)
{
  return binding == NULL || binding->terminal_error != NULL ||
         goodix_enrollment_outbound_transaction_is_failed (
           binding->transaction);
}

const GError *
goodix_enrollment_fpi_usb_binding_get_error (
  const GoodixEnrollmentFpiUsbBinding *binding)
{
  return binding != NULL ? binding->terminal_error : NULL;
}
