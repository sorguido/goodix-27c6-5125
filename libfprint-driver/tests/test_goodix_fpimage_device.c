/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Host-only deterministic tests for the Goodix FpImageDevice shell.
 *
 * These tests exercise the real repository-local libfprint 1.94.5 FpImageDevice
 * state machine through public async actions, with an in-memory fake backend.
 */
#include "../goodix_fpimage_device.h"
#include "../goodix_fpi_usb_backend.h"
#include "../goodix_usb_router.h"
#include "../goodix_u16_to_fpimage.h"

#include "test_sigfm_control.h"

#include "fpi-image-device.h"
#include "fp-device.h"
#include "fp-image-device.h"
#include "fp-print.h"

#include <glib.h>

#define TEST_TIMEOUT_MS 5000

void  goodix_test_gusb_reset_counts (void);
guint goodix_test_gusb_get_open_count (void);
guint goodix_test_gusb_get_close_count (void);

typedef struct
{
  GMainLoop            *loop;
  GoodixFpImageDevice  *device;
  GoodixDeviceContext  *ctx;
  FpiImageDeviceState   last_state;

  gboolean              done;
  gboolean              timed_out;
  guint                 completion_count;
  gboolean              success;
  GError               *error;
  FpImage              *capture_image;
  FpPrint              *enroll_print;
  guint                 enroll_progress_count;
} TestFixture;

static void
host_only_usb_submit (GoodixFpiUsbBackend *backend,
                      GoodixUsbDirection   direction,
                      guint64              generation,
                      GBytes              *bytes,
                      gpointer             user_data)
{
  (void) backend;
  (void) direction;
  (void) generation;
  (void) bytes;
  (void) user_data;
}

static void
state_changed_cb (FpImageDevice      *dev,
                  FpiImageDeviceState  state,
                  gpointer             user_data)
{
  TestFixture *f = user_data;

  (void) dev;
  f->last_state = state;
}

static TestFixture *
test_fixture_new (void)
{
  TestFixture *f;

  f = g_new0 (TestFixture, 1);
  f->loop = g_main_loop_new (NULL, FALSE);
  f->device = goodix_fpimage_device_new ();
  f->ctx = goodix_fpimage_device_get_context (f->device);
  g_signal_connect (f->device, "fpi-image-device-state-changed",
                    G_CALLBACK (state_changed_cb), f);

  return f;
}

static void
test_fixture_free (TestFixture *f)
{
  if (f == NULL)
    return;

  g_print ("DEBUG fixture_free capture_image=%p device=%p loop=%p\n",
           f->capture_image, f->device, f->loop);
  g_clear_object (&f->capture_image);
  g_clear_object (&f->enroll_print);
  g_clear_error (&f->error);
  g_clear_object (&f->device);
  if (f->loop)
    g_main_loop_unref (f->loop);
  g_free (f);
}

static gboolean
test_timeout_cb (gpointer user_data)
{
  TestFixture *f = user_data;

  f->done = TRUE;
  f->timed_out = TRUE;
  f->success = FALSE;
  g_main_loop_quit (f->loop);
  return G_SOURCE_REMOVE;
}

static void
test_wait (TestFixture *f)
{
  guint timeout_id;

  if (f->done)
    return;
  f->timed_out = FALSE;
  timeout_id = g_timeout_add (TEST_TIMEOUT_MS, test_timeout_cb, f);
  g_main_loop_run (f->loop);
  if (!f->timed_out)
    g_source_remove (timeout_id);
  g_assert_false (f->timed_out);
}

static void
test_complete (TestFixture *f)
{
  f->done = TRUE;
  f->completion_count++;
  g_main_loop_quit (f->loop);
}

static void
open_cb (FpDevice *device, GAsyncResult *res, gpointer user_data)
{
  TestFixture *f = user_data;

  f->success = fp_device_open_finish (device, res, &f->error);
  test_complete (f);
}

static void
close_cb (FpDevice *device, GAsyncResult *res, gpointer user_data)
{
  TestFixture *f = user_data;

  f->success = fp_device_close_finish (device, res, &f->error);
  test_complete (f);
}

static void
capture_cb (FpDevice *device, GAsyncResult *res, gpointer user_data)
{
  TestFixture *f = user_data;

  f->capture_image = fp_device_capture_finish (device, res, &f->error);
  g_print ("DEBUG capture_cb image=%p error=%p\n", f->capture_image, f->error);
  f->success = (f->error == NULL);
  test_complete (f);
}

