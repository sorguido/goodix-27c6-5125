/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_FPIMAGE_PIPELINE_H
#define GOODIX_FPIMAGE_PIPELINE_H

#include <stddef.h>
#include <stdint.h>

typedef struct _FpImage FpImage;
typedef struct _GoodixFpImagePipeline GoodixFpImagePipeline;

typedef enum
{
  GOODIX_FPIMAGE_PIPELINE_OK = 0,
  GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT,
  GOODIX_FPIMAGE_PIPELINE_INVALID_SAMPLE_COUNT,
  GOODIX_FPIMAGE_PIPELINE_SAMPLE_OUT_OF_RANGE,
  GOODIX_FPIMAGE_PIPELINE_ALLOCATION_FAILED,
  GOODIX_FPIMAGE_PIPELINE_CONTRACT_VIOLATION,
  GOODIX_FPIMAGE_PIPELINE_PHYSICAL_PPMM_REQUIRED,
} GoodixFpImagePipelineResult;

typedef enum
{
  /* The target-specific physical scan resolution has not been established. */
  GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN = 0,
} GoodixFpImagePhysicalPpmmState;

typedef enum
{
  GOODIX_FPIMAGE_PPMM_CONSUMER_NBIS = 0,
  GOODIX_FPIMAGE_PPMM_CONSUMER_SIGFM,
} GoodixFpImagePpmmConsumer;

/*
 * Construct a real repository-local FpImage from the canonical Goodix raster.
 * The returned opaque owner holds the only initial GObject reference and must
 * be released with goodix_fpimage_pipeline_free().  On failure, *pipeline_out
 * remains NULL.  The caller must initialize *pipeline_out to NULL.
 */
GoodixFpImagePipelineResult
goodix_fpimage_pipeline_new (const uint16_t          *samples,
                             size_t                   sample_count,
                             GoodixFpImagePipeline **pipeline_out);

/* Build an FpImage containing the exact D279/49 R2 raster for SIGFM. */
GoodixFpImagePipelineResult
goodix_fpimage_pipeline_new_sigfm (const uint16_t          *baseline,
                                   size_t                   baseline_count,
                                   const uint16_t          *samples,
                                   size_t                   sample_count,
                                   GoodixFpImagePipeline **pipeline_out);

/* Transfer none: the image remains owned by the opaque pipeline object. */
FpImage *
goodix_fpimage_pipeline_get_image (GoodixFpImagePipeline *pipeline);

/* Transfer none; valid for the pipeline lifetime. */
const uint16_t *goodix_fpimage_pipeline_get_source_samples (
  const GoodixFpImagePipeline *pipeline,
  size_t                      *sample_count);

GoodixFpImagePhysicalPpmmState
goodix_fpimage_pipeline_get_physical_ppmm_state (
  const GoodixFpImagePipeline *pipeline);

/*
 * Gate only the physical-ppmm requirement of the selected extractor.  Neither
 * the production NBIS extraction/matching path in libfprint 1.94.100 nor the
 * historical SIGFM path requires a physical value.  NBIS quality remains
 * physically uncalibrated; no value is synthesized for FpImage::ppmm.
 */
GoodixFpImagePipelineResult
goodix_fpimage_pipeline_check_ppmm_requirement (
  const GoodixFpImagePipeline *pipeline,
  GoodixFpImagePpmmConsumer    consumer);

void
goodix_fpimage_pipeline_free (GoodixFpImagePipeline *pipeline);

#endif
