/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_FPI_USB_BACKEND_H
#define GOODIX_FPI_USB_BACKEND_H
#include <glib.h>
typedef struct _FpDevice FpDevice;
typedef struct _GoodixUsbRouter GoodixUsbRouter;
typedef struct _GoodixFpiUsbBackend GoodixFpiUsbBackend;
typedef void (*GoodixUsbSubmitSeam) (GoodixFpiUsbBackend *, gpointer);

GoodixFpiUsbBackend *goodix_fpi_usb_backend_new (FpDevice *device,
                                                  GoodixUsbRouter *router,
                                                  guint8 endpoint,
                                                  gsize receive_size);
void goodix_fpi_usb_backend_free (GoodixFpiUsbBackend *backend);
void goodix_fpi_usb_backend_set_submit_seam (GoodixFpiUsbBackend *backend,
                                              GoodixUsbSubmitSeam seam,
                                              gpointer user_data);
gboolean goodix_fpi_usb_backend_arm_receive (GoodixFpiUsbBackend *backend,
                                             guint64 generation,
                                             GError **error);
void goodix_fpi_usb_backend_complete (GoodixFpiUsbBackend *backend,
                                      guint64 generation,
                                      const guint8 *data, gsize length,
                                      const GError *error);
void goodix_fpi_usb_backend_cancel (GoodixFpiUsbBackend *backend);
guint goodix_fpi_usb_backend_get_outstanding (GoodixFpiUsbBackend *backend);
guint goodix_fpi_usb_backend_get_max_outstanding (GoodixFpiUsbBackend *backend);
guint64 goodix_fpi_usb_backend_get_delivery_count (GoodixFpiUsbBackend *backend);
guint64 goodix_fpi_usb_backend_get_real_submit_count (GoodixFpiUsbBackend *backend);
#endif
