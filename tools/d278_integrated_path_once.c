/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * D278/13 thin operator binding.  Protocol, TLS, FDT and image semantics stay
 * in the single GoodixDeviceContext-owned LGPL graph.  The ordinary build is
 * deliberately unapproved and exits before material or USB access.
 */
#include "goodix_d190_pe.h"
#include "goodix_fpimage_device.h"
#include "goodix_target_material.h"

#include <errno.h>
#include <fcntl.h>
#include <glib/gstdio.h>
#include <openssl/crypto.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef D278_13_LIVE_BINDING
#include <gusb.h>
#endif

#define D278_VID 0x27c6u
#define D278_PID 0x5125u
#define D278_INTERFACE 0u
#define D278_CACHE_SIZE 13520u
#define D278_CACHE_CRC_OFFSET 13516u
#define D278_CACHE_FDT_OFFSET 64u

#ifndef D278_13_APPROVED_BASELINE
#define D278_13_APPROVED_BASELINE "UNAPPROVED_FOR_LIVE"
#endif

#define D278_13_AUTHORIZATION_TOKEN \
  "D278_13_ONE_INTEGRATED_TWO_ACQUISITION_RUN_NO_RETRY"
#define D278_13_OPERATION_NAME "D278_13_INTEGRATED_PATH_ONCE"

static const gchar *const manifest_path =
  "/var/lib/goodix-5125-poc/target-material-manifest.json";
static const gchar *const transport_path =
  "/var/lib/goodix-5125-poc/transport-material.bin";
static const gchar *const config90_path =
  "/var/lib/goodix-5125-poc/target-config-90.bin";
static const gchar *const cache_relative_path =
  "captures/D255_20260822T205631772Z_85c8c41f/raw/cache_before/"
  "9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2.bin";
static const gchar *const cache_sha256 =
  "9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2";

static gboolean
is_full_sha (const gchar *value)
{
  if (value == NULL || strlen (value) != 40u)
    return FALSE;
  for (guint i = 0; i < 40u; i++)
    if (!g_ascii_isxdigit (value[i]))
      return FALSE;
  return TRUE;
}

static gboolean
live_authorization_gate (void)
{
  const gchar *runtime_sha =
    g_getenv ("D278_13_APPROVED_LIVE_BASELINE_SHA");
  const gchar *authorization =
    g_getenv ("D278_13_OPERATOR_AUTHORIZATION");
  const gchar *operation = g_getenv ("D278_13_OPERATION");

  if (!is_full_sha (D278_13_APPROVED_BASELINE) ||
      g_str_equal (D278_13_APPROVED_BASELINE, "UNAPPROVED_FOR_LIVE"))
    return FALSE;
  return is_full_sha (runtime_sha) && authorization != NULL &&
         operation != NULL &&
         g_str_equal (runtime_sha, D278_13_APPROVED_BASELINE) &&
         g_str_equal (authorization, D278_13_AUTHORIZATION_TOKEN) &&
         g_str_equal (operation, D278_13_OPERATION_NAME);
}

