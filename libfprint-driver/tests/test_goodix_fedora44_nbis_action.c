/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Target-native Fedora 44/libfprint 1.94.100 NBIS action test.
 *
 * This deliberately uses the host-only Goodix constructor.  It validates the
 * libfprint action/NBIS mechanics with a public-domain NIST fixture reduced to
 * the target raster dimensions; it is not target biometric evidence.
 */
#include "../goodix_fpimage_device.h"
#include "../goodix_u16_to_fpimage.h"

#include "fp-device.h"
#include "fp-image-device-private.h"
#include "fp-print-private.h"
#include "fpi-device.h"
#include "fpi-print.h"

#include <cairo.h>
#include <glib.h>
#include <nbis.h>

#define HOST_ACTION_TIMEOUT_MS 15000u

typedef struct
{
  GMainLoop           *loop;
  GoodixFpImageDevice *device;
  GoodixDeviceContext *ctx;
  FpiImageDeviceState  last_state;
  gboolean             done;
  gboolean             timed_out;
  gboolean             success;
  guint                completion_count;
  guint                progress_count;
  guint                minimum_minutiae;
  GError              *error;
  FpPrint             *enroll_print;
} NbisFixture;

static gboolean
timeout_cb (gpointer user_data)
{
  NbisFixture *fixture = user_data;

  fixture->timed_out = TRUE;
  g_main_loop_quit (fixture->loop);
  return G_SOURCE_REMOVE;
}

static void
wait_until (NbisFixture *fixture,
            gboolean    *condition)
{
  guint timeout_id;

  if (*condition)
    return;

  fixture->timed_out = FALSE;
  /* This is only a host-test hang bound.  It says nothing about device-side
   * timeout or quiescence after an interrupted real transaction. */
  timeout_id = g_timeout_add (HOST_ACTION_TIMEOUT_MS, timeout_cb, fixture);
  while (!*condition && !fixture->timed_out)
    g_main_context_iteration (NULL, TRUE);
  if (!fixture->timed_out)
    g_source_remove (timeout_id);
  g_assert_false (fixture->timed_out);
}

static void
wait_for_progress (NbisFixture *fixture,
                   guint        expected_progress)
{
  guint timeout_id;

  if (fixture->progress_count >= expected_progress || fixture->done)
    return;

  fixture->timed_out = FALSE;
  /* As above, this bounds only the offline host test. */
  timeout_id = g_timeout_add (HOST_ACTION_TIMEOUT_MS, timeout_cb, fixture);
  while (fixture->progress_count < expected_progress && !fixture->done &&
         !fixture->timed_out)
    g_main_context_iteration (NULL, TRUE);
  if (!fixture->timed_out)
    g_source_remove (timeout_id);
  g_assert_false (fixture->timed_out);
}

static void
state_changed_cb (FpImageDevice      *device,
                  FpiImageDeviceState state,
                  gpointer            user_data)
{
  NbisFixture *fixture = user_data;

  (void) device;
  fixture->last_state = state;
}

static void
open_cb (FpDevice     *device,
         GAsyncResult *result,
         gpointer      user_data)
{
  NbisFixture *fixture = user_data;

  fixture->success = fp_device_open_finish (device, result, &fixture->error);
  fixture->completion_count++;
  fixture->done = TRUE;
  g_main_loop_quit (fixture->loop);
}

static void
close_cb (FpDevice     *device,
          GAsyncResult *result,
          gpointer      user_data)
{
  NbisFixture *fixture = user_data;

  fixture->success = fp_device_close_finish (device, result, &fixture->error);
  fixture->completion_count++;
  fixture->done = TRUE;
  g_main_loop_quit (fixture->loop);
}

static void
enroll_cb (FpDevice     *device,
           GAsyncResult *result,
           gpointer      user_data)
{
  NbisFixture *fixture = user_data;

  fixture->enroll_print = fp_device_enroll_finish (
    device, result, &fixture->error);
  fixture->success = fixture->error == NULL;
  fixture->completion_count++;
  fixture->done = TRUE;
  g_main_loop_quit (fixture->loop);
}

