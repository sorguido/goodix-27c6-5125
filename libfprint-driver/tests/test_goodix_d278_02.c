/* SPDX-License-Identifier: GPL-2.0-or-later */
/* D278/02 host-only tests.  All protected material is synthetic. */
#include "goodix_a0_protocol.h"
#include "goodix_d190_binder.h"
#include "goodix_d190_pe.h"
#include "goodix_d278_harness.h"
#include "goodix_target_material.h"

#include <errno.h>
#include <fcntl.h>
#include <openssl/crypto.h>
#include <openssl/ssl.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include <glib/gstdio.h>

#define CANONICAL_DLL "analysis/D230/work/GoodixExport/gfusb.dll"

/* ASSERT_CMPMEM in some GLib versions stores lengths in int, which trips
 * -Wsign-conversion under -Wconversion.  Use a size_t-safe local wrapper. */
#define ASSERT_CMPMEM(m1, l1, m2, l2) G_STMT_START { \
  gconstpointer __m1 = (m1), __m2 = (m2); \
  gsize __l1 = (l1), __l2 = (l2); \
  g_assert_cmpuint (__l1, ==, __l2); \
  if (__l1 != 0) \
    g_assert_true (memcmp (__m1, __m2, __l1) == 0); \
} G_STMT_END

typedef struct
{
  gchar *directory;
  gchar *manifest;
  gchar *transport;
  gchar *config;
  gchar *symlink_target;
  GoodixTargetMaterialPolicy policy;
  GoodixTargetMaterialAudit audit;
  guint8 transport_bytes[GOODIX_TARGET_TRANSPORT_LENGTH];
  guint8 config_bytes[GOODIX_SECURE_SESSION_CONFIG90_LENGTH];
  guint8 expected_validator[32];
  gboolean manifest_is_directory;
  gboolean cleanse_all_zero;
  guint cleanse_observation_count;
} MaterialFixture;

