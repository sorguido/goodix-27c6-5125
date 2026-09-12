/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Minimal host-only adaptation of the enrollment selector in
 * Rockytkg/src/goodixgf.c at upstream snapshot
 * 227eba219fa9e3fbac5bd59aca79f624f67cd11b.
 *
 * The Rocky MAD<8 duplicate test, 3/8 accepted-stage bounds and two-duplicate
 * convergence rule are preserved.  This target integration additionally
 * caps physical contacts at 20 so retries can never become hidden or
 * unbounded.  It contains no transport, device-state or persistent I/O.
 */
#include "goodix_enrollment_diversity.h"

#include <string.h>

struct _GoodixEnrollmentDiversity
{
  gsize frame_size;
  guint8 *accepted[GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES];
  guint distinct_count;
  guint duplicate_streak;
  guint physical_attempt_count;
  guint template_stage_target;
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
    if (diversity->accepted[i] != NULL)
      {
        secure_clear (diversity->accepted[i], diversity->frame_size);
        g_free (diversity->accepted[i]);
      }
  secure_clear (diversity, sizeof *diversity);
  g_free (diversity);
}

static gboolean
is_duplicate (const GoodixEnrollmentDiversity *diversity,
              const guint8                   *frame)
{
  const guint64 limit =
    (guint64) diversity->frame_size * GOODIX_ENROLLMENT_DIVERSITY_MAD_LIMIT;

  for (guint sample = 0u; sample < diversity->distinct_count; sample++)
    {
      guint64 difference_sum = 0u;

      for (gsize pixel = 0u; pixel < diversity->frame_size; pixel++)
        {
          gint difference = (gint) frame[pixel] -
                            (gint) diversity->accepted[sample][pixel];
          difference_sum += (guint64) ABS (difference);
        }
      if (difference_sum < limit)
        return TRUE;
    }
  return FALSE;
}

GoodixEnrollmentDiversityDecision
goodix_enrollment_diversity_observe (GoodixEnrollmentDiversity *diversity,
                                     const guint8              *frame,
                                     gsize                      frame_size)
{
  gboolean duplicate;

  if (diversity == NULL || frame == NULL ||
      frame_size != diversity->frame_size || diversity->terminal)
    return GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED;

  diversity->physical_attempt_count++;
  duplicate = diversity->distinct_count > 0u &&
              is_duplicate (diversity, frame);
  if (duplicate)
    {
      diversity->duplicate_streak++;
      if (diversity->distinct_count >=
            GOODIX_ENROLLMENT_DIVERSITY_MIN_DISTINCT &&
          diversity->distinct_count <
            GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES &&
          diversity->duplicate_streak >=
            GOODIX_ENROLLMENT_DIVERSITY_DUP_STREAK)
        {
          diversity->template_stage_target = diversity->distinct_count + 1u;
          diversity->terminal = TRUE;
          return GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL;
        }
      return diversity->physical_attempt_count <
               GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS ?
        GOODIX_ENROLLMENT_DIVERSITY_RETRY_DUPLICATE :
        GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED;
    }

  diversity->duplicate_streak = 0u;
  if (diversity->distinct_count >= GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES)
    return GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED;
  diversity->accepted[diversity->distinct_count] =
    g_try_malloc (frame_size);
  if (diversity->accepted[diversity->distinct_count] == NULL)
    return GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED;
  memcpy (diversity->accepted[diversity->distinct_count], frame, frame_size);
  diversity->distinct_count++;
  if (diversity->distinct_count == GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES)
    {
      diversity->template_stage_target = diversity->distinct_count;
      diversity->terminal = TRUE;
      return GOODIX_ENROLLMENT_DIVERSITY_ACCEPT_TERMINAL;
    }
  if (diversity->physical_attempt_count >=
      GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS)
    return GOODIX_ENROLLMENT_DIVERSITY_EXHAUSTED;
  return GOODIX_ENROLLMENT_DIVERSITY_ACCEPT;
}

guint
goodix_enrollment_diversity_get_physical_attempt_count (
  const GoodixEnrollmentDiversity *diversity)
{
  return diversity != NULL ? diversity->physical_attempt_count : 0u;
}

guint
goodix_enrollment_diversity_get_distinct_count (
  const GoodixEnrollmentDiversity *diversity)
{
  return diversity != NULL ? diversity->distinct_count : 0u;
}

guint
goodix_enrollment_diversity_get_template_stage_target (
  const GoodixEnrollmentDiversity *diversity)
{
  return diversity != NULL ? diversity->template_stage_target : 0u;
}
