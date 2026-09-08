/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "../goodix_sigfm_preprocess.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define N GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT

static uint16_t
clamp_u12 (int value)
{
  if (value < 0)
    return 0;
  if (value > (int) GOODIX_SENSOR_SAMPLE_MAX)
    return GOODIX_SENSOR_SAMPLE_MAX;
  return (uint16_t) value;
}

int
main (void)
{
  uint16_t baseline[N];
  uint16_t frame[N];
  uint8_t output[N];
  uint8_t unchanged[N];

  for (size_t y = 0; y < GOODIX_CANONICAL_IMAGE_HEIGHT; y++)
    for (size_t x = 0; x < GOODIX_CANONICAL_IMAGE_WIDTH; x++)
      {
        size_t index = y * GOODIX_CANONICAL_IMAGE_WIDTH + x;
        int value = 1500 +
          (int) ((x * 17u + y * 29u + (x * y) % 31u) % 700u);
        int delta = (int) ((index * 43u + y * 11u) % 401u) - 200;

        baseline[index] = (uint16_t) value;
        frame[index] = clamp_u12 (value + delta);
      }

  memset (unchanged, 0xa5, sizeof unchanged);
  assert (goodix_sigfm_preprocess_r2 (
            NULL, N, frame, N, unchanged, sizeof unchanged) ==
          GOODIX_SIGFM_PREPROCESS_INVALID_ARGUMENT);
  assert (goodix_sigfm_preprocess_r2 (
            baseline, N - 1u, frame, N, unchanged, sizeof unchanged) ==
          GOODIX_SIGFM_PREPROCESS_INVALID_SAMPLE_COUNT);
  assert (goodix_sigfm_preprocess_r2 (
            baseline, N, frame, N, unchanged, N - 1u) ==
          GOODIX_SIGFM_PREPROCESS_OUTPUT_TOO_SMALL);
  frame[17] = GOODIX_SENSOR_SAMPLE_MAX + 1u;
  assert (goodix_sigfm_preprocess_r2 (
            baseline, N, frame, N, unchanged, sizeof unchanged) ==
          GOODIX_SIGFM_PREPROCESS_SAMPLE_OUT_OF_RANGE);
  for (size_t i = 0; i < N; i++)
    assert (unchanged[i] == 0xa5);
  frame[17] = clamp_u12 ((int) baseline[17] +
                         (int) ((17u * 43u) % 401u) - 200);

  assert (goodix_sigfm_preprocess_r2 (
            baseline, N, frame, N, output, sizeof output) ==
          GOODIX_SIGFM_PREPROCESS_OK);
  assert (fwrite (output, 1, sizeof output, stdout) == sizeof output);
  return 0;
}
