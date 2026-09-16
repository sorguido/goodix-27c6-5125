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

  memset (transport, 0x5au, sizeof transport);
  memcpy (transport, "G5125POC", 8u);
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
  g_test_add_func ("/goodix/runtime-material/production-layout",
                   test_production_layout);
  return g_test_run ();
}
