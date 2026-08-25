/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Synthetic-only executable closure for the real local SIGFM implementation. */
#include "../goodix_sigfm_metrics.h"

#include <cassert>
#include <cstdint>
#include <cstdio>

static void
fill_synthetic (uint16_t *samples)
{
  uint32_t state = 0x27301u;
  for (size_t index = 0; index < 5120; ++index)
    {
      state = state * 1664525u + 1013904223u;
      samples[index] = static_cast<uint16_t> ((state >> 12) & 0x0fffu);
    }
}

static GoodixSigfmResult
extract_once (const uint16_t *samples, GoodixSigfmSample **sample, int *keypoints)
{
  GoodixSigfmResult result = goodix_sigfm_extract_ephemeral (
    samples, 5120, sample, keypoints);
  assert (result == GOODIX_SIGFM_OK ||
          result == GOODIX_SIGFM_KEYPOINT_GATE_FAILED ||
          result == GOODIX_SIGFM_EXTRACT_NULL);
  assert ((result == GOODIX_SIGFM_OK) == (*sample != nullptr));
  return result;
}

int
main ()
{
  uint16_t samples[5120];
  GoodixSigfmSample *first = nullptr;
  GoodixSigfmSample *second = nullptr;
  int first_keypoints = 0;
  int second_keypoints = 0;
  int score = 0;

  fill_synthetic (samples);
  GoodixSigfmResult first_result = extract_once (
    samples, &first, &first_keypoints);
  GoodixSigfmResult second_result = extract_once (
    samples, &second, &second_keypoints);
  assert (first_result == second_result);
  assert (first_keypoints == second_keypoints);
  if (first_result == GOODIX_SIGFM_OK)
    {
      assert (first_keypoints >= 25);
      assert (goodix_sigfm_match_ephemeral (first, second, &score) ==
              GOODIX_SIGFM_OK);
      assert (score >= 0);
    }

  goodix_sigfm_sample_free (first);
  goodix_sigfm_sample_free (second);
  for (size_t index = 0; index < 5120; ++index)
    samples[index] = 0;
  std::puts ("goodix real SIGFM synthetic plumbing: PASS");
  return 0;
}