static void
enroll_cb (FpDevice *device, GAsyncResult *res, gpointer user_data)
{
  TestFixture *f = user_data;

  f->enroll_print = fp_device_enroll_finish (device, res, &f->error);
  f->success = (f->error == NULL);
  test_complete (f);
}

static void
progress_cb (FpDevice     *device,
             gint          completed_stages,
             FpPrint      *print,
             gpointer      user_data,
             GError       *error)
{
  TestFixture *f = user_data;

  (void) device;
  (void) completed_stages;
  (void) print;
  (void) error;

  f->enroll_progress_count++;
}

static void
fixture_open (TestFixture *f)
{
  f->done = FALSE;
  f->completion_count = 0;
  fp_device_open (FP_DEVICE (f->device), NULL, (GAsyncReadyCallback) open_cb, f);
  test_wait (f);
  g_assert_true (f->success);
  g_assert_cmpuint (f->completion_count, ==, 1);
  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
  f->completion_count = 0;
}

static void
fixture_close (TestFixture *f)
{
  f->done = FALSE;
  f->completion_count = 0;
  fp_device_close (FP_DEVICE (f->device), NULL, (GAsyncReadyCallback) close_cb, f);
  test_wait (f);
  g_assert_true (f->success);
}

static void
fill_gradient_samples (uint16_t *samples)
{
  size_t i;

  for (i = 0; i < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT; i++)
    samples[i] = (uint16_t) (i % (GOODIX_SENSOR_SAMPLE_MAX + 1));
}

/* -------------------------------------------------------------
 * 7.1 Base lifecycle (capture)
 * ------------------------------------------------------------- */
static void
test_lifecycle_base_capture (void)
{
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  TestFixture *f = test_fixture_new ();

  fixture_open (f);

  fill_gradient_samples (samples);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);

  /* Activate -> fake arm -> activate complete -> AWAIT_FINGER_ON. */
  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING);
  g_assert_cmpuint (goodix_in_memory_backend_get_arm_count (f->ctx), ==, 1);

  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_ACTIVE);
  g_assert_cmpint (f->last_state, ==, FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);

  goodix_device_context_emit_finger_down (f->ctx);
  g_assert_cmpint (f->last_state, ==, FPI_IMAGE_DEVICE_STATE_CAPTURE);

  goodix_device_context_emit_image_ready (f->ctx, samples,
                                          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
  g_assert_cmpint (f->last_state, ==, FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_OFF);

  goodix_device_context_emit_release_tail_complete (f->ctx);
  g_assert_true (goodix_device_context_get_release_tail_complete (f->ctx));

  goodix_device_context_emit_finger_up_ready (f->ctx);

  test_wait (f);
  g_assert_true (f->success);
  g_assert_cmpuint (f->completion_count, ==, 1);
  g_assert_nonnull (f->capture_image);
  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);

  fixture_close (f);
  test_fixture_free (f);
}

/* -------------------------------------------------------------
 * 7.2 Reentrancy: NON_ENROLL_FINGER_OFF_SYNCHRONOUS_DEACTIVATE
 * ------------------------------------------------------------- */
static void
test_non_enroll_finger_off_synchronous_deactivate (void)
{
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  TestFixture *f = test_fixture_new ();
  guint commands_before_deactivate;

  fixture_open (f);

  fill_gradient_samples (samples);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  goodix_device_context_emit_finger_down (f->ctx);
  goodix_device_context_emit_image_ready (f->ctx, samples,
                                          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);

  commands_before_deactivate =
    goodix_device_context_get_backend_command_count (f->ctx);

  goodix_device_context_emit_release_tail_complete (f->ctx);
  goodix_device_context_emit_finger_up_ready (f->ctx);

  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
  g_assert_true (goodix_device_context_get_terminal_fence (f->ctx));

  test_wait (f);

  /* No new fake backend command after the finger-off report. */
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_before_deactivate + 1 /* disarm */);
  g_assert_cmpstr (goodix_in_memory_backend_get_last_command (f->ctx), ==,
                   "disarm");

  fixture_close (f);
  test_fixture_free (f);
}

/* -------------------------------------------------------------
 * 7.2 Reentrancy helpers for enrollment ordering
 * ------------------------------------------------------------- */
