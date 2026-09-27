/* SPDX-License-Identifier: GPL-2.0-or-later */
/* One public-API action; no print serialization, storage, retry or reopen. */
#include "fp-context.h"
#include "fp-device.h"
#include "fp-print.h"
#include <glib-unix.h>
#include <signal.h>
#include <string.h>
#include <unistd.h>

gboolean goodix_fpimage_device_enable_zero_mask_probe (FpDevice *device);

static gboolean
cancel_action (gpointer data)
{
  g_cancellable_cancel (data);
  return G_SOURCE_CONTINUE;
}

static void
progress (FpDevice *device, gint stages, FpPrint *print,
          gpointer data, GError *error)
{
  (void) device; (void) print;
  g_print ("GOODIX_PROBE_PROGRESS stages=%d retry_reported=%u\n", stages, error != NULL);
  if (error != NULL) g_cancellable_cancel (data);
  g_print ("Solleva il dito, poi riposizionalo quando il sensore attende il contatto.\n");
}

int
main (int argc, char **argv)
{
  /* This branch MUST precede fp_context_new(): no enumeration in offline QA. */
  if (argc == 2 && strcmp (argv[1], "--self-check") == 0)
    {
      g_print ("GOODIX_ZERO_MASK_PROBE_BUILD=1 max_events=4 window_ms=3000 action_deadline_ms=120000\n");
      return 0;
    }
  if (argc != 2 || strcmp (argv[1], "--run-once") != 0 || geteuid () != 0)
    {
      g_printerr ("Use the manual operator kit; --self-check does not enumerate USB.\n");
      return 2;
    }
  g_autoptr(FpContext) context = fp_context_new ();
  GPtrArray *devices = fp_context_get_devices (context);
  FpDevice *device = NULL;
  for (guint i = 0; i < devices->len; i++)
    {
      FpDevice *candidate = g_ptr_array_index (devices, i);
      if (strcmp (fp_device_get_driver (candidate), "goodix_27c6_5125") == 0)
        {
          if (device != NULL) return 3;
          device = candidate;
        }
    }
  if (device == NULL || !goodix_fpimage_device_enable_zero_mask_probe (device)) return 3;
  g_autoptr(GError) error = NULL;
  g_autoptr(GCancellable) cancel = g_cancellable_new ();
  guint deadline = g_timeout_add (120000u, cancel_action, cancel);
  guint interrupt = g_unix_signal_add (SIGINT, cancel_action, cancel);
  guint terminate = g_unix_signal_add (SIGTERM, cancel_action, cancel);
  gboolean opened = fp_device_open_sync (device, cancel, &error);
  if (opened)
    {
      g_print ("Appoggia e solleva lo stesso dito a ogni avanzamento. Una sola action, nessun salvataggio.\n");
      /* Sink our reference before the transfer-floating API takes its own.
       * This also keeps early cancellation paths balanced. */
      g_autoptr(FpPrint) template = g_object_ref_sink (fp_print_new (device));
      g_autoptr(FpPrint) result = fp_device_enroll_sync (
        device, template, cancel, progress, cancel, &error);
      g_print ("GOODIX_PROBE_ACTION_DONE success=%u error_code=%d\n", result != NULL,
               error != NULL ? error->code : 0);
      /* Even a completed ordinary enrollment is discarded in memory. */
      g_clear_error (&error);
      gboolean closed = fp_device_close_sync (device, NULL, &error);
      g_print ("GOODIX_PROBE_CLOSE success=%u\n", closed);
      opened = closed;
    }
  else
    g_print ("GOODIX_PROBE_OPEN_FAILED code=%d\n", error != NULL ? error->code : 0);
  g_source_remove (deadline);
  g_source_remove (interrupt);
  g_source_remove (terminate);
  return opened ? 0 : 4;
}
