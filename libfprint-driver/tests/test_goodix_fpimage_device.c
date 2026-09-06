/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Host-only deterministic tests for the Goodix FpImageDevice shell.
 *
 * These tests exercise the real repository-local libfprint 1.94.5 FpImageDevice
 * state machine through public async actions, with an in-memory fake backend.
 */
#include "../goodix_fpimage_device.h"
#include "../goodix_a0_protocol.h"
#include "../goodix_enrollment_fpi_usb_binding.h"
#include "../goodix_enrollment_post_tls_events.h"
#include "../goodix_fpi_usb_backend.h"
#include "../goodix_usb_router.h"
#include "../goodix_u16_to_fpimage.h"

#include "test_sigfm_control.h"

#include "fpi-image-device.h"
#include "fp-device.h"
#include "fp-image-device.h"
#include "fp-print.h"

#include <glib.h>
#include <openssl/evp.h>

#define TEST_TIMEOUT_MS 5000

void  goodix_test_gusb_reset_counts (void);
guint goodix_test_gusb_get_open_count (void);
guint goodix_test_gusb_get_close_count (void);
void  goodix_test_gusb_set_open_close_success (gboolean value);

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
test_fixture_new_with_device (GoodixFpImageDevice *device)
{
  TestFixture *f;

  f = g_new0 (TestFixture, 1);
  f->loop = g_main_loop_new (NULL, FALSE);
  f->device = device;
  f->ctx = goodix_fpimage_device_get_context (f->device);
  g_signal_connect (f->device, "fpi-image-device-state-changed",
                    G_CALLBACK (state_changed_cb), f);

  return f;
}

static TestFixture *
test_fixture_new (void)
{
  return test_fixture_new_with_device (goodix_fpimage_device_new ());
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
  f->ctx = goodix_fpimage_device_get_context (f->device);
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

static gboolean
d279_20_image_ready (GoodixEnrollmentPipeline *pipeline,
                     guint                     stage_index,
                     FpImage                  *image,
                     gpointer                  user_data,
                     GError                  **error)
{
  (void) pipeline;
  (void) stage_index;
  (void) image;
  (void) user_data;
  (void) error;
  return TRUE;
}

static gboolean
d279_20_timestamp_ready (guint                           stage_index,
                         GoodixEnrollmentCommandPurpose purpose,
                         guint16                        *timestamp,
                         gpointer                        user_data,
                         GError                        **error)
{
  (void) stage_index;
  (void) purpose;
  (void) user_data;
  (void) error;
  *timestamp = 0x3000u;
  return TRUE;
}

static gboolean
d279_20_auxiliary_ready (GBytes   *plaintext,
                         gpointer  user_data,
                         GError  **error)
{
  (void) plaintext;
  (void) user_data;
  (void) error;
  return TRUE;
}

static GBytes *
d279_20_build_irq2 (void)
{
  guint8 body[16] = { 0x02, 0x00, 0x3f, 0x00 };
  g_autoptr(GError) error = NULL;
  GBytes *frame;

  for (guint i = 0u; i < 6u; i++)
    {
      guint16 word = (guint16) (0x88u + i * 2u);

      body[4u + i * 2u] = (guint8) word;
      body[5u + i * 2u] = (guint8) (word >> 8);
    }
  frame = goodix_a0_build_frame (0x32, 0x32, body, sizeof body, &error);
  g_assert_no_error (error);
  g_assert_nonnull (frame);
  return frame;
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

  /* Cancel before the configured multistage enrollment proceeds further. */
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
test_d279_11_full_target_local_stage_policy (void)
{
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(FpPrint) template = NULL;
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  TestFixture *f = test_fixture_new ();

  fixture_open (f);
  g_assert_cmpint (fp_device_get_nr_enroll_stages (FP_DEVICE (f->device)), ==,
                   (gint) GOODIX_TARGET_LOCAL_ENROLL_STAGES);
  template = fp_print_new (FP_DEVICE (f->device));
  fill_gradient_samples (samples);
  f->done = FALSE;
  f->completion_count = 0;
  f->enroll_progress_count = 0;
  fp_device_enroll (FP_DEVICE (f->device), g_steal_pointer (&template),
                    cancellable, progress_cb, f, NULL,
                    (GAsyncReadyCallback) enroll_cb, f);
  goodix_device_context_emit_arm_complete (f->ctx, NULL);

  for (guint stage = 1u; stage <= GOODIX_TARGET_LOCAL_ENROLL_STAGES; stage++)
    {
      gint64 deadline;
      gboolean final_stage = stage == GOODIX_TARGET_LOCAL_ENROLL_STAGES;

      g_assert_cmpint (f->last_state, ==,
                       FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);
      goodix_device_context_emit_finger_down (f->ctx);
      g_assert_cmpint (f->last_state, ==, FPI_IMAGE_DEVICE_STATE_CAPTURE);
      samples[stage % G_N_ELEMENTS (samples)] = (uint16_t) (stage * 17u);
      if (final_stage)
        goodix_test_sigfm_extract_set_block (TRUE);
      goodix_device_context_emit_image_ready (
        f->ctx, samples, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);

      if (final_stage)
        {
          g_assert_true (goodix_test_sigfm_extract_wait_blocked (
            TEST_TIMEOUT_MS * 1000));
          goodix_device_context_emit_release_tail_complete (f->ctx);
          goodix_device_context_emit_finger_up_ready (f->ctx);
          g_assert_cmpint (f->last_state, ==, FPI_IMAGE_DEVICE_STATE_IDLE);
          goodix_test_sigfm_extract_unblock ();
        }

      deadline = g_get_monotonic_time () + TEST_TIMEOUT_MS * 1000;
      while (f->enroll_progress_count < stage && !f->done &&
             g_get_monotonic_time () < deadline)
        g_main_context_iteration (NULL, FALSE);
      g_assert_cmpuint (f->enroll_progress_count, ==, stage);

      if (!final_stage)
        {
          goodix_device_context_emit_release_tail_complete (f->ctx);
          goodix_device_context_emit_finger_up_ready (f->ctx);
          g_assert_cmpint (f->last_state, ==,
                           FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);
        }
    }

  test_wait (f);
  g_assert_true (f->success);
  g_assert_nonnull (f->enroll_print);
  g_assert_cmpuint (f->completion_count, ==, 1u);
  g_assert_cmpuint (f->enroll_progress_count, ==,
                    GOODIX_TARGET_LOCAL_ENROLL_STAGES);
  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);

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

typedef struct
{
  GoodixFpImageDevice *device;
  GString *events;
  guint acquire_count;
  guint material_release_count;
  guint claim_count;
  guint interface_release_count;
  gboolean fail_acquire;
  gboolean fail_claim;
  gboolean fail_release;
  gboolean cancel_after_acquire;
  guint in_submit_count;
  guint out_submit_count;
  guint8 validator[32];
  guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH];
  guint8 a2[3];
  guint8 chip[4];
  guint8 otp[64];
  guint8 synthetic_psk[GOODIX_SECURE_SESSION_PSK_LENGTH];
} ProductionOpenSeam;

static void
production_digest (const guint8 *data,
                   gsize         length,
                   guint8        output[32])
{
  unsigned int output_length = 0;

  g_assert_true (EVP_Digest (data, length, output, &output_length,
                             EVP_sha256 (), NULL));
  g_assert_cmpuint (output_length, ==, 32u);
}

static void
production_set_config_finalizer (
  guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH])
{
  guint32 sum = 0;
  guint16 finalizer;

  for (guint i = 0; i < 111u; i++)
    sum += (guint16) ((guint16) config[i * 2u] |
                     (guint16) ((guint16) config[i * 2u + 1u] << 8));
  finalizer = (guint16) (0u - 0xa5a5u - sum);
  config[222] = (guint8) finalizer;
  config[223] = (guint8) (finalizer >> 8);
}

