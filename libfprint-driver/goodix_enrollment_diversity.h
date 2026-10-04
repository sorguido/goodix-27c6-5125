/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_DIVERSITY_H
#define GOODIX_ENROLLMENT_DIVERSITY_H

#include <glib.h>

G_BEGIN_DECLS

/* Normative fixed-21 enrollment policy for the APP12509 target: enrollment
 * completes exactly at the 21st accepted valid sample.  There is no early
 * completion, a 22nd accepted sample is unreachable, and no policy-side
 * physical-contact maximum exists (poor/unusable captures retry and physical
 * contacts may exceed 21 without bound).  This constant is the dedicated
 * policy source; the historical GOODIX_TARGET_LOCAL_ENROLL_STAGES wire-fixture
 * metadata in goodix_fpimage_device.h is not a policy input. */
#define GOODIX_ENROLLMENT_DIVERSITY_REQUIRED_ACCEPTED_SAMPLES 21u

/* Poor/unusable quality gate.  This gate is separate from the fixed-21
 * completion rule and is never a diversity or completion criterion; it only
 * keeps an unusable capture out of the template. */
#define GOODIX_ENROLLMENT_DIVERSITY_MIN_SIGFM_KEYPOINTS 25u
#define GOODIX_ENROLLMENT_DIVERSITY_MIN_COVERAGE_CELLS 4u
#define GOODIX_ENROLLMENT_DIVERSITY_MIN_RASTER_RANGE 48u
#define GOODIX_ENROLLMENT_DIVERSITY_MIN_RASTER_CONTRAST 12u

/* Duplicate/near-duplicate detection thresholds.  Detection is diagnostic
 * only: a valid duplicate or near-duplicate is accepted, counts toward the
 * required samples, and never anticipates, blocks or determines completion. */
#define GOODIX_ENROLLMENT_DIVERSITY_EXACT_MAD_LIMIT 4u
#define GOODIX_ENROLLMENT_DIVERSITY_NEAR_MAD_LIMIT 24u
#define GOODIX_ENROLLMENT_DIVERSITY_NEAR_COVERAGE_PERCENT 75u
#define GOODIX_ENROLLMENT_DIVERSITY_NEAR_KEYPOINT_DELTA_PERCENT 25u

typedef struct
{
  guint sigfm_keypoints;
  /* One bit per 10x8-pixel cell in the canonical 80x64 SIGFM raster. */
  guint64 sigfm_coverage_mask;
} GoodixEnrollmentSampleMetrics;

typedef enum
{
  /* Valid sample accepted; it counts toward the fixed 21. */
  GOODIX_ENROLLMENT_DIVERSITY_ACCEPT,
  /* Poor/unusable sample; retry without advancing the accepted count. */
  GOODIX_ENROLLMENT_DIVERSITY_RETRY_POOR,
  /* The 21st accepted valid sample; enrollment is complete. */
  GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL,
  /* Internal policy failure (invalid input, observation after completion or
   * allocation failure).  This is never a physical-contact bound. */
  GOODIX_ENROLLMENT_DIVERSITY_FAILED,
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
