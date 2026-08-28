/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_fpi_usb_backend.h"
#include "goodix_usb_router.h"
#include "fpi-usb-transfer.h"

typedef struct
{
  GoodixFpiUsbBackend *backend;
  guint64 submit_generation;
  gboolean receive;
} PendingTransfer;

struct _GoodixFpiUsbBackend
{
  FpDevice *device;
  GoodixUsbRouter *router;
  GCancellable *cancellable;
  guint8 in_endpoint, out_endpoint;
  gsize receive_size;
  guint64 generation, in_generation, out_generation;
  guint in_outstanding, out_outstanding, max_outstanding;
  guint64 delivery_count, real_submit_count, out_submit_count;
  gboolean terminal_fence, async_seam, drain_notified;
  GoodixUsbSubmitSeam seam;
  gpointer seam_data;
  GoodixFpiUsbBackendDrainedFunc drained_callback;
  gpointer drained_data;
};

static GQuark
backend_error_quark (void)
{
  return g_quark_from_static_string ("goodix-fpi-usb-backend-error");
}

static gboolean
backend_is_drained (GoodixFpiUsbBackend *backend)
{
  return backend->in_outstanding == 0 && backend->out_outstanding == 0;
}

static void
maybe_notify_drained (GoodixFpiUsbBackend *backend)
{
  if (!backend->terminal_fence || !backend_is_drained (backend) ||
      backend->drain_notified)
    return;
  backend->drain_notified = TRUE;
  if (backend->drained_callback != NULL)
    backend->drained_callback (backend, backend->drained_data);
}

static PendingTransfer *
pending_new (GoodixFpiUsbBackend *backend,
             gboolean             receive)
{
  PendingTransfer *pending = g_new0 (PendingTransfer, 1);
  pending->backend = backend;
  pending->submit_generation = backend->generation;
  pending->receive = receive;
  return pending;
}

static void
transfer_complete_cb (FpiUsbTransfer *transfer,
                      FpDevice       *device,
                      gpointer        user_data,
                      GError         *error)
{
  PendingTransfer *pending = user_data;
  GoodixFpiUsbBackend *backend = pending->backend;
  (void) device;

  if (pending->receive)
    goodix_fpi_usb_backend_complete_receive (
      backend, pending->submit_generation, transfer->buffer,
      error == NULL ? (gsize) transfer->actual_length : 0, error);
  else
    goodix_fpi_usb_backend_complete_out (backend,
                                         pending->submit_generation, error);
  g_free (pending);
}

static void
production_submit_in (GoodixFpiUsbBackend *backend)
{
  FpiUsbTransfer *transfer = fpi_usb_transfer_new (backend->device);
  fpi_usb_transfer_fill_bulk (transfer, backend->in_endpoint,
                              backend->receive_size);
  backend->real_submit_count++;
  fpi_usb_transfer_submit (transfer, 0, backend->cancellable,
                           transfer_complete_cb,
                           pending_new (backend, TRUE));
}

static void
production_submit_out (GoodixFpiUsbBackend *backend,
                       GBytes              *bytes)
{
  gsize length;
  const guint8 *data = g_bytes_get_data (bytes, &length);
  FpiUsbTransfer *transfer = fpi_usb_transfer_new (backend->device);
  fpi_usb_transfer_fill_bulk_full (transfer, backend->out_endpoint,
                                   g_memdup2 (data, length), length, g_free);
  backend->real_submit_count++;
  fpi_usb_transfer_submit (transfer, 0, backend->cancellable,
                           transfer_complete_cb,
                           pending_new (backend, FALSE));
}

GoodixFpiUsbBackend *
goodix_fpi_usb_backend_new (FpDevice       *device,
                            GoodixUsbRouter *router,
                            guint8          in_endpoint,
                            guint8          out_endpoint,
                            gsize           receive_size)
{
  GoodixFpiUsbBackend *backend = g_new0 (GoodixFpiUsbBackend, 1);
  backend->device = device;
  backend->router = router;
  backend->in_endpoint = in_endpoint;
  backend->out_endpoint = out_endpoint;
  backend->receive_size = receive_size;
  return backend;
}

void
goodix_fpi_usb_backend_free (GoodixFpiUsbBackend *backend)
{
  if (backend == NULL)
    return;
  g_return_if_fail (goodix_fpi_usb_backend_can_free (backend));
  g_clear_object (&backend->cancellable);
  g_free (backend);
}

static void
set_submit_seam (GoodixFpiUsbBackend *backend,
                 GoodixUsbSubmitSeam  seam,
                 gpointer             data,
                 gboolean             asynchronous)
{
  g_return_if_fail (backend != NULL && backend_is_drained (backend));
  backend->seam = seam;
  backend->seam_data = data;
  backend->async_seam = asynchronous;
}

void
goodix_fpi_usb_backend_set_submit_seam (GoodixFpiUsbBackend *backend,
                                        GoodixUsbSubmitSeam  seam,
                                        gpointer             data)
{
  set_submit_seam (backend, seam, data, FALSE);
}

void
goodix_fpi_usb_backend_set_async_submit_seam (GoodixFpiUsbBackend *backend,
                                              GoodixUsbSubmitSeam  seam,
                                              gpointer             data)
{
  set_submit_seam (backend, seam, data, TRUE);
}

void
goodix_fpi_usb_backend_set_drained_callback (
  GoodixFpiUsbBackend            *backend,
  GoodixFpiUsbBackendDrainedFunc  callback,
  gpointer                        data)
{
  g_return_if_fail (backend != NULL);
  backend->drained_callback = callback;
  backend->drained_data = data;
}

