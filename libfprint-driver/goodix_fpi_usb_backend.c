/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_fpi_usb_backend.h"
#include "goodix_usb_router.h"
#include "fpi-usb-transfer.h"

struct _GoodixFpiUsbBackend {
  FpDevice *device;                 /* borrowed: open-epoch owner */
  GoodixUsbRouter *router;          /* borrowed: sole receive owner */
  GCancellable *cancellable;
  guint8 endpoint;
  gsize receive_size;
  guint64 generation;
  guint outstanding;
  guint max_outstanding;
  guint64 delivery_count;
  guint64 real_submit_count;
  gboolean terminal_fence;
  GoodixUsbSubmitSeam seam;
  gpointer seam_data;
};

static GQuark backend_error_quark (void)
{
  return g_quark_from_static_string ("goodix-fpi-usb-backend-error");
}

static void
transfer_complete_cb (FpiUsbTransfer *transfer, FpDevice *device,
                      gpointer user_data, GError *error)
{
  GoodixFpiUsbBackend *backend = user_data;
  (void) device;
  goodix_fpi_usb_backend_complete (backend, backend->generation,
                                   transfer->buffer,
                                   error == NULL ? (gsize) transfer->actual_length : 0,
                                   error);
}

static void
production_submit (GoodixFpiUsbBackend *backend, gpointer user_data)
{
  FpiUsbTransfer *transfer;
  (void) user_data;
  transfer = fpi_usb_transfer_new (backend->device);
  fpi_usb_transfer_fill_bulk (transfer, backend->endpoint,
                              backend->receive_size);
  backend->real_submit_count++;
  fpi_usb_transfer_submit (transfer, 0, backend->cancellable,
                           transfer_complete_cb, backend);
}

GoodixFpiUsbBackend *
goodix_fpi_usb_backend_new (FpDevice *device, GoodixUsbRouter *router,
                            guint8 endpoint, gsize receive_size)
{
  GoodixFpiUsbBackend *backend = g_new0 (GoodixFpiUsbBackend, 1);
  backend->device = device;
  backend->router = router;
  backend->endpoint = endpoint;
  backend->receive_size = receive_size;
  backend->cancellable = g_cancellable_new ();
  backend->seam = production_submit;
  return backend;
}

void goodix_fpi_usb_backend_free (GoodixFpiUsbBackend *backend)
{
  if (backend == NULL) return;
  /* The open-epoch owner must drain the cancelled callback before teardown;
   * freeing a callback target while a transfer is outstanding is forbidden. */
  g_return_if_fail (backend->outstanding == 0);
  goodix_fpi_usb_backend_cancel (backend);
  g_clear_object (&backend->cancellable);
  g_free (backend);
}

void
goodix_fpi_usb_backend_set_submit_seam (GoodixFpiUsbBackend *backend,
                                        GoodixUsbSubmitSeam seam,
                                        gpointer user_data)
{
  g_return_if_fail (backend != NULL && backend->outstanding == 0);
  backend->seam = seam;
  backend->seam_data = user_data;
}

gboolean
goodix_fpi_usb_backend_arm_receive (GoodixFpiUsbBackend *backend,
                                    guint64 generation, GError **error)
{
  g_return_val_if_fail (backend != NULL, FALSE);
  if (backend->terminal_fence || generation == 0 || backend->outstanding != 0)
    {
      g_set_error_literal (error, backend_error_quark (), 1,
                           "receive fenced or already outstanding");
      return FALSE;
    }
  if (!goodix_usb_router_request_receive (backend->router, error)) return FALSE;
  backend->generation = generation;
  backend->outstanding = 1;
  backend->max_outstanding = MAX (backend->max_outstanding, backend->outstanding);
  if (backend->seam != NULL) backend->seam (backend, backend->seam_data);
  return TRUE;
}

void
goodix_fpi_usb_backend_complete (GoodixFpiUsbBackend *backend,
                                 guint64 generation, const guint8 *data,
                                 gsize length, const GError *error)
{
  g_return_if_fail (backend != NULL);
  if (backend->outstanding == 0) return;
  if (generation != backend->generation)
    return;
  backend->outstanding = 0;
  if (!backend->terminal_fence)
    backend->delivery_count++;
  goodix_usb_router_receive_complete (backend->router, generation,
                                      data, length, error);
}

void goodix_fpi_usb_backend_cancel (GoodixFpiUsbBackend *backend)
{
  if (backend == NULL || backend->terminal_fence) return;
  backend->terminal_fence = TRUE;
  g_cancellable_cancel (backend->cancellable);
  goodix_usb_router_cancel (backend->router);
}
guint goodix_fpi_usb_backend_get_outstanding (GoodixFpiUsbBackend *b) { return b->outstanding; }
guint goodix_fpi_usb_backend_get_max_outstanding (GoodixFpiUsbBackend *b) { return b->max_outstanding; }
guint64 goodix_fpi_usb_backend_get_delivery_count (GoodixFpiUsbBackend *b) { return b->delivery_count; }
guint64 goodix_fpi_usb_backend_get_real_submit_count (GoodixFpiUsbBackend *b) { return b->real_submit_count; }
