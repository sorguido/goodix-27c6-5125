/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Synthetic-only executable closure for the real local SIGFM implementation.
 *
 * This test exercises the POSITIVE runtime path deterministically:
 *   extract succeeds above the >=25 keypoint gate  AND
 *   the match path executes through sigfm_match_score().
 *
 * It uses a structured synthetic fixture (no target image, no biometric
 * corpus, no target-derived pixels, no threshold tuning, no orientation or
 * polarity assumption). A separate negative test covers the keypoint gate
 * without making the positive test ambiguous.
 */
#include "../goodix_sigfm_metrics.h"

#include <cassert>
#include <cstdint>
#include <cstdio>

#define W 80
#define H 64
#define N (W * H)

/* Deterministic structured synthetic raster: 8x8 blocks of 4x4 bright cells
 * over a dark field, with an additional 1px grating overlay. Verified to
 * produce a stable, large keypoint count under OpenCV 4.5.4 SIFT. */
static void
fill_synthetic_positive (uint16_t *samples)
{
  for (int y = 0; y < H; ++y)
    for (int x = 0; x < W; ++x)
      {
        int gx = x % 8;
        int gy = y % 8;
        int v = (gx < 4 && gy < 4) ? 4095 : 0;
        if (((x + y) & 1) == 0)
          v = (v == 0) ? 2048 : v;
        samples[y * W + x] = static_cast<uint16_t> (v);
      }
}

/* Flat raster -> no gradient -> zero keypoints -> keypoint gate must fail. */
static void
fill_synthetic_flat (uint16_t *samples)
{
  for (int i = 0; i < N; ++i)
    samples[i] = 0;
}

static int
extract_positive (const uint16_t *samples,
                  GoodixSigfmSample **sample,
                  int *keypoints)
{
  GoodixSigfmResult result = goodix_sigfm_extract_ephemeral (
    samples, N, sample, keypoints);
  if (result != GOODIX_SIGFM_OK)
    return 1;
  assert (*sample != nullptr);
  assert (*keypoints >= 25);
  return 0;
}

int
main ()
{
  uint16_t pos[N];
  uint16_t flat[N];
  GoodixSigfmSample *first = nullptr;
  GoodixSigfmSample *second = nullptr;
  int first_keypoints = 0;
  int second_keypoints = 0;
  int score = 0;

  /* --- POSITIVE runtime path (must actually be traversed) --- */
  fill_synthetic_positive (pos);
  if (extract_positive (pos, &first, &first_keypoints))
    {
      std::fputs ("REAL_SIGFM_POSITIVE_EXTRACT=FAIL\n", stdout);
      return 1;
    }
  if (extract_positive (pos, &second, &second_keypoints))
    {
      goodix_sigfm_sample_free (first);
      std::fputs ("REAL_SIGFM_POSITIVE_EXTRACT=FAIL\n", stdout);
      return 1;
    }
  assert (first_keypoints == second_keypoints);

  GoodixSigfmResult match_result =
    goodix_sigfm_match_ephemeral (first, second, &score);
  assert (match_result == GOODIX_SIGFM_OK);
  assert (score >= 0);

  std::printf ("REAL_SIGFM_POSITIVE_EXTRACT=PASS\n");
  std::printf ("REAL_SIGFM_KEYPOINTS=%d\n", first_keypoints);
  std::printf ("REAL_SIGFM_MATCH_PATH=PASS\n");
  std::printf ("REAL_SIGFM_IDENTICAL_FIXTURE_SCORE=%d\n", score);

  goodix_sigfm_sample_free (first);
  goodix_sigfm_sample_free (second);

  /* --- NEGATIVE gate test (separate; does not make the positive PASS) --- */
  fill_synthetic_flat (flat);
  GoodixSigfmSample *neg = nullptr;
  int neg_keypoints = 0;
  GoodixSigfmResult neg_result =
    goodix_sigfm_extract_ephemeral (flat, N, &neg, &neg_keypoints);
  assert (neg_result == GOODIX_SIGFM_KEYPOINT_GATE_FAILED);
  assert (neg == nullptr);
  assert (neg_keypoints == 0);

  std::puts ("goodix real SIGFM synthetic plumbing: PASS");
  return 0;
}
