/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_diversity.h"

/* Offline verification point 10: the fixed-21 policy must not define any
 * policy-side physical-attempt maximum.  This is a compile-time proof; the
 * behavioral proofs below show contacts exceeding 21 with retries. */
#if defined(GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS) || \
    defined(GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES) || \
    defined(GOODIX_ENROLLMENT_DIVERSITY_MIN_ACCEPTED) || \
    defined(GOODIX_ENROLLMENT_DIVERSITY_NORMAL_TARGET)
#error "fixed-21 policy must not carry bounded-v2 acceptance or contact caps"
#endif

#include <glib.h>
#include <stdint.h>
#include <string.h>

#define FRAME_SIZE 5120u
/* A contact count far above 21 used to prove retries are unbounded. */
#define UNBOUNDED_POOR_CONTACTS 40u

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
test_fixed_21_constants (void)
{
  g_assert_cmpuint (GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES,
                    ==, 21u);
}

/* Points 1 and 2: 20 consecutive valid samples never complete; the 21st
 * valid sample is terminal.  Point 8 (no anticipation): even maximal
 * coverage/keypoint metrics cannot complete before the 21st accepted
 * sample. */
static void
test_completion_exactly_at_21st_accepted (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = 96u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);

  g_assert_nonnull (diversity);
  for (guint sample = 1u;
       sample <= GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES;
       sample++)
    {
      GoodixEnrollmentDiversityDecision decision = observe_seed (
        diversity, UINT32_C (0x1000) + sample, &metrics);

      if (sample < GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES)
        {
          g_assert_cmpint (decision, ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
          g_assert_cmpuint (
            goodix_enrollment_diversity_get_template_stage_target (diversity),
            ==, 0u);
        }
      else
        g_assert_cmpint (decision, ==,
                         GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL);
      g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (
                          diversity), ==, sample);
    }
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_template_stage_target (diversity),
    ==, GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES);
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_physical_attempt_count (diversity),
    ==, GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES);
}

/* Point 3: no 22nd sample is acceptable after completion. */
static void
test_no_22nd_accepted_sample (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = 96u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);

  for (guint sample = 1u;
       sample <= GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES;
       sample++)
    observe_seed (diversity, UINT32_C (0x2000) + sample, &metrics);
  g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (diversity),
                    ==, GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES);
  for (guint extra = 0u; extra < 3u; extra++)
    {
      g_assert_cmpint (observe_seed (diversity,
                                     UINT32_C (0x3000) + extra, &metrics),
                       ==, GOODIX_ENROLLMENT_DIVERSITY_FAILED);
      g_assert_cmpuint (
        goodix_enrollment_diversity_get_accepted_count (diversity),
        ==, GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES);
    }
}

/* Point 4: interleaved poor/unusable captures retry without advancing the
 * accepted count. */
static void
test_poor_interleaved_retries_without_progress (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = 48u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);
  guint8 poor[FRAME_SIZE];

  memset (poor, 0x80, sizeof poor);
  for (guint sample = 1u; sample <= 5u; sample++)
    {
      g_assert_cmpint (observe_seed (diversity,
                                     UINT32_C (0x4000) + sample, &metrics),
                       ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
      /* A flat raster fails the quality gate even with strong SIGFM
       * metrics: the poor gate is raster-visible and separate. */
      g_assert_cmpint (goodix_enrollment_diversity_observe (
                         diversity, poor, sizeof poor, &metrics),
                       ==, GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR);
      g_assert_cmpuint (
        goodix_enrollment_diversity_get_accepted_count (diversity),
        ==, sample);
    }
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_physical_attempt_count (diversity),
    ==, 10u);
  /* A capture with too few SIGFM keypoints is poor even on a textured
   * raster: the gate is not a diversity criterion. */
  {
    GoodixEnrollmentSampleMetrics few_keypoints = {
      .sigfm_keypoints = GOODIX_ENROLLMENT_DIVERSITY_MIN_SIGFM_KEYPOINTS - 1u,
      .sigfm_coverage_mask = G_MAXUINT64,
    };
    g_assert_cmpint (observe_seed (diversity, UINT32_C (0x4100),
                                   &few_keypoints),
                     ==, GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR);
    g_assert_cmpuint (
      goodix_enrollment_diversity_get_accepted_count (diversity), ==, 5u);
  }
}