static void
production_material_init (ProductionOpenSeam *seam)
{
  static const guint8 registers[4][2] = {
    { 0x20, 0x02 }, { 0x36, 0x02 }, { 0x38, 0x02 }, { 0x3a, 0x02 }
  };
  static const guint8 values[4][2] = {
    { 0xd8, 0x0b }, { 0xbe, 0x00 }, { 0xbd, 0x00 }, { 0xbc, 0x00 }
  };
  static const guint offsets[] = { 117, 121, 125, 129 };

  for (guint i = 0; i < 32u; i++)
    {
      seam->validator[i] = (guint8) (0x20u + i);
      seam->synthetic_psk[i] = (guint8) (0x80u + i);
    }
  seam->a2[0] = 0x11;
  seam->a2[1] = 0x22;
  seam->a2[2] = 0x33;
  seam->chip[0] = 0x25;
  seam->chip[1] = 0x04;
  seam->chip[2] = 0x12;
  seam->chip[3] = 0x50;
  for (guint i = 0; i < sizeof seam->otp; i++)
    seam->otp[i] = (guint8) (i * 3u + 1u);
  for (guint i = 0; i < G_N_ELEMENTS (offsets); i++)
    {
      memcpy (seam->config + offsets[i], registers[i], 2u);
      memcpy (seam->config + offsets[i] + 2u, values[i], 2u);
    }
  production_set_config_finalizer (seam->config);
}

static gboolean
production_acquire_seam (
  GoodixRuntimeMaterial       **owner,
  GoodixSecureSessionMaterial  *secure_view,
  guint8                        fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GoodixRuntimeMaterialAudit   *audit,
  gpointer                      user_data,
  GError                      **error)
{
  ProductionOpenSeam *seam = user_data;
  static const guint8 identity[] = "GF_ST411SEC_APP_12509";
  static const guint8 values[4][2] = {
    { 0xd8, 0x0b }, { 0xbe, 0x00 }, { 0xbd, 0x00 }, { 0xbc, 0x00 }
  };

  seam->acquire_count++;
  g_string_append_c (seam->events, 'A');
  g_assert_cmpuint (goodix_test_gusb_get_open_count (), ==,
                    seam->acquire_count);
  memset (audit, 0, sizeof *audit);
  memset (secure_view, 0, sizeof *secure_view);
  memset (fdt_seed, 0x80, GOODIX_RUNTIME_FDT_SEED_LENGTH);
  if (seam->fail_acquire)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                           "synthetic runtime material failure");
      return FALSE;
    }
  secure_view->expected_identity = identity;
  secure_view->expected_identity_length = sizeof identity;
  secure_view->e4_validator = seam->validator;
  secure_view->e4_validator_length = sizeof seam->validator;
  secure_view->config90 = seam->config;
  secure_view->config90_length = sizeof seam->config;
  secure_view->psk = seam->synthetic_psk;
  secure_view->psk_length = sizeof seam->synthetic_psk;
  memcpy (secure_view->dac_values, values, sizeof values);
  production_digest (seam->validator, sizeof seam->validator,
                     secure_view->e4_validator_sha256);
  production_digest (seam->a2, sizeof seam->a2,
                     secure_view->a2_response_sha256);
  production_digest (seam->chip, sizeof seam->chip,
                     secure_view->chip82_response_sha256);
  production_digest (seam->otp, sizeof seam->otp,
                     secure_view->otp_a6_response_sha256);
  production_digest (seam->config, sizeof seam->config,
                     secure_view->config90_sha256);
  *owner = (GoodixRuntimeMaterial *) g_malloc0 (1u);
  if (seam->cancel_after_acquire)
    g_cancellable_cancel (
      fpi_device_get_cancellable (FP_DEVICE (seam->device)));
  return TRUE;
}

static void
production_material_release_seam (GoodixRuntimeMaterial *owner,
                                  gpointer               user_data)
{
  ProductionOpenSeam *seam = user_data;

  seam->material_release_count++;
  g_string_append_c (seam->events, 'F');
  g_free (owner);
}

static gboolean
production_claim_seam (GUsbDevice *usb_device,
                       guint8      interface_number,
                       gpointer    user_data,
                       GError    **error)
{
  ProductionOpenSeam *seam = user_data;
  GoodixDeviceContext *ctx =
    goodix_fpimage_device_get_context (seam->device);

  (void) usb_device;
  g_assert_cmpuint (interface_number, ==, 0u);
  g_assert_true (goodix_device_context_has_runtime_material (ctx));
  g_assert_false (goodix_device_context_has_usb_claim (ctx));
  seam->claim_count++;
  g_string_append_c (seam->events, 'C');
  if (seam->fail_claim)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                           "synthetic interface claim failure");
      return FALSE;
    }
  return TRUE;
}

