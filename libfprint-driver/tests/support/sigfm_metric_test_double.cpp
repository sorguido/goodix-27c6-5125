/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "sigfm_metric_test_double.h"
#include "sigfm.h"

#include <stdexcept>

struct SigfmImgInfo
{
  int marker;
};

static SigfmTestMode mode = SIGFM_TEST_OK;
static int keypoint_count = 30;
static int match_score = 0;
static int last_width = 0;
static int last_height = 0;
static unsigned int last_pixels[4] = {};
static int live_info_count = 0;

void sigfm_test_set_mode (SigfmTestMode value) { mode = value; }
void sigfm_test_set_keypoints (int value) { keypoint_count = value; }
void sigfm_test_set_score (int value) { match_score = value; }
int sigfm_test_last_width (void) { return last_width; }
int sigfm_test_last_height (void) { return last_height; }
unsigned int sigfm_test_last_pixel (unsigned int index)
{
  return index < 4 ? last_pixels[index] : 0;
}
int sigfm_test_live_info_count (void) { return live_info_count; }

extern "C" SigfmImgInfo *
sigfm_extract (const SigfmPix *pixels, int width, int height)
{
  last_width = width;
  last_height = height;
  for (unsigned int index = 0; index < 4; ++index)
    last_pixels[index] = pixels[index];
  if (mode == SIGFM_TEST_EXTRACT_THROW)
    throw std::runtime_error ("synthetic extract exception");
  if (mode == SIGFM_TEST_EXTRACT_NULL)
    return nullptr;
  SigfmImgInfo *info = new SigfmImgInfo { 0x5125 };
  ++live_info_count;
  return info;
}

extern "C" void
sigfm_free_info (SigfmImgInfo *info)
{
  if (info != nullptr)
    --live_info_count;
  delete info;
}

extern "C" int
sigfm_keypoints_count (SigfmImgInfo *info)
{
  return info == nullptr ? -1 : keypoint_count;
}

extern "C" int
sigfm_match_score (SigfmImgInfo *, SigfmImgInfo *)
{
  if (mode == SIGFM_TEST_MATCH_THROW)
    throw std::runtime_error ("synthetic match exception");
  return match_score;
}
