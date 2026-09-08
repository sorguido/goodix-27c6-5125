/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_post_tls_events.h"
#include "goodix_enrollment_outbound_transaction.h"
#include "goodix_enrollment_fpi_usb_binding.h"
#include "goodix_usb_router.h"

#include <fpi-image.h>
#include <string.h>

typedef struct
{
  guint image_count;
  guint timestamp_count;
  guint auxiliary_delivery_count;
  guint8 auxiliary_last_byte;
  guint backend_out_count;
  guint contact_down_count;
  guint contact_up_count;
} Fixture;

static gboolean
image_ready (GoodixEnrollmentPipeline *pipeline,
             guint                     stage_index,
             FpImage                  *image,
             gpointer                  user_data,
             GError                  **error)
{
  Fixture *fixture = user_data;

  (void) pipeline;
  (void) error;
  g_assert_true (FP_IS_IMAGE (image));
  g_assert_cmpuint (stage_index, ==, fixture->image_count + 1u);
  fixture->image_count++;
  return TRUE;
}

static gboolean
timestamp_ready (guint                           stage_index,
                 GoodixEnrollmentCommandPurpose purpose,
                 guint16                        *timestamp,
                 gpointer                        user_data,
                 GError                        **error)
{
  Fixture *fixture = user_data;

  (void) stage_index;
  (void) purpose;
  (void) error;
  *timestamp = (guint16) (0x3000u + fixture->timestamp_count++);
  return TRUE;
}

static gboolean
auxiliary_ready (GBytes   *plaintext,
                 gpointer  user_data,
                 GError  **error)
{
  Fixture *fixture = user_data;
  gsize length;

  (void) error;
  const guint8 *bytes = g_bytes_get_data (plaintext, &length);
  g_assert_cmpuint (length, ==, GOODIX_IMAGE_PLAINTEXT_LENGTH);
  fixture->auxiliary_last_byte = bytes[length - 1u];
  fixture->auxiliary_delivery_count++;
  return TRUE;
}

static gboolean
contact_ready (guint      stage_index,
               gboolean   present,
               gpointer   user_data,
               GError   **error)
{
  Fixture *fixture = user_data;

  (void) error;
  if (present)
    {
      g_assert_cmpuint (stage_index, ==, fixture->contact_down_count + 1u);
      g_assert_cmpuint (fixture->image_count, ==, stage_index - 1u);
      fixture->contact_down_count++;
    }
  else
    {
      g_assert_cmpuint (stage_index, ==, fixture->contact_up_count + 1u);
      /* A deferred terminal image is delivered during IRQ0200 acceptance,
       * before finger-up reaches the eventual libfprint consumer. */
      g_assert_cmpuint (fixture->image_count, ==, stage_index);
      fixture->contact_up_count++;
    }
  return TRUE;
}

static gboolean
reject_contact (guint      stage_index,
                gboolean   present,
                gpointer   user_data,
                GError   **error)
{
  (void) stage_index;
  (void) present;
  (void) user_data;
  g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                       "synthetic contact callback rejection");
  return FALSE;
}

static GBytes *
build_ack (guint8 echo)
{
  const guint8 body[] = { echo, 0x01 };
  g_autoptr(GError) error = NULL;
  GBytes *frame = goodix_a0_build_frame (0xb0, 0xb0, body, sizeof body,
                                         &error);

  g_assert_no_error (error);
  g_assert_nonnull (frame);
  return frame;
}

static void
fill_raw (guint seed, guint8 raw[12])
{
  for (guint i = 0u; i < 6u; i++)
    {
      guint16 word = (guint16) (seed + i * 2u);
      raw[i * 2u] = (guint8) word;
      raw[i * 2u + 1u] = (guint8) (word >> 8);
    }
}

static GBytes *
build_irq (guint8       control,
           guint16      irq,
           guint16      flags,
           const guint8 raw[12])
{
  guint8 body[16];
  g_autoptr(GError) error = NULL;
  GBytes *frame;

  body[0] = (guint8) irq;
  body[1] = (guint8) (irq >> 8);
  body[2] = (guint8) flags;
  body[3] = (guint8) (flags >> 8);
  memcpy (body + 4u, raw, 12u);
  frame = goodix_a0_build_frame (control, control, body, sizeof body, &error);
  g_assert_no_error (error);
  g_assert_nonnull (frame);
  return frame;
}

