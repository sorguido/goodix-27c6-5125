/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_U16_TO_FPIMAGE_H
#define GOODIX_U16_TO_FPIMAGE_H

#include <stddef.h>
#include <stdint.h>

#define GOODIX_CANONICAL_IMAGE_WIDTH 80u
#define GOODIX_CANONICAL_IMAGE_HEIGHT 64u
#define GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT \
  (GOODIX_CANONICAL_IMAGE_WIDTH * GOODIX_CANONICAL_IMAGE_HEIGHT)
#define GOODIX_SENSOR_SAMPLE_MAX 4095u

/*
 * The current local libfprint FpImage contract has no stride field and stores
 * one guint8 per pixel.  Zero flags deliberately preserve the canonical
 * decoder raster: physical/natural fingerprint orientation is unresolved.
 */
#define GOODIX_LIBFPRINT_IMAGE_FLAGS_NONE 0u

typedef enum
{
  GOODIX_U16_TO_FPIMAGE_OK = 0,
  GOODIX_U16_TO_FPIMAGE_INVALID_ARGUMENT,
  GOODIX_U16_TO_FPIMAGE_INVALID_SAMPLE_COUNT,
  GOODIX_U16_TO_FPIMAGE_OUTPUT_TOO_SMALL,
  GOODIX_U16_TO_FPIMAGE_SAMPLE_OUT_OF_RANGE,
} GoodixU16ToFpImageResult;

typedef struct
{
  size_t width;
  size_t height;
  size_t stride;
  size_t data_length;
  uint32_t libfprint_image_flags;
  int canonical_orientation_preserved;
  int natural_orientation_resolved;
} GoodixLibfprintImageMetadata;

/*
 * Convert the canonical Goodix 80x64 u16/12-bit raster to the byte buffer
 * required by FpImage.  The fixed Linux-specific mapping is
 * round(sample * 255 / 4095).  Inputs are validated completely before output
 * or metadata is changed.  Input and output buffers must not overlap.
 */
GoodixU16ToFpImageResult
goodix_u16_to_fpimage (const uint16_t                 *samples,
                       size_t                          sample_count,
                       uint8_t                        *output,
                       size_t                          output_size,
                       GoodixLibfprintImageMetadata   *metadata);

#endif
