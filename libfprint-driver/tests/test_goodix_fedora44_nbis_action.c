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
  FpPrint             *identify_match;
  FpPrint             *identify_print;
  FpPrint             *verify_print;
  gboolean             verify_match;
  guint                verify_match_count;
  guint                verify_no_match_count;
  guint                verify_retry_count;
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
identify_cb (FpDevice     *device,
             GAsyncResult *result,
             gpointer      user_data)
{
  SigfmFixture *fixture = user_data;

  fixture->success = fp_device_identify_finish (
    device, result, &fixture->identify_match, &fixture->identify_print,
    &fixture->error);
  fixture->completion_count++;
  fixture->done = TRUE;
  g_main_loop_quit (fixture->loop);
}

static void
verify_cb (FpDevice     *device,
           GAsyncResult *result,
           gpointer      user_data)
{
  SigfmFixture *fixture = user_data;

  fixture->success = fp_device_verify_finish (
    device, result, &fixture->verify_match, &fixture->verify_print,
    &fixture->error);
  fixture->completion_count++;
  fixture->done = TRUE;
  g_main_loop_quit (fixture->loop);
}

static void
verify_report_cb (FpDevice *device,
                  FpPrint  *match,
                  FpPrint  *print,
                  gpointer  user_data,
                  GError   *error)
{
  SigfmFixture *fixture = user_data;

  (void) device;
  (void) print;
  if (error != NULL)
    fixture->verify_retry_count++;
  else if (match != NULL)
    fixture->verify_match_count++;
  else
    fixture->verify_no_match_count++;
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
fill_distinct_structured_sigfm_samples (
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT])
{
  for (guint y = 0u; y < GOODIX_CANONICAL_IMAGE_HEIGHT; y++)
    for (guint x = 0u; x < GOODIX_CANONICAL_IMAGE_WIDTH; x++)
      {
        guint gx = x % 10u;
        guint gy = y % 6u;
        guint value = ((gx < 5u) != (gy < 3u)) ? 4095u : 0u;

        if (((x * 3u + y * 5u) % 7u) == 0u)
          value = 1536u;
        samples[y * GOODIX_CANONICAL_IMAGE_WIDTH + x] = (uint16_t) value;
      }
}

