/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_sigfm_metrics.h"

#include "goodix_u16_to_fpimage.h"
#include "sigfm.h"

#include <new>

struct GoodixSigfmSample
{
  SigfmImgInfo *info;
};

static void
secure_clear (uint8_t *buffer, size_t length)
{
  volatile uint8_t *cursor = buffer;
  while (length-- > 0)
    *cursor++ = 0;
}

GoodixSigfmResult
goodix_sigfm_extract_ephemeral (const uint16_t      *samples,
                                size_t               sample_count,
                                GoodixSigfmSample  **sample_out,
                                int                 *keypoints_out)
{
  uint8_t pixels[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  GoodixLibfprintImageMetadata metadata = {};
  GoodixU16ToFpImageResult mapped;
  SigfmImgInfo *info = nullptr;
  GoodixSigfmSample *result = nullptr;
  int keypoints = 0;

  if (samples == nullptr || sample_out == nullptr || keypoints_out == nullptr)
    return GOODIX_SIGFM_INVALID_ARGUMENT;

  *sample_out = nullptr;
  *keypoints_out = 0;
  mapped = goodix_u16_to_fpimage (samples, sample_count, pixels,
                                  sizeof pixels, &metadata);
  if (mapped != GOODIX_U16_TO_FPIMAGE_OK)
    {
      secure_clear (pixels, sizeof pixels);
      return GOODIX_SIGFM_MAPPING_FAILURE;
    }

  try
    {
      info = sigfm_extract (pixels, static_cast<int> (metadata.width),
                            static_cast<int> (metadata.height));
      secure_clear (pixels, sizeof pixels);
      if (info == nullptr)
        return GOODIX_SIGFM_EXTRACT_NULL;
      keypoints = sigfm_keypoints_count (info);
      if (keypoints < 25)
        {
          sigfm_free_info (info);
          return GOODIX_SIGFM_KEYPOINT_GATE_FAILED;
        }
      result = new (std::nothrow) GoodixSigfmSample { info };
      if (result == nullptr)
        {
          sigfm_free_info (info);
          return GOODIX_SIGFM_EXTRACT_NULL;
        }
    }
  catch (...)
    {
      secure_clear (pixels, sizeof pixels);
      if (info != nullptr)
        {
          try
            {
              sigfm_free_info (info);
            }
          catch (...)
            {
            }
        }
      return GOODIX_SIGFM_EXTRACT_EXCEPTION;
    }

  *keypoints_out = keypoints;
  *sample_out = result;
  return GOODIX_SIGFM_OK;
}

GoodixSigfmResult
goodix_sigfm_match_ephemeral (GoodixSigfmSample *frame,
                              GoodixSigfmSample *enrolled,
                              int               *score_out)
{
  int score;
  if (frame == nullptr || enrolled == nullptr || score_out == nullptr ||
      frame->info == nullptr || enrolled->info == nullptr)
    return GOODIX_SIGFM_INVALID_ARGUMENT;

  *score_out = 0;
  try
    {
      score = sigfm_match_score (frame->info, enrolled->info);
    }
  catch (...)
    {
      return GOODIX_SIGFM_MATCH_EXCEPTION;
    }
  if (score < 0)
    return GOODIX_SIGFM_MATCH_ERROR;
  *score_out = score;
  return GOODIX_SIGFM_OK;
}

void
goodix_sigfm_sample_free (GoodixSigfmSample *sample)
{
  if (sample == nullptr)
    return;
  if (sample->info != nullptr)
    {
      try
        {
          sigfm_free_info (sample->info);
        }
      catch (...)
        {
        }
      sample->info = nullptr;
    }
  delete sample;
}
