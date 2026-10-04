/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_diversity.h"

#include <glib.h>
#include <stdint.h>
#include <string.h>

#define FRAME_SIZE 5120u

static void
fill_frame (guint8 *frame,
            guint32 seed)
{
  guint32 state = seed;

  for (guint i = 0u; i < FRAME_SIZE; i++)
    {
      state = state * UINT32_C (1664525) + UINT32_C (1013904223);
      frame[i] = (guint8) (state >> 24);
    }
}

static void
make_near (guint8       *near_frame,
           const guint8 *source)
{
  for (guint i = 0u; i < FRAME_SIZE; i++)
    near_frame[i] = source[i] <= 245u ?
      (guint8) (source[i] + 10u) : (guint8) (source[i] - 10u);
}

static GoodixEnrollmentDiversityDecision
observe_seed (GoodixEnrollmentDiversity          *diversity,
              guint32                             seed,
              const GoodixEnrollmentSampleMetrics *metrics)
{
  guint8 frame[FRAME_SIZE];

  fill_frame (frame, seed);
  return goodix_enrollment_diversity_observe (
    diversity, frame, sizeof frame, metrics);
}

static void
test_candidate_constants (void)
{
  g_assert_cmpuint (GOODIX_ENROLLMENT_DIVERSITY_MIN_ACCEPTED, ==, 12u);
  g_assert_cmpuint (GOODIX_ENROLLMENT_DIVERSITY_NORMAL_TARGET, ==, 16u);
  g_assert_cmpuint (GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES, ==, 20u);
  g_assert_cmpuint (GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS,
                    ==, 36u);
}

static void
test_minimum_and_early_sufficiency (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = 96u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);

  g_assert_nonnull (diversity);
  for (guint sample = 1u;
       sample <= GOODIX_ENROLLMENT_DIVERSITY_MIN_ACCEPTED;
       sample++)
    {
      GoodixEnrollmentDiversityDecision decision = observe_seed (
        diversity, UINT32_C (0x1000) + sample, &metrics);

      if (sample < GOODIX_ENROLLMENT_DIVERSITY_MIN_ACCEPTED)
        g_assert_cmpint (decision, ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
      else
        g_assert_cmpint (decision, ==,
                         GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL);
    }
  g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (diversity),
                    ==, GOODIX_ENROLLMENT_DIVERSITY_MIN_ACCEPTED);
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_template_stage_target (diversity),
    ==, GOODIX_ENROLLMENT_DIVERSITY_MIN_ACCEPTED);
}

static void
test_normal_target (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = 48u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);

  for (guint sample = 1u;
       sample <= GOODIX_ENROLLMENT_DIVERSITY_NORMAL_TARGET;
       sample++)
    {
      GoodixEnrollmentDiversityDecision decision = observe_seed (
        diversity, UINT32_C (0x2000) + sample, &metrics);

      if (sample < GOODIX_ENROLLMENT_DIVERSITY_NORMAL_TARGET)
        g_assert_cmpint (decision, ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
      else
        g_assert_cmpint (decision, ==,
                         GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL);
    }
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_template_stage_target (diversity),
    ==, GOODIX_ENROLLMENT_DIVERSITY_NORMAL_TARGET);
}

static void
test_duplicate_near_and_poor_retry (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = 48u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  GoodixEnrollmentDiversityObservation observation;
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);
  guint8 original[FRAME_SIZE];
  guint8 near_frame[FRAME_SIZE];
  guint8 poor[FRAME_SIZE];

  fill_frame (original, UINT32_C (0x3001));
  make_near (near_frame, original);
  memset (poor, 0x80, sizeof poor);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, original, sizeof original, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, original, sizeof original, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE);
  goodix_enrollment_diversity_get_last_observation (diversity, &observation);
  g_assert_true (observation.exact_duplicate);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, near_frame, sizeof near_frame, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE);
  goodix_enrollment_diversity_get_last_observation (diversity, &observation);
  g_assert_true (observation.near_duplicate);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, near_frame, sizeof near_frame, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE);
  g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (diversity),
                    ==, 1u);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, poor, sizeof poor, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR);
  g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (diversity),
                    ==, 1u);
}

static void
test_continue_to_maximum_and_fail_insufficient (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = GOODIX_ENROLLMENT_DIVERSITY_MIN_SIGFM_KEYPOINTS,
    .sigfm_coverage_mask = UINT64_C (0x0f),
  };
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);

  for (guint sample = 1u;
       sample <= GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES;
       sample++)
    {
      GoodixEnrollmentDiversityDecision decision = observe_seed (
        diversity, UINT32_C (0x4000) + sample, &metrics);

      if (sample < GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES)
        g_assert_cmpint (decision, ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
      else
        g_assert_cmpint (decision, ==,
                         GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED);
    }
  g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (diversity),
                    ==, GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES);
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_template_stage_target (diversity), ==, 0u);
  g_assert_cmpint (observe_seed (diversity, UINT32_C (0x5000), &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED);
  g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (diversity),
                    ==, GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES);
}

static void
test_physical_contact_bound (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = 48u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);
  guint8 frame[FRAME_SIZE];

  fill_frame (frame, UINT32_C (0x6001));
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, frame, sizeof frame, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
  for (guint contact = 2u;
       contact <= GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS;
       contact++)
    {
      GoodixEnrollmentDiversityDecision decision =
        goodix_enrollment_diversity_observe (
          diversity, frame, sizeof frame, &metrics);

      if (contact < GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS)
        g_assert_cmpint (decision, ==,
                         GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE);
      else
        g_assert_cmpint (decision, ==,
                         GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED);
    }
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_physical_attempt_count (diversity),
    ==, GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS);
  g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (diversity),
                    ==, 1u);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/enrollment-v2/constants", test_candidate_constants);
  g_test_add_func ("/enrollment-v2/minimum-and-early-sufficiency",
                   test_minimum_and_early_sufficiency);
  g_test_add_func ("/enrollment-v2/normal-target", test_normal_target);
  g_test_add_func ("/enrollment-v2/duplicate-near-poor",
                   test_duplicate_near_and_poor_retry);
  g_test_add_func ("/enrollment-v2/max-insufficient",
                   test_continue_to_maximum_and_fail_insufficient);
  g_test_add_func ("/enrollment-v2/physical-bound",
                   test_physical_contact_bound);
  return g_test_run ();
}
