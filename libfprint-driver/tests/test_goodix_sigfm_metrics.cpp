/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "../goodix_sigfm_metrics.h"
#include "support/sigfm_metric_test_double.h"

#include <cassert>
#include <cstdint>
#include <cstdio>

static void
fill (uint16_t *samples)
{
  for (size_t index = 0; index < 5120; ++index)
    samples[index] = static_cast<uint16_t> (index % 4096);
  samples[0] = 0;
  samples[1] = 1;
  samples[2] = 2048;
  samples[3] = 4095;
}

int
main ()
{
  uint16_t samples[5120];
  GoodixSigfmSample *one = nullptr;
  GoodixSigfmSample *two = nullptr;
  GoodixSigfmSample *copy = nullptr;
  GoodixSigfmSample *restored = nullptr;
  uint8_t *serialized = nullptr;
  size_t serialized_size = 0;
  int keypoints = -1;
  int score = -99;
  fill (samples);

  sigfm_test_set_mode (SIGFM_TEST_OK);
  sigfm_test_set_keypoints (30);
  assert (goodix_sigfm_extract_ephemeral (samples, 5120, &one, &keypoints) ==
          GOODIX_SIGFM_OK);
  assert (one != nullptr && keypoints == 30);
  assert (sigfm_test_last_width () == 80);
  assert (sigfm_test_last_height () == 64);
  assert (sigfm_test_last_pixel (0) == 0);
  assert (sigfm_test_last_pixel (1) == 0);
  assert (sigfm_test_last_pixel (2) == 128);
  assert (sigfm_test_last_pixel (3) == 255);

  uint8_t direct_pixels[5120] = {};
  GoodixSigfmSample *direct = nullptr;
  assert (goodix_sigfm_extract_pixels (
            direct_pixels, sizeof direct_pixels, &direct, &keypoints) ==
          GOODIX_SIGFM_OK);
  assert (direct != nullptr && keypoints == 30);
  goodix_sigfm_sample_free (direct);
  assert (goodix_sigfm_extract_ephemeral (samples, 5120, &two, &keypoints) ==
          GOODIX_SIGFM_OK);
  assert (sigfm_test_last_pixel (0) == 0);
  assert (sigfm_test_last_pixel (1) == 0);
  assert (sigfm_test_last_pixel (2) == 128);
  assert (sigfm_test_last_pixel (3) == 255);

  assert (goodix_sigfm_sample_copy (one, &copy) == GOODIX_SIGFM_OK);
  assert (copy != nullptr);
  assert (goodix_sigfm_sample_serialize (
            copy, &serialized, &serialized_size) == GOODIX_SIGFM_OK);
  assert (serialized != nullptr && serialized_size == 16244u);
  assert (goodix_sigfm_sample_deserialize (
            serialized, serialized_size, &restored, &keypoints) ==
          GOODIX_SIGFM_OK);
  assert (restored != nullptr && keypoints == 30);

  serialized[20] ^= 1u;
  GoodixSigfmSample *rejected = nullptr;
  assert (goodix_sigfm_sample_deserialize (
            serialized, serialized_size, &rejected, &keypoints) ==
          GOODIX_SIGFM_DESERIALIZE_INVALID);
  assert (rejected == nullptr);
  serialized[20] ^= 1u;
  assert (goodix_sigfm_sample_deserialize (
            serialized, serialized_size - 1u, &rejected, &keypoints) ==
          GOODIX_SIGFM_DESERIALIZE_INVALID);
  serialized[12] = 0;
  assert (goodix_sigfm_sample_deserialize (
            serialized, serialized_size, &rejected, &keypoints) ==
          GOODIX_SIGFM_DESERIALIZE_INVALID);
  serialized[12] = 30;

  sigfm_test_set_score (0);
  assert (goodix_sigfm_match_ephemeral (one, two, &score) == GOODIX_SIGFM_OK);
  assert (score == 0);
  sigfm_test_set_score (17);
  assert (goodix_sigfm_match_ephemeral (one, two, &score) == GOODIX_SIGFM_OK);
  assert (score == 17);
  sigfm_test_set_score (-1);
  assert (goodix_sigfm_match_ephemeral (one, two, &score) ==
          GOODIX_SIGFM_MATCH_ERROR);

  sigfm_test_set_mode (SIGFM_TEST_MATCH_THROW);
  assert (goodix_sigfm_match_ephemeral (one, two, &score) ==
          GOODIX_SIGFM_MATCH_EXCEPTION);
  sigfm_test_set_mode (SIGFM_TEST_OK);
  goodix_sigfm_serialized_free (serialized, serialized_size);
  goodix_sigfm_sample_free (restored);
  goodix_sigfm_sample_free (copy);
  goodix_sigfm_sample_free (one);
  goodix_sigfm_sample_free (two);
  assert (sigfm_test_live_info_count () == 0);
  one = nullptr;
  two = nullptr;

  sigfm_test_set_keypoints (24);
  assert (goodix_sigfm_extract_ephemeral (samples, 5120, &one, &keypoints) ==
          GOODIX_SIGFM_KEYPOINT_GATE_FAILED);
  assert (one == nullptr);
  assert (sigfm_test_live_info_count () == 0);
  sigfm_test_set_keypoints (GOODIX_SIGFM_MAX_KEYPOINTS + 1);
  assert (goodix_sigfm_extract_ephemeral (samples, 5120, &one, &keypoints) ==
          GOODIX_SIGFM_KEYPOINT_GATE_FAILED);
  assert (one == nullptr);
  assert (sigfm_test_live_info_count () == 0);
  sigfm_test_set_mode (SIGFM_TEST_EXTRACT_NULL);
  assert (goodix_sigfm_extract_ephemeral (samples, 5120, &one, &keypoints) ==
          GOODIX_SIGFM_EXTRACT_NULL);
  sigfm_test_set_mode (SIGFM_TEST_EXTRACT_THROW);
  assert (goodix_sigfm_extract_ephemeral (samples, 5120, &one, &keypoints) ==
          GOODIX_SIGFM_EXTRACT_EXCEPTION);
  sigfm_test_set_mode (SIGFM_TEST_OK);
  samples[10] = 4096;
  assert (goodix_sigfm_extract_ephemeral (samples, 5120, &one, &keypoints) ==
          GOODIX_SIGFM_MAPPING_FAILURE);
  assert (goodix_sigfm_extract_ephemeral (nullptr, 5120, &one, &keypoints) ==
          GOODIX_SIGFM_INVALID_ARGUMENT);
  assert (sigfm_test_live_info_count () == 0);

  std::puts ("goodix_sigfm_metrics synthetic: PASS");
  return 0;
}