static void
digest (const guint8 *data,
        gsize         length,
        guint8        output[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  gsize output_length = 32;

  g_assert_cmpuint (length, <=, G_MAXSSIZE);
  g_checksum_update (checksum, data, (gssize) length);
  g_checksum_get_digest (checksum, output, &output_length);
  g_assert_cmpuint (output_length, ==, 32);
}

static void
decode_hex (const gchar *hex,
            guint8      *output,
            gsize        output_length)
{
  g_assert_cmpuint (strlen (hex), ==, output_length * 2u);
  for (gsize i = 0; i < output_length; i++)
    {
      gchar pair[3] = { hex[i * 2u], hex[i * 2u + 1u], 0 };
      output[i] = (guint8) g_ascii_strtoull (pair, NULL, 16);
    }
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
write_mode600 (const gchar  *path,
               const guint8 *bytes,
               gsize         length)
{
  g_assert_true (g_file_set_contents (path, (const gchar *) bytes,
                                      (gssize) length, NULL));
  g_assert_cmpint (g_chmod (path, 0600), ==, 0);
}

static void
cleanse_observer (const gchar  *label,
                  const guint8 *bytes,
                  gsize         length,
                  gpointer      user_data)
{
  MaterialFixture *fixture = user_data;
  guint8 aggregate = 0;

  g_assert_nonnull (label);
  for (gsize i = 0; i < length; i++)
    aggregate |= bytes[i];
  fixture->cleanse_all_zero &= aggregate == 0;
  fixture->cleanse_observation_count++;
}

static void
material_fixture_init (MaterialFixture *fixture)
{
  static const gchar manifest_text[] =
    "D278/02 synthetic pinned manifest: no target material";
  static const gchar validator_v0[] =
    "b5e0beeb94c84eb99b883abd5c251073c56b91035c562a91a46c7f3349c36c89";

  memset (fixture, 0, sizeof *fixture);
  fixture->cleanse_all_zero = TRUE;
  fixture->directory = g_dir_make_tmp ("goodix-d278-02-material-XXXXXX", NULL);
  g_assert_nonnull (fixture->directory);
  fixture->manifest = g_build_filename (fixture->directory, "manifest.json", NULL);
  fixture->transport = g_build_filename (fixture->directory, "transport.bin", NULL);
  fixture->config = g_build_filename (fixture->directory, "config90.bin", NULL);
  fixture->symlink_target = g_build_filename (fixture->directory, "target.bin", NULL);

  goodix_target_material_policy_production (&fixture->policy);
  fixture->policy.owner_uid = getuid ();
  fixture->policy.manifest_length = sizeof manifest_text - 1u;
  fixture->policy.cleanse_observer = cleanse_observer;
  fixture->policy.cleanse_observer_data = fixture;

  memset (fixture->transport_bytes, 0x5a, sizeof fixture->transport_bytes);
  memcpy (fixture->transport_bytes, "G5125POC", 8);
  memset (fixture->transport_bytes + 24, 0, 32); /* synthetic KAT V0 PSK */
  memset (fixture->config_bytes, 0, sizeof fixture->config_bytes);
  for (guint i = 0; i < 4; i++)
    {
      guint offset = fixture->policy.dac_offsets[i];
      guint16 reg = fixture->policy.dac_registers[i];
      fixture->config_bytes[offset] = (guint8) reg;
      fixture->config_bytes[offset + 1u] = (guint8) (reg >> 8);
      memcpy (fixture->config_bytes + offset + 2u,
              fixture->policy.dac_values[i], 2);
    }
  set_config_finalizer (fixture->config_bytes);
  memcpy (fixture->policy.config90_finalizer,
          fixture->config_bytes + 222, 2);
  decode_hex (validator_v0, fixture->expected_validator,
              sizeof fixture->expected_validator);
  digest ((const guint8 *) manifest_text, sizeof manifest_text - 1u,
          fixture->policy.manifest_sha256);
  digest (fixture->transport_bytes, sizeof fixture->transport_bytes,
          fixture->policy.transport_sha256);
  digest (fixture->config_bytes, sizeof fixture->config_bytes,
          fixture->policy.config90_sha256);
  digest (fixture->expected_validator, sizeof fixture->expected_validator,
          fixture->policy.e4_validator_sha256);

  write_mode600 (fixture->manifest, (const guint8 *) manifest_text,
                 sizeof manifest_text - 1u);
  write_mode600 (fixture->transport, fixture->transport_bytes,
                 sizeof fixture->transport_bytes);
  write_mode600 (fixture->config, fixture->config_bytes,
                 sizeof fixture->config_bytes);
}

static void
material_fixture_clear (MaterialFixture *fixture)
{
  g_remove (fixture->manifest);
  if (fixture->manifest_is_directory)
    g_rmdir (fixture->manifest);
  g_remove (fixture->transport);
  g_remove (fixture->config);
  g_remove (fixture->symlink_target);
  g_rmdir (fixture->directory);
  g_free (fixture->manifest);
  g_free (fixture->transport);
  g_free (fixture->config);
  g_free (fixture->symlink_target);
  g_free (fixture->directory);
  OPENSSL_cleanse (fixture, sizeof *fixture);
}

static GoodixTargetMaterial *
load_fixture (MaterialFixture            *fixture,
              GoodixSecureSessionMaterial *view,
              gboolean                    bind,
              GError                    **error)
{
  GoodixTargetMaterial *owner;
  guint8 seed_a[6] = { 0 };
  guint8 seed_b[6] = { 0 };

  owner = goodix_target_material_load (fixture->manifest, fixture->transport,
                                       fixture->config, &fixture->policy,
                                       &fixture->audit, error);
  if (owner == NULL || !bind)
    return owner;
  if (!goodix_d190_pe_extract (CANONICAL_DLL, seed_a, seed_b, error) ||
      !goodix_target_material_bind (owner, seed_a, seed_b, error) ||
      (view != NULL &&
       !goodix_target_material_get_secure_session_material (owner, view, error)))
    {
      goodix_target_material_free (owner);
      owner = NULL;
    }
  goodix_d190_pe_cleanse_seed (seed_a);
  goodix_d190_pe_cleanse_seed (seed_b);
  return owner;
}

static void
test_binder_kat (gconstpointer user_data)
{
  static const gchar *const expected[] = {
    "b5e0beeb94c84eb99b883abd5c251073c56b91035c562a91a46c7f3349c36c89",
    "e51d069d67065a052307d3bd6dd8edf377e8b2389dc309475891e415e5f2148c",
    "d1ba9a4790f8d47ba8b50043d72b577cdc2d1b701d466197aa741a94fd0f1ec4",
    "ea43b0f9a2eae84d55fa9b0a961c35b7dd8e5c2594e5e4562c92c3f198a19209",
    "af13a21ec8f8250b47da268f32ef74cd0ff5dbc0f8b48b93ee5411e422e8a9b4"
  };
  guint index = GPOINTER_TO_UINT (user_data);
  guint8 secrets[5][32] = { { 0 } };
  guint8 wanted[32];
  guint8 actual[32];
  guint8 seed_a[6] = { 0 };
  guint8 seed_b[6] = { 0 };
  g_autoptr(GError) error = NULL;

  memset (secrets[1], 1, 32);
  for (guint i = 0; i < 32; i++)
    secrets[2][i] = (guint8) i;
  for (guint i = 0; i < 32; i++)
    secrets[3][i] = (i % 2u) == 0 ? 0xaa : 0x55;
  decode_hex ("31dc314296631fa52db5a09e625f74d43f5420455a214272ab444f84393e8d5a",
              secrets[4], 32);
  decode_hex (expected[index], wanted, 32);
  g_assert_true (goodix_d190_pe_extract (CANONICAL_DLL, seed_a, seed_b,
                                         &error));
  g_assert_no_error (error);
  g_assert_true (goodix_d190_bind_validator (secrets[index], 32,
                                             seed_a, 6, seed_b, 6,
                                             actual, &error));
  g_assert_no_error (error);
  ASSERT_CMPMEM (actual, (gsize) 32, wanted, (gsize) 32);
  goodix_d190_pe_cleanse_seed (seed_a);
  goodix_d190_pe_cleanse_seed (seed_b);
  OPENSSL_cleanse (secrets, sizeof secrets);
  OPENSSL_cleanse (wanted, sizeof wanted);
  OPENSSL_cleanse (actual, sizeof actual);
}

static void
test_binder_argument_validation (void)
{
  guint8 secret[32] = { 0 };
  guint8 seed[6] = { 0 };
  guint8 output[32];
  g_autoptr(GError) error = NULL;

  memset (output, 0xa5, sizeof output);
  g_assert_false (goodix_d190_bind_validator (secret, 31, seed, 6, seed, 6,
                                              output, &error));
  g_assert_error (error, g_quark_from_static_string ("goodix-d190-error"), 0);
  for (guint i = 0; i < sizeof output; i++)
    g_assert_cmphex (output[i], ==, 0);
}

static void
test_pe_canonical (void)
{
  guint8 seed_a[6] = { 0 };
  guint8 seed_b[6] = { 0 };
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_d190_pe_extract (CANONICAL_DLL, seed_a, seed_b,
                                         &error));
  g_assert_no_error (error);
  goodix_d190_pe_cleanse_seed (seed_a);
  goodix_d190_pe_cleanse_seed (seed_b);
  for (guint i = 0; i < 6; i++)
    {
      g_assert_cmphex (seed_a[i], ==, 0);
      g_assert_cmphex (seed_b[i], ==, 0);
    }
}

static void
test_pe_wrong_hash (void)
{
  g_autofree gchar *contents = NULL;
  gsize length = 0;
  GoodixD190PePolicy policy;
  guint8 seed_a[6] = { 0 };
  guint8 seed_b[6] = { 0 };
  g_autoptr(GError) error = NULL;

  g_assert_true (g_file_get_contents (CANONICAL_DLL, &contents, &length, NULL));
  goodix_d190_pe_policy_production (&policy);
  policy.expected_sha256[0] ^= 1;
  g_assert_false (goodix_d190_pe_extract_bytes_with_policy (
    (const guint8 *) contents, length, &policy, seed_a, seed_b, &error));
  g_assert_nonnull (error);
}

static void
test_pe_malformed (void)
{
  guint8 bytes[32] = { 0 };
  GoodixD190PePolicy policy;
  guint8 seed_a[6] = { 0 };
  guint8 seed_b[6] = { 0 };
  g_autoptr(GError) error = NULL;

  goodix_d190_pe_policy_production (&policy);
  digest (bytes, sizeof bytes, policy.expected_sha256);
  g_assert_false (goodix_d190_pe_extract_bytes_with_policy (
    bytes, sizeof bytes, &policy, seed_a, seed_b, &error));
  g_assert_nonnull (error);
}

static gssize
find_producer_pattern (const guint8 *bytes,
                       gsize         length)
{
  for (gsize i = 0; i + 12u <= length; i++)
    if (bytes[i] == 0xc7 && bytes[i + 1u] == 0x45 &&
        bytes[i + 2u] == 0x9f && bytes[i + 7u] == 0xc7 &&
        bytes[i + 8u] == 0x45 && bytes[i + 9u] == 0xa3)
      return (gssize) i;
  return -1;
}

static void
test_pe_pattern_negative (gconstpointer user_data)
{
  gboolean ambiguous = GPOINTER_TO_UINT (user_data) != 0;
  g_autofree gchar *contents = NULL;
  gsize length = 0;
  GoodixD190PePolicy policy;
  guint8 seed_a[6] = { 0 };
  guint8 seed_b[6] = { 0 };
  g_autoptr(GError) error = NULL;
  gssize offset;

  g_assert_true (g_file_get_contents (CANONICAL_DLL, &contents, &length, NULL));
  offset = find_producer_pattern ((const guint8 *) contents, length);
  g_assert_cmpint (offset, >=, 0);
  if (ambiguous)
    memcpy ((guint8 *) contents + length - 12u,
            (guint8 *) contents + offset, 12);
  else
    ((guint8 *) contents)[offset] ^= 1;
  goodix_d190_pe_policy_production (&policy);
  digest ((const guint8 *) contents, length, policy.expected_sha256);
  g_assert_false (goodix_d190_pe_extract_bytes_with_policy (
    (const guint8 *) contents, length, &policy, seed_a, seed_b, &error));
  g_assert_nonnull (error);
}

static void
test_pe_bounded_offset (void)
{
  g_autofree gchar *contents = NULL;
  gsize length = 0;
  GoodixD190PePolicy policy;
  guint8 seed_a[6] = { 0 };
  guint8 seed_b[6] = { 0 };
  g_autoptr(GError) error = NULL;

  g_assert_true (g_file_get_contents (CANONICAL_DLL, &contents, &length, NULL));
  goodix_d190_pe_policy_production (&policy);
  policy.first_seed_rva = G_MAXUINT32;
  g_assert_false (goodix_d190_pe_extract_bytes_with_policy (
    (const guint8 *) contents, length, &policy, seed_a, seed_b, &error));
  g_assert_nonnull (error);
}

static void
test_material_production_policy (void)
{
  GoodixTargetMaterialPolicy policy;
  goodix_target_material_policy_production (&policy);
  g_assert_cmpuint (policy.owner_uid, ==, 0);
  g_assert_cmpuint (policy.mode, ==, 0600);
  g_assert_cmphex (policy.config90_finalizer[0], ==, 0x51);
  g_assert_cmphex (policy.config90_finalizer[1], ==, 0x9a);
  g_assert_cmpuint (policy.transport_length, ==, 88);
  g_assert_cmpuint (policy.config90_length, ==, 224);
}

static void
test_material_production_policy_canonical_pins (void)
{
  GoodixTargetMaterialPolicy policy;
  guint8 expected_manifest_sha256[32];
  guint8 expected_transport_sha256[32];
  guint8 expected_config90_sha256[32];
  guint8 expected_e4_sha256[32];
  guint8 expected_a2_sha256[32];
  guint8 expected_chip82_sha256[32];
  guint8 expected_otp_a6_sha256[32];
  static const guint16 expected_registers[4] = {
    0x0220, 0x0236, 0x0238, 0x023a
  };
  static const guint8 expected_values[4][2] = {
    { 0xd8, 0x0b }, { 0xbe, 0x00 }, { 0xbd, 0x00 }, { 0xbc, 0x00 }
  };
  static const guint expected_offsets[4] = { 117, 121, 125, 129 };

  decode_hex ("1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15",
              expected_manifest_sha256, 32);
  decode_hex ("eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75",
              expected_transport_sha256, 32);
  decode_hex ("e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82",
              expected_config90_sha256, 32);
  decode_hex ("1fa642d3f190e7074d1db201aa32ee8f34e41d69d55797158b9480affb3d0b87",
              expected_e4_sha256, 32);
  decode_hex ("39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5",
              expected_a2_sha256, 32);
  decode_hex ("82537d2c108887baef128b47ad401fc888d54b184673b1fc23811d79ab6d5703",
              expected_chip82_sha256, 32);
  decode_hex ("d7e81a415aa5e7b0168c9a632756d1dc8b7b47346cc0a44dc68796f854c2b92b",
              expected_otp_a6_sha256, 32);

  goodix_target_material_policy_production (&policy);
  g_assert_cmpuint (policy.owner_uid, ==, 0);
  g_assert_cmpuint (policy.mode, ==, 0600);
  g_assert_cmpuint (policy.manifest_length, ==, 2305);
  ASSERT_CMPMEM (policy.manifest_sha256, (gsize) 32,
                   expected_manifest_sha256, (gsize) 32);
  g_assert_cmpuint (policy.transport_length, ==, 88);
  ASSERT_CMPMEM (policy.transport_sha256, (gsize) 32,
                   expected_transport_sha256, (gsize) 32);
  g_assert_cmpuint (policy.config90_length, ==, 224);
  ASSERT_CMPMEM (policy.config90_sha256, (gsize) 32,
                   expected_config90_sha256, (gsize) 32);
  g_assert_cmphex (policy.config90_finalizer[0], ==, 0x51);
  g_assert_cmphex (policy.config90_finalizer[1], ==, 0x9a);
  ASSERT_CMPMEM (policy.e4_validator_sha256, (gsize) 32,
                   expected_e4_sha256, (gsize) 32);
  ASSERT_CMPMEM (policy.a2_response_sha256, (gsize) 32,
                   expected_a2_sha256, (gsize) 32);
  ASSERT_CMPMEM (policy.chip82_response_sha256, (gsize) 32,
                   expected_chip82_sha256, (gsize) 32);
  ASSERT_CMPMEM (policy.otp_a6_response_sha256, (gsize) 32,
                   expected_otp_a6_sha256, (gsize) 32);
  ASSERT_CMPMEM (policy.dac_registers, sizeof expected_registers,
                   expected_registers, sizeof expected_registers);
  ASSERT_CMPMEM (policy.dac_values, sizeof expected_values,
                   expected_values, sizeof expected_values);
  ASSERT_CMPMEM (policy.dac_offsets, sizeof expected_offsets,
                   expected_offsets, sizeof expected_offsets);

  OPENSSL_cleanse (expected_manifest_sha256, sizeof expected_manifest_sha256);
  OPENSSL_cleanse (expected_transport_sha256, sizeof expected_transport_sha256);
  OPENSSL_cleanse (expected_config90_sha256, sizeof expected_config90_sha256);
  OPENSSL_cleanse (expected_e4_sha256, sizeof expected_e4_sha256);
  OPENSSL_cleanse (expected_a2_sha256, sizeof expected_a2_sha256);
  OPENSSL_cleanse (expected_chip82_sha256, sizeof expected_chip82_sha256);
  OPENSSL_cleanse (expected_otp_a6_sha256, sizeof expected_otp_a6_sha256);
}

static void
test_material_positive (void)
{
  MaterialFixture fixture;
  GoodixSecureSessionMaterial view;
  g_autoptr(GError) error = NULL;
  GoodixTargetMaterial *owner;

  material_fixture_init (&fixture);
  owner = load_fixture (&fixture, &view, TRUE, &error);
  g_assert_nonnull (owner);
  g_assert_no_error (error);
  g_assert_true (fixture.audit.e4_binding_match);
  ASSERT_CMPMEM (view.e4_validator, (gsize) 32,
                   fixture.expected_validator, (gsize) 32);
  ASSERT_CMPMEM (view.psk, (gsize) 32,
                   fixture.transport_bytes + 24, (gsize) 32);
  goodix_target_material_free (owner);
  g_assert_true (fixture.audit.project_secret_zeroized);
  g_assert_true (fixture.cleanse_all_zero);
  material_fixture_clear (&fixture);
}

static void
test_material_symlink (void)
{
  MaterialFixture fixture;
  g_autoptr(GError) error = NULL;
  GoodixTargetMaterial *owner;

  material_fixture_init (&fixture);
  write_mode600 (fixture.symlink_target, fixture.transport_bytes,
                 sizeof fixture.transport_bytes);
  g_assert_cmpint (g_remove (fixture.transport), ==, 0);
  g_assert_cmpint (symlink (fixture.symlink_target, fixture.transport), ==, 0);
  owner = load_fixture (&fixture, NULL, FALSE, &error);
  g_assert_null (owner);
  g_assert_nonnull (error);
  material_fixture_clear (&fixture);
}

static void
test_material_not_regular (void)
{
  MaterialFixture fixture;
  g_autoptr(GError) error = NULL;

  material_fixture_init (&fixture);
  g_assert_cmpint (g_remove (fixture.manifest), ==, 0);
  g_assert_cmpint (g_mkdir (fixture.manifest, 0700), ==, 0);
  fixture.manifest_is_directory = TRUE;
  g_assert_null (load_fixture (&fixture, NULL, FALSE, &error));
  g_assert_nonnull (error);
  material_fixture_clear (&fixture);
}

static void
test_material_wrong_mode (void)
{
  MaterialFixture fixture;
  g_autoptr(GError) error = NULL;

  material_fixture_init (&fixture);
  g_assert_cmpint (g_chmod (fixture.transport, 0644), ==, 0);
  g_assert_null (load_fixture (&fixture, NULL, FALSE, &error));
  g_assert_nonnull (error);
  material_fixture_clear (&fixture);
}

static void
test_material_wrong_owner_policy (void)
{
  MaterialFixture fixture;
  g_autoptr(GError) error = NULL;

  material_fixture_init (&fixture);
  fixture.policy.owner_uid = getuid () + 1u;
  g_assert_null (load_fixture (&fixture, NULL, FALSE, &error));
  g_assert_nonnull (error);
  material_fixture_clear (&fixture);
}

static void
change_during_read (const gchar *path,
                    gint         fd,
                    gpointer     user_data)
{
  gboolean *changed = user_data;
  (void) path;
  if (!*changed)
    {
      g_assert_cmpint (fchmod (fd, 0644), ==, 0);
      *changed = TRUE;
    }
}

static void
test_material_change_during_read (void)
{
  MaterialFixture fixture;
  g_autoptr(GError) error = NULL;
  gboolean changed = FALSE;

  material_fixture_init (&fixture);
  fixture.policy.after_read = change_during_read;
  fixture.policy.after_read_data = &changed;
  g_assert_null (load_fixture (&fixture, NULL, FALSE, &error));
  g_assert_true (changed);
  g_assert_nonnull (error);
  material_fixture_clear (&fixture);
}

typedef enum
{
  MATERIAL_MUT_TRANSPORT_LENGTH,
  MATERIAL_MUT_TRANSPORT_MAGIC,
  MATERIAL_MUT_TRANSPORT_HASH,
  MATERIAL_MUT_CONFIG_LENGTH,
  MATERIAL_MUT_CONFIG_HASH,
  MATERIAL_MUT_CONFIG_FINALIZER,
  MATERIAL_MUT_DAC_0220,
  MATERIAL_MUT_DAC_0236,
  MATERIAL_MUT_DAC_0238,
  MATERIAL_MUT_DAC_023A,
  MATERIAL_MUT_DAC_ORDER,
  MATERIAL_MUT_E4_PIN,
  MATERIAL_MUT_MANIFEST_HASH,
} MaterialMutation;

static void
test_material_mutation (gconstpointer user_data)
{
  MaterialMutation mutation = (MaterialMutation) GPOINTER_TO_UINT (user_data);
  MaterialFixture fixture;
  g_autoptr(GError) error = NULL;
  GoodixSecureSessionMaterial view;
  GoodixTargetMaterial *owner;

  material_fixture_init (&fixture);
  switch (mutation)
    {
    case MATERIAL_MUT_TRANSPORT_LENGTH:
      write_mode600 (fixture.transport, fixture.transport_bytes,
                     sizeof fixture.transport_bytes - 1u);
      break;
    case MATERIAL_MUT_TRANSPORT_MAGIC:
      fixture.transport_bytes[0] ^= 1;
      write_mode600 (fixture.transport, fixture.transport_bytes,
                     sizeof fixture.transport_bytes);
      break;
    case MATERIAL_MUT_TRANSPORT_HASH:
      fixture.transport_bytes[80] ^= 1;
      write_mode600 (fixture.transport, fixture.transport_bytes,
                     sizeof fixture.transport_bytes);
      break;
    case MATERIAL_MUT_CONFIG_LENGTH:
      write_mode600 (fixture.config, fixture.config_bytes,
                     sizeof fixture.config_bytes - 1u);
      break;
    case MATERIAL_MUT_CONFIG_HASH:
      fixture.config_bytes[10] ^= 1;
      write_mode600 (fixture.config, fixture.config_bytes,
                     sizeof fixture.config_bytes);
      break;
    case MATERIAL_MUT_CONFIG_FINALIZER:
      fixture.config_bytes[222] ^= 1;
      digest (fixture.config_bytes, sizeof fixture.config_bytes,
              fixture.policy.config90_sha256);
      write_mode600 (fixture.config, fixture.config_bytes,
                     sizeof fixture.config_bytes);
      break;
    case MATERIAL_MUT_DAC_0220:
    case MATERIAL_MUT_DAC_0236:
    case MATERIAL_MUT_DAC_0238:
    case MATERIAL_MUT_DAC_023A:
      {
        guint index = (guint) mutation - MATERIAL_MUT_DAC_0220;
        fixture.config_bytes[fixture.policy.dac_offsets[index] + 2u] ^= 1;
        set_config_finalizer (fixture.config_bytes);
        memcpy (fixture.policy.config90_finalizer,
                fixture.config_bytes + 222, 2);
        digest (fixture.config_bytes, sizeof fixture.config_bytes,
                fixture.policy.config90_sha256);
        write_mode600 (fixture.config, fixture.config_bytes,
                       sizeof fixture.config_bytes);
        break;
      }
    case MATERIAL_MUT_DAC_ORDER:
      {
        guint16 temporary = fixture.policy.dac_registers[0];
        fixture.policy.dac_registers[0] = fixture.policy.dac_registers[1];
        fixture.policy.dac_registers[1] = temporary;
        break;
      }
    case MATERIAL_MUT_E4_PIN:
      fixture.policy.e4_validator_sha256[0] ^= 1;
      break;
    case MATERIAL_MUT_MANIFEST_HASH:
      fixture.policy.manifest_sha256[0] ^= 1;
      break;
    }
  owner = load_fixture (&fixture, &view, mutation == MATERIAL_MUT_E4_PIN,
                        &error);
  g_assert_null (owner);
  g_assert_nonnull (error);
  material_fixture_clear (&fixture);
}

static void
test_material_one_owner_lifetime (void)
{
  MaterialFixture fixture;
  g_autoptr(GError) error = NULL;
  GoodixTargetMaterial *owner;

  material_fixture_init (&fixture);
  owner = load_fixture (&fixture, NULL, TRUE, &error);
  g_assert_nonnull (owner);
  goodix_target_material_free (owner);
  g_assert_cmpuint (fixture.audit.owner_free_count, ==, 1);
  g_assert_cmpuint (fixture.audit.owner_psk_cleanse_count, ==, 1);
  g_assert_cmpuint (fixture.audit.validator_cleanse_count, ==, 1);
  g_assert_true (fixture.audit.project_secret_zeroized);
  material_fixture_clear (&fixture);
}

static void
test_material_psk_scratch_cleansed (void)
{
  MaterialFixture fixture;
  g_autoptr(GError) error = NULL;
  GoodixTargetMaterial *owner;

  material_fixture_init (&fixture);
  owner = load_fixture (&fixture, NULL, FALSE, &error);
  g_assert_nonnull (owner);
  g_assert_true (fixture.audit.psk_scratch_cleansed);
  g_assert_cmpuint (fixture.audit.psk_scratch_cleanse_count, ==, 1);
  g_assert_true (fixture.cleanse_all_zero);
  goodix_target_material_free (owner);
  material_fixture_clear (&fixture);
}

static void
test_material_failure_path_cleansed (void)
{
  MaterialFixture fixture;
  g_autoptr(GError) error = NULL;

  material_fixture_init (&fixture);
  fixture.config_bytes[0] ^= 1;
  write_mode600 (fixture.config, fixture.config_bytes,
                 sizeof fixture.config_bytes);
  g_assert_null (load_fixture (&fixture, NULL, FALSE, &error));
  g_assert_true (fixture.audit.psk_scratch_cleansed);
  g_assert_true (fixture.audit.project_secret_zeroized);
  g_assert_true (fixture.cleanse_all_zero);
  g_assert_cmpuint (fixture.audit.owner_psk_cleanse_count, ==, 1);
  material_fixture_clear (&fixture);
}

typedef enum
{
  PREFLIGHT_SUCCESS,
  PREFLIGHT_OPEN,
  PREFLIGHT_METADATA,
  PREFLIGHT_CONTENT,
  PREFLIGHT_PE,
  PREFLIGHT_E4,
} PreflightCase;

static void
test_preflight_observability (gconstpointer user_data)
{
  PreflightCase test_case = (PreflightCase) GPOINTER_TO_UINT (user_data);
  MaterialFixture fixture;
  GoodixD190PePolicy pe_policy;
  GoodixD278PreflightFailure failure;
  GoodixSecureSessionMaterial view = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixTargetMaterial *owner;
  const gchar *manifest;
  const gchar *dll = CANONICAL_DLL;

  material_fixture_init (&fixture);
  goodix_d190_pe_policy_production (&pe_policy);
  manifest = fixture.manifest;
  switch (test_case)
    {
    case PREFLIGHT_SUCCESS:
      break;
    case PREFLIGHT_OPEN:
      manifest = fixture.symlink_target;
      break;
    case PREFLIGHT_METADATA:
      g_assert_cmpint (g_chmod (fixture.manifest, 0644), ==, 0);
      break;
    case PREFLIGHT_CONTENT:
      fixture.policy.manifest_sha256[0] ^= 1;
      break;
    case PREFLIGHT_PE:
      dll = fixture.symlink_target;
      break;
    case PREFLIGHT_E4:
      fixture.policy.e4_validator_sha256[0] ^= 1;
      break;
    }

  owner = goodix_d278_prepare_target_material (
    manifest, fixture.transport, fixture.config, dll, &fixture.policy,
    &pe_policy, &fixture.audit, &view, &failure, &error);
  if (test_case == PREFLIGHT_SUCCESS)
    {
      g_assert_nonnull (owner);
      g_assert_no_error (error);
      g_assert_cmpstr (failure.failure_stage, ==, "NONE");
      g_assert_cmpstr (failure.failure_class, ==, "NONE");
    }
  else
    {
      static const gchar *const stages[] = {
        "NONE", "TARGET_MATERIAL_LOAD", "TARGET_MATERIAL_LOAD",
        "TARGET_MATERIAL_LOAD", "CANONICAL_PE", "E4_BIND"
      };
      static const gchar *const classes[] = {
        "NONE", "PROTECTED_OPEN", "PROTECTED_METADATA",
        "PROTECTED_CONTENT", "CANONICAL_PE_OR_DLL", "E4_BINDING"
      };
      g_assert_null (owner);
      g_assert_nonnull (error);
      g_assert_cmpstr (failure.failure_stage, ==, stages[test_case]);
      g_assert_cmpstr (failure.failure_class, ==, classes[test_case]);
      g_assert_null (strstr (failure.failure_stage, "G5125POC"));
      g_assert_null (strstr (failure.failure_class, "G5125POC"));
      g_assert_null (strstr (failure.failure_stage, "b5e0beeb"));
      g_assert_null (strstr (failure.failure_class, "b5e0beeb"));
    }
  goodix_target_material_free (owner);
  OPENSSL_cleanse (&view, sizeof view);
  material_fixture_clear (&fixture);
}

static void
test_preflight_material_export_state_mapping (void)
{
  MaterialFixture fixture;
  GoodixSecureSessionMaterial view = { 0 };
  g_autoptr(GError) error = NULL;
  GoodixTargetMaterial *owner;

  material_fixture_init (&fixture);
  owner = load_fixture (&fixture, NULL, FALSE, &error);
  g_assert_nonnull (owner);
  g_assert_no_error (error);
  g_assert_false (goodix_target_material_get_secure_session_material (
    owner, &view, &error));
  g_assert_cmpstr (goodix_target_material_error_class (error), ==,
                   "MATERIAL_EXPORT_OR_STATE");
  goodix_target_material_free (owner);
  OPENSSL_cleanse (&view, sizeof view);
  material_fixture_clear (&fixture);
}

typedef struct
{
  guint64 generation;
  GBytes *bytes;
} HarnessSubmission;

typedef struct
{
  GoodixD278Harness *harness;
  GoodixD278Telemetry telemetry;
  GoodixSecureSessionMaterial material;
  GQueue *out;
  GByteArray *server_record;
  guint64 generation;
  guint in_submit_count;
  guint out_submit_count;
  guint schedule_count;
  guint64 scheduled_generation;
  gboolean schedule_pending;
  gboolean sealed;
  guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH];
  guint8 validator[32];
  guint8 a2[3];
  guint8 chip[4];
  guint8 otp[64];
  guint8 psk[GOODIX_SECURE_SESSION_PSK_LENGTH];
} HarnessFixture;