static GBytes *
build_nav_no_check (void)
{
  guint8 body[2409] = { 0x50, 0x01 };
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) additive = goodix_a0_build_frame (
    0x50, 0x50, body, sizeof body, &error);
  gsize length;
  const guint8 *source;
  guint8 *copy;

  g_assert_no_error (error);
  source = g_bytes_get_data (additive, &length);
  g_assert_cmpuint (length, ==, 2417u);
  copy = g_memdup2 (source, length);
  copy[length - 1u] = 0x88;
  return g_bytes_new_take (copy, length);
}

static void
handle_a0 (GoodixEnrollmentPostTlsEvents *events,
           GBytes                        *frame)
{
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_enrollment_post_tls_events_handle_a0 (
    events, frame, &error));
  g_assert_no_error (error);
}

static void
handle_irq (GoodixEnrollmentPostTlsEvents *events,
            guint8                         control,
            guint16                        irq,
            guint16                        flags,
            const guint8                  *raw)
{
  g_autoptr(GBytes) frame = build_irq (control, irq, flags, raw);

  handle_a0 (events, frame);
}

static void
prepare_commit (GoodixEnrollmentPostTlsEvents *events,
                GoodixEnrollmentEvent          command_event)
{
  GoodixEnrollmentPreparedCommand prepared = { 0 };
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_enrollment_post_tls_events_prepare (
    events, &prepared, &error));
  g_assert_no_error (error);
  g_assert_cmpint (prepared.intent.event, ==, command_event);
  g_assert_false (prepared.intent.wire_frame_serializable);
  g_assert_true (goodix_enrollment_post_tls_events_commit (
    events, command_event, &error));
  g_assert_no_error (error);
  goodix_enrollment_prepared_command_clear (&prepared);
}

static gboolean
synthetic_frame_sink (guint64    generation,
                      GBytes    *frame,
                      gpointer   user_data,
                      GError   **error)
{
  gsize length;

  (void) user_data;
  (void) error;
  g_assert_cmpuint (generation, ==, 1u);
  (void) g_bytes_get_data (frame, &length);
  g_assert_cmpuint (length, ==, GOODIX_ENROLLMENT_FIXED64_LENGTH);
  return TRUE;
}

static void
backend_submit_seam (GoodixFpiUsbBackend *backend,
                     GoodixUsbDirection   direction,
                     guint64              generation,
                     GBytes              *bytes,
                     gpointer             user_data)
{
  Fixture *fixture = user_data;
  gsize length;

  (void) backend;
  g_assert_cmpint (direction, ==, GOODIX_USB_TRANSFER_OUT);
  g_assert_cmpuint (generation, ==, 7u);
  g_assert_nonnull (bytes);
  (void) g_bytes_get_data (bytes, &length);
  g_assert_cmpuint (length, ==, GOODIX_ENROLLMENT_FIXED64_LENGTH);
  fixture->backend_out_count++;
}