static void
test_true_sigfm_stage8_action (void)
{
  uint16_t baseline[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  uint16_t distinct_samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  g_autoptr(FpPrint) template = NULL;
  g_autoptr(FpPrint) restored = NULL;
  g_autoptr(FpPrint) invalid = NULL;
  g_autoptr(GPtrArray) gallery = NULL;
  g_autoptr(GVariant) stored_blob = NULL;
  g_autofree guchar *serialized = NULL;
  g_autofree guchar *corrupted = NULL;
  const guchar *stored_bytes;
  gsize serialized_size = 0u;
  gsize stored_size = 0u;
  GDate *enroll_date;
  SigfmFixture fixture = { 0 };

  fill_structured_sigfm_samples (samples);
  fill_distinct_structured_sigfm_samples (distinct_samples);
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
  fp_print_set_finger (template, FP_FINGER_RIGHT_INDEX);
  fp_print_set_username (template, "d280-01-offline");
  fp_print_set_description (template, "D280/01 synthetic SIGFM");
  enroll_date = g_date_new_dmy (10u, G_DATE_SEPTEMBER, 2026u);
  fp_print_set_enroll_date (template, enroll_date);
  g_date_free (enroll_date);
  fp_device_enroll (FP_DEVICE (fixture.device),
                    g_steal_pointer (&template), NULL,
                    progress_cb, &fixture, NULL,
                    (GAsyncReadyCallback) enroll_cb, &fixture);
  g_assert_cmpint (goodix_device_context_get_state (fixture.ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING);
  goodix_device_context_emit_arm_complete (fixture.ctx, NULL);
  g_assert_cmpint (fixture.last_state, ==,
                   FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);

  g_assert_cmpint (fp_device_get_nr_enroll_stages (
                     FP_DEVICE (fixture.device)), ==,
                   (gint) GOODIX_SIGFM_ENROLL_MAX_STAGES);

  for (guint stage = 1u; stage <= GOODIX_SIGFM_ENROLL_MAX_STAGES; stage++)
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

      if (stage < GOODIX_SIGFM_ENROLL_MAX_STAGES)
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
                    GOODIX_SIGFM_ENROLL_MAX_STAGES);
  g_assert_cmpint (goodix_device_context_get_state (fixture.ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);

  g_assert_true (fp_print_serialize (fixture.enroll_print, &serialized,
                                    &serialized_size, &fixture.error));
  g_assert_no_error (fixture.error);
  stored_blob = g_variant_ref_sink (g_variant_new_fixed_array (
    G_VARIANT_TYPE_BYTE, serialized, serialized_size, 1u));
  stored_bytes = g_variant_get_fixed_array (stored_blob, &stored_size, 1u);
  g_assert_cmpuint (stored_size, ==, serialized_size);

  /* D280/01 deliberately crosses the same close/open boundary required by
   * the production driver between enrollment and identify.  The only object
   * carried across epochs is the public serialized FP3 byte sequence. */
  fixture.done = FALSE;
  fixture.success = FALSE;
  fixture.completion_count = 0u;
  fp_device_close (FP_DEVICE (fixture.device), NULL,
                   (GAsyncReadyCallback) close_cb, &fixture);
  wait_until (&fixture, &fixture.done);
  g_assert_no_error (fixture.error);
  g_assert_true (fixture.success);
  g_assert_cmpuint (fixture.completion_count, ==, 1u);
  g_assert_null (goodix_fpimage_device_get_context (fixture.device));
  g_clear_object (&fixture.enroll_print);

  fixture.done = FALSE;
  fixture.success = FALSE;
  fixture.completion_count = 0u;
  fp_device_open (FP_DEVICE (fixture.device), NULL,
                  (GAsyncReadyCallback) open_cb, &fixture);
  wait_until (&fixture, &fixture.done);
  g_assert_no_error (fixture.error);
  g_assert_true (fixture.success);
  g_assert_cmpuint (fixture.completion_count, ==, 1u);
  fixture.ctx = goodix_fpimage_device_get_context (fixture.device);
  g_assert_nonnull (fixture.ctx);
  g_assert_cmpint (goodix_device_context_get_state (fixture.ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);

  restored = fp_print_deserialize (stored_bytes, stored_size, &fixture.error);
  g_assert_no_error (fixture.error);
  g_assert_nonnull (restored);
  g_assert_true (fp_print_compatible (restored,
                                     FP_DEVICE (fixture.device)));
  g_assert_cmpint (fp_print_get_finger (restored), ==,
                   FP_FINGER_RIGHT_INDEX);
  g_assert_cmpstr (fp_print_get_username (restored), ==,
                   "d280-01-offline");
  g_assert_cmpstr (fp_print_get_description (restored), ==,
                   "D280/01 synthetic SIGFM");
  g_assert_nonnull (fp_print_get_enroll_date (restored));
  g_assert_cmpuint (g_date_get_day (fp_print_get_enroll_date (restored)), ==,
                    10u);
  g_assert_cmpint (g_date_get_month (fp_print_get_enroll_date (restored)), ==,
                   G_DATE_SEPTEMBER);
  g_assert_cmpuint (g_date_get_year (fp_print_get_enroll_date (restored)), ==,
                    2026u);

  gallery = g_ptr_array_new_with_free_func (g_object_unref);
  g_ptr_array_add (gallery, g_object_ref (restored));
  fixture.done = FALSE;
  fixture.success = FALSE;
  fixture.completion_count = 0u;
  fp_device_identify (FP_DEVICE (fixture.device), gallery, NULL,
                      NULL, NULL, NULL,
                      (GAsyncReadyCallback) identify_cb, &fixture);
  g_assert_cmpint (goodix_device_context_get_state (fixture.ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING);
  goodix_device_context_emit_arm_complete (fixture.ctx, NULL);
  g_assert_cmpint (fixture.last_state, ==,
                   FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON);
  goodix_device_context_emit_finger_down (fixture.ctx);
  g_assert_cmpint (fixture.last_state, ==, FPI_IMAGE_DEVICE_STATE_CAPTURE);
  goodix_device_context_emit_sigfm_image_ready (
    fixture.ctx, baseline, samples, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
  goodix_device_context_emit_release_tail_complete (fixture.ctx);
  goodix_device_context_emit_finger_up_ready (fixture.ctx);
  wait_until (&fixture, &fixture.done);
  g_assert_no_error (fixture.error);
  g_assert_true (fixture.success);
  g_assert_cmpuint (fixture.completion_count, ==, 1u);
  g_assert_nonnull (fixture.identify_match);
  g_assert_nonnull (fixture.identify_print);
  g_assert_true (fp_print_equal (restored, fixture.identify_match));
  g_assert_cmpint (fpi_print_get_type (fixture.identify_print), ==,
                   FPI_PRINT_SIGFM);
  g_assert_cmpuint (fixture.identify_print->prints->len, ==, 1u);

  /* Fedora 1.94.100 FpImageDevice VERIFY uses the specific FP3 template,
   * SIGFM extraction and matcher-backed report/completion path. */
  fixture.done = FALSE;
  fixture.success = FALSE;
  fixture.completion_count = 0u;
  fp_device_verify (FP_DEVICE (fixture.device), restored, NULL,
                    verify_report_cb, &fixture, NULL,
                    (GAsyncReadyCallback) verify_cb, &fixture);
  goodix_device_context_emit_arm_complete (fixture.ctx, NULL);
  goodix_device_context_emit_finger_down (fixture.ctx);
  goodix_device_context_emit_sigfm_image_ready (
    fixture.ctx, baseline, samples, GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
  goodix_device_context_emit_release_tail_complete (fixture.ctx);
  goodix_device_context_emit_finger_up_ready (fixture.ctx);
  wait_until (&fixture, &fixture.done);
  g_assert_no_error (fixture.error);
  g_assert_true (fixture.success);
  g_assert_true (fixture.verify_match);
  g_assert_nonnull (fixture.verify_print);
  g_assert_cmpuint (fixture.verify_match_count, ==, 1u);
  g_assert_cmpuint (fixture.verify_no_match_count, ==, 0u);
  g_assert_cmpuint (fixture.verify_retry_count, ==, 0u);

  /* A second, structurally valid but distinct deterministic raster exercises
   * the real SIGFM no-match path; this is not biometric or FAR/FRR evidence. */
  fixture.done = FALSE;
  fixture.success = FALSE;
  fixture.completion_count = 0u;
  g_clear_object (&fixture.verify_print);
  fp_device_verify (FP_DEVICE (fixture.device), restored, NULL,
                    verify_report_cb, &fixture, NULL,
                    (GAsyncReadyCallback) verify_cb, &fixture);
  goodix_device_context_emit_arm_complete (fixture.ctx, NULL);
  goodix_device_context_emit_finger_down (fixture.ctx);
  goodix_device_context_emit_sigfm_image_ready (
    fixture.ctx, baseline, distinct_samples,
    GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT);
  goodix_device_context_emit_release_tail_complete (fixture.ctx);
  goodix_device_context_emit_finger_up_ready (fixture.ctx);
  wait_until (&fixture, &fixture.done);
  g_assert_no_error (fixture.error);
  g_assert_true (fixture.success);
  g_assert_false (fixture.verify_match);
  g_assert_nonnull (fixture.verify_print);
  g_assert_cmpuint (fixture.verify_match_count, ==, 1u);
  g_assert_cmpuint (fixture.verify_no_match_count, ==, 1u);
  g_assert_cmpuint (fixture.verify_retry_count, ==, 0u);

  corrupted = g_memdup2 (stored_bytes, stored_size);
  corrupted[0] = (guchar) 'X';
  invalid = fp_print_deserialize (corrupted, stored_size, &fixture.error);
  g_assert_null (invalid);
  g_assert_error (fixture.error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA);
  g_clear_error (&fixture.error);

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
  g_print ("D279_53_PUBLIC_FP3_STORAGE_ROUNDTRIP=PASS\n");
  g_print ("D279_53_TRUE_SIGFM_IDENTIFY_ACTION=PASS\n");
  g_print ("D279_55_PRODUCTION_IDENTIFY_ACTION_ENABLED=true\n");
  g_print ("D280_01_FP3_SURVIVES_CLOSE_REOPEN=PASS\n");
  g_print ("D280_01_TRUE_SIGFM_TWO_OPEN_EPOCH_REUSE=PASS\n");
  g_print ("D280_01_CORRUPT_FP3_REJECTED=PASS\n");
  g_print ("D280_01_TEMPLATE_PERSISTED_TO_DISK=false\n");
  g_print ("D282_01_FEDORA44_SIGFM_VERIFY_MATCH=PASS\n");
  g_print ("D282_01_FEDORA44_SIGFM_DISTINCT_TEMPLATE_NO_MATCH=PASS_SYNTHETIC\n");
  g_print ("D282_01_VERIFY_RETRY_CALLBACK_COUNT=%u\n",
           fixture.verify_retry_count);
  g_clear_object (&fixture.identify_match);
  g_clear_object (&fixture.identify_print);
  g_clear_object (&fixture.verify_print);
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
  g_test_add_func ("/goodix/d279-57-fedora44-native-sigfm-stage8-action",
                   test_true_sigfm_stage8_action);
  return g_test_run ();
}
