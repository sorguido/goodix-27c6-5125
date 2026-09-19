/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Deterministic host-only tests for the D278/12 post-TLS lifecycle. */
#include "goodix_a0_protocol.h"
#include "goodix_post_tls_lifecycle.h"
#include "goodix_usb_router.h"

#include <string.h>

typedef struct
{
  guint64 generation;
  GBytes *bytes;
} Submission;

typedef struct
{
  GoodixUsbRouter *router;
  GoodixFpiUsbBackend *backend;
  GoodixPostTlsLifecycle *lifecycle;
  GoodixPostTlsAudit audit;
  GoodixPostTlsMaterial material;
  GQueue *out;
  guint in_submit_count;
  guint terminal_count;
  guint finger_down_count;
  guint release_tail_count;
  guint finger_up_count;
  guint image_count;
  guint handoff_count;
  guint new_owner_completion_count;
  gboolean handoff_should_fail;
  gboolean stop_before_finger;
  guint16 baseline_flags;
  gboolean response_before_ack;
  gboolean stop_before_82;
  guint reverse_events;
  guint64 generation;
  uint16_t expected[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  guint8 expected_up[12];
  guint8 expected_down[12];
} Fixture;

static void
submission_free (Submission *submission)
{
  if (submission == NULL)
    return;
  g_bytes_unref (submission->bytes);
  g_free (submission);
}

static void
a0_consumer (guint8   type,
             GBytes  *frame,
             gpointer user_data)
{
  Fixture *fixture = user_data;
  g_assert_cmphex (type, ==, 0xa0);
  goodix_post_tls_lifecycle_handle_a0 (fixture->lifecycle, frame);
}

static void
b0_consumer (guint8   type,
             GBytes  *frame,
             gpointer user_data)
{
  (void) frame;
  (void) user_data;
  g_assert_cmphex (type, ==, 0xb0);
  g_assert_not_reached ();
}

static void
submit_seam (GoodixFpiUsbBackend *backend,
             GoodixUsbDirection   direction,
             guint64              generation,
             GBytes              *bytes,
             gpointer             user_data)
{
  Fixture *fixture = user_data;

  (void) backend;
  g_assert_cmpuint (generation, ==, fixture->generation);
  if (direction == GOODIX_USB_TRANSFER_IN)
    {
      fixture->in_submit_count++;
      g_assert_null (bytes);
      return;
    }
  Submission *submission = g_new0 (Submission, 1);
  submission->generation = generation;
  submission->bytes = g_bytes_ref (bytes);
  g_queue_push_tail (fixture->out, submission);
}

static gboolean
image_callback (GoodixPostTlsLifecycle *lifecycle,
                guint                   acquisition_index,
                const uint16_t          samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT],
                gpointer                user_data,
                GError                **error)
{
  Fixture *fixture = user_data;

  (void) lifecycle;
  (void) error;
  g_assert_cmpuint (acquisition_index, ==, fixture->image_count + 1u);
  g_assert_true (memcmp (samples, fixture->expected,
                         sizeof fixture->expected) == 0);
  fixture->image_count++;
  return TRUE;
}

static void
finger_down_callback (GoodixPostTlsLifecycle *lifecycle,
                      gpointer                user_data)
{
  (void) lifecycle;
  ((Fixture *) user_data)->finger_down_count++;
}

static void
release_tail_callback (GoodixPostTlsLifecycle *lifecycle,
                       gpointer                user_data)
{
  (void) lifecycle;
  ((Fixture *) user_data)->release_tail_count++;
}

static void
finger_up_callback (GoodixPostTlsLifecycle *lifecycle,
                    gpointer                user_data)
{
  (void) lifecycle;
  ((Fixture *) user_data)->finger_up_count++;
}

static void
terminal_callback (GoodixPostTlsLifecycle *lifecycle,
                   const GError           *error,
                   gpointer                user_data)
{
  (void) lifecycle;
  g_assert_nonnull (error);
  ((Fixture *) user_data)->terminal_count++;
}

static void
new_owner_out_complete (GoodixFpiUsbBackend *backend,
                        guint64               generation,
                        const GError         *error,
                        gpointer              user_data)
{
  Fixture *fixture = user_data;

  (void) backend;
  g_assert_cmpuint (generation, ==, fixture->generation);
  g_assert_null (error);
  fixture->new_owner_completion_count++;
}

static gboolean
first_arm_handoff_callback (GoodixPostTlsLifecycle *lifecycle,
                            GoodixFpiUsbBackend    *backend,
                            guint64                 generation,
                            gpointer                user_data,
                            GError                **error)
{
  Fixture *fixture = user_data;

  (void) lifecycle;
  (void) error;
  g_assert_true (backend == fixture->backend);
  g_assert_cmpuint (generation, ==, fixture->generation);
  g_assert_true (goodix_fpi_usb_backend_is_drained (backend));
  fixture->handoff_count++;
  if (fixture->handoff_should_fail)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                           "synthetic handoff rejection");
      return FALSE;
    }
  goodix_fpi_usb_backend_set_out_completed_callback (
    backend, new_owner_out_complete, fixture);
  return TRUE;
}

