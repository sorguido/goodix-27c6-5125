/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_fpi_usb_backend.h"
#include "goodix_usb_router.h"
#include "fpi-usb-transfer.h"

typedef struct {
  GoodixFpiUsbBackend *backend;
  guint64 submit_generation;
  gboolean receive;
} PendingTransfer;

struct _GoodixFpiUsbBackend {
  FpDevice *device; GoodixUsbRouter *router; GCancellable *cancellable;
  guint8 in_endpoint, out_endpoint; gsize receive_size; guint64 generation;
  guint in_outstanding, out_outstanding, max_outstanding;
  guint64 delivery_count, real_submit_count, out_submit_count;
  gboolean terminal_fence; GoodixUsbSubmitSeam seam; gpointer seam_data;
};

static GQuark backend_error_quark (void) { return g_quark_from_static_string ("goodix-fpi-usb-backend-error"); }

static PendingTransfer *pending_new (GoodixFpiUsbBackend *b, gboolean receive)
{ PendingTransfer *p = g_new0 (PendingTransfer, 1); p->backend = b; p->submit_generation = b->generation; p->receive = receive; return p; }

static void transfer_complete_cb (FpiUsbTransfer *transfer, FpDevice *device,
                                  gpointer user_data, GError *error)
{
  PendingTransfer *pending = user_data; GoodixFpiUsbBackend *b = pending->backend;
  (void) device;
  if (pending->receive)
    goodix_fpi_usb_backend_complete_receive (b, pending->submit_generation,
                                             transfer->buffer,
                                             error == NULL ? (gsize) transfer->actual_length : 0, error);
  else if (b->out_outstanding != 0)
    b->out_outstanding--;
  g_free (pending);
}

static void production_submit_in (GoodixFpiUsbBackend *b)
{
  FpiUsbTransfer *t = fpi_usb_transfer_new (b->device);
  fpi_usb_transfer_fill_bulk (t, b->in_endpoint, b->receive_size);
  b->real_submit_count++;
  fpi_usb_transfer_submit (t, 0, b->cancellable, transfer_complete_cb, pending_new (b, TRUE));
}

static void production_submit_out (GoodixFpiUsbBackend *b, GBytes *bytes)
{
  gsize length; const guint8 *data = g_bytes_get_data (bytes, &length);
  FpiUsbTransfer *t = fpi_usb_transfer_new (b->device);
  fpi_usb_transfer_fill_bulk_full (t, b->out_endpoint, g_memdup2 (data, length), length, g_free);
  b->real_submit_count++;
  fpi_usb_transfer_submit (t, 0, b->cancellable, transfer_complete_cb, pending_new (b, FALSE));
}

GoodixFpiUsbBackend *goodix_fpi_usb_backend_new (FpDevice *device, GoodixUsbRouter *router,
                                                  guint8 in_ep, guint8 out_ep, gsize size)
{ GoodixFpiUsbBackend *b = g_new0 (GoodixFpiUsbBackend, 1); b->device=device; b->router=router; b->in_endpoint=in_ep; b->out_endpoint=out_ep; b->receive_size=size; return b; }

void goodix_fpi_usb_backend_free (GoodixFpiUsbBackend *b)
{ if (!b) return; g_return_if_fail (b->in_outstanding == 0 && b->out_outstanding == 0); g_clear_object (&b->cancellable); g_free (b); }
void goodix_fpi_usb_backend_set_submit_seam (GoodixFpiUsbBackend *b, GoodixUsbSubmitSeam seam, gpointer data)
{ g_return_if_fail (b && b->in_outstanding == 0 && b->out_outstanding == 0); b->seam=seam; b->seam_data=data; }
void goodix_fpi_usb_backend_begin_generation (GoodixFpiUsbBackend *b, guint64 generation, GCancellable *c)
{ g_return_if_fail (b && generation != 0 && b->in_outstanding == 0 && b->out_outstanding == 0); g_set_object (&b->cancellable, c); b->generation=generation; b->terminal_fence=FALSE; }

gboolean goodix_fpi_usb_backend_arm_receive (GoodixFpiUsbBackend *b, guint64 generation, GError **error)
{
  if (!b || b->terminal_fence || generation != b->generation || b->in_outstanding) { g_set_error_literal (error, backend_error_quark (), 1, "receive stale, fenced, or already pending"); return FALSE; }
  if (!goodix_usb_router_request_receive (b->router, error)) return FALSE;
  b->in_outstanding=1; b->max_outstanding=MAX(b->max_outstanding,b->in_outstanding);
  if (b->seam) b->seam (b, GOODIX_USB_TRANSFER_IN, generation, NULL, b->seam_data); else production_submit_in (b);
  return TRUE;
}

gboolean goodix_fpi_usb_backend_submit_out (GoodixFpiUsbBackend *b, guint64 generation, GBytes *bytes, GError **error)
{
  if (!b || !bytes || b->terminal_fence || generation != b->generation) { g_set_error_literal (error, backend_error_quark (), 2, "OUT stale or fenced"); return FALSE; }
  b->out_outstanding++; b->out_submit_count++;
  if (b->seam) { b->seam (b, GOODIX_USB_TRANSFER_OUT, generation, bytes, b->seam_data); b->out_outstanding--; }
  else production_submit_out (b, bytes);
  return TRUE;
}

void goodix_fpi_usb_backend_complete_receive (GoodixFpiUsbBackend *b, guint64 submit_generation,
                                               const guint8 *data, gsize length, const GError *error)
{
  if (!b || submit_generation != b->generation || b->in_outstanding == 0) return;
  b->in_outstanding=0;
  if (!b->terminal_fence) b->delivery_count++;
  goodix_usb_router_receive_complete (b->router, submit_generation, data, length, error);
}
void goodix_fpi_usb_backend_cancel (GoodixFpiUsbBackend *b)
{ if (!b || b->terminal_fence) return; b->terminal_fence=TRUE; if (b->cancellable && (b->in_outstanding || b->out_outstanding)) g_cancellable_cancel (b->cancellable); goodix_usb_router_cancel (b->router); }
gboolean goodix_fpi_usb_backend_is_drained (GoodixFpiUsbBackend *b) { return b && b->in_outstanding == 0 && b->out_outstanding == 0; }
guint goodix_fpi_usb_backend_get_outstanding (GoodixFpiUsbBackend *b) { return b->in_outstanding; }
guint goodix_fpi_usb_backend_get_max_outstanding (GoodixFpiUsbBackend *b) { return b->max_outstanding; }
guint64 goodix_fpi_usb_backend_get_delivery_count (GoodixFpiUsbBackend *b) { return b->delivery_count; }
guint64 goodix_fpi_usb_backend_get_real_submit_count (GoodixFpiUsbBackend *b) { return b->real_submit_count; }
guint64 goodix_fpi_usb_backend_get_out_submit_count (GoodixFpiUsbBackend *b) { return b->out_submit_count; }