/* Points 5 and 10: physical contacts may exceed 21 without bound when
 * retries occur; completion still happens exactly at the 21st accepted
 * sample. */
static void
test_unbounded_physical_contacts (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = 48u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);
  guint8 poor[FRAME_SIZE];

  memset (poor, 0x80, sizeof poor);
  for (guint contact = 0u; contact < UNBOUNDED_POOR_CONTACTS; contact++)
    g_assert_cmpint (goodix_enrollment_diversity_observe (
                       diversity, poor, sizeof poor, &metrics),
                     ==, GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR);
  for (guint sample = 1u;
       sample < GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES;
       sample++)
    {
      g_assert_cmpint (observe_seed (diversity,
                                     UINT32_C (0x5000) + sample, &metrics),
                       ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
      /* Interleave further poor contacts well beyond 21 total contacts. */
      g_assert_cmpint (goodix_enrollment_diversity_observe (
                         diversity, poor, sizeof poor, &metrics),
                       ==, GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR);
    }
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_physical_attempt_count (diversity), >,
    GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES);
  g_assert_cmpint (
    observe_seed (diversity,
                  UINT32_C (0x5000) +
                    GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES,
                  &metrics),
    ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL);
  g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (diversity),
                    ==, GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES);
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_physical_attempt_count (diversity),
    ==, UNBOUNDED_POOR_CONTACTS +
          2u * GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES - 1u);
}

/* Points 6, 8 and 9: a valid exact duplicate is ACCEPTED and counts; exact
 * duplicates neither anticipate completion (samples 1..20 of one identical
 * frame never complete) nor block it (the 21st identical frame completes). */
static void
test_exact_duplicate_accepted_and_counts (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = 96u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  GoodixEnrollmentDiversityObservation observation;
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);
  guint8 frame[FRAME_SIZE];

  fill_frame (frame, UINT32_C (0x6001));
  for (guint sample = 1u;
       sample <= GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES;
       sample++)
    {
      GoodixEnrollmentDiversityDecision decision =
        goodix_enrollment_diversity_observe (
          diversity, frame, sizeof frame, &metrics);

      goodix_enrollment_diversity_get_last_observation (diversity,
                                                        &observation);
      if (sample < GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES)
        {
          g_assert_cmpint (decision, ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
          g_assert_cmpuint (
            goodix_enrollment_diversity_get_template_stage_target (diversity),
            ==, 0u);
        }
      else
        g_assert_cmpint (decision, ==,
                         GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL);
      if (sample > 1u)
        {
          g_assert_true (observation.exact_duplicate);
          g_assert_cmpuint (observation.nearest_mad, ==, 0u);
        }
      g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (
                          diversity), ==, sample);
    }
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_template_stage_target (diversity),
    ==, GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, frame, sizeof frame, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_FAILED);
}

/* Point 7: a valid near-duplicate is ACCEPTED and counts. */
static void
test_near_duplicate_accepted_and_counts (void)
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

  fill_frame (original, UINT32_C (0x7001));
  make_near (near_frame, original);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, original, sizeof original, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, near_frame, sizeof near_frame, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
  goodix_enrollment_diversity_get_last_observation (diversity, &observation);
  g_assert_true (observation.near_duplicate);
  g_assert_false (observation.exact_duplicate);
  g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (diversity),
                    ==, 2u);
  /* Alternating the two near frames keeps accepting and counting. */
  for (guint sample = 3u;
       sample <= GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES;
       sample++)
    {
      const guint8 *frame = sample % 2u == 0u ? near_frame : original;
      GoodixEnrollmentDiversityDecision expected =
        sample < GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES ?
          GOODIX_ENROLLMENT_DIVERSITY_ACCEPT :
          GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL;

      g_assert_cmpint (goodix_enrollment_diversity_observe (
                         diversity, frame, FRAME_SIZE, &metrics),
                       ==, expected);
      g_assert_cmpuint (
        goodix_enrollment_diversity_get_accepted_count (diversity),
        ==, sample);
    }
}

/* Point 11: diversity metrics remain present in every observation but are
 * not decisional; only the accepted-sample count drives completion. */
