/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Host-only APP12509 enrollment-v2 candidate selector.
 *
 * Raster MAD is retained only as an auxiliary duplicate signal. Acceptance
 * and completion also require observable SIGFM keypoint coverage and raster
 * quality. The thresholds in the public header are experimental candidate
 * parameters, not universal biometric claims. This module contains no
 * transport, device-state or persistent I/O.
 */
#include "goodix_enrollment_diversity.h"

#include <string.h>

typedef struct
{
  guint8 *frame;
  guint sigfm_keypoints;
  guint64 sigfm_coverage_mask;
  guint raster_contrast;
} AcceptedSample;

struct _GoodixEnrollmentDiversity
{
  gsize frame_size;
  AcceptedSample accepted[GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES];
  guint accepted_count;
  guint physical_attempt_count;
  guint template_stage_target;
  guint64 aggregate_coverage_mask;
  guint64 keypoint_total;
  guint64 contrast_total;
  GoodixEnrollmentDiversityObservation last;
  gboolean terminal;
};

static void
secure_clear (gpointer memory,
              gsize    size)
{
  volatile guint8 *cursor = memory;

  while (size-- > 0u)
    *cursor++ = 0u;
}

static guint
count_bits (guint64 value)
{
  guint count = 0u;

  while (value != 0u)
    {
      value &= value - 1u;
      count++;
    }
  return count;
}

GoodixEnrollmentDiversity *
goodix_enrollment_diversity_new (gsize frame_size)
{
  GoodixEnrollmentDiversity *diversity;

  if (frame_size == 0u || frame_size > G_MAXUINT64 / G_MAXUINT8)
    return NULL;
  diversity = g_try_new0 (GoodixEnrollmentDiversity, 1);
  if (diversity != NULL)
    diversity->frame_size = frame_size;
  return diversity;
}

void
goodix_enrollment_diversity_free (GoodixEnrollmentDiversity *diversity)
{
  if (diversity == NULL)
    return;
  for (guint i = 0u; i < G_N_ELEMENTS (diversity->accepted); i++)
    if (diversity->accepted[i].frame != NULL)
      {
        secure_clear (diversity->accepted[i].frame, diversity->frame_size);
        g_free (diversity->accepted[i].frame);
      }
  secure_clear (diversity, sizeof *diversity);
  g_free (diversity);
}

static void
raster_quality (const guint8 *frame,
                gsize         frame_size,
                guint        *range_out,
                guint        *contrast_out)
{
  guint8 minimum = G_MAXUINT8;
  guint8 maximum = 0u;
  guint64 sum = 0u;
  guint64 deviation_sum = 0u;
  guint mean;

  for (gsize i = 0u; i < frame_size; i++)
    {
      minimum = MIN (minimum, frame[i]);
      maximum = MAX (maximum, frame[i]);
      sum += frame[i];
    }
  mean = (guint) ((sum + frame_size / 2u) / frame_size);
  for (gsize i = 0u; i < frame_size; i++)
    deviation_sum += (guint64) ABS ((gint) frame[i] - (gint) mean);

  *range_out = (guint) maximum - (guint) minimum;
  *contrast_out = (guint) ((deviation_sum + frame_size / 2u) / frame_size);
}

static guint
mean_absolute_difference (const GoodixEnrollmentDiversity *diversity,
                          const guint8                    *left,
                          const guint8                    *right)
{
  guint64 difference_sum = 0u;

  for (gsize pixel = 0u; pixel < diversity->frame_size; pixel++)
    difference_sum += (guint64) ABS ((gint) left[pixel] -
                                     (gint) right[pixel]);
  return (guint) ((difference_sum + diversity->frame_size / 2u) /
                  diversity->frame_size);
}

static guint
coverage_similarity_percent (guint64 left,
                             guint64 right)
{
  const guint union_count = count_bits (left | right);

  if (union_count == 0u)
    return 0u;
  return count_bits (left & right) * 100u / union_count;
}

static gboolean
keypoints_are_near (guint left,
                    guint right)
{
  const guint maximum = MAX (left, right);
  const guint difference = maximum - MIN (left, right);

  return maximum != 0u &&
         difference * 100u <=
           maximum * GOODIX_ENROLLMENT_DIVERSITY_NEAR_KEYPOINT_DELTA_PERCENT;
}