static gboolean
production_release_seam (GUsbDevice *usb_device,
                         guint8      interface_number,
                         gpointer    user_data,
                         GError    **error)
{
  ProductionOpenSeam *seam = user_data;
  GoodixDeviceContext *ctx =
    goodix_fpimage_device_get_context (seam->device);

  (void) usb_device;
  g_assert_cmpuint (interface_number, ==, 0u);
  g_assert_true (goodix_device_context_has_runtime_material (ctx));
  g_assert_true (goodix_device_context_has_usb_claim (ctx));
  seam->interface_release_count++;
  g_string_append_c (seam->events, 'R');
  if (seam->fail_release)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                           "synthetic interface release failure");
      return FALSE;
    }
  return TRUE;
}

static TestFixture *
production_fixture_new (ProductionOpenSeam *seam)
{
  g_autoptr(GUsbDevice) usb_device = NULL;
  TestFixture *f;

  goodix_test_gusb_reset_counts ();
  goodix_test_gusb_set_open_close_success (TRUE);
  usb_device = (GUsbDevice *) g_object_new (G_USB_TYPE_DEVICE, NULL);
  f = test_fixture_new_with_device (
    goodix_fpimage_device_new_for_usb (usb_device));
  seam->device = f->device;
  seam->events = g_string_new (NULL);
  production_material_init (seam);
  goodix_fpimage_device_set_production_open_seams (
    f->device, production_acquire_seam, production_material_release_seam,
    production_claim_seam, production_release_seam, seam);
  return f;
}

static void
production_seam_clear (ProductionOpenSeam *seam)
{
  if (seam->events != NULL)
    g_string_free (seam->events, TRUE);
  seam->events = NULL;
  memset (seam->synthetic_psk, 0, sizeof seam->synthetic_psk);
  memset (seam->validator, 0, sizeof seam->validator);
  memset (seam->config, 0, sizeof seam->config);
  memset (seam->a2, 0, sizeof seam->a2);
  memset (seam->chip, 0, sizeof seam->chip);
  memset (seam->otp, 0, sizeof seam->otp);
}

static void
production_graph_submit_seam (GoodixFpiUsbBackend *backend,
                              GoodixUsbDirection   direction,
                              guint64              generation,
                              GBytes              *bytes,
                              gpointer             user_data)
{
  ProductionOpenSeam *seam = user_data;

  (void) backend;
  g_assert_cmpuint (generation, >, 0u);
  if (direction == GOODIX_USB_TRANSFER_IN)
    {
      g_assert_null (bytes);
      seam->in_submit_count++;
    }
  else
    {
      g_assert_nonnull (bytes);
      seam->out_submit_count++;
    }
}

static void
wait_for_context_state (GoodixDeviceContext      *ctx,
                        GoodixDeviceContextState  state)
{
  gint64 deadline = g_get_monotonic_time () + TEST_TIMEOUT_MS * 1000;

  while (goodix_device_context_get_state (ctx) != state &&
         g_get_monotonic_time () < deadline)
    g_main_context_iteration (NULL, TRUE);
  g_assert_cmpint (goodix_device_context_get_state (ctx), ==, state);
}

static void
test_d279_08_production_open_close_ownership (void)
{
  ProductionOpenSeam seam = { 0 };
  TestFixture *f = production_fixture_new (&seam);

  fixture_open (f);
  g_assert_true (goodix_device_context_has_runtime_material (f->ctx));
  g_assert_true (goodix_device_context_has_usb_claim (f->ctx));
  g_assert_cmpstr (seam.events->str, ==, "AC");
  fixture_close (f);
  g_assert_null (goodix_fpimage_device_get_context (f->device));
  g_assert_cmpstr (seam.events->str, ==, "ACRF");

  /* A second open on the same FpDevice creates a distinct owned epoch. */
  fixture_open (f);
  fixture_close (f);
  g_assert_cmpstr (seam.events->str, ==, "ACRFACRF");
  g_assert_cmpuint (seam.acquire_count, ==, 2u);
  g_assert_cmpuint (seam.claim_count, ==, 2u);
  g_assert_cmpuint (seam.interface_release_count, ==, 2u);
  g_assert_cmpuint (seam.material_release_count, ==, 2u);
  g_assert_cmpuint (goodix_test_gusb_get_open_count (), ==, 2u);
  g_assert_cmpuint (goodix_test_gusb_get_close_count (), ==, 2u);

  test_fixture_free (f);
  production_seam_clear (&seam);
}

static void
test_d279_08_production_open_failures (void)
{
  ProductionOpenSeam acquire_failure = { .fail_acquire = TRUE };
  ProductionOpenSeam claim_failure = { .fail_claim = TRUE };
  ProductionOpenSeam cancelled = { .cancel_after_acquire = TRUE };
  g_autoptr(GCancellable) cancellable = NULL;
  TestFixture *f;

  f = production_fixture_new (&acquire_failure);
  f->done = FALSE;
  fp_device_open (FP_DEVICE (f->device), NULL,
                  (GAsyncReadyCallback) open_cb, f);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_error (f->error, G_IO_ERROR, G_IO_ERROR_FAILED);
  g_assert_cmpstr (acquire_failure.events->str, ==, "A");
  g_assert_null (goodix_fpimage_device_get_context (f->device));
  test_fixture_free (f);
  production_seam_clear (&acquire_failure);

  f = production_fixture_new (&claim_failure);
  f->done = FALSE;
  fp_device_open (FP_DEVICE (f->device), NULL,
                  (GAsyncReadyCallback) open_cb, f);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_error (f->error, G_IO_ERROR, G_IO_ERROR_FAILED);
  g_assert_cmpstr (claim_failure.events->str, ==, "ACF");
  g_assert_cmpuint (claim_failure.material_release_count, ==, 1u);
  g_assert_cmpuint (claim_failure.interface_release_count, ==, 0u);
  g_assert_null (goodix_fpimage_device_get_context (f->device));
  test_fixture_free (f);
  production_seam_clear (&claim_failure);

  f = production_fixture_new (&cancelled);
  cancellable = g_cancellable_new ();
  f->done = FALSE;
  fp_device_open (FP_DEVICE (f->device), cancellable,
                  (GAsyncReadyCallback) open_cb, f);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_error (f->error, G_IO_ERROR, G_IO_ERROR_CANCELLED);
  g_assert_cmpstr (cancelled.events->str, ==, "AF");
  g_assert_cmpuint (cancelled.claim_count, ==, 0u);
  g_assert_cmpuint (cancelled.material_release_count, ==, 1u);
  g_assert_null (goodix_fpimage_device_get_context (f->device));
  test_fixture_free (f);
  production_seam_clear (&cancelled);
}