static Fixture *
fixture_new_for_profile (GoodixPostTlsCaptureProfile capture_profile)
{
  Fixture *fixture = g_new0 (Fixture, 1);
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GError) error = NULL;

  fixture->generation = 23;
  fixture->out = g_queue_new ();
  for (guint i = 0; i < 6u; i++)
    {
      fixture->material.initial_fdt_table[i * 2u] = 0x80;
      fixture->material.initial_fdt_table[i * 2u + 1u] =
        (guint8) (0x40u + i);
      fixture->expected_up[i * 2u] = 0x80;
      fixture->expected_up[i * 2u + 1u] = (guint8) (0xc0u + 0x1du + i);
      fixture->expected_down[i * 2u] = 0x80;
      fixture->expected_down[i * 2u + 1u] = (guint8) (0x90u + i);
    }
  fixture->material.af_timestamp = 0x1234;
  fixture->material.first_arm_timestamp = 0x2345;
  fixture->material.second_arm_timestamp = 0x3456;
  fixture->material.capture_profile = capture_profile;
  for (gsize i = 0; i < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT; i++)
    fixture->expected[i] = (uint16_t) (i & 0x0fffu);
  fixture->router = goodix_usb_router_new (a0_consumer, b0_consumer, fixture);
  goodix_usb_router_begin_generation (fixture->router, fixture->generation);
  fixture->backend = goodix_fpi_usb_backend_new (NULL, fixture->router,
                                                  0x81, 0x01, 32768);
  goodix_fpi_usb_backend_set_async_submit_seam (fixture->backend,
                                                 submit_seam, fixture);
  g_assert_true (goodix_fpi_usb_backend_begin_generation (
    fixture->backend, fixture->generation, cancellable, &error));
  g_assert_no_error (error);
  fixture->lifecycle = goodix_post_tls_lifecycle_new (
    fixture->backend, fixture->generation, &fixture->material, image_callback,
    finger_down_callback, release_tail_callback, finger_up_callback,
    terminal_callback, fixture, &fixture->audit, &error);
  g_assert_nonnull (fixture->lifecycle);
  g_assert_no_error (error);
  return fixture;
}

static Fixture *
fixture_new (void)
{
  return fixture_new_for_profile (
    GOODIX_POST_TLS_CAPTURE_PROFILE_TWO_ACQUISITION);
}

static void
fixture_free (Fixture *fixture)
{
  if (fixture == NULL)
    return;
  while (!g_queue_is_empty (fixture->out))
    submission_free (g_queue_pop_head (fixture->out));
  if (!goodix_fpi_usb_backend_is_drained (fixture->backend))
    {
      if (goodix_fpi_usb_backend_get_out_outstanding (fixture->backend) != 0)
        goodix_fpi_usb_backend_complete_out (fixture->backend,
                                             fixture->generation, NULL);
      if (goodix_fpi_usb_backend_get_outstanding (fixture->backend) != 0)
        goodix_fpi_usb_backend_complete_receive (fixture->backend,
                                                 fixture->generation,
                                                 NULL, 0, NULL);
    }
  goodix_post_tls_lifecycle_free (fixture->lifecycle);
  goodix_fpi_usb_backend_free (fixture->backend);
  goodix_usb_router_free (fixture->router);
  g_queue_free (fixture->out);
  g_free (fixture);
}

static GBytes *
build_response (guint8        control,
                const guint8 *body,
                gsize         body_length)
{
  g_autoptr(GError) error = NULL;
  GBytes *frame = goodix_a0_build_frame (control, control, body, body_length,
                                         &error);
  g_assert_no_error (error);
  g_assert_nonnull (frame);
  return frame;
}

static GBytes *
build_nav_no_check (const guint8 *body,
                    gsize         body_length)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) additive = NULL;
  const guint8 *data;
  guint8 *copy;
  gsize length;

  g_assert_cmpuint (body_length, ==, 2409u);
  g_assert_cmphex (body[0], ==, 0x50);
  g_assert_cmphex (body[1], ==, 0x01);

  additive = goodix_a0_build_frame (0x50, 0x50, body, body_length, &error);
  g_assert_no_error (error);
  g_assert_nonnull (additive);

  data = g_bytes_get_data (additive, &length);
  g_assert_cmpuint (length, ==, 2417u);

  copy = g_malloc (length);
  memcpy (copy, data, length);
  copy[length - 1u] = 0x88;

  return g_bytes_new_take (copy, length);
}

static GBytes *
build_ack (guint8 control)
{
  const guint8 body[2] = { control, 0x01 };
  return build_response (0xb0, body, sizeof body);
}

static GBytes *
build_event (guint8  control,
             guint16 irq,
             guint16 flags,
             guint16 base)
{
  guint8 body[16];

  body[0] = (guint8) irq;
  body[1] = (guint8) (irq >> 8);
  body[2] = (guint8) flags;
  body[3] = (guint8) (flags >> 8);
  for (guint i = 0; i < 6u; i++)
    {
      guint16 word = (guint16) (base + i * 2u);
      body[4u + i * 2u] = (guint8) word;
      body[5u + i * 2u] = (guint8) (word >> 8);
    }
  return build_response (control, body, sizeof body);
}

static void
feed_bytes (Fixture      *fixture,
            const guint8 *bytes,
            gsize         length,
            guint         fragmentation)
{
  gsize offset = 0;
  static const gsize chunks[] = { 1u, 2u, 5u, 11u, 23u };

  while (offset < length)
    {
      g_autoptr(GError) error = NULL;
      gsize chunk = length - offset;
      if (fragmentation != 0)
        chunk = MIN (chunk, chunks[(offset + fragmentation) %
                                   G_N_ELEMENTS (chunks)]);
      g_assert_true (goodix_fpi_usb_backend_arm_receive (
        fixture->backend, fixture->generation, &error));
      g_assert_no_error (error);
      goodix_fpi_usb_backend_complete_receive (
        fixture->backend, fixture->generation, bytes + offset, chunk, NULL);
      offset += chunk;
    }
}

static void
feed_frame (Fixture *fixture,
            GBytes  *frame,
            guint    fragmentation)
{
  gsize length;
  const guint8 *bytes = g_bytes_get_data (frame, &length);
  feed_bytes (fixture, bytes, length, fragmentation);
}

static void
feed_pair (Fixture *fixture,
           GBytes  *first,
           GBytes  *second,
           guint    fragmentation)
{
  gsize first_length;
  gsize second_length;
  const guint8 *first_bytes = g_bytes_get_data (first, &first_length);
  const guint8 *second_bytes = g_bytes_get_data (second, &second_length);
  g_autoptr(GByteArray) combined = g_byte_array_sized_new (
    (guint) (first_length + second_length));
  g_byte_array_append (combined, first_bytes, (guint) first_length);
  g_byte_array_append (combined, second_bytes, (guint) second_length);
  feed_bytes (fixture, combined->data, combined->len, fragmentation);
}

