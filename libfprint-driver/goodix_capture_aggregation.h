/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_CAPTURE_AGGREGATION_H
#define GOODIX_CAPTURE_AGGREGATION_H

#include <stddef.h>
#include <stdint.h>

#include "goodix_fpimage_pipeline.h"

/*
 * Host-only offline collector of already-decoded Goodix captures.
 *
 * This is the collection boundary that, in a future libfprint driver, would be
 * driven by the device capture loop: it receives one canonical 80x64 u16/12-bit
 * raster per capture (the output of the GPL decoder) and assembles a bounded
 * enroll set of real FpImage objects via the D270 pipeline.
 *
 * The module contains NO USB, TLS, file, network, device-command, retry or
 * persistent-write path.  Each aggregated image keeps the unresolved ppmm state
 * and zero orientation/polarity flags, so no unproven target semantics are
 * assumed.  A future driver loop is the only place that may feed it.
 */

typedef enum
{
  GOODIX_CAPTURE_AGGREGATION_OK = 0,
  GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT,
  GOODIX_CAPTURE_AGGREGATION_INVALID_SAMPLE_COUNT,
  GOODIX_CAPTURE_AGGREGATION_SAMPLE_OUT_OF_RANGE,
  GOODIX_CAPTURE_AGGREGATION_OVER_MAX,
  GOODIX_CAPTURE_AGGREGATION_BELOW_MIN,
  GOODIX_CAPTURE_AGGREGATION_PIPELINE_FAILED,
} GoodixCaptureAggregationResult;

typedef struct _GoodixCaptureAggregator GoodixCaptureAggregator;

/* min_captures >= 1 and min_captures <= max_captures.  D272 sample policy uses
 * 2..8.  *out must be NULL on entry. */
GoodixCaptureAggregationResult
goodix_capture_aggregation_new (GoodixCaptureAggregator **out,
                                size_t                    min_captures,
                                size_t                    max_captures);

/* Feed one already-decoded canonical 80x64 u16/12-bit capture.  Builds a real
 * FpImage through the D270 pipeline; never emits a device command. */
GoodixCaptureAggregationResult
goodix_capture_aggregation_add (GoodixCaptureAggregator *agg,
                                const uint16_t          *samples,
                                size_t                   sample_count);

size_t
goodix_capture_aggregation_count (const GoodixCaptureAggregator *agg);

/* Transfer none: the image remains owned by the internal pipeline object. */
FpImage *
goodix_capture_aggregation_get_image (GoodixCaptureAggregator *agg,
                                      size_t                   index);

GoodixFpImagePhysicalPpmmState
goodix_capture_aggregation_get_image_ppmm_state (const GoodixCaptureAggregator *agg,
                                                 size_t                         index);

/* Fail-closed unless the collected count satisfies the configured bounds. */
GoodixCaptureAggregationResult
goodix_capture_aggregation_finalize (GoodixCaptureAggregator *agg);

void
goodix_capture_aggregation_free (GoodixCaptureAggregator *agg);

#endif
