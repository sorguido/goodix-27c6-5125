/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_DIVERSITY_H
#define GOODIX_ENROLLMENT_DIVERSITY_H

#include <glib.h>

G_BEGIN_DECLS

/* Empirical APP12509 enrollment-v2 candidate bounds. These values are not
 * universal biometric constants and require target-live qualification. */
#define GOODIX_ENROLLMENT_DIVERSITY_MIN_ACCEPTED 12u
#define GOODIX_ENROLLMENT_DIVERSITY_NORMAL_TARGET 16u
#define GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES 20u
#define GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS 36u

/* Experimental quality/diversity thresholds for the first v2 candidate. */
#define GOODIX_ENROLLMENT_DIVERSITY_MIN_SIGFM_KEYPOINTS 25u
#define GOODIX_ENROLLMENT_DIVERSITY_MIN_COVERAGE_CELLS 4u
#define GOODIX_ENROLLMENT_DIVERSITY_MIN_RASTER_RANGE 48u
#define GOODIX_ENROLLMENT_DIVERSITY_MIN_RASTER_CONTRAST 12u
#define GOODIX_ENROLLMENT_DIVERSITY_EXACT_MAD_LIMIT 4u
#define GOODIX_ENROLLMENT_DIVERSITY_NEAR_MAD_LIMIT 24u
#define GOODIX_ENROLLMENT_DIVERSITY_NEAR_COVERAGE_PERCENT 75u
#define GOODIX_ENROLLMENT_DIVERSITY_NEAR_KEYPOINT_DELTA_PERCENT 25u
#define GOODIX_ENROLLMENT_DIVERSITY_EARLY_COVERAGE_CELLS 56u
#define GOODIX_ENROLLMENT_DIVERSITY_EARLY_AVG_KEYPOINTS 80u
#define GOODIX_ENROLLMENT_DIVERSITY_EARLY_AVG_CONTRAST 24u
#define GOODIX_ENROLLMENT_DIVERSITY_NORMAL_COVERAGE_CELLS 32u
#define GOODIX_ENROLLMENT_DIVERSITY_NORMAL_AVG_KEYPOINTS 40u
#define GOODIX_ENROLLMENT_DIVERSITY_NORMAL_AVG_CONTRAST 16u

typedef struct
{
  guint sigfm_keypoints;
  /* One bit per 10x8-pixel cell in the canonical 80x64 SIGFM raster. */
  guint64 sigfm_coverage_mask;
} GoodixEnrollmentSampleMetrics;

typedef enum
{
  GOODIX_ENROLLMENT_DIVERSITY_ACCEPT,
  GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE,
  GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR,
  GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL,
  GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED,
} GoodixEnrollmentDiversityDecision;

typedef struct
{
  GoodixEnrollmentDiversityDecision decision;
  guint physical_attempt_count;
  guint accepted_sample_count;
  guint sigfm_keypoints;
  guint sigfm_coverage_cells;
  guint aggregate_coverage_cells;
  guint raster_range;
  guint raster_contrast;
  guint nearest_mad;
  guint nearest_coverage_percent;
  gboolean exact_duplicate;
  gboolean near_duplicate;
} GoodixEnrollmentDiversityObservation;

typedef struct _GoodixEnrollmentDiversity GoodixEnrollmentDiversity;

GoodixEnrollmentDiversity *goodix_enrollment_diversity_new (gsize frame_size);
void goodix_enrollment_diversity_free (GoodixEnrollmentDiversity *diversity);

GoodixEnrollmentDiversityDecision goodix_enrollment_diversity_observe (
  GoodixEnrollmentDiversity           *diversity,
  const guint8                        *frame,
  gsize                                frame_size,
  const GoodixEnrollmentSampleMetrics *metrics);

guint goodix_enrollment_diversity_get_physical_attempt_count (
  const GoodixEnrollmentDiversity *diversity);
guint goodix_enrollment_diversity_get_accepted_count (
  const GoodixEnrollmentDiversity *diversity);
guint goodix_enrollment_diversity_get_template_stage_target (
  const GoodixEnrollmentDiversity *diversity);
void goodix_enrollment_diversity_get_last_observation (
  const GoodixEnrollmentDiversity       *diversity,
  GoodixEnrollmentDiversityObservation *observation);

G_DEFINE_AUTOPTR_CLEANUP_FUNC (GoodixEnrollmentDiversity,
                               goodix_enrollment_diversity_free)

G_END_DECLS

#endif