static void
complete_command (Fixture      *fixture,
                  guint8        expected_control,
                  const guint8 *expected_tail,
                  gsize         expected_tail_length)
{
  Submission *submission = g_queue_pop_head (fixture->out);
  GoodixA0Message message = { 0 };
  g_autoptr(GError) error = NULL;
  gsize physical_length;
  gsize body_length;
  const guint8 *physical;
  const guint8 *body;
  guint16 payload_length;
  gsize logical_length;

  g_assert_nonnull (submission);
  physical = g_bytes_get_data (submission->bytes, &physical_length);
  g_assert_cmpuint (physical_length, ==, 64u);
  payload_length = (guint16) physical[1] | ((guint16) physical[2] << 8);
  logical_length = (gsize) payload_length + 4u;
  for (gsize i = logical_length; i < physical_length; i++)
    g_assert_cmphex (physical[i], ==, 0);
  g_autoptr(GBytes) logical = g_bytes_new (physical, logical_length);
  g_assert_true (goodix_a0_parse_frame (
    logical, (guint8) (expected_control & 0xfeu), &message, &error));
  g_assert_no_error (error);
  g_assert_cmphex (message.control, ==, expected_control);
  body = g_bytes_get_data (message.body, &body_length);
  if (expected_tail != NULL)
    {
      g_assert_cmpuint (body_length, ==, expected_tail_length);
      g_assert_true (memcmp (body, expected_tail, body_length) == 0);
    }
  goodix_a0_message_clear (&message);
  goodix_fpi_usb_backend_complete_out (fixture->backend,
                                       submission->generation, NULL);
  submission_free (submission);
}

static guint32
test_crc32_mpeg2 (const guint8 *data,
                  gsize         length)
{
  guint32 crc = UINT32_C (0xffffffff);
  for (gsize i = 0; i < length; i++)
    {
      crc ^= (guint32) data[i] << 24;
      for (guint bit = 0; bit < 8u; bit++)
        crc = (crc & UINT32_C (0x80000000)) != 0 ?
          (crc << 1) ^ UINT32_C (0x04c11db7) : crc << 1;
    }
  return crc;
}

static GBytes *
build_image (Fixture *fixture)
{
  g_autoptr(GByteArray) bytes = g_byte_array_sized_new (
    GOODIX_IMAGE_PLAINTEXT_LENGTH);
  guint8 header[3] = { 0x20, 0x0a, 0x1e };
  guint8 prefix[5] = { 0 };
  guint8 packed[GOODIX_IMAGE_PACKED_LENGTH];
  guint32 crc;
  guint8 trailer[4];
  guint8 no_check = 0x88;

  g_byte_array_append (bytes, header, sizeof header);
  g_byte_array_append (bytes, prefix, sizeof prefix);
  memset (packed, 0, sizeof packed);
  for (gsize wire = 0; wire < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT;
       wire += 4u)
    {
      uint16_t value[4];
      for (gsize item = 0; item < 4u; item++)
        {
          gsize index = wire + item;
          gsize raster = (index % GOODIX_CANONICAL_IMAGE_HEIGHT) *
                           GOODIX_CANONICAL_IMAGE_WIDTH +
                         index / GOODIX_CANONICAL_IMAGE_HEIGHT;
          value[item] = fixture->expected[raster];
        }
      gsize offset = (wire / 4u) * 6u;
      packed[offset] = (guint8) (((value[1] & 0x0fu) << 4) |
                                  (value[0] >> 8));
      packed[offset + 1u] = (guint8) value[0];
      packed[offset + 2u] = (guint8) value[2];
      packed[offset + 3u] = (guint8) (value[1] >> 4);
      packed[offset + 4u] = (guint8) (value[3] >> 4);
      packed[offset + 5u] = (guint8) (((value[3] & 0x0fu) << 4) |
                                      (value[2] >> 8));
    }
  crc = test_crc32_mpeg2 (packed, sizeof packed);
  trailer[0] = (guint8) (crc >> 8);
  trailer[1] = (guint8) crc;
  trailer[2] = (guint8) (crc >> 24);
  trailer[3] = (guint8) (crc >> 16);
  g_byte_array_append (bytes, packed, sizeof packed);
  g_byte_array_append (bytes, trailer, sizeof trailer);
  g_byte_array_append (bytes, &no_check, 1u);
  g_assert_cmpuint (bytes->len, ==, GOODIX_IMAGE_PLAINTEXT_LENGTH);
  return g_byte_array_free_to_bytes (g_steal_pointer (&bytes));
}

