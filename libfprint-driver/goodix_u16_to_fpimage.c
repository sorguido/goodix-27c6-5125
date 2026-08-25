/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_u16_to_fpimage.h"

static uint8_t
map_sample_to_u8 (uint16_t sample)
{
  /* uint32_t is ample: 4095 * 255 + 4095 / 2 < 2^20. */
  return (uint8_t) ((((uint32_t) sample * 255u) +
                     (GOODIX_SENSOR_SAMPLE_MAX / 2u)) /
                    GOODIX_SENSOR_SAMPLE_MAX);
}

GoodixU16ToFpImageResult
goodix_u16_to_fpimage (const uint16_t                *samples,
                       size_t                         sample_count,
                       uint8_t                       *output,
                       size_t                         output_size,
                       GoodixLibfprintImageMetadata  *metadata)
{
  size_t index;

  if (samples == NULL || output == NULL || metadata == NULL)
    return GOODIX_U16_TO_FPIMAGE_INVALID_ARGUMENT;

  if (sample_count != GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT)
    return GOODIX_U16_TO_FPIMAGE_INVALID_SAMPLE_COUNT;

  if (output_size < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT)
    return GOODIX_U16_TO_FPIMAGE_OUTPUT_TOO_SMALL;

  /* Fail without partially changing caller-owned output or metadata. */
  for (index = 0; index < sample_count; index++)
    {
      if (samples[index] > GOODIX_SENSOR_SAMPLE_MAX)
        return GOODIX_U16_TO_FPIMAGE_SAMPLE_OUT_OF_RANGE;
    }

  for (index = 0; index < sample_count; index++)
    output[index] = map_sample_to_u8 (samples[index]);

  metadata->width = GOODIX_CANONICAL_IMAGE_WIDTH;
  metadata->height = GOODIX_CANONICAL_IMAGE_HEIGHT;
  metadata->stride = GOODIX_CANONICAL_IMAGE_WIDTH;
  metadata->data_length = GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT;
  metadata->libfprint_image_flags = GOODIX_LIBFPRINT_IMAGE_FLAGS_NONE;
  metadata->canonical_orientation_preserved = 1;
  metadata->natural_orientation_resolved = 0;

  return GOODIX_U16_TO_FPIMAGE_OK;
}