typedef struct
{
  SSL_CTX *context;
  SSL *ssl;
  const guint8 *psk;
  gsize psk_length;
} HarnessTlsClient;

typedef struct
{
  guint count;
  GoodixSecurePhase phase;
  guint64 generation;
} WatchdogObservation;

static void
harness_submission_free (HarnessSubmission *submission)
{
  if (submission == NULL)
    return;
  g_bytes_unref (submission->bytes);
  g_free (submission);
}

static void
harness_material_init (HarnessFixture *fixture)
{
  static const guint8 identity[] = "GF_ST411SEC_APP_12509";
  static const guint8 values[4][2] = {
    { 0xd8, 0x0b }, { 0xbe, 0x00 }, { 0xbd, 0x00 }, { 0xbc, 0x00 }
  };
  static const guint16 registers[] = { 0x0220, 0x0236, 0x0238, 0x023a };
  static const guint offsets[] = { 117, 121, 125, 129 };

  for (guint i = 0; i < sizeof fixture->validator; i++)
    {
      fixture->validator[i] = (guint8) (0x20u + i);
      fixture->psk[i] = (guint8) (0x80u + i);
    }
  fixture->a2[0] = 0x11;
  fixture->a2[1] = 0x22;
  fixture->a2[2] = 0x33;
  fixture->chip[0] = 0x25;
  fixture->chip[1] = 0x04;
  fixture->chip[2] = 0x12;
  fixture->chip[3] = 0x50;
  for (guint i = 0; i < sizeof fixture->otp; i++)
    fixture->otp[i] = (guint8) (i * 3u + 1u);
  for (guint i = 0; i < G_N_ELEMENTS (offsets); i++)
    {
      fixture->config[offsets[i]] = (guint8) registers[i];
      fixture->config[offsets[i] + 1u] = (guint8) (registers[i] >> 8);
      memcpy (fixture->config + offsets[i] + 2u, values[i], 2);
      memcpy (fixture->material.dac_values[i], values[i], 2);
    }
  set_config_finalizer (fixture->config);
  fixture->material.expected_identity = identity;
  fixture->material.expected_identity_length = sizeof identity;
  fixture->material.e4_validator = fixture->validator;
  fixture->material.e4_validator_length = sizeof fixture->validator;
  fixture->material.config90 = fixture->config;
  fixture->material.config90_length = sizeof fixture->config;
  fixture->material.psk = fixture->psk;
  fixture->material.psk_length = sizeof fixture->psk;
  digest (fixture->validator, sizeof fixture->validator,
          fixture->material.e4_validator_sha256);
  digest (fixture->a2, sizeof fixture->a2,
          fixture->material.a2_response_sha256);
  digest (fixture->chip, sizeof fixture->chip,
          fixture->material.chip82_response_sha256);
  digest (fixture->otp, sizeof fixture->otp,
          fixture->material.otp_a6_response_sha256);
  digest (fixture->config, sizeof fixture->config,
          fixture->material.config90_sha256);
}

