/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_capture_aggregation.h"

#include <fpi-image.h>
#include <glib-object.h>

struct _GoodixCaptureAggregator
{
  size_t                  min_captures;
  size_t                  max_captures;
  size_t                  count;
  GoodixFpImagePipeline **pipelines;
};

GoodixCaptureAggregationResult
goodix_capture_aggregation_new (GoodixCaptureAggregator **out,
                                size_t                    min_captures,
                                size_t                    max_captures)
{
  GoodixCaptureAggregator *agg;

  if (out == NULL || *out != NULL)
    return GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT;
  if (min_captures < 1 || min_captures > max_captures)
    return GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT;

  agg = g_try_new0 (GoodixCaptureAggregator, 1);
  if (agg == NULL)
    return GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT;

  agg->min_captures = min_captures;
  agg->max_captures = max_captures;
  agg->count = 0;
  agg->pipelines = g_try_new0 (GoodixFpImagePipeline *, max_captures + 1);
  if (agg->pipelines == NULL)
    {
      g_free (agg);
      return GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT;
    }

  *out = agg;
  return GOODIX_CAPTURE_AGGREGATION_OK;
}

GoodixCaptureAggregationResult
goodix_capture_aggregation_add (GoodixCaptureAggregator *agg,
                                const uint16_t          *samples,
                                size_t                   sample_count)
{
  GoodixFpImagePipeline *pipeline = NULL;
  GoodixFpImagePipelineResult result;

  if (agg == NULL || samples == NULL)
    return GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT;
  if (sample_count != GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT)
    return GOODIX_CAPTURE_AGGREGATION_INVALID_SAMPLE_COUNT;
  if (agg->count >= agg->max_captures)
    return GOODIX_CAPTURE_AGGREGATION_OVER_MAX;

  result = goodix_fpimage_pipeline_new (samples, sample_count, &pipeline);
  if (result != GOODIX_FPIMAGE_PIPELINE_OK)
    return GOODIX_CAPTURE_AGGREGATION_PIPELINE_FAILED;

  agg->pipelines[agg->count] = pipeline;
  agg->count += 1;
  return GOODIX_CAPTURE_AGGREGATION_OK;
}

size_t
goodix_capture_aggregation_count (const GoodixCaptureAggregator *agg)
{
  if (agg == NULL)
    return 0;
  return agg->count;
}

FpImage *
goodix_capture_aggregation_get_image (GoodixCaptureAggregator *agg,
                                      size_t                   index)
{
  if (agg == NULL || index >= agg->count)
    return NULL;
  return goodix_fpimage_pipeline_get_image (agg->pipelines[index]);
}

GoodixFpImagePhysicalPpmmState
goodix_capture_aggregation_get_image_ppmm_state (const GoodixCaptureAggregator *agg,
                                                 size_t                         index)
{
  if (agg == NULL || index >= agg->count)
    return GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN;
  return goodix_fpimage_pipeline_get_physical_ppmm_state (agg->pipelines[index]);
}

GoodixCaptureAggregationResult
goodix_capture_aggregation_finalize (GoodixCaptureAggregator *agg)
{
  if (agg == NULL)
    return GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT;
  if (agg->count < agg->min_captures)
    return GOODIX_CAPTURE_AGGREGATION_BELOW_MIN;
  return GOODIX_CAPTURE_AGGREGATION_OK;
}

void
goodix_capture_aggregation_free (GoodixCaptureAggregator *agg)
{
  size_t index;

  if (agg == NULL)
    return;
  for (index = 0; index < agg->count; index++)
    goodix_fpimage_pipeline_free (agg->pipelines[index]);
  g_free (agg->pipelines);
  g_free (agg);
}
