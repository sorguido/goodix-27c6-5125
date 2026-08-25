/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_SIGFM_METRICS_H
#define GOODIX_SIGFM_METRICS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct GoodixSigfmSample GoodixSigfmSample;

typedef enum
{
  GOODIX_SIGFM_OK = 0,
  GOODIX_SIGFM_INVALID_ARGUMENT,
  GOODIX_SIGFM_MAPPING_FAILURE,
  GOODIX_SIGFM_EXTRACT_EXCEPTION,
  GOODIX_SIGFM_EXTRACT_NULL,
  GOODIX_SIGFM_KEYPOINT_GATE_FAILED,
  GOODIX_SIGFM_MATCH_EXCEPTION,
  GOODIX_SIGFM_MATCH_ERROR,
} GoodixSigfmResult;

/*
 * Ephemeral extraction only.  The canonical D269 mapping is applied exactly
 * once; serialized templates and persistence are intentionally not exposed.
 * A successful sample owns SIGFM state and must be freed below.
 */
GoodixSigfmResult
goodix_sigfm_extract_ephemeral (const uint16_t      *samples,
                                size_t               sample_count,
                                GoodixSigfmSample  **sample_out,
                                int                 *keypoints_out);

/* A score of zero is GOODIX_SIGFM_OK.  Negative SIGFM values are errors. */
GoodixSigfmResult
goodix_sigfm_match_ephemeral (GoodixSigfmSample *frame,
                              GoodixSigfmSample *enrolled,
                              int               *score_out);

void goodix_sigfm_sample_free (GoodixSigfmSample *sample);

#ifdef __cplusplus
}
#endif

#endif
