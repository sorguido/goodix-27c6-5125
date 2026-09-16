/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "fpi-usb-transfer.h"
FpiUsbTransfer *fpi_usb_transfer_new (FpDevice *device) { (void) device; return g_new0 (FpiUsbTransfer, 1); }
void fpi_usb_transfer_fill_bulk (FpiUsbTransfer *t, guint8 ep, gsize length) { t->endpoint = ep; t->length = (gssize) length; t->buffer = g_malloc0 (length); }
void fpi_usb_transfer_fill_bulk_full (FpiUsbTransfer *t, guint8 ep, guint8 *buffer, gsize length, GDestroyNotify free_func) { t->endpoint=ep; t->length=(gssize)length; t->buffer=buffer; t->free_buffer=free_func; }
void fpi_usb_transfer_submit (FpiUsbTransfer *t, guint timeout, GCancellable *c, FpiUsbTransferCallback cb, gpointer data) { (void) timeout; (void) c; (void) cb; (void) data; g_free (t->buffer); g_free (t); g_error ("host-only seam forbids production submit"); }