static void
run_full_trace (Fixture *fixture,
                guint    fragmentation)
{
  static const guint8 d4[] = { 0x00, 0x00 };
  static const guint8 cmd01[] = { 0x01, 0x00 };
  guint8 af[16] = { 0 };
  guint8 typed82[2] = { 0x00, 0x20 };
  guint8 nav[2409] = { 0 };
  g_autoptr(GBytes) image = build_image (fixture);
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GBytes) typed = NULL;
  g_autoptr(GBytes) event = NULL;
  g_autoptr(GBytes) auxiliary = g_bytes_new_static ("aux", 3u);
  g_autoptr(GError) error = NULL;

  nav[0] = 0x50;
  nav[1] = 0x01;

  g_assert_true (goodix_post_tls_lifecycle_start (fixture->lifecycle, &error));
  g_assert_no_error (error);
  complete_command (fixture, 0xd4, d4, sizeof d4);
  ack = build_ack (0xd4);
  feed_frame (fixture, ack, fragmentation);

  {
    const guint8 af_request[] = { 0x55, 0x34, 0x12, 0x00, 0x00 };
    complete_command (fixture, 0xaf, af_request, sizeof af_request);
  }
  af[1] = 0x02;
  g_clear_pointer (&typed, g_bytes_unref);
  typed = build_response (0xae, af, sizeof af);
  feed_frame (fixture, typed, fragmentation);

  for (guint fdt_index = 0; fdt_index < 3u; fdt_index++)
    {
      complete_command (fixture, 0x36, NULL, 0);
      g_clear_pointer (&ack, g_bytes_unref);
      ack = build_ack (0x36);
      feed_frame (fixture, ack, fragmentation);
      g_clear_pointer (&event, g_bytes_unref);
      event = build_event (0x36, 0x0100, fixture->baseline_flags,
                           (guint16) (0x0300u + fdt_index * 0x20u));
      feed_frame (fixture, event, fragmentation);
      if (fdt_index == 0)
        {
          complete_command (fixture, 0x50, cmd01, sizeof cmd01);
          g_clear_pointer (&ack, g_bytes_unref);
          ack = build_ack (0x50);
          g_clear_pointer (&typed, g_bytes_unref);
          typed = build_nav_no_check (nav, sizeof nav);
          feed_pair (fixture, ack, typed, fragmentation);
        }
      else if (fdt_index == 1)
        {
          complete_command (fixture, 0x82, NULL, 0);
          if (fixture->stop_before_82)
            return;
          g_clear_pointer (&ack, g_bytes_unref);
          ack = build_ack (0x82);
          g_clear_pointer (&typed, g_bytes_unref);
          typed = build_response (0x82, typed82, sizeof typed82);
          if (fixture->response_before_ack)
            feed_pair (fixture, typed, ack, fragmentation);
          else
            feed_pair (fixture, ack, typed, fragmentation);
          complete_command (fixture, 0x20, cmd01, sizeof cmd01);
          g_clear_pointer (&ack, g_bytes_unref);
          ack = build_ack (0x20);
          feed_frame (fixture, ack, fragmentation);
          goodix_post_tls_lifecycle_handle_plaintext (fixture->lifecycle,
                                                       image);
        }
    }

  complete_command (fixture, 0x32, NULL, 0);
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x32);
  feed_frame (fixture, ack, fragmentation);
  if (fixture->handoff_count != 0u)
    {
      g_assert_true (g_queue_is_empty (fixture->out));
      return;
    }
  for (guint i = 0; i < fixture->reverse_events; i++)
    {
      g_clear_pointer (&event, g_bytes_unref);
      event = build_event (0x32, 0x0080, 0x0000, 0x0180);
      feed_frame (fixture, event, fragmentation);
    }
  if (fixture->stop_before_finger)
    return;
  g_clear_pointer (&event, g_bytes_unref);
  event = build_event (0x32, 0x0002, 0x003f, 0x0180);
  feed_frame (fixture, event, fragmentation);
  complete_command (fixture, 0x22, cmd01, sizeof cmd01);
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x22);
  feed_frame (fixture, ack, fragmentation);
  goodix_post_tls_lifecycle_handle_plaintext (fixture->lifecycle, image);

  {
    guint8 body34[14] = { 0x0a, 0x01 };
    memcpy (body34 + 2, fixture->expected_up, 12);
    complete_command (fixture, 0x34, body34, sizeof body34);
  }
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x34);
  feed_frame (fixture, ack, fragmentation);
  g_clear_pointer (&event, g_bytes_unref);
  event = build_event (0x34, 0x0200, 0x0000, 0x0120);
  feed_frame (fixture, event, fragmentation);
  complete_command (fixture, 0x20, cmd01, sizeof cmd01);
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x20);
  feed_frame (fixture, ack, fragmentation);
  goodix_post_tls_lifecycle_handle_plaintext (fixture->lifecycle, auxiliary);
  complete_command (fixture, 0x50, cmd01, sizeof cmd01);
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x50);
  feed_frame (fixture, ack, fragmentation);
  g_clear_pointer (&typed, g_bytes_unref);
  typed = build_nav_no_check (nav, sizeof nav);
  feed_frame (fixture, typed, fragmentation);

  g_assert_true (g_queue_is_empty (fixture->out));
  if (fixture->material.capture_profile ==
      GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION)
    {
      goodix_post_tls_lifecycle_set_framework_await_finger_on (
        fixture->lifecycle, fixture->generation, TRUE);
      g_assert_true (g_queue_is_empty (fixture->out));
      return;
    }
  goodix_post_tls_lifecycle_set_framework_await_finger_on (
    fixture->lifecycle, fixture->generation - 1u, TRUE);
  g_assert_true (g_queue_is_empty (fixture->out));
  goodix_post_tls_lifecycle_set_framework_await_finger_on (
    fixture->lifecycle, fixture->generation, TRUE);
  {
    guint8 rearm[16] = { 0x08, 0x01 };
    memcpy (rearm + 2, fixture->expected_down, 12);
    rearm[14] = 0x56;
    rearm[15] = 0x34;
    complete_command (fixture, 0x32, rearm, sizeof rearm);
  }
  goodix_post_tls_lifecycle_set_framework_await_finger_on (
    fixture->lifecycle, fixture->generation, TRUE);
  g_assert_true (g_queue_is_empty (fixture->out));
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x32);
  feed_frame (fixture, ack, fragmentation);
  g_clear_pointer (&event, g_bytes_unref);
  event = build_event (0x32, 0x0002, 0x003f, 0x0180);
  feed_frame (fixture, event, fragmentation);
  complete_command (fixture, 0x22, cmd01, sizeof cmd01);
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x22);
  feed_frame (fixture, ack, fragmentation);
  goodix_post_tls_lifecycle_handle_plaintext (fixture->lifecycle, image);
}