static void
harness_submit (GoodixD278Harness  *harness,
                GoodixUsbDirection direction,
                guint64            generation,
                GBytes            *bytes,
                gpointer           user_data)
{
  HarnessFixture *fixture = user_data;
  HarnessSubmission *submission;

  g_assert_true (harness == fixture->harness);
  g_assert_cmpuint (generation, ==, fixture->generation);
  if (direction == GOODIX_USB_TRANSFER_IN)
    {
      g_assert_null (bytes);
      fixture->in_submit_count++;
      return;
    }
  g_assert_nonnull (bytes);
  submission = g_new0 (HarnessSubmission, 1);
  submission->generation = generation;
  submission->bytes = g_bytes_ref (bytes);
  fixture->out_submit_count++;
  g_queue_push_tail (fixture->out, submission);
}

static void
harness_pacing (GoodixD278Harness *harness,
                guint64           generation,
                guint             delay_ms,
                gpointer          user_data)
{
  HarnessFixture *fixture = user_data;

  g_assert_true (harness == fixture->harness);
  g_assert_cmpuint (generation, ==, fixture->generation);
  g_assert_cmpuint (delay_ms, ==, GOODIX_SECURE_SESSION_TLS_PACING_MS);
  g_assert_false (fixture->schedule_pending);
  fixture->schedule_pending = TRUE;
  fixture->scheduled_generation = generation;
  fixture->schedule_count++;
}

static HarnessFixture *
harness_fixture_new (void)
{
  HarnessFixture *fixture = g_new0 (HarnessFixture, 1);
  g_autoptr(GError) error = NULL;

  fixture->out = g_queue_new ();
  fixture->server_record = g_byte_array_new ();
  harness_material_init (fixture);
  goodix_d278_telemetry_init (&fixture->telemetry, FALSE);
  /* Synthetic fixture ownership is outside the harness, as the protected
   * owner is outside it in live composition.  The fixture explicitly wipes
   * those bytes at teardown. */
  fixture->telemetry.project_secret_zeroized = TRUE;
  fixture->harness = goodix_d278_harness_new (
    NULL, &fixture->material, TRUE, TRUE, harness_submit, harness_pacing,
    fixture, &fixture->telemetry, &error);
  g_assert_no_error (error);
  g_assert_nonnull (fixture->harness);
  fixture->generation = goodix_d278_harness_get_generation (fixture->harness);
  if (!goodix_d278_harness_start (fixture->harness, &error))
    g_error ("synthetic D278 harness start failed: %s",
             error != NULL ? error->message : "unknown error");
  g_assert_no_error (error);
  return fixture;
}

static void
harness_clear_out (HarnessFixture *fixture)
{
  while (!g_queue_is_empty (fixture->out))
    harness_submission_free (g_queue_pop_head (fixture->out));
}

static void
harness_fixture_drain_and_seal (HarnessFixture *fixture)
{
  if (fixture->sealed)
    return;
  if (!goodix_fpi_usb_backend_is_drained (
        goodix_d278_harness_get_backend (fixture->harness)))
    goodix_d278_harness_force_synthetic_drain (fixture->harness);
  g_assert_true (goodix_fpi_usb_backend_is_drained (
    goodix_d278_harness_get_backend (fixture->harness)));
  goodix_d278_harness_seal (fixture->harness);
  fixture->sealed = TRUE;
}

