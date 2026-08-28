/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_USB_ROUTER_H
#define GOODIX_USB_ROUTER_H

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_USB_ROUTER_MAX_PAYLOAD (32768u)

typedef struct _GoodixUsbRouter GoodixUsbRouter;
/*
 * @frame is borrowed (transfer-none) for the duration of the callback.
 * The consumer must call g_bytes_ref() if it needs to retain the frame.
 */
typedef void (*GoodixUsbRouterFrameFunc) (guint8       outer_type,
                                          GBytes      *frame,
                                          gpointer     user_data);

GoodixUsbRouter *goodix_usb_router_new (GoodixUsbRouterFrameFunc a0_consumer,
                                        GoodixUsbRouterFrameFunc b0_consumer,
                                        gpointer                 user_data);
void             goodix_usb_router_free (GoodixUsbRouter *router);

/* Starts one activation-local receive generation. */
guint64  goodix_usb_router_begin_generation (GoodixUsbRouter *router);
gboolean goodix_usb_router_request_receive  (GoodixUsbRouter *router,
                                             GError         **error);

/* The sole physical receive completion entry point.  @data is borrowed. */
void goodix_usb_router_receive_complete (GoodixUsbRouter *router,
                                         guint64          generation,
                                         const guint8    *data,
                                         gsize            length,
                                         const GError    *transport_error);

/* Host-only cancellation: no device command or recovery is performed. */
void     goodix_usb_router_cancel   (GoodixUsbRouter *router);
gboolean goodix_usb_router_finalize (GoodixUsbRouter *router,
                                     GError         **error);

guint64       goodix_usb_router_get_generation        (GoodixUsbRouter *router);
gboolean      goodix_usb_router_get_terminal_fence    (GoodixUsbRouter *router);
const GError *goodix_usb_router_get_terminal_error    (GoodixUsbRouter *router);
guint         goodix_usb_router_get_outstanding       (GoodixUsbRouter *router);
guint         goodix_usb_router_get_max_outstanding   (GoodixUsbRouter *router);
guint         goodix_usb_router_get_receive_owner_count (GoodixUsbRouter *router);
guint64       goodix_usb_router_get_delivery_count    (GoodixUsbRouter *router);

G_END_DECLS

#endif