static void
test_d279_08_production_release_failure (void)
{
  ProductionOpenSeam seam = { .fail_release = TRUE };
  TestFixture *f = production_fixture_new (&seam);

  fixture_open (f);
  f->done = FALSE;
  f->completion_count = 0;
  fp_device_close (FP_DEVICE (f->device), NULL,
                   (GAsyncReadyCallback) close_cb, f);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_error (f->error, G_IO_ERROR, G_IO_ERROR_FAILED);
  g_assert_cmpstr (seam.events->str, ==, "ACRF");
  g_assert_cmpuint (seam.material_release_count, ==, 1u);
  g_assert_null (goodix_fpimage_device_get_context (f->device));
  g_assert_cmpuint (goodix_test_gusb_get_close_count (), ==, 1u);

  test_fixture_free (f);
  production_seam_clear (&seam);
}

static void
test_d279_09_production_activation_binding (void)
{
  ProductionOpenSeam seam = { 0 };
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GError) timeout = NULL;
  g_autoptr(GError) cancelled = NULL;
  TestFixture *f = production_fixture_new (&seam);
  GoodixFpiUsbBackend *backend;
  GoodixPreSessionRxSyncAudit sync_audit;
  guint64 generation;

  fixture_open (f);
  backend = goodix_device_context_get_fpi_usb_backend (f->ctx);
  goodix_device_context_set_async_usb_submit_seam (
    f->ctx, production_graph_submit_seam, &seam);

  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  generation = goodix_device_context_get_generation (f->ctx);
  g_assert_cmpuint (generation, >, 0u);
  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING);
  g_assert_cmpuint (seam.in_submit_count, ==, 1u);
  g_assert_cmpuint (seam.out_submit_count, ==, 0u);
  g_assert_cmpint (goodix_fpi_usb_backend_get_receive_purpose (backend), ==,
                   GOODIX_USB_RECEIVE_PRE_SESSION_SYNC_RX);

  timeout = g_error_new_literal (G_USB_DEVICE_ERROR,
                                 G_USB_DEVICE_ERROR_TIMED_OUT,
                                 "synthetic quiet boundary");
  goodix_device_context_complete_receive (f->ctx, generation, NULL, 0,
                                           timeout);
  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_ACTIVE);
  g_assert_cmpint (f->last_state, ==,
                   FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);
  g_assert_nonnull (goodix_device_context_get_secure_session (f->ctx));
  g_assert_nonnull (goodix_device_context_get_post_tls_lifecycle (f->ctx));
  g_assert_true (goodix_device_context_runtime_handoff_views_cleared (f->ctx));
  g_assert_cmpuint (seam.out_submit_count, ==, 1u);
  g_assert_cmpuint (seam.in_submit_count, ==, 2u);
  goodix_device_context_get_pre_session_rx_sync_audit (f->ctx, &sync_audit);
  g_assert_cmpint (sync_audit.pre_session_rx_result, ==,
                   GOODIX_PRE_SESSION_RX_SYNC_PASS);
  g_assert_true (sync_audit.first_protocol_out_after_rx_sync);

  g_cancellable_cancel (cancellable);
  wait_for_context_state (f->ctx, GOODIX_DEVICE_CONTEXT_STATE_DEACTIVATING);
  cancelled = g_error_new_literal (G_IO_ERROR, G_IO_ERROR_CANCELLED,
                                   "synthetic cancelled transfer");
  goodix_fpi_usb_backend_complete_out (backend, generation, cancelled);
  goodix_device_context_complete_receive (f->ctx, generation, NULL, 0,
                                           cancelled);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_true (goodix_device_context_has_runtime_material (f->ctx));
  g_assert_cmpuint (seam.material_release_count, ==, 0u);

  fixture_close (f);
  g_assert_cmpstr (seam.events->str, ==, "ACRF");
  test_fixture_free (f);
  production_seam_clear (&seam);
}

static void
test_d279_09_production_activation_sync_failure (void)
{
  ProductionOpenSeam seam = { 0 };
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GCancellable) enroll_cancellable = g_cancellable_new ();
  g_autoptr(FpPrint) template = NULL;
  g_autoptr(GError) transport_error = NULL;
  TestFixture *f = production_fixture_new (&seam);
  GLogLevelFlags old_fatal;
  guint in_submits_before;
  guint out_submits_before;
  guint64 generation;

  fixture_open (f);
  goodix_device_context_set_async_usb_submit_seam (
    f->ctx, production_graph_submit_seam, &seam);
  f->done = FALSE;
  f->completion_count = 0;
  fp_device_capture (FP_DEVICE (f->device), TRUE, cancellable,
                     (GAsyncReadyCallback) capture_cb, f);
  generation = goodix_device_context_get_generation (f->ctx);
  transport_error = g_error_new_literal (G_IO_ERROR, G_IO_ERROR_FAILED,
                                         "synthetic sync transport failure");
  goodix_device_context_complete_receive (f->ctx, generation, NULL, 0,
                                           transport_error);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_error (f->error, G_IO_ERROR, G_IO_ERROR_FAILED);
  g_assert_true (goodix_device_context_get_poisoned (f->ctx));
  g_assert_cmpuint (seam.out_submit_count, ==, 0u);
  g_assert_cmpuint (seam.in_submit_count, ==, 1u);

  /* The enrollment policy gate must not mask an existing sticky poison. */
  in_submits_before = seam.in_submit_count;
  out_submits_before = seam.out_submit_count;
  template = fp_print_new (FP_DEVICE (f->device));
  g_clear_error (&f->error);
  f->done = FALSE;
  f->completion_count = 0;
  old_fatal = g_log_set_always_fatal (0);
  fp_device_enroll (FP_DEVICE (f->device), g_steal_pointer (&template),
                    enroll_cancellable, progress_cb, f, NULL,
                    (GAsyncReadyCallback) enroll_cb, f);
  g_log_set_always_fatal (old_fatal);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_error (f->error, G_IO_ERROR, G_IO_ERROR_FAILED);
  g_assert_true (goodix_device_context_get_poisoned (f->ctx));
  g_assert_cmpuint (goodix_device_context_get_generation (f->ctx), ==, 0u);
  g_assert_cmpuint (seam.in_submit_count, ==, in_submits_before);
  g_assert_cmpuint (seam.out_submit_count, ==, out_submits_before);
  fixture_close (f);
  test_fixture_free (f);
  production_seam_clear (&seam);
}

