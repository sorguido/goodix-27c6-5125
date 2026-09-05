/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_model.h"

#include <string.h>

typedef struct
{
  guint callback_count;
  gboolean reject_stage;
  gboolean set_reject_error;
} Fixture;

static gboolean
stage_ready (GoodixEnrollmentModel *model,
             guint                  stage_index,
             gpointer               user_data,
             GError               **error)
{
  Fixture *fixture = user_data;

  (void) model;
  g_assert_cmpuint (stage_index, ==, fixture->callback_count + 1u);
  if (fixture->reject_stage)
    {
      if (fixture->set_reject_error)
        g_set_error_literal (error, G_FILE_ERROR, G_FILE_ERROR_FAILED,
                             "fixture rejected stage");
      return FALSE;
    }
  fixture->callback_count++;
  return TRUE;
}

static void
feed (GoodixEnrollmentModel *model,
      GoodixEnrollmentEvent  event)
{
  g_autoptr(GError) error = NULL;

  g_assert_cmpint (goodix_enrollment_model_get_expected_event (model), ==,
                   event);
  g_assert_true (goodix_enrollment_model_feed (model, event, &error));
  g_assert_no_error (error);
}

static void
feed_primary (GoodixEnrollmentModel *model)
{
  feed (model, GOODIX_ENROLLMENT_EVENT_IRQ2);
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_22);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_22);
  feed (model, GOODIX_ENROLLMENT_EVENT_PRIMARY_B0);
}

static void
feed_first_transition (GoodixEnrollmentModel *model)
{
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_34);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_34);
  feed (model, GOODIX_ENROLLMENT_EVENT_IRQ0200);
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_20);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_20);
  feed (model, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0);
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_32);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_32);
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_50);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_50);
  feed (model, GOODIX_ENROLLMENT_EVENT_NAV);
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_32);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_32);
}

static void
feed_repeated_transition (GoodixEnrollmentModel *model,
                          gboolean               terminal)
{
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_34);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_34);
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_36);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_36);
  feed (model, GOODIX_ENROLLMENT_EVENT_IRQ0100);
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_20);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_20);
  feed (model, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0);
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_34);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_34);
  feed (model, GOODIX_ENROLLMENT_EVENT_IRQ0200);
  if (!terminal)
    {
      feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_32);
      feed (model, GOODIX_ENROLLMENT_EVENT_ACK_32);
    }
}

static void
run_profile (guint required_stages)
{
  GoodixEnrollmentModelConfig config = { required_stages };
  GoodixEnrollmentModelAudit audit;
  Fixture fixture = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentModel *model = goodix_enrollment_model_new (
    &config, stage_ready, &fixture, &audit, &error);

  g_assert_nonnull (model);
  g_assert_no_error (error);
  for (guint stage = 1u; stage <= required_stages; stage++)
    {
      feed_primary (model);
      if (stage == 1u)
        feed_first_transition (model);
      else
        feed_repeated_transition (model, stage == required_stages);
    }

  g_assert_true (goodix_enrollment_model_is_complete (model));
  g_assert_false (goodix_enrollment_model_is_failed (model));
  g_assert_cmpuint (fixture.callback_count, ==, required_stages);
  g_assert_cmpuint (audit.configured_required_stage_count, ==,
                    required_stages);
  g_assert_cmpuint (audit.completed_stage_count, ==, required_stages);
  g_assert_cmpuint (audit.primary_b0_count, ==, required_stages);
  g_assert_cmpuint (audit.auxiliary_b0_count, ==, required_stages);
  g_assert_cmpuint (audit.libfprint_stage_report_count, ==, required_stages);
  g_assert_cmpuint (audit.first_nav_transition_count, ==, 1u);
  g_assert_cmpuint (audit.repeated_rearm_transition_count, ==,
                    required_stages - 2u);
  g_assert_cmpuint (audit.terminal_transition_count, ==, 1u);
  g_assert_cmpuint (audit.inter_stage_rearm_count, ==,
                    required_stages - 1u);
  g_assert_cmpuint (audit.unexpected_event_count, ==, 0u);
  g_assert_true (audit.complete);
  g_assert_false (audit.failed);
  goodix_enrollment_model_free (model);
}

static void
test_configurable_profiles (void)
{
  run_profile (2u);
  run_profile (3u);
  run_profile (21u);
}

static void
test_auxiliary_does_not_report_stage (void)
{
  GoodixEnrollmentModelConfig config = { 2u };
  GoodixEnrollmentModelAudit audit;
  Fixture fixture = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentModel *model = goodix_enrollment_model_new (
    &config, stage_ready, &fixture, &audit, &error);

  g_assert_nonnull (model);
  feed_primary (model);
  g_assert_cmpuint (fixture.callback_count, ==, 1u);
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_34);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_34);
  feed (model, GOODIX_ENROLLMENT_EVENT_IRQ0200);
  feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_20);
  feed (model, GOODIX_ENROLLMENT_EVENT_ACK_20);
  feed (model, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0);
  g_assert_cmpuint (audit.auxiliary_b0_count, ==, 1u);
  g_assert_cmpuint (audit.libfprint_stage_report_count, ==, 1u);
  g_assert_cmpuint (fixture.callback_count, ==, 1u);

  goodix_enrollment_model_free (model);
}

