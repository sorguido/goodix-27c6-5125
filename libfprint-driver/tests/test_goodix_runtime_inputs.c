/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_runtime_inputs.h"

#include <string.h>

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
  g_assert_cmpuint (pe.first_seed_rva, ==, 0x56f030u);
  g_assert_cmpuint (pe.second_instruction_rva, ==, 0x69d0u);
  g_assert_cmpuint (fdt.cache_length, ==, 13520u);
  g_assert_cmpuint (fdt.crc_offset, ==, 13516u);
  g_assert_cmpuint (fdt.otp_length, ==, 64u);
  g_assert_cmpuint (fdt.fdt_offset, ==, 64u);
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
  return g_test_run ();
}