static void
harness_fixture_free (HarnessFixture *fixture)
{
  if (fixture == NULL)
    return;
  if (!goodix_d278_harness_is_terminal (fixture->harness))
    goodix_d278_harness_cancel (fixture->harness, "TEST_TEARDOWN");
  harness_fixture_drain_and_seal (fixture);
  harness_clear_out (fixture);
  goodix_d278_harness_free (fixture->harness);
  g_queue_free (fixture->out);
  g_byte_array_unref (fixture->server_record);
  OPENSSL_cleanse (fixture, sizeof *fixture);
  g_free (fixture);
}

static HarnessSubmission *
harness_pop_out (HarnessFixture *fixture)
{
  HarnessSubmission *submission = g_queue_pop_head (fixture->out);

  g_assert_nonnull (submission);
  return submission;
}

static GBytes *
harness_build_response (guint8       control,
                        const guint8 *body,
                        gsize         body_length)
{
  g_autoptr(GError) error = NULL;
  GBytes *frame = goodix_a0_build_frame (control, control, body, body_length,
                                         &error);
  g_assert_no_error (error);
  g_assert_nonnull (frame);
  return frame;
}

static GBytes *
harness_build_ack_status (guint8 echo,
                          guint8 status)
{
  guint8 body[2] = { echo, status };
  return harness_build_response (0xb0, body, sizeof body);
}

static GBytes *
harness_build_ack (guint8 echo)
{
  return harness_build_ack_status (echo, 0x01);
}

static guint8
harness_control_for_phase (GoodixSecurePhase phase)
{
  switch (phase)
    {
    case GOODIX_SECURE_PHASE_A8: return 0xa8;
    case GOODIX_SECURE_PHASE_E4: return 0xe4;
    case GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2:
    case GOODIX_SECURE_PHASE_OEM_COLD_START_A2_1:
    case GOODIX_SECURE_PHASE_OEM_COLD_START_A2_2: return 0xa2;
    case GOODIX_SECURE_PHASE_CHIP_82: return 0x82;
    case GOODIX_SECURE_PHASE_OTP_A6: return 0xa6;
    case GOODIX_SECURE_PHASE_MODE_70: return 0x70;
    case GOODIX_SECURE_PHASE_DAC_220:
    case GOODIX_SECURE_PHASE_DAC_236:
    case GOODIX_SECURE_PHASE_DAC_238:
    case GOODIX_SECURE_PHASE_DAC_23A: return 0x80;
    case GOODIX_SECURE_PHASE_CONFIG_90: return 0x90;
    case GOODIX_SECURE_PHASE_D1: return 0xd1;
    default: return 0;
    }
}

static GBytes *
harness_typed_for_phase (HarnessFixture   *fixture,
                         GoodixSecurePhase phase)
{
  guint8 e4[41] = { 0x00, 0x03, 0x00, 0x02, 0xbb, 0x20, 0, 0, 0 };
  static const guint8 done90[] = { 1, 0 };

  switch (phase)
    {
    case GOODIX_SECURE_PHASE_A8:
      return harness_build_response (
        0xa8, fixture->material.expected_identity,
        fixture->material.expected_identity_length);
    case GOODIX_SECURE_PHASE_E4:
      memcpy (e4 + 9, fixture->validator, sizeof fixture->validator);
      return harness_build_response (0xe4, e4, sizeof e4);
    case GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2:
    case GOODIX_SECURE_PHASE_OEM_COLD_START_A2_1:
    case GOODIX_SECURE_PHASE_OEM_COLD_START_A2_2:
      return harness_build_response (0xa2, fixture->a2, sizeof fixture->a2);
    case GOODIX_SECURE_PHASE_CHIP_82:
      return harness_build_response (0x82, fixture->chip,
                                     sizeof fixture->chip);
    case GOODIX_SECURE_PHASE_OTP_A6:
      return harness_build_response (0xa6, fixture->otp,
                                     sizeof fixture->otp);
    case GOODIX_SECURE_PHASE_CONFIG_90:
      return harness_build_response (0x90, done90, sizeof done90);
    default:
      return NULL;
    }
}

static void
harness_respond_valid (HarnessFixture *fixture)
{
  GoodixSecureSession *session = goodix_d278_harness_get_session (
    fixture->harness);
  GoodixSecurePhase phase = goodix_secure_session_get_phase (session);
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GBytes) typed = NULL;
  g_autoptr(GByteArray) response = g_byte_array_new ();
  HarnessSubmission *submission = harness_pop_out (fixture);
  gsize length;
  const guint8 *data;

  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_outstanding (
                     goodix_d278_harness_get_backend (fixture->harness)), ==, 1);
  goodix_d278_harness_complete_out (fixture->harness,
                                    submission->generation, NULL);
  harness_submission_free (submission);
  if (phase == GOODIX_SECURE_PHASE_D1)
    return;
  ack = harness_build_ack (harness_control_for_phase (phase));
  typed = harness_typed_for_phase (fixture, phase);
  data = g_bytes_get_data (ack, &length);
  g_byte_array_append (response, data, (guint) length);
  if (typed != NULL)
    {
      data = g_bytes_get_data (typed, &length);
      g_byte_array_append (response, data, (guint) length);
    }
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (
                     goodix_d278_harness_get_backend (fixture->harness)), ==, 1);
  goodix_d278_harness_complete_receive (fixture->harness,
                                        fixture->generation,
                                        response->data, response->len, NULL);
}

static void
harness_advance_to (HarnessFixture   *fixture,
                    GoodixSecurePhase target)
{
  while (goodix_secure_session_get_phase (
           goodix_d278_harness_get_session (fixture->harness)) < target)
    harness_respond_valid (fixture);
}

static unsigned int
harness_client_psk (SSL          *ssl,
                    const char   *hint,
                    char         *identity,
                    unsigned int  identity_max,
                    unsigned char *psk,
                    unsigned int  psk_max)
{
  HarnessTlsClient *client = SSL_get_app_data (ssl);

  (void) hint;
  g_strlcpy (identity, "Client_identity", identity_max);
  g_assert_cmpuint (psk_max, >=, client->psk_length);
  memcpy (psk, client->psk, client->psk_length);
  return (unsigned int) client->psk_length;
}

static void
harness_client_init (HarnessTlsClient *client,
                     HarnessFixture   *fixture)
{
  BIO *input;
  BIO *output;

  memset (client, 0, sizeof *client);
  client->psk = fixture->psk;
  client->psk_length = sizeof fixture->psk;
  client->context = SSL_CTX_new (TLS_client_method ());
  g_assert_nonnull (client->context);
  g_assert_cmpint (SSL_CTX_set_min_proto_version (client->context,
                                                  TLS1_2_VERSION), ==, 1);
  g_assert_cmpint (SSL_CTX_set_max_proto_version (client->context,
                                                  TLS1_2_VERSION), ==, 1);
  g_assert_cmpint (SSL_CTX_set_cipher_list (client->context,
                                             "PSK-AES128-GCM-SHA256"), ==, 1);
  SSL_CTX_set_psk_client_callback (client->context, harness_client_psk);
  client->ssl = SSL_new (client->context);
  g_assert_nonnull (client->ssl);
  SSL_set_app_data (client->ssl, client);
  input = BIO_new (BIO_s_mem ());
  output = BIO_new (BIO_s_mem ());
  g_assert_nonnull (input);
  g_assert_nonnull (output);
  BIO_set_mem_eof_return (input, -1);
  SSL_set_bio (client->ssl, input, output);
  SSL_set_connect_state (client->ssl);
}

static void
harness_client_clear (HarnessTlsClient *client)
{
  SSL_free (client->ssl);
  SSL_CTX_free (client->context);
}

static void
harness_feed_client_records (HarnessFixture   *fixture,
                             HarnessTlsClient *client)
{
  guint8 buffer[8192];
  int read_length;
  g_autoptr(GByteArray) pending = g_byte_array_new ();

  while ((read_length = BIO_read (SSL_get_wbio (client->ssl), buffer,
                                  sizeof buffer)) > 0)
    g_byte_array_append (pending, buffer, (guint) read_length);
  while (pending->len >= 5)
    {
      gsize record_length = 5u + ((gsize) pending->data[3] << 8) +
                            pending->data[4];
      guint8 header[4] = { 0xb0, (guint8) record_length,
                           (guint8) (record_length >> 8), 0 };
      g_autoptr(GByteArray) b0 = NULL;

      g_assert_cmpuint (pending->len, >=, record_length);
      header[3] = (guint8) (header[0] + header[1] + header[2]);
      b0 = g_byte_array_sized_new ((guint) record_length + 4u);
      g_byte_array_append (b0, header, sizeof header);
      g_byte_array_append (b0, pending->data, (guint) record_length);
      g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (
        goodix_d278_harness_get_backend (fixture->harness)), ==, 1);
      goodix_d278_harness_complete_receive (fixture->harness,
                                            fixture->generation,
                                            b0->data, b0->len, NULL);
      g_byte_array_remove_range (pending, 0, (guint) record_length);
    }
  g_assert_cmpuint (pending->len, ==, 0);
}