gboolean
goodix_fpi_usb_backend_begin_generation (GoodixFpiUsbBackend *backend,
                                         guint64               generation,
                                         GCancellable         *cancellable,
                                         GError              **error)
{
  if (backend == NULL || generation == 0 || !backend_is_drained (backend))
    {
      g_set_error_literal (error, backend_error_quark (), 3,
                           "cannot begin generation before backend drain");
      return FALSE;
    }
  g_set_object (&backend->cancellable, cancellable);
  backend->generation = generation;
  backend->terminal_fence = FALSE;
  backend->drain_notified = FALSE;
  return TRUE;
}

gboolean
goodix_fpi_usb_backend_arm_receive (GoodixFpiUsbBackend *backend,
                                    guint64               generation,
                                    GError              **error)
{
  if (backend == NULL || backend->terminal_fence ||
      generation != backend->generation || backend->in_outstanding != 0)
    {
      g_set_error_literal (error, backend_error_quark (), 1,
                           "receive stale, fenced, or already pending");
      return FALSE;
    }
  if (!goodix_usb_router_request_receive (backend->router, error))
    return FALSE;
  backend->in_outstanding = 1;
  backend->in_generation = generation;
  backend->max_outstanding = MAX (backend->max_outstanding,
                                  backend->in_outstanding);
  if (backend->seam != NULL)
    backend->seam (backend, GOODIX_USB_TRANSFER_IN, generation, NULL,
                   backend->seam_data);
  else
    production_submit_in (backend);
  return TRUE;
}

gboolean
goodix_fpi_usb_backend_submit_out (GoodixFpiUsbBackend *backend,
                                   guint64               generation,
                                   GBytes               *bytes,
                                   GError              **error)
{
  if (backend == NULL || bytes == NULL || backend->terminal_fence ||
      generation != backend->generation)
    {
      g_set_error_literal (error, backend_error_quark (), 2,
                           "OUT stale or fenced");
      return FALSE;
    }
  if (backend->out_outstanding != 0 &&
      backend->out_generation != generation)
    {
      g_set_error_literal (error, backend_error_quark (), 2,
                           "OUT belongs to another generation");
      return FALSE;
    }
  backend->out_outstanding++;
  backend->out_generation = generation;
  backend->out_submit_count++;
  if (backend->seam != NULL)
    {
      backend->seam (backend, GOODIX_USB_TRANSFER_OUT, generation, bytes,
                     backend->seam_data);
      if (!backend->async_seam)
        goodix_fpi_usb_backend_complete_out (backend, generation, NULL);
    }
  else
    production_submit_out (backend, bytes);
  return TRUE;
}

void
goodix_fpi_usb_backend_complete_receive (GoodixFpiUsbBackend *backend,
                                         guint64 submit_generation,
                                         const guint8 *data,
                                         gsize length,
                                         const GError *error)
{
  if (backend == NULL || backend->in_outstanding == 0 ||
      submit_generation != backend->in_generation)
    return;

  backend->in_outstanding = 0;
  backend->in_generation = 0;
  if (!backend->terminal_fence && submit_generation == backend->generation)
    {
      backend->delivery_count++;
      goodix_usb_router_receive_complete (backend->router, submit_generation,
                                          data, length, error);
    }
  maybe_notify_drained (backend);
}

void
goodix_fpi_usb_backend_complete_out (GoodixFpiUsbBackend *backend,
                                     guint64 submit_generation,
                                     const GError *error)
{
  (void) error;
  if (backend == NULL || backend->out_outstanding == 0 ||
      submit_generation != backend->out_generation)
    return;
  backend->out_outstanding--;
  if (backend->out_outstanding == 0)
    backend->out_generation = 0;
  maybe_notify_drained (backend);
}

void
goodix_fpi_usb_backend_cancel (GoodixFpiUsbBackend *backend)
{
  if (backend == NULL || backend->terminal_fence)
    return;
  backend->terminal_fence = TRUE;
  backend->drain_notified = FALSE;
  if (backend->cancellable != NULL &&
      (backend->in_outstanding != 0 || backend->out_outstanding != 0))
    g_cancellable_cancel (backend->cancellable);
  goodix_usb_router_cancel (backend->router);
  maybe_notify_drained (backend);
}

gboolean goodix_fpi_usb_backend_is_drained (GoodixFpiUsbBackend *backend)
{ return backend != NULL && backend_is_drained (backend); }
gboolean goodix_fpi_usb_backend_can_free (GoodixFpiUsbBackend *backend)
{ return backend != NULL && backend_is_drained (backend); }
guint goodix_fpi_usb_backend_get_outstanding (GoodixFpiUsbBackend *backend)
{ return backend != NULL ? backend->in_outstanding : 0; }
guint goodix_fpi_usb_backend_get_out_outstanding (GoodixFpiUsbBackend *backend)
{ return backend != NULL ? backend->out_outstanding : 0; }
guint goodix_fpi_usb_backend_get_max_outstanding (GoodixFpiUsbBackend *backend)
{ return backend != NULL ? backend->max_outstanding : 0; }
guint64 goodix_fpi_usb_backend_get_delivery_count (GoodixFpiUsbBackend *backend)
{ return backend != NULL ? backend->delivery_count : 0; }
guint64 goodix_fpi_usb_backend_get_real_submit_count (GoodixFpiUsbBackend *backend)
{ return backend != NULL ? backend->real_submit_count : 0; }
guint64 goodix_fpi_usb_backend_get_out_submit_count (GoodixFpiUsbBackend *backend)
{ return backend != NULL ? backend->out_submit_count : 0; }
