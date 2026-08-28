/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Minimal compile-time seam for the repository-local libfprint copy when
 * libfprint private headers are compiled without a real libgusb installation.
 * No runtime USB operation is performed by the host-only fake backend.
 */
#ifndef GUSB_H
#define GUSB_H

#include <glib-object.h>

G_BEGIN_DECLS

typedef struct _GUsbDevice GUsbDevice;
typedef enum { G_USB_DEVICE_DIRECTION_HOST_TO_DEVICE, G_USB_DEVICE_DIRECTION_DEVICE_TO_HOST } GUsbDeviceDirection;
typedef enum { G_USB_DEVICE_REQUEST_TYPE_STANDARD, G_USB_DEVICE_REQUEST_TYPE_CLASS, G_USB_DEVICE_REQUEST_TYPE_VENDOR } GUsbDeviceRequestType;
typedef enum { G_USB_DEVICE_RECIPIENT_DEVICE, G_USB_DEVICE_RECIPIENT_INTERFACE, G_USB_DEVICE_RECIPIENT_ENDPOINT, G_USB_DEVICE_RECIPIENT_OTHER } GUsbDeviceRecipient;

#define G_USB_TYPE_DEVICE G_TYPE_OBJECT

G_DEFINE_AUTOPTR_CLEANUP_FUNC (GUsbDevice, g_object_unref)

gboolean g_usb_device_open  (GUsbDevice  *self, GError **error);
gboolean g_usb_device_close (GUsbDevice  *self, GError **error);
guint8   g_usb_device_get_bus (GUsbDevice *self);
GUsbDevice *g_usb_device_get_parent (GUsbDevice *self);
guint8   g_usb_device_get_port_number (GUsbDevice *self);

G_END_DECLS

#endif
