/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Target-native Fedora 44/libfprint 1.94.100 SIGFM action test.
 *
 * This deliberately uses the host-only Goodix constructor.  It validates the
 * libfprint action/SIGFM mechanics with a deterministic structured raster;
 * it is not target biometric evidence.
 */
#include "../goodix_fpimage_device.h"
#include "../goodix_u16_to_fpimage.h"

#include "fp-device.h"
#include "fp-image-device-private.h"
#include "fp-print-private.h"
#include "fpi-device.h"
#include "fpi-print.h"

#include <glib.h>

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
  GError              *error;
  FpPrint             *enroll_print;
} SigfmFixture;

static gboolean
timeout_cb (gpointer user_data)
{
  SigfmFixture *fixture = user_data;

  fixture->timed_out = TRUE;
  g_main_loop_quit (fixture->loop);
  return G_SOURCE_REMOVE;
}

static void
wait_until (SigfmFixture *fixture,
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
wait_for_progress (SigfmFixture *fixture,
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
  SigfmFixture *fixture = user_data;

  (void) device;
  fixture->last_state = state;
}

static void
open_cb (FpDevice     *device,
         GAsyncResult *result,
         gpointer      user_data)
{
  SigfmFixture *fixture = user_data;

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
  SigfmFixture *fixture = user_data;

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
  SigfmFixture *fixture = user_data;

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
  SigfmFixture *fixture = user_data;
  (void) device;
  g_assert_no_error (error);
  g_assert_nonnull (print);
  g_assert_cmpint (fpi_print_get_type (print), ==, FPI_PRINT_SIGFM);
  g_assert_nonnull (print->prints);
  g_assert_cmpuint (print->prints->len, ==, 1u);
  g_assert_nonnull (g_ptr_array_index (print->prints, 0u));

  fixture->progress_count++;
  g_assert_cmpint (completed_stages, ==, (gint) fixture->progress_count);
}

static void
fill_structured_sigfm_samples (
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT])
{
  for (guint y = 0u; y < GOODIX_CANONICAL_IMAGE_HEIGHT; y++)
    for (guint x = 0u; x < GOODIX_CANONICAL_IMAGE_WIDTH; x++)
      {
        guint gx = x % 8u;
        guint gy = y % 8u;
        guint value = (gx < 4u && gy < 4u) ? 4095u : 0u;

        if (((x + y) & 1u) == 0u && value == 0u)
          value = 2048u;
        samples[y * GOODIX_CANONICAL_IMAGE_WIDTH + x] = (uint16_t) value;
      }
}

static void
test_true_sigfm_21_stage_action (void)
{
  uint16_t baseline[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  g_autoptr(FpPrint) template = NULL;
  SigfmFixture fixture = { 0 };

  fill_structured_sigfm_samples (samples);
  for (guint i = 0u; i < G_N_ELEMENTS (baseline); i++)
    baseline[i] = 2048u;
  fixture.loop = g_main_loop_new (NULL, FALSE);
  fixture.device = goodix_fpimage_device_new ();
  fixture.ctx = goodix_fpimage_device_get_context (fixture.device);
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
      goodix_device_context_emit_sigfm_image_ready (
        fixture.ctx, baseline, samples, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
      /* The sensor transcript completes its release tail and reports
       * finger-off while host-side minutiae extraction may still be running.
       * In particular, the final stage must be idle before libfprint starts
       * deactivation after the asynchronous SIGFM result. */
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
                   FPI_PRINT_SIGFM);
  g_assert_nonnull (fixture.enroll_print->prints);
  g_assert_cmpuint (fixture.enroll_print->prints->len, ==,
                    GOODIX_TARGET_LOCAL_ENROLL_STAGES);
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

  g_print ("D279_52_FEDORA44_NATIVE_SIGFM_ACTION=PASS\n");
  g_print ("D279_52_SIGFM_PROGRESS_COUNT=%u\n", fixture.progress_count);
  g_print ("D279_52_R2_PREPROCESSING_IN_ACTION=true\n");
  g_print ("D279_52_PRODUCTION_USB_REACHED=false\n");
  g_clear_object (&fixture.enroll_print);
  g_clear_error (&fixture.error);
  g_clear_object (&fixture.device);
  g_main_loop_unref (fixture.loop);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_assert_cmpint (argc, ==, 1);
  g_test_add_func ("/goodix/d279-52-fedora44-native-sigfm-action",
                   test_true_sigfm_21_stage_action);
  return g_test_run ();
}