static void
harness_drain_server_records (HarnessFixture   *fixture,
                              HarnessTlsClient *client)
{
  while (!g_queue_is_empty (fixture->out) || fixture->schedule_pending)
    {
      HarnessSubmission *submission;
      gsize length;
      const guint8 *data;

      if (g_queue_is_empty (fixture->out))
        {
          guint64 generation = fixture->scheduled_generation;
          fixture->schedule_pending = FALSE;
          goodix_d278_harness_pacing_ready (fixture->harness, generation - 1u);
          g_assert_true (g_queue_is_empty (fixture->out));
          goodix_d278_harness_pacing_ready (fixture->harness, generation);
          continue;
        }
      submission = harness_pop_out (fixture);
      data = g_bytes_get_data (submission->bytes, &length);
      g_assert_cmpuint (length, ==, 64);
      g_byte_array_append (fixture->server_record, data, (guint) length);
      if (fixture->server_record->len >= 4)
        {
          guint16 payload_length = (guint16) (
            fixture->server_record->data[1] |
            ((guint16) fixture->server_record->data[2] << 8));
          gsize logical_length = (gsize) payload_length + 4u;
          if (fixture->server_record->len >= logical_length)
            {
              g_assert_cmphex (fixture->server_record->data[0], ==, 0xb0);
              g_assert_cmphex (fixture->server_record->data[3], ==,
                               (guint8) (0xb0u +
                                 fixture->server_record->data[1] +
                                 fixture->server_record->data[2]));
              for (gsize i = logical_length;
                   i < fixture->server_record->len; i++)
                g_assert_cmphex (fixture->server_record->data[i], ==, 0);
              g_assert_cmpint (BIO_write (SSL_get_rbio (client->ssl),
                                          fixture->server_record->data + 4,
                                          payload_length), ==,
                               payload_length);
              g_byte_array_set_size (fixture->server_record, 0);
            }
        }
      goodix_d278_harness_complete_out (fixture->harness,
                                        submission->generation, NULL);
      harness_submission_free (submission);
    }
  g_assert_cmpuint (fixture->server_record->len, ==, 0);
}

static gboolean
harness_pump_tls (HarnessFixture   *fixture,
                  HarnessTlsClient *client)
{
  for (guint iteration = 0; iteration < 64; iteration++)
    {
      int result = SSL_do_handshake (client->ssl);
      if (result != 1)
        {
          int ssl_error = SSL_get_error (client->ssl, result);
          if (ssl_error != SSL_ERROR_WANT_READ &&
              ssl_error != SSL_ERROR_WANT_WRITE)
            return FALSE;
        }
      harness_feed_client_records (fixture, client);
      harness_drain_server_records (fixture, client);
      if (SSL_is_init_finished (client->ssl) &&
          goodix_secure_session_get_phase (
            goodix_d278_harness_get_session (fixture->harness)) ==
            GOODIX_SECURE_PHASE_STOP)
        return TRUE;
      if (goodix_secure_session_get_phase (
            goodix_d278_harness_get_session (fixture->harness)) ==
          GOODIX_SECURE_PHASE_TERMINAL)
        return FALSE;
    }
  return FALSE;
}

static void
harness_run_success (HarnessFixture *fixture)
{
  HarnessTlsClient client;

  harness_advance_to (fixture, GOODIX_SECURE_PHASE_D1);
  harness_respond_valid (fixture);
  harness_client_init (&client, fixture);
  if (!harness_pump_tls (fixture, &client))
    {
      const GError *session_error = goodix_secure_session_get_error (
        goodix_d278_harness_get_session (fixture->harness));
      g_error ("synthetic TLS failed: phase=%s trace=%s failure=%s error=%s",
               goodix_secure_phase_name (goodix_secure_session_get_phase (
                 goodix_d278_harness_get_session (fixture->harness))),
               goodix_d278_harness_get_phase_trace (fixture->harness),
               fixture->telemetry.failure_class,
               session_error != NULL ? session_error->message : "none");
    }
  g_assert_true (SSL_is_init_finished (client.ssl));
  harness_client_clear (&client);
  g_assert_cmpint (goodix_secure_session_get_phase (
    goodix_d278_harness_get_session (fixture->harness)), ==,
    GOODIX_SECURE_PHASE_STOP);
}

static void
watchdog_observe (GoodixSecurePhase phase,
                  guint64           generation,
                  gpointer          user_data)
{
  WatchdogObservation *observation = user_data;
  observation->count++;
  observation->phase = phase;
  observation->generation = generation;
}

static void
test_harness_material_failure_before_open (void)
{
  MaterialFixture fixture;
  GoodixSecureSessionMaterial view;
  g_autoptr(GError) error = NULL;
  GoodixTargetMaterial *owner;
  guint synthetic_open_count = 0;

  material_fixture_init (&fixture);
  fixture.transport_bytes[0] ^= 1;
  write_mode600 (fixture.transport, fixture.transport_bytes,
                 sizeof fixture.transport_bytes);
  owner = load_fixture (&fixture, &view, FALSE, &error);
  if (owner != NULL)
    synthetic_open_count++;
  g_assert_null (owner);
  g_assert_nonnull (error);
  g_assert_cmpuint (synthetic_open_count, ==, 0);
  material_fixture_clear (&fixture);
}

static void
test_harness_synthetic_single_open_claim (void)
{
  guint synthetic_open_count = 0;
  guint synthetic_claim_count = 0;
  HarnessFixture *fixture;
  g_autoptr(GError) second_start_error = NULL;

  synthetic_open_count++;
  synthetic_claim_count++;
  fixture = harness_fixture_new ();
  g_assert_cmpuint (synthetic_open_count, ==, 1);
  g_assert_cmpuint (synthetic_claim_count, ==, 1);
  g_assert_cmpuint (fixture->generation, ==, 1);
  g_assert_cmpuint (fixture->telemetry.real_usb_submit_count, ==, 0);
  g_assert_false (goodix_d278_harness_start (fixture->harness,
                                              &second_start_error));
  g_assert_nonnull (second_start_error);
  harness_fixture_free (fixture);
}

static void
test_harness_full_secure_session_to_stop (void)
{
  HarnessFixture *fixture = harness_fixture_new ();
  const GoodixSecureSessionAudit *session_audit;
  static const gchar expected_trace[] =
    "REENTRY_RECOVERY_A2,A8,E4,OEM_COLD_START_A2_1,CHIP_82,OTP_A6,"
    "OEM_COLD_START_A2_2,MODE_70,DAC_220,DAC_236,"
    "DAC_238,DAC_23A,CONFIG_90,D1,TLS,STOP";

  harness_run_success (fixture);
  g_assert_cmpstr (goodix_d278_harness_get_phase_trace (fixture->harness), ==,
                   expected_trace);
  g_assert_cmpuint (fixture->schedule_count, >, 0);
  harness_fixture_drain_and_seal (fixture);
  session_audit = goodix_d278_harness_get_session_audit (fixture->harness);
  g_assert_nonnull (session_audit);
  g_assert_cmpuint (session_audit->e4_validator_cleanse_count, ==, 1);
  g_assert_cmpuint (session_audit->config90_cleanse_count, ==, 1);
  g_assert_cmpuint (session_audit->material_descriptor_cleanse_count, ==, 1);
  g_assert_true (session_audit->project_material_zeroized);
  g_assert_cmpstr (fixture->telemetry.result, ==, "pass");
  g_assert_cmpuint (fixture->telemetry.command_count, ==, 14);
  g_assert_cmpuint (fixture->telemetry.ack_count, ==, 13);
  g_assert_cmpuint (fixture->telemetry.typed_response_count, ==, 8);
  g_assert_cmpuint (fixture->telemetry.reentry_recovery_a2_submit_count, ==, 1);
  g_assert_cmpuint (fixture->telemetry.reentry_recovery_a2_ack_count, ==, 1);
  g_assert_cmpuint (fixture->telemetry.reentry_recovery_a2_typed_count, ==, 1);
  g_assert_false (fixture->telemetry.reentry_pre_ack_typed_observed);
  g_assert_false (fixture->telemetry.reentry_pre_ack_typed_pin_match);
  g_assert_cmpuint (fixture->telemetry.reentry_pre_ack_typed_discard_count,
                    ==, 0);
  g_assert_cmpstr (fixture->telemetry.reentry_recovery_a2_result_class, ==,
                   "STRICT_MATCH");
  g_assert_cmpuint (fixture->telemetry.a8_submit_count, ==, 1);
  g_assert_cmpuint (fixture->telemetry.a8_ack_count, ==, 1);
  g_assert_cmpuint (fixture->telemetry.a8_typed_count, ==, 1);
  g_assert_true (fixture->telemetry.a8_app12509_pin_match);
  g_assert_cmpuint (fixture->telemetry.e4_submit_count, ==, 1);
  g_assert_cmpuint (fixture->telemetry.oem_cold_start_a2_1_submit_count, ==, 1);
  g_assert_cmpuint (fixture->telemetry.oem_cold_start_a2_2_submit_count, ==, 1);
  g_assert_cmpuint (fixture->telemetry.tls_handshake_count, ==, 1);
  g_assert_true (fixture->telemetry.tls_established);
  g_assert_true (fixture->telemetry.backend_drained);
  g_assert_true (fixture->telemetry.terminal_cleanup_completed);
  g_assert_cmpuint (fixture->telemetry.real_usb_submit_count, ==, 0);
  /* The deterministic OpenSSL peer and fixed 64-byte B0 egress policy make
   * the complete host-only reference path's physical budget reproducible. */
  g_assert_cmpuint (fixture->telemetry.physical_in_submit_count, ==, 18);
  g_assert_cmpuint (fixture->telemetry.physical_in_completion_count, ==, 18);
  g_assert_cmpuint (fixture->telemetry.physical_out_submit_count, ==, 19);
  g_assert_cmpuint (fixture->telemetry.physical_out_completion_count, ==, 19);
  g_assert_cmpuint (session_audit->b0_physical_submit_count, ==, 5);
  g_test_message ("D278/11 happy physical IN=%" G_GUINT64_FORMAT
                  " OUT=%" G_GUINT64_FORMAT " B0=%u",
                  fixture->telemetry.physical_in_submit_count,
                  fixture->telemetry.physical_out_submit_count,
                  session_audit->b0_physical_submit_count);
  harness_fixture_free (fixture);
}

static void
fire_harness_watchdog (HarnessFixture *fixture)
{
  GoodixD278Watchdog *watchdog = goodix_d278_harness_get_watchdog (
    fixture->harness);
  guint64 serial = goodix_d278_watchdog_get_serial (watchdog);

  goodix_d278_watchdog_fire_for_test (watchdog, fixture->generation, serial);
  g_assert_true (goodix_d278_harness_is_terminal (fixture->harness));
}