static void
test_d279_09_production_enrollment_rejected_before_submit (void)
{
  ProductionOpenSeam seam = { 0 };
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(FpPrint) template = NULL;
  TestFixture *f = production_fixture_new (&seam);

  fixture_open (f);
  goodix_device_context_set_async_usb_submit_seam (
    f->ctx, production_graph_submit_seam, &seam);
  template = fp_print_new (FP_DEVICE (f->device));
  f->done = FALSE;
  f->completion_count = 0;
  fp_device_enroll (FP_DEVICE (f->device), g_steal_pointer (&template),
                    cancellable, progress_cb, f, NULL,
                    (GAsyncReadyCallback) enroll_cb, f);
  test_wait (f);
  g_assert_false (f->success);
  g_assert_error (f->error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_NOT_SUPPORTED);
  g_assert_cmpuint (goodix_device_context_get_generation (f->ctx), ==, 0u);
  g_assert_false (goodix_device_context_get_poisoned (f->ctx));
  g_assert_cmpuint (seam.in_submit_count, ==, 0u);
  g_assert_cmpuint (seam.out_submit_count, ==, 0u);
  fixture_close (f);
  test_fixture_free (f);
  production_seam_clear (&seam);
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

static GBytes *
d279_24_build_response (guint8        control,
                        const guint8 *body,
                        gsize         body_length)
{
  g_autoptr(GError) error = NULL;
  GBytes *frame = goodix_a0_build_frame (
    control, control, body, body_length, &error);

  g_assert_no_error (error);
  g_assert_nonnull (frame);
  return frame;
}

static GBytes *
d279_24_build_ack (guint8 command)
{
  const guint8 body[2] = { command, 0x01 };

  return d279_24_build_response (0xb0, body, sizeof body);
}

static GBytes *
d279_24_build_event (guint8  control,
                     guint16 irq,
                     guint16 flags,
                     guint16 base)
{
  guint8 body[16];

  body[0] = (guint8) irq;
  body[1] = (guint8) (irq >> 8);
  body[2] = (guint8) flags;
  body[3] = (guint8) (flags >> 8);
  for (guint i = 0u; i < 6u; i++)
    {
      guint16 word = (guint16) (base + i * 2u);
      body[4u + i * 2u] = (guint8) word;
      body[5u + i * 2u] = (guint8) (word >> 8);
    }
  return d279_24_build_response (control, body, sizeof body);
}

static GBytes *
d279_24_build_nav (void)
{
  guint8 body[2409] = { 0x50, 0x01 };
  g_autoptr(GBytes) additive = d279_24_build_response (
    0x50, body, sizeof body);
  gsize length;
  const guint8 *source = g_bytes_get_data (additive, &length);
  guint8 *copy = g_memdup2 (source, length);

  copy[length - 1u] = 0x88;
  return g_bytes_new_take (copy, length);
}

static void
d279_24_complete_out (GoodixDeviceContext *ctx,
                      guint64              generation)
{
  GoodixFpiUsbBackend *backend =
    goodix_device_context_get_fpi_usb_backend (ctx);

  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_outstanding (backend), ==,
                    1u);
  goodix_fpi_usb_backend_complete_out (backend, generation, NULL);
}

static gboolean
d279_24_auxiliary_ready (GBytes   *plaintext,
                         gpointer  user_data,
                         GError  **error)
{
  guint *count = user_data;

  (void) error;
  g_assert_nonnull (plaintext);
  (*count)++;
  return TRUE;
}

static guint32
d279_25_crc32_mpeg2 (const guint8 *data,
                     gsize         length)
{
  guint32 crc = UINT32_C (0xffffffff);

  for (gsize i = 0u; i < length; i++)
    {
      crc ^= (guint32) data[i] << 24;
      for (guint bit = 0u; bit < 8u; bit++)
        crc = (crc & UINT32_C (0x80000000)) != 0u ?
          (crc << 1) ^ UINT32_C (0x04c11db7) : crc << 1;
    }
  return crc;
}

static GBytes *
d279_25_build_primary_plaintext (guint stage)
{
  guint8 bytes[GOODIX_IMAGE_PLAINTEXT_LENGTH] = { 0 };
  guint32 crc;

  bytes[0] = 0x20;
  bytes[1] = 0x0a;
  bytes[2] = 0x1e;
  bytes[8u + stage] = (guint8) stage;
  crc = d279_25_crc32_mpeg2 (bytes + 8u, GOODIX_IMAGE_PACKED_LENGTH);
  bytes[7688] = (guint8) (crc >> 8);
  bytes[7689] = (guint8) crc;
  bytes[7690] = (guint8) (crc >> 24);
  bytes[7691] = (guint8) (crc >> 16);
  bytes[7692] = 0x88;
  return g_bytes_new (bytes, sizeof bytes);
}

static GBytes *
d279_25_wrap_b0 (GBytes *plaintext)
{
  gsize length;
  const guint8 *data = g_bytes_get_data (plaintext, &length);
  guint8 header[4];
  g_autoptr(GByteArray) frame = NULL;

  g_assert_cmpuint (length, <=, G_MAXUINT16);
  header[0] = 0xb0;
  header[1] = (guint8) length;
  header[2] = (guint8) (length >> 8);
  header[3] = (guint8) (header[0] + header[1] + header[2]);
  frame = g_byte_array_sized_new ((guint) length + 4u);
  g_byte_array_append (frame, header, sizeof header);
  g_byte_array_append (frame, data, (guint) length);
  return g_byte_array_free_to_bytes (g_steal_pointer (&frame));
}

