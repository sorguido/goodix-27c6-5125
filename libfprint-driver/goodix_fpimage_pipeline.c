/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_fpimage_pipeline.h"

#include "goodix_u16_to_fpimage.h"

#include <fpi-image.h>
#include <glib-object.h>

struct _GoodixFpImagePipeline
{
  FpImage                           *image;
  GoodixFpImagePhysicalPpmmState     physical_ppmm_state;
};

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

FpImage *
goodix_fpimage_pipeline_get_image (GoodixFpImagePipeline *pipeline)
{
  if (pipeline == NULL)
    return NULL;

  return pipeline->image;
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
      return GOODIX_FPIMAGE_PIPELINE_PHYSICAL_PPMM_REQUIRED;
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
  g_free (pipeline);
}