static void
run_enroll_cycle (TestFixture *f,
                  gboolean     block_minutiae,
                  gboolean     minutiae_done_before_finger_off)
{
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(FpPrint) template = fp_print_new (FP_DEVICE (f->device));
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];

  fill_gradient_samples (samples);

  f->enroll_progress_count = 0;
  goodix_test_sigfm_extract_set_block (block_minutiae);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_enroll (FP_DEVICE (f->device), g_steal_pointer (&template), cancellable,
                    progress_cb, f, NULL,
                    (GAsyncReadyCallback) enroll_cb, f);

  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  goodix_device_context_emit_finger_down (f->ctx);
  goodix_device_context_emit_image_ready (f->ctx, samples,
                                          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);

  if (minutiae_done_before_finger_off)
    {
      /* Wait for the host-only SIGFM double to report minutiae completion. */
      while (f->enroll_progress_count == 0)
        g_main_context_iteration (NULL, TRUE);
    }

  goodix_device_context_set_fresh_down_table (f->ctx, TRUE);
  goodix_device_context_emit_release_tail_complete (f->ctx);
  goodix_device_context_emit_finger_up_ready (f->ctx);

  if (block_minutiae)
    {
      gint64 deadline = g_get_monotonic_time () + TEST_TIMEOUT_MS * 1000;

      while (!goodix_test_sigfm_extract_is_blocked () &&
             g_get_monotonic_time () < deadline)
        g_main_context_iteration (NULL, FALSE);
      g_assert_true (goodix_test_sigfm_extract_is_blocked ());
      /* With minutiae still pending, re-arm must not happen yet. */
      g_assert_cmpuint (goodix_in_memory_backend_get_rearm_count (f->ctx), ==, 0);
      goodix_test_sigfm_extract_unblock ();
      /* Drain the GTask completion for minutiae extraction. */
      while (f->last_state != FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON)
        g_main_context_iteration (NULL, TRUE);
    }

  g_assert_cmpuint (goodix_in_memory_backend_get_rearm_count (f->ctx), ==, 1);

  /* Duplicate gate notifications in the same generation are idempotent. */
  goodix_device_context_set_fresh_down_table (f->ctx, TRUE);
  goodix_device_context_emit_release_tail_complete (f->ctx);
  g_assert_cmpuint (goodix_in_memory_backend_get_rearm_count (f->ctx), ==, 1);

  /* Cancel before the full five-stage enrollment proceeds further. */
  g_cancellable_cancel (cancellable);
  test_wait (f);
  g_assert_false (f->success);
}

static void
test_enroll_minutiae_done_before_finger_off (void)
{
  TestFixture *f = test_fixture_new ();

  fixture_open (f);
  run_enroll_cycle (f, FALSE, TRUE);
  fixture_close (f);
  test_fixture_free (f);
}

static void
test_enroll_finger_off_before_minutiae_done (void)
{
  TestFixture *f = test_fixture_new ();

  fixture_open (f);
  run_enroll_cycle (f, TRUE, FALSE);
  fixture_close (f);
  test_fixture_free (f);
}

static void
test_no_rearm_before_both_gates (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(FpPrint) template = fp_print_new (FP_DEVICE (f->device));
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];

  fixture_open (f);
  fill_gradient_samples (samples);

  f->done = FALSE;
  f->completion_count = 0;
  f->enroll_progress_count = 0;
  fp_device_enroll (FP_DEVICE (f->device), g_steal_pointer (&template), cancellable,
                    progress_cb, f, NULL,
                    (GAsyncReadyCallback) enroll_cb, f);

  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  goodix_device_context_emit_finger_down (f->ctx);
  goodix_device_context_emit_image_ready (f->ctx, samples,
                                          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);

  /* Release tail completes, but fresh down-table is intentionally false. */
  goodix_device_context_set_fresh_down_table (f->ctx, FALSE);
  goodix_device_context_emit_release_tail_complete (f->ctx);
  goodix_device_context_emit_finger_up_ready (f->ctx);

  g_assert_cmpuint (goodix_in_memory_backend_get_rearm_count (f->ctx), ==, 0);

  g_cancellable_cancel (cancellable);
  test_wait (f);
  g_assert_false (f->success);

  fixture_close (f);
  test_fixture_free (f);
}

static void
test_no_command_after_deactivate_fence (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  guint commands_before;

  fixture_open (f);
  fill_gradient_samples (samples);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  goodix_device_context_emit_finger_down (f->ctx);
  goodix_device_context_emit_image_ready (f->ctx, samples,
                                          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);

  commands_before = goodix_device_context_get_backend_command_count (f->ctx);

  /* Cancel the action: this raises the terminal fence and deactivates. */
  g_cancellable_cancel (cancellable);

  /* Spin until the deactivate fence is observable. */
  while (!goodix_device_context_get_terminal_fence (f->ctx))
    g_main_context_iteration (NULL, TRUE);

  /* Old-generation events after the fence must be ignored. */
  goodix_device_context_emit_finger_down (f->ctx);
  goodix_device_context_emit_image_ready (f->ctx, samples,
                                          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);

  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_before + 1 /* disarm */);

  test_wait (f);
  g_assert_false (f->success);

  fixture_close (f);
  test_fixture_free (f);
}