static void
d279_25_feed_context_frame (GoodixDeviceContext *ctx,
                            guint64              generation,
                            GBytes              *frame)
{
  GoodixFpiUsbBackend *backend =
    goodix_device_context_get_fpi_usb_backend (ctx);
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);

  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (backend), ==, 1u);
  g_assert_cmpint (goodix_fpi_usb_backend_get_receive_purpose (backend), ==,
                   GOODIX_USB_RECEIVE_PROTOCOL_RX);
  goodix_device_context_complete_receive (
    ctx, generation, data, length, NULL);
  if (goodix_device_context_get_terminal_fence (ctx))
    {
      const GError *error = goodix_device_context_get_terminal_error (ctx);
      g_error ("D279/25 context fenced after input: %s",
               error != NULL ? error->message : "unknown error");
    }
}

static void
d279_25_complete_and_ack (GoodixDeviceContext *ctx,
                          guint64              generation,
                          guint8               command)
{
  g_autoptr(GBytes) ack = d279_24_build_ack (command);

  d279_24_complete_out (ctx, generation);
  d279_25_feed_context_frame (ctx, generation, ack);
}

static void
d279_25_feed_plaintext (GoodixDeviceContext *ctx,
                        guint64              generation,
                        GBytes              *plaintext)
{
  g_autoptr(GBytes) frame = d279_25_wrap_b0 (plaintext);

  d279_25_feed_context_frame (ctx, generation, frame);
}

