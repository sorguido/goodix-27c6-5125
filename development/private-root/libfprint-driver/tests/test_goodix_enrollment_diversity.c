/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_diversity.h"

#include <string.h>

#define FRAME_SIZE 32u

static void
fill (guint8 frame[FRAME_SIZE],
      guint8 seed)
{
  for (guint i = 0u; i < FRAME_SIZE; i++)
    frame[i] = (guint8) (seed + i * 11u);
}

static void
test_eight_distinct_terminate (void)
{
  GoodixEnrollmentDiversity *diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);
  guint8 frame[FRAME_SIZE];

  g_assert_nonnull (diversity);
  for (guint i = 0u; i < 8u; i++)
    {
      fill (frame, (guint8) (i * 24u));
      g_assert_cmpint (goodix_enrollment_diversity_observe (
                         diversity, frame, sizeof frame), ==,
                       i == 7u ?
                         GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL :
                         GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
    }
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_physical_attempt_count (diversity), ==,
    8u);
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_distinct_count (diversity), ==, 8u);
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_template_stage_target (diversity), ==,
    8u);
  goodix_enrollment_diversity_free (diversity);
}

static void
test_rocky_duplicate_convergence (void)
{
  GoodixEnrollmentDiversity *diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);
  guint8 distinct[3][FRAME_SIZE];

  g_assert_nonnull (diversity);
  for (guint i = 0u; i < 3u; i++)
    {
      fill (distinct[i], (guint8) (i * 40u));
      g_assert_cmpint (goodix_enrollment_diversity_observe (
                         diversity, distinct[i], FRAME_SIZE), ==,
                       GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
    }
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, distinct[0], FRAME_SIZE), ==,
                   GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, distinct[0], FRAME_SIZE), ==,
                   GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL);
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_template_stage_target (diversity), ==,
    4u);
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_physical_attempt_count (diversity), ==,
    5u);
  goodix_enrollment_diversity_free (diversity);
}

static void
test_strict_mad_boundary (void)
{
  GoodixEnrollmentDiversity *diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);
  guint8 first[FRAME_SIZE] = { 0 };
  guint8 below[FRAME_SIZE];
  guint8 boundary[FRAME_SIZE];

  memset (below, 7, sizeof below);
  memset (boundary, 8, sizeof boundary);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, first, FRAME_SIZE), ==,
                   GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, below, FRAME_SIZE), ==,
                   GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, boundary, FRAME_SIZE), ==,
                   GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
  goodix_enrollment_diversity_free (diversity);
}

static void
test_twenty_contact_bound (void)
{
  GoodixEnrollmentDiversity *diversity =
    goodix_enrollment_diversity_new (FRAME_SIZE);
  guint8 distinct[2][FRAME_SIZE];

  fill (distinct[0], 0u);
  fill (distinct[1], 80u);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, distinct[0], FRAME_SIZE), ==,
                   GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
  g_assert_cmpint (goodix_enrollment_diversity_observe (
                     diversity, distinct[1], FRAME_SIZE), ==,
                   GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
  for (guint attempt = 3u;
       attempt <= GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS;
       attempt++)
    g_assert_cmpint (goodix_enrollment_diversity_observe (
                       diversity, distinct[attempt % 2u], FRAME_SIZE), ==,
                     attempt == GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS ?
                       GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED :
                       GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE);
  g_assert_cmpuint (
    goodix_enrollment_diversity_get_physical_attempt_count (diversity), ==,
    GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS);
  goodix_enrollment_diversity_free (diversity);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d291/diversity/eight-distinct",
                   test_eight_distinct_terminate);
  g_test_add_func ("/d291/diversity/duplicate-convergence",
                   test_rocky_duplicate_convergence);
  g_test_add_func ("/d291/diversity/strict-mad-boundary",
                   test_strict_mad_boundary);
  g_test_add_func ("/d291/diversity/twenty-contact-bound",
                   test_twenty_contact_bound);
  return g_test_run ();
}
