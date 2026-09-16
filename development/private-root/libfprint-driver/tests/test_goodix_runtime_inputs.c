/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_runtime_inputs.h"
#include "goodix_runtime_material.h"
#include "goodix_d190_binder.h"

#include <glib/gstdio.h>
#include <openssl/crypto.h>
#include <string.h>
#include <unistd.h>

#define SYNTHETIC_PE_LENGTH 1024u
#define SYNTHETIC_CACHE_LENGTH 128u
#define PRODUCTION_CACHE_LENGTH 13520u

static void
write_le16 (guint8 *bytes,
            guint16 value)
{
  bytes[0] = (guint8) value;
  bytes[1] = (guint8) (value >> 8);
}

static void
write_le32 (guint8 *bytes,
            guint32 value)
{
  bytes[0] = (guint8) value;
  bytes[1] = (guint8) (value >> 8);
  bytes[2] = (guint8) (value >> 16);
  bytes[3] = (guint8) (value >> 24);
}

static void
digest (const guint8 *bytes,
        gsize length,
        guint8 output[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  gsize output_length = 32u;

  g_checksum_update (checksum, bytes, (gssize) length);
  g_checksum_get_digest (checksum, output, &output_length);
  g_assert_cmpuint (output_length, ==, 32u);
}

static guint32
crc32_mpeg2 (const guint8 *bytes,
             gsize length)
{
  guint32 crc = 0xffffffffu;

  for (gsize i = 0; i < length; i++)
    {
      crc ^= (guint32) bytes[i] << 24;
      for (guint bit = 0; bit < 8u; bit++)
        crc = (crc & 0x80000000u) != 0u ?
          (crc << 1) ^ 0x04c11db7u : crc << 1;
    }
  return crc;
}

static void
build_pe (guint8 bytes[SYNTHETIC_PE_LENGTH],
          GoodixRuntimePePolicy *policy)
{
  static const guint8 first[6] = { 1u, 2u, 3u, 4u, 5u, 6u };
  static const guint8 instruction[14] = {
    0xc7u, 0x45u, 0x9fu, 0x11u, 0x22u, 0x33u, 0x44u,
    0xc7u, 0x45u, 0xa3u, 0x55u, 0x66u, 0x90u, 0x90u
  };
  const guint pe_offset = 0x80u;
  const guint section_offset = pe_offset + 24u;

  memset (bytes, 0, SYNTHETIC_PE_LENGTH);
  bytes[0] = 'M';
  bytes[1] = 'Z';
  write_le32 (bytes + 0x3cu, pe_offset);
  memcpy (bytes + pe_offset, "PE\0\0", 4u);
  write_le16 (bytes + pe_offset + 6u, 1u);
  write_le16 (bytes + pe_offset + 20u, 0u);
  write_le32 (bytes + section_offset + 8u, 0x200u);
  write_le32 (bytes + section_offset + 12u, 0x1000u);
  write_le32 (bytes + section_offset + 16u, 0x200u);
  write_le32 (bytes + section_offset + 20u, 0x200u);
  memcpy (bytes + 0x210u, first, sizeof first);
  memcpy (bytes + 0x230u, instruction, sizeof instruction);

  memset (policy, 0, sizeof *policy);
  policy->file_length = SYNTHETIC_PE_LENGTH;
  policy->first_seed_rva = 0x1010u;
  policy->second_instruction_rva = 0x1030u;
  digest (bytes, SYNTHETIC_PE_LENGTH, policy->expected_sha256);
}

static void
test_pe_extract_and_cleanse (void)
{
  guint8 bytes[SYNTHETIC_PE_LENGTH];
  GoodixRuntimePePolicy policy;
  guint8 seed_a[6] = { 0 };
  guint8 seed_b[6] = { 0 };
  g_autoptr(GError) error = NULL;
  static const guint8 expected_a[6] = { 1u, 2u, 3u, 4u, 5u, 6u };
  static const guint8 expected_b[6] = { 0x11u, 0x22u, 0x33u,
                                        0x44u, 0x55u, 0x66u };

  build_pe (bytes, &policy);
  g_assert_true (goodix_runtime_extract_producer_seeds (
    bytes, sizeof bytes, &policy, seed_a, seed_b, &error));
  g_assert_no_error (error);
  g_assert_cmpmem (seed_a, sizeof seed_a, expected_a, sizeof expected_a);
  g_assert_cmpmem (seed_b, sizeof seed_b, expected_b, sizeof expected_b);
  goodix_runtime_cleanse_producer_seed (seed_a);
  goodix_runtime_cleanse_producer_seed (seed_b);
  for (guint i = 0; i < 6u; i++)
    {
      g_assert_cmpuint (seed_a[i], ==, 0u);
      g_assert_cmpuint (seed_b[i], ==, 0u);
    }
}

static void
test_pe_fail_closed (void)
{
  guint8 bytes[SYNTHETIC_PE_LENGTH];
  GoodixRuntimePePolicy policy;
  guint8 seed_a[6] = { 0xa5u, 0xa5u, 0xa5u, 0xa5u, 0xa5u, 0xa5u };
  guint8 seed_b[6] = { 0xa5u, 0xa5u, 0xa5u, 0xa5u, 0xa5u, 0xa5u };
  g_autoptr(GError) error = NULL;

  build_pe (bytes, &policy);
  bytes[0x300u] ^= 1u;
  g_assert_false (goodix_runtime_extract_producer_seeds (
    bytes, sizeof bytes, &policy, seed_a, seed_b, &error));
  g_assert_cmpstr (goodix_runtime_inputs_error_class (error), ==,
                   "INPUT_HASH");
  for (guint i = 0; i < 6u; i++)
    {
      g_assert_cmpuint (seed_a[i], ==, 0u);
      g_assert_cmpuint (seed_b[i], ==, 0u);
    }

  g_clear_error (&error);
  build_pe (bytes, &policy);
  memcpy (bytes + 0x300u, bytes + 0x230u, 12u);
  digest (bytes, sizeof bytes, policy.expected_sha256);
  g_assert_false (goodix_runtime_extract_producer_seeds (
    bytes, sizeof bytes, &policy, seed_a, seed_b, &error));
  g_assert_cmpstr (goodix_runtime_inputs_error_class (error), ==,
                   "PE_PATTERN");
}

static void
build_cache (guint8 bytes[SYNTHETIC_CACHE_LENGTH],
             GoodixRuntimeFdtPolicy *policy)
{
  guint32 crc;

  memset (bytes, 0, SYNTHETIC_CACHE_LENGTH);
  for (guint i = 0; i < 64u; i++)
    bytes[i] = (guint8) (i + 1u);
  for (guint i = 0; i < 12u; i++)
    bytes[64u + i] = (guint8) (0x80u + i);
  for (guint i = 76u; i < 124u; i++)
    bytes[i] = (guint8) (i ^ 0x5au);
  crc = crc32_mpeg2 (bytes, 124u);
  write_le32 (bytes + 124u, crc);

  memset (policy, 0, sizeof *policy);
  policy->cache_length = SYNTHETIC_CACHE_LENGTH;
  policy->crc_offset = 124u;
  policy->otp_length = 64u;
  policy->fdt_offset = 64u;
  digest (bytes, SYNTHETIC_CACHE_LENGTH, policy->expected_sha256);
  digest (bytes, 64u, policy->expected_otp_sha256);
}

static void
test_fdt_extract (void)
{
  guint8 bytes[SYNTHETIC_CACHE_LENGTH];
  GoodixRuntimeFdtPolicy policy;
  guint8 seed[12] = { 0 };
  g_autoptr(GError) error = NULL;

  build_cache (bytes, &policy);
  g_assert_true (goodix_runtime_extract_fdt_seed (
    bytes, sizeof bytes, &policy, seed, &error));
  g_assert_no_error (error);
  for (guint i = 0; i < 12u; i++)
    g_assert_cmpuint (seed[i], ==, 0x80u + i);
}

static void
test_fdt_fail_closed (void)
{
  guint8 bytes[SYNTHETIC_CACHE_LENGTH];
  GoodixRuntimeFdtPolicy policy;
  guint8 seed[12];
  g_autoptr(GError) error = NULL;

  build_cache (bytes, &policy);
  bytes[124u] ^= 1u;
  digest (bytes, sizeof bytes, policy.expected_sha256);
  memset (seed, 0xa5, sizeof seed);
  g_assert_false (goodix_runtime_extract_fdt_seed (
    bytes, sizeof bytes, &policy, seed, &error));
  g_assert_cmpstr (goodix_runtime_inputs_error_class (error), ==,
                   "FDT_CACHE_CRC");
  for (guint i = 0; i < 12u; i++)
    g_assert_cmpuint (seed[i], ==, 0u);

  g_clear_error (&error);
  build_cache (bytes, &policy);
  policy.expected_otp_sha256[0] ^= 1u;
  g_assert_false (goodix_runtime_extract_fdt_seed (
    bytes, sizeof bytes, &policy, seed, &error));
  g_assert_cmpstr (goodix_runtime_inputs_error_class (error), ==,
                   "FDT_CACHE_OTP_BINDING");

  g_clear_error (&error);
  build_cache (bytes, &policy);
  memset (bytes + 64u, 0, 12u);
  write_le32 (bytes + 124u, crc32_mpeg2 (bytes, 124u));
  digest (bytes, sizeof bytes, policy.expected_sha256);
  g_assert_false (goodix_runtime_extract_fdt_seed (
    bytes, sizeof bytes, &policy, seed, &error));
  g_assert_cmpstr (goodix_runtime_inputs_error_class (error), ==,
                   "FDT_CACHE_SEED");
}

static void
test_production_policies (void)
{
  GoodixRuntimePePolicy pe;
  GoodixRuntimeFdtPolicy fdt;

  goodix_runtime_pe_policy_production (&pe);
  goodix_runtime_fdt_policy_production (&fdt);
  g_assert_cmpuint (pe.file_length, ==, 5771496u);
  g_assert_cmpuint (pe.first_seed_rva, ==, 0x56f030u);
  g_assert_cmpuint (pe.second_instruction_rva, ==, 0x69d0u);
  g_assert_cmpuint (fdt.cache_length, ==, 13520u);
  g_assert_cmpuint (fdt.crc_offset, ==, 13516u);
  g_assert_cmpuint (fdt.otp_length, ==, 64u);
  g_assert_cmpuint (fdt.fdt_offset, ==, 64u);
}

static void
write_private_fixture (const gchar *path,
                       const guint8 *bytes,
                       gsize length)
{
  g_autoptr(GError) error = NULL;

  g_assert_true (g_file_set_contents (path, (const gchar *) bytes,
                                      (gssize) length, &error));
  g_assert_no_error (error);
  g_assert_cmpint (g_chmod (path, 0600), ==, 0);
}

typedef struct
{
  guint count;
  gboolean all_zero;
} CleanseObservation;

static void
observe_input_cleanse (const guint8 *bytes,
                       gsize length,
                       gpointer user_data)
{
  CleanseObservation *observation = user_data;
  guint8 aggregate = 0;

  for (gsize i = 0; i < length; i++)
    aggregate |= bytes[i];
  observation->count++;
  observation->all_zero = observation->all_zero && aggregate == 0u;
}

static void
test_file_provider_roundtrip (void)
{
  guint8 pe[SYNTHETIC_PE_LENGTH];
  guint8 cache[SYNTHETIC_CACHE_LENGTH];
  GoodixRuntimePePolicy pe_policy;
  GoodixRuntimeFdtPolicy fdt_policy;
  GoodixRuntimeInputFilePolicy file_policy = { 0 };
  GoodixRuntimeInputFileAudit audit;
  CleanseObservation observation = { .all_zero = TRUE };
  guint8 seed_a[6] = { 0 };
  guint8 seed_b[6] = { 0 };
  guint8 fdt[12] = { 0 };
  g_autofree gchar *directory = NULL;
  g_autofree gchar *pe_path = NULL;
  g_autofree gchar *cache_path = NULL;
  g_autoptr(GError) error = NULL;

  build_pe (pe, &pe_policy);
  build_cache (cache, &fdt_policy);
  directory = g_dir_make_tmp ("goodix-runtime-inputs-test.XXXXXX", &error);
  g_assert_no_error (error);
  g_assert_nonnull (directory);
  pe_path = g_build_filename (directory, "synthetic-pe.bin", NULL);
  cache_path = g_build_filename (directory, "synthetic-cache.bin", NULL);
  write_private_fixture (pe_path, pe, sizeof pe);
  write_private_fixture (cache_path, cache, sizeof cache);
  file_policy.owner_uid = getuid ();
  file_policy.owner_gid = getgid ();
  file_policy.mode = 0600;
  file_policy.cleanse_observer = observe_input_cleanse;
  file_policy.cleanse_observer_data = &observation;

  g_assert_true (goodix_runtime_extract_inputs_from_files (
    pe_path, cache_path, &pe_policy, &fdt_policy, &file_policy,
    seed_a, seed_b, fdt, &audit, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (audit.open_count, ==, 2u);
  g_assert_cmpuint (audit.read_count, ==, 2u);
  g_assert_cmpuint (audit.buffer_allocation_count, ==, 2u);
  g_assert_cmpuint (audit.buffer_cleanse_count, ==, 2u);
  g_assert_true (audit.all_buffers_cleansed);
  g_assert_cmpuint (observation.count, ==, 2u);
  g_assert_true (observation.all_zero);
  g_assert_cmpuint (seed_a[0], ==, 1u);
  g_assert_cmpuint (seed_b[0], ==, 0x11u);
  g_assert_cmpuint (fdt[0], ==, 0x80u);

  file_policy.owner_gid = (gid_t) (getgid () + 1u);
  g_clear_error (&error);
  g_assert_false (goodix_runtime_extract_inputs_from_files (
    pe_path, cache_path, &pe_policy, &fdt_policy, &file_policy,
    seed_a, seed_b, fdt, &audit, &error));
  g_assert_cmpstr (goodix_runtime_inputs_error_class (error), ==,
                   "PRIVATE_INPUT_METADATA");
  g_assert_cmpuint (seed_a[0], ==, 0u);
  g_assert_cmpuint (seed_b[0], ==, 0u);
  g_assert_cmpuint (fdt[0], ==, 0u);

  g_assert_cmpint (g_remove (pe_path), ==, 0);
  g_assert_cmpint (g_remove (cache_path), ==, 0);
  g_assert_cmpint (g_rmdir (directory), ==, 0);
}

static void
change_mode_after_read (const gchar *path,
                        gint fd,
                        gpointer user_data)
{
  (void) path;
  (void) user_data;
  g_assert_cmpint (fchmod (fd, 0644), ==, 0);
}

static void
test_file_provider_changed_fail_closed (void)
{
  guint8 pe[SYNTHETIC_PE_LENGTH];
  guint8 cache[SYNTHETIC_CACHE_LENGTH];
  GoodixRuntimePePolicy pe_policy;
  GoodixRuntimeFdtPolicy fdt_policy;
  GoodixRuntimeInputFilePolicy file_policy = { 0 };
  GoodixRuntimeInputFileAudit audit;
  CleanseObservation observation = { .all_zero = TRUE };
  guint8 seed_a[6];
  guint8 seed_b[6];
  guint8 fdt[12];
  g_autofree gchar *directory = NULL;
  g_autofree gchar *pe_path = NULL;
  g_autofree gchar *cache_path = NULL;
  g_autoptr(GError) error = NULL;

  build_pe (pe, &pe_policy);
  build_cache (cache, &fdt_policy);
  directory = g_dir_make_tmp ("goodix-runtime-inputs-change.XXXXXX", &error);
  g_assert_no_error (error);
  pe_path = g_build_filename (directory, "synthetic-pe.bin", NULL);
  cache_path = g_build_filename (directory, "synthetic-cache.bin", NULL);
  write_private_fixture (pe_path, pe, sizeof pe);
  write_private_fixture (cache_path, cache, sizeof cache);
  file_policy.owner_uid = getuid ();
  file_policy.owner_gid = getgid ();
  file_policy.mode = 0600;
  file_policy.after_read = change_mode_after_read;
  file_policy.cleanse_observer = observe_input_cleanse;
  file_policy.cleanse_observer_data = &observation;
  memset (seed_a, 0xa5, sizeof seed_a);
  memset (seed_b, 0xa5, sizeof seed_b);
  memset (fdt, 0xa5, sizeof fdt);

  g_assert_false (goodix_runtime_extract_inputs_from_files (
    pe_path, cache_path, &pe_policy, &fdt_policy, &file_policy,
    seed_a, seed_b, fdt, &audit, &error));
  g_assert_cmpstr (goodix_runtime_inputs_error_class (error), ==,
                   "PRIVATE_INPUT_METADATA");
  g_assert_cmpuint (audit.open_count, ==, 1u);
  g_assert_cmpuint (audit.buffer_allocation_count, ==, 1u);
  g_assert_cmpuint (audit.buffer_cleanse_count, ==, 1u);
  g_assert_true (audit.all_buffers_cleansed);
  g_assert_cmpuint (observation.count, ==, 1u);
  g_assert_true (observation.all_zero);
  for (guint i = 0; i < 6u; i++)
    {
      g_assert_cmpuint (seed_a[i], ==, 0u);
      g_assert_cmpuint (seed_b[i], ==, 0u);
    }
  for (guint i = 0; i < 12u; i++)
    g_assert_cmpuint (fdt[i], ==, 0u);

  g_assert_cmpint (g_remove (pe_path), ==, 0);
  g_assert_cmpint (g_remove (cache_path), ==, 0);
  g_assert_cmpint (g_rmdir (directory), ==, 0);
}

static void
set_config_finalizer (guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH])
{
  guint32 sum = 0;
  guint16 finalizer;

  for (guint i = 0; i < 111u; i++)
    sum += (guint32) config[i * 2u] |
           ((guint32) config[i * 2u + 1u] << 8);
  finalizer = (guint16) (0u - 0xa5a5u - sum);
  config[222] = (guint8) finalizer;
  config[223] = (guint8) (finalizer >> 8);
}

static void
set_transport_header (guint8 transport[GOODIX_TARGET_TRANSPORT_LENGTH])
{
  memset (transport, 0, GOODIX_TARGET_TRANSPORT_LENGTH);
  memcpy (transport, "G5125POC", 8u);
  write_le16 (transport + 8u, 1u);
  write_le16 (transport + 10u, 24u);
  write_le16 (transport + 12u, 0x27c6u);
  write_le16 (transport + 14u, 0x5125u);
  write_le16 (transport + 16u, 1u);
  write_le16 (transport + 18u, 32u);
  write_le16 (transport + 20u, 32u);
  write_le16 (transport + 22u, 0u);
}

typedef struct
{
  gchar *directory;
  gchar *manifest_path;
  gchar *transport_path;
  gchar *config_path;
  gchar *pe_path;
  gchar *cache_path;
  gchar *manifest;
  GoodixRuntimeMaterialPolicy policy;
  GoodixRuntimeMaterialPaths paths;
  guint8 transport[GOODIX_TARGET_TRANSPORT_LENGTH];
  guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH];
  guint8 pe[SYNTHETIC_PE_LENGTH];
  guint8 cache[PRODUCTION_CACHE_LENGTH];
  guint8 a2[3];
  guint8 chip82[4];
} DynamicBundleFixture;

typedef struct
{
  guint8 transport_sha256[32];
  guint8 config90_sha256[32];
  guint8 cache_sha256[32];
  guint8 a2_sha256[32];
  guint8 chip82_sha256[32];
  guint8 otp_sha256[32];
  guint8 validator_sha256[32];
  guint8 dac_values[4][2];
  guint8 config90_finalizer[2];
} DynamicBundleSummary;

static gchar *
sha256_string (const guint8 *bytes,
               gsize length)
{
  return g_compute_checksum_for_data (G_CHECKSUM_SHA256, bytes, length);
}

static gchar *
build_dynamic_manifest (const DynamicBundleFixture *fixture)
{
  g_autofree gchar *transport = sha256_string (
    fixture->transport, sizeof fixture->transport);
  g_autofree gchar *config = sha256_string (
    fixture->config, sizeof fixture->config);
  g_autofree gchar *cache = sha256_string (
    fixture->cache, sizeof fixture->cache);
  g_autofree gchar *a2 = sha256_string (fixture->a2, sizeof fixture->a2);
  g_autofree gchar *chip82 = sha256_string (
    fixture->chip82, sizeof fixture->chip82);
  g_autofree gchar *otp = sha256_string (fixture->cache, 64u);

  return g_strdup_printf (
    "{\"schema\":\"goodix-5125-device-materials-v1\","
    "\"vid\":\"27c6\",\"pid\":\"5125\","
    "\"app\":\"GF_ST411SEC_APP_12509\","
    "\"transport_sha256\":\"%s\",\"config90_sha256\":\"%s\","
    "\"fdt_cache_sha256\":\"%s\",\"a2_response_sha256\":\"%s\","
    "\"chip82_response_sha256\":\"%s\","
    "\"otp_a6_response_sha256\":\"%s\"}\n",
    transport, config, cache, a2, chip82, otp);
}

static void
dynamic_bundle_init (DynamicBundleFixture *fixture,
                     guint variant)
{
  static const guint8 seed_a[6] = { 1u, 2u, 3u, 4u, 5u, 6u };
  static const guint8 seed_b[6] = { 0x11u, 0x22u, 0x33u,
                                    0x44u, 0x55u, 0x66u };
  guint8 validator[32] = { 0 };
  g_autoptr(GError) error = NULL;

  memset (fixture, 0, sizeof *fixture);
  goodix_runtime_material_policy_production (&fixture->policy);
  build_pe (fixture->pe, &fixture->policy.pe);
  fixture->policy.private_files.owner_uid = getuid ();
  fixture->policy.private_files.owner_gid = getgid ();
  fixture->policy.target.owner_uid = getuid ();
  fixture->policy.target.owner_gid = getgid ();
  fixture->policy.directory_owner_uid = getuid ();
  fixture->policy.directory_owner_gid = getgid ();
  g_assert_cmpuint (fixture->policy.target.manifest_length, ==, 0u);

  set_transport_header (fixture->transport);
  for (guint i = 0; i < 32u; i++)
    fixture->transport[24u + i] = (guint8) (variant * 41u + i * 3u + 1u);
  g_assert_true (goodix_d190_bind_validator (
    fixture->transport + 24u, 32u, seed_a, sizeof seed_a,
    seed_b, sizeof seed_b, validator, &error));
  g_assert_no_error (error);
  memcpy (fixture->transport + 56u, validator, sizeof validator);

  for (guint i = 0; i < 222u; i++)
    fixture->config[i] = (guint8) (variant * 29u + i * 7u + 3u);
  for (guint i = 0; i < 4u; i++)
    {
      guint offset = fixture->policy.target.dac_offsets[i];
      guint16 reg = fixture->policy.target.dac_registers[i];
      fixture->config[offset] = (guint8) reg;
      fixture->config[offset + 1u] = (guint8) (reg >> 8);
      fixture->config[offset + 2u] = (guint8) (variant * 17u + i * 2u + 1u);
      fixture->config[offset + 3u] = (guint8) (variant * 19u + i * 3u + 2u);
    }
  set_config_finalizer (fixture->config);

  for (guint i = 0; i < sizeof fixture->cache - 4u; i++)
    fixture->cache[i] = (guint8) (variant * 23u + i * 5u + 7u);
  for (guint i = 0; i < 12u; i++)
    fixture->cache[64u + i] = (guint8) (variant * 31u + i + 1u);
  write_le32 (fixture->cache + sizeof fixture->cache - 4u,
              crc32_mpeg2 (fixture->cache, sizeof fixture->cache - 4u));
  fixture->a2[0] = (guint8) (variant + 1u);
  fixture->a2[1] = (guint8) (variant + 11u);
  fixture->a2[2] = (guint8) (variant + 21u);
  for (guint i = 0; i < sizeof fixture->chip82; i++)
    fixture->chip82[i] = (guint8) (variant * 13u + i + 1u);
  fixture->manifest = build_dynamic_manifest (fixture);

  fixture->directory = g_dir_make_tmp ("goodix-dynamic-bundle.XXXXXX", &error);
  g_assert_no_error (error);
  fixture->manifest_path = g_build_filename (
    fixture->directory, "target-material-manifest.json", NULL);
  fixture->transport_path = g_build_filename (
    fixture->directory, "transport-material.bin", NULL);
  fixture->config_path = g_build_filename (
    fixture->directory, "target-config-90.bin", NULL);
  fixture->pe_path = g_build_filename (fixture->directory, "gfusb.dll", NULL);
  fixture->cache_path = g_build_filename (
    fixture->directory, "fdt-cache.bin", NULL);
  write_private_fixture (fixture->manifest_path,
                         (const guint8 *) fixture->manifest,
                         strlen (fixture->manifest));
  write_private_fixture (fixture->transport_path, fixture->transport,
                         sizeof fixture->transport);
  write_private_fixture (fixture->config_path, fixture->config,
                         sizeof fixture->config);
  write_private_fixture (fixture->pe_path, fixture->pe, sizeof fixture->pe);
  write_private_fixture (fixture->cache_path, fixture->cache,
                         sizeof fixture->cache);
  fixture->paths = (GoodixRuntimeMaterialPaths) {
    .directory_path = fixture->directory,
    .manifest_path = fixture->manifest_path,
    .transport_path = fixture->transport_path,
    .config90_path = fixture->config_path,
    .pe_path = fixture->pe_path,
    .fdt_cache_path = fixture->cache_path,
  };
  OPENSSL_cleanse (validator, sizeof validator);
}

static void
dynamic_bundle_clear (DynamicBundleFixture *fixture)
{
  g_remove (fixture->manifest_path);
  g_remove (fixture->transport_path);
  g_remove (fixture->config_path);
  g_remove (fixture->pe_path);
  g_remove (fixture->cache_path);
  g_rmdir (fixture->directory);
  g_free (fixture->manifest_path);
  g_free (fixture->transport_path);
  g_free (fixture->config_path);
  g_free (fixture->pe_path);
  g_free (fixture->cache_path);
  g_free (fixture->directory);
  g_free (fixture->manifest);
  OPENSSL_cleanse (fixture, sizeof *fixture);
}

static void
load_dynamic_bundle (DynamicBundleFixture *fixture,
                     DynamicBundleSummary *summary)
{
  GoodixRuntimeMaterialAudit audit;
  GoodixSecureSessionMaterial view;
  GoodixRuntimeMaterial *owner;
  guint8 fdt[GOODIX_RUNTIME_FDT_SEED_LENGTH] = { 0 };
  g_autoptr(GError) error = NULL;

  owner = goodix_runtime_material_load (&fixture->paths, &fixture->policy,
                                        &audit, &error);
  g_assert_no_error (error);
  g_assert_nonnull (owner);
  g_assert_true (goodix_runtime_material_get_secure_view (owner, &view, &error));
  g_assert_no_error (error);
  g_assert_true (goodix_runtime_material_get_fdt_seed (owner, fdt, &error));
  g_assert_no_error (error);
  g_assert_cmpmem (fdt, sizeof fdt, fixture->cache + 64u, sizeof fdt);
  g_assert_true (audit.target.e4_binding_match);
  digest (fixture->transport, sizeof fixture->transport,
          summary->transport_sha256);
  digest (fixture->config, sizeof fixture->config, summary->config90_sha256);
  digest (fixture->cache, sizeof fixture->cache, summary->cache_sha256);
  memcpy (summary->a2_sha256, view.a2_response_sha256, 32u);
  memcpy (summary->chip82_sha256, view.chip82_response_sha256, 32u);
  memcpy (summary->otp_sha256, view.otp_a6_response_sha256, 32u);
  memcpy (summary->validator_sha256, view.e4_validator_sha256, 32u);
  memcpy (summary->dac_values, view.dac_values, sizeof summary->dac_values);
  memcpy (summary->config90_finalizer, fixture->config + 222u, 2u);
  goodix_runtime_material_free (owner);
}

static void
test_runtime_material_device_dynamic_bundles (void)
{
  DynamicBundleFixture first;
  DynamicBundleFixture second;
  DynamicBundleSummary first_summary = { 0 };
  DynamicBundleSummary second_summary = { 0 };

  dynamic_bundle_init (&first, 1u);
  dynamic_bundle_init (&second, 2u);
  load_dynamic_bundle (&first, &first_summary);
  load_dynamic_bundle (&second, &second_summary);
  g_assert_true (memcmp (first_summary.transport_sha256,
                         second_summary.transport_sha256, 32u) != 0);
  g_assert_true (memcmp (first_summary.config90_sha256,
                         second_summary.config90_sha256, 32u) != 0);
  g_assert_true (memcmp (first_summary.cache_sha256,
                         second_summary.cache_sha256, 32u) != 0);
  g_assert_true (memcmp (first_summary.a2_sha256,
                         second_summary.a2_sha256, 32u) != 0);
  g_assert_true (memcmp (first_summary.chip82_sha256,
                         second_summary.chip82_sha256, 32u) != 0);
  g_assert_true (memcmp (first_summary.otp_sha256,
                         second_summary.otp_sha256, 32u) != 0);
  g_assert_true (memcmp (first_summary.validator_sha256,
                         second_summary.validator_sha256, 32u) != 0);
  g_assert_true (memcmp (first_summary.dac_values,
                         second_summary.dac_values,
                         sizeof first_summary.dac_values) != 0);
  g_assert_true (memcmp (first_summary.config90_finalizer,
                         second_summary.config90_finalizer, 2u) != 0);
  dynamic_bundle_clear (&first);
  dynamic_bundle_clear (&second);
}

typedef enum
{
  MANIFEST_MISSING_OPEN,
  MANIFEST_MISSING_CLOSE,
  MANIFEST_MISSING_COMMA,
  MANIFEST_MISSING_COLON,
  MANIFEST_NON_JSON_WHITESPACE,
  MANIFEST_DUPLICATE_KEY,
  MANIFEST_UNKNOWN_KEY,
  MANIFEST_MISSING_KEY,
  MANIFEST_NON_HEX_DIGEST,
  MANIFEST_SHORT_DIGEST,
  MANIFEST_WRONG_SCHEMA,
  MANIFEST_WRONG_VID,
  MANIFEST_WRONG_PID,
  MANIFEST_WRONG_APP,
  MANIFEST_EMBEDDED_NUL,
  MANIFEST_TRAILING_GARBAGE,
  MANIFEST_OVERSIZED,
} ManifestMutation;

static GBytes *
mutated_manifest (const gchar *valid,
                  ManifestMutation mutation)
{
  GString *text = g_string_new (valid);
  gchar *found;
  gchar *result;
  gsize result_length;

  switch (mutation)
    {
    case MANIFEST_MISSING_OPEN:
      g_string_erase (text, 0, 1);
      break;
    case MANIFEST_MISSING_CLOSE:
      found = strrchr (text->str, '}');
      g_assert_nonnull (found);
      g_string_erase (text, (gssize) (found - text->str), 1);
      break;
    case MANIFEST_MISSING_COMMA:
      found = strchr (text->str, ',');
      g_assert_nonnull (found);
      *found = ' ';
      break;
    case MANIFEST_MISSING_COLON:
      found = strchr (text->str, ':');
      g_assert_nonnull (found);
      *found = ' ';
      break;
    case MANIFEST_NON_JSON_WHITESPACE:
      g_string_insert_c (text, 1, '\v');
      break;
    case MANIFEST_DUPLICATE_KEY:
      found = strrchr (text->str, '}');
      g_assert_nonnull (found);
      g_string_insert (text, (gssize) (found - text->str),
                       ",\"vid\":\"27c6\"");
      break;
    case MANIFEST_UNKNOWN_KEY:
      found = strrchr (text->str, '}');
      g_assert_nonnull (found);
      g_string_insert (text, (gssize) (found - text->str),
                       ",\"unrecognized\":\"value\"");
      break;
    case MANIFEST_MISSING_KEY:
      found = strstr (text->str, "\"app\":\"GF_ST411SEC_APP_12509\",");
      g_assert_nonnull (found);
      g_string_erase (text, (gssize) (found - text->str),
                      (gssize) strlen ("\"app\":\"GF_ST411SEC_APP_12509\","));
      break;
    case MANIFEST_NON_HEX_DIGEST:
      found = strstr (text->str, "\"transport_sha256\":\"");
      g_assert_nonnull (found);
      found += strlen ("\"transport_sha256\":\"");
      *found = 'z';
      break;
    case MANIFEST_SHORT_DIGEST:
      found = strstr (text->str, "\"transport_sha256\":\"");
      g_assert_nonnull (found);
      found += strlen ("\"transport_sha256\":\"");
      g_string_erase (text, (gssize) (found - text->str), 1);
      break;
    case MANIFEST_WRONG_SCHEMA:
      found = strstr (text->str, "goodix-5125-device-materials-v1");
      g_assert_nonnull (found);
      found[0] = 'x';
      break;
    case MANIFEST_WRONG_VID:
      found = strstr (text->str, "\"vid\":\"27c6\"");
      g_assert_nonnull (found);
      found[strlen ("\"vid\":\"")] = '3';
      break;
    case MANIFEST_WRONG_PID:
      found = strstr (text->str, "\"pid\":\"5125\"");
      g_assert_nonnull (found);
      found[strlen ("\"pid\":\"")] = '6';
      break;
    case MANIFEST_WRONG_APP:
      found = strstr (text->str, "GF_ST411SEC_APP_12509");
      g_assert_nonnull (found);
      found[0] = 'X';
      break;
    case MANIFEST_EMBEDDED_NUL:
      found = strstr (text->str, "GF_ST411SEC_APP_12509");
      g_assert_nonnull (found);
      *found = '\0';
      break;
    case MANIFEST_TRAILING_GARBAGE:
      g_string_append (text, "garbage");
      break;
    case MANIFEST_OVERSIZED:
      g_string_set_size (text, GOODIX_TARGET_MANIFEST_MAX_LENGTH + 1u);
      memset (text->str, 'x', text->len);
      break;
    }
  result_length = text->len;
  result = g_string_free (text, FALSE);
  return g_bytes_new_take (result, result_length);
}

static void
test_manifest_mutation_rejected (gconstpointer user_data)
{
  DynamicBundleFixture fixture;
  g_autoptr(GBytes) bytes = NULL;
  g_autoptr(GError) error = NULL;
  gsize length;
  const guint8 *data;

  dynamic_bundle_init (&fixture, 3u);
  bytes = mutated_manifest (fixture.manifest,
                            (ManifestMutation) GPOINTER_TO_UINT (user_data));
  data = g_bytes_get_data (bytes, &length);
  write_private_fixture (fixture.manifest_path, data, length);
  g_assert_null (goodix_target_material_load (
    fixture.manifest_path, fixture.transport_path, fixture.config_path,
    &fixture.policy.target, NULL, &error));
  g_assert_nonnull (error);
  dynamic_bundle_clear (&fixture);
}

static void
observe_target_cleanse (const gchar *label,
                        const guint8 *bytes,
                        gsize length,
                        gpointer user_data)
{
  (void) label;
  observe_input_cleanse (bytes, length, user_data);
}

static void
test_runtime_material_owner (void)
{
  static const guint8 seed_a[6] = { 1u, 2u, 3u, 4u, 5u, 6u };
  static const guint8 seed_b[6] = { 0x11u, 0x22u, 0x33u,
                                    0x44u, 0x55u, 0x66u };
  static const gchar manifest[] = "synthetic runtime material manifest";
  guint8 pe[SYNTHETIC_PE_LENGTH];
  guint8 cache[SYNTHETIC_CACHE_LENGTH];
  guint8 transport[GOODIX_TARGET_TRANSPORT_LENGTH];
  guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH];
  guint8 validator[32] = { 0 };
  guint8 fdt[GOODIX_RUNTIME_FDT_SEED_LENGTH] = { 0 };
  GoodixRuntimeMaterialPolicy policy;
  GoodixRuntimeMaterialPaths paths;
  GoodixRuntimeMaterialPaths invalid_paths;
  GoodixRuntimeMaterialAudit audit;
  GoodixSecureSessionMaterial view;
  GoodixRuntimeMaterial *owner = NULL;
  CleanseObservation input_observation = { .all_zero = TRUE };
  CleanseObservation target_observation = { .all_zero = TRUE };
  g_autofree gchar *directory = NULL;
  g_autofree gchar *manifest_path = NULL;
  g_autofree gchar *transport_path = NULL;
  g_autofree gchar *config_path = NULL;
  g_autofree gchar *pe_path = NULL;
  g_autofree gchar *cache_path = NULL;
  g_autoptr(GError) error = NULL;

  goodix_runtime_material_policy_production (&policy);
  build_pe (pe, &policy.pe);
  build_cache (cache, &policy.fdt);
  policy.private_files.owner_uid = getuid ();
  policy.private_files.owner_gid = getgid ();
  policy.private_files.cleanse_observer = observe_input_cleanse;
  policy.private_files.cleanse_observer_data = &input_observation;
  policy.target.owner_uid = getuid ();
  policy.target.owner_gid = getgid ();
  policy.directory_owner_uid = getuid ();
  policy.directory_owner_gid = getgid ();
  policy.target.manifest_length = sizeof manifest - 1u;
  policy.target.cleanse_observer = observe_target_cleanse;
  policy.target.cleanse_observer_data = &target_observation;

  set_transport_header (transport);
  memset (transport + 24u, 0x3cu, 32u);
  memset (config, 0, sizeof config);
  for (guint i = 0; i < 4u; i++)
    {
      guint offset = policy.target.dac_offsets[i];
      guint16 reg = policy.target.dac_registers[i];
      config[offset] = (guint8) reg;
      config[offset + 1u] = (guint8) (reg >> 8);
      memcpy (config + offset + 2u, policy.target.dac_values[i], 2u);
    }
  set_config_finalizer (config);
  memcpy (policy.target.config90_finalizer, config + 222u, 2u);
  digest ((const guint8 *) manifest, sizeof manifest - 1u,
          policy.target.manifest_sha256);
  digest (transport, sizeof transport, policy.target.transport_sha256);
  digest (config, sizeof config, policy.target.config90_sha256);
  g_assert_true (goodix_d190_bind_validator (
    transport + 24u, 32u, seed_a, sizeof seed_a, seed_b, sizeof seed_b,
    validator, &error));
  g_assert_no_error (error);
  memcpy (transport + 56u, validator, 32u);
  digest (transport, sizeof transport, policy.target.transport_sha256);
  digest (validator, sizeof validator, policy.target.e4_validator_sha256);

  directory = g_dir_make_tmp ("goodix-runtime-owner.XXXXXX", &error);
  g_assert_no_error (error);
  manifest_path = g_build_filename (directory, "manifest", NULL);
  transport_path = g_build_filename (directory, "transport", NULL);
  config_path = g_build_filename (directory, "config", NULL);
  pe_path = g_build_filename (directory, "pe", NULL);
  cache_path = g_build_filename (directory, "cache", NULL);
  write_private_fixture (manifest_path, (const guint8 *) manifest,
                         sizeof manifest - 1u);
  write_private_fixture (transport_path, transport, sizeof transport);
  write_private_fixture (config_path, config, sizeof config);
  write_private_fixture (pe_path, pe, sizeof pe);
  write_private_fixture (cache_path, cache, sizeof cache);
  paths = (GoodixRuntimeMaterialPaths) {
    .directory_path = directory,
    .manifest_path = manifest_path,
    .transport_path = transport_path,
    .config90_path = config_path,
    .pe_path = pe_path,
    .fdt_cache_path = cache_path,
  };

  owner = goodix_runtime_material_load (&paths, &policy, &audit, &error);
  g_assert_no_error (error);
  g_assert_nonnull (owner);
  g_assert_true (goodix_runtime_material_get_secure_view (owner, &view,
                                                          &error));
  g_assert_no_error (error);
  g_assert_true (goodix_runtime_material_get_fdt_seed (owner, fdt, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (view.psk_length, ==, 32u);
  g_assert_cmpuint (view.config90_length, ==,
                    GOODIX_SECURE_SESSION_CONFIG90_LENGTH);
  g_assert_cmpuint (view.psk[0], ==, 0x3cu);
  g_assert_cmpuint (fdt[0], ==, 0x80u);
  g_assert_true (audit.target.e4_binding_match);
  g_assert_cmpuint (audit.directory_open_count, ==, 1u);
  g_assert_true (audit.directory_verified);
  g_assert_true (audit.private_files.all_buffers_cleansed);
  g_assert_true (input_observation.all_zero);
  g_assert_true (audit.producer_seeds_cleansed);
  memset (&view, 0, sizeof view);
  memset (fdt, 0, sizeof fdt);
  goodix_runtime_material_free (owner);
  g_assert_cmpuint (audit.owner_free_count, ==, 1u);
  g_assert_cmpuint (audit.target.owner_free_count, ==, 1u);
  g_assert_true (audit.target.project_secret_zeroized);
  g_assert_true (audit.descriptor_cleansed);
  g_assert_true (audit.fdt_seed_cleansed);
  g_assert_true (target_observation.all_zero);

  invalid_paths = paths;
  invalid_paths.pe_path = "/tmp/not-a-direct-layout-child";
  g_clear_error (&error);
  g_assert_null (goodix_runtime_material_load (&invalid_paths, &policy, &audit,
                                               &error));
  g_assert_nonnull (error);
  g_assert_cmpuint (audit.directory_open_count, ==, 0u);

  g_assert_cmpint (g_remove (manifest_path), ==, 0);
  g_assert_cmpint (g_remove (transport_path), ==, 0);
  g_assert_cmpint (g_remove (config_path), ==, 0);
  g_assert_cmpint (g_remove (pe_path), ==, 0);
  g_assert_cmpint (g_remove (cache_path), ==, 0);
  g_assert_cmpint (g_rmdir (directory), ==, 0);
  OPENSSL_cleanse (transport, sizeof transport);
  OPENSSL_cleanse (config, sizeof config);
  OPENSSL_cleanse (validator, sizeof validator);
}

static void
test_production_layout (void)
{
  GoodixRuntimeMaterialPaths paths;
  GoodixRuntimeMaterialPolicy policy;

  goodix_runtime_material_paths_production (&paths);
  goodix_runtime_material_policy_production (&policy);
  g_assert_cmpstr (paths.directory_path, ==, "/var/lib/goodix-5125-poc");
  g_assert_cmpstr (paths.manifest_path, ==,
                   "/var/lib/goodix-5125-poc/target-material-manifest.json");
  g_assert_cmpstr (paths.transport_path, ==,
                   "/var/lib/goodix-5125-poc/transport-material.bin");
  g_assert_cmpstr (paths.config90_path, ==,
                   "/var/lib/goodix-5125-poc/target-config-90.bin");
  g_assert_cmpstr (paths.pe_path, ==,
                   "/var/lib/goodix-5125-poc/gfusb.dll");
  g_assert_cmpstr (paths.fdt_cache_path, ==,
                   "/var/lib/goodix-5125-poc/fdt-cache.bin");
  g_assert_cmpuint (policy.directory_owner_uid, ==, 0u);
  g_assert_cmpuint (policy.directory_owner_gid, ==, 0u);
  g_assert_cmpuint (policy.directory_mode, ==, 0700u);
  g_assert_cmpuint (policy.target.owner_uid, ==, 0u);
  g_assert_cmpuint (policy.target.owner_gid, ==, 0u);
  g_assert_cmpuint (policy.target.mode, ==, 0600u);
  g_assert_cmpuint (policy.private_files.owner_uid, ==, 0u);
  g_assert_cmpuint (policy.private_files.owner_gid, ==, 0u);
  g_assert_cmpuint (policy.private_files.mode, ==, 0600u);
}

int
main (int argc, char **argv)
{
  static const gchar *const manifest_mutation_names[] = {
    "missing-open", "missing-close", "missing-comma", "missing-colon",
    "non-json-whitespace", "duplicate-key", "unknown-key", "missing-key",
    "non-hex-digest", "short-digest", "wrong-schema", "wrong-vid",
    "wrong-pid", "wrong-app", "embedded-nul", "trailing-garbage",
    "oversized",
  };

  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/goodix/runtime-inputs/pe-extract-cleanse",
                   test_pe_extract_and_cleanse);
  g_test_add_func ("/goodix/runtime-inputs/pe-fail-closed",
                   test_pe_fail_closed);
  g_test_add_func ("/goodix/runtime-inputs/fdt-extract", test_fdt_extract);
  g_test_add_func ("/goodix/runtime-inputs/fdt-fail-closed",
                   test_fdt_fail_closed);
  g_test_add_func ("/goodix/runtime-inputs/production-policies",
                   test_production_policies);
  g_test_add_func ("/goodix/runtime-inputs/file-roundtrip",
                   test_file_provider_roundtrip);
  g_test_add_func ("/goodix/runtime-inputs/file-changed-fail-closed",
                   test_file_provider_changed_fail_closed);
  g_test_add_func ("/goodix/runtime-material/owner-composition",
                   test_runtime_material_owner);
  g_test_add_func ("/goodix/runtime-material/device-dynamic-bundles",
                   test_runtime_material_device_dynamic_bundles);
  for (guint i = 0; i < G_N_ELEMENTS (manifest_mutation_names); i++)
    {
      g_autofree gchar *path = g_strdup_printf (
        "/goodix/runtime-material/manifest-rejects/%s",
        manifest_mutation_names[i]);
      g_test_add_data_func (path, GUINT_TO_POINTER (i),
                            test_manifest_mutation_rejected);
    }
  g_test_add_func ("/goodix/runtime-material/production-layout",
                   test_production_layout);
  return g_test_run ();
}