static void
test_d279_24_context_first_arm_enrollment_handoff (void)
{
  GoodixEnrollmentModelConfig config = { 21u, TRUE };
  GoodixEnrollmentPostTlsEventsAudit events_audit;
  GoodixEnrollmentFpiUsbBindingAudit binding_audit;
  GoodixPostTlsMaterial material = { 0 };
  GoodixPostTlsAudit post_audit;
  TestFixture *f = test_fixture_new ();
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(FpPrint) template = NULL;
  g_autoptr(GError) error = NULL;
  GoodixFpiUsbBackend *backend;
  GoodixPostTlsLifecycle *post_tls;
  guint64 generation;
  guint auxiliary_count = 0u;
  guint8 af[16] = { 0 };
  const guint8 typed82_body[2] = { 0x00, 0x20 };
  const guint8 auxiliary_body[] = { 'a', 'u', 'x' };

  fixture_open (f);
  backend = goodix_device_context_get_fpi_usb_backend (f->ctx);
  goodix_device_context_set_async_usb_submit_seam (
    f->ctx, host_only_usb_submit, NULL);
  template = fp_print_new (FP_DEVICE (f->device));
  f->done = FALSE;
  f->completion_count = 0u;
  f->enroll_progress_count = 0u;
  fp_device_enroll (FP_DEVICE (f->device), g_steal_pointer (&template),
                    cancellable, progress_cb, f, NULL,
                    (GAsyncReadyCallback) enroll_cb, f);
  generation = goodix_device_context_get_generation (f->ctx);
  for (guint i = 0u; i < 6u; i++)
    {
      material.initial_fdt_table[i * 2u] = 0x80;
      material.initial_fdt_table[i * 2u + 1u] = (guint8) (0x40u + i);
    }
  material.af_timestamp = 0x1234;
  material.first_arm_timestamp = 0x2345;
  material.second_arm_timestamp = 0x3456;
  g_assert_true (goodix_device_context_configure_post_tls_lifecycle (
    f->ctx, &material, &post_audit, &error));
  g_assert_true (goodix_device_context_configure_enrollment_graph (
    f->ctx, &config, d279_24_auxiliary_ready, &auxiliary_count,
    &events_audit, &binding_audit, &error));
  g_assert_true (goodix_device_context_has_pending_enrollment_graph (f->ctx));
  g_assert_false (goodix_device_context_has_dormant_enrollment_binding (f->ctx));
  goodix_device_context_emit_arm_complete (f->ctx, NULL);
  g_assert_cmpint (f->last_state, ==,
                   FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);
  post_tls = goodix_device_context_get_post_tls_lifecycle (f->ctx);
  g_assert_true (goodix_post_tls_lifecycle_start (post_tls, &error));

  d279_24_complete_out (f->ctx, generation);
  {
    g_autoptr(GBytes) frame = d279_24_build_ack (0xd4);
    goodix_post_tls_lifecycle_handle_a0 (post_tls, frame);
  }
  d279_24_complete_out (f->ctx, generation);
  af[1] = 0x02;
  {
    g_autoptr(GBytes) frame = d279_24_build_response (0xae, af, sizeof af);
    goodix_post_tls_lifecycle_handle_a0 (post_tls, frame);
  }
  for (guint fdt_index = 0u; fdt_index < 3u; fdt_index++)
    {
      d279_24_complete_out (f->ctx, generation);
      {
        g_autoptr(GBytes) ack = d279_24_build_ack (0x36);
        goodix_post_tls_lifecycle_handle_a0 (post_tls, ack);
      }
      {
        g_autoptr(GBytes) event = d279_24_build_event (
          0x36, 0x0100, 0x0000,
          (guint16) (0x0300u + fdt_index * 0x20u));
        goodix_post_tls_lifecycle_handle_a0 (post_tls, event);
      }
      if (fdt_index == 0u)
        {
          d279_24_complete_out (f->ctx, generation);
          {
            g_autoptr(GBytes) ack = d279_24_build_ack (0x50);
            g_autoptr(GBytes) nav = d279_24_build_nav ();
            goodix_post_tls_lifecycle_handle_a0 (post_tls, ack);
            goodix_post_tls_lifecycle_handle_a0 (post_tls, nav);
          }
        }
      else if (fdt_index == 1u)
        {
          d279_24_complete_out (f->ctx, generation);
          {
            g_autoptr(GBytes) ack = d279_24_build_ack (0x82);
            g_autoptr(GBytes) typed = d279_24_build_response (
              0x82, typed82_body, sizeof typed82_body);
            goodix_post_tls_lifecycle_handle_a0 (post_tls, ack);
            goodix_post_tls_lifecycle_handle_a0 (post_tls, typed);
          }
          d279_24_complete_out (f->ctx, generation);
          {
            g_autoptr(GBytes) ack = d279_24_build_ack (0x20);
            g_autoptr(GBytes) auxiliary = g_bytes_new_static (
              auxiliary_body, sizeof auxiliary_body);
            goodix_post_tls_lifecycle_handle_a0 (post_tls, ack);
            goodix_post_tls_lifecycle_handle_plaintext (post_tls, auxiliary);
          }
        }
    }
  d279_24_complete_out (f->ctx, generation);
  {
    g_autoptr(GBytes) ack = d279_24_build_ack (0x32);
    goodix_post_tls_lifecycle_handle_a0 (post_tls, ack);
  }

  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (post_tls), ==,
                   GOODIX_POST_TLS_PHASE_STOP);
  g_assert_cmpuint (post_audit.first_arm_handoff_count, ==, 1u);
  g_assert_cmpuint (post_audit.command_count, ==, 9u);
  g_assert_false (goodix_device_context_has_pending_enrollment_graph (f->ctx));
  g_assert_true (goodix_device_context_has_dormant_enrollment_binding (f->ctx));
  g_assert_cmpuint (auxiliary_count, ==, 0u);

  {
    g_autoptr(GBytes) irq = d279_20_build_irq2 ();
    gsize length;
    const guint8 *bytes = g_bytes_get_data (irq, &length);

    g_assert_true (goodix_device_context_arm_receive (f->ctx, &error));
    goodix_device_context_complete_receive (
      f->ctx, generation, bytes, length, NULL);
  }
  g_assert_cmpuint (binding_audit.graph_ready_submit_count, ==, 1u);
  g_assert_cmpuint (events_audit.irq2_count, ==, 1u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_outstanding (backend), ==,
                    1u);
  d279_24_complete_out (f->ctx, generation);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (backend), ==, 1u);
  g_assert_cmpint (goodix_fpi_usb_backend_get_receive_purpose (backend), ==,
                   GOODIX_USB_RECEIVE_PROTOCOL_RX);

  for (guint stage = 1u; stage <= 21u; stage++)
    {
      g_autoptr(GBytes) primary = d279_25_build_primary_plaintext (stage);
      const guint8 auxiliary_bytes[] = { 0x20, 0x01, 0x00, 0x88 };
      g_autoptr(GBytes) auxiliary = g_bytes_new_static (
        auxiliary_bytes, sizeof auxiliary_bytes);

      if (stage > 1u)
        {
          g_autoptr(GBytes) irq2 = d279_24_build_event (
            0x32, 0x0002, 0x003f, (guint16) (0x80u + stage * 8u));
          d279_25_feed_context_frame (f->ctx, generation, irq2);
          d279_25_complete_and_ack (f->ctx, generation, 0x22);
        }
      else
        {
          g_autoptr(GBytes) ack22 = d279_24_build_ack (0x22);
          d279_25_feed_context_frame (f->ctx, generation, ack22);
        }
      d279_25_feed_plaintext (f->ctx, generation, primary);
      d279_25_complete_and_ack (f->ctx, generation, 0x34);
      if (stage == 1u)
        {
          g_autoptr(GBytes) irq0200 = d279_24_build_event (
            0x34, 0x0200, 0x0000, 0x48);
          g_autoptr(GBytes) nav = d279_24_build_nav ();

          d279_25_feed_context_frame (f->ctx, generation, irq0200);
          d279_25_complete_and_ack (f->ctx, generation, 0x20);
          d279_25_feed_plaintext (f->ctx, generation, auxiliary);
          d279_25_complete_and_ack (f->ctx, generation, 0x32);
          d279_25_complete_and_ack (f->ctx, generation, 0x50);
          d279_25_feed_context_frame (f->ctx, generation, nav);
          d279_25_complete_and_ack (f->ctx, generation, 0x32);
        }
      else
        {
          g_autoptr(GBytes) irq0100 = d279_24_build_event (
            0x36, 0x0100, 0x0000, (guint16) (0x80u + stage * 8u));
          g_autoptr(GBytes) irq0200 = d279_24_build_event (
            0x34, 0x0200, 0x0000, (guint16) (0x40u + stage * 8u));

          d279_25_complete_and_ack (f->ctx, generation, 0x36);
          d279_25_feed_context_frame (f->ctx, generation, irq0100);
          d279_25_complete_and_ack (f->ctx, generation, 0x20);
          d279_25_feed_plaintext (f->ctx, generation, auxiliary);
          d279_25_complete_and_ack (f->ctx, generation, 0x34);
          d279_25_feed_context_frame (f->ctx, generation, irq0200);
          if (stage < 21u)
            d279_25_complete_and_ack (f->ctx, generation, 0x32);
        }
      {
        gint64 deadline = g_get_monotonic_time () + TEST_TIMEOUT_MS * 1000;

        while (f->enroll_progress_count < stage && !f->done &&
               g_get_monotonic_time () < deadline)
          g_main_context_iteration (NULL, FALSE);
        g_assert_cmpuint (f->enroll_progress_count, ==, stage);
        if (stage < 21u)
          g_assert_cmpint (f->last_state, ==,
                           FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);
      }
    }

  g_assert_true (events_audit.lifecycle.plan.pipeline.protocol.complete);
  g_assert_cmpuint (
    events_audit.lifecycle.plan.pipeline.protocol.configured_required_stage_count,
    ==, 21u);
  g_assert_cmpuint (events_audit.parsed_a0_count, ==, 188u);
  g_assert_cmpuint (events_audit.primary_b0_count, ==, 21u);
  g_assert_cmpuint (events_audit.auxiliary_b0_count, ==, 21u);
  g_assert_cmpuint (events_audit.lifecycle.plan.pipeline.fpimage_delivery_count,
                    ==, 21u);
  g_assert_cmpuint (events_audit.finger_down_delivery_count, ==, 21u);
  g_assert_cmpuint (events_audit.finger_up_delivery_count, ==, 21u);
  g_assert_cmpuint (events_audit.auxiliary_b0_delivery_count, ==, 21u);
  g_assert_cmpuint (auxiliary_count, ==, 21u);
  g_assert_cmpuint (binding_audit.graph_ready_submit_count, ==, 125u);
  g_assert_cmpuint (binding_audit.transaction.committed_after_completion_count,
                    ==, 125u);
  g_assert_cmpuint (binding_audit.retry_count, ==, 0u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (backend), ==, 0u);

  test_wait (f);
  g_assert_true (f->success);
  g_assert_nonnull (f->enroll_print);
  g_assert_cmpuint (f->completion_count, ==, 1u);
  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
  g_assert_cmpuint (binding_audit.cancellation_count, ==, 0u);
  g_assert_false (binding_audit.terminal);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (backend), ==,
                    0u);
  fixture_close (f);
  test_fixture_free (f);
  g_print ("D279_24_CONTEXT_FIRST_ARM_ENROLLMENT_HANDOFF=PASS\n");
  g_print ("D279_25_CONTEXT_21_STAGE_TRANSCRIPT=PASS\n");
  g_print ("D279_26_LIBFPRINT_21_STAGE_ACTION=PASS\n");
}

