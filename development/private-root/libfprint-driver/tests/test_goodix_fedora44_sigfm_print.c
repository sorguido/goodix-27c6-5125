/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "fp-print-private.h"
#include "fpi-print.h"
#include "fpi-image-device.h"
#include "goodix_sigfm_metrics.h"
#include "support/sigfm_metric_test_double.h"

#include <gio/gio.h>
#include <string.h>

#define TEST_PIXELS 5120u

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

static GoodixSigfmSample *
new_sample (guint8 seed)
{
  guint8 pixels[TEST_PIXELS];
  GoodixSigfmSample *sample = NULL;
  gint keypoints = 0;

  for (gsize i = 0; i < G_N_ELEMENTS (pixels); i++)
    pixels[i] = (guint8) (seed + i);
  g_assert_cmpint (goodix_sigfm_extract_pixels (
                     pixels, sizeof pixels, &sample, &keypoints),
                   ==, GOODIX_SIGFM_OK);
  g_assert_nonnull (sample);
  g_assert_cmpint (keypoints, ==, 30);
  return sample;
}

static void
test_multi_sample_roundtrip_and_match (void)
{
  g_autoptr(FpPrint) template = new_sigfm_print ();
  g_autoptr(FpPrint) probe = new_sigfm_print ();
  g_autoptr(FpPrint) copy_source = new_sigfm_print ();
  g_autoptr(FpPrint) restored = NULL;
  GoodixSigfmSample *first = new_sample (1);
  GoodixSigfmSample *second = new_sample (2);
  GoodixSigfmSample *probe_sample = new_sample (3);
  g_autoptr(GError) error = NULL;
  g_autofree guchar *serialized = NULL;
  g_autofree guchar *reserialized = NULL;
  gsize serialized_size = 0;
  gsize reserialized_size = 0;

  g_assert_true (fpi_print_add_sigfm_sample (template, first, &error));
  g_assert_no_error (error);
  g_assert_true (fpi_print_add_sigfm_sample (copy_source, second, &error));
  g_assert_no_error (error);
  g_assert_true (fpi_print_add_print_checked (template, copy_source, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (template->prints->len, ==, 2);
  g_assert_true (fpi_print_add_sigfm_sample (probe, probe_sample, &error));
  g_assert_no_error (error);

  sigfm_test_set_score (42);
  g_assert_cmpint (fpi_print_sigfm_match (template, probe, 40, &error),
                   ==, FPI_MATCH_SUCCESS);
  g_assert_no_error (error);
  sigfm_test_set_score (39);
  g_assert_cmpint (fpi_print_sigfm_match (template, probe, 40, &error),
                   ==, FPI_MATCH_FAIL);
  g_assert_no_error (error);
  sigfm_test_set_score (-1);
  g_assert_cmpint (fpi_print_sigfm_match (template, probe, 40, &error),
                   ==, FPI_MATCH_ERROR);
  g_assert_error (error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_DATA_INVALID);
  g_clear_error (&error);
  sigfm_test_set_score (42);

  g_assert_true (fp_print_serialize (template, &serialized,
                                    &serialized_size, &error));
  g_assert_no_error (error);
  restored = fp_print_deserialize (serialized, serialized_size, &error);
  g_assert_no_error (error);
  g_assert_nonnull (restored);
  g_assert_cmpint (fpi_print_get_type (restored), ==, FPI_PRINT_SIGFM);
  g_assert_cmpuint (restored->prints->len, ==, 2);
  g_assert_true (fp_print_equal (template, restored));
  g_assert_true (fp_print_serialize (restored, &reserialized,
                                    &reserialized_size, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (serialized_size, ==, reserialized_size);
  g_assert_cmpmem (serialized, serialized_size,
                   reserialized, reserialized_size);

  goodix_sigfm_sample_free (first);
  goodix_sigfm_sample_free (second);
  goodix_sigfm_sample_free (probe_sample);
}

static void
test_checked_append_is_atomic_on_copy_failure (void)
{
  g_autoptr(FpPrint) template = new_sigfm_print ();
  g_autoptr(FpPrint) source = new_sigfm_print ();
  GoodixSigfmSample *sample = new_sample (6);
  g_autoptr(GError) error = NULL;

  g_assert_true (fpi_print_add_sigfm_sample (source, sample, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (template->prints->len, ==, 0);

  sigfm_test_set_mode (SIGFM_TEST_COPY_THROW);
  g_assert_false (fpi_print_add_print_checked (template, source, &error));
  g_assert_error (error, G_IO_ERROR, G_IO_ERROR_FAILED);
  g_assert_cmpuint (template->prints->len, ==, 0);
  sigfm_test_set_mode (SIGFM_TEST_OK);

  goodix_sigfm_sample_free (sample);
}

static void
test_enroll_stage_does_not_advance_on_copy_failure (void)
{
  g_autoptr(FpPrint) template = new_sigfm_print ();
  g_autoptr(FpPrint) source = new_sigfm_print ();
  GoodixSigfmSample *sample = new_sample (7);
  g_autoptr(GError) error = NULL;
  gint enroll_stage = 3;

  g_assert_true (fpi_print_add_sigfm_sample (source, sample, &error));
  g_assert_no_error (error);
  sigfm_test_set_mode (SIGFM_TEST_COPY_THROW);
  g_assert_false (fpi_image_device_add_enroll_sample_checked (
                    template, source, &enroll_stage, &error));
  g_assert_error (error, G_IO_ERROR, G_IO_ERROR_FAILED);
  g_assert_cmpint (enroll_stage, ==, 3);
  g_assert_cmpuint (template->prints->len, ==, 0);
  sigfm_test_set_mode (SIGFM_TEST_OK);
  goodix_sigfm_sample_free (sample);
}

static void
test_corrupt_payload_rejected (void)
{
  g_autoptr(FpPrint) print = new_sigfm_print ();
  GoodixSigfmSample *sample = new_sample (4);
  g_autoptr(GError) error = NULL;
  g_autofree guchar *serialized = NULL;
  gsize serialized_size = 0;
  gsize marker = 0;

  g_assert_true (fpi_print_add_sigfm_sample (print, sample, &error));
  g_assert_true (fp_print_serialize (print, &serialized,
                                    &serialized_size, &error));
  for (gsize i = 3; i + 24u <= serialized_size; i++)
    if (memcmp (&serialized[i], "GSF1", 4) == 0)
      {
        marker = i;
        break;
      }
  g_assert_cmpuint (marker, >, 0);
  serialized[marker + 20u] ^= 1u;
  g_assert_null (fp_print_deserialize (serialized, serialized_size, &error));
  g_assert_error (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA);
  g_clear_error (&error);
  g_assert_null (fp_print_deserialize (serialized, 3, &error));
  g_assert_error (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA);

  goodix_sigfm_sample_free (sample);
}

static void
test_sample_count_bounds (void)
{
  g_autoptr(FpPrint) empty = new_sigfm_print ();
  g_autoptr(FpPrint) oversized = new_sigfm_print ();
  GoodixSigfmSample *sample = new_sample (5);
  g_autoptr(GError) error = NULL;
  guchar *serialized = NULL;
  gsize serialized_size = 0;

  g_assert_false (fp_print_serialize (empty, &serialized,
                                     &serialized_size, &error));
  g_assert_error (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA);
  g_clear_error (&error);

  for (guint i = 0; i < GOODIX_SIGFM_MAX_PRINT_SAMPLES; i++)
    g_assert_true (fpi_print_add_sigfm_sample (oversized, sample, &error));
  g_assert_cmpuint (oversized->prints->len, ==,
                    GOODIX_SIGFM_MAX_PRINT_SAMPLES);
  g_assert_false (fpi_print_add_sigfm_sample (oversized, sample, &error));
  g_assert_error (error, G_IO_ERROR, G_IO_ERROR_NO_SPACE);
  g_assert_cmpuint (oversized->prints->len, ==,
                    GOODIX_SIGFM_MAX_PRINT_SAMPLES);
  g_clear_error (&error);
  g_assert_true (fp_print_serialize (oversized, &serialized,
                                    &serialized_size, &error));
  g_assert_no_error (error);
  g_clear_pointer (&serialized, g_free);

  goodix_sigfm_sample_free (sample);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  sigfm_test_set_mode (SIGFM_TEST_OK);
  sigfm_test_set_keypoints (30);
  g_test_add_func ("/goodix/sigfm-print/multi-sample-roundtrip-match",
                   test_multi_sample_roundtrip_and_match);
  g_test_add_func ("/goodix/sigfm-print/corrupt-payload-rejected",
                   test_corrupt_payload_rejected);
  g_test_add_func ("/goodix/sigfm-print/sample-count-bounds",
                   test_sample_count_bounds);
  g_test_add_func ("/goodix/sigfm-print/checked-append-atomic-failure",
                   test_checked_append_is_atomic_on_copy_failure);
  g_test_add_func ("/goodix/sigfm-print/enroll-stage-stable-on-copy-failure",
                   test_enroll_stage_does_not_advance_on_copy_failure);
  return g_test_run ();
}
