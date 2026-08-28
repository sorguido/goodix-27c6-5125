/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Transport-agnostic A0/B0 receive router.
 *
 * Independently implemented from the neutral framing facts in the canonical
 * project manual and D276/01.  No GPL implementation source was consulted or
 * adapted.  The fourth outer-header byte and every payload byte are opaque to
 * this layer; protocol consumers, not the router, own inner semantics.
 */
#include "goodix_usb_router.h"

typedef enum
{
  GOODIX_USB_ROUTER_ERROR_MALFORMED,
  GOODIX_USB_ROUTER_ERROR_TRUNCATED,
  GOODIX_USB_ROUTER_ERROR_STATE,
  GOODIX_USB_ROUTER_ERROR_TRANSPORT,
} GoodixUsbRouterError;

#define GOODIX_USB_ROUTER_ERROR (goodix_usb_router_error_quark ())

struct _GoodixUsbRouter
{
  GByteArray *pending;
  GoodixUsbRouterFrameFunc a0_consumer;
  GoodixUsbRouterFrameFunc b0_consumer;
  gpointer user_data;
  guint64 generation;
  guint64 outstanding_generation;
  guint outstanding;
  guint max_outstanding;
  guint64 delivery_count;
  gboolean terminal_fence;
  GError *terminal_error;
};

static GQuark
goodix_usb_router_error_quark (void)
{
  return g_quark_from_static_string ("goodix-usb-router-error");
}

static void
router_fail (GoodixUsbRouter *router,
             GoodixUsbRouterError code,
             const gchar *message)
{
  if (router->terminal_error == NULL)
    router->terminal_error = g_error_new_literal (GOODIX_USB_ROUTER_ERROR,
                                                   code, message);
  router->terminal_fence = TRUE;
  router->outstanding = 0;
}

GoodixUsbRouter *
goodix_usb_router_new (GoodixUsbRouterFrameFunc a0_consumer,
                       GoodixUsbRouterFrameFunc b0_consumer,
                       gpointer user_data)
{
  GoodixUsbRouter *router = g_new0 (GoodixUsbRouter, 1);
  router->pending = g_byte_array_new ();
  router->a0_consumer = a0_consumer;
  router->b0_consumer = b0_consumer;
  router->user_data = user_data;
  return router;
}

void
goodix_usb_router_free (GoodixUsbRouter *router)
{
  if (router == NULL)
    return;
  g_byte_array_unref (router->pending);
  g_clear_error (&router->terminal_error);
  g_free (router);
}

void
goodix_usb_router_begin_generation (GoodixUsbRouter *router,
                                    guint64          generation)
{
  g_return_if_fail (router != NULL);
  g_return_if_fail (generation != 0);
  router->generation = generation;
  router->terminal_fence = FALSE;
  router->outstanding = 0;
  router->outstanding_generation = 0;
  g_byte_array_set_size (router->pending, 0);
  g_clear_error (&router->terminal_error);
}

gboolean
goodix_usb_router_request_receive (GoodixUsbRouter *router, GError **error)
{
  g_return_val_if_fail (router != NULL, FALSE);
  if (router->terminal_fence || router->generation == 0)
    {
      g_set_error_literal (error, GOODIX_USB_ROUTER_ERROR,
                           GOODIX_USB_ROUTER_ERROR_STATE,
                           "receive submission after terminal fence");
      return FALSE;
    }
  if (router->outstanding != 0)
    {
      g_set_error_literal (error, GOODIX_USB_ROUTER_ERROR,
                           GOODIX_USB_ROUTER_ERROR_STATE,
                           "second physical receive is forbidden");
      return FALSE;
    }
  router->outstanding = 1;
  router->outstanding_generation = router->generation;
  router->max_outstanding = MAX (router->max_outstanding,
                                 router->outstanding);
  return TRUE;
}

