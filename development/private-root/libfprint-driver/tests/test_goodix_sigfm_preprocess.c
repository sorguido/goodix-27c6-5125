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

static void
test_session_coupled_baseline_variation (void)
{
  uint16_t baseline_a[N];
  uint16_t baseline_b[N];
  uint16_t frame_a[N];
  uint16_t frame_b[N];
  uint8_t paired_a[N];
  uint8_t paired_b[N];
  uint8_t stale_baseline[N];
  size_t changed = 0u;

  /* Model two independently opened sessions.  The same non-biometric local
   * relief rides on the B0 measured in that session, while B0 itself changes
   * spatially.  This is the physically coupled case that the former D291
   * fixed-raw-frame fixture did not represent. */
  for (size_t y = 0; y < GOODIX_CANONICAL_IMAGE_HEIGHT; y++)
    for (size_t x = 0; x < GOODIX_CANONICAL_IMAGE_WIDTH; x++)
      {
        size_t index = y * GOODIX_CANONICAL_IMAGE_WIDTH + x;
        int relief = (int) ((x * 41u + y * 67u + (x * y) % 53u) % 1001u) -
                     500;
        int spatial_drift =
          ((x / 4u + y / 5u) % 2u == 0u ? 260 : -220) +
          (int) ((3u * x + 5u * y) % 47u) - 23;

        baseline_a[index] = (uint16_t) (1800u +
          (x * 7u + y * 11u + (x * y) % 17u) % 301u);
        baseline_b[index] = clamp_u12 ((int) baseline_a[index] +
                                        spatial_drift);
        frame_a[index] = clamp_u12 ((int) baseline_a[index] + relief);
        frame_b[index] = clamp_u12 ((int) baseline_b[index] + relief);
      }

  assert (goodix_sigfm_preprocess_r2 (
            baseline_a, N, frame_a, N, paired_a, sizeof paired_a) ==
          GOODIX_SIGFM_PREPROCESS_OK);
  assert (goodix_sigfm_preprocess_r2 (
            baseline_b, N, frame_b, N, paired_b, sizeof paired_b) ==
          GOODIX_SIGFM_PREPROCESS_OK);
  assert (memcmp (paired_a, paired_b, sizeof paired_a) == 0);

  assert (goodix_sigfm_preprocess_r2 (
            baseline_a, N, frame_b, N, stale_baseline,
            sizeof stale_baseline) == GOODIX_SIGFM_PREPROCESS_OK);
  for (size_t i = 0; i < N; i++)
    if (stale_baseline[i] != paired_b[i])
      changed++;
  assert (changed > N / 2u);
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

  test_session_coupled_baseline_variation ();

  assert (goodix_sigfm_preprocess_r2 (
            baseline, N, frame, N, output, sizeof output) ==
          GOODIX_SIGFM_PREPROCESS_OK);
  assert (fwrite (output, 1, sizeof output, stdout) == sizeof output);
  return 0;
}