static void
command_ack (GoodixEnrollmentPostTlsEvents *events,
             GoodixEnrollmentEvent          command_event,
             guint8                         echo)
{
  g_autoptr(GBytes) ack = NULL;
  GoodixEnrollmentOutboundTransactionAudit transaction_audit;
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentOutboundTransaction *transaction =
    goodix_enrollment_outbound_transaction_new (
      events, 1u, synthetic_frame_sink, NULL, &transaction_audit, &error);

  g_assert_nonnull (transaction);
  g_assert_no_error (error);
  g_assert_true (goodix_enrollment_outbound_transaction_submit_next (
    transaction, &error));
  g_assert_no_error (error);
  g_assert_true (goodix_enrollment_outbound_transaction_has_pending (
    transaction));
  g_assert_cmpint (goodix_enrollment_post_tls_events_get_expected_event (events),
                   ==, command_event);
  g_assert_true (goodix_enrollment_outbound_transaction_complete_out (
    transaction, 1u, NULL, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (transaction_audit.sink_call_count, ==, 1u);
  g_assert_cmpuint (transaction_audit.positive_completion_count, ==, 1u);
  g_assert_cmpuint (transaction_audit.committed_after_completion_count, ==, 1u);
  g_assert_cmpuint (transaction_audit.retry_count, ==, 0u);
  g_assert_cmpuint (transaction_audit.real_usb_submit_count, ==, 0u);
  goodix_enrollment_outbound_transaction_free (transaction);
  ack = build_ack (echo);
  handle_a0 (events, ack);
}

static void
handle_primary (GoodixEnrollmentPostTlsEvents *events,
                guint                          stage)
{
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  g_autoptr(GError) error = NULL;

  for (gsize i = 0u; i < G_N_ELEMENTS (samples); i++)
    samples[i] = (uint16_t) ((i + stage * 97u) & GOODIX_SENSOR_SAMPLE_MAX);
  g_assert_true (goodix_enrollment_post_tls_events_handle_primary_samples (
    events, samples, G_N_ELEMENTS (samples), &error));
  g_assert_no_error (error);
}

static void
handle_auxiliary (GoodixEnrollmentPostTlsEvents *events)
{
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_enrollment_post_tls_events_handle_auxiliary_b0 (
    events, &error));
  g_assert_no_error (error);
}

static void
run_profile (guint stages)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = stages,
    .defer_terminal_stage_delivery = TRUE,
    .defer_intermediate_stage_delivery_until_release_ready = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit audit;
  Fixture fixture = { 0 };
  guint8 irq2_raw[21][12];
  guint8 irq0200_raw[21][12];
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &audit, &error);

  g_assert_nonnull (events);
  g_assert_no_error (error);
  g_assert_true (goodix_enrollment_post_tls_events_set_contact_callback (
    events, contact_ready, &fixture, &error));
  g_assert_no_error (error);
  for (guint stage = 1u; stage <= stages; stage++)
    {
      fill_raw (0x80u + stage * 8u, irq2_raw[stage - 1u]);
      fill_raw (0x40u + stage * 8u, irq0200_raw[stage - 1u]);
      handle_irq (events, 0x32, 0x0002, 0x003f,
                  irq2_raw[stage - 1u]);
      command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_22, 0x22);
      handle_primary (events, stage);
      g_assert_cmpuint (fixture.image_count, ==, stage - 1u);
      command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_34, 0x34);
      if (stage == 1u)
        {
          g_autoptr(GBytes) nav = NULL;

          handle_irq (events, 0x34, 0x0200, 0x0000,
                      irq0200_raw[stage - 1u]);
          command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_20, 0x20);
          handle_auxiliary (events);
          command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_32, 0x32);
          command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_50, 0x50);
          nav = build_nav_no_check ();
          handle_a0 (events, nav);
          command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_32, 0x32);
        }
      else
        {
          command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_36, 0x36);
          handle_irq (events, 0x36, 0x0100, 0x003f,
                      irq2_raw[stage - 1u]);
          command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_20, 0x20);
          handle_auxiliary (events);
          command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_34, 0x34);
          handle_irq (events, 0x34, 0x0200, 0x0000,
                      irq0200_raw[stage - 1u]);
          if (stage < stages)
            command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_32, 0x32);
        }
    }
  g_assert_true (goodix_enrollment_post_tls_events_is_complete (events));
  g_assert_false (goodix_enrollment_post_tls_events_is_failed (events));
  g_assert_cmpuint (fixture.image_count, ==, stages);
  g_assert_cmpuint (fixture.contact_down_count, ==, stages);
  g_assert_cmpuint (fixture.contact_up_count, ==, stages);
  g_assert_cmpuint (fixture.timestamp_count, ==, stages);
  g_assert_cmpuint (audit.ack_count, ==, 6u * stages - 1u);
  g_assert_cmpuint (audit.irq2_count, ==, stages);
  g_assert_cmpuint (audit.irq0100_count, ==, stages - 1u);
  g_assert_cmpuint (audit.irq0200_count, ==, stages);
  g_assert_cmpuint (audit.finger_down_delivery_count, ==, stages);
  g_assert_cmpuint (audit.finger_up_delivery_count, ==, stages);
  g_assert_cmpuint (audit.nav_count, ==, 1u);
  g_assert_cmpuint (audit.primary_b0_count, ==, stages);
  g_assert_cmpuint (audit.auxiliary_b0_count, ==, stages);
  g_assert_cmpuint (fixture.auxiliary_delivery_count, ==, 0u);
  g_assert_cmpuint (audit.parsed_a0_count, ==, 9u * stages - 1u);
  g_assert_cmpuint (audit.retry_count, ==, 0u);
  g_assert_cmpuint (audit.a0_frame_build_count, ==, 0u);
  g_assert_cmpuint (audit.submit_count, ==, 0u);
  goodix_enrollment_post_tls_events_free (events);
}

