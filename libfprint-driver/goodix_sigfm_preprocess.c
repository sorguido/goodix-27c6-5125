/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Target-specific, host-only boundary around the minimally adapted Rockytkg
 * image pipeline in rockytkg-imgproc/. This file fixes the authentic D279/48
 * R2 parameters and translates the local uint16_t raster contract explicitly
 * to the upstream pipeline's endian-stable 16-bit little-endian input.
 */
#include "goodix_sigfm_preprocess.h"

#include "rockytkg-imgproc/goodix_imgproc.h"

#include <stdlib.h>
#include <string.h>

#define GOODIX_SIGFM_U16LE_BYTES \
  (GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT * 2u)

static void
secure_clear (void   *memory,
              size_t  length)
{
  volatile uint8_t *cursor = memory;

  while (length-- > 0)
    *cursor++ = 0;
}

static int
samples_valid (const uint16_t *samples,
               size_t          count)
{
  for (size_t i = 0; i < count; i++)
    if (samples[i] > GOODIX_SENSOR_SAMPLE_MAX)
      return 0;

  return 1;
}

static void
encode_u16le (const uint16_t *samples,
              uint8_t        *encoded,
              size_t          count)
{
  for (size_t i = 0; i < count; i++)
    {
      encoded[2u * i] = (uint8_t) samples[i];
      encoded[2u * i + 1u] = (uint8_t) (samples[i] >> 8);
    }
}

GoodixSigfmPreprocessResult
goodix_sigfm_preprocess_r2 (const uint16_t *baseline,
                            size_t          baseline_count,
                            const uint16_t *frame,
                            size_t          frame_count,
                            uint8_t        *output,
                            size_t          output_size)
{
  const struct gx_imgproc_params params = GX_IMGPROC_SIGFM_PARAMS;
  struct gx_imgproc_frame view = {
    .width = GOODIX_CANONICAL_IMAGE_WIDTH,
    .height = GOODIX_CANONICAL_IMAGE_HEIGHT,
    .baseline16le = NULL,
    .baseline_valid = 1,
  };
  uint8_t *baseline16le;
  uint8_t *frame16le;
  uint8_t *candidate;
  int status;

  if (baseline == NULL || frame == NULL || output == NULL)
    return GOODIX_SIGFM_PREPROCESS_INVALID_ARGUMENT;
  if (baseline_count != GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT ||
      frame_count != GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT)
    return GOODIX_SIGFM_PREPROCESS_INVALID_SAMPLE_COUNT;
  if (output_size < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT)
    return GOODIX_SIGFM_PREPROCESS_OUTPUT_TOO_SMALL;
  if (!samples_valid (baseline, baseline_count) ||
      !samples_valid (frame, frame_count))
    return GOODIX_SIGFM_PREPROCESS_SAMPLE_OUT_OF_RANGE;

  baseline16le = malloc (GOODIX_SIGFM_U16LE_BYTES);
  frame16le = malloc (GOODIX_SIGFM_U16LE_BYTES);
  candidate = malloc (GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
  if (baseline16le == NULL || frame16le == NULL || candidate == NULL)
    {
      free (baseline16le);
      free (frame16le);
      free (candidate);
      return GOODIX_SIGFM_PREPROCESS_ALLOCATION_FAILED;
    }

  encode_u16le (baseline, baseline16le, baseline_count);
  encode_u16le (frame, frame16le, frame_count);
  view.baseline16le = baseline16le;
  status = gx_imgproc_to8bit (&view, &params, frame16le, candidate);
  if (status == 0)
    memcpy (output, candidate, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);

  secure_clear (baseline16le, GOODIX_SIGFM_U16LE_BYTES);
  secure_clear (frame16le, GOODIX_SIGFM_U16LE_BYTES);
  secure_clear (candidate, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
  free (baseline16le);
  free (frame16le);
  free (candidate);

  return status == 0 ? GOODIX_SIGFM_PREPROCESS_OK :
                       GOODIX_SIGFM_PREPROCESS_EXECUTION_FAILED;
}