/* -------------------------------------------------------------
 * 7.3 Cancellation per state
 * ------------------------------------------------------------- */
static void
test_cancellation_opening (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_open (FP_DEVICE (f->device), cancellable,
                  (GAsyncReadyCallback) open_cb, f);
  g_cancellable_cancel (cancellable);

  test_wait (f);
  g_assert_false (f->success);
  g_assert_error (f->error, G_IO_ERROR, G_IO_ERROR_CANCELLED);
  g_assert_cmpuint (f->completion_count, ==, 1);

  test_fixture_free (f);
}

static void
test_cancellation_activating (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GCancellable) second_cancellable = g_cancellable_new ();
  guint64 poisoned_generation;
  GLogLevelFlags old_fatal;
  guint commands_before;
  guint64 real_submits_before;
  guint64 out_submits_before;
  GoodixFpiUsbBackend *usb_backend;

  fixture_open (f);
  usb_backend = goodix_device_context_get_fpi_usb_backend (f->ctx);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING);
  /* The backend arm is reached before the cancellable can fire; the remaining
   * open epoch is therefore non-quiescent and must become sticky poisoned. */
  g_assert_cmpuint (goodix_in_memory_backend_get_arm_count (f->ctx), ==, 1);
  poisoned_generation = goodix_device_context_get_generation (f->ctx);
  g_assert_cmpuint (poisoned_generation, >, 0);

  g_cancellable_cancel (cancellable);

  test_wait (f);
  g_assert_false (f->success);
  g_assert_error (f->error, G_IO_ERROR, G_IO_ERROR_CANCELLED);
  g_assert_cmpuint (f->completion_count, ==, 1);
  g_assert_true (goodix_device_context_get_terminal_fence (f->ctx));
  g_assert_true (goodix_device_context_get_poisoned (f->ctx));
  g_assert_cmpuint (goodix_device_context_get_generation (f->ctx), ==, 0);

  commands_before = goodix_device_context_get_backend_command_count (f->ctx);
  real_submits_before = goodix_fpi_usb_backend_get_real_submit_count (usb_backend);
  out_submits_before = goodix_fpi_usb_backend_get_out_submit_count (usb_backend);

  /* A second capture request in the same open epoch must be rejected by the
   * sticky poison gate without creating a new generation, backend command or
   * USB submit.  libfprint leaves FpImageDevice in ACTIVATING after
   * activate_complete(error), which would normally be a host-side warning; the
   * only assertion of interest here is that the driver stays poisoned and does
   * not reach the backend or USB. */
  g_clear_error (&f->error);
  f->done = FALSE;
  f->completion_count = 0;
  f->success = FALSE;
  old_fatal = g_log_set_always_fatal (0);
  fp_device_capture (FP_DEVICE (f->device), TRUE, second_cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  g_log_set_always_fatal (old_fatal);
  test_wait (f);

  g_assert_false (f->success);
  g_assert_error (f->error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_PROTO);
  g_assert_true (goodix_device_context_get_poisoned (f->ctx));
  g_assert_true (goodix_device_context_get_terminal_fence (f->ctx));
  g_assert_cmpuint (goodix_device_context_get_generation (f->ctx), ==, 0);
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_before);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (usb_backend),
                    ==, real_submits_before);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_submit_count (usb_backend),
                    ==, out_submits_before);

  /* Stale callbacks / events from the interrupted activation cannot reopen
   * the poisoned context. */
  goodix_device_context_complete_receive (f->ctx, poisoned_generation,
                                           NULL, 0, NULL);
  goodix_device_context_emit_finger_down_for_generation (
    f->ctx, poisoned_generation);
  g_assert_true (goodix_device_context_get_poisoned (f->ctx));
  g_assert_cmpuint (goodix_device_context_get_generation (f->ctx), ==, 0);
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_before);

  fixture_close (f);
  g_assert_null (goodix_fpimage_device_get_context (f->device));
  test_fixture_free (f);
}

static void
test_cancellation_await_finger_on (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();

  fixture_open (f);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  g_assert_cmpint (f->last_state, ==, FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);

  g_cancellable_cancel (cancellable);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_cmpuint (f->completion_count, ==, 1);

  fixture_close (f);
  test_fixture_free (f);
}