static void
test_mismatch_is_terminal (void)
{
  GoodixEnrollmentModelConfig config = { 21u };
  GoodixEnrollmentModelAudit audit;
  Fixture fixture = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentModel *model = goodix_enrollment_model_new (
    &config, stage_ready, &fixture, &audit, &error);

  g_assert_nonnull (model);
  g_assert_false (goodix_enrollment_model_feed (
    model, GOODIX_ENROLLMENT_EVENT_COMMAND_22, &error));
  g_assert_nonnull (error);
  g_assert_nonnull (strstr (error->message, "expected IRQ2"));
  g_assert_nonnull (strstr (error->message, "observed COMMAND_22"));
  g_assert_true (goodix_enrollment_model_is_failed (model));
  g_assert_false (goodix_enrollment_model_is_complete (model));
  g_assert_true (audit.failed);
  g_assert_cmpuint (audit.unexpected_event_count, ==, 1u);
  g_assert_cmpint (goodix_enrollment_model_get_expected_event (model), ==,
                   GOODIX_ENROLLMENT_EVENT_NONE);

  goodix_enrollment_model_free (model);
}

static void
test_callback_failure_is_terminal (void)
{
  for (guint with_error = 0u; with_error < 2u; with_error++)
    {
      GoodixEnrollmentModelConfig config = { 2u };
      GoodixEnrollmentModelAudit audit;
      Fixture fixture = { 0 };
      g_autoptr(GError) error = NULL;
      GoodixEnrollmentModel *model;

      fixture.reject_stage = TRUE;
      fixture.set_reject_error = with_error != 0u;
      model = goodix_enrollment_model_new (
        &config, stage_ready, &fixture, &audit, &error);
      g_assert_nonnull (model);
      feed (model, GOODIX_ENROLLMENT_EVENT_IRQ2);
      feed (model, GOODIX_ENROLLMENT_EVENT_COMMAND_22);
      feed (model, GOODIX_ENROLLMENT_EVENT_ACK_22);
      g_assert_false (goodix_enrollment_model_feed (
        model, GOODIX_ENROLLMENT_EVENT_PRIMARY_B0, &error));
      g_assert_nonnull (error);
      g_assert_true (goodix_enrollment_model_is_failed (model));
      g_assert_cmpuint (audit.primary_b0_count, ==, 1u);
      g_assert_cmpuint (audit.completed_stage_count, ==, 0u);
      g_assert_cmpuint (audit.libfprint_stage_report_count, ==, 0u);
      goodix_enrollment_model_free (model);
    }
}

static void
test_post_completion_rejected_without_audit_corruption (void)
{
  GoodixEnrollmentModelConfig config = { 2u };
  GoodixEnrollmentModelAudit audit;
  Fixture fixture = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentModel *model = goodix_enrollment_model_new (
    &config, stage_ready, &fixture, &audit, &error);

  g_assert_nonnull (model);
  feed_primary (model);
  feed_first_transition (model);
  feed_primary (model);
  feed_repeated_transition (model, TRUE);
  g_assert_true (goodix_enrollment_model_is_complete (model));
  g_assert_false (goodix_enrollment_model_feed (
    model, GOODIX_ENROLLMENT_EVENT_IRQ2, &error));
  g_assert_nonnull (error);
  g_assert_true (audit.complete);
  g_assert_false (audit.failed);
  g_assert_cmpuint (audit.unexpected_event_count, ==, 0u);
  goodix_enrollment_model_free (model);
}

static void
test_invalid_stage_count (void)
{
  GoodixEnrollmentModelConfig config = { 1u };
  Fixture fixture = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentModel *model = goodix_enrollment_model_new (
    &config, stage_ready, &fixture, NULL, &error);

  g_assert_null (model);
  g_assert_nonnull (error);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d279-11/configurable-profiles",
                   test_configurable_profiles);
  g_test_add_func ("/d279-11/auxiliary-not-stage",
                   test_auxiliary_does_not_report_stage);
  g_test_add_func ("/d279-11/mismatch-terminal",
                   test_mismatch_is_terminal);
  g_test_add_func ("/d279-11/callback-failure-terminal",
                   test_callback_failure_is_terminal);
  g_test_add_func ("/d279-11/post-completion-audit-stable",
                   test_post_completion_rejected_without_audit_corruption);
  g_test_add_func ("/d279-11/invalid-stage-count",
                   test_invalid_stage_count);
  return g_test_run ();
}
