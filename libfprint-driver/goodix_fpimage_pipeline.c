/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_fpimage_pipeline.h"

#include "goodix_u16_to_fpimage.h"
#ifdef GOODIX_LIBFPRINT_SIGFM
#include "goodix_sigfm_preprocess.h"
#endif

#include <fpi-image.h>
#include <glib-object.h>

struct _GoodixFpImagePipeline
{
  FpImage                           *image;
  uint16_t                          *source_samples;
  GoodixFpImagePhysicalPpmmState     physical_ppmm_state;
};

static void
secure_clear (void *data,
              size_t size)
{
  volatile guint8 *cursor = data;

  while (size-- > 0)
    *cursor++ = 0;
}

static GoodixFpImagePipelineResult
map_adapter_result (GoodixU16ToFpImageResult result)
{
  switch (result)
    {
    case GOODIX_U16_TO_FPIMAGE_OK:
      return GOODIX_FPIMAGE_PIPELINE_OK;
    case GOODIX_U16_TO_FPIMAGE_INVALID_ARGUMENT:
      return GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT;
    case GOODIX_U16_TO_FPIMAGE_INVALID_SAMPLE_COUNT:
      return GOODIX_FPIMAGE_PIPELINE_INVALID_SAMPLE_COUNT;
    case GOODIX_U16_TO_FPIMAGE_SAMPLE_OUT_OF_RANGE:
      return GOODIX_FPIMAGE_PIPELINE_SAMPLE_OUT_OF_RANGE;
    case GOODIX_U16_TO_FPIMAGE_OUTPUT_TOO_SMALL:
    default:
      return GOODIX_FPIMAGE_PIPELINE_CONTRACT_VIOLATION;
    }
}

GoodixFpImagePipelineResult
goodix_fpimage_pipeline_new (const uint16_t          *samples,
                             size_t                   sample_count,
                             GoodixFpImagePipeline **pipeline_out)
{
  GoodixLibfprintImageMetadata metadata = { 0 };
  GoodixFpImagePipeline *pipeline;
  GoodixU16ToFpImageResult adapter_result;

  if (samples == NULL || pipeline_out == NULL || *pipeline_out != NULL)
    return GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT;

  if (sample_count != GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT)
    return GOODIX_FPIMAGE_PIPELINE_INVALID_SAMPLE_COUNT;

  pipeline = g_try_new0 (GoodixFpImagePipeline, 1);
  if (pipeline == NULL)
    return GOODIX_FPIMAGE_PIPELINE_ALLOCATION_FAILED;

  pipeline->image = fp_image_new ((gint) GOODIX_CANONICAL_IMAGE_WIDTH,
                                  (gint) GOODIX_CANONICAL_IMAGE_HEIGHT);
  if (pipeline->image == NULL)
    {
      g_free (pipeline);
      return GOODIX_FPIMAGE_PIPELINE_ALLOCATION_FAILED;
    }
  pipeline->source_samples = g_try_malloc (
    GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT * sizeof (uint16_t));
  if (pipeline->source_samples == NULL)
    {
      g_free (pipeline);
      return GOODIX_FPIMAGE_PIPELINE_ALLOCATION_FAILED;
    }
  memcpy (pipeline->source_samples, samples,
          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT * sizeof (uint16_t));

  adapter_result = goodix_u16_to_fpimage (
    samples,
    sample_count,
    pipeline->image->data,
    (size_t) pipeline->image->width * (size_t) pipeline->image->height,
    &metadata);
  if (adapter_result != GOODIX_U16_TO_FPIMAGE_OK)
    {
      GoodixFpImagePipelineResult result = map_adapter_result (adapter_result);

      goodix_fpimage_pipeline_free (pipeline);
      return result;
    }

  if (metadata.width != GOODIX_CANONICAL_IMAGE_WIDTH ||
      metadata.height != GOODIX_CANONICAL_IMAGE_HEIGHT ||
      metadata.stride != GOODIX_CANONICAL_IMAGE_WIDTH ||
      metadata.data_length != GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT ||
      metadata.libfprint_image_flags != GOODIX_LIBFPRINT_IMAGE_FLAGS_NONE ||
      metadata.canonical_orientation_preserved != 1 ||
      metadata.natural_orientation_resolved != 0)
    {
      goodix_fpimage_pipeline_free (pipeline);
      return GOODIX_FPIMAGE_PIPELINE_CONTRACT_VIOLATION;
    }

  /*
   * flags=0 means only that no transform is currently justified.  Do not
   * assign image->ppmm: its zero-initialized storage is not a physical value.
   * The separate state below is the authoritative semantic representation.
   */
  pipeline->image->flags = (FpiImageFlags) GOODIX_LIBFPRINT_IMAGE_FLAGS_NONE;
  pipeline->physical_ppmm_state = GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN;

  *pipeline_out = pipeline;
  return GOODIX_FPIMAGE_PIPELINE_OK;
}