static void
test_cancellation_capture (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];

  fixture_open (f);
  fill_gradient_samples (samples);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  goodix_device_context_emit_finger_down (f->ctx);
  g_assert_cmpint (f->last_state, ==, FPI_IMAGE_DEVICE_STATE_CAPTURE);

  g_cancellable_cancel (cancellable);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_cmpuint (f->completion_count, ==, 1);

  fixture_close (f);
  test_fixture_free (f);
}

static void
test_cancellation_await_finger_off (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];

  fixture_open (f);
  fill_gradient_samples (samples);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  goodix_device_context_emit_finger_down (f->ctx);
  goodix_device_context_emit_image_ready (f->ctx, samples,
                                          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
  g_assert_cmpint (f->last_state, ==, FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_OFF);

  g_cancellable_cancel (cancellable);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_cmpuint (f->completion_count, ==, 1);

  fixture_close (f);
  test_fixture_free (f);
}

static void
test_cancellation_deactivating (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  guint completion_before;

  fixture_open (f);
  fill_gradient_samples (samples);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  goodix_device_context_emit_finger_down (f->ctx);
  goodix_device_context_emit_image_ready (f->ctx, samples,
                                          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);

  goodix_device_context_set_deactivation_held (f->ctx, TRUE);
  g_cancellable_cancel (cancellable);

  /* libfprint forwards external cancellation through an idle source.
   * Give that source a chance to invoke the driver's deactivate vfunc;
   * deactivation_held keeps the driver in DEACTIVATING until the test
   * explicitly completes it below. */
  while (g_main_context_pending (NULL))
    g_main_context_iteration (NULL, FALSE);

  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_DEACTIVATING);

  completion_before = f->completion_count;

  /* A second cancellation while deactivating must not produce a second
   * completion or any new backend command. */
  g_cancellable_cancel (cancellable);

  goodix_device_context_complete_deactivation (f->ctx);

  test_wait (f);
  g_assert_cmpuint (f->completion_count, ==, completion_before + 1);

  fixture_close (f);
  test_fixture_free (f);
}

/* -------------------------------------------------------------
 * 7.4 Stale callbacks / generation guard
 * ------------------------------------------------------------- */
static void
test_stale_callback_generation_guard (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  guint commands_before;
  guint64 old_generation;
  g_autoptr(GCancellable) second_cancellable = g_cancellable_new ();
  GoodixFpiUsbBackend *usb_backend;
  GoodixUsbRouter *router;
  const guint8 synthetic_a0[] = { 0xa0, 0x01, 0x00, 0xa1, 0x01 };

  fixture_open (f);
  fill_gradient_samples (samples);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  goodix_device_context_emit_finger_down (f->ctx);

  old_generation = goodix_device_context_get_generation (f->ctx);
  usb_backend = goodix_device_context_get_fpi_usb_backend (f->ctx);
  router = goodix_device_context_get_usb_router (f->ctx);
  goodix_device_context_set_async_usb_submit_seam (f->ctx,
                                                    host_only_usb_submit, NULL);
  g_assert_true (goodix_device_context_arm_receive (f->ctx, NULL));

  /* Complete the action, invalidating the generation. */
  goodix_device_context_emit_image_ready (f->ctx, samples,
                                          GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
  goodix_device_context_emit_release_tail_complete (f->ctx);
  goodix_device_context_emit_finger_up_ready (f->ctx);

  while (goodix_device_context_get_state (f->ctx) !=
         GOODIX_DEVICE_CONTEXT_STATE_DEACTIVATING)
    g_main_context_iteration (NULL, TRUE);
  g_assert_false (f->done);
  g_assert_false (goodix_fpi_usb_backend_is_drained (usb_backend));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (usb_backend), ==, 1);

  /* Cancellation requests only fence the transfer.  The synthetic callback
   * owns and releases N's physical-shaped token, which allows deactivation
   * completion without claiming device-side protocol quiescence. */
  g_autoptr(GError) cancelled = g_error_new_literal (
    G_IO_ERROR, G_IO_ERROR_CANCELLED, "synthetic cancelled IN completion");
  goodix_device_context_complete_receive (f->ctx, old_generation, NULL, 0,
                                           cancelled);
  g_assert_true (goodix_fpi_usb_backend_is_drained (usb_backend));
  test_wait (f);

  g_assert_true (f->success);
  g_assert_cmpuint (goodix_device_context_get_generation (f->ctx), ==, 0);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, second_cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  guint64 current_generation = goodix_device_context_get_generation (f->ctx);
  g_assert_cmpuint (current_generation, !=, old_generation);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  g_assert_true (goodix_device_context_arm_receive (f->ctx, NULL));

  /* The late N callback is routed through the integrated context/backend
   * seam and cannot consume the N+1 router token. */
  goodix_device_context_complete_receive (f->ctx, old_generation,
                                           synthetic_a0,
                                           sizeof synthetic_a0, NULL);
  g_assert_cmpuint (goodix_usb_router_get_outstanding (router), ==, 1);
  g_assert_cmpuint (goodix_usb_router_get_delivery_count (router), ==, 0);
  goodix_device_context_complete_receive (f->ctx, current_generation,
                                           synthetic_a0,
                                           sizeof synthetic_a0, NULL);
  g_assert_cmpuint (goodix_usb_router_get_delivery_count (router), ==, 1);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_max_outstanding (usb_backend),
                    ==, 1);

  /* An N-1 callback must cause zero new backend commands. */
  commands_before = goodix_device_context_get_backend_command_count (f->ctx);
  goodix_device_context_emit_finger_down_for_generation (f->ctx,
                                                         old_generation);
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_before);
  g_cancellable_cancel (second_cancellable);
  test_wait (f);

  fixture_close (f);
  test_fixture_free (f);
}