static void
progress_cb (FpDevice *device,
             gint      completed_stages,
             FpPrint  *print,
             gpointer  user_data,
             GError   *error)
{
  NbisFixture *fixture = user_data;
  struct xyt_struct *xyt;

  (void) device;
  g_assert_no_error (error);
  g_assert_nonnull (print);
  g_assert_cmpint (fpi_print_get_type (print), ==, FPI_PRINT_NBIS);
  g_assert_nonnull (print->prints);
  g_assert_cmpuint (print->prints->len, ==, 1u);
  xyt = g_ptr_array_index (print->prints, 0u);
  g_assert_nonnull (xyt);
  g_assert_cmpint (xyt->nrows, >, 0);

  fixture->progress_count++;
  fixture->minimum_minutiae = MIN (fixture->minimum_minutiae,
                                   (guint) xyt->nrows);
  g_assert_cmpint (completed_stages, ==, (gint) fixture->progress_count);
}

static void
load_nist_fixture (const gchar *path,
                   uint16_t     samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT])
{
  cairo_surface_t *source;
  cairo_surface_t *target;
  cairo_t *cr;
  cairo_status_t status;
  const guint8 *data;
  gint source_width;
  gint source_height;
  gint stride;

  source = cairo_image_surface_create_from_png (path);
  status = cairo_surface_status (source);
  g_assert_cmpint (status, ==, CAIRO_STATUS_SUCCESS);
  source_width = cairo_image_surface_get_width (source);
  source_height = cairo_image_surface_get_height (source);

  target = cairo_image_surface_create (
    CAIRO_FORMAT_A8, (gint) GOODIX_CANONICAL_IMAGE_WIDTH,
    (gint) GOODIX_CANONICAL_IMAGE_HEIGHT);
  g_assert_cmpint (cairo_surface_status (target), ==, CAIRO_STATUS_SUCCESS);
  cr = cairo_create (target);
  cairo_set_operator (cr, CAIRO_OPERATOR_SOURCE);
  cairo_scale (cr,
               (double) GOODIX_CANONICAL_IMAGE_WIDTH / source_width,
               (double) GOODIX_CANONICAL_IMAGE_HEIGHT / source_height);
  cairo_set_source_surface (cr, source, 0.0, 0.0);
  cairo_pattern_set_filter (cairo_get_source (cr), CAIRO_FILTER_BILINEAR);
  cairo_paint (cr);
  g_assert_cmpint (cairo_status (cr), ==, CAIRO_STATUS_SUCCESS);
  cairo_destroy (cr);
  cairo_surface_flush (target);

  data = cairo_image_surface_get_data (target);
  stride = cairo_image_surface_get_stride (target);
  for (guint y = 0u; y < GOODIX_CANONICAL_IMAGE_HEIGHT; y++)
    for (guint x = 0u; x < GOODIX_CANONICAL_IMAGE_WIDTH; x++)
      {
        guint8 pixel = data[y * (guint) stride + x];

        samples[y * GOODIX_CANONICAL_IMAGE_WIDTH + x] =
          (uint16_t) (((guint) pixel * GOODIX_SENSOR_SAMPLE_MAX + 127u) /
                      255u);
      }

  cairo_surface_destroy (target);
  cairo_surface_destroy (source);
}