static void
test_repeated_primary_early_finger_up_is_diagnostic_fail_closed (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 3u,
    .defer_terminal_stage_delivery = TRUE,
    .defer_intermediate_stage_delivery_until_release_ready = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit audit;
  Fixture fixture = { 0 };
  guint8 irq2_raw[12];
  guint8 irq0200_raw[12];
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) nav = NULL;
  g_autoptr(GBytes) early_up = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &audit, &error);

  g_assert_nonnull (events);
  fill_raw (0x88u, irq2_raw);
  fill_raw (0x48u, irq0200_raw);

  /* Complete the distinct first contact. */
  handle_irq (events, 0x32, 0x0002, 0x003f, irq2_raw);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_22, 0x22);
  handle_primary (events, 1u);
  g_assert_cmpuint (fixture.image_count, ==, 0u);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_34, 0x34);
  g_assert_cmpuint (fixture.image_count, ==, 1u);
  handle_irq (events, 0x34, 0x0200, 0x0000, irq0200_raw);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_20, 0x20);
  handle_auxiliary (events);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_32, 0x32);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_50, 0x50);
  nav = build_nav_no_check ();
  handle_a0 (events, nav);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_32, 0x32);

  /* On a repeated contact, PRIMARY_B0 is not release-ready. Simulate the
   * observed operator action: an early physical release causes IRQ0200 while
   * the graph still expects IRQ0100 after ACK_36. */
  handle_irq (events, 0x32, 0x0002, 0x003f, irq2_raw);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_22, 0x22);
  handle_primary (events, 2u);
  g_assert_cmpuint (fixture.image_count, ==, 1u);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_34, 0x34);
  g_assert_cmpuint (fixture.image_count, ==, 1u);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_36, 0x36);
  early_up = build_irq (0x34, 0x0200, 0x0000, irq0200_raw);
  g_assert_false (goodix_enrollment_post_tls_events_handle_a0 (
    events, early_up, &error));
  g_assert_nonnull (error);
  g_assert_nonnull (strstr (error->message, "expected IRQ0100"));
  g_assert_nonnull (strstr (error->message, "control 0x34"));
  g_assert_nonnull (strstr (error->message, "IRQ 0x0200"));
  g_assert_true (goodix_enrollment_post_tls_events_is_failed (events));
  g_assert_cmpuint (fixture.image_count, ==, 1u);
  g_assert_cmpint (audit.last_mismatch_expected_event, ==,
                   GOODIX_ENROLLMENT_EVENT_IRQ0100);
  g_assert_cmphex (audit.last_mismatch_observed_control, ==, 0x34);
  g_assert_true (audit.last_mismatch_observed_irq_classified);
  g_assert_cmphex (audit.last_mismatch_observed_irq, ==, 0x0200);
  g_assert_cmphex (audit.last_mismatch_observed_irq_flags, ==, 0x0000);
  g_assert_cmpuint (audit.rejected_inbound_count, ==, 1u);
  goodix_enrollment_post_tls_events_free (events);
}

static void
test_profiles (void)
{
  run_profile (2u);
  run_profile (3u);
  run_profile (21u);
}

static void
test_wrong_ack_fails_closed (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit audit;
  Fixture fixture = { 0 };
  guint8 raw[12];
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &audit, &error);

  fill_raw (0x88u, raw);
  handle_irq (events, 0x32, 0x0002, 0x003f, raw);
  prepare_commit (events, GOODIX_ENROLLMENT_EVENT_COMMAND_22);
  ack = build_ack (0x20);
  g_assert_false (goodix_enrollment_post_tls_events_handle_a0 (
    events, ack, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_post_tls_events_is_failed (events));
  g_assert_cmpuint (audit.rejected_inbound_count, ==, 1u);
  g_assert_cmpint (audit.last_mismatch_expected_event, ==,
                   GOODIX_ENROLLMENT_EVENT_ACK_22);
  g_assert_cmphex (audit.last_mismatch_observed_control, ==, 0xb0);
  g_assert_false (audit.last_mismatch_observed_irq_classified);
  goodix_enrollment_post_tls_events_free (events);
}

static void
test_bad_irq_flags_fail_closed (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit audit;
  Fixture fixture = { 0 };
  guint8 raw[12];
  g_autoptr(GBytes) frame = NULL;
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &audit, &error);

  fill_raw (0x88u, raw);
  frame = build_irq (0x32, 0x0002, 0x0000, raw);
  g_assert_false (goodix_enrollment_post_tls_events_handle_a0 (
    events, frame, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_post_tls_events_is_failed (events));
  g_assert_cmpint (audit.last_mismatch_expected_event, ==,
                   GOODIX_ENROLLMENT_EVENT_IRQ2);
  g_assert_cmphex (audit.last_mismatch_observed_control, ==, 0x32);
  g_assert_true (audit.last_mismatch_observed_irq_classified);
  g_assert_cmphex (audit.last_mismatch_observed_irq, ==, 0x0002);
  g_assert_cmphex (audit.last_mismatch_observed_irq_flags, ==, 0x0000);
  goodix_enrollment_post_tls_events_free (events);
}

