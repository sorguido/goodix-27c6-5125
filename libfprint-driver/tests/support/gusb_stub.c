/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Stub implementations for the few GUsb symbols that are referenced by the
 * repository-local libfprint copy.  The host-only test harness never reaches
 * these functions; they exist only to satisfy the linker when --gc-sections
 * does not remove the containing libfprint object code.
 */
#include "gusb.h"

#include <glib.h>
#include <gio/gio.h>

static guint open_count;
static guint close_count;
static gboolean open_success;
static gboolean close_success;

GType
g_usb_device_get_type (void)
{
  return G_TYPE_OBJECT;
}

GQuark
g_usb_device_error_quark (void)
{
  return g_quark_from_static_string ("g-usb-device-error-quark");
}

void
goodix_test_gusb_reset_counts (void)
{
  open_count = 0;
  close_count = 0;
  open_success = FALSE;
  close_success = FALSE;
}

void
goodix_test_gusb_set_open_close_success (gboolean value)
{
  open_success = value;
  close_success = value;
}

guint
goodix_test_gusb_get_open_count (void)
{
  return open_count;
}

guint
goodix_test_gusb_get_close_count (void)
{
  return close_count;
}

gboolean
g_usb_device_open (GUsbDevice  *self,
                   GError     **error)
{
  open_count++;
  (void) self;
  if (open_success)
    return TRUE;
  if (error)
    g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
                         "g_usb_device_open: host-only stub");
  return FALSE;
}

gboolean
g_usb_device_close (GUsbDevice  *self,
                    GError     **error)
{
  close_count++;
  (void) self;
  if (close_success)
    return TRUE;
  if (error)
    g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
                         "g_usb_device_close: host-only stub");
  return FALSE;
}

gboolean
g_usb_device_claim_interface (GUsbDevice                    *self,
                              guint8                         interface_number,
                              GUsbDeviceClaimInterfaceFlags  flags,
                              GError                       **error)
{
  (void) self;
  (void) interface_number;
  (void) flags;
  if (error)
    g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
                         "g_usb_device_claim_interface: host-only stub");
  return FALSE;
}

gboolean
g_usb_device_release_interface (GUsbDevice                    *self,
                                guint8                         interface_number,
                                GUsbDeviceClaimInterfaceFlags  flags,
                                GError                       **error)
{
  (void) self;
  (void) interface_number;
  (void) flags;
  if (error)
    g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED,
                         "g_usb_device_release_interface: host-only stub");
  return FALSE;
}

guint8
g_usb_device_get_bus (GUsbDevice *self)
{
  (void) self;
  return 0;
}

GUsbDevice *
g_usb_device_get_parent (GUsbDevice *self)
{
  (void) self;
  return NULL;
}

guint8
g_usb_device_get_port_number (GUsbDevice *self)
{
  (void) self;
  return 0;
}
