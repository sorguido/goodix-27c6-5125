/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * D278/02 single-shot operator harness.  --self-test is synthetic and
 * hardware-free.  --material-preflight-only reads only the protected store
 * and inert canonical DLL.  --live-exact-secure-session is intentionally
 * compiled and fully wired, but execution requires separate procedural
 * authorization and is never invoked by host-only tests or CI.
 */
#include "goodix_d190_pe.h"
#include "goodix_d278_harness.h"
#include "goodix_target_material.h"

#include <openssl/crypto.h>
#include <string.h>

#ifdef D278_LIVE_BINDING
#include <gusb.h>
#include "fpi-device.h"
#endif

#define D278_VID 0x27c6u
#define D278_PID 0x5125u
#define D278_INTERFACE 0u

static const gchar *const manifest_path =
  "/var/lib/goodix-5125-poc/target-material-manifest.json";
static const gchar *const transport_path =
  "/var/lib/goodix-5125-poc/transport-material.bin";
static const gchar *const config90_path =
  "/var/lib/goodix-5125-poc/target-config-90.bin";

#ifdef D278_LIVE_BINDING
static void
record_host_failure (GoodixD278Telemetry *telemetry,
                     const gchar         *failure_class)
{
  g_strlcpy (telemetry->result, "fail", sizeof telemetry->result);
  if (g_str_equal (telemetry->failure_class, "none"))
    g_strlcpy (telemetry->failure_class, failure_class,
               sizeof telemetry->failure_class);
}
#endif