static gboolean
digest (const guint8 *data,
        gsize         length,
        guint8        output[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  gsize output_length = 32u;

  if (length > G_MAXSSIZE)
    return FALSE;
  g_checksum_update (checksum, data, (gssize) length);
  g_checksum_get_digest (checksum, output, &output_length);
  return output_length == 32u;
}

static guint32
crc32_mpeg2 (const guint8 *data,
             gsize         length)
{
  guint32 crc = 0xffffffffu;

  for (gsize i = 0; i < length; i++)
    {
      crc ^= (guint32) data[i] << 24;
      for (guint bit = 0; bit < 8u; bit++)
        crc = (crc & 0x80000000u) != 0u ?
          (crc << 1) ^ 0x04c11db7u : crc << 1;
    }
  return crc;
}

static gchar *
canonical_dll_path (void)
{
  g_autofree gchar *cwd = g_get_current_dir ();
  return g_canonicalize_filename (
    "analysis/D230/work/GoodixExport/gfusb.dll", cwd);
}

static GoodixTargetMaterial *
prepare_target_material (GoodixTargetMaterialAudit  *audit,
                         GoodixSecureSessionMaterial *view,
                         GError                     **error)
{
  GoodixTargetMaterialPolicy policy;
  GoodixD190PePolicy pe_policy;
  GoodixTargetMaterial *owner = NULL;
  g_autofree gchar *dll = canonical_dll_path ();
  guint8 seed_a[GOODIX_D190_PE_SEED_LENGTH] = { 0 };
  guint8 seed_b[GOODIX_D190_PE_SEED_LENGTH] = { 0 };

  goodix_target_material_policy_production (&policy);
  goodix_d190_pe_policy_production (&pe_policy);
  owner = goodix_target_material_load (manifest_path, transport_path,
                                       config90_path, &policy, audit, error);
  if (owner == NULL ||
      !goodix_d190_pe_extract_with_policy (dll, &pe_policy, seed_a, seed_b,
                                           error) ||
      !goodix_target_material_bind (owner, seed_a, seed_b, error) ||
      !goodix_target_material_get_secure_session_material (owner, view,
                                                            error))
    {
      goodix_target_material_free (owner);
      owner = NULL;
    }
  goodix_d190_pe_cleanse_seed (seed_a);
  goodix_d190_pe_cleanse_seed (seed_b);
  return owner;
}

static gboolean
read_exact (gint     fd,
            guint8  *data,
            gsize    length)
{
  gsize offset = 0;

  while (offset < length)
    {
      ssize_t got = read (fd, data + offset, length - offset);
      if (got < 0 && errno == EINTR)
        continue;
      if (got <= 0)
        return FALSE;
      offset += (gsize) got;
    }
  return TRUE;
}

static gboolean
load_canonical_fdt_seed (guint8    output[12],
                         GError  **error)
{
  GoodixTargetMaterialPolicy policy;
  g_autofree gchar *cwd = g_get_current_dir ();
  g_autofree gchar *path = g_canonicalize_filename (cache_relative_path, cwd);
  g_autofree gchar *actual_sha = NULL;
  g_autofree guint8 *cache = g_malloc0 (D278_CACHE_SIZE);
  guint8 otp_sha[32] = { 0 };
  struct stat st;
  gint fd = -1;
  guint32 stored_crc;
  gboolean seed_present = FALSE;
  gboolean ok = FALSE;

  fd = g_open (path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW, 0);
  if (fd < 0 || fstat (fd, &st) != 0 || !S_ISREG (st.st_mode) ||
      st.st_size != (off_t) D278_CACHE_SIZE ||
      !read_exact (fd, cache, D278_CACHE_SIZE))
    goto out;
  actual_sha = g_compute_checksum_for_data (G_CHECKSUM_SHA256, cache,
                                            D278_CACHE_SIZE);
  stored_crc = (guint32) cache[D278_CACHE_CRC_OFFSET] |
               ((guint32) cache[D278_CACHE_CRC_OFFSET + 1u] << 8) |
               ((guint32) cache[D278_CACHE_CRC_OFFSET + 2u] << 16) |
               ((guint32) cache[D278_CACHE_CRC_OFFSET + 3u] << 24);
  goodix_target_material_policy_production (&policy);
  if (!g_str_equal (actual_sha, cache_sha256) ||
      stored_crc != crc32_mpeg2 (cache, D278_CACHE_CRC_OFFSET) ||
      !digest (cache, 64u, otp_sha) ||
      CRYPTO_memcmp (otp_sha, policy.otp_a6_response_sha256, 32u) != 0)
    goto out;
  memcpy (output, cache + D278_CACHE_FDT_OFFSET, 12u);
  for (guint i = 0; i < 12u; i++)
    seed_present = seed_present || output[i] != 0;
  ok = seed_present;
out:
  if (fd >= 0)
    close (fd);
  OPENSSL_cleanse (otp_sha, sizeof otp_sha);
  OPENSSL_cleanse (cache, D278_CACHE_SIZE);
  if (!ok)
    g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                         "canonical FDT seed validation failed");
  return ok;
}

