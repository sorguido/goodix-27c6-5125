/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "../goodix_capture_aggregation.h"
#include "../goodix_u16_to_fpimage.h"

#include <fpi-image.h>
#include <glib-object.h>

#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];

static void
fill (uint16_t value)
{
  size_t index;

  for (index = 0; index < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT; index++)
    samples[index] = value;
}

static void
test_multi_capture_aggregation (void)
{
  GoodixCaptureAggregator *agg = NULL;
  size_t index;

  assert (goodix_capture_aggregation_new (&agg, 2, 8) ==
          GOODIX_CAPTURE_AGGREGATION_OK);
  assert (agg != NULL);

  /* below min must fail-closed before finalize */
  assert (goodix_capture_aggregation_finalize (agg) ==
          GOODIX_CAPTURE_AGGREGATION_BELOW_MIN);

  for (index = 0; index < 3; index++)
    {
      fill ((uint16_t) (index * 1000u));
      assert (goodix_capture_aggregation_add (agg, samples,
                                               GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT) ==
              GOODIX_CAPTURE_AGGREGATION_OK);
    }

  assert (goodix_capture_aggregation_count (agg) == 3u);

  for (index = 0; index < 3; index++)
    {
      FpImage *image = goodix_capture_aggregation_get_image (agg, index);

      assert (FP_IS_IMAGE (image));
      assert (fp_image_get_width (image) == GOODIX_CANONICAL_IMAGE_WIDTH);
      assert (fp_image_get_height (image) == GOODIX_CANONICAL_IMAGE_HEIGHT);
      assert (image->flags == 0u);
      assert (image->ppmm == 0.0);
      assert (goodix_capture_aggregation_get_image_ppmm_state (agg, index) ==
              GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN);
    }

  /* out-of-range index is contained, not crash */
  assert (goodix_capture_aggregation_get_image (agg, 3) == NULL);
  assert (goodix_capture_aggregation_get_image_ppmm_state (agg, 3) ==
          GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN);

  assert (goodix_capture_aggregation_finalize (agg) ==
          GOODIX_CAPTURE_AGGREGATION_OK);

  goodix_capture_aggregation_free (agg);
}

static void
test_negative_paths (void)
{
  GoodixCaptureAggregator *agg = NULL;

  /* bad bounds */
  assert (goodix_capture_aggregation_new (&agg, 0, 8) ==
          GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT);
  assert (goodix_capture_aggregation_new (&agg, 5, 4) ==
          GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT);
  /* double-out */
  assert (goodix_capture_aggregation_new (&agg, 2, 8) ==
          GOODIX_CAPTURE_AGGREGATION_OK);
  assert (goodix_capture_aggregation_new (&agg, 2, 8) ==
          GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT);

  /* null/short inputs */
  assert (goodix_capture_aggregation_add (NULL, samples, 5120u) ==
          GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT);
  assert (goodix_capture_aggregation_add (agg, NULL, 5120u) ==
          GOODIX_CAPTURE_AGGREGATION_INVALID_ARGUMENT);
  assert (goodix_capture_aggregation_add (agg, samples, 5119u) ==
          GOODIX_CAPTURE_AGGREGATION_INVALID_SAMPLE_COUNT);

  fill (7u);
  assert (goodix_capture_aggregation_add (agg, samples, 5120u) ==
          GOODIX_CAPTURE_AGGREGATION_OK);

  /* exceeding max is fail-closed */
  {
    size_t extra = 0;

    while (goodix_capture_aggregation_add (agg, samples, 5120u) ==
           GOODIX_CAPTURE_AGGREGATION_OK)
      extra++;
    assert (extra == 7u); /* 1 already added + 7 = 8 == max */
    assert (goodix_capture_aggregation_add (agg, samples, 5120u) ==
            GOODIX_CAPTURE_AGGREGATION_OVER_MAX);
  }

  goodix_capture_aggregation_free (agg);
  goodix_capture_aggregation_free (NULL);
}

int
main (void)
{
  test_multi_capture_aggregation ();
  test_negative_paths ();
  puts ("goodix_capture_aggregation: PASS");
  return 0;
}
