/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "fp-print-private.h"
#include "fpi-print.h"
#include "goodix_sigfm_metrics.h"
#include "goodix_sigfm_preprocess.h"

#include <gio/gio.h>
#include <string.h>

#define TEST_WIDTH 80u
#define TEST_HEIGHT 64u
#define TEST_PIXELS (TEST_WIDTH * TEST_HEIGHT)

static void
fill_structured_raster (guint8 pixels[TEST_PIXELS])
{
  for (guint y = 0; y < TEST_HEIGHT; y++)
    for (guint x = 0; x < TEST_WIDTH; x++)
      {
        guint gx = x % 8u;
        guint gy = y % 8u;
        guint value = (gx < 4u && gy < 4u) ? 255u : 0u;

        if (((x + y) & 1u) == 0u && value == 0u)
          value = 128u;
        pixels[y * TEST_WIDTH + x] = (guint8) value;
      }
}

static FpPrint *
new_sigfm_print (void)
{
  FpPrint *print = g_object_new (FP_TYPE_PRINT,
                                 "driver", "goodix_27c6_5125",
                                 "device-id", "27c6:5125",
                                 NULL);

  g_object_ref_sink (print);
  fpi_print_set_type (print, FPI_PRINT_SIGFM);
  return print;
}

static void
fill_d291_rasters (guint16 baseline[TEST_PIXELS],
                   guint16 enrolled[TEST_PIXELS],
                   guint16 wrong[TEST_PIXELS])
{
  for (guint y = 0; y < TEST_HEIGHT; y++)
    for (guint x = 0; x < TEST_WIDTH; x++)
      {
        gsize i = (gsize) y * TEST_WIDTH + x;
        guint base = 900u + (x % 5u);
        guint enrolled_value =
          ((x % 8u) < 4u && (y % 8u) < 4u) ? 255u :
          (((x + y) & 1u) == 0u ? 128u : 0u);
        guint wrong_value =
          (((x / 5u) + (y / 7u)) % 3u == 0u) ? 255u :
          (((2u * x + 3u * y) % 11u) < 3u ? 96u : 0u);

        baseline[i] = (guint16) base;
        enrolled[i] = (guint16) (base + 6u * enrolled_value);
        wrong[i] = (guint16) (base + 6u * wrong_value);
      }
}

