/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_pipeline.h"

typedef enum
{
  GOODIX_ENROLLMENT_PIPELINE_ERROR_ARGUMENT,
  GOODIX_ENROLLMENT_PIPELINE_ERROR_STATE,
  GOODIX_ENROLLMENT_PIPELINE_ERROR_IMAGE,
} GoodixEnrollmentPipelineError;

#define GOODIX_ENROLLMENT_PIPELINE_ERROR \
  (goodix_enrollment_pipeline_error_quark ())

struct _GoodixEnrollmentPipeline
{
  GoodixEnrollmentModel *model;
  GoodixEnrollmentImageFunc image_ready;
  gpointer user_data;
  GoodixEnrollmentPipelineAudit *audit;
  GoodixFpImagePipeline *pending_image;
  gboolean failed;
};

static GQuark
goodix_enrollment_pipeline_error_quark (void)
{
  return g_quark_from_static_string ("goodix-enrollment-pipeline-error");
}

static gboolean
pipeline_stage_ready (GoodixEnrollmentModel *model,
                      guint                  stage_index,
                      gpointer               user_data,
                      GError               **error)
{
  GoodixEnrollmentPipeline *pipeline = user_data;
  FpImage *image;

  (void) model;
  if (pipeline->pending_image == NULL)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_PIPELINE_ERROR,
                           GOODIX_ENROLLMENT_PIPELINE_ERROR_STATE,
                           "primary stage has no pending FpImage");
      return FALSE;
    }
  image = goodix_fpimage_pipeline_get_image (pipeline->pending_image);
  if (image == NULL ||
      !pipeline->image_ready (pipeline, stage_index, image,
                              pipeline->user_data, error))
    return FALSE;
  if (pipeline->audit != NULL)
    pipeline->audit->fpimage_delivery_count++;
  return TRUE;
}

GoodixEnrollmentPipeline *
goodix_enrollment_pipeline_new (const GoodixEnrollmentModelConfig *config,
                                GoodixEnrollmentImageFunc          image_ready,
                                gpointer                           user_data,
                                GoodixEnrollmentPipelineAudit     *audit,
                                GError                           **error)
{
  GoodixEnrollmentPipeline *pipeline;

  if (config == NULL || image_ready == NULL)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_PIPELINE_ERROR,
                           GOODIX_ENROLLMENT_PIPELINE_ERROR_ARGUMENT,
                           "enrollment image pipeline requires config and callback");
      return NULL;
    }
  pipeline = g_new0 (GoodixEnrollmentPipeline, 1);
  pipeline->image_ready = image_ready;
  pipeline->user_data = user_data;
  pipeline->audit = audit;
  if (audit != NULL)
    *audit = (GoodixEnrollmentPipelineAudit) { 0 };
  pipeline->model = goodix_enrollment_model_new (
    config, pipeline_stage_ready, pipeline, audit != NULL ? &audit->protocol :
                                                           NULL,
    error);
  if (pipeline->model == NULL)
    {
      g_free (pipeline);
      return NULL;
    }
  return pipeline;
}

void
goodix_enrollment_pipeline_free (GoodixEnrollmentPipeline *pipeline)
{
  if (pipeline == NULL)
    return;
  goodix_fpimage_pipeline_free (pipeline->pending_image);
  goodix_enrollment_model_free (pipeline->model);
  g_free (pipeline);
}

static gboolean
pipeline_fail (GoodixEnrollmentPipeline *pipeline,
               GoodixEnrollmentPipelineError code,
               const gchar             *message,
               GError                 **error)
{
  goodix_fpimage_pipeline_free (pipeline->pending_image);
  pipeline->pending_image = NULL;
  pipeline->failed = TRUE;
  if (pipeline->audit != NULL)
    pipeline->audit->failed = TRUE;
  g_set_error_literal (error, GOODIX_ENROLLMENT_PIPELINE_ERROR, code, message);
  return FALSE;
}