static gboolean
is_duplicate (const GoodixEnrollmentDiversity *diversity,
              const guint8                    *frame,
              const GoodixEnrollmentSampleMetrics *metrics,
              GoodixEnrollmentDiversityObservation *observation)
{
  if (diversity->accepted_count == 0u)
    return FALSE;
  observation->nearest_mad = G_MAXUINT;

  for (guint i = 0u; i < diversity->accepted_count; i++)
    {
      const AcceptedSample *accepted = &diversity->accepted[i];
      const guint mad = mean_absolute_difference (
        diversity, frame, accepted->frame);
      const guint coverage = coverage_similarity_percent (
        metrics->sigfm_coverage_mask, accepted->sigfm_coverage_mask);

      observation->nearest_mad = MIN (observation->nearest_mad, mad);
      observation->nearest_coverage_percent =
        MAX (observation->nearest_coverage_percent, coverage);
      if (mad < GOODIX_ENROLLMENT_DIVERSITY_EXACT_MAD_LIMIT)
        {
          observation->exact_duplicate = TRUE;
          return TRUE;
        }
      if (mad < GOODIX_ENROLLMENT_DIVERSITY_NEAR_MAD_LIMIT &&
          coverage >= GOODIX_ENROLLMENT_DIVERSITY_NEAR_COVERAGE_PERCENT &&
          keypoints_are_near (metrics->sigfm_keypoints,
                              accepted->sigfm_keypoints))
        {
          observation->near_duplicate = TRUE;
          return TRUE;
        }
    }
  return FALSE;
}

static gboolean
candidate_sufficient (const GoodixEnrollmentDiversity *diversity,
                      const GoodixEnrollmentSampleMetrics *metrics,
                      guint raster_contrast)
{
  const guint count = diversity->accepted_count + 1u;
  const guint coverage = count_bits (diversity->aggregate_coverage_mask |
                                     metrics->sigfm_coverage_mask);
  const guint average_keypoints =
    (guint) ((diversity->keypoint_total + metrics->sigfm_keypoints) / count);
  const guint average_contrast =
    (guint) ((diversity->contrast_total + raster_contrast) / count);

  if (count < GOODIX_ENROLLMENT_DIVERSITY_MIN_ACCEPTED)
    return FALSE;
  if (coverage >= GOODIX_ENROLLMENT_DIVERSITY_EARLY_COVERAGE_CELLS &&
      average_keypoints >= GOODIX_ENROLLMENT_DIVERSITY_EARLY_AVG_KEYPOINTS &&
      average_contrast >= GOODIX_ENROLLMENT_DIVERSITY_EARLY_AVG_CONTRAST)
    return TRUE;
  return count >= GOODIX_ENROLLMENT_DIVERSITY_NORMAL_TARGET &&
         coverage >= GOODIX_ENROLLMENT_DIVERSITY_NORMAL_COVERAGE_CELLS &&
         average_keypoints >= GOODIX_ENROLLMENT_DIVERSITY_NORMAL_AVG_KEYPOINTS &&
         average_contrast >= GOODIX_ENROLLMENT_DIVERSITY_NORMAL_AVG_CONTRAST;
}

static void
record_decision (GoodixEnrollmentDiversity         *diversity,
                 GoodixEnrollmentDiversityDecision decision)
{
  diversity->last.decision = decision;
  diversity->last.physical_attempt_count = diversity->physical_attempt_count;
  diversity->last.accepted_sample_count = diversity->accepted_count;
  diversity->last.aggregate_coverage_cells =
    count_bits (diversity->aggregate_coverage_mask);
}