#ifdef GOODIX_LIBFPRINT_SIGFM
GoodixFpImagePipelineResult
goodix_fpimage_pipeline_new_sigfm (const uint16_t          *baseline,
                                   size_t                   baseline_count,
                                   const uint16_t          *samples,
                                   size_t                   sample_count,
                                   GoodixFpImagePipeline **pipeline_out)
{
  GoodixFpImagePipeline *pipeline;
  GoodixSigfmPreprocessResult preprocess_result;

  if (baseline == NULL || samples == NULL || pipeline_out == NULL ||
      *pipeline_out != NULL)
    return GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT;
  if (baseline_count != GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT ||
      sample_count != GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT)
    return GOODIX_FPIMAGE_PIPELINE_INVALID_SAMPLE_COUNT;
  pipeline = g_try_new0 (GoodixFpImagePipeline, 1);
  if (pipeline == NULL)
    return GOODIX_FPIMAGE_PIPELINE_ALLOCATION_FAILED;
  pipeline->source_samples = g_try_malloc (
    GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT * sizeof (uint16_t));
  pipeline->image = fp_image_new ((gint) GOODIX_CANONICAL_IMAGE_WIDTH,
                                  (gint) GOODIX_CANONICAL_IMAGE_HEIGHT);
  if (pipeline->source_samples == NULL || pipeline->image == NULL)
    {
      goodix_fpimage_pipeline_free (pipeline);
      return GOODIX_FPIMAGE_PIPELINE_ALLOCATION_FAILED;
    }
  memcpy (pipeline->source_samples, samples,
          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT * sizeof (uint16_t));
  preprocess_result = goodix_sigfm_preprocess_r2 (
    baseline, baseline_count, samples, sample_count, pipeline->image->data,
    GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
  if (preprocess_result != GOODIX_SIGFM_PREPROCESS_OK)
    {
      goodix_fpimage_pipeline_free (pipeline);
      return preprocess_result == GOODIX_SIGFM_PREPROCESS_SAMPLE_OUT_OF_RANGE ?
        GOODIX_FPIMAGE_PIPELINE_SAMPLE_OUT_OF_RANGE :
        GOODIX_FPIMAGE_PIPELINE_CONTRACT_VIOLATION;
    }
  pipeline->image->flags = FPI_IMAGE_NONE;
  pipeline->physical_ppmm_state = GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN;
  *pipeline_out = pipeline;
  return GOODIX_FPIMAGE_PIPELINE_OK;
}
#endif

FpImage *
goodix_fpimage_pipeline_get_image (GoodixFpImagePipeline *pipeline)
{
  if (pipeline == NULL)
    return NULL;

  return pipeline->image;
}

const uint16_t *
goodix_fpimage_pipeline_get_source_samples (
  const GoodixFpImagePipeline *pipeline,
  size_t                      *sample_count)
{
  if (sample_count != NULL)
    *sample_count = pipeline != NULL && pipeline->source_samples != NULL ?
      GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT : 0u;
  return pipeline != NULL ? pipeline->source_samples : NULL;
}

GoodixFpImagePhysicalPpmmState
goodix_fpimage_pipeline_get_physical_ppmm_state (
  const GoodixFpImagePipeline *pipeline)
{
  if (pipeline == NULL)
    return GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN;

  return pipeline->physical_ppmm_state;
}

GoodixFpImagePipelineResult
goodix_fpimage_pipeline_check_ppmm_requirement (
  const GoodixFpImagePipeline *pipeline,
  GoodixFpImagePpmmConsumer    consumer)
{
  if (pipeline == NULL || pipeline->image == NULL)
    return GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT;

  switch (consumer)
    {
    case GOODIX_FPIMAGE_PPMM_CONSUMER_NBIS:
      /* libfprint 1.94.100 consumes ppmm only for a reliability
       * neighbourhood whose value is discarded before Bozorth3.  Keeping the
       * field unset therefore preserves the unknown physical scale without
       * blocking extraction or matching (D279/02). */
      return GOODIX_FPIMAGE_PIPELINE_OK;
    case GOODIX_FPIMAGE_PPMM_CONSUMER_SIGFM:
      return GOODIX_FPIMAGE_PIPELINE_OK;
    default:
      return GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT;
    }
}

void
goodix_fpimage_pipeline_free (GoodixFpImagePipeline *pipeline)
{
  if (pipeline == NULL)
    return;

  g_clear_object (&pipeline->image);
  if (pipeline->source_samples != NULL)
    {
      secure_clear (pipeline->source_samples,
                    GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT * sizeof (uint16_t));
      g_free (pipeline->source_samples);
    }
  g_free (pipeline);
}