static void
assert_full_audit (Fixture *fixture)
{
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_STOP);
  g_assert_cmpuint (fixture->image_count, ==, 2u);
  g_assert_cmpuint (fixture->finger_down_count, ==, 2u);
  g_assert_cmpuint (fixture->release_tail_count, ==, 1u);
  g_assert_cmpuint (fixture->finger_up_count, ==, 1u);
  g_assert_true (fixture->audit.post_tls_lifecycle_started);
  g_assert_cmpuint (fixture->audit.d4_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.af_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.command_count, ==, 15u);
  g_assert_cmpuint (fixture->audit.ack_count, ==, 14u);
  g_assert_cmpuint (fixture->audit.fdt36_submit_count, ==, 3u);
  g_assert_cmpuint (fixture->audit.fdt_irq100_count, ==, 3u);
  g_assert_cmpuint (fixture->audit.fresh_fdt_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.fdt_delta_classification_count, ==, 2u);
  g_assert_cmpuint (fixture->audit.fdt_delta_within_threshold_count, ==, 2u);
  g_assert_cmpuint (fixture->audit.fdt_delta_outside_threshold_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.baseline_b0_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.baseline_decode_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.first_irq0002_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.first_image_b0_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.first_image_command_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.first_image_pipeline_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.post_up_b0_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.release_0x34_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.irq0200_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.post_up_0x20_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.nav_0x50_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.nav_response_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.release_tail_complete_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.single_acquisition_terminal_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.fresh_down_table_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.second_b0_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.second_irq0002_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.second_image_command_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.second_image_pipeline_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.rearm_0x32_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.third_cycle_command_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.retry_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.reopen_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.device_reset_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.clear_halt_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.persistent_device_write_count, ==, 0u);
  g_assert_true (fixture->audit.fresh_down_table);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_max_outstanding (
                     fixture->backend), ==, 1u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_max_out_outstanding (
                     fixture->backend), ==, 1u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (
                     fixture->backend), ==, 0u);
}

static void
test_single_acquisition_terminal_no_rearm (void)
{
  Fixture *fixture = fixture_new_for_profile (
    GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION);

  run_full_trace (fixture, 1u);

  g_assert_cmpint (goodix_post_tls_lifecycle_get_capture_profile (
                     fixture->lifecycle), ==,
                   GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_STOP);
  g_assert_cmpuint (fixture->image_count, ==, 1u);
  g_assert_cmpuint (fixture->finger_down_count, ==, 1u);
  g_assert_cmpuint (fixture->release_tail_count, ==, 1u);
  g_assert_cmpuint (fixture->finger_up_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.command_count, ==, 13u);
  g_assert_cmpuint (fixture->audit.ack_count, ==, 12u);
  g_assert_cmpuint (fixture->audit.first_image_pipeline_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.release_tail_complete_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.single_acquisition_terminal_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.rearm_0x32_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.second_irq0002_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.second_image_command_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.second_image_pipeline_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.third_cycle_command_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.retry_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.persistent_device_write_count, ==, 0u);
  g_assert_true (g_queue_is_empty (fixture->out));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (
                     fixture->backend), ==, 0u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_outstanding (
                     fixture->backend), ==, 0u);

  fixture_free (fixture);
}

static void
test_full_trace_unfragmented (void)
{
  Fixture *fixture = fixture_new ();
  run_full_trace (fixture, 0u);
  assert_full_audit (fixture);
  goodix_post_tls_lifecycle_free (fixture->lifecycle);
  fixture->lifecycle = NULL;
  g_assert_true (fixture->audit.backend_drained);
  g_assert_true (fixture->audit.terminal_cleanup_completed);
  fixture_free (fixture);
}

static void
test_full_trace_fragmented (void)
{
  Fixture *fixture = fixture_new ();
  run_full_trace (fixture, 1u);
  assert_full_audit (fixture);
  g_assert_cmpuint (fixture->in_submit_count, >, 18u);
  fixture_free (fixture);
}

static void
test_deterministic_repeat (void)
{
  for (guint i = 0; i < 3u; i++)
    {
      Fixture *fixture = fixture_new ();
      run_full_trace (fixture, i % 2u);
      assert_full_audit (fixture);
      fixture_free (fixture);
    }
}

static void
test_wrong_ack_terminal (void)
{
  Fixture *fixture = fixture_new ();
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) wrong = NULL;
  guint8 body[2] = { 0xd4, 0x07 };

  g_assert_true (goodix_post_tls_lifecycle_start (fixture->lifecycle, &error));
  complete_command (fixture, 0xd4, NULL, 0);
  wrong = build_response (0xb0, body, sizeof body);
  feed_frame (fixture, wrong, 0u);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_TERMINAL);
  g_assert_cmpuint (fixture->terminal_count, ==, 1u);
  fixture_free (fixture);
}

static void
test_cancel_invalidates_generation (void)
{
  Fixture *fixture = fixture_new ();
  g_autoptr(GError) error = NULL;
  guint out_count;

  g_assert_true (goodix_post_tls_lifecycle_start (fixture->lifecycle, &error));
  out_count = g_queue_get_length (fixture->out);
  goodix_post_tls_lifecycle_cancel (fixture->lifecycle, "test cancel");
  goodix_post_tls_lifecycle_set_framework_await_finger_on (
    fixture->lifecycle, fixture->generation, TRUE);
  g_assert_cmpuint (g_queue_get_length (fixture->out), ==, out_count);
  g_assert_false (fixture->audit.fresh_down_table);
  g_assert_cmpuint (fixture->terminal_count, ==, 1u);
  fixture_free (fixture);
}

