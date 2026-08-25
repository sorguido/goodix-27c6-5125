/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "../goodix_u16_to_fpimage.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
static uint16_t snapshot[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
static uint8_t output_a[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
static uint8_t output_b[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];

static void
fill (uint16_t value)
{
  size_t index;

  for (index = 0; index < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT; index++)
    samples[index] = value;
}

static void
test_valid_gradient_kat_and_metadata (void)
{
  GoodixLibfprintImageMetadata metadata = { 0 };
  size_t index;

  for (index = 0; index < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT; index++)
    samples[index] = (uint16_t) (index % 4096u);
  memcpy (snapshot, samples, sizeof samples);

  assert (goodix_u16_to_fpimage (samples,
                                 GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT,
                                 output_a,
                                 sizeof output_a,
                                 &metadata) == GOODIX_U16_TO_FPIMAGE_OK);
  assert (metadata.width == 80u);
  assert (metadata.height == 64u);
  assert (metadata.stride == 80u);
  assert (metadata.data_length == 5120u);
  assert (metadata.libfprint_image_flags == 0u);
  assert (metadata.canonical_orientation_preserved == 1);
  assert (metadata.natural_orientation_resolved == 0);
  assert (output_a[0] == 0u);
  assert (output_a[8] == 0u);
  assert (output_a[9] == 1u);
  assert (output_a[257] == 16u);
  assert (output_a[1024] == 64u);
  assert (output_a[2047] == 127u);
  assert (output_a[2048] == 128u);
  assert (output_a[3072] == 191u);
  assert (output_a[4095] == 255u);
  assert (memcmp (samples, snapshot, sizeof samples) == 0);

  for (index = 1; index < 4096u; index++)
    assert (output_a[index - 1] <= output_a[index]);
}

static void
test_minimum_maximum_and_determinism (void)
{
  GoodixLibfprintImageMetadata metadata_a = { 0 };
  GoodixLibfprintImageMetadata metadata_b = { 0 };
  size_t index;

  fill (0u);
  assert (goodix_u16_to_fpimage (samples, 5120u, output_a,
                                 sizeof output_a, &metadata_a) ==
          GOODIX_U16_TO_FPIMAGE_OK);
  for (index = 0; index < sizeof output_a; index++)
    assert (output_a[index] == 0u);

  fill (4095u);
  memcpy (snapshot, samples, sizeof samples);
  assert (goodix_u16_to_fpimage (samples, 5120u, output_a,
                                 sizeof output_a, &metadata_a) ==
          GOODIX_U16_TO_FPIMAGE_OK);
  assert (goodix_u16_to_fpimage (samples, 5120u, output_b,
                                 sizeof output_b, &metadata_b) ==
          GOODIX_U16_TO_FPIMAGE_OK);
  assert (memcmp (output_a, output_b, sizeof output_a) == 0);
  assert (memcmp (&metadata_a, &metadata_b, sizeof metadata_a) == 0);
  assert (memcmp (samples, snapshot, sizeof samples) == 0);
  for (index = 0; index < sizeof output_a; index++)
    assert (output_a[index] == 255u);
}

static void
test_mapping_is_frame_independent (void)
{
  GoodixLibfprintImageMetadata metadata = { 0 };

  fill (0u);
  samples[123] = 2048u;
  assert (goodix_u16_to_fpimage (samples, 5120u, output_a,
                                 sizeof output_a, &metadata) ==
          GOODIX_U16_TO_FPIMAGE_OK);

  fill (4095u);
  samples[123] = 2048u;
  assert (goodix_u16_to_fpimage (samples, 5120u, output_b,
                                 sizeof output_b, &metadata) ==
          GOODIX_U16_TO_FPIMAGE_OK);
  assert (output_a[123] == 128u);
  assert (output_b[123] == 128u);
}

static void
test_rejections_are_fail_closed (void)
{
  GoodixLibfprintImageMetadata metadata;
  GoodixLibfprintImageMetadata unchanged_metadata;
  size_t index;

  fill (7u);
  memset (output_a, 0xa5, sizeof output_a);
  memset (&metadata, 0x5a, sizeof metadata);
  unchanged_metadata = metadata;

  assert (goodix_u16_to_fpimage (samples, 5119u, output_a,
                                 sizeof output_a, &metadata) ==
          GOODIX_U16_TO_FPIMAGE_INVALID_SAMPLE_COUNT);
  assert (goodix_u16_to_fpimage (samples, 5120u, output_a,
                                 sizeof output_a - 1u, &metadata) ==
          GOODIX_U16_TO_FPIMAGE_OUTPUT_TOO_SMALL);

  samples[4096] = 4096u;
  assert (goodix_u16_to_fpimage (samples, 5120u, output_a,
                                 sizeof output_a, &metadata) ==
          GOODIX_U16_TO_FPIMAGE_SAMPLE_OUT_OF_RANGE);
  for (index = 0; index < sizeof output_a; index++)
    assert (output_a[index] == 0xa5u);
  assert (memcmp (&metadata, &unchanged_metadata, sizeof metadata) == 0);

  /* A negative source value is not representable by uint16_t; its casted
   * representation is nevertheless rejected by the sensor-domain gate. */
  samples[4096] = (uint16_t) -1;
  assert (goodix_u16_to_fpimage (samples, 5120u, output_a,
                                 sizeof output_a, &metadata) ==
          GOODIX_U16_TO_FPIMAGE_SAMPLE_OUT_OF_RANGE);

  assert (goodix_u16_to_fpimage (NULL, 5120u, output_a,
                                 sizeof output_a, &metadata) ==
          GOODIX_U16_TO_FPIMAGE_INVALID_ARGUMENT);
  assert (goodix_u16_to_fpimage (samples, 5120u, NULL,
                                 sizeof output_a, &metadata) ==
          GOODIX_U16_TO_FPIMAGE_INVALID_ARGUMENT);
  assert (goodix_u16_to_fpimage (samples, 5120u, output_a,
                                 sizeof output_a, NULL) ==
          GOODIX_U16_TO_FPIMAGE_INVALID_ARGUMENT);
}

int
main (void)
{
  test_valid_gradient_kat_and_metadata ();
  test_minimum_maximum_and_determinism ();
  test_mapping_is_frame_independent ();
  test_rejections_are_fail_closed ();
  puts ("goodix_u16_to_fpimage: PASS");
  return 0;
}
