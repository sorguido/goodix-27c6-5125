/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_DIVERSITY_H
#define GOODIX_ENROLLMENT_DIVERSITY_H

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_ENROLLMENT_DIVERSITY_MIN_DISTINCT 3u
#define GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES 8u
#define GOODIX_ENROLLMENT_DIVERSITY_DUP_STREAK 2u
#define GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS 20u
#define GOODIX_ENROLLMENT_DIVERSITY_MAD_LIMIT 8u

typedef enum
{
  GOODIX_ENROLLMENT_DIVERSITY_ACCEPT,
  GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE,
  GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL,
  GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED,
} GoodixEnrollmentDiversityDecision;

typedef struct _GoodixEnrollmentDiversity GoodixEnrollmentDiversity;

GoodixEnrollmentDiversity *goodix_enrollment_diversity_new (gsize frame_size);
void goodix_enrollment_diversity_free (GoodixEnrollmentDiversity *diversity);

GoodixEnrollmentDiversityDecision goodix_enrollment_diversity_observe (
  GoodixEnrollmentDiversity *diversity,
  const guint8              *frame,
  gsize                      frame_size);

guint goodix_enrollment_diversity_get_physical_attempt_count (
  const GoodixEnrollmentDiversity *diversity);
guint goodix_enrollment_diversity_get_distinct_count (
  const GoodixEnrollmentDiversity *diversity);
guint goodix_enrollment_diversity_get_template_stage_target (
  const GoodixEnrollmentDiversity *diversity);

G_END_DECLS

#endif