static void
test_contact_callback_failure_fails_closed (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit audit;
  Fixture fixture = { 0 };
  guint8 raw[12];
  g_autoptr(GBytes) frame = NULL;
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &audit, &error);

  g_assert_true (goodix_enrollment_post_tls_events_set_contact_callback (
    events, reject_contact, NULL, &error));
  fill_raw (0x88u, raw);
  frame = build_irq (0x32, 0x0002, 0x003f, raw);
  g_assert_false (goodix_enrollment_post_tls_events_handle_a0 (
    events, frame, &error));
  g_assert_error (error, G_IO_ERROR, G_IO_ERROR_FAILED);
  g_assert_true (goodix_enrollment_post_tls_events_is_failed (events));
  g_assert_cmpuint (audit.irq2_count, ==, 1u);
  g_assert_cmpuint (audit.finger_down_delivery_count, ==, 0u);
  g_assert_cmpuint (audit.rejected_inbound_count, ==, 1u);
  g_assert_cmpint (audit.last_mismatch_expected_event, ==,
                   GOODIX_ENROLLMENT_EVENT_NONE);
  goodix_enrollment_post_tls_events_free (events);
}

static guint32
test_crc32_mpeg2 (const guint8 *data,
                  gsize         length)
{
  guint32 crc = UINT32_C (0xffffffff);

  for (gsize i = 0u; i < length; i++)
    {
      crc ^= (guint32) data[i] << 24;
      for (guint bit = 0u; bit < 8u; bit++)
        crc = (crc & UINT32_C (0x80000000)) != 0u ?
          (crc << 1) ^ UINT32_C (0x04c11db7) : crc << 1;
    }
  return crc;
}

static GBytes *
build_image_plaintext (void)
{
  guint8 bytes[GOODIX_IMAGE_PLAINTEXT_LENGTH] = { 0 };
  guint32 crc;

  bytes[0] = 0x20;
  bytes[1] = 0x0a;
  bytes[2] = 0x1e;
  crc = test_crc32_mpeg2 (bytes + 8u, GOODIX_IMAGE_PACKED_LENGTH);
  bytes[7688] = (guint8) (crc >> 8);
  bytes[7689] = (guint8) crc;
  bytes[7690] = (guint8) (crc >> 24);
  bytes[7691] = (guint8) (crc >> 16);
  bytes[7692] = 0x88;
  return g_bytes_new (bytes, sizeof bytes);
}

static void
feed_fragmented_plaintext (GoodixEnrollmentPostTlsEvents *events,
                           GBytes                        *plaintext)
{
  const gsize splits[] = { 2u, 31u, GOODIX_IMAGE_PLAINTEXT_LENGTH - 33u };
  gsize offset = 0u;

  for (guint i = 0u; i < G_N_ELEMENTS (splits); i++)
    {
      g_autoptr(GBytes) chunk = g_bytes_new_from_bytes (
        plaintext, offset, splits[i]);
      g_autoptr(GError) error = NULL;

      g_assert_true (goodix_enrollment_post_tls_events_handle_plaintext_chunk (
        events, chunk, &error));
      g_assert_no_error (error);
      offset += splits[i];
    }
}

