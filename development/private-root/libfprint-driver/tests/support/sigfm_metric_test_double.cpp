/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "sigfm_metric_test_double.h"
#include "sigfm.h"

#include <cstdlib>
#include <cstring>
#include <stdexcept>

struct SigfmImgInfo
{
  int marker;
  int keypoints;
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
  SigfmImgInfo *info = new SigfmImgInfo { 0x5125, keypoint_count };
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
  return info == nullptr ? -1 : info->keypoints;
}

extern "C" int
sigfm_match_score (SigfmImgInfo *, SigfmImgInfo *)
{
  if (mode == SIGFM_TEST_MATCH_THROW)
    throw std::runtime_error ("synthetic match exception");
  return match_score;
}

extern "C" SigfmImgInfo *
sigfm_copy_info (SigfmImgInfo *info)
{
  if (mode == SIGFM_TEST_COPY_THROW)
    throw std::runtime_error ("synthetic copy exception");
  if (info == nullptr)
    return nullptr;
  auto *copy = new SigfmImgInfo { *info };
  ++live_info_count;
  return copy;
}

extern "C" unsigned char *
sigfm_serialize_binary (SigfmImgInfo *info,
                        int          *size_out)
{
  const size_t keypoints = static_cast<size_t> (info->keypoints);
  const size_t matrix_header = 8u + keypoints * 28u;
  const size_t size = 20u + keypoints * 540u;
  auto *data = static_cast<unsigned char *> (std::calloc (1, size));
  const int type = 5;
  const int rows = info->keypoints;
  const int columns = 128;

  if (data == nullptr)
    return nullptr;
  std::memcpy (data, &keypoints, sizeof keypoints);
  std::memcpy (&data[matrix_header], &type, sizeof type);
  std::memcpy (&data[matrix_header + 4u], &rows, sizeof rows);
  std::memcpy (&data[matrix_header + 8u], &columns, sizeof columns);
  for (size_t i = 0; i < keypoints; i++)
    {
      const size_t point = 8u + i * 28u;
      const float angle = 1.0f;
      const float response = 1.0f;
      const float scale = 1.0f;
      const float x = 1.0f;
      const float y = 1.0f;

      std::memcpy (&data[point + 4u], &angle, sizeof angle);
      std::memcpy (&data[point + 12u], &response, sizeof response);
      std::memcpy (&data[point + 16u], &scale, sizeof scale);
      std::memcpy (&data[point + 20u], &x, sizeof x);
      std::memcpy (&data[point + 24u], &y, sizeof y);
    }
  *size_out = static_cast<int> (size);
  return data;
}

extern "C" SigfmImgInfo *
sigfm_deserialize_binary (const unsigned char *data,
                          int                  size)
{
  size_t keypoints = 0;

  if (data == nullptr || size < 20)
    return nullptr;
  std::memcpy (&keypoints, data, sizeof keypoints);
  auto *info = new SigfmImgInfo {
    0x5125, static_cast<int> (keypoints)
  };
  ++live_info_count;
  return info;
}