static gboolean
digest (const guint8 *data,
        gsize         length,
        guint8        output[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  gsize output_length = 32;

  if (length > G_MAXSSIZE)
    return FALSE;
  g_checksum_update (checksum, data, (gssize) length);
  g_checksum_get_digest (checksum, output, &output_length);
  return output_length == 32;
}

static gchar *
canonical_dll_path (void)
{
  g_autofree gchar *cwd = g_get_current_dir ();
  return g_canonicalize_filename (
    "analysis/D230/work/GoodixExport/gfusb.dll", cwd);
}

static GoodixTargetMaterial *
prepare_target_material (GoodixTargetMaterialAudit *audit,
                         GoodixSecureSessionMaterial *view,
                         GError                    **error)
{
  GoodixTargetMaterialPolicy policy;
  GoodixTargetMaterial *owner = NULL;
  g_autofree gchar *dll = canonical_dll_path ();
  guint8 seed_a[6] = { 0 };
  guint8 seed_b[6] = { 0 };

  goodix_target_material_policy_production (&policy);
  owner = goodix_target_material_load (manifest_path, transport_path,
                                       config90_path, &policy, audit, error);
  if (owner == NULL)
    goto out;
  if (!goodix_d190_pe_extract (dll, seed_a, seed_b, error) ||
      !goodix_target_material_bind (owner, seed_a, seed_b, error) ||
      !goodix_target_material_get_secure_session_material (owner, view, error))
    {
      goodix_target_material_free (owner);
      owner = NULL;
    }
out:
  goodix_d190_pe_cleanse_seed (seed_a);
  goodix_d190_pe_cleanse_seed (seed_b);
  return owner;
}

static void
set_config_finalizer (guint8 config[224])
{
  guint32 sum = 0;
  guint16 finalizer;

  for (guint i = 0; i < 111; i++)
    sum += (guint32) config[i * 2u] |
           ((guint32) config[i * 2u + 1u] << 8);
  finalizer = (guint16) (0u - 0xa5a5u - sum);
  config[222] = (guint8) finalizer;
  config[223] = (guint8) (finalizer >> 8);
}

static void
self_test_submit (GoodixD278Harness  *harness,
                  GoodixUsbDirection direction,
                  guint64            generation,
                  GBytes            *bytes,
                  gpointer           user_data)
{
  (void) harness;
  (void) direction;
  (void) generation;
  (void) bytes;
  (void) user_data;
}

static int
run_self_test (void)
{
  static const guint8 identity[] = "GF_ST411SEC_APP_12509";
  static const guint16 registers[4] = { 0x0220, 0x0236, 0x0238, 0x023a };
  static const guint offsets[4] = { 117, 121, 125, 129 };
  static const guint8 values[4][2] = {
    { 0xd8, 0x0b }, { 0xbe, 0x00 }, { 0xbd, 0x00 }, { 0xbc, 0x00 }
  };
  GoodixSecureSessionMaterial material = { 0 };
  GoodixD278Telemetry telemetry;
  g_autoptr(GError) error = NULL;
  GoodixD278Harness *harness = NULL;
  g_autofree gchar *terminal_json = NULL;
  guint8 psk[32] = { 0 };
  guint8 validator[32] = { 0 };
  guint8 config[224] = { 0 };
  guint8 a2[3] = { 1, 2, 3 };
  guint8 chip[4] = { 4, 5, 6, 7 };
  guint8 otp[64];
  guint64 serial;
  gboolean passed;

  for (guint i = 0; i < sizeof validator; i++)
    validator[i] = (guint8) (0x40u + i);
  for (guint i = 0; i < sizeof psk; i++)
    psk[i] = (guint8) (0x80u + i);
  for (guint i = 0; i < sizeof otp; i++)
    otp[i] = (guint8) (i * 3u + 1u);
  for (guint i = 0; i < 4; i++)
    {
      config[offsets[i]] = (guint8) registers[i];
      config[offsets[i] + 1u] = (guint8) (registers[i] >> 8);
      memcpy (config + offsets[i] + 2u, values[i], 2);
      memcpy (material.dac_values[i], values[i], 2);
    }
  set_config_finalizer (config);
  material.expected_identity = identity;
  material.expected_identity_length = sizeof identity;
  material.e4_validator = validator;
  material.e4_validator_length = sizeof validator;
  material.config90 = config;
  material.config90_length = sizeof config;
  material.psk = psk;
  material.psk_length = sizeof psk;
  digest (validator, sizeof validator, material.e4_validator_sha256);
  digest (a2, sizeof a2, material.a2_response_sha256);
  digest (chip, sizeof chip, material.chip82_response_sha256);
  digest (otp, sizeof otp, material.otp_a6_response_sha256);
  digest (config, sizeof config, material.config90_sha256);

  goodix_d278_telemetry_init (&telemetry, FALSE);
  telemetry.project_secret_zeroized = TRUE;
  harness = goodix_d278_harness_new (NULL, &material, TRUE, TRUE,
                                     self_test_submit, NULL, NULL,
                                     &telemetry, &error);
  if (harness == NULL || !goodix_d278_harness_start (harness, &error))
    {
      g_printerr ("D278/02 self-test composition failed\n");
      goodix_d278_harness_free (harness);
      return 1;
    }
  OPENSSL_cleanse (psk, sizeof psk);
  OPENSSL_cleanse (validator, sizeof validator);
  OPENSSL_cleanse (config, sizeof config);
  serial = goodix_d278_watchdog_get_serial (
    goodix_d278_harness_get_watchdog (harness));
  goodix_d278_watchdog_fire_for_test (
    goodix_d278_harness_get_watchdog (harness),
    goodix_d278_harness_get_generation (harness), serial);
  goodix_d278_harness_force_synthetic_drain (harness);
  goodix_d278_harness_seal (harness);
  terminal_json = goodix_d278_telemetry_to_json (harness, &telemetry);
  passed = telemetry.backend_drained && telemetry.terminal_cleanup_completed &&
           telemetry.real_usb_submit_count == 0 && telemetry.usb_open_count == 0 &&
           telemetry.usb_claim_count == 0 && telemetry.project_secret_zeroized &&
           g_str_has_prefix (telemetry.failure_class, "PHASE_TIMEOUT_A8");
  g_print ("{\"result\":\"%s\",\"self_test\":\"EXPECTED_A8_WATCHDOG_TERMINAL\","
           "\"real_usb_access\":0,\"real_usb_submit\":0,"
           "\"usb_open_count\":0,\"usb_claim_count\":0,"
           "\"current_live_authorized\":false,\"terminal_case\":%s}\n",
           passed ? "pass" : "fail", terminal_json);
  goodix_d278_harness_free (harness);
  return passed ? 0 : 1;
}

static int
run_material_preflight (void)
{
  GoodixTargetMaterialAudit audit;
  GoodixSecureSessionMaterial view = { 0 };
  GoodixD278Telemetry telemetry;
  g_autoptr(GError) error = NULL;
  GoodixTargetMaterial *owner;
  g_autofree gchar *json = NULL;
  gboolean match;

  goodix_d278_telemetry_init (&telemetry, FALSE);
  owner = prepare_target_material (&audit, &view, &error);
  match = owner != NULL && audit.e4_binding_match;
  goodix_target_material_free (owner);
  OPENSSL_cleanse (&view, sizeof view);
  g_strlcpy (telemetry.result, match ? "pass" : "fail",
             sizeof telemetry.result);
  if (!match)
    g_strlcpy (telemetry.failure_class,
               "PROTECTED_MATERIAL_PREFLIGHT_FAILED",
               sizeof telemetry.failure_class);
  telemetry.e4_binding_match = match;
  telemetry.project_secret_zeroized = audit.project_secret_zeroized;
  json = goodix_d278_boundary_telemetry_to_json (&telemetry);
  g_print ("%s\n", json);
  return match ? 0 : 1;
}

#ifdef D278_LIVE_BINDING
typedef struct _D278HarnessDevice D278HarnessDevice;
typedef struct _D278HarnessDeviceClass D278HarnessDeviceClass;
struct _D278HarnessDevice { FpDevice parent_instance; };
struct _D278HarnessDeviceClass { FpDeviceClass parent_class; };
GType d278_harness_device_get_type (void);

G_DEFINE_TYPE (D278HarnessDevice, d278_harness_device, FP_TYPE_DEVICE)

static const FpIdEntry d278_id_table[] = {
  { .vid = D278_VID, .pid = D278_PID },
  { .vid = 0, .pid = 0 }
};

static void
d278_harness_device_class_init (D278HarnessDeviceClass *klass)
{
  FpDeviceClass *device_class = FP_DEVICE_CLASS (klass);
  device_class->id = "d278_native_secure_session_harness_only";
  device_class->full_name = "D278 native secure-session harness-only binding";
  device_class->type = FP_DEVICE_TYPE_USB;
  device_class->id_table = d278_id_table;
  device_class->features = FP_DEVICE_FEATURE_CAPTURE;
  device_class->scan_type = FP_SCAN_TYPE_PRESS;
  device_class->temp_hot_seconds = -1;
}

static void
d278_harness_device_init (D278HarnessDevice *self)
{
  (void) self;
}

static int
run_live_once (void)
{
  GoodixTargetMaterialAudit material_audit;
  GoodixSecureSessionMaterial view = { 0 };
  GoodixD278Telemetry telemetry;
  g_autoptr(GError) error = NULL;
  g_autoptr(GUsbContext) usb_context = NULL;
  g_autoptr(GPtrArray) devices = NULL;
  g_autoptr(FpDevice) fp_device = NULL;
  GoodixTargetMaterial *owner = NULL;
  GoodixD278Harness *harness = NULL;
  GUsbDevice *target = NULL;
  g_autofree gchar *json = NULL;
  guint matches = 0;
  gboolean opened = FALSE;
  gboolean claimed = FALSE;
  int rc = 1;

  goodix_d278_telemetry_init (&telemetry, TRUE);
  owner = prepare_target_material (&material_audit, &view, &error);
  if (owner == NULL)
    {
      g_autofree gchar *boundary_json = NULL;
      telemetry.current_live_authorized = FALSE;
      record_host_failure (&telemetry,
                           "PROTECTED_MATERIAL_BEFORE_USB_OPEN");
      telemetry.project_secret_zeroized =
        material_audit.project_secret_zeroized;
      boundary_json = goodix_d278_boundary_telemetry_to_json (&telemetry);
      g_print ("%s\n", boundary_json);
      OPENSSL_cleanse (&view, sizeof view);
      return 1;
    }
  telemetry.e4_binding_match = material_audit.e4_binding_match;

  /* The target discovery/open boundary is unreachable until all protected
   * material, DLL, D190 and E4-pin gates above have passed. */
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
  if (matches != 1)
    goto cleanup;
  fp_device = g_object_new (d278_harness_device_get_type (),
                            "fpi-usb-device", target,
                            "fpi-driver-data", (guint64) 0, NULL);
  telemetry.live_authorization_consumed = TRUE;
  telemetry.usb_open_attempt_count = 1;
  if (!g_usb_device_open (target, &error))
    goto cleanup;
  opened = TRUE;
  telemetry.usb_open_count = 1;
  if (!g_usb_device_claim_interface (target, D278_INTERFACE,
                                      G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                      &error))
    goto cleanup;
  claimed = TRUE;
  telemetry.usb_claim_count = 1;
  harness = goodix_d278_harness_new (fp_device, &view, FALSE, FALSE,
                                     NULL, NULL, NULL, &telemetry, &error);
  if (harness == NULL || !goodix_d278_harness_start (harness, &error))
    {
      if (harness != NULL)
        {
          goodix_d278_harness_cancel (harness, "HARNESS_START_FAILED");
          goodix_d278_harness_run_main_loop (harness);
        }
      goto cleanup;
    }
  goodix_target_material_free (owner);
  owner = NULL;
  telemetry.project_secret_zeroized = material_audit.project_secret_zeroized;
  OPENSSL_cleanse (&view, sizeof view);
  goodix_d278_harness_run_main_loop (harness);

cleanup:
  if (owner != NULL)
    {
      goodix_target_material_free (owner);
      owner = NULL;
      telemetry.project_secret_zeroized = material_audit.project_secret_zeroized;
    }
  OPENSSL_cleanse (&view, sizeof view);
  if (harness != NULL && !goodix_fpi_usb_backend_is_drained (
        goodix_d278_harness_get_backend (harness)))
    {
      goodix_d278_harness_cancel (harness, "TERMINAL_CLEANUP");
      goodix_d278_harness_run_main_loop (harness);
    }
  if (claimed)
    {
      g_clear_error (&error);
      if (g_usb_device_release_interface (target, D278_INTERFACE,
                                           G_USB_DEVICE_CLAIM_INTERFACE_NONE,
                                           &error))
        telemetry.usb_release_count = 1;
      else
        record_host_failure (&telemetry, "USB_RELEASE_FAILED");
    }
  if (opened)
    {
      g_clear_error (&error);
      if (g_usb_device_close (target, &error))
        telemetry.usb_close_count = 1;
      else
        record_host_failure (&telemetry, "USB_CLOSE_FAILED");
    }
  telemetry.current_live_authorized = FALSE;
  if (harness != NULL)
    {
      goodix_d278_harness_seal (harness);
      json = goodix_d278_telemetry_to_json (harness, &telemetry);
      rc = g_str_equal (telemetry.result, "pass") &&
           telemetry.usb_release_count == 1 && telemetry.usb_close_count == 1 ?
           0 : 1;
      g_print ("%s\n", json);
      goodix_d278_harness_free (harness);
    }
  else
    {
      record_host_failure (&telemetry, "LIVE_HOST_BOUNDARY_FAILED");
      json = goodix_d278_boundary_telemetry_to_json (&telemetry);
      g_print ("%s\n", json);
    }
  return rc;
}
#endif

int
main (int argc, char **argv)
{
  if (argc == 2 && g_str_equal (argv[1], "--self-test"))
    return run_self_test ();
  if (argc == 2 && g_str_equal (argv[1], "--material-preflight-only"))
    return run_material_preflight ();
#ifdef D278_LIVE_BINDING
  if (argc == 2 && g_str_equal (argv[1], "--live-exact-secure-session"))
    return run_live_once ();
#endif
  g_printerr ("usage: %s --self-test | --material-preflight-only%s\n", argv[0],
#ifdef D278_LIVE_BINDING
              " | --live-exact-secure-session"
#else
              ""
#endif
              );
  return 2;
}