static void
test_metrics_present_but_not_decisional (void)
{
  GoodixEnrollmentSampleMetrics strong = {
    .sigfm_keypoints = 120u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  GoodixEnrollmentSampleMetrics minimal = {
    .sigfm_keypoints = GOODIX_ENROLLMENT_DIVERSITY_MIN_SIGFM_KEYPOINTS,
    .sigfm_coverage_mask = UINT64_C (0x0f),
  };
  GoodixEnrollmentDiversityObservation observation;
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);

  /* Maximal metrics on the first samples cannot anticipate completion. */
  for (guint sample = 1u; sample <= 5u; sample++)
    {
      g_assert_cmpint (observe_seed (diversity,
                                     UINT32_C (0x8000) + sample, &strong),
                       ==, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
      goodix_enrollment_diversity_get_last_observation (diversity,
                                                        &observation);
      g_assert_cmpuint (observation.sigfm_keypoints, ==, 120u);
      g_assert_cmpuint (observation.sigfm_coverage_cells, ==, 64u);
      g_assert_cmpuint (observation.aggregate_coverage_cells, ==, 64u);
      g_assert_cmpuint (observation.raster_range, >, 0u);
      g_assert_cmpuint (observation.raster_contrast, >, 0u);
      g_assert_cmpuint (observation.accepted_sample_count, ==, sample);
      g_assert_cmpuint (
        goodix_enrollment_diversity_get_template_stage_target (diversity),
        ==, 0u);
    }
  /* Minimal gate-passing metrics are accepted exactly like strong ones;
   * weak diversity never blocks or delays completion beyond the count. */
  for (guint sample = 6u;
       sample <= GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES;
       sample++)
    {
      GoodixEnrollmentDiversityDecision expected =
        sample < GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES ?
          GOODIX_ENROLLMENT_DIVERSITY_ACCEPT :
          GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL;

      g_assert_cmpint (observe_seed (diversity,
                                     UINT32_C (0x9000) + sample, &minimal),
                       ==, expected);
      goodix_enrollment_diversity_get_last_observation (diversity,
                                                        &observation);
      g_assert_cmpuint (observation.decision, ==, (guint) expected);
      g_assert_cmpuint (observation.physical_attempt_count, ==, sample);
    }
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_template_stage_target (diversity),
    ==, GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES);
}

/* Invalid input and post-completion observations fail closed without
 * touching counters. */
static void
test_invalid_input_fails_closed (void)
{
  GoodixEnrollmentSampleMetrics metrics = {
    .sigfm_keypoints = 48u,
    .sigfm_coverage_mask = G_MAXUINT64,
  };
  g_autoptr(GoodixEnrollmentDiversity) diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);
  guint8 frame[FRAME_SIZE];

  fill_frame (frame, UINT32_C (0xa001));
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     NULL, frame, sizeof frame, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_FAILED);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, NULL, sizeof frame, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_FAILED);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, frame, sizeof frame, NULL),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_FAILED);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, frame, FRAME_SIZE - 1u, &metrics),
                   ==, GOODIX_ENROLLMENT_DIVERSITY_FAILED);
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_physical_attempt_count (diversity),
    ==, 0u);
  g_assert_cmpuint (goodix_enrollment_diversity_get_accepted_count (diversity),
                    ==, 0u);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/enrollment-fixed-21/constants",
                   test_fixed_21_constants);
  g_test_add_func ("/enrollment-fixed-21/completion-at-21st",
                   test_completion_exactly_at_21st_accepted);
  g_test_add_func ("/enrollment-fixed-21/no-22nd-sample",
                   test_no_22nd_accepted_sample);
  g_test_add_func ("/enrollment-fixed-21/poor-interleaved",
                   test_poor_interleaved_retries_without_progress);
  g_test_add_func ("/enrollment-fixed-21/unbounded-physical-contacts",
                   test_unbounded_physical_contacts);
  g_test_add_func ("/enrollment-fixed-21/exact-duplicate-accepted",
                   test_exact_duplicate_accepted_and_counts);
  g_test_add_func ("/enrollment-fixed-21/near-duplicate-accepted",
                   test_near_duplicate_accepted_and_counts);
  g_test_add_func ("/enrollment-fixed-21/metrics-not-decisional",
                   test_metrics_present_but_not_decisional);
  g_test_add_func ("/enrollment-fixed-21/invalid-input-fails-closed",
                   test_invalid_input_fails_closed);
  return g_test_run ();
}
