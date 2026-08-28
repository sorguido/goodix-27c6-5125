/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_usb_router.h"

typedef struct
{
  GPtrArray *frames;
  GByteArray *types;
  guint cancel_on_delivery;
  GoodixUsbRouter *router;
} Recorder;

static GBytes *
make_frame (guint8 type, guint8 marker, gsize payload_length)
{
  GByteArray *bytes = g_byte_array_sized_new ((guint) payload_length + 4);
  guint8 header[4] = { type, (guint8) payload_length,
                       (guint8) (payload_length >> 8), 0x5a };
  g_byte_array_append (bytes, header, sizeof header);
  for (gsize i = 0; i < payload_length; i++)
    {
      guint8 byte = i == 0 ? marker : (guint8) i;
      g_byte_array_append (bytes, &byte, 1);
    }
  return g_byte_array_free_to_bytes (bytes);
}

static void
record_frame (guint8 type, GBytes *frame, gpointer user_data)
{
  Recorder *recorder = user_data;
  g_ptr_array_add (recorder->frames, g_bytes_ref (frame));
  g_byte_array_append (recorder->types, &type, 1);
  if (recorder->cancel_on_delivery == recorder->frames->len)
    goodix_usb_router_cancel (recorder->router);
}

static void
recorder_init (Recorder *recorder)
{
  recorder->frames = g_ptr_array_new_with_free_func ((GDestroyNotify) g_bytes_unref);
  recorder->types = g_byte_array_new ();
  recorder->router = goodix_usb_router_new (record_frame, record_frame, recorder);
}

static void
recorder_clear (Recorder *recorder)
{
  goodix_usb_router_free (recorder->router);
  g_ptr_array_unref (recorder->frames);
  g_byte_array_unref (recorder->types);
}

static void
feed (Recorder *recorder, guint64 generation, const guint8 *data, gsize length)
{
  g_autoptr(GError) error = NULL;
  g_assert_true (goodix_usb_router_request_receive (recorder->router, &error));
  g_assert_no_error (error);
  goodix_usb_router_receive_complete (recorder->router, generation,
                                      data, length, NULL);
}

static void
test_incremental_and_concatenated (void)
{
  Recorder r = { 0 };
  g_autoptr(GBytes) a0 = make_frame (0xa0, 0x01, 7);
  g_autoptr(GBytes) b0 = make_frame (0xb0, 0x17, 9);
  g_autoptr(GByteArray) stream = g_byte_array_new ();
  gsize a_len, b_len;
  const guint8 *a = g_bytes_get_data (a0, &a_len);
  const guint8 *b = g_bytes_get_data (b0, &b_len);
  guint64 generation;

  recorder_init (&r);
  generation = goodix_usb_router_begin_generation (r.router);
  /* Both headers and both bodies cross arbitrary receive boundaries. */
  feed (&r, generation, a, 1);
  feed (&r, generation, a + 1, 2);
  feed (&r, generation, a + 3, 5);
  g_byte_array_append (stream, a + 8, (guint) (a_len - 8));
  g_byte_array_append (stream, b, (guint) b_len);
  feed (&r, generation, stream->data, stream->len);

  g_assert_cmpuint (r.frames->len, ==, 2);
  g_assert_cmpmem (g_bytes_get_data (g_ptr_array_index (r.frames, 0), NULL),
                   a_len, a, a_len);
  g_assert_cmpmem (g_bytes_get_data (g_ptr_array_index (r.frames, 1), NULL),
                   b_len, b, b_len);
  g_assert_cmpuint (goodix_usb_router_get_delivery_count (r.router), ==, 2);
  recorder_clear (&r);
}

static void
test_synthetic_demux_order (void)
{
  /* Markers denote synthetic ACK, IRQ2, IRQ0200, NAV, and opaque B0. */
  const guint8 types[] = { 0xa0, 0xa0, 0xb0, 0xa0, 0xa0 };
  const guint8 markers[] = { 0x07, 0x02, 0x17, 0x20, 0x50 };
  Recorder r = { 0 };
  g_autoptr(GByteArray) all = g_byte_array_new ();
  guint64 generation;

  recorder_init (&r);
  generation = goodix_usb_router_begin_generation (r.router);
  for (guint i = 0; i < G_N_ELEMENTS (types); i++)
    {
      g_autoptr(GBytes) frame = make_frame (types[i], markers[i], i + 1);
      gsize length;
      const guint8 *data = g_bytes_get_data (frame, &length);
      g_byte_array_append (all, data, (guint) length);
    }
  feed (&r, generation, all->data, all->len);
  g_assert_cmpuint (r.frames->len, ==, G_N_ELEMENTS (types));
  g_assert_cmpmem (r.types->data, r.types->len, types, sizeof types);
  for (guint i = 0; i < r.frames->len; i++)
    {
      gsize length;
      const guint8 *data = g_bytes_get_data (g_ptr_array_index (r.frames, i),
                                             &length);
      g_assert_cmpuint (length, >=, 5);
      g_assert_cmpuint (data[4], ==, markers[i]);
    }
  recorder_clear (&r);
}