static void
test_harness_phase_watchdog_reentry_recovery_a2 (void)
{
  HarnessFixture *fixture = harness_fixture_new ();
  fire_harness_watchdog (fixture);
  harness_fixture_drain_and_seal (fixture);
  g_assert_cmpstr (fixture->telemetry.failure_class, ==,
                   "PHASE_TIMEOUT_REENTRY_RECOVERY_A2");
  g_assert_cmpuint (fixture->telemetry.a8_submit_count, ==, 0);
  g_assert_cmpuint (fixture->telemetry.e4_submit_count, ==, 0);
  g_assert_cmpuint (fixture->telemetry.command_count, ==, 1);
  g_assert_true (fixture->telemetry.backend_drained);
  g_assert_true (fixture->telemetry.terminal_cleanup_completed);
  harness_fixture_free (fixture);
}

static void
test_harness_phase_watchdog_pre_d1 (void)
{
  HarnessFixture *fixture = harness_fixture_new ();
  harness_advance_to (fixture, GOODIX_SECURE_PHASE_CONFIG_90);
  fire_harness_watchdog (fixture);
  g_assert_cmpstr (fixture->telemetry.failure_class, ==,
                   "PHASE_TIMEOUT_CONFIG_90");
  harness_fixture_free (fixture);
}

static void
test_harness_phase_watchdog_tls (void)
{
  HarnessFixture *fixture = harness_fixture_new ();
  HarnessTlsClient client;

  harness_advance_to (fixture, GOODIX_SECURE_PHASE_D1);
  harness_respond_valid (fixture);
  harness_client_init (&client, fixture);
  {
    int result = SSL_do_handshake (client.ssl);
    g_assert_cmpint (result, ==, -1);
    g_assert_cmpint (SSL_get_error (client.ssl, result), ==,
                     SSL_ERROR_WANT_READ);
  }
  harness_feed_client_records (fixture, &client);
  g_assert_cmpint (goodix_secure_session_get_phase (
    goodix_d278_harness_get_session (fixture->harness)), ==,
    GOODIX_SECURE_PHASE_TLS);
  fire_harness_watchdog (fixture);
  g_assert_cmpstr (fixture->telemetry.failure_class, ==, "PHASE_TIMEOUT_TLS");
  harness_client_clear (&client);
  harness_fixture_free (fixture);
}

static void
test_harness_watchdog_cancelled_on_progress (void)
{
  static const guint expected_bounds[] = {
    1000, 1000, 1000, 1000, 500, 750, 1000, 500,
    250, 250, 250, 250, 1000, 1000, 3000
  };
  WatchdogObservation observation = { 0 };
  GoodixD278Watchdog *watchdog = goodix_d278_watchdog_new (
    TRUE, watchdog_observe, &observation);
  guint64 stale_serial;

  for (guint phase = 0; phase < G_N_ELEMENTS (expected_bounds); phase++)
    g_assert_cmpuint (goodix_d278_watchdog_timeout_for_phase (
                       (GoodixSecurePhase) phase), ==,
                      expected_bounds[phase]);

  goodix_d278_watchdog_progress (watchdog, GOODIX_SECURE_PHASE_A8, 3);
  stale_serial = goodix_d278_watchdog_get_serial (watchdog);
  goodix_d278_watchdog_progress (watchdog, GOODIX_SECURE_PHASE_E4, 3);
  goodix_d278_watchdog_fire_for_test (watchdog, 3, stale_serial);
  g_assert_cmpuint (observation.count, ==, 0);
  goodix_d278_watchdog_fire_for_test (
    watchdog, 3, goodix_d278_watchdog_get_serial (watchdog));
  g_assert_cmpuint (observation.count, ==, 1);
  g_assert_cmpint (observation.phase, ==, GOODIX_SECURE_PHASE_E4);
  goodix_d278_watchdog_free (watchdog);
}

static void
test_harness_watchdog_invalidated_on_terminal (void)
{
  WatchdogObservation observation = { 0 };
  GoodixD278Watchdog *watchdog = goodix_d278_watchdog_new (
    TRUE, watchdog_observe, &observation);
  guint64 serial;

  goodix_d278_watchdog_progress (watchdog, GOODIX_SECURE_PHASE_TLS, 9);
  serial = goodix_d278_watchdog_get_serial (watchdog);
  goodix_d278_watchdog_invalidate (watchdog);
  goodix_d278_watchdog_fire_for_test (watchdog, 9, serial);
  g_assert_cmpuint (observation.count, ==, 0);
  goodix_d278_watchdog_free (watchdog);
}

static void
test_harness_drain_before_free (void)
{
  HarnessFixture *fixture = harness_fixture_new ();

  g_assert_false (goodix_fpi_usb_backend_is_drained (
    goodix_d278_harness_get_backend (fixture->harness)));
  goodix_d278_harness_cancel (fixture->harness, "EXPECTED_CANCEL");
  harness_fixture_drain_and_seal (fixture);
  g_assert_true (fixture->telemetry.backend_drained);
  g_assert_true (fixture->telemetry.terminal_cleanup_completed);
  harness_fixture_free (fixture);
}

static void
test_harness_stale_receive_after_terminal (void)
{
  HarnessFixture *fixture = harness_fixture_new ();
  guint submits;

  fire_harness_watchdog (fixture);
  goodix_d278_harness_force_synthetic_drain (fixture->harness);
  submits = fixture->out_submit_count;
  goodix_d278_harness_complete_receive (fixture->harness,
                                        fixture->generation,
                                        (const guint8 *) "stale", 5, NULL);
  g_assert_cmpuint (fixture->out_submit_count, ==, submits);
  harness_fixture_free (fixture);
}

static void
test_harness_stale_out_after_terminal (void)
{
  HarnessFixture *fixture = harness_fixture_new ();
  guint submits;

  fire_harness_watchdog (fixture);
  goodix_d278_harness_force_synthetic_drain (fixture->harness);
  submits = fixture->out_submit_count;
  goodix_d278_harness_complete_out (fixture->harness,
                                    fixture->generation, NULL);
  g_assert_cmpuint (fixture->out_submit_count, ==, submits);
  harness_fixture_free (fixture);
}

static HarnessFixture *
successful_sealed_fixture (void)
{
  HarnessFixture *fixture = harness_fixture_new ();
  harness_run_success (fixture);
  harness_fixture_drain_and_seal (fixture);
  return fixture;
}

static void
test_harness_max_one_in (void)
{
  HarnessFixture *fixture = successful_sealed_fixture ();
  g_assert_cmpuint (fixture->telemetry.max_outstanding_bulk_in, ==, 1);
  harness_fixture_free (fixture);
}

static void
test_harness_max_one_out (void)
{
  HarnessFixture *fixture = successful_sealed_fixture ();
  g_assert_cmpuint (fixture->telemetry.max_outstanding_bulk_out, ==, 1);
  harness_fixture_free (fixture);
}

static void
test_harness_no_retry (void)
{
  HarnessFixture *fixture = successful_sealed_fixture ();
  g_assert_cmpuint (fixture->telemetry.retry_count, ==, 0);
  harness_fixture_free (fixture);
}

static void
test_harness_no_reopen (void)
{
  HarnessFixture *fixture = successful_sealed_fixture ();
  g_assert_cmpuint (fixture->telemetry.transport_reopen_count, ==, 0);
  harness_fixture_free (fixture);
}

static void
test_harness_no_reset (void)
{
  HarnessFixture *fixture = successful_sealed_fixture ();
  g_assert_cmpuint (fixture->telemetry.device_reset_count, ==, 0);
  g_assert_cmpuint (fixture->telemetry.clear_halt_count, ==, 0);
  harness_fixture_free (fixture);
}

static void
test_harness_d4_unreachable (void)
{
  HarnessFixture *fixture = successful_sealed_fixture ();
  g_assert_false (fixture->telemetry.d4_reachable);
  g_assert_cmpuint (fixture->telemetry.persistent_device_write_count, ==, 0);
  harness_fixture_free (fixture);
}

static void
test_harness_application_data_out_of_scope (void)
{
  HarnessFixture *fixture = successful_sealed_fixture ();
  g_assert_cmpuint (fixture->telemetry.application_data_count, ==, 0);
  g_assert_cmpuint (fixture->telemetry.finger_wait_count, ==, 0);
  g_assert_cmpuint (fixture->telemetry.image_count, ==, 0);
  harness_fixture_free (fixture);
}

