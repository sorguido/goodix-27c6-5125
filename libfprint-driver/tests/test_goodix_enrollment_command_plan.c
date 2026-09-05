/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_command_plan.h"

#include <fpi-image.h>

typedef struct
{
  guint image_count;
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
  g_assert_cmpuint (stage_index, ==, fixture->image_count + 1u);
  g_assert_true (FP_IS_IMAGE (image));
  fixture->image_count++;
  return TRUE;
}

static void
observe (GoodixEnrollmentCommandPlan *plan,
         GoodixEnrollmentEvent        event)
{
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_enrollment_command_plan_observe (
    plan, event, NULL, 0u, &error));
  g_assert_no_error (error);
}

static void
observe_primary (GoodixEnrollmentCommandPlan *plan,
                 guint                        stage)
{
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  g_autoptr(GError) error = NULL;

  for (gsize i = 0; i < G_N_ELEMENTS (samples); i++)
    samples[i] = (uint16_t) ((i + stage * 53u) & GOODIX_SENSOR_SAMPLE_MAX);
  g_assert_true (goodix_enrollment_command_plan_observe (
    plan, GOODIX_ENROLLMENT_EVENT_PRIMARY_B0, samples,
    G_N_ELEMENTS (samples), &error));
  g_assert_no_error (error);
}

static void
commit (GoodixEnrollmentCommandPlan   *plan,
        GoodixEnrollmentEvent          event,
        guint8                         control,
        GoodixEnrollmentCommandPurpose purpose,
        GoodixEnrollmentBodyClass      body_class,
        guint                          stage)
{
  GoodixEnrollmentCommandIntent intent;
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_enrollment_command_plan_peek (plan, &intent));
  g_assert_cmpint (intent.event, ==, event);
  g_assert_cmphex (intent.control, ==, control);
  g_assert_cmpint (intent.purpose, ==, purpose);
  g_assert_cmpint (intent.body_class, ==, body_class);
  g_assert_cmpuint (intent.stage_index, ==, stage);
  g_assert_false (intent.serializable);
  g_assert_true (goodix_enrollment_command_plan_commit (plan, event, &error));
  g_assert_no_error (error);
}

static void
feed_primary_prefix (GoodixEnrollmentCommandPlan *plan,
                     guint                        stage)
{
  observe (plan, GOODIX_ENROLLMENT_EVENT_IRQ2);
  commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_22, 0x22,
          GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRIMARY_ACQUIRE,
          GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, stage);
  observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_22);
  observe_primary (plan, stage);
}

static void
feed_first_transition (GoodixEnrollmentCommandPlan *plan)
{
  commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_34, 0x34,
          GOODIX_ENROLLMENT_COMMAND_PURPOSE_FINGER_UP,
          GOODIX_ENROLLMENT_BODY_FDT_0A01, 1u);
  observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_34);
  observe (plan, GOODIX_ENROLLMENT_EVENT_IRQ0200);
  commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_20, 0x20,
          GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUXILIARY_TRANSITION,
          GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, 1u);
  observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_20);
  observe (plan, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0);
  commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_32, 0x32,
          GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV_PREPARE,
          GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801, 1u);
  observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_32);
  commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_50, 0x50,
          GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV,
          GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, 1u);
  observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_50);
  observe (plan, GOODIX_ENROLLMENT_EVENT_NAV);
  commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_32, 0x32,
          GOODIX_ENROLLMENT_COMMAND_PURPOSE_INTER_STAGE_REARM,
          GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801, 1u);
  observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_32);
}

