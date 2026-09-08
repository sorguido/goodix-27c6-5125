/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GOODIX_SIGFM_PREPROCESS_H
#define GOODIX_SIGFM_PREPROCESS_H

#include <stddef.h>
#include <stdint.h>

#include "goodix_u16_to_fpimage.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
  GOODIX_SIGFM_PREPROCESS_OK = 0,
  GOODIX_SIGFM_PREPROCESS_INVALID_ARGUMENT,
  GOODIX_SIGFM_PREPROCESS_INVALID_SAMPLE_COUNT,
  GOODIX_SIGFM_PREPROCESS_OUTPUT_TOO_SMALL,
  GOODIX_SIGFM_PREPROCESS_SAMPLE_OUT_OF_RANGE,
  GOODIX_SIGFM_PREPROCESS_ALLOCATION_FAILED,
  GOODIX_SIGFM_PREPROCESS_EXECUTION_FAILED,
} GoodixSigfmPreprocessResult;

/*
 * Apply the exact D279/48 R2 preprocessing chain to one canonical 80x64
 * frame using a session-local baseline:
 *
 *   signed baseline delta (+2048) -> flatfield r=12 -> percentile 1/99
 *   -> SIGFM unsharp boost=0.8, sigma=1.5
 *
 * Both inputs are validated before output is changed. No environment, file,
 * USB, TLS, secret or persistent-state interface is reachable here.
 */
GoodixSigfmPreprocessResult
goodix_sigfm_preprocess_r2 (const uint16_t *baseline,
                            size_t          baseline_count,
                            const uint16_t *frame,
                            size_t          frame_count,
                            uint8_t        *output,
                            size_t          output_size);

#ifdef __cplusplus
}
#endif

#endif
