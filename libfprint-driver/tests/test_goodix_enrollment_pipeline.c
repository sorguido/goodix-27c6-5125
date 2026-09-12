/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_pipeline.h"

#include <fpi-image.h>

typedef struct
{
  guint delivery_count;
  FpImage *weak_image;
  gboolean reject;
} Fixture;

typedef struct
{
  guint physical_count;
  guint delivered_count;
} DynamicFixture;

static gboolean
image_ready (GoodixEnrollmentPipeline *pipeline,
             guint                     stage_index,
             FpImage                  *image,
             gpointer                  user_data,
             GError                  **error)
{
  Fixture *fixture = user_data;

  (void) pipeline;
  g_assert_cmpuint (stage_index, ==, fixture->delivery_count + 1u);
  g_assert_true (FP_IS_IMAGE (image));
  g_assert_cmpint (fp_image_get_width (image), ==,
                   GOODIX_CANONICAL_IMAGE_WIDTH);
  g_assert_cmpint (fp_image_get_height (image), ==,
                   GOODIX_CANONICAL_IMAGE_HEIGHT);
  g_assert_cmpfloat (image->ppmm, ==, 0.0);
  if (fixture->reject)
    {
      g_set_error_literal (error, G_FILE_ERROR, G_FILE_ERROR_FAILED,
                           "fixture rejected FpImage");
      return FALSE;
    }
  fixture->delivery_count++;
  fixture->weak_image = image;
  g_object_add_weak_pointer (G_OBJECT (image),
                             (gpointer *) &fixture->weak_image);
  return TRUE;
}

static void
feed_event (GoodixEnrollmentPipeline *pipeline,
            GoodixEnrollmentEvent     event)
{
  g_autoptr(GError) error = NULL;

  g_assert_cmpint (goodix_enrollment_pipeline_get_expected_event (pipeline),
                   ==, event);
  if (!goodix_enrollment_pipeline_feed (pipeline, event, NULL, 0u, &error))
    g_error ("feed %s failed: %s", goodix_enrollment_event_name (event),
             error != NULL ? error->message : "no error");
  g_assert_no_error (error);
}

static void
feed_primary (GoodixEnrollmentPipeline *pipeline,
              guint                     stage,
              Fixture                  *fixture)
{
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  g_autoptr(GError) error = NULL;

  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_IRQ2);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_22);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_22);
  for (gsize i = 0; i < G_N_ELEMENTS (samples); i++)
    samples[i] = (uint16_t) ((i + stage * 97u) & GOODIX_SENSOR_SAMPLE_MAX);
  g_assert_true (goodix_enrollment_pipeline_feed (
    pipeline, GOODIX_ENROLLMENT_EVENT_PRIMARY_B0, samples,
    G_N_ELEMENTS (samples), &error));
  g_assert_no_error (error);
  g_assert_null (fixture->weak_image);
}

static void
feed_first_transition (GoodixEnrollmentPipeline *pipeline)
{
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_34);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_34);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_IRQ0200);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_20);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_20);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_32);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_32);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_50);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_50);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_NAV);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_32);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_32);
}

static void
feed_repeated_transition (GoodixEnrollmentPipeline *pipeline,
                          gboolean                  terminal)
{
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_34);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_34);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_36);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_36);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_IRQ0100);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_20);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_20);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_34);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_34);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_IRQ0200);
  if (!terminal)
    {
      feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_32);
      feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_32);
    }
}