GoodixEnrollmentDiversityDecision
goodix_enrollment_diversity_observe (
  GoodixEnrollmentDiversity           *diversity,
  const guint8                        *frame,
  gsize                                frame_size,
  const GoodixEnrollmentSampleMetrics *metrics)
{
  AcceptedSample *destination;
  guint coverage_cells;
  gboolean sufficient;

  if (diversity == NULL || frame == NULL || metrics == NULL ||
      frame_size != diversity->frame_size || diversity->terminal ||
      diversity->physical_attempt_count >=
        GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS)
    return GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED;

  diversity->physical_attempt_count++;
  diversity->last = (GoodixEnrollmentDiversityObservation) { 0 };
  diversity->last.sigfm_keypoints = metrics->sigfm_keypoints;
  coverage_cells = count_bits (metrics->sigfm_coverage_mask);
  diversity->last.sigfm_coverage_cells = coverage_cells;
  raster_quality (frame, frame_size, &diversity->last.raster_range,
                  &diversity->last.raster_contrast);

  if (metrics->sigfm_keypoints <
        GOODIX_ENROLLMENT_DIVERSITY_MIN_SIGFM_KEYPOINTS ||
      coverage_cells < GOODIX_ENROLLMENT_DIVERSITY_MIN_COVERAGE_CELLS ||
      diversity->last.raster_range <
        GOODIX_ENROLLMENT_DIVERSITY_MIN_RASTER_RANGE ||
      diversity->last.raster_contrast <
        GOODIX_ENROLLMENT_DIVERSITY_MIN_RASTER_CONTRAST)
    {
      if (diversity->physical_attempt_count ==
          GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS)
        {
          diversity->terminal = TRUE;
          record_decision (diversity, GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED);
          return GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED;
        }
      record_decision (diversity, GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR);
      return GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR;
    }

  if (is_duplicate (diversity, frame, metrics, &diversity->last))
    {
      if (diversity->physical_attempt_count ==
          GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS)
        {
          diversity->terminal = TRUE;
          record_decision (diversity, GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED);
          return GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED;
        }
      record_decision (diversity,
                       GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE);
      return GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE;
    }

  sufficient = candidate_sufficient (diversity, metrics,
                                     diversity->last.raster_contrast);
  destination = &diversity->accepted[diversity->accepted_count];
  destination->frame = g_try_malloc (frame_size);
  if (destination->frame == NULL)
    {
      diversity->terminal = TRUE;
      record_decision (diversity, GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED);
      return GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED;
    }
  memcpy (destination->frame, frame, frame_size);
  destination->sigfm_keypoints = metrics->sigfm_keypoints;
  destination->sigfm_coverage_mask = metrics->sigfm_coverage_mask;
  destination->raster_contrast = diversity->last.raster_contrast;
  diversity->accepted_count++;
  diversity->aggregate_coverage_mask |= metrics->sigfm_coverage_mask;
  diversity->keypoint_total += metrics->sigfm_keypoints;
  diversity->contrast_total += diversity->last.raster_contrast;

  if (sufficient)
    {
      diversity->template_stage_target = diversity->accepted_count;
      diversity->terminal = TRUE;
      record_decision (diversity,
                       GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL);
      return GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL;
    }
  if (diversity->accepted_count >=
        GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES ||
      diversity->physical_attempt_count >=
        GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS)
    {
      diversity->terminal = TRUE;
      record_decision (diversity, GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED);
      return GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED;
    }
  record_decision (diversity, GOODIX_ENROLLMENT_DIVERSITY_ACCEPT);
  return GOODIX_ENROLLMENT_DIVERSITY_ACCEPT;
}

guint
goodix_enrollment_diversity_get_physical_attempt_count (
  const GoodixEnrollmentDiversity *diversity)
{
  return diversity != NULL ? diversity->physical_attempt_count : 0u;
}

guint
goodix_enrollment_diversity_get_accepted_count (
  const GoodixEnrollmentDiversity *diversity)
{
  return diversity != NULL ? diversity->accepted_count : 0u;
}

guint
goodix_enrollment_diversity_get_template_stage_target (
  const GoodixEnrollmentDiversity *diversity)
{
  return diversity != NULL ? diversity->template_stage_target : 0u;
}

void
goodix_enrollment_diversity_get_last_observation (
  const GoodixEnrollmentDiversity       *diversity,
  GoodixEnrollmentDiversityObservation *observation)
{
  g_return_if_fail (observation != NULL);
  *observation = diversity != NULL ? diversity->last :
    (GoodixEnrollmentDiversityObservation) { 0 };
}