static int
run_gate_self_test (void)
{
  gboolean closed = !live_authorization_gate ();

  g_print ("EXECUTABLE_CLOSURE=%s\n", closed ? "PASS_HOST_ONLY" : "FAIL");
  g_print ("REAL_USB_ACCESS=false\nREAL_USB_SUBMIT=0\n");
  g_print ("REAL_PRODUCTION_SECRET_READ=false\n");
  g_print ("LIVE_EXECUTION_PERFORMED=false\n");
  g_print ("CURRENT_LIVE_AUTHORIZED=false\nREADY_FOR_LIVE=false\n");
  return closed ? 0 : 1;
}

#ifdef D278_13_LIVE_BINDING
typedef struct
{
  GoodixDeviceContext *ctx;
  GMainLoop *loop;
  GString *phase_trace;
  guint monitor_source;
  gint64 deadline_us;
  gboolean stopping;
  gboolean success;
  const gchar *failure_class;
} Runtime;

static void
observe_phase (GoodixSecurePhase phase,
               guint64           generation,
               gpointer          user_data)
{
  Runtime *runtime = user_data;

  (void) generation;
  if (runtime->phase_trace->len != 0)
    g_string_append_c (runtime->phase_trace, '>');
  g_string_append (runtime->phase_trace, goodix_secure_phase_name (phase));
}

static gboolean
monitor_runtime (gpointer user_data)
{
  Runtime *runtime = user_data;
  GoodixPostTlsLifecycle *post =
    goodix_device_context_get_post_tls_lifecycle (runtime->ctx);
  GoodixPostTlsPhase phase = goodix_post_tls_lifecycle_get_phase (post);

  if (!runtime->stopping && phase == GOODIX_POST_TLS_PHASE_STOP)
    {
      runtime->success = TRUE;
      runtime->stopping = TRUE;
      goodix_device_context_stop_operator_epoch (runtime->ctx);
    }
  else if (!runtime->stopping &&
           (phase == GOODIX_POST_TLS_PHASE_TERMINAL ||
            goodix_device_context_get_terminal_fence (runtime->ctx) ||
            g_get_monotonic_time () >= runtime->deadline_us))
    {
      runtime->failure_class = g_get_monotonic_time () >= runtime->deadline_us ?
        "ONE_SHOT_DEADLINE" : "INTEGRATED_PATH_TERMINAL";
      runtime->stopping = TRUE;
      goodix_device_context_stop_operator_epoch (runtime->ctx);
    }
  if (runtime->stopping &&
      goodix_device_context_operator_epoch_is_drained (runtime->ctx))
    {
      runtime->monitor_source = 0;
      g_main_loop_quit (runtime->loop);
      return G_SOURCE_REMOVE;
    }
  return G_SOURCE_CONTINUE;
}

static guint16
operator_timestamp (void)
{
  return (guint16) ((guint64) (g_get_monotonic_time () / 1000) & 0xffffu);
}

static gboolean
drain_after_stop (GoodixDeviceContext *ctx)
{
  gint64 deadline = g_get_monotonic_time () + 10 * G_TIME_SPAN_SECOND;

  while (!goodix_device_context_operator_epoch_is_drained (ctx) &&
         g_get_monotonic_time () < deadline)
    {
      while (g_main_context_iteration (NULL, FALSE))
        ;
      g_usleep (1000u);
    }
  return goodix_device_context_operator_epoch_is_drained (ctx);
}