static void
test_true_nbis_21_stage_action (gconstpointer user_data)
{
  const gchar *fixture_path = user_data;
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  g_autoptr(FpPrint) template = NULL;
  NbisFixture fixture = { 0 };

  load_nist_fixture (fixture_path, samples);
  fixture.loop = g_main_loop_new (NULL, FALSE);
  fixture.device = goodix_fpimage_device_new ();
  fixture.ctx = goodix_fpimage_device_get_context (fixture.device);
  fixture.minimum_minutiae = G_MAXUINT;
  g_assert_cmpint (FP_DEVICE_GET_CLASS (fixture.device)->type, ==,
                   FP_DEVICE_TYPE_VIRTUAL);
  g_assert_cmpstr (fp_device_get_driver (FP_DEVICE (fixture.device)), ==,
                   "goodix_27c6_5125_host_only");
  g_signal_connect (fixture.device, "fpi-image-device-state-changed",
                    G_CALLBACK (state_changed_cb), &fixture);

  fp_device_open (FP_DEVICE (fixture.device), NULL,
                  (GAsyncReadyCallback) open_cb, &fixture);
  wait_until (&fixture, &fixture.done);
  g_assert_no_error (fixture.error);
  g_assert_true (fixture.success);
  g_assert_cmpuint (fixture.completion_count, ==, 1u);
  g_assert_cmpint (goodix_device_context_get_state (fixture.ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);

  fixture.done = FALSE;
  fixture.success = FALSE;
  fixture.completion_count = 0u;
  template = fp_print_new (FP_DEVICE (fixture.device));
  fp_device_enroll (FP_DEVICE (fixture.device),
                    g_steal_pointer (&template), NULL,
                    progress_cb, &fixture, NULL,
                    (GAsyncReadyCallback) enroll_cb, &fixture);
  g_assert_cmpint (goodix_device_context_get_state (fixture.ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING);
  goodix_device_context_emit_arm_complete (fixture.ctx, NULL);
  g_assert_cmpint (fixture.last_state, ==,
                   FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);

  for (guint stage = 1u; stage <= GOODIX_TARGET_LOCAL_ENROLL_STAGES; stage++)
    {
      guint expected_progress = stage;

      goodix_device_context_emit_finger_down (fixture.ctx);
      g_assert_cmpint (fixture.last_state, ==,
                       FPI_IMAGE_DEVICE_STATE_CAPTURE);
      goodix_device_context_emit_image_ready (
        fixture.ctx, samples, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
      /* The sensor transcript completes its release tail and reports
       * finger-off while host-side minutiae extraction may still be running.
       * In particular, the final stage must be idle before libfprint starts
       * deactivation after the asynchronous NBIS result. */
      goodix_device_context_set_fresh_down_table (fixture.ctx, TRUE);
      goodix_device_context_emit_release_tail_complete (fixture.ctx);
      goodix_device_context_emit_finger_up_ready (fixture.ctx);
      wait_for_progress (&fixture, expected_progress);
      g_assert_false (fixture.done && fixture.progress_count < expected_progress);
      g_assert_cmpuint (fixture.progress_count, ==, expected_progress);

      if (stage < GOODIX_TARGET_LOCAL_ENROLL_STAGES)
        {
          g_assert_cmpint (fixture.last_state, ==,
                           FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);
        }
    }

  wait_until (&fixture, &fixture.done);
  g_assert_no_error (fixture.error);
  g_assert_true (fixture.success);
  g_assert_cmpuint (fixture.completion_count, ==, 1u);
  g_assert_nonnull (fixture.enroll_print);
  g_assert_cmpint (fpi_print_get_type (fixture.enroll_print), ==,
                   FPI_PRINT_NBIS);
  g_assert_nonnull (fixture.enroll_print->prints);
  g_assert_cmpuint (fixture.enroll_print->prints->len, ==,
                    GOODIX_TARGET_LOCAL_ENROLL_STAGES);
  g_assert_cmpuint (fixture.minimum_minutiae, >, 0u);
  g_assert_cmpint (goodix_device_context_get_state (fixture.ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);

  fixture.done = FALSE;
  fixture.success = FALSE;
  fixture.completion_count = 0u;
  fp_device_close (FP_DEVICE (fixture.device), NULL,
                   (GAsyncReadyCallback) close_cb, &fixture);
  wait_until (&fixture, &fixture.done);
  g_assert_no_error (fixture.error);
  g_assert_true (fixture.success);
  g_assert_cmpuint (fixture.completion_count, ==, 1u);

  g_print ("D279_27_FEDORA44_NATIVE_NBIS_ACTION=PASS\n");
  g_print ("D279_27_NBIS_PROGRESS_COUNT=%u\n", fixture.progress_count);
  g_print ("D279_27_NBIS_MIN_MINUTIAE=%u\n", fixture.minimum_minutiae);
  g_print ("D279_27_PRODUCTION_USB_REACHED=false\n");
  g_clear_object (&fixture.enroll_print);
  g_clear_error (&fixture.error);
  g_clear_object (&fixture.device);
  g_main_loop_unref (fixture.loop);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_assert_cmpint (argc, ==, 2);
  g_test_add_data_func ("/goodix/d279-27-fedora44-native-nbis-action",
                        argv[1], test_true_nbis_21_stage_action);
  return g_test_run ();
}