static void
test_image_decoder_crc_terminal (void)
{
  Fixture *fixture = fixture_new ();
  g_autoptr(GBytes) image = build_image (fixture);
  gsize length;
  const guint8 *data = g_bytes_get_data (image, &length);
  g_autofree guint8 *bad = g_memdup2 (data, length);
  g_autoptr(GBytes) corrupted = NULL;

  {
    g_autofree guint8 *ordinary_data = g_memdup2 (data, length);
    g_autoptr(GBytes) ordinary = NULL;
    uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
    GoodixImageDecodeAudit audit = { 0 };
    g_autoptr(GError) error = NULL;
    guint sum = (guint) ordinary_data[0] + (guint) (length - 3u);

    for (gsize i = 3u; i < length - 1u; i++)
      sum += ordinary_data[i];
    ordinary_data[length - 1u] = (guint8) (0xaau - sum);
    ordinary = g_bytes_new_take (g_steal_pointer (&ordinary_data), length);
    g_assert_true (goodix_image_decode_plaintext (ordinary, samples, &audit,
                                                  &error));
    g_assert_no_error (error);
    g_assert_cmpint (audit.checksum_policy, ==,
                     GOODIX_IMAGE_CHECKSUM_ADDITIVE_VERIFIED);
  }

  bad[100] ^= 0x01;
  corrupted = g_bytes_new_take (g_steal_pointer (&bad), length);
  /* Decoder correctness is exercised independently of lifecycle positioning. */
  {
    uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
    g_autoptr(GError) error = NULL;
    g_assert_false (goodix_image_decode_plaintext (corrupted, samples, NULL,
                                                   &error));
    g_assert_nonnull (error);
  }
  fixture_free (fixture);
}

static void
test_fdt_delta_outside_threshold_terminal (void)
{
  Fixture *fixture = fixture_new ();
  static const guint8 cmd01[] = { 0x01, 0x00 };
  guint8 af[16] = { 0 };
  guint8 nav[2409] = { 0 };
  guint8 typed82[2] = { 0x00, 0x20 };
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GBytes) typed = NULL;
  g_autoptr(GBytes) event = NULL;
  g_autoptr(GError) error = NULL;

  nav[0] = 0x50;
  nav[1] = 0x01;

  g_assert_true (goodix_post_tls_lifecycle_start (fixture->lifecycle, &error));
  g_assert_no_error (error);

  complete_command (fixture, 0xd4, NULL, 0);
  ack = build_ack (0xd4);
  feed_frame (fixture, ack, 0);

  complete_command (fixture, 0xaf, NULL, 0);
  af[1] = 0x02;
  typed = build_response (0xae, af, sizeof af);
  feed_frame (fixture, typed, 0);

  complete_command (fixture, 0x36, NULL, 0);
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x36);
  feed_frame (fixture, ack, 0);
  event = build_event (0x36, 0x0100, 0x0000, 0x0300);
  feed_frame (fixture, event, 0);

  complete_command (fixture, 0x50, cmd01, sizeof cmd01);
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x50);
  feed_frame (fixture, ack, 0);
  g_clear_pointer (&typed, g_bytes_unref);
  typed = build_nav_no_check (nav, sizeof nav);
  feed_frame (fixture, typed, 0);

  complete_command (fixture, 0x36, NULL, 0);
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x36);
  feed_frame (fixture, ack, 0);
  g_clear_pointer (&event, g_bytes_unref);
  event = build_event (0x36, 0x0100, 0x0000, 0x0342);
  feed_frame (fixture, event, 0);

  complete_command (fixture, 0x82, NULL, 0);
  g_clear_pointer (&ack, g_bytes_unref);
  ack = build_ack (0x82);
  feed_frame (fixture, ack, 0);
  g_clear_pointer (&typed, g_bytes_unref);
  typed = build_response (0x82, typed82, sizeof typed82);
  feed_frame (fixture, typed, 0);

  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_TERMINAL);
  g_assert_cmpuint (fixture->audit.fdt_delta_classification_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.fdt_delta_within_threshold_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.fdt_delta_outside_threshold_count, ==, 1u);
  g_assert_cmpuint (fixture->terminal_count, ==, 1u);
  g_assert_true (g_queue_is_empty (fixture->out));

  fixture_free (fixture);
}

static void
test_rejected_a0_sanitized_telemetry (void)
{
  Fixture *fixture = fixture_new ();
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) event = NULL;

  g_assert_true (goodix_post_tls_lifecycle_start (fixture->lifecycle, &error));
  g_assert_no_error (error);

  /* Complete physical D4 OUT, then inject a structurally valid FDT event
   * where the lifecycle is still expecting the D4 ACK. */
  complete_command (fixture, 0xd4, NULL, 0);
  event = build_event (0x32, 0x0080, 0x1234, 0x0300);
  feed_frame (fixture, event, 0);

  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_TERMINAL);
  g_assert_true (fixture->audit.rejected_a0_observed);
  g_assert_cmpint (fixture->audit.rejected_a0_phase,
                   ==, GOODIX_POST_TLS_PHASE_D4);
  g_assert_cmpint (fixture->audit.rejected_a0_control, ==, 0x32);
  g_assert_cmpint (fixture->audit.rejected_a0_irq, ==, 0x0080);
  g_assert_cmpint (fixture->audit.rejected_a0_flags, ==, 0x1234);
  g_assert_cmpint (fixture->audit.rejected_a0_body_length, ==, 16);
  g_assert_cmpuint (fixture->terminal_count, ==, 1u);

  fixture_free (fixture);
}

/* Characterization, not a fix or a simulation of firmware contact detection.
 * The metadata is target-observed in the 2026-09-15 D297 journal; the raw
 * channel values are synthetic. Do not append an invented IRQ2 to make the
 * missing-event case pass as an authentication. */
static void
test_login_baseline_contact_rejected (void)
{
  Fixture *fixture = fixture_new_for_profile (
    GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION);
  guint8 state[16] = { 0 };
  g_autoptr(GBytes) ack_d4 = build_ack (0xd4);
  g_autoptr(GBytes) ack_fdt = build_ack (0x36);
  g_autoptr(GBytes) event = build_event (0x36, 0x0100, 0x003f, 0x0300);
  g_autoptr(GBytes) ae = NULL;

  state[1] = 0x02;
  ae = build_response (0xae, state, sizeof state);
  g_assert_true (goodix_post_tls_lifecycle_start (fixture->lifecycle, NULL));
  complete_command (fixture, 0xd4, NULL, 0);
  feed_frame (fixture, ack_d4, 0);
  complete_command (fixture, 0xaf, NULL, 0);
  feed_frame (fixture, ae, 0);
  complete_command (fixture, 0x36, NULL, 0);
  feed_frame (fixture, ack_fdt, 0);
  feed_frame (fixture, event, 0);

#ifdef GOODIX_SAME_ACTION_TEST
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_FDT_NAV_1);
  g_assert_false (fixture->audit.rejected_a0_observed);
  g_assert_cmpuint (fixture->audit.command_count, ==, 4u);
  complete_command (fixture, 0x50, NULL, 0);
  goodix_post_tls_lifecycle_cancel (fixture->lifecycle, "test cancellation");