static void
run_profile (guint stages)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = stages,
    .defer_terminal_stage_delivery = TRUE,
    .defer_intermediate_stage_delivery_until_release_ready = TRUE,
  };
  GoodixEnrollmentPipelineAudit audit;
  Fixture fixture = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPipeline *pipeline = goodix_enrollment_pipeline_new (
    &config, image_ready, &fixture, &audit, &error);

  g_assert_nonnull (pipeline);
  g_assert_no_error (error);
  for (guint stage = 1u; stage <= stages; stage++)
    {
      feed_primary (pipeline, stage, &fixture);
      g_assert_cmpuint (audit.fpimage_construct_count, ==, stage);
      g_assert_cmpuint (audit.fpimage_delivery_count, ==, stage - 1u);
      g_assert_cmpuint (audit.protocol.primary_b0_count, ==, stage);
      if (stage == 1u)
        feed_first_transition (pipeline);
      else
        feed_repeated_transition (pipeline, stage == stages);
      g_assert_cmpuint (audit.fpimage_delivery_count, ==, stage);
    }
  g_assert_true (goodix_enrollment_pipeline_is_complete (pipeline));
  g_assert_false (goodix_enrollment_pipeline_is_failed (pipeline));
  g_assert_cmpuint (fixture.delivery_count, ==, stages);
  g_assert_cmpuint (audit.fpimage_construct_count, ==, stages);
  g_assert_cmpuint (audit.fpimage_delivery_count, ==, stages);
  g_assert_cmpuint (audit.auxiliary_fpimage_delivery_count, ==, 0u);
  g_assert_cmpuint (audit.protocol.primary_b0_count, ==, stages);
  g_assert_cmpuint (audit.protocol.auxiliary_b0_count, ==, stages);
  g_assert_false (audit.failed);
  goodix_enrollment_pipeline_free (pipeline);
}

static void
test_configurable_image_delivery (void)
{
  run_profile (2u);
  run_profile (3u);
  run_profile (21u);
}

static void
test_auxiliary_raster_rejected (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPipelineAudit audit;
  Fixture fixture = { 0 };
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT] = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPipeline *pipeline = goodix_enrollment_pipeline_new (
    &config, image_ready, &fixture, &audit, &error);

  g_assert_nonnull (pipeline);
  feed_primary (pipeline, 1u, &fixture);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_34);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_34);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_IRQ0200);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_20);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_20);
  g_assert_false (goodix_enrollment_pipeline_feed (
    pipeline, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0, samples,
    G_N_ELEMENTS (samples), &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_pipeline_is_failed (pipeline));
  g_assert_cmpuint (audit.protocol.auxiliary_b0_count, ==, 0u);
  g_assert_cmpuint (audit.auxiliary_fpimage_delivery_count, ==, 0u);
  goodix_enrollment_pipeline_free (pipeline);
}

static void
test_delivery_failure_is_terminal (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPipelineAudit audit;
  Fixture fixture = { 0 };
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT] = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPipeline *pipeline;

  fixture.reject = TRUE;
  pipeline = goodix_enrollment_pipeline_new (
    &config, image_ready, &fixture, &audit, &error);
  g_assert_nonnull (pipeline);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_IRQ2);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_22);
  feed_event (pipeline, GOODIX_ENROLLMENT_EVENT_ACK_22);
  g_assert_false (goodix_enrollment_pipeline_feed (
    pipeline, GOODIX_ENROLLMENT_EVENT_PRIMARY_B0, samples,
    G_N_ELEMENTS (samples), &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_pipeline_is_failed (pipeline));
  g_assert_cmpuint (audit.fpimage_construct_count, ==, 1u);
  g_assert_cmpuint (audit.fpimage_delivery_count, ==, 0u);
  g_assert_cmpuint (audit.protocol.primary_b0_count, ==, 1u);
  g_assert_cmpuint (audit.protocol.completed_stage_count, ==, 0u);
  goodix_enrollment_pipeline_free (pipeline);
}

static void
test_out_of_order_primary_does_not_construct (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 21u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPipelineAudit audit;
  Fixture fixture = { 0 };
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT] = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPipeline *pipeline = goodix_enrollment_pipeline_new (
    &config, image_ready, &fixture, &audit, &error);

  g_assert_nonnull (pipeline);
  g_assert_false (goodix_enrollment_pipeline_feed (
    pipeline, GOODIX_ENROLLMENT_EVENT_PRIMARY_B0, samples,
    G_N_ELEMENTS (samples), &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_pipeline_is_failed (pipeline));
  g_assert_cmpuint (audit.fpimage_construct_count, ==, 0u);
  g_assert_cmpuint (audit.fpimage_delivery_count, ==, 0u);
  g_assert_cmpuint (audit.protocol.primary_b0_count, ==, 0u);
  g_assert_cmpuint (audit.protocol.unexpected_event_count, ==, 1u);
  goodix_enrollment_pipeline_free (pipeline);
}

