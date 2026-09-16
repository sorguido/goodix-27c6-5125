/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * D278/06 dedicated zero-OUT precommand observer.
 *
 * This file deliberately has no Goodix command builder, secure-session object,
 * TLS object, bulk-OUT endpoint, reset, clear-halt, reopen or retry path.
 */
#include <string.h>

#include <gio/gio.h>
#include <glib.h>

#include "goodix_d278_precommand_observer.h"

#define D278_06_VID 0x27c6u
#define D278_06_PID 0x5125u
#define D278_06_INTERFACE 0u
#define D278_06_EP_IN 0x81u
#define D278_06_GENERATION 1u

#ifndef D278_06_APPROVED_BASELINE
#define D278_06_APPROVED_BASELINE "UNAPPROVED_FOR_LIVE"
#endif

#define D278_06_AUTHORIZATION_TOKEN \
  "D278_06_ONE_ZERO_OUT_PRECOMMAND_OBSERVATION_NO_RETRY"

typedef struct
{
  GoodixD278PrecommandObserver *observer;
  guint64 generation;
} SelfTestSubmit;

static gboolean
self_test_submit (GoodixD278PrecommandObserver  *observer,
                  GoodixD278PrecommandDirection  direction,
                  guint64                        generation,
                  gpointer                       user_data,
                  GError                       **error)
{
  SelfTestSubmit *submit = user_data;

  if (!goodix_d278_precommand_observer_guard_direction (observer, direction,
                                                         error))
    return FALSE;
  submit->observer = observer;
  submit->generation = generation;
  return TRUE;
}

static int
run_self_test (void)
{
  g_autoptr(GError) error = NULL;
  g_autofree gchar *json = NULL;
  GoodixD278PrecommandAudit *audit;
  SelfTestSubmit submit = { 0 };
  GoodixD278PrecommandObserver *observer;

  observer = goodix_d278_precommand_observer_new (self_test_submit, &submit);
  if (!goodix_d278_precommand_observer_start (observer,
                                               D278_06_GENERATION, &error))
    {
      goodix_d278_precommand_observer_free (observer);
      return 1;
    }
  g_set_error_literal (&error, G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
                       "synthetic bounded timeout");
  goodix_d278_precommand_observer_complete (submit.observer,
                                             submit.generation,
                                             NULL, 0, error);
  audit = goodix_d278_precommand_observer_get_mutable_audit (observer);
  audit->identity_preflight_result =
    "HOST_ONLY_SYNTHETIC_NO_USB_APP12509_NOT_REVALIDATED";
  json = goodix_d278_precommand_observer_audit_to_json (observer);
  g_print ("%s\n", json);
  if (!goodix_d278_precommand_observer_is_terminal (observer) ||
      audit->physical_in_submit_count != 1 ||
      audit->physical_in_completion_count != 1 ||
      audit->timeout_count != 1 || audit->out_submit_count != 0 ||
      audit->goodix_command_count != 0 ||
      audit->secure_session_start_count != 0 ||
      audit->tls_handshake_count != 0 || audit->retry_count != 0 ||
      !audit->backend_drained || !audit->cleanup_completed)
    {
      goodix_d278_precommand_observer_free (observer);
      return 1;
    }
  goodix_d278_precommand_observer_free (observer);
  return 0;
}

#ifdef D278_06_LIVE_BINDING
#include <gusb.h>
#include <glib-unix.h>

typedef struct
{
  GUsbDevice *target;
  GCancellable *cancellable;
  GoodixD278PrecommandObserver *observer;
  guint64 generation;
  guint8 *buffer;
} LiveTransfer;

typedef struct
{
  GUsbDevice *target;
  GCancellable *cancellable;
} LiveSubmit;