static void
test_d279_20_dormant_enrollment_context_ownership (void)
{
  GoodixEnrollmentModelConfig config = { 2u, TRUE };
  GoodixEnrollmentPostTlsEventsAudit events_audit;
  GoodixEnrollmentFpiUsbBindingAudit binding_audit;
  GoodixEnrollmentPostTlsEventsAudit foreign_events_audit;
  GoodixEnrollmentFpiUsbBindingAudit foreign_binding_audit;
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GError) error = NULL;
  g_autoptr(GError) cancelled = g_error_new_literal (
    G_IO_ERROR, G_IO_ERROR_CANCELLED, "synthetic context cancellation");
  g_autoptr(GBytes) irq = d279_20_build_irq2 ();
  GoodixFpImageDevice *device = goodix_fpimage_device_new ();
  GoodixDeviceContext *ctx = goodix_fpimage_device_get_context (device);
  GoodixFpiUsbBackend *backend =
    goodix_device_context_get_fpi_usb_backend (ctx);
  GoodixEnrollmentPostTlsEvents *events;
  GoodixEnrollmentFpiUsbBinding *binding;
  GoodixUsbRouter *foreign_router;
  GoodixFpiUsbBackend *foreign_backend;
  GoodixEnrollmentPostTlsEvents *foreign_events;
  GoodixEnrollmentFpiUsbBinding *foreign_binding;
  guint64 generation;

  goodix_device_context_set_async_usb_submit_seam (
    ctx, host_only_usb_submit, NULL);
  g_assert_true (goodix_device_context_begin_operator_epoch (
    ctx, cancellable, &error));
  generation = goodix_device_context_get_generation (ctx);

  foreign_router = goodix_usb_router_new (NULL, NULL, NULL);
  foreign_backend = goodix_fpi_usb_backend_new (
    NULL, foreign_router, 0x81, 0x01, 8192u);
  goodix_usb_router_begin_generation (foreign_router, generation);
  g_assert_true (goodix_fpi_usb_backend_begin_generation (
    foreign_backend, generation, cancellable, &error));
  foreign_events = goodix_enrollment_post_tls_events_new (
    &config, d279_20_image_ready, d279_20_timestamp_ready,
    d279_20_auxiliary_ready, NULL, &foreign_events_audit, &error);
  foreign_binding = goodix_enrollment_fpi_usb_binding_new (
    foreign_events, foreign_backend, generation, &foreign_binding_audit,
    &error);
  g_assert_nonnull (foreign_binding);
  g_assert_false (goodix_device_context_adopt_dormant_enrollment_binding (
    ctx, foreign_binding, &error));
  g_assert_error (error, G_IO_ERROR, G_IO_ERROR_CLOSED);
  g_clear_error (&error);
  g_assert_false (goodix_device_context_has_dormant_enrollment_binding (ctx));
  goodix_enrollment_fpi_usb_binding_free (foreign_binding);
  goodix_fpi_usb_backend_free (foreign_backend);
  goodix_usb_router_free (foreign_router);

  events = goodix_enrollment_post_tls_events_new (
    &config, d279_20_image_ready, d279_20_timestamp_ready,
    d279_20_auxiliary_ready, NULL, &events_audit, &error);
  g_assert_nonnull (events);
  binding = goodix_enrollment_fpi_usb_binding_new (
    events, backend, generation, &binding_audit, &error);
  g_assert_nonnull (binding);
  g_assert_true (goodix_device_context_adopt_dormant_enrollment_binding (
    ctx, binding, &error));
  g_assert_true (goodix_device_context_has_dormant_enrollment_binding (ctx));
  g_assert_true (goodix_enrollment_fpi_usb_binding_handle_a0 (
    binding, irq, &error));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_outstanding (backend), ==,
                    1u);

  goodix_device_context_stop_operator_epoch (ctx);
  g_assert_true (goodix_enrollment_fpi_usb_binding_is_failed (binding));
  g_assert_cmpuint (binding_audit.cancellation_count, ==, 1u);
  g_assert_false (goodix_device_context_operator_epoch_is_drained (ctx));
  g_assert_cmpuint (events_audit.lifecycle.plan.committed_command_count, ==,
                    0u);

  goodix_fpi_usb_backend_complete_out (backend, generation, cancelled);
  g_assert_true (goodix_device_context_operator_epoch_is_drained (ctx));
  g_assert_cmpuint (events_audit.lifecycle.plan.committed_command_count, ==,
                    0u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (backend), ==,
                    0u);

  g_object_unref (device);
  g_print ("D279_20_DORMANT_CONTEXT_OWNERSHIP=PASS\n");
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
  g_test_add_func ("/goodix-fpimage-device/d279-11-full-target-local-stage-policy",
                   test_d279_11_full_target_local_stage_policy);
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
  g_test_add_func ("/goodix-fpimage-device/d279-08-production-open-close-ownership",
                   test_d279_08_production_open_close_ownership);
  g_test_add_func ("/goodix-fpimage-device/d279-08-production-open-failures",
                   test_d279_08_production_open_failures);
  g_test_add_func ("/goodix-fpimage-device/d279-08-production-release-failure",
                   test_d279_08_production_release_failure);
  g_test_add_func ("/goodix-fpimage-device/d279-09-production-activation-binding",
                   test_d279_09_production_activation_binding);
  g_test_add_func ("/goodix-fpimage-device/d279-09-production-activation-sync-failure",
                   test_d279_09_production_activation_sync_failure);
  g_test_add_func ("/goodix-fpimage-device/d279-09-production-enrollment-rejected",
                   test_d279_09_production_enrollment_rejected_before_submit);
  g_test_add_func ("/goodix-fpimage-device/d279-20-dormant-enrollment-context-ownership",
                   test_d279_20_dormant_enrollment_context_ownership);
  g_test_add_func ("/goodix-fpimage-device/d279-24-context-first-arm-enrollment-handoff",
                   test_d279_24_context_first_arm_enrollment_handoff);

  return g_test_run ();
}