/* -------------------------------------------------------------
 * 7.5 Error path
 * ------------------------------------------------------------- */
static void
test_terminal_error_path (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GError) terminal = NULL;
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  guint commands_after_error;

  fixture_open (f);
  fill_gradient_samples (samples);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  goodix_device_context_emit_finger_down (f->ctx);

  terminal = g_error_new (FP_DEVICE_ERROR, FP_DEVICE_ERROR_PROTO,
                          "host-only terminal error");
  goodix_device_context_emit_terminal_error (f->ctx, terminal);

  test_wait (f);
  g_assert_false (f->success);
  g_assert_true (goodix_device_context_get_poisoned (f->ctx));
  g_assert_true (goodix_device_context_get_terminal_fence (f->ctx));
  g_assert_cmpuint (f->completion_count, ==, 1);

  /* fpi_image_device_session_error() deactivates the framework session, so
   * the expected teardown is exactly ARM + DISARM, with no REARM. */
  g_assert_cmpuint (goodix_in_memory_backend_get_arm_count (f->ctx), ==, 1);
  g_assert_cmpuint (goodix_in_memory_backend_get_disarm_count (f->ctx), ==, 1);
  g_assert_cmpuint (goodix_in_memory_backend_get_rearm_count (f->ctx), ==, 0);
  commands_after_error = goodix_device_context_get_backend_command_count (f->ctx);

  /* No further commands accepted after the terminal fence. */
  goodix_device_context_emit_finger_up_ready (f->ctx);
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_after_error);

  fixture_close (f);
  test_fixture_free (f);
}

static void
test_poison_is_sticky_until_close (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) first_cancellable = g_cancellable_new ();
  g_autoptr(GCancellable) second_cancellable = g_cancellable_new ();
  g_autoptr(GError) terminal = NULL;
  GoodixFpiUsbBackend *usb_backend;
  guint64 poisoned_generation;
  guint64 real_submits_before;
  guint64 out_submits_before;
  guint commands_before;

  fixture_open (f);
  usb_backend = goodix_device_context_get_fpi_usb_backend (f->ctx);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, first_cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  poisoned_generation = goodix_device_context_get_generation (f->ctx);
  g_assert_cmpuint (poisoned_generation, >, 0);

  terminal = g_error_new (FP_DEVICE_ERROR, FP_DEVICE_ERROR_PROTO,
                          "host-only sticky poison trigger");
  goodix_device_context_emit_terminal_error (f->ctx, terminal);
  test_wait (f);

  g_assert_false (f->success);
  g_assert_true (goodix_device_context_get_poisoned (f->ctx));
  g_assert_true (goodix_device_context_get_terminal_fence (f->ctx));
  g_assert_cmpuint (goodix_device_context_get_generation (f->ctx), ==, 0);

  commands_before = goodix_device_context_get_backend_command_count (f->ctx);
  real_submits_before =
    goodix_fpi_usb_backend_get_real_submit_count (usb_backend);
  out_submits_before =
    goodix_fpi_usb_backend_get_out_submit_count (usb_backend);

  g_clear_error (&f->error);
  f->done = FALSE;
  f->completion_count = 0;
  f->success = FALSE;
  fp_device_capture (FP_DEVICE (f->device), TRUE, second_cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  test_wait (f);

  g_assert_false (f->success);
  g_assert_error (f->error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_PROTO);
  g_assert_true (goodix_device_context_get_poisoned (f->ctx));
  g_assert_true (goodix_device_context_get_terminal_fence (f->ctx));
  g_assert_cmpuint (goodix_device_context_get_generation (f->ctx), ==, 0);
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_before);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (usb_backend),
                    ==, real_submits_before);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_submit_count (usb_backend),
                    ==, out_submits_before);

  /* Neither an old-generation callback nor a fake device event may reopen
   * the poisoned context or reach a backend command. */
  goodix_device_context_complete_receive (f->ctx, poisoned_generation,
                                           NULL, 0, NULL);
  goodix_device_context_emit_finger_down_for_generation (
    f->ctx, poisoned_generation);
  g_assert_true (goodix_device_context_get_poisoned (f->ctx));
  g_assert_cmpuint (goodix_device_context_get_generation (f->ctx), ==, 0);
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_before);

  fixture_close (f);
  g_assert_null (goodix_fpimage_device_get_context (f->device));
  test_fixture_free (f);
}