static void
live_transfer_complete (GObject      *source_object,
                        GAsyncResult *result,
                        gpointer      user_data)
{
  LiveTransfer *transfer = user_data;
  g_autoptr(GError) error = NULL;
  g_autoptr(GError) translated = NULL;
  gssize actual_length;
  const GError *completion_error = NULL;
  gsize length = 0;

  (void) source_object;
  actual_length = g_usb_device_bulk_transfer_finish (transfer->target,
                                                      result, &error);
  if (actual_length >= 0)
    length = (gsize) actual_length;
  else if (g_error_matches (error, G_USB_DEVICE_ERROR,
                            G_USB_DEVICE_ERROR_TIMED_OUT))
    {
      g_set_error_literal (&translated, G_IO_ERROR, G_IO_ERROR_TIMED_OUT,
                           "bounded bulk-IN timed out");
      completion_error = translated;
    }
  else if (g_error_matches (error, G_USB_DEVICE_ERROR,
                            G_USB_DEVICE_ERROR_CANCELLED))
    {
      g_set_error_literal (&translated, G_IO_ERROR, G_IO_ERROR_CANCELLED,
                           "bounded bulk-IN was cancelled");
      completion_error = translated;
    }
  else
    completion_error = error;

  goodix_d278_precommand_observer_complete (
    transfer->observer, transfer->generation, transfer->buffer, length,
    completion_error);
  g_free (transfer->buffer);
  g_free (transfer);
}

static gboolean
live_submit (GoodixD278PrecommandObserver  *observer,
             GoodixD278PrecommandDirection  direction,
             guint64                        generation,
             gpointer                       user_data,
             GError                       **error)
{
  LiveSubmit *submit = user_data;
  LiveTransfer *transfer;

  if (!goodix_d278_precommand_observer_guard_direction (observer, direction,
                                                         error))
    return FALSE;
  transfer = g_new0 (LiveTransfer, 1);
  transfer->target = submit->target;
  transfer->cancellable = submit->cancellable;
  transfer->observer = observer;
  transfer->generation = generation;
  transfer->buffer = g_malloc0 (GOODIX_D278_06_RECEIVE_SIZE);
  g_usb_device_bulk_transfer_async (
    transfer->target, D278_06_EP_IN, transfer->buffer,
    GOODIX_D278_06_RECEIVE_SIZE, GOODIX_D278_06_OBSERVATION_TIMEOUT_MS,
    transfer->cancellable, live_transfer_complete, transfer);
  return TRUE;
}

static gboolean
live_authorization_gate (void)
{
  const gchar *approved = g_getenv ("D278_06_APPROVED_LIVE_BASELINE_SHA");
  const gchar *authorization = g_getenv ("D278_06_OPERATOR_AUTHORIZATION");

  if (g_str_equal (D278_06_APPROVED_BASELINE, "UNAPPROVED_FOR_LIVE") ||
      strlen (D278_06_APPROVED_BASELINE) != 40)
    return FALSE;
  return approved != NULL && authorization != NULL &&
         g_str_equal (approved, D278_06_APPROVED_BASELINE) &&
         g_str_equal (authorization, D278_06_AUTHORIZATION_TOKEN);
}

static gboolean
cancel_on_signal (gpointer user_data)
{
  GCancellable *cancellable = user_data;

  g_cancellable_cancel (cancellable);
  return G_SOURCE_CONTINUE;
}

static void
record_host_failure (GoodixD278PrecommandAudit *audit,
                     const gchar                *error_class)
{
  audit->completion_class = "HOST_BOUNDARY_ERROR";
  audit->error_class = error_class;
}