#else
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_TERMINAL);
  g_assert_true (fixture->audit.rejected_a0_observed);
  g_assert_cmpint (fixture->audit.rejected_a0_phase,
                   ==, GOODIX_POST_TLS_PHASE_FDT_IRQ100_1);
  g_assert_cmpint (fixture->audit.rejected_a0_control, ==, 0x36);
  g_assert_cmpint (fixture->audit.rejected_a0_irq, ==, 0x0100);
  g_assert_cmpint (fixture->audit.rejected_a0_flags, ==, 0x003f);
  g_assert_cmpuint (fixture->audit.command_count, ==, 3u);
#endif
  g_assert_cmpuint (fixture->audit.first_image_command_count, ==, 0u);
  g_assert_cmpuint (fixture->terminal_count, ==, 1u);
  g_assert_true (g_queue_is_empty (fixture->out));
  g_assert_true (goodix_fpi_usb_backend_is_drained (fixture->backend));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (
                     fixture->backend), ==, 0u);
  fixture_free (fixture);
}

static void
test_login_readiness_without_irq2_does_not_capture (void)
{
  Fixture *fixture = fixture_new_for_profile (
    GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION);

  fixture->stop_before_finger = TRUE;
  run_full_trace (fixture, 1u);
  g_assert_cmpuint (fixture->audit.ack_count, ==, 8u);
  for (guint i = 0; i < 3u; i++)
    goodix_post_tls_lifecycle_set_framework_await_finger_on (
      fixture->lifecycle, fixture->generation, i != 0u);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_FIRST_IRQ2);
  g_assert_cmpuint (fixture->audit.command_count, ==, 9u);
  g_assert_cmpuint (fixture->audit.first_irq0002_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.first_image_command_count, ==, 0u);
  g_assert_cmpuint (fixture->image_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.retry_count, ==, 0u);
  g_assert_true (g_queue_is_empty (fixture->out));

  goodix_post_tls_lifecycle_cancel (fixture->lifecycle, "test cancellation");
  g_assert_cmpuint (fixture->terminal_count, ==, 1u);
  g_assert_true (goodix_fpi_usb_backend_is_drained (fixture->backend));
  g_assert_true (g_queue_is_empty (fixture->out));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (
                     fixture->backend), ==, 0u);
  fixture_free (fixture);
}

#ifdef GOODIX_SAME_ACTION_TEST
static void
test_same_action_baseline_scope (void)
{
  for (guint i = 0; i < 3u; i++)
    {
      Fixture *fixture = fixture_new_for_profile (
        i == 2u ? GOODIX_POST_TLS_CAPTURE_PROFILE_TWO_ACQUISITION :
                  GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION);
      guint8 state[16] = { 0, 2 };
      const guint16 flags[] = { 0x0040, 0x0001, 0x003f };
      g_autoptr(GBytes) ack_d4 = build_ack (0xd4);
      g_autoptr(GBytes) ack36 = build_ack (0x36);
      g_autoptr(GBytes) ae = build_response (0xae, state, sizeof state);
      g_autoptr(GBytes) event = build_event (0x36, 0x0100, flags[i], 0x0300);
      g_assert_true (goodix_post_tls_lifecycle_start (fixture->lifecycle, NULL));
      complete_command (fixture, 0xd4, NULL, 0);
      feed_frame (fixture, ack_d4, 1u);
      complete_command (fixture, 0xaf, NULL, 0);
      feed_frame (fixture, ae, 1u);
      complete_command (fixture, 0x36, NULL, 0);
      feed_frame (fixture, ack36, 1u);
      feed_frame (fixture, event, 1u);
      g_assert_cmpuint (fixture->terminal_count, ==, 1u);
      g_assert_cmpuint (fixture->audit.command_count, ==, 3u);
      g_assert_true (fixture->audit.rejected_a0_observed);
      g_assert_true (goodix_fpi_usb_backend_is_drained (fixture->backend));
      fixture_free (fixture);
    }
}

static void
test_same_action_known_prefix_then_irq (void)
{
  Fixture *fixture = fixture_new_for_profile (
    GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION);
  fixture->baseline_flags = 0x003f;
  fixture->response_before_ack = TRUE;
  fixture->reverse_events = 2;
  run_full_trace (fixture, 1u);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_STOP);
  g_assert_cmpuint (fixture->image_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.command_count, ==, 13u);
  g_assert_cmpuint (fixture->audit.ack_count, ==, 12u);
  g_assert_cmpuint (fixture->audit.rearm_0x32_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.retry_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.release_tail_complete_count, ==, 1u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (
                     fixture->backend), ==, 0u);
  fixture_free (fixture);
}

static void
test_same_action_missing_irq_and_reverse_limit (void)
{
  Fixture *fixture = fixture_new_for_profile (
    GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION);
  g_autoptr(GBytes) reverse = build_event (0x32, 0x0080, 0, 0x0180);
  fixture->baseline_flags = 0x003f;
  fixture->response_before_ack = TRUE;
  fixture->reverse_events = 2;
  fixture->stop_before_finger = TRUE;
  run_full_trace (fixture, 1u);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_FIRST_IRQ2);
  g_assert_cmpuint (fixture->audit.command_count, ==, 9u);
  g_assert_cmpuint (fixture->audit.first_image_command_count, ==, 0u);
  g_assert_cmpuint (fixture->image_count, ==, 0u);
  g_assert_true (g_queue_is_empty (fixture->out));
  feed_frame (fixture, reverse, 1u);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_TERMINAL);
  g_assert_cmpuint (fixture->terminal_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.command_count, ==, 9u);
  g_assert_true (goodix_fpi_usb_backend_is_drained (fixture->backend));
  fixture_free (fixture);
}