static void
test_d276_04_context_ownership (void)
{
  static const guint8 synthetic_secret[] = { 0x44, 0x32, 0x37, 0x36, 0x2d, 0x30, 0x34 };
  TestFixture *f = test_fixture_new ();
  GoodixTlsAudit audit = { 0 };
  g_autoptr(GError) error = NULL;

  fixture_open (f);
  g_assert_nonnull (goodix_device_context_get_usb_router (f->ctx));
  g_assert_nonnull (goodix_device_context_get_fpi_usb_backend (f->ctx));
  g_assert_null (goodix_device_context_get_tls_server (f->ctx));
  g_assert_true (goodix_device_context_configure_tls (
    f->ctx, synthetic_secret, sizeof synthetic_secret, NULL, NULL, &audit,
    &error));
  g_assert_no_error (error);
  g_assert_nonnull (goodix_device_context_get_tls_server (f->ctx));
  fixture_close (f);
  g_assert_true (audit.project_secret_zeroized);
  test_fixture_free (f);
}

static void
test_d278_12_post_tls_context_ownership (void)
{
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  GoodixPostTlsMaterial material = { 0 };
  GoodixPostTlsAudit audit = { 0 };
  GoodixFpiUsbBackend *backend;
  GoodixUsbRouter *router;
  g_autoptr(GError) error = NULL;

  fixture_open (f);
  backend = goodix_device_context_get_fpi_usb_backend (f->ctx);
  router = goodix_device_context_get_usb_router (f->ctx);
  for (guint i = 0; i < 6u; i++)
    {
      material.initial_fdt_table[i * 2u] = 0x80;
      material.initial_fdt_table[i * 2u + 1u] = (guint8) (0x40u + i);
    }
  material.af_timestamp = 1;
  material.first_arm_timestamp = 2;
  material.second_arm_timestamp = 3;

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  g_assert_cmpuint (goodix_device_context_get_generation (f->ctx), >, 0u);
  g_assert_true (goodix_device_context_configure_post_tls_lifecycle (
    f->ctx, &material, &audit, &error));
  g_assert_no_error (error);
  g_assert_nonnull (goodix_device_context_get_post_tls_lifecycle (f->ctx));
  g_assert_true (goodix_device_context_get_fpi_usb_backend (f->ctx) == backend);
  g_assert_true (goodix_device_context_get_usb_router (f->ctx) == router);

  g_cancellable_cancel (cancellable);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_error (f->error, G_IO_ERROR, G_IO_ERROR_CANCELLED);
  fixture_close (f);
  test_fixture_free (f);
}