static void
test_terminal_pending_image_released_on_mismatch (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentPipelineAudit audit;
  Fixture fixture = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPipeline *pipeline = goodix_enrollment_pipeline_new (
    &config, image_ready, &fixture, &audit, &error);

  g_assert_nonnull (pipeline);
  feed_primary (pipeline, 1u, &fixture);
  feed_first_transition (pipeline);
  feed_primary (pipeline, 2u, &fixture);
  g_assert_cmpuint (fixture.delivery_count, ==, 1u);
  g_assert_cmpuint (audit.fpimage_construct_count, ==, 2u);
  g_assert_cmpuint (audit.fpimage_delivery_count, ==, 1u);
  g_assert_false (goodix_enrollment_pipeline_feed (
    pipeline, GOODIX_ENROLLMENT_EVENT_COMMAND_36, NULL, 0u, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_pipeline_is_failed (pipeline));
  g_assert_cmpuint (fixture.delivery_count, ==, 1u);
  goodix_enrollment_pipeline_free (pipeline);
}

static gboolean
dynamic_image_ready (GoodixEnrollmentPipeline *pipeline,
                     guint                     stage_index,
                     FpImage                  *image,
                     gpointer                  user_data,
                     GError                  **error)
{
  DynamicFixture *fixture = user_data;

  g_assert_true (FP_IS_IMAGE (image));
  fixture->physical_count++;
  g_assert_cmpuint (stage_index, ==, fixture->physical_count);
  if (stage_index == 4u)
    return goodix_enrollment_pipeline_retry_current_stage (pipeline, error);
  fixture->delivered_count++;
  if (stage_index == 5u)
    return goodix_enrollment_pipeline_finish_current_stage (pipeline, error);
  return TRUE;
}

static void
test_dynamic_retry_and_early_terminal (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 4u,
    .max_physical_stage_count = 20u,
    .defer_terminal_stage_delivery_until_release_ready = TRUE,
    .defer_intermediate_stage_delivery_until_release_ready = TRUE,
  };
  GoodixEnrollmentPipelineAudit audit;
  DynamicFixture fixture = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentPipeline *pipeline = goodix_enrollment_pipeline_new (
    &config, dynamic_image_ready, &fixture, &audit, &error);

  g_assert_nonnull (pipeline);
  for (guint physical = 1u; physical <= 5u; physical++)
    {
      Fixture primary_fixture = { 0 };

      feed_primary (pipeline, physical, &primary_fixture);
      if (physical == 1u)
        feed_first_transition (pipeline);
      else
        feed_repeated_transition (pipeline, physical == 5u);
    }
  g_assert_true (goodix_enrollment_pipeline_is_complete (pipeline));
  g_assert_cmpuint (fixture.physical_count, ==, 5u);
  g_assert_cmpuint (fixture.delivered_count, ==, 4u);
  g_assert_cmpuint (audit.protocol.observed_primary_stage_count, ==, 5u);
  g_assert_cmpuint (audit.protocol.completed_stage_count, ==, 4u);
  g_assert_cmpuint (audit.protocol.retry_stage_count, ==, 1u);
  g_assert_cmpuint (audit.protocol.terminal_transition_count, ==, 1u);
  g_assert_cmpuint (audit.fpimage_construct_count, ==, 5u);
  g_assert_cmpuint (audit.fpimage_delivery_count, ==, 4u);
  goodix_enrollment_pipeline_free (pipeline);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d279-11-pipeline/configurable-image-delivery",
                   test_configurable_image_delivery);
  g_test_add_func ("/d279-11-pipeline/auxiliary-raster-rejected",
                   test_auxiliary_raster_rejected);
  g_test_add_func ("/d279-11-pipeline/delivery-failure-terminal",
                   test_delivery_failure_is_terminal);
  g_test_add_func ("/d279-11-pipeline/out-of-order-primary-no-construct",
                   test_out_of_order_primary_does_not_construct);
  g_test_add_func ("/d279-11-pipeline/terminal-pending-mismatch",
                   test_terminal_pending_image_released_on_mismatch);
  g_test_add_func ("/d291-pipeline/dynamic-retry-early-terminal",
                   test_dynamic_retry_and_early_terminal);
  return g_test_run ();
}