static void
feed_repeated_transition (GoodixEnrollmentCommandPlan *plan,
                          guint                        stage,
                          gboolean                     terminal)
{
  commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_34, 0x34,
          GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRE_AUX_FDT,
          GOODIX_ENROLLMENT_BODY_FDT_0A01, stage);
  observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_34);
  commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_36, 0x36,
          GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUX_FDT_SCAN,
          GOODIX_ENROLLMENT_BODY_FDT_0901, stage);
  observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_36);
  observe (plan, GOODIX_ENROLLMENT_EVENT_IRQ0100);
  commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_20, 0x20,
          GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUXILIARY_TRANSITION,
          GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, stage);
  observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_20);
  observe (plan, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0);
  commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_34, 0x34,
          GOODIX_ENROLLMENT_COMMAND_PURPOSE_FINGER_UP,
          GOODIX_ENROLLMENT_BODY_FDT_0A01, stage);
  observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_34);
  observe (plan, GOODIX_ENROLLMENT_EVENT_IRQ0200);
  if (!terminal)
    {
      commit (plan, GOODIX_ENROLLMENT_EVENT_COMMAND_32, 0x32,
              GOODIX_ENROLLMENT_COMMAND_PURPOSE_INTER_STAGE_REARM,
              GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801, stage);
      observe (plan, GOODIX_ENROLLMENT_EVENT_ACK_32);
    }
}

static void
run_profile (guint stages)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = stages,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentCommandPlanAudit audit;
  Fixture fixture = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentCommandPlan *plan = goodix_enrollment_command_plan_new (
    &config, image_ready, &fixture, &audit, &error);

  g_assert_nonnull (plan);
  g_assert_no_error (error);
  for (guint stage = 1u; stage <= stages; stage++)
    {
      feed_primary_prefix (plan, stage);
      if (stage == 1u)
        feed_first_transition (plan);
      else
        feed_repeated_transition (plan, stage, stage == stages);
    }
  g_assert_true (goodix_enrollment_command_plan_is_complete (plan));
  g_assert_false (goodix_enrollment_command_plan_is_failed (plan));
  g_assert_cmpuint (fixture.image_count, ==, stages);
  g_assert_cmpuint (audit.committed_command_count, ==, 6u * stages - 1u);
  g_assert_cmpuint (audit.command_20_count, ==, stages);
  g_assert_cmpuint (audit.command_22_count, ==, stages);
  g_assert_cmpuint (audit.command_32_count, ==, stages);
  g_assert_cmpuint (audit.command_34_count, ==, 2u * stages - 1u);
  g_assert_cmpuint (audit.command_36_count, ==, stages - 1u);
  g_assert_cmpuint (audit.command_50_count, ==, 1u);
  g_assert_cmpuint (audit.pre_aux_fdt_count, ==, stages - 1u);
  g_assert_cmpuint (audit.finger_up_count, ==, stages);
  g_assert_cmpuint (audit.first_nav_prepare_count, ==, 1u);
  g_assert_cmpuint (audit.inter_stage_rearm_count, ==, stages - 1u);
  g_assert_cmpuint (audit.retry_count, ==, 0u);
  g_assert_cmpuint (audit.serialized_command_count, ==, 0u);
  goodix_enrollment_command_plan_free (plan);
}

static void
test_profiles (void)
{
  run_profile (2u);
  run_profile (3u);
  run_profile (21u);
}

static void
test_wrong_commit_fails_closed (void)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentCommandPlanAudit audit;
  Fixture fixture = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentCommandPlan *plan = goodix_enrollment_command_plan_new (
    &config, image_ready, &fixture, &audit, &error);

  g_assert_nonnull (plan);
  observe (plan, GOODIX_ENROLLMENT_EVENT_IRQ2);
  g_assert_false (goodix_enrollment_command_plan_commit (
    plan, GOODIX_ENROLLMENT_EVENT_COMMAND_34, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_command_plan_is_failed (plan));
  g_assert_cmpuint (audit.committed_command_count, ==, 0u);
  g_assert_cmpuint (audit.serialized_command_count, ==, 0u);
  goodix_enrollment_command_plan_free (plan);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d279-11-command-plan/configurable-profiles",
                   test_profiles);
  g_test_add_func ("/d279-11-command-plan/wrong-commit-fails-closed",
                   test_wrong_commit_fails_closed);
  return g_test_run ();
}