static int
run_live_once (void)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GUsbContext) usb_context = NULL;
  g_autoptr(GPtrArray) devices = NULL;
  g_autoptr(GCancellable) cancellable = NULL;
  g_autofree gchar *json = NULL;
  GoodixD278PrecommandObserver *observer = NULL;
  GoodixD278PrecommandAudit *audit;
  LiveSubmit submit = { 0 };
  GUsbDevice *target = NULL;
  guint matches = 0;
  gboolean opened = FALSE;
  gboolean claimed = FALSE;
  guint interrupt_source = 0;
  guint terminate_source = 0;
  int return_code = 1;

  /* A future AI-PM-approved build must pin a reviewed full SHA.  The D278/06
   * host-only closure build uses UNAPPROVED_FOR_LIVE and stops here, before
   * context creation, enumeration, open, claim, or any transfer. */
  if (!live_authorization_gate ())
    {
      g_printerr ("LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED\n");
      return 3;
    }

  cancellable = g_cancellable_new ();
  submit.cancellable = cancellable;
  observer = goodix_d278_precommand_observer_new (live_submit, &submit);
  audit = goodix_d278_precommand_observer_get_mutable_audit (observer);
  audit->identity_preflight_result = "HOST_DESCRIPTOR_GATE_NOT_COMPLETED";

  usb_context = g_usb_context_new (&error);
  if (usb_context == NULL || !g_usb_context_enumerate (usb_context, &error))
    {
      record_host_failure (audit, "USB_ENUMERATION_FAILED");
      goto cleanup;
    }
  devices = g_usb_context_get_devices (usb_context);
  for (guint i = 0; i < devices->len; i++)
    {
      GUsbDevice *candidate = g_ptr_array_index (devices, i);
      if (g_usb_device_get_vid (candidate) == D278_06_VID &&
          g_usb_device_get_pid (candidate) == D278_06_PID)
        {
          target = candidate;
          matches++;
        }
    }
  if (matches != 1)
    {
      audit->identity_preflight_result = "EXACT_ONE_27C6_5125_REQUIRED";
      record_host_failure (audit, "TARGET_COUNT_NOT_ONE");
      goto cleanup;
    }

  submit.target = target;
  audit->identity_preflight_result =
    "EXACT_ONE_27C6_5125_PRIOR_D277_02_APP12509_PROOF_CURRENT_FW_NOT_READ";

  if (!g_usb_device_open (target, &error))
    {
      record_host_failure (audit, "USB_OPEN_FAILED");
      goto cleanup;
    }
  opened = TRUE;
  audit->usb_open_count = 1;
  if (!g_usb_device_claim_interface (target, D278_06_INTERFACE,
                                      G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                      &error))
    {
      record_host_failure (audit, "USB_CLAIM_FAILED");
      goto cleanup;
    }
  claimed = TRUE;
  audit->usb_claim_count = 1;
  interrupt_source = g_unix_signal_add (SIGINT, cancel_on_signal, cancellable);
  terminate_source = g_unix_signal_add (SIGTERM, cancel_on_signal, cancellable);
  if (!goodix_d278_precommand_observer_start (observer,
                                               D278_06_GENERATION, &error))
    goto cleanup;
  while (!goodix_d278_precommand_observer_is_terminal (observer))
    g_main_context_iteration (NULL, TRUE);

cleanup:
  if (interrupt_source != 0)
    g_source_remove (interrupt_source);
  if (terminate_source != 0)
    g_source_remove (terminate_source);
  if (claimed)
    {
      g_clear_error (&error);
      if (g_usb_device_release_interface (target, D278_06_INTERFACE,
                                           G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                           &error))
        audit->usb_release_count = 1;
      else
        audit->error_class = "USB_RELEASE_FAILED";
    }
  if (opened)
    {
      g_clear_error (&error);
      if (g_usb_device_close (target, &error))
        audit->usb_close_count = 1;
      else
        audit->error_class = "USB_CLOSE_FAILED";
    }
  if (observer != NULL)
    {
      audit = goodix_d278_precommand_observer_get_mutable_audit (observer);
      audit->cleanup_completed =
        audit->backend_drained && (!claimed || audit->usb_release_count == 1) &&
        (!opened || audit->usb_close_count == 1);
      json = goodix_d278_precommand_observer_audit_to_json (observer);
      g_print ("%s\n", json);
      return_code = audit->cleanup_completed &&
                    audit->physical_in_submit_count == 1 &&
                    audit->physical_in_completion_count == 1 &&
                    audit->out_submit_count == 0 &&
                    audit->goodix_command_count == 0 &&
                    !g_str_equal (audit->completion_class,
                                  "RECEIVE_ERROR") ? 0 : 1;
      goodix_d278_precommand_observer_free (observer);
    }
  return return_code;
}
#endif

int
main (int argc, char **argv)
{
  if (argc == 2 && g_str_equal (argv[1], "--self-test"))
    return run_self_test ();
#ifdef D278_06_LIVE_BINDING
  if (argc == 2 && g_str_equal (argv[1], "--live-zero-out-observe-once"))
    return run_live_once ();
#endif
  g_printerr ("usage: %s --self-test\n", argv[0]);
  return 2;
}