static void
test_d291_real_biometric_continuity (void)
{
  guint16 baseline[TEST_PIXELS];
  guint16 enrolled_raster[TEST_PIXELS];
  guint16 wrong_raster[TEST_PIXELS];
  guint8 enrolled_pixels[TEST_PIXELS];
  guint8 wrong_pixels[TEST_PIXELS];
  g_autoptr(FpPrint) template = new_sigfm_print ();
  g_autoptr(FpPrint) enrolled_probe = new_sigfm_print ();
  g_autoptr(FpPrint) wrong_probe = new_sigfm_print ();
  g_autofree guchar *before = NULL;
  g_autofree guchar *after = NULL;
  gsize before_size = 0;
  gsize after_size = 0;
  gint enrolled_keypoints = 0;
  gint wrong_keypoints = 0;
  g_autoptr(GError) error = NULL;

  fill_d291_rasters (baseline, enrolled_raster, wrong_raster);
  g_assert_cmpint (goodix_sigfm_preprocess_r2 (
                     baseline, TEST_PIXELS, enrolled_raster, TEST_PIXELS,
                     enrolled_pixels, sizeof enrolled_pixels), ==,
                   GOODIX_SIGFM_PREPROCESS_OK);
  g_assert_cmpint (goodix_sigfm_preprocess_r2 (
                     baseline, TEST_PIXELS, wrong_raster, TEST_PIXELS,
                     wrong_pixels, sizeof wrong_pixels), ==,
                   GOODIX_SIGFM_PREPROCESS_OK);

  for (guint i = 0; i < 8u; i++)
    {
      GoodixSigfmSample *sample = NULL;

      g_assert_cmpint (goodix_sigfm_extract_pixels (
                         enrolled_pixels, sizeof enrolled_pixels, &sample,
                         &enrolled_keypoints), ==, GOODIX_SIGFM_OK);
      g_assert_cmpint (enrolled_keypoints, >=, GOODIX_SIGFM_MIN_KEYPOINTS);
      g_assert_true (fpi_print_add_sigfm_sample (template, sample, &error));
      g_assert_no_error (error);
      goodix_sigfm_sample_free (sample);
    }
  {
    GoodixSigfmSample *sample = NULL;

    g_assert_cmpint (goodix_sigfm_extract_pixels (
                       wrong_pixels, sizeof wrong_pixels, &sample,
                       &wrong_keypoints), ==, GOODIX_SIGFM_OK);
    g_assert_cmpint (wrong_keypoints, >=, GOODIX_SIGFM_MIN_KEYPOINTS);
    g_assert_true (fpi_print_add_sigfm_sample (wrong_probe, sample, &error));
    g_assert_no_error (error);
    goodix_sigfm_sample_free (sample);
  }
  {
    GoodixSigfmSample *sample = NULL;

    g_assert_cmpint (goodix_sigfm_extract_pixels (
                       enrolled_pixels, sizeof enrolled_pixels, &sample,
                       &enrolled_keypoints), ==, GOODIX_SIGFM_OK);
    g_assert_true (fpi_print_add_sigfm_sample (enrolled_probe, sample,
                                               &error));
    g_assert_no_error (error);
    goodix_sigfm_sample_free (sample);
  }

  g_assert_true (fp_print_serialize (template, &before, &before_size, &error));
  g_assert_no_error (error);
  g_assert_cmpint (fpi_print_sigfm_match (template, wrong_probe, 40, &error),
                   ==, FPI_MATCH_FAIL);
  g_assert_no_error (error);
  g_assert_cmpint (fpi_print_sigfm_match (template, enrolled_probe, 40,
                                         &error), ==, FPI_MATCH_SUCCESS);
  g_assert_no_error (error);
  g_assert_true (fp_print_serialize (template, &after, &after_size, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (before_size, ==, after_size);
  g_assert_cmpmem (before, before_size, after, after_size);

  g_print ("D291_REAL_SIGFM_TEMPLATE_SAMPLES=8\n");
  g_print ("D291_REAL_SIGFM_CANONICAL_DIMENSIONS=80x64_U8\n");
  g_print ("D291_REAL_SIGFM_WRONG_THEN_ENROLLED=NO_MATCH_THEN_MATCH\n");
  g_print ("D291_REAL_SIGFM_TEMPLATE_IDENTITY_ACROSS_MATCH=PASS\n");
}

int
main (void)
{
  guint8 pixels[TEST_PIXELS];
  GoodixSigfmSample *first = NULL;
  GoodixSigfmSample *second = NULL;
  GoodixSigfmSample *probe_sample = NULL;
  gint first_keypoints = 0;
  gint second_keypoints = 0;
  gint probe_keypoints = 0;
  g_autoptr(FpPrint) template = new_sigfm_print ();
  g_autoptr(FpPrint) probe = new_sigfm_print ();
  g_autoptr(FpPrint) restored = NULL;
  g_autoptr(GError) error = NULL;
  g_autofree guchar *serialized = NULL;
  g_autofree guchar *reserialized = NULL;
  gsize serialized_size = 0;
  gsize reserialized_size = 0;
  gsize marker = 0;

  fill_structured_raster (pixels);
  test_d291_real_biometric_continuity ();
  g_assert_cmpint (goodix_sigfm_extract_pixels (
                     pixels, sizeof pixels, &first, &first_keypoints),
                   ==, GOODIX_SIGFM_OK);
  g_assert_cmpint (goodix_sigfm_extract_pixels (
                     pixels, sizeof pixels, &second, &second_keypoints),
                   ==, GOODIX_SIGFM_OK);
  g_assert_cmpint (goodix_sigfm_extract_pixels (
                     pixels, sizeof pixels, &probe_sample, &probe_keypoints),
                   ==, GOODIX_SIGFM_OK);
  g_assert_cmpint (first_keypoints, ==, second_keypoints);
  g_assert_cmpint (first_keypoints, ==, probe_keypoints);

  g_assert_true (fpi_print_add_sigfm_sample (template, first, &error));
  g_assert_true (fpi_print_add_sigfm_sample (template, second, &error));
  g_assert_true (fpi_print_add_sigfm_sample (probe, probe_sample, &error));
  g_assert_no_error (error);
  g_assert_cmpint (fpi_print_sigfm_match (template, probe, 1, &error),
                   ==, FPI_MATCH_SUCCESS);
  g_assert_no_error (error);

  g_assert_true (fp_print_serialize (template, &serialized,
                                    &serialized_size, &error));
  restored = fp_print_deserialize (serialized, serialized_size, &error);
  g_assert_no_error (error);
  g_assert_nonnull (restored);
  g_assert_true (fp_print_equal (template, restored));
  g_assert_cmpint (fpi_print_sigfm_match (restored, probe, 1, &error),
                   ==, FPI_MATCH_SUCCESS);
  g_assert_true (fp_print_serialize (restored, &reserialized,
                                    &reserialized_size, &error));
  g_assert_cmpuint (serialized_size, ==, reserialized_size);
  g_assert_cmpmem (serialized, serialized_size,
                   reserialized, reserialized_size);

  for (gsize i = 3; i + 24u <= serialized_size; i++)
    if (memcmp (&serialized[i], "GSF1", 4) == 0)
      {
        marker = i;
        break;
      }
  g_assert_cmpuint (marker, >, 0);
  serialized[marker + 20u] ^= 1u;
  g_clear_object (&restored);
  restored = fp_print_deserialize (serialized, serialized_size, &error);
  g_assert_null (restored);
  g_assert_error (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA);

  g_print ("D279_51_REAL_SIGFM_KEYPOINTS=%d\n", first_keypoints);
  g_print ("D279_51_REAL_SIGFM_FP3_MATCH_ROUNDTRIP=PASS\n");
  goodix_sigfm_sample_free (first);
  goodix_sigfm_sample_free (second);
  goodix_sigfm_sample_free (probe_sample);
  return 0;
}