static void
test_fragmented_primary_and_opaque_auxiliary (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit audit;
  Fixture fixture = { 0 };
  guint8 irq2[12];
  guint8 irq0200[12];
  g_autoptr(GBytes) primary = build_image_plaintext ();
  g_autoptr(GBytes) auxiliary = NULL;
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &audit, &error);
  gsize length;
  const guint8 *source = g_bytes_get_data (primary, &length);
  guint8 *opaque = g_memdup2 (source, length);

  /* Keep only the generic length framing valid. Deliberately invalidate the
   * image CRC/no-check trailer: auxiliary delivery must remain opaque. */
  opaque[7688] ^= 0x5a;
  opaque[7692] = 0x00;
  auxiliary = g_bytes_new_take (opaque, length);

  fill_raw (0x88u, irq2);
  fill_raw (0x48u, irq0200);
  handle_irq (events, 0x32, 0x0002, 0x003f, irq2);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_22, 0x22);
  feed_fragmented_plaintext (events, primary);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_34, 0x34);
  handle_irq (events, 0x34, 0x0200, 0x0000, irq0200);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_20, 0x20);
  feed_fragmented_plaintext (events, auxiliary);

  g_assert_cmpuint (fixture.image_count, ==, 1u);
  g_assert_cmpuint (fixture.auxiliary_delivery_count, ==, 1u);
  g_assert_cmphex (fixture.auxiliary_last_byte, ==, 0x00);
  g_assert_cmpuint (audit.plaintext_chunk_count, ==, 6u);
  g_assert_cmpuint (audit.completed_b0_message_count, ==, 2u);
  g_assert_cmpuint (audit.primary_b0_decode_count, ==, 1u);
  g_assert_cmpuint (audit.auxiliary_b0_delivery_count, ==, 1u);
  g_assert_cmpuint (audit.primary_b0_count, ==, 1u);
  g_assert_cmpuint (audit.auxiliary_b0_count, ==, 1u);
  g_assert_false (goodix_enrollment_post_tls_events_is_failed (events));
  goodix_enrollment_post_tls_events_free (events);
}

static void
test_primary_declared_length_fails_closed (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit audit;
  Fixture fixture = { 0 };
  guint8 irq2[12];
  const guint8 invalid_header[] = { 0x20, 0x01, 0x00 };
  g_autoptr(GBytes) chunk = g_bytes_new_static (
    invalid_header, sizeof invalid_header);
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &audit, &error);

  fill_raw (0x88u, irq2);
  handle_irq (events, 0x32, 0x0002, 0x003f, irq2);
  command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_22, 0x22);
  g_assert_false (goodix_enrollment_post_tls_events_handle_plaintext_chunk (
    events, chunk, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_post_tls_events_is_failed (events));
  g_assert_cmpuint (audit.rejected_inbound_count, ==, 1u);
  g_assert_cmpuint (audit.primary_b0_decode_count, ==, 0u);
  goodix_enrollment_post_tls_events_free (events);
}

static void
test_transaction_stale_completion_fails_closed (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit events_audit;
  GoodixEnrollmentOutboundTransactionAudit transaction_audit;
  Fixture fixture = { 0 };
  guint8 raw[12];
  g_autoptr(GBytes) irq = NULL;
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &events_audit, &error);
  GoodixEnrollmentOutboundTransaction *transaction =
    goodix_enrollment_outbound_transaction_new (
      events, 1u, synthetic_frame_sink, NULL, &transaction_audit, &error);

  fill_raw (0x88u, raw);
  irq = build_irq (0x32, 0x0002, 0x003f, raw);
  g_assert_true (goodix_enrollment_outbound_transaction_handle_a0 (
    transaction, irq, &error));
  g_assert_true (goodix_enrollment_outbound_transaction_submit_next (
    transaction, &error));
  g_assert_false (goodix_enrollment_outbound_transaction_complete_out (
    transaction, 2u, NULL, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_outbound_transaction_is_failed (
    transaction));
  g_assert_cmpuint (transaction_audit.stale_generation_count, ==, 1u);
  g_assert_cmpuint (transaction_audit.committed_after_completion_count, ==, 0u);
  g_assert_cmpuint (events_audit.lifecycle.plan.committed_command_count, ==, 0u);
  goodix_enrollment_outbound_transaction_free (transaction);
  goodix_enrollment_post_tls_events_free (events);
}

static void
test_transaction_early_ack_fails_closed (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit events_audit;
  GoodixEnrollmentOutboundTransactionAudit transaction_audit;
  Fixture fixture = { 0 };
  guint8 raw[12];
  g_autoptr(GBytes) irq = NULL;
  g_autoptr(GBytes) ack = build_ack (0x22);
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &events_audit, &error);
  GoodixEnrollmentOutboundTransaction *transaction =
    goodix_enrollment_outbound_transaction_new (
      events, 1u, synthetic_frame_sink, NULL, &transaction_audit, &error);

  fill_raw (0x88u, raw);
  irq = build_irq (0x32, 0x0002, 0x003f, raw);
  g_assert_true (goodix_enrollment_outbound_transaction_handle_a0 (
    transaction, irq, &error));
  g_assert_true (goodix_enrollment_outbound_transaction_submit_next (
    transaction, &error));
  g_assert_false (goodix_enrollment_outbound_transaction_handle_a0 (
    transaction, ack, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_outbound_transaction_is_failed (
    transaction));
  g_assert_cmpuint (transaction_audit.committed_after_completion_count, ==, 0u);
  g_assert_cmpuint (events_audit.ack_count, ==, 0u);
  goodix_enrollment_outbound_transaction_free (transaction);
  goodix_enrollment_post_tls_events_free (events);
}