static int
run_live_once (void)
{
  GoodixTargetMaterialAudit material_audit = { 0 };
  GoodixSecureSessionMaterial secure_material = { 0 };
  GoodixSecureSessionAudit secure_audit = { 0 };
  GoodixTlsAudit tls_audit = { 0 };
  GoodixPostTlsAudit post_audit = { 0 };
  GoodixPostTlsMaterial post_material = { 0 };
  g_autoptr(GError) error = NULL;
  g_autoptr(GUsbContext) usb_context = NULL;
  g_autoptr(GPtrArray) devices = NULL;
  g_autoptr(GCancellable) cancellable = NULL;
  g_autoptr(GoodixFpImageDevice) device = NULL;
  GoodixTargetMaterial *material_owner = NULL;
  GoodixFpiUsbBackend *backend = NULL;
  GUsbDevice *target = NULL;
  Runtime runtime = { 0 };
  guint matches = 0;
  guint open_count = 0;
  guint claim_count = 0;
  guint release_count = 0;
  guint close_count = 0;
  gboolean opened = FALSE;
  gboolean claimed = FALSE;
  gboolean epoch_started = FALSE;
  gboolean backend_drained = FALSE;
  gboolean project_secret_zeroized = FALSE;
  guint64 real_submit_count = 0;
  guint64 out_submit_count = 0;
  guint64 in_completion_count = 0;
  guint64 out_completion_count = 0;
  guint max_in_outstanding = 0;
  guint max_out_outstanding = 0;
  int rc = 1;

  runtime.failure_class = "PRE_BIND_FAILURE";
  if (!live_authorization_gate ())
    {
      g_printerr ("LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED\n");
      return 3;
    }

  material_owner = prepare_target_material (&material_audit,
                                             &secure_material, &error);
  if (material_owner == NULL ||
      !load_canonical_fdt_seed (post_material.initial_fdt_table, &error))
    goto cleanup;
  post_material.af_timestamp = operator_timestamp ();
  post_material.first_arm_timestamp = operator_timestamp ();
  post_material.second_arm_timestamp = operator_timestamp ();

  usb_context = g_usb_context_new (&error);
  if (usb_context == NULL || !g_usb_context_enumerate (usb_context, &error))
    goto cleanup;
  devices = g_usb_context_get_devices (usb_context);
  for (guint i = 0; i < devices->len; i++)
    {
      GUsbDevice *candidate = g_ptr_array_index (devices, i);
      if (g_usb_device_get_vid (candidate) == D278_VID &&
          g_usb_device_get_pid (candidate) == D278_PID)
        {
          target = candidate;
          matches++;
        }
    }
  if (matches != 1u)
    goto cleanup;
  open_count = 1u;
  if (!g_usb_device_open (target, &error))
    goto cleanup;
  opened = TRUE;
  if (!g_usb_device_claim_interface (target, D278_INTERFACE,
                                      G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                      &error))
    goto cleanup;
  claimed = TRUE;
  claim_count = 1u;

  device = goodix_fpimage_device_new_for_usb (target);
  runtime.ctx = goodix_fpimage_device_get_context (device);
  runtime.loop = g_main_loop_new (NULL, FALSE);
  runtime.phase_trace = g_string_new (NULL);
  runtime.failure_class = "NONE";
  runtime.deadline_us = g_get_monotonic_time () + 120 * G_TIME_SPAN_SECOND;
  cancellable = g_cancellable_new ();
  if (!goodix_device_context_begin_operator_epoch (runtime.ctx, cancellable,
                                                    &error))
    goto cleanup;
  epoch_started = TRUE;
  backend = goodix_device_context_get_fpi_usb_backend (runtime.ctx);
  goodix_device_context_set_secure_phase_observer (runtime.ctx,
                                                    observe_phase, &runtime);
  if (!goodix_device_context_configure_post_tls_lifecycle (
        runtime.ctx, &post_material, &post_audit, &error))
    goto cleanup;
  goodix_device_context_set_post_tls_await_finger_on (runtime.ctx, TRUE);
  if (!goodix_device_context_start_secure_session (
        runtime.ctx, &secure_material, NULL, NULL,
        &secure_audit, &tls_audit, &error))
    goto cleanup;
  goodix_target_material_free (material_owner);
  material_owner = NULL;
  OPENSSL_cleanse (&secure_material, sizeof secure_material);
  runtime.monitor_source = g_timeout_add (10u, monitor_runtime, &runtime);
  g_main_loop_run (runtime.loop);

cleanup:
  if (material_owner != NULL)
    goodix_target_material_free (material_owner);
  OPENSSL_cleanse (&secure_material, sizeof secure_material);
  if (epoch_started && !runtime.stopping)
    goodix_device_context_stop_operator_epoch (runtime.ctx);
  if (runtime.monitor_source != 0)
    g_source_remove (runtime.monitor_source);
  if (epoch_started && !drain_after_stop (runtime.ctx))
    runtime.failure_class = "BACKEND_DRAIN_TIMEOUT";
  if (claimed)
    {
      g_clear_error (&error);
      if (g_usb_device_release_interface (target, D278_INTERFACE,
                                           G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                           &error))
        release_count = 1u;
    }
  if (opened)
    {
      g_clear_error (&error);
      if (g_usb_device_close (target, &error))
        close_count = 1u;
    }
  if (backend != NULL)
    {
      backend_drained = goodix_fpi_usb_backend_is_drained (backend);
      real_submit_count = goodix_fpi_usb_backend_get_real_submit_count (backend);
      out_submit_count = goodix_fpi_usb_backend_get_out_submit_count (backend);
      in_completion_count =
        goodix_fpi_usb_backend_get_in_completion_count (backend);
      out_completion_count =
        goodix_fpi_usb_backend_get_out_completion_count (backend);
      max_in_outstanding = goodix_fpi_usb_backend_get_max_outstanding (backend);
      max_out_outstanding =
        goodix_fpi_usb_backend_get_max_out_outstanding (backend);
      rc = runtime.success && backend_drained &&
         post_audit.second_image_pipeline_count == 1u &&
         post_audit.third_cycle_command_count == 0u &&
         secure_audit.retry_count == 0u &&
         secure_audit.transport_reopen_count == 0u &&
         secure_audit.device_reset_count == 0u &&
         secure_audit.clear_halt_count == 0u &&
         secure_audit.persistent_write_count == 0u &&
         post_audit.retry_count == 0u && post_audit.reopen_count == 0u &&
         post_audit.device_reset_count == 0u &&
         post_audit.clear_halt_count == 0u &&
         post_audit.persistent_device_write_count == 0u &&
         release_count == 1u && close_count == 1u ? 0 : 1;
    }
  if (backend_drained)
    g_clear_object (&device);
  else if (device != NULL)
    (void) g_steal_pointer (&device);
  project_secret_zeroized = material_audit.project_secret_zeroized &&
    secure_audit.project_material_zeroized &&
    tls_audit.project_secret_zeroized;
  if (!project_secret_zeroized)
    rc = 1;
  g_print ("{\"result\":\"%s\",\"failure_class\":\"%s\","
           "\"phase_trace\":\"%s\","
           "\"live_authorization_consumed\":true,"
           "\"usb_open_attempt_count\":%u,"
           "\"usb_open_count\":%u,\"usb_claim_count\":%u,"
           "\"usb_release_count\":%u,\"usb_close_count\":%u,"
           "\"physical_submit_count\":%" G_GUINT64_FORMAT ","
           "\"physical_in_submit_count\":%" G_GUINT64_FORMAT ","
           "\"physical_out_submit_count\":%" G_GUINT64_FORMAT ","
           "\"physical_in_completion_count\":%" G_GUINT64_FORMAT ","
           "\"physical_out_completion_count\":%" G_GUINT64_FORMAT ","
           "\"max_outstanding_in\":%u,\"max_outstanding_out\":%u,"
           "\"secure_command_count\":%u,\"ack_count\":%u,"
           "\"typed_count\":%u,\"reentry_a2_result\":\"%s\","
           "\"a8_app12509_pin\":%s,\"e4_binding\":%s,"
           "\"tls_handshake_count\":%u,\"tls_established\":%s,"
           "\"secret_handoff_count\":%u,\"project_secret_zeroized\":%s,"
           "\"d4_count\":%u,\"af_count\":%u,"
           "\"fdt36_count\":%u,\"fdt_irq100_count\":%u,"
           "\"fresh_fdt_count\":%u,\"first_irq0002_count\":%u,"
           "\"first_0x22_count\":%u,\"first_b0_count\":%u,"
           "\"first_decode_count\":%u,"
           "\"first_image_pipeline_count\":%u,"
           "\"release_0x34_count\":%u,\"irq0200_count\":%u,"
           "\"post_up_0x20_count\":%u,\"post_up_b0_count\":%u,"
           "\"nav_0x50_count\":%u,\"nav_response_count\":%u,"
           "\"release_tail_complete_count\":%u,"
           "\"fresh_down_table_count\":%u,\"rearm_count\":%u,"
           "\"second_irq0002_count\":%u,\"second_0x22_count\":%u,"
           "\"second_b0_count\":%u,\"second_decode_count\":%u,"
           "\"second_image_pipeline_count\":%u,"
           "\"third_cycle_command_count\":%u,\"stop_reached\":%s,"
           "\"retry_count\":0,\"reopen_count\":0,"
           "\"device_reset_count\":0,\"clear_halt_count\":0,"
           "\"persistent_device_write_count\":0,"
           "\"backend_drained\":%s,\"cleanup_complete\":%s}\n",
           rc == 0 ? "pass" : "fail", runtime.failure_class,
           runtime.phase_trace != NULL ? runtime.phase_trace->str : "",
           open_count, opened ? 1u : 0u, claim_count, release_count,
           close_count,
           real_submit_count,
           real_submit_count >= out_submit_count ?
             real_submit_count - out_submit_count : 0u,
           out_submit_count, in_completion_count, out_completion_count,
           max_in_outstanding, max_out_outstanding,
           secure_audit.command_count, secure_audit.ack_count,
           secure_audit.typed_response_count,
           goodix_reentry_recovery_a2_result_class_name (
             secure_audit.reentry_recovery_a2_result_class),
           secure_audit.a8_app12509_pin_match ? "true" : "false",
           material_audit.e4_binding_match ? "true" : "false",
           tls_audit.handshake_count,
           secure_audit.tls_established ? "true" : "false",
           tls_audit.secret_handoff_count,
           project_secret_zeroized ? "true" : "false",
           post_audit.d4_count, post_audit.af_count,
           post_audit.fdt36_submit_count, post_audit.fdt_irq100_count,
           post_audit.fresh_fdt_count, post_audit.first_irq0002_count,
           post_audit.first_image_command_count,
           post_audit.first_image_b0_count,
           post_audit.first_image_decode_count,
           post_audit.first_image_pipeline_count,
           post_audit.release_0x34_count, post_audit.irq0200_count,
           post_audit.post_up_0x20_count, post_audit.post_up_b0_count,
           post_audit.nav_0x50_count, post_audit.nav_response_count,
           post_audit.release_tail_complete_count,
           post_audit.fresh_down_table_count,
           post_audit.rearm_0x32_count,
           post_audit.second_irq0002_count,
           post_audit.second_image_command_count,
           post_audit.second_b0_count,
           post_audit.second_image_decode_count,
           post_audit.second_image_pipeline_count,
           post_audit.third_cycle_command_count,
           runtime.success ? "true" : "false",
           backend_drained ? "true" : "false",
           backend_drained && project_secret_zeroized &&
             release_count == 1u && close_count == 1u ? "true" : "false");
  if (runtime.phase_trace != NULL)
    g_string_free (runtime.phase_trace, TRUE);
  if (runtime.loop != NULL)
    g_main_loop_unref (runtime.loop);
  return rc;
}
#endif

int
main (int argc, char **argv)
{
  if (argc == 2 && g_str_equal (argv[1], "--authorization-gate-self-test"))
    return run_gate_self_test ();
#ifdef D278_13_LIVE_BINDING
  if (argc == 2 && g_str_equal (argv[1], "--live-integrated-once"))
    return run_live_once ();
#endif
  g_printerr ("usage: %s --authorization-gate-self-test%s\n", argv[0],
#ifdef D278_13_LIVE_BINDING
              " | --live-integrated-once"
#else
              ""
#endif
              );
  return 2;
}
