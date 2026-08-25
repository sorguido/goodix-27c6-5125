/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "../goodix_fpimage_pipeline.h"
#include "../goodix_u16_to_fpimage.h"

#include <fpi-image.h>
#include <glib-object.h>

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
static uint16_t snapshot[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];

static void
fill (uint16_t value)
{
  size_t index;

  for (index = 0; index < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT; index++)
    samples[index] = value;
}

static void
test_real_object_construction_and_lifetime (void)
{
  GoodixFpImagePipeline *pipeline = NULL;
  FpImage *image;
  FpImage *weak_image;
  const guchar *data;
  gsize data_length = 0;
  size_t index;

  for (index = 0; index < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT; index++)
    samples[index] = (uint16_t) (index % 4096u);
  memcpy (snapshot, samples, sizeof samples);

  assert (goodix_fpimage_pipeline_new (
            samples, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT, &pipeline) ==
          GOODIX_FPIMAGE_PIPELINE_OK);
  assert (pipeline != NULL);

  image = goodix_fpimage_pipeline_get_image (pipeline);
  assert (FP_IS_IMAGE (image));
  assert (fp_image_get_width (image) == GOODIX_CANONICAL_IMAGE_WIDTH);
  assert (fp_image_get_height (image) == GOODIX_CANONICAL_IMAGE_HEIGHT);

  data = fp_image_get_data (image, &data_length);
  assert (data != NULL);
  assert (data == image->data);
  assert (data_length == GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
  assert (data[0] == 0u);
  assert (data[8] == 0u);
  assert (data[9] == 1u);
  assert (data[2047] == 127u);
  assert (data[2048] == 128u);
  assert (data[4095] == 255u);
  assert (memcmp (samples, snapshot, sizeof samples) == 0);

  assert (image->width == 80u);
  assert (image->height == 64u);
  assert (image->flags == 0u);
  assert (image->ppmm == 0.0);
  assert (image->binarized == NULL);
  assert (image->minutiae == NULL);
  assert (image->sigfm_info == NULL);
  assert (image->ref_count == 0u);
  assert (goodix_fpimage_pipeline_get_physical_ppmm_state (pipeline) ==
          GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN);

  weak_image = image;
  g_object_add_weak_pointer (G_OBJECT (image), (gpointer *) &weak_image);
  goodix_fpimage_pipeline_free (pipeline);
  assert (weak_image == NULL);
}

static void
test_determinism_and_frame_independence (void)
{
  GoodixFpImagePipeline *pipeline_a = NULL;
  GoodixFpImagePipeline *pipeline_b = NULL;
  const guchar *data_a;
  const guchar *data_b;
  gsize length_a = 0;
  gsize length_b = 0;

  fill (0u);
  samples[123] = 2048u;
  assert (goodix_fpimage_pipeline_new (samples, 5120u, &pipeline_a) ==
          GOODIX_FPIMAGE_PIPELINE_OK);

  fill (4095u);
  samples[123] = 2048u;
  assert (goodix_fpimage_pipeline_new (samples, 5120u, &pipeline_b) ==
          GOODIX_FPIMAGE_PIPELINE_OK);

  data_a = fp_image_get_data (
    goodix_fpimage_pipeline_get_image (pipeline_a), &length_a);
  data_b = fp_image_get_data (
    goodix_fpimage_pipeline_get_image (pipeline_b), &length_b);
  assert (length_a == 5120u);
  assert (length_b == 5120u);
  assert (data_a[123] == 128u);
  assert (data_b[123] == 128u);

  goodix_fpimage_pipeline_free (pipeline_a);
  goodix_fpimage_pipeline_free (pipeline_b);
  pipeline_a = NULL;
  pipeline_b = NULL;

  fill (317u);
  assert (goodix_fpimage_pipeline_new (samples, 5120u, &pipeline_a) ==
          GOODIX_FPIMAGE_PIPELINE_OK);
  assert (goodix_fpimage_pipeline_new (samples, 5120u, &pipeline_b) ==
          GOODIX_FPIMAGE_PIPELINE_OK);
  data_a = fp_image_get_data (
    goodix_fpimage_pipeline_get_image (pipeline_a), &length_a);
  data_b = fp_image_get_data (
    goodix_fpimage_pipeline_get_image (pipeline_b), &length_b);
  assert (memcmp (data_a, data_b, 5120u) == 0);

  goodix_fpimage_pipeline_free (pipeline_a);
  goodix_fpimage_pipeline_free (pipeline_b);
}

static void
test_ppmm_gate_is_truth_preserving (void)
{
  GoodixFpImagePipeline *pipeline = NULL;

  fill (1024u);
  assert (goodix_fpimage_pipeline_new (samples, 5120u, &pipeline) ==
          GOODIX_FPIMAGE_PIPELINE_OK);
  assert (goodix_fpimage_pipeline_check_ppmm_requirement (
            pipeline, GOODIX_FPIMAGE_PPMM_CONSUMER_NBIS) ==
          GOODIX_FPIMAGE_PIPELINE_PHYSICAL_PPMM_REQUIRED);
  assert (goodix_fpimage_pipeline_check_ppmm_requirement (
            pipeline, GOODIX_FPIMAGE_PPMM_CONSUMER_SIGFM) ==
          GOODIX_FPIMAGE_PIPELINE_OK);
  assert (goodix_fpimage_pipeline_check_ppmm_requirement (
            pipeline, (GoodixFpImagePpmmConsumer) 99) ==
          GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT);
  assert (goodix_fpimage_pipeline_check_ppmm_requirement (
            NULL, GOODIX_FPIMAGE_PPMM_CONSUMER_NBIS) ==
          GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT);

  goodix_fpimage_pipeline_free (pipeline);
}

static void
test_failures_leave_output_unchanged (void)
{
  GoodixFpImagePipeline *pipeline = NULL;

  fill (7u);
  assert (goodix_fpimage_pipeline_new (NULL, 5120u, &pipeline) ==
          GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT);
  assert (pipeline == NULL);
  assert (goodix_fpimage_pipeline_new (samples, 5120u, NULL) ==
          GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT);
  assert (goodix_fpimage_pipeline_new (samples, 5119u, &pipeline) ==
          GOODIX_FPIMAGE_PIPELINE_INVALID_SAMPLE_COUNT);
  assert (pipeline == NULL);

  samples[4096] = 4096u;
  assert (goodix_fpimage_pipeline_new (samples, 5120u, &pipeline) ==
          GOODIX_FPIMAGE_PIPELINE_SAMPLE_OUT_OF_RANGE);
  assert (pipeline == NULL);

  samples[4096] = 7u;
  assert (goodix_fpimage_pipeline_new (samples, 5120u, &pipeline) ==
          GOODIX_FPIMAGE_PIPELINE_OK);
  assert (goodix_fpimage_pipeline_new (samples, 5120u, &pipeline) ==
          GOODIX_FPIMAGE_PIPELINE_INVALID_ARGUMENT);
  goodix_fpimage_pipeline_free (pipeline);
  goodix_fpimage_pipeline_free (NULL);
}

int
main (void)
{
  test_real_object_construction_and_lifetime ();
  test_determinism_and_frame_independence ();
  test_ppmm_gate_is_truth_preserving ();
  test_failures_leave_output_unchanged ();
  puts ("goodix_fpimage_pipeline: PASS");
  return 0;
}
