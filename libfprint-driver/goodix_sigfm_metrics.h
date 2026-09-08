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
  GOODIX_SIGFM_UNSUPPORTED_HOST_ABI,
  GOODIX_SIGFM_COPY_EXCEPTION,
  GOODIX_SIGFM_SERIALIZE_EXCEPTION,
  GOODIX_SIGFM_SERIALIZE_INVALID,
  GOODIX_SIGFM_DESERIALIZE_INVALID,
  GOODIX_SIGFM_DESERIALIZE_EXCEPTION,
} GoodixSigfmResult;

#define GOODIX_SIGFM_MIN_KEYPOINTS 25
#define GOODIX_SIGFM_MAX_KEYPOINTS 1024
#define GOODIX_SIGFM_MAX_SERIALIZED_SIZE (24u + 20u + 540u * 1024u)

/*
 * Legacy D272 extraction entrypoint: the canonical D269 mapping is applied
 * exactly once. New production work first applies the D279/49 R2 preprocessor
 * and calls goodix_sigfm_extract_pixels(). A successful sample owns SIGFM
 * state and must be freed below.
 */
GoodixSigfmResult
goodix_sigfm_extract_ephemeral (const uint16_t      *samples,
                                size_t               sample_count,
                                GoodixSigfmSample  **sample_out,
                                int                 *keypoints_out);

/* Extract from the already preprocessed 80x64 R2 byte raster. */
GoodixSigfmResult
goodix_sigfm_extract_pixels (const uint8_t       *pixels,
                             size_t               pixel_count,
                             GoodixSigfmSample  **sample_out,
                             int                 *keypoints_out);

/* A score of zero is GOODIX_SIGFM_OK.  Negative SIGFM values are errors. */
GoodixSigfmResult
goodix_sigfm_match_ephemeral (GoodixSigfmSample *frame,
                              GoodixSigfmSample *enrolled,
                              int               *score_out);

GoodixSigfmResult
goodix_sigfm_sample_copy (const GoodixSigfmSample  *source,
                          GoodixSigfmSample       **copy_out);

/*
 * Stable project envelope around Rockytkg's native x86_64-little-endian
 * payload. Deserialization validates exact bounds, shape, type, CRC and a
 * canonical reserialization before returning an owned sample.
 */
GoodixSigfmResult
goodix_sigfm_sample_serialize (const GoodixSigfmSample  *sample,
                               uint8_t                 **data_out,
                               size_t                   *size_out);

GoodixSigfmResult
goodix_sigfm_sample_deserialize (const uint8_t       *data,
                                 size_t               size,
                                 GoodixSigfmSample  **sample_out,
                                 int                 *keypoints_out);

void goodix_sigfm_serialized_free (uint8_t *data,
                                   size_t   size);

void goodix_sigfm_sample_free (GoodixSigfmSample *sample);

#ifdef __cplusplus
}
#endif

#endif
