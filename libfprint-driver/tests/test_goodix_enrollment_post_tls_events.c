/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_post_tls_events.h"

#include <fpi-image.h>
#include <string.h>

typedef struct
{
  guint image_count;
  guint timestamp_count;
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

static void
command_ack (GoodixEnrollmentPostTlsEvents *events,
             GoodixEnrollmentEvent          command_event,
             guint8                         echo)
{
  g_autoptr(GBytes) ack = NULL;

  prepare_commit (events, command_event);
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
  };
  GoodixEnrollmentPostTlsEventsAudit audit;
  Fixture fixture = { 0 };
  guint8 irq2_raw[21][12];
  guint8 irq0200_raw[21][12];
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, &fixture, &audit, &error);

  g_assert_nonnull (events);
  g_assert_no_error (error);
  for (guint stage = 1u; stage <= stages; stage++)
    {
      fill_raw (0x80u + stage * 8u, irq2_raw[stage - 1u]);
      fill_raw (0x40u + stage * 8u, irq0200_raw[stage - 1u]);
      handle_irq (events, 0x32, 0x0002, 0x003f,
                  irq2_raw[stage - 1u]);
      command_ack (events, GOODIX_ENROLLMENT_EVENT_COMMAND_22, 0x22);
      handle_primary (events, stage);
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
          handle_irq (events, 0x36, 0x0100, 0x0000,
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
  g_assert_cmpuint (fixture.timestamp_count, ==, stages);
  g_assert_cmpuint (audit.ack_count, ==, 6u * stages - 1u);
  g_assert_cmpuint (audit.irq2_count, ==, stages);
  g_assert_cmpuint (audit.irq0100_count, ==, stages - 1u);
  g_assert_cmpuint (audit.irq0200_count, ==, stages);
  g_assert_cmpuint (audit.nav_count, ==, 1u);
  g_assert_cmpuint (audit.primary_b0_count, ==, stages);
  g_assert_cmpuint (audit.auxiliary_b0_count, ==, stages);
  g_assert_cmpuint (audit.parsed_a0_count, ==, 9u * stages - 1u);
  g_assert_cmpuint (audit.retry_count, ==, 0u);
  g_assert_cmpuint (audit.a0_frame_build_count, ==, 0u);
  g_assert_cmpuint (audit.submit_count, ==, 0u);
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
  GoodixEnrollmentModelConfig config = { 2u, TRUE };
  GoodixEnrollmentPostTlsEventsAudit audit;
  Fixture fixture = { 0 };
  guint8 raw[12];
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, &fixture, &audit, &error);

  fill_raw (0x88u, raw);
  handle_irq (events, 0x32, 0x0002, 0x003f, raw);
  prepare_commit (events, GOODIX_ENROLLMENT_EVENT_COMMAND_22);
  ack = build_ack (0x20);
  g_assert_false (goodix_enrollment_post_tls_events_handle_a0 (
    events, ack, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_post_tls_events_is_failed (events));
  g_assert_cmpuint (audit.rejected_inbound_count, ==, 1u);
  goodix_enrollment_post_tls_events_free (events);
}

static void
test_bad_irq_flags_fail_closed (void)
{
  GoodixEnrollmentModelConfig config = { 2u, TRUE };
  GoodixEnrollmentPostTlsEventsAudit audit;
  Fixture fixture = { 0 };
  guint8 raw[12];
  g_autoptr(GBytes) frame = NULL;
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPostTlsEvents *events =
    goodix_enrollment_post_tls_events_new (
      &config, image_ready, timestamp_ready, &fixture, &audit, &error);

  fill_raw (0x88u, raw);
  frame = build_irq (0x32, 0x0002, 0x0000, raw);
  g_assert_false (goodix_enrollment_post_tls_events_handle_a0 (
    events, frame, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_post_tls_events_is_failed (events));
  goodix_enrollment_post_tls_events_free (events);
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
  return g_test_run ();
}
