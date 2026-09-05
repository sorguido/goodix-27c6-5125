/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_PIPELINE_H
#define GOODIX_ENROLLMENT_PIPELINE_H

#include "goodix_enrollment_model.h"
#include "goodix_fpimage_pipeline.h"
#include "goodix_u16_to_fpimage.h"

G_BEGIN_DECLS

typedef struct _GoodixEnrollmentPipeline GoodixEnrollmentPipeline;

typedef struct
{
  GoodixEnrollmentModelAudit protocol;
  guint fpimage_construct_count;
  guint fpimage_delivery_count;
  guint auxiliary_fpimage_delivery_count;
  gboolean failed;
} GoodixEnrollmentPipelineAudit;

/* @image is transfer-none and remains valid only for the callback duration.
 * A consumer that queues it (including FpImageDevice) must take a reference. */
typedef gboolean (*GoodixEnrollmentImageFunc) (
  GoodixEnrollmentPipeline *pipeline,
  guint                     stage_index,
  FpImage                  *image,
  gpointer                  user_data,
  GError                  **error);

GoodixEnrollmentPipeline *goodix_enrollment_pipeline_new (
  const GoodixEnrollmentModelConfig *config,
  GoodixEnrollmentImageFunc          image_ready,
  gpointer                           user_data,
  GoodixEnrollmentPipelineAudit     *audit,
  GError                           **error);
void goodix_enrollment_pipeline_free (GoodixEnrollmentPipeline *pipeline);

/* Samples are required exactly for PRIMARY_B0 and forbidden for all other
 * events.  In particular, AUXILIARY_B0 remains an opaque protocol event. */
gboolean goodix_enrollment_pipeline_feed (
  GoodixEnrollmentPipeline *pipeline,
  GoodixEnrollmentEvent     event,
  const uint16_t           *samples,
  size_t                    sample_count,
  GError                  **error);

GoodixEnrollmentEvent goodix_enrollment_pipeline_get_expected_event (
  const GoodixEnrollmentPipeline *pipeline);
gboolean goodix_enrollment_pipeline_is_complete (
  const GoodixEnrollmentPipeline *pipeline);
gboolean goodix_enrollment_pipeline_is_failed (
  const GoodixEnrollmentPipeline *pipeline);

G_END_DECLS

#endif
