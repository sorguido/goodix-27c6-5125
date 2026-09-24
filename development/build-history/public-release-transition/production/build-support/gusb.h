/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Compile declarations for the installed Fedora 44 libgusb 0.4 runtime.
 * The canonical builder uses this because libgusb-devel is absent from the host; the
 * production-shaped build still links the installed libgusb.so.2 and never
 * instantiates a USB context during validation.
 */
#ifndef GOODIX_PRODUCTION_GUSB_H
#define GOODIX_PRODUCTION_GUSB_H

#include <gio/gio.h>
#include <glib-object.h>

G_BEGIN_DECLS

typedef struct _GUsbContext GUsbContext;
typedef struct _GUsbDevice GUsbDevice;

typedef enum {
  G_USB_DEVICE_DIRECTION_HOST_TO_DEVICE = 0,
  G_USB_DEVICE_DIRECTION_DEVICE_TO_HOST = 1
} GUsbDeviceDirection;
typedef enum {
  G_USB_DEVICE_REQUEST_TYPE_STANDARD = 0,
  G_USB_DEVICE_REQUEST_TYPE_CLASS = 1,
  G_USB_DEVICE_REQUEST_TYPE_VENDOR = 2,
  G_USB_DEVICE_REQUEST_TYPE_RESERVED = 3
} GUsbDeviceRequestType;
typedef enum {
  G_USB_DEVICE_RECIPIENT_DEVICE = 0,
  G_USB_DEVICE_RECIPIENT_INTERFACE = 1,
  G_USB_DEVICE_RECIPIENT_ENDPOINT = 2,
  G_USB_DEVICE_RECIPIENT_OTHER = 3
} GUsbDeviceRecipient;
typedef enum {
  G_USB_DEVICE_CLAIM_INTERFACE_NONE = 0,
  G_USB_DEVICE_CLAIM_INTERFACE_BIND_KERNEL_DRIVER = 1 << 0
} GUsbDeviceClaimInterfaceFlags;
typedef enum {
  G_USB_DEVICE_ERROR_INTERNAL,
  G_USB_DEVICE_ERROR_IO,
  G_USB_DEVICE_ERROR_TIMED_OUT,
  G_USB_DEVICE_ERROR_NOT_SUPPORTED,
  G_USB_DEVICE_ERROR_NO_DEVICE,
  G_USB_DEVICE_ERROR_NOT_OPEN,
  G_USB_DEVICE_ERROR_ALREADY_OPEN,
  G_USB_DEVICE_ERROR_CANCELLED,
  G_USB_DEVICE_ERROR_FAILED
} GUsbDeviceError;

GType g_usb_context_get_type (void) G_GNUC_CONST;
GType g_usb_device_get_type (void) G_GNUC_CONST;
GQuark g_usb_device_error_quark (void);

#define G_USB_TYPE_CONTEXT (g_usb_context_get_type ())
#define G_USB_TYPE_DEVICE (g_usb_device_get_type ())
#define G_USB_DEVICE(obj) ((GUsbDevice *) (obj))
#define G_USB_DEVICE_ERROR (g_usb_device_error_quark ())

GUsbContext *g_usb_context_new (GError **error);
void g_usb_context_set_debug (GUsbContext *self, GLogLevelFlags flags);
void g_usb_context_enumerate (GUsbContext *self);
GPtrArray *g_usb_context_get_devices (GUsbContext *self);

guint16 g_usb_device_get_vid (GUsbDevice *self);
guint16 g_usb_device_get_pid (GUsbDevice *self);
guint8 g_usb_device_get_bus (GUsbDevice *self);
guint8 g_usb_device_get_address (GUsbDevice *self);
guint8 g_usb_device_get_port_number (GUsbDevice *self);
GUsbDevice *g_usb_device_get_parent (GUsbDevice *self);
gboolean g_usb_device_open (GUsbDevice *self, GError **error);
gboolean g_usb_device_close (GUsbDevice *self, GError **error);
gboolean g_usb_device_claim_interface (GUsbDevice *self, guint8 interface,
                                       GUsbDeviceClaimInterfaceFlags flags,
                                       GError **error);
gboolean g_usb_device_release_interface (GUsbDevice *self, guint8 interface,
                                         GUsbDeviceClaimInterfaceFlags flags,
                                         GError **error);

void g_usb_device_bulk_transfer_async (GUsbDevice *self, guint8 endpoint,
                                       guint8 *data, gsize length,
                                       guint timeout, GCancellable *cancellable,
                                       GAsyncReadyCallback callback,
                                       gpointer user_data);
gssize g_usb_device_bulk_transfer_finish (GUsbDevice *self, GAsyncResult *res,
                                          GError **error);
gboolean g_usb_device_bulk_transfer (GUsbDevice *self, guint8 endpoint,
                                     guint8 *data, gsize length,
                                     gsize *actual_length, guint timeout,
                                     GCancellable *cancellable, GError **error);
void g_usb_device_control_transfer_async (GUsbDevice *self,
                                          GUsbDeviceDirection direction,
                                          GUsbDeviceRequestType request_type,
                                          GUsbDeviceRecipient recipient,
                                          guint8 request, guint16 value,
                                          guint16 idx, guint8 *data,
                                          gsize length, guint timeout,
                                          GCancellable *cancellable,
                                          GAsyncReadyCallback callback,
                                          gpointer user_data);
gssize g_usb_device_control_transfer_finish (GUsbDevice *self,
                                             GAsyncResult *res,
                                             GError **error);
gboolean g_usb_device_control_transfer (GUsbDevice *self,
                                        GUsbDeviceDirection direction,
                                        GUsbDeviceRequestType request_type,
                                        GUsbDeviceRecipient recipient,
                                        guint8 request, guint16 value,
                                        guint16 idx, guint8 *data,
                                        gsize length, gsize *actual_length,
                                        guint timeout,
                                        GCancellable *cancellable,
                                        GError **error);
void g_usb_device_interrupt_transfer_async (GUsbDevice *self, guint8 endpoint,
                                            guint8 *data, gsize length,
                                            guint timeout,
                                            GCancellable *cancellable,
                                            GAsyncReadyCallback callback,
                                            gpointer user_data);
gssize g_usb_device_interrupt_transfer_finish (GUsbDevice *self,
                                               GAsyncResult *res,
                                               GError **error);
gboolean g_usb_device_interrupt_transfer (GUsbDevice *self, guint8 endpoint,
                                          guint8 *data, gsize length,
                                          gsize *actual_length, guint timeout,
                                          GCancellable *cancellable,
                                          GError **error);

G_DEFINE_AUTOPTR_CLEANUP_FUNC (GUsbContext, g_object_unref)
G_DEFINE_AUTOPTR_CLEANUP_FUNC (GUsbDevice, g_object_unref)

G_END_DECLS
#endif