static void
test_same_action_duplicate_response_fails (void)
{
  Fixture *fixture = fixture_new_for_profile (
    GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION);
  const guint8 data[] = { 0, 32 };
  g_autoptr(GBytes) response = build_response (0x82, data, sizeof data);
  fixture->stop_before_82 = TRUE;
  run_full_trace (fixture, 1u);
  feed_frame (fixture, response, 1u);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_FDT_82);
  g_assert_true (g_queue_is_empty (fixture->out));
  g_assert_cmpuint (fixture->audit.command_count, ==, 6u);
  feed_frame (fixture, response, 1u);
  g_assert_cmpuint (fixture->terminal_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.command_count, ==, 6u);
  g_assert_true (goodix_fpi_usb_backend_is_drained (fixture->backend));
  fixture_free (fixture);
}
#endif

static void
test_first_arm_backend_handoff (void)
{
  Fixture *fixture = fixture_new ();
  const guint8 synthetic[] = { 0xa5 };
  g_autoptr(GBytes) bytes = g_bytes_new_static (synthetic,
                                                 sizeof synthetic);
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_post_tls_lifecycle_set_first_arm_handoff (
    fixture->lifecycle, first_arm_handoff_callback, &error));
  g_assert_no_error (error);
  run_full_trace (fixture, 1u);

  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_STOP);
  g_assert_cmpuint (fixture->handoff_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.first_arm_handoff_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.backend_handoff_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.command_count, ==, 9u);
  g_assert_cmpuint (fixture->audit.ack_count, ==, 8u);
  g_assert_cmpuint (fixture->image_count, ==, 0u);
  g_assert_cmpuint (fixture->finger_down_count, ==, 0u);

  g_assert_true (goodix_fpi_usb_backend_submit_out (
    fixture->backend, fixture->generation, bytes, &error));
  g_assert_no_error (error);
  goodix_fpi_usb_backend_complete_out (fixture->backend,
                                       fixture->generation, NULL);
  g_assert_cmpuint (fixture->new_owner_completion_count, ==, 1u);

  goodix_post_tls_lifecycle_free (fixture->lifecycle);
  fixture->lifecycle = NULL;
  g_assert_true (goodix_fpi_usb_backend_submit_out (
    fixture->backend, fixture->generation, bytes, &error));
  g_assert_no_error (error);
  goodix_fpi_usb_backend_complete_out (fixture->backend,
                                       fixture->generation, NULL);
  g_assert_cmpuint (fixture->new_owner_completion_count, ==, 2u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (
                     fixture->backend), ==, 0u);
  fixture_free (fixture);
}

static void
test_first_arm_backend_handoff_failure (void)
{
  Fixture *fixture = fixture_new ();

  fixture->handoff_should_fail = TRUE;
  g_assert_true (goodix_post_tls_lifecycle_set_first_arm_handoff (
    fixture->lifecycle, first_arm_handoff_callback, NULL));
  run_full_trace (fixture, 0u);

  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->lifecycle),
                   ==, GOODIX_POST_TLS_PHASE_TERMINAL);
  g_assert_cmpuint (fixture->handoff_count, ==, 1u);
  g_assert_cmpuint (fixture->terminal_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.first_arm_handoff_count, ==, 1u);
  g_assert_cmpuint (fixture->audit.backend_handoff_count, ==, 1u);
  g_assert_true (fixture->audit.terminal);
  g_assert_true (goodix_fpi_usb_backend_is_drained (fixture->backend));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (
                     fixture->backend), ==, 0u);
  fixture_free (fixture);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d278-12/full-unfragmented",
                   test_full_trace_unfragmented);
  g_test_add_func ("/d278-12/full-fragmented",
                   test_full_trace_fragmented);
  g_test_add_func ("/d278-12/deterministic-repeat",
                   test_deterministic_repeat);
  g_test_add_func ("/d279-55/single-acquisition-terminal-no-rearm",
                   test_single_acquisition_terminal_no_rearm);
  g_test_add_func ("/d278-12/wrong-ack-terminal",
                   test_wrong_ack_terminal);
  g_test_add_func ("/d278-12/cancel-generation-fence",
                   test_cancel_invalidates_generation);
  g_test_add_func ("/d278-12/image-crc-terminal",
                   test_image_decoder_crc_terminal);
  g_test_add_func ("/d278-12/fdt-delta-outside-threshold-terminal",
                   test_fdt_delta_outside_threshold_terminal);
  g_test_add_func ("/d278-12/rejected-a0-sanitized-telemetry",
                   test_rejected_a0_sanitized_telemetry);
  g_test_add_func ("/d279-21/first-arm-backend-handoff",
                   test_first_arm_backend_handoff);
  g_test_add_func ("/d279-21/first-arm-backend-handoff-failure",
                   test_first_arm_backend_handoff_failure);
  g_test_add_func ("/login-latency/baseline-contact-rejected",
                   test_login_baseline_contact_rejected);
  g_test_add_func ("/login-latency/readiness-without-irq2-does-not-capture",
                   test_login_readiness_without_irq2_does_not_capture);
#ifdef GOODIX_SAME_ACTION_TEST
  g_test_add_func ("/same-action/baseline-scope", test_same_action_baseline_scope);
  g_test_add_func ("/same-action/known-prefix-conditional-irq", test_same_action_known_prefix_then_irq);
  g_test_add_func ("/same-action/missing-irq-reverse-limit", test_same_action_missing_irq_and_reverse_limit);
  g_test_add_func ("/same-action/duplicate-response-fails", test_same_action_duplicate_response_fails);
#endif
  return g_test_run ();
}