static void
test_d278_14_non_null_usb_binding (void)
{
  g_autoptr(GUsbDevice) usb_device = NULL;
  g_autoptr(GoodixFpImageDevice) device = NULL;
  GoodixDeviceContext *ctx;
  GoodixFpiUsbBackend *backend;
  GoodixUsbRouter *router;
  FpDeviceClass *device_class;

  goodix_test_gusb_reset_counts ();
  usb_device = (GUsbDevice *) g_object_new (G_USB_TYPE_DEVICE, NULL);
  g_assert_nonnull (usb_device);

  device = goodix_fpimage_device_new_for_usb (usb_device);
  g_assert_nonnull (device);
  g_assert_true (fpi_device_get_usb_device (FP_DEVICE (device)) == usb_device);
  device_class = FP_DEVICE_GET_CLASS (device);
  g_assert_cmpint (device_class->type, ==, FP_DEVICE_TYPE_USB);
  g_assert_cmpstr (device_class->id, ==, "goodix_27c6_5125");
  g_assert_cmpstr (device_class->full_name, ==,
                   "Goodix 27c6:5125 Fingerprint Sensor");
  g_assert_nonnull (device_class->id_table);
  g_assert_cmpuint (device_class->id_table[0].vid, ==, 0x27c6u);
  g_assert_cmpuint (device_class->id_table[0].pid, ==, 0x5125u);
  g_assert_cmpuint (device_class->id_table[0].driver_data, ==, 0u);
  g_assert_cmpuint (device_class->id_table[1].vid, ==, 0u);
  g_assert_cmpuint (device_class->id_table[1].pid, ==, 0u);
  g_assert_cmpuint (fpi_device_goodix_27c6_5125_get_type (), ==,
                    G_OBJECT_TYPE (device));

  ctx = goodix_fpimage_device_get_context (device);
  backend = goodix_device_context_get_fpi_usb_backend (ctx);
  router = goodix_device_context_get_usb_router (ctx);
  g_assert_nonnull (ctx);
  g_assert_nonnull (backend);
  g_assert_nonnull (router);
  g_assert_true (goodix_device_context_get_fpi_usb_backend (ctx) == backend);
  g_assert_true (goodix_device_context_get_usb_router (ctx) == router);
  g_assert_true (goodix_fpi_usb_backend_is_drained (backend));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (backend), ==, 0u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_outstanding (backend), ==,
                    0u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (backend), ==,
                    0u);
  g_assert_cmpuint (goodix_test_gusb_get_open_count (), ==, 0u);
  g_assert_cmpuint (goodix_test_gusb_get_close_count (), ==, 0u);

  g_print ("NON_NULL_GUSBDEVICE_FPDEVICE_BINDING_HOST_ONLY_PROVEN=true\n");
}

/* -------------------------------------------------------------
 * Main
 * ------------------------------------------------------------- */
int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);

  g_test_add_func ("/goodix-fpimage-device/lifecycle-base-capture",
                   test_lifecycle_base_capture);
  g_test_add_func ("/goodix-fpimage-device/non-enroll-finger-off-sync-deactivate",
                   test_non_enroll_finger_off_synchronous_deactivate);
  g_test_add_func ("/goodix-fpimage-device/enroll-minutiae-done-before-finger-off",
                   test_enroll_minutiae_done_before_finger_off);
  g_test_add_func ("/goodix-fpimage-device/enroll-finger-off-before-minutiae-done",
                   test_enroll_finger_off_before_minutiae_done);
  g_test_add_func ("/goodix-fpimage-device/no-rearm-before-both-gates",
                   test_no_rearm_before_both_gates);
  g_test_add_func ("/goodix-fpimage-device/no-command-after-deactivate-fence",
                   test_no_command_after_deactivate_fence);
  g_test_add_func ("/goodix-fpimage-device/cancellation-opening",
                   test_cancellation_opening);
  g_test_add_func ("/goodix-fpimage-device/cancellation-activating",
                   test_cancellation_activating);
  g_test_add_func ("/goodix-fpimage-device/cancellation-await-finger-on",
                   test_cancellation_await_finger_on);
  g_test_add_func ("/goodix-fpimage-device/cancellation-capture",
                   test_cancellation_capture);
  g_test_add_func ("/goodix-fpimage-device/cancellation-await-finger-off",
                   test_cancellation_await_finger_off);
  g_test_add_func ("/goodix-fpimage-device/cancellation-deactivating",
                   test_cancellation_deactivating);
  g_test_add_func ("/goodix-fpimage-device/stale-callback-generation-guard",
                   test_stale_callback_generation_guard);
  g_test_add_func ("/goodix-fpimage-device/terminal-error-path",
                   test_terminal_error_path);
  g_test_add_func ("/goodix-fpimage-device/poison-is-sticky-until-close",
                   test_poison_is_sticky_until_close);
  g_test_add_func ("/goodix-fpimage-device/d276-04-context-ownership",
                   test_d276_04_context_ownership);
  g_test_add_func ("/goodix-fpimage-device/d278-12-post-tls-context-ownership",
                   test_d278_12_post_tls_context_ownership);
  g_test_add_func ("/goodix-fpimage-device/d278-14-non-null-usb-binding",
                   test_d278_14_non_null_usb_binding);

  return g_test_run ();
}