static void
test_dormant_backend_binding_completion_gate (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit events_audit;
  GoodixEnrollmentFpiUsbBindingAudit binding_audit;
  Fixture fixture = { 0 };
  guint8 raw[12];
  g_autoptr(GBytes) irq = NULL;
  g_autoptr(GBytes) ack = build_ack (0x22);
  g_autoptr(GBytes) primary = build_image_plaintext ();
  g_autoptr(GBytes) primary_header = NULL;
  g_autoptr(GBytes) primary_tail = NULL;
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GError) error = NULL;
  GoodixFpiUsbBackend *backend = goodix_fpi_usb_backend_new (
    NULL, NULL, 0x81, 0x01, 8192u);
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &events_audit, &error);
  GoodixEnrollmentFpiUsbBinding *binding;

  g_assert_true (goodix_fpi_usb_backend_begin_generation (
    backend, 7u, cancellable, &error));
  goodix_fpi_usb_backend_set_async_submit_seam (
    backend, backend_submit_seam, &fixture);
  binding = goodix_enrollment_fpi_usb_binding_new (
    events, backend, 7u, &binding_audit, &error);
  g_assert_nonnull (binding);
  fill_raw (0x88u, raw);
  irq = build_irq (0x32, 0x0002, 0x003f, raw);
  g_assert_true (goodix_enrollment_fpi_usb_binding_handle_a0 (
    binding, irq, &error));
  g_assert_true (goodix_enrollment_fpi_usb_binding_has_pending (binding));
  g_assert_cmpuint (fixture.backend_out_count, ==, 1u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_outstanding (backend), ==,
                    1u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (backend), ==,
                    0u);
  g_assert_cmpuint (events_audit.lifecycle.plan.committed_command_count, ==,
                    0u);

  /* Stale backend completion is ignored and cannot commit the planner. */
  goodix_fpi_usb_backend_complete_out (backend, 6u, NULL);
  g_assert_true (goodix_enrollment_fpi_usb_binding_has_pending (binding));
  g_assert_cmpuint (events_audit.lifecycle.plan.committed_command_count, ==,
                    0u);
  goodix_fpi_usb_backend_complete_out (backend, 7u, NULL);
  g_assert_false (goodix_enrollment_fpi_usb_binding_has_pending (binding));
  g_assert_cmpuint (events_audit.lifecycle.plan.committed_command_count, ==,
                    1u);
  g_assert_cmpuint (binding_audit.backend_submit_attempt_count, ==, 1u);
  g_assert_cmpuint (binding_audit.graph_ready_submit_count, ==, 1u);
  g_assert_cmpuint (binding_audit.backend_completion_count, ==, 1u);
  g_assert_cmpuint (binding_audit.transaction.committed_after_completion_count,
                    ==, 1u);
  g_assert_cmpuint (binding_audit.retry_count, ==, 0u);
  g_assert_true (goodix_enrollment_fpi_usb_binding_handle_a0 (
    binding, ack, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (binding_audit.graph_ready_submit_count, ==, 1u);
  g_assert_false (goodix_enrollment_fpi_usb_binding_has_pending (binding));

  primary_header = g_bytes_new_from_bytes (primary, 0u, 2u);
  primary_tail = g_bytes_new_from_bytes (
    primary, 2u, GOODIX_IMAGE_PLAINTEXT_LENGTH - 2u);
  g_assert_true (goodix_enrollment_fpi_usb_binding_handle_plaintext_chunk (
    binding, primary_header, &error));
  g_assert_false (goodix_enrollment_fpi_usb_binding_has_pending (binding));
  g_assert_cmpuint (binding_audit.graph_ready_submit_count, ==, 1u);
  g_assert_true (goodix_enrollment_fpi_usb_binding_handle_plaintext_chunk (
    binding, primary_tail, &error));
  g_assert_true (goodix_enrollment_fpi_usb_binding_has_pending (binding));
  g_assert_cmpuint (binding_audit.graph_ready_submit_count, ==, 2u);
  g_assert_cmpuint (fixture.image_count, ==, 1u);
  goodix_fpi_usb_backend_complete_out (backend, 7u, NULL);
  g_assert_false (goodix_enrollment_fpi_usb_binding_has_pending (binding));
  g_assert_cmpuint (binding_audit.transaction.committed_after_completion_count,
                    ==, 2u);

  goodix_enrollment_fpi_usb_binding_free (binding);
  goodix_fpi_usb_backend_free (backend);
}

static void
test_backend_binding_cancel_waits_for_drain (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPostTlsEventsAudit events_audit;
  GoodixEnrollmentFpiUsbBindingAudit binding_audit;
  Fixture fixture = { 0 };
  guint8 raw[12];
  g_autoptr(GBytes) irq = NULL;
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GError) error = NULL;
  g_autoptr(GError) cancelled = g_error_new_literal (
    G_IO_ERROR, G_IO_ERROR_CANCELLED, "synthetic cancelled OUT");
  GoodixUsbRouter *router = goodix_usb_router_new (NULL, NULL, NULL);
  GoodixFpiUsbBackend *backend = goodix_fpi_usb_backend_new (
    NULL, router, 0x81, 0x01, 8192u);
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, auxiliary_ready,
      &fixture, &events_audit, &error);
  GoodixEnrollmentFpiUsbBinding *binding;

  goodix_usb_router_begin_generation (router, 7u);
  g_assert_true (goodix_fpi_usb_backend_begin_generation (
    backend, 7u, cancellable, &error));
  goodix_fpi_usb_backend_set_async_submit_seam (
    backend, backend_submit_seam, &fixture);
  binding = goodix_enrollment_fpi_usb_binding_new (
    events, backend, 7u, &binding_audit, &error);
  fill_raw (0x88u, raw);
  irq = build_irq (0x32, 0x0002, 0x003f, raw);
  g_assert_true (goodix_enrollment_fpi_usb_binding_handle_a0 (
    binding, irq, &error));
  goodix_enrollment_fpi_usb_binding_cancel (binding, "synthetic cancel");
  goodix_enrollment_fpi_usb_binding_cancel (binding, "duplicate cancel");
  g_assert_true (g_cancellable_is_cancelled (cancellable));
  g_assert_true (goodix_enrollment_fpi_usb_binding_is_failed (binding));
  g_assert_false (goodix_enrollment_fpi_usb_binding_can_free (binding));
  g_assert_cmpuint (binding_audit.cancellation_count, ==, 1u);
  g_assert_cmpuint (events_audit.lifecycle.plan.committed_command_count, ==,
                    0u);

  goodix_fpi_usb_backend_complete_out (backend, 7u, cancelled);
  g_assert_true (goodix_enrollment_fpi_usb_binding_can_free (binding));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_completion_count (backend),
                    ==, 1u);
  g_assert_cmpuint (events_audit.lifecycle.plan.committed_command_count, ==,
                    0u);
  goodix_enrollment_fpi_usb_binding_free (binding);
  goodix_fpi_usb_backend_free (backend);
  goodix_usb_router_free (router);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d279-14-post-tls-events/configurable-profiles",
                   test_profiles);
  g_test_add_func ("/d279-14-post-tls-events/wrong-ack-fails-closed",
                   test_wrong_ack_fails_closed);
  g_test_add_func ("/d279-14-post-tls-events/bad-irq-flags-fail-closed",
                   test_bad_irq_flags_fail_closed);
  g_test_add_func ("/d279-57-contact/early-up-after-repeated-primary-diagnostic",
                   test_repeated_primary_early_finger_up_is_diagnostic_fail_closed);
  g_test_add_func ("/d279-22-contact/callback-failure-fails-closed",
                   test_contact_callback_failure_fails_closed);
  g_test_add_func ("/d279-15-b0-stream/fragmented-primary-opaque-auxiliary",
                   test_fragmented_primary_and_opaque_auxiliary);
  g_test_add_func ("/d279-15-b0-stream/invalid-primary-length-fails-closed",
                   test_primary_declared_length_fails_closed);
  g_test_add_func ("/d279-17-transaction/stale-completion-fails-closed",
                   test_transaction_stale_completion_fails_closed);
  g_test_add_func ("/d279-17-transaction/early-ack-fails-closed",
                   test_transaction_early_ack_fails_closed);
  g_test_add_func ("/d279-18-fpi-usb-binding/completion-gate",
                   test_dormant_backend_binding_completion_gate);
  g_test_add_func ("/d279-19-fpi-usb-binding/cancel-waits-for-drain",
                   test_backend_binding_cancel_waits_for_drain);
  return g_test_run ();
}