static void
test_harness_redacted_telemetry (void)
{
  HarnessFixture *fixture = successful_sealed_fixture ();
  g_autofree gchar *json = goodix_d278_telemetry_to_json (
    fixture->harness, &fixture->telemetry);
  GoodixD278Telemetry boundary;
  g_autofree gchar *boundary_json = NULL;

  g_assert_nonnull (strstr (json, "\"real_usb_access\":0"));
  g_assert_nonnull (strstr (json, "\"current_live_authorized\":false"));
  g_assert_nonnull (strstr (json,
                            "\"reentry_recovery_a2_submit_count\":1"));
  g_assert_nonnull (strstr (json,
                            "\"reentry_recovery_a2_result_class\":\"STRICT_MATCH\""));
  g_assert_nonnull (strstr (json,
                            "\"reentry_pre_ack_typed_observed\":false"));
  g_assert_nonnull (strstr (json,
                            "\"reentry_pre_ack_typed_pin_match\":false"));
  g_assert_nonnull (strstr (json,
                            "\"reentry_pre_ack_typed_discard_count\":0"));
  g_assert_nonnull (strstr (json,
                            "\"reentry_recovery_a2_oem_equivalence\":false"));
  g_assert_nonnull (strstr (json,
                            "\"reentry_recovery_a2_project_policy\":true"));
  g_assert_nonnull (strstr (json, "\"a8_submit_count\":1"));
  g_assert_nonnull (strstr (json, "\"a8_app12509_pin_match\":true"));
  g_assert_nonnull (strstr (json, "\"e4_submit_count\":1"));
  g_assert_null (strstr (json, "8081828384858687"));
  g_assert_null (strstr (json, "/var/lib/goodix-5125-poc"));
  g_assert_null (strstr (json, "psk"));
  goodix_d278_telemetry_init (&boundary, FALSE);
  g_strlcpy (boundary.result, "fail", sizeof boundary.result);
  g_strlcpy (boundary.failure_class, "PRE_USB_GATE",
             sizeof boundary.failure_class);
  boundary_json = goodix_d278_boundary_telemetry_to_json (&boundary);
  g_assert_nonnull (strstr (boundary_json, "\"phase_trace\":\"\""));
  g_assert_nonnull (strstr (boundary_json, "\"real_usb_access\":0"));
  g_assert_nonnull (strstr (boundary_json,
                            "\"usb_open_attempt_count\":0"));
  g_assert_null (strstr (boundary_json, "psk"));
  harness_fixture_free (fixture);

  /* A future first rejected E4 frame is causally classifiable without
   * retaining validator, PSK, CONFIG90 or any raw payload. */
  fixture = harness_fixture_new ();
  harness_advance_to (fixture, GOODIX_SECURE_PHASE_E4);
  {
    HarnessSubmission *submission = harness_pop_out (fixture);
    g_autoptr(GBytes) rejected = harness_build_ack_status (0xe4, 0x02);
    gsize length;
    const guint8 *data;

    goodix_d278_harness_complete_out (fixture->harness,
                                      submission->generation, NULL);
    harness_submission_free (submission);
    data = g_bytes_get_data (rejected, &length);
    goodix_d278_harness_complete_receive (fixture->harness,
                                          fixture->generation,
                                          data, length, NULL);
  }
  g_assert_true (goodix_d278_harness_is_terminal (fixture->harness));
  harness_fixture_drain_and_seal (fixture);
  g_clear_pointer (&json, g_free);
  json = goodix_d278_telemetry_to_json (fixture->harness,
                                        &fixture->telemetry);
  g_assert_nonnull (strstr (json, "\"protocol_failure_phase\":\"E4\""));
  g_assert_nonnull (strstr (json,
                            "\"protocol_failure_kind\":\"ACK_STATUS_REJECTED\""));
  g_assert_nonnull (strstr (json, "\"observed_outer_type\":160"));
  g_assert_nonnull (strstr (json, "\"observed_a0_control\":176"));
  g_assert_nonnull (strstr (json, "\"observed_ack_echo\":228"));
  g_assert_nonnull (strstr (json, "\"observed_ack_status\":2"));
  g_assert_nonnull (strstr (json, "\"observed_body_length\":2"));
  g_assert_null (strstr (json, "8081828384858687"));
  g_assert_null (strstr (json, "/var/lib/goodix-5125-poc"));
  g_assert_null (strstr (json, "psk"));
  harness_fixture_free (fixture);
}

static void
test_harness_live_mode_build_only (void)
{
  g_autofree gchar *source = NULL;
  gsize length = 0;

  g_assert_true (g_file_get_contents (
    "tools/d278_native_secure_session_once.c", &source, &length, NULL));
  g_assert_cmpuint (length, >, 0);
  g_assert_nonnull (strstr (source, "#ifdef D278_LIVE_BINDING"));
  g_assert_nonnull (strstr (source, "--live-exact-secure-session"));
  g_assert_nonnull (strstr (source, "run_live_once"));
}

int
main (int argc,
      char **argv)
{
  static const gchar *const kat_names[] = {
    "v0", "v1", "v2", "v3", "v4"
  };
  static const gchar *const pe_pattern_names[] = {
    "wrong", "ambiguous"
  };
  static const gchar *const preflight_names[] = {
    "success_redacted", "protected_open", "protected_metadata",
    "protected_content", "canonical_pe", "e4_binding"
  };
  static const struct
  {
    const gchar *name;
    MaterialMutation mutation;
  } material_mutations[] = {
    { "transport_length_rejected", MATERIAL_MUT_TRANSPORT_LENGTH },
    { "transport_magic_rejected", MATERIAL_MUT_TRANSPORT_MAGIC },
    { "transport_hash_rejected", MATERIAL_MUT_TRANSPORT_HASH },
    { "config_length_rejected", MATERIAL_MUT_CONFIG_LENGTH },
    { "config_hash_rejected", MATERIAL_MUT_CONFIG_HASH },
    { "config_finalizer_rejected", MATERIAL_MUT_CONFIG_FINALIZER },
    { "dac_0220_rejected", MATERIAL_MUT_DAC_0220 },
    { "dac_0236_rejected", MATERIAL_MUT_DAC_0236 },
    { "dac_0238_rejected", MATERIAL_MUT_DAC_0238 },
    { "dac_023a_rejected", MATERIAL_MUT_DAC_023A },
    { "dac_order_rejected", MATERIAL_MUT_DAC_ORDER },
    { "e4_pin_rejected", MATERIAL_MUT_E4_PIN },
  };

  g_test_init (&argc, &argv, NULL);
  for (guint i = 0; i < G_N_ELEMENTS (kat_names); i++)
    {
      g_autofree gchar *path = g_strdup_printf ("/d278_02/d190/kat_%s",
                                                kat_names[i]);
      g_test_add_data_func (path, GUINT_TO_POINTER (i), test_binder_kat);
    }
  g_test_add_func ("/d278_02/d190/argument_and_output_zeroization",
                   test_binder_argument_validation);
  g_test_add_func ("/d278_02/pe/canonical", test_pe_canonical);
  g_test_add_func ("/d278_02/pe/wrong_hash", test_pe_wrong_hash);
  g_test_add_func ("/d278_02/pe/malformed", test_pe_malformed);
  for (guint i = 0; i < G_N_ELEMENTS (pe_pattern_names); i++)
    {
      g_autofree gchar *path = g_strdup_printf ("/d278_02/pe/%s_pattern",
                                                pe_pattern_names[i]);
      g_test_add_data_func (path, GUINT_TO_POINTER (i),
                            test_pe_pattern_negative);
    }
  g_test_add_func ("/d278_02/pe/bounded_offsets", test_pe_bounded_offset);

  g_test_add_func ("/d278_02/material/production_policy",
                   test_material_production_policy);
  g_test_add_func ("/d278_02/material/production_policy_canonical_pins",
                   test_material_production_policy_canonical_pins);
  g_test_add_func ("/d278_02/material/positive", test_material_positive);
  g_test_add_func ("/d278_02/material/symlink_rejected",
                   test_material_symlink);
  g_test_add_func ("/d278_02/material/not_regular_rejected",
                   test_material_not_regular);
  g_test_add_func ("/d278_02/material/wrong_mode_rejected",
                   test_material_wrong_mode);
  g_test_add_func ("/d278_02/material/wrong_owner_policy_rejected",
                   test_material_wrong_owner_policy);
  g_test_add_func ("/d278_02/material/change_during_read_rejected",
                   test_material_change_during_read);
  for (guint i = 0; i < G_N_ELEMENTS (material_mutations); i++)
    {
      g_autofree gchar *path = g_strdup_printf ("/d278_02/material/%s",
                                                material_mutations[i].name);
      g_test_add_data_func (path,
                            GUINT_TO_POINTER (material_mutations[i].mutation),
                            test_material_mutation);
    }
  g_test_add_func ("/d278_02/material/one_owner_lifetime",
                   test_material_one_owner_lifetime);
  g_test_add_func ("/d278_02/material/psk_scratch_cleansed",
                   test_material_psk_scratch_cleansed);
  g_test_add_func ("/d278_02/material/failure_path_cleansed",
                   test_material_failure_path_cleansed);
  for (guint i = 0; i < G_N_ELEMENTS (preflight_names); i++)
    {
      g_autofree gchar *path = g_strdup_printf (
        "/d278_02/preflight/%s", preflight_names[i]);
      g_test_add_data_func (path, GUINT_TO_POINTER (i),
                            test_preflight_observability);
    }
  g_test_add_func ("/d278_02/preflight/material_export_state_mapping",
                   test_preflight_material_export_state_mapping);

  g_test_add_func ("/d278_02/harness/material_failure_before_open",
                   test_harness_material_failure_before_open);
  g_test_add_func ("/d278_02/harness/synthetic_single_open_claim",
                   test_harness_synthetic_single_open_claim);
  g_test_add_func ("/d278_02/harness/full_secure_session_to_stop",
                   test_harness_full_secure_session_to_stop);
  g_test_add_func ("/d278_02/harness/phase_watchdog_reentry_recovery_a2",
                   test_harness_phase_watchdog_reentry_recovery_a2);
  g_test_add_func ("/d278_02/harness/phase_watchdog_pre_d1",
                   test_harness_phase_watchdog_pre_d1);
  g_test_add_func ("/d278_02/harness/phase_watchdog_tls",
                   test_harness_phase_watchdog_tls);
  g_test_add_func ("/d278_02/harness/watchdog_cancelled_on_progress",
                   test_harness_watchdog_cancelled_on_progress);
  g_test_add_func ("/d278_02/harness/watchdog_invalidated_on_terminal",
                   test_harness_watchdog_invalidated_on_terminal);
  g_test_add_func ("/d278_02/harness/drain_before_free",
                   test_harness_drain_before_free);
  g_test_add_func ("/d278_02/harness/stale_receive_after_terminal",
                   test_harness_stale_receive_after_terminal);
  g_test_add_func ("/d278_02/harness/stale_out_after_terminal",
                   test_harness_stale_out_after_terminal);
  g_test_add_func ("/d278_02/harness/max_one_in", test_harness_max_one_in);
  g_test_add_func ("/d278_02/harness/max_one_out", test_harness_max_one_out);
  g_test_add_func ("/d278_02/harness/no_retry", test_harness_no_retry);
  g_test_add_func ("/d278_02/harness/no_reopen", test_harness_no_reopen);
  g_test_add_func ("/d278_02/harness/no_reset", test_harness_no_reset);
  g_test_add_func ("/d278_02/harness/d4_unreachable",
                   test_harness_d4_unreachable);
  g_test_add_func ("/d278_02/harness/application_data_out_of_scope",
                   test_harness_application_data_out_of_scope);
  g_test_add_func ("/d278_02/harness/redacted_telemetry",
                   test_harness_redacted_telemetry);
  g_test_add_func ("/d278_02/harness/live_mode_build_only",
                   test_harness_live_mode_build_only);
  return g_test_run ();
}
