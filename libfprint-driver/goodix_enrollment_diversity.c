/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Host-only APP12509 fixed-21 enrollment policy.
 *
 * Enrollment completes exactly at the 21st accepted valid sample.  The
 * poor/unusable quality gate is separate and only keeps an unusable capture
 * out of the template; it never acts as a diversity or completion criterion.
 * Duplicate/near-duplicate detection, SIGFM keypoint counts, coverage, raster
 * range/contrast and raster MAD remain computed as diagnostics, but they do
 * not govern acceptance or completion: a valid duplicate is accepted and
 * counts like any other valid sample.  No policy-side physical-contact
 * maximum exists.  This module contains no transport, device-state or
 * persistent I/O.
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
  AcceptedSample accepted[GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES];
  guint accepted_count;
  guint physical_attempt_count;
  guint template_stage_target;
  guint64 aggregate_coverage_mask;
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

/* Diagnostic-only classification.  It records the nearest-sample MAD, the
 * nearest coverage overlap and the exact/near-duplicate flags in the
 * observation; it never rejects a sample. */
static void
classify_duplicate (const GoodixEnrollmentDiversity *diversity,
                    const guint8                    *frame,
                    const GoodixEnrollmentSampleMetrics *metrics,
                    GoodixEnrollmentDiversityObservation *observation)
{
  if (diversity->accepted_count == 0u)
    return;
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
        observation->exact_duplicate = TRUE;
      if (mad < GOODIX_ENROLLMENT_DIVERSITY_NEAR_MAD_LIMIT &&
          coverage >= GOODIX_ENROLLMENT_DIVERSITY_NEAR_COVERAGE_PERCENT &&
          keypoints_are_near (metrics->sigfm_keypoints,
                              accepted->sigfm_keypoints))
        observation->near_duplicate = TRUE;
    }
}

static gboolean
is_poor (const GoodixEnrollmentDiversity *diversity,
         const GoodixEnrollmentSampleMetrics *metrics,
         guint coverage_cells)
{
  return metrics->sigfm_keypoints <
           GOODIX_ENROLLMENT_DIVERSITY_MIN_SIGFM_KEYPOINTS ||
         coverage_cells < GOODIX_ENROLLMENT_DIVERSITY_MIN_COVERAGE_CELLS ||
         diversity->last.raster_range <
           GOODIX_ENROLLMENT_DIVERSITY_MIN_RASTER_RANGE ||
         diversity->last.raster_contrast <
           GOODIX_ENROLLMENT_DIVERSITY_MIN_RASTER_CONTRAST;
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

  /* A completed fixed-21 enrollment is terminal: no 22nd accepted sample is
   * reachable, and no physical-contact counter can produce a decision. */
  if (diversity == NULL || frame == NULL || metrics == NULL ||
      frame_size != diversity->frame_size || diversity->terminal)
    return GOODIX_ENROLLMENT_DIVERSITY_FAILED;

  diversity->physical_attempt_count++;
  diversity->last = (GoodixEnrollmentDiversityObservation) { 0 };
  diversity->last.sigfm_keypoints = metrics->sigfm_keypoints;
  coverage_cells = count_bits (metrics->sigfm_coverage_mask);
  diversity->last.sigfm_coverage_cells = coverage_cells;
  raster_quality (frame, frame_size, &diversity->last.raster_range,
                  &diversity->last.raster_contrast);

  /* Poor/unusable gate: retry without advancing the accepted count.  There
   * is no bound on how often this may happen. */
  if (is_poor (diversity, metrics, coverage_cells))
    {
      record_decision (diversity, GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR);
      return GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR;
    }

  /* Duplicate/near-duplicate flags stay diagnostic; a valid sample is
   * accepted regardless of its similarity to earlier samples. */
  classify_duplicate (diversity, frame, metrics, &diversity->last);

  destination = &diversity->accepted[diversity->accepted_count];
  destination->frame = g_try_malloc (frame_size);
  if (destination->frame == NULL)
    {
      diversity->terminal = TRUE;
      record_decision (diversity, GOODIX_ENROLLMENT_DIVERSITY_FAILED);
      return GOODIX_ENROLLMENT_DIVERSITY_FAILED;
    }
  memcpy (destination->frame, frame, frame_size);
  destination->sigfm_keypoints = metrics->sigfm_keypoints;
  destination->sigfm_coverage_mask = metrics->sigfm_coverage_mask;
  destination->raster_contrast = diversity->last.raster_contrast;
  diversity->accepted_count++;
  diversity->aggregate_coverage_mask |= metrics->sigfm_coverage_mask;

  /* Completion is exactly the 21st accepted valid sample: no coverage,
   * keypoint, contrast or duplicate heuristic can complete earlier. */
  if (diversity->accepted_count ==
      GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES)
    {
      diversity->template_stage_target = diversity->accepted_count;
      diversity->terminal = TRUE;
      record_decision (diversity,
                       GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL);
      return GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL;
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