static void
test_single_reader_contract (void)
{
  Recorder r = { 0 };
  g_autoptr(GError) error = NULL;
  recorder_init (&r);
  goodix_usb_router_begin_generation (r.router);
  g_assert_true (goodix_usb_router_request_receive (r.router, &error));
  g_assert_false (goodix_usb_router_request_receive (r.router, &error));
  g_assert_error (error, g_quark_from_static_string ("goodix-usb-router-error"), 2);
  g_assert_cmpuint (goodix_usb_router_get_receive_owner_count (r.router), ==, 1);
  g_assert_cmpuint (goodix_usb_router_get_max_outstanding (r.router), ==, 1);
  g_assert_cmpuint (goodix_usb_router_get_outstanding (r.router), ==, 1);
  recorder_clear (&r);
}

static void
test_stale_generation (void)
{
  Recorder r = { 0 };
  g_autoptr(GBytes) frame = make_frame (0xa0, 0x02, 2);
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);
  guint64 old_generation, generation;
  g_autoptr(GError) error = NULL;

  recorder_init (&r);
  old_generation = goodix_usb_router_begin_generation (r.router);
  generation = goodix_usb_router_begin_generation (r.router);
  g_assert_true (goodix_usb_router_request_receive (r.router, &error));
  goodix_usb_router_receive_complete (r.router, old_generation, data, length, NULL);
  g_assert_cmpuint (r.frames->len, ==, 0);
  g_assert_cmpuint (goodix_usb_router_get_outstanding (r.router), ==, 1);
  goodix_usb_router_receive_complete (r.router, generation, data, length, NULL);
  g_assert_cmpuint (r.frames->len, ==, 1);
  recorder_clear (&r);
}

static void
test_cancel_and_callback_fence (void)
{
  Recorder r = { 0 };
  g_autoptr(GBytes) frame = make_frame (0xb0, 0x17, 4);
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);
  guint64 generation;
  g_autoptr(GError) error = NULL;

  recorder_init (&r);
  generation = goodix_usb_router_begin_generation (r.router);
  g_assert_true (goodix_usb_router_request_receive (r.router, &error));
  goodix_usb_router_cancel (r.router);
  goodix_usb_router_receive_complete (r.router, generation, data, length, NULL);
  g_assert_cmpuint (r.frames->len, ==, 0);
  g_assert_cmpuint (goodix_usb_router_get_outstanding (r.router), ==, 0);
  g_assert_true (goodix_usb_router_get_terminal_fence (r.router));
  g_clear_error (&error);
  g_assert_false (goodix_usb_router_request_receive (r.router, &error));
  recorder_clear (&r);
}

static void
test_consumer_cancel_stops_coalesced_delivery (void)
{
  Recorder r = { 0 };
  g_autoptr(GBytes) first = make_frame (0xa0, 1, 1);
  g_autoptr(GBytes) second = make_frame (0xb0, 2, 1);
  g_autoptr(GByteArray) all = g_byte_array_new ();
  gsize length;
  const guint8 *data;

  recorder_init (&r);
  r.cancel_on_delivery = 1;
  data = g_bytes_get_data (first, &length);
  g_byte_array_append (all, data, (guint) length);
  data = g_bytes_get_data (second, &length);
  g_byte_array_append (all, data, (guint) length);
  feed (&r, goodix_usb_router_begin_generation (r.router), all->data, all->len);
  g_assert_cmpuint (r.frames->len, ==, 1);
  recorder_clear (&r);
}

static void
assert_terminal_for (const guint8 *bytes, gsize length)
{
  Recorder r = { 0 };
  guint64 generation;
  recorder_init (&r);
  generation = goodix_usb_router_begin_generation (r.router);
  feed (&r, generation, bytes, length);
  g_assert_true (goodix_usb_router_get_terminal_fence (r.router));
  g_assert_nonnull (goodix_usb_router_get_terminal_error (r.router));
  g_assert_cmpuint (r.frames->len, ==, 0);
  recorder_clear (&r);
}

static void
test_malformed_fail_closed (void)
{
  const guint8 bad_type[] = { 0xc0, 1, 0, 0, 1 };
  const guint8 zero_length[] = { 0xa0, 0, 0, 0 };
  const guint8 oversized[] = { 0xb0, 0xff, 0xff, 0 };
  assert_terminal_for (bad_type, sizeof bad_type);
  assert_terminal_for (zero_length, sizeof zero_length);
  assert_terminal_for (oversized, sizeof oversized);
}

static void
test_truncated_finalize (void)
{
  const guint8 partial[] = { 0xa0, 4, 0, 0, 1 };
  Recorder r = { 0 };
  g_autoptr(GError) error = NULL;
  recorder_init (&r);
  feed (&r, goodix_usb_router_begin_generation (r.router),
        partial, sizeof partial);
  g_assert_false (goodix_usb_router_finalize (r.router, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_usb_router_get_terminal_fence (r.router));
  recorder_clear (&r);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/goodix/router/incremental-concatenated", test_incremental_and_concatenated);
  g_test_add_func ("/goodix/router/synthetic-demux-order", test_synthetic_demux_order);
  g_test_add_func ("/goodix/router/single-reader", test_single_reader_contract);
  g_test_add_func ("/goodix/router/stale-generation", test_stale_generation);
  g_test_add_func ("/goodix/router/cancel-fence", test_cancel_and_callback_fence);
  g_test_add_func ("/goodix/router/consumer-cancel", test_consumer_cancel_stops_coalesced_delivery);
  g_test_add_func ("/goodix/router/malformed", test_malformed_fail_closed);
  g_test_add_func ("/goodix/router/truncated", test_truncated_finalize);
  return g_test_run ();
}