gboolean
goodix_enrollment_pipeline_feed (GoodixEnrollmentPipeline *pipeline,
                                 GoodixEnrollmentEvent     event,
                                 const uint16_t           *samples,
                                 size_t                    sample_count,
                                 GError                  **error)
{
  GoodixFpImagePipelineResult image_result;
  gboolean accepted;
  guint completed_before;

  if (pipeline == NULL)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_PIPELINE_ERROR,
                           GOODIX_ENROLLMENT_PIPELINE_ERROR_ARGUMENT,
                           "enrollment image pipeline is absent");
      return FALSE;
    }
  if (pipeline->failed || goodix_enrollment_model_is_complete (pipeline->model))
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_PIPELINE_ERROR,
                           GOODIX_ENROLLMENT_PIPELINE_ERROR_STATE,
                           "enrollment image pipeline is already terminal");
      return FALSE;
    }
  if (event != goodix_enrollment_model_get_expected_event (pipeline->model))
    {
      accepted = goodix_enrollment_model_feed (pipeline->model, event, error);
      g_assert (!accepted);
      goodix_fpimage_pipeline_free (pipeline->pending_image);
      pipeline->pending_image = NULL;
      pipeline->failed = TRUE;
      if (pipeline->audit != NULL)
        pipeline->audit->failed = TRUE;
      return FALSE;
    }
  if (event == GOODIX_ENROLLMENT_EVENT_PRIMARY_B0)
    {
      if (samples == NULL ||
          sample_count != GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT)
        return pipeline_fail (pipeline,
                              GOODIX_ENROLLMENT_PIPELINE_ERROR_ARGUMENT,
                              "primary B0 requires one canonical raster",
                              error);
      image_result = goodix_fpimage_pipeline_new (
        samples, sample_count, &pipeline->pending_image);
      if (image_result != GOODIX_FPIMAGE_PIPELINE_OK ||
          goodix_fpimage_pipeline_check_ppmm_requirement (
            pipeline->pending_image, GOODIX_FPIMAGE_PPMM_CONSUMER_NBIS) !=
          GOODIX_FPIMAGE_PIPELINE_OK)
        {
          goodix_fpimage_pipeline_free (pipeline->pending_image);
          pipeline->pending_image = NULL;
          return pipeline_fail (pipeline, GOODIX_ENROLLMENT_PIPELINE_ERROR_IMAGE,
                                "primary raster cannot form an NBIS-compatible FpImage",
                                error);
        }
      if (pipeline->audit != NULL)
        pipeline->audit->fpimage_construct_count++;
    }
  else if (samples != NULL || sample_count != 0u)
    return pipeline_fail (pipeline, GOODIX_ENROLLMENT_PIPELINE_ERROR_ARGUMENT,
                          "non-primary enrollment event cannot carry a raster",
                          error);

  completed_before = goodix_enrollment_model_get_completed_stage_count (
    pipeline->model);
  accepted = goodix_enrollment_model_feed (pipeline->model, event, error);
  if (!accepted ||
      goodix_enrollment_model_get_completed_stage_count (pipeline->model) >
        completed_before)
    {
      goodix_fpimage_pipeline_free (pipeline->pending_image);
      pipeline->pending_image = NULL;
    }
  if (!accepted)
    {
      pipeline->failed = TRUE;
      if (pipeline->audit != NULL)
        pipeline->audit->failed = TRUE;
    }
  return accepted;
}

GoodixEnrollmentEvent
goodix_enrollment_pipeline_get_expected_event (
  const GoodixEnrollmentPipeline *pipeline)
{
  return pipeline != NULL ?
    goodix_enrollment_model_get_expected_event (pipeline->model) :
    GOODIX_ENROLLMENT_EVENT_NONE;
}

gboolean
goodix_enrollment_pipeline_is_complete (
  const GoodixEnrollmentPipeline *pipeline)
{
  return pipeline != NULL &&
         goodix_enrollment_model_is_complete (pipeline->model);
}

gboolean
goodix_enrollment_pipeline_is_failed (
  const GoodixEnrollmentPipeline *pipeline)
{
  return pipeline == NULL || pipeline->failed ||
         goodix_enrollment_model_is_failed (pipeline->model);
}

const uint16_t *
goodix_enrollment_pipeline_get_pending_source_samples (
  const GoodixEnrollmentPipeline *pipeline,
  size_t                         *sample_count)
{
  return pipeline != NULL ?
    goodix_fpimage_pipeline_get_source_samples (pipeline->pending_image,
                                                 sample_count) : NULL;
}