static gboolean
parse_pending (GoodixUsbRouter *router)
{
  while (router->pending->len >= 4)
    {
      const guint8 *header = router->pending->data;
      guint payload_length;
      gsize frame_length;
      GoodixUsbRouterFrameFunc consumer;
      guint8 outer_type;
      GBytes *frame;

      if (header[0] != 0xa0 && header[0] != 0xb0)
        {
          router_fail (router, GOODIX_USB_ROUTER_ERROR_MALFORMED,
                       "outer type is neither A0 nor B0");
          return FALSE;
        }
      payload_length = (guint) header[1] | ((guint) header[2] << 8);
      if (payload_length == 0 || payload_length > GOODIX_USB_ROUTER_MAX_PAYLOAD)
        {
          router_fail (router, GOODIX_USB_ROUTER_ERROR_MALFORMED,
                       "outer payload length is invalid");
          return FALSE;
        }
      frame_length = (gsize) payload_length + 4;
      if (router->pending->len < frame_length)
        return TRUE;

      outer_type = header[0];
      frame = g_bytes_new (router->pending->data, frame_length);
      consumer = outer_type == 0xa0 ? router->a0_consumer : router->b0_consumer;
      g_byte_array_remove_range (router->pending, 0, (guint) frame_length);
      router->delivery_count++;
      if (consumer != NULL)
        consumer (outer_type, frame, router->user_data);
      g_bytes_unref (frame);

      /* A consumer may synchronously cancel the generation. */
      if (router->terminal_fence)
        return FALSE;
    }
  return TRUE;
}

void
goodix_usb_router_receive_complete (GoodixUsbRouter *router,
                                    guint64 generation,
                                    const guint8 *data,
                                    gsize length,
                                    const GError *transport_error)
{
  g_return_if_fail (router != NULL);

  /* Stale callbacks never consume the current generation's receive token. */
  if (generation != router->generation ||
      generation != router->outstanding_generation)
    return;
  if (router->terminal_fence || router->outstanding != 1)
    return;

  router->outstanding = 0;
  router->outstanding_generation = 0;
  if (transport_error != NULL)
    {
      router_fail (router, GOODIX_USB_ROUTER_ERROR_TRANSPORT,
                   transport_error->message);
      return;
    }
  if (length > G_MAXUINT)
    {
      router_fail (router, GOODIX_USB_ROUTER_ERROR_MALFORMED,
                   "receive completion exceeds host buffer bound");
      return;
    }
  if (length != 0 && data == NULL)
    {
      router_fail (router, GOODIX_USB_ROUTER_ERROR_MALFORMED,
                   "non-empty completion has no bytes");
      return;
    }
  if (length != 0)
    g_byte_array_append (router->pending, data, (guint) length);
  parse_pending (router);
}

void
goodix_usb_router_cancel (GoodixUsbRouter *router)
{
  g_return_if_fail (router != NULL);
  router->terminal_fence = TRUE;
  router->outstanding = 0;
  router->outstanding_generation = 0;
  g_byte_array_set_size (router->pending, 0);
}

gboolean
goodix_usb_router_finalize (GoodixUsbRouter *router, GError **error)
{
  g_return_val_if_fail (router != NULL, FALSE);
  if (!router->terminal_fence && router->pending->len != 0)
    router_fail (router, GOODIX_USB_ROUTER_ERROR_TRUNCATED,
                 "stream ended with a truncated frame");
  if (router->terminal_error != NULL)
    {
      if (error != NULL)
        *error = g_error_copy (router->terminal_error);
      return FALSE;
    }
  return TRUE;
}

guint64 goodix_usb_router_get_generation (GoodixUsbRouter *r) { return r->generation; }
gboolean goodix_usb_router_get_terminal_fence (GoodixUsbRouter *r) { return r->terminal_fence; }
const GError *goodix_usb_router_get_terminal_error (GoodixUsbRouter *r) { return r->terminal_error; }
guint goodix_usb_router_get_outstanding (GoodixUsbRouter *r) { return r->outstanding; }
guint goodix_usb_router_get_max_outstanding (GoodixUsbRouter *r) { return r->max_outstanding; }
guint goodix_usb_router_get_receive_owner_count (GoodixUsbRouter *r) { (void) r; return 1; }
guint64 goodix_usb_router_get_delivery_count (GoodixUsbRouter *r) { return r->delivery_count; }
