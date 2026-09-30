/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_pairing_crypto.h"

#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/rand.h>

#include <string.h>

typedef struct
{
  const gchar *name;
  guint8 mode;
  const gchar *secret_hex;
  const gchar *validator_hex;
} Kat;

static const Kat kats[] = {
  { "V0", 0x00, NULL,
    "b5e0beeb94c84eb99b883abd5c251073c56b91035c562a91a46c7f3349c36c89" },
  { "V1", 0x01, NULL,
    "e51d069d67065a052307d3bd6dd8edf377e8b2389dc309475891e415e5f2148c" },
  { "V2", 0xff, NULL,
    "d1ba9a4790f8d47ba8b50043d72b577cdc2d1b701d466197aa741a94fd0f1ec4" },
  { "V3", 0xaa, NULL,
    "ea43b0f9a2eae84d55fa9b0a961c35b7dd8e5c2594e5e4562c92c3f198a19209" },
  { "V4", 0xfe,
    "31dc314296631fa52db5a09e625f74d43f5420455a214272ab444f84393e8d5a",
    "af13a21ec8f8250b47da268f32ef74cd0ff5dbc0f8b48b93ee5411e422e8a9b4" },
};

static const guint8 expected_v2_envelope[102] = {
  0x45, 0xa3, 0x73, 0x2a, 0xcf, 0x29, 0x90, 0xf4,
  0xce, 0xb3, 0x0e, 0x89, 0x96, 0xe4, 0xad, 0xd1,
  0x2e, 0x88, 0x71, 0x60, 0xd6, 0xdc, 0xaa, 0x99,
  0xc8, 0xbc, 0xd8, 0x33, 0x8c, 0x77, 0x43, 0xf2,
  0x02, 0xff, 0x20, 0x00, 0x00, 0x00, 0xe7, 0xbc,
  0x09, 0x96, 0x2a, 0xed, 0xfb, 0x47, 0x0f, 0xac,
  0x38, 0x87, 0xde, 0x32, 0x46, 0x5c, 0x5a, 0x71,
  0xc8, 0x8f, 0xe0, 0x1d, 0xd7, 0x76, 0xcf, 0xa5,
  0x19, 0xe7, 0x0c, 0x63, 0xf8, 0x24, 0x01, 0xf8,
  0x24, 0x73, 0x24, 0xfd, 0xe9, 0xc6, 0x56, 0x23,
  0x21, 0xd4, 0xd8, 0x2b, 0x0d, 0xd5, 0x52, 0xc0,
  0xbf, 0x1f, 0x74, 0x71, 0x60, 0x85, 0xb8, 0x52,
  0x65, 0x8b, 0xfe, 0x77, 0x29, 0x64
};

static void
fill_secret (const Kat *kat,
             guint8     secret[32])
{
  if (kat->secret_hex != NULL)
    {
      for (guint i = 0; i < 32; i++)
        {
          gchar byte[3] = { kat->secret_hex[i * 2u],
                            kat->secret_hex[i * 2u + 1u], 0 };
          secret[i] = (guint8) g_ascii_strtoull (byte, NULL, 16);
        }
    }
  else if (kat->mode == 0xff)
    for (guint i = 0; i < 32; i++)
      secret[i] = (guint8) i;
  else if (kat->mode == 0xaa)
    for (guint i = 0; i < 32; i++)
      secret[i] = (i % 2u) == 0u ? 0xaa : 0x55;
  else
    memset (secret, kat->mode, 32);
}

static void
parse_hex_32 (const gchar *hex,
              guint8       output[32])
{
  g_assert_cmpuint (strlen (hex), ==, 64u);
  for (guint i = 0; i < 32; i++)
    {
      gchar byte[3] = { hex[i * 2u], hex[i * 2u + 1u], 0 };

      output[i] = (guint8) g_ascii_strtoull (byte, NULL, 16);
    }
}

static void
sha256 (const guint8 *input,
        gsize         length,
        guint8        output[32])
{
  EVP_MD_CTX *context = EVP_MD_CTX_new ();
  unsigned int output_length = 0;

  g_assert_nonnull (context);
  g_assert_cmpint (EVP_DigestInit_ex (context, EVP_sha256 (), NULL), ==, 1);
  g_assert_cmpint (EVP_DigestUpdate (context, input, length), ==, 1);
  g_assert_cmpint (EVP_DigestFinal_ex (context, output, &output_length), ==, 1);
  g_assert_cmpuint (output_length, ==, 32u);
  EVP_MD_CTX_free (context);
}

static void
assert_rejected (const guint8 psk[32],
                 const guint8 envelope[102],
                 const guint8 validator[32])
{
  GError *error = NULL;

  g_assert_false (goodix_pairing_crypto_validate (psk, 32, envelope, 102,
                                                   validator, 32, &error));
  g_assert_error (error, GOODIX_PAIRING_CRYPTO_ERROR,
                  GOODIX_PAIRING_CRYPTO_ERROR_MISMATCH);
  g_clear_error (&error);
}

static void
test_five_oem_oracle_kats (void)
{
  for (guint vector = 0; vector < G_N_ELEMENTS (kats); vector++)
    {
      guint8 secret[32] = { 0 };
      guint8 envelope[102] = { 0 };
      guint8 validator[32] = { 0 };
      guint8 expected[32] = { 0 };
      GError *error = NULL;

      g_test_message ("checking %s", kats[vector].name);
      fill_secret (&kats[vector], secret);
      parse_hex_32 (kats[vector].validator_hex, expected);
      g_assert_true (goodix_pairing_crypto_derive (secret, sizeof secret,
                                                   envelope, validator,
                                                   &error));
      g_assert_no_error (error);
      g_assert_cmpmem (validator, sizeof validator, expected, sizeof expected);
      g_assert_true (goodix_pairing_crypto_validate (secret, sizeof secret,
                                                     envelope, sizeof envelope,
                                                     validator,
                                                     sizeof validator, &error));
      g_assert_no_error (error);
      OPENSSL_cleanse (secret, sizeof secret);
      OPENSSL_cleanse (envelope, sizeof envelope);
      OPENSSL_cleanse (validator, sizeof validator);
      OPENSSL_cleanse (expected, sizeof expected);
    }
}

static void
test_qualified_bb010003_and_bb020003 (void)
{
  guint8 secret[32];
  guint8 envelope[102] = { 0 };
  guint8 validator[32] = { 0 };
  guint8 expected_validator[32] = { 0 };
  GError *error = NULL;

  for (guint i = 0; i < 32; i++)
    secret[i] = (guint8) i;
  parse_hex_32 (kats[2].validator_hex, expected_validator);
  g_assert_true (goodix_pairing_crypto_derive (secret, sizeof secret,
                                               envelope, validator, &error));
  g_assert_no_error (error);
  g_assert_cmpmem (envelope, sizeof envelope,
                   expected_v2_envelope, sizeof expected_v2_envelope);
  g_assert_cmpmem (validator, sizeof validator,
                   expected_validator, sizeof expected_validator);
}

static void
test_random_psks_are_deterministic (void)
{
  for (guint iteration = 0; iteration < 32; iteration++)
    {
      guint8 secret[32] = { 0 };
      guint8 envelope_a[102] = { 0 };
      guint8 envelope_b[102] = { 0 };
      guint8 validator_a[32] = { 0 };
      guint8 validator_b[32] = { 0 };
      GError *error = NULL;

      g_assert_cmpint (RAND_bytes (secret, sizeof secret), ==, 1);
      g_assert_true (goodix_pairing_crypto_derive (secret, sizeof secret,
                                                   envelope_a, validator_a,
                                                   &error));
      g_assert_no_error (error);
      g_assert_true (goodix_pairing_crypto_derive (secret, sizeof secret,
                                                   envelope_b, validator_b,
                                                   &error));
      g_assert_no_error (error);
      g_assert_cmpmem (envelope_a, sizeof envelope_a,
                       envelope_b, sizeof envelope_b);
      g_assert_cmpmem (validator_a, sizeof validator_a,
                       validator_b, sizeof validator_b);
      g_assert_true (goodix_pairing_crypto_validate (secret, sizeof secret,
                                                     envelope_a,
                                                     sizeof envelope_a,
                                                     validator_a,
                                                     sizeof validator_a,
                                                     &error));
      g_assert_no_error (error);
      OPENSSL_cleanse (secret, sizeof secret);
    }
}

static void
test_negative_profile_and_envelope_kats (void)
{
  static const guint8 fixed_key[32] = {
    0x5c, 0xba, 0x6e, 0x25, 0x81, 0x95, 0x18, 0xde,
    0x2d, 0x53, 0xe9, 0x6d, 0xc0, 0x34, 0x7a, 0xb0,
    0xd4, 0x27, 0xd4, 0x08, 0x4b, 0xda, 0x4f, 0xae,
    0x1b, 0xff, 0x2b, 0x09, 0x11, 0x2a, 0x57, 0xe5
  };
  static const guint8 fixed_aad[16] = {
    0x52, 0x2d, 0xc1, 0xf0, 0x99, 0x56, 0x7d, 0x07,
    0xf4, 0x7f, 0x37, 0xa3, 0x2a, 0x84, 0x42, 0x7d
  };
  static const guint8 fixed_header[6] = { 0x02, 0xff, 0x20, 0, 0, 0 };
  guint8 secret[32];
  guint8 key[32];
  guint8 aad[16];
  guint8 header[6];
  guint8 envelope[102] = { 0 };
  guint8 validator[32] = { 0 };
  GError *error = NULL;

  for (guint i = 0; i < 32; i++)
    secret[i] = (guint8) i;

  memcpy (key, fixed_key, sizeof key);
  key[0] ^= 1u;
  g_assert_true (goodix_pairing_crypto_derive_profile_for_test (
    secret, sizeof secret, key, sizeof key, fixed_aad, sizeof fixed_aad,
    fixed_header, sizeof fixed_header, envelope, validator, &error));
  g_assert_no_error (error);
  assert_rejected (secret, envelope, validator);

  memcpy (aad, fixed_aad, sizeof aad);
  aad[0] ^= 1u;
  g_assert_true (goodix_pairing_crypto_derive_profile_for_test (
    secret, sizeof secret, fixed_key, sizeof fixed_key, aad, sizeof aad,
    fixed_header, sizeof fixed_header, envelope, validator, &error));
  g_assert_no_error (error);
  assert_rejected (secret, envelope, validator);

  memcpy (header, fixed_header, sizeof header);
  header[0] ^= 1u;
  g_assert_true (goodix_pairing_crypto_derive_profile_for_test (
    secret, sizeof secret, fixed_key, sizeof fixed_key,
    fixed_aad, sizeof fixed_aad, header, sizeof header,
    envelope, validator, &error));
  g_assert_no_error (error);
  assert_rejected (secret, envelope, validator);

  g_assert_true (goodix_pairing_crypto_derive (secret, sizeof secret,
                                               envelope, validator, &error));
  g_assert_no_error (error);
  for (guint mutation = 0; mutation < 4; mutation++)
    {
      static const gsize offsets[] = { 0u, 38u, 54u, 86u };
      guint8 changed[102];
      guint8 changed_validator[32];

      memcpy (changed, envelope, sizeof changed);
      changed[offsets[mutation]] ^= 1u;
      sha256 (changed, sizeof changed, changed_validator);
      assert_rejected (secret, changed, changed_validator);
    }

  validator[0] ^= 1u;
  assert_rejected (secret, envelope, validator);
}

static void
test_invalid_lengths_clear_outputs (void)
{
  guint8 secret[32] = { 0 };
  guint8 envelope[102];
  guint8 validator[32];
  guint8 zero_envelope[102] = { 0 };
  guint8 zero_validator[32] = { 0 };
  GError *error = NULL;

  memset (envelope, 0xa5, sizeof envelope);
  memset (validator, 0xa5, sizeof validator);
  g_assert_false (goodix_pairing_crypto_derive (secret, 31, envelope,
                                                 validator, &error));
  g_assert_error (error, GOODIX_PAIRING_CRYPTO_ERROR,
                  GOODIX_PAIRING_CRYPTO_ERROR_ARGUMENT);
  g_assert_cmpmem (envelope, sizeof envelope,
                   zero_envelope, sizeof zero_envelope);
  g_assert_cmpmem (validator, sizeof validator,
                   zero_validator, sizeof zero_validator);
  g_clear_error (&error);
  g_assert_false (goodix_pairing_crypto_validate (secret, sizeof secret,
                                                   envelope, 101,
                                                   validator,
                                                   sizeof validator, &error));
  g_assert_error (error, GOODIX_PAIRING_CRYPTO_ERROR,
                  GOODIX_PAIRING_CRYPTO_ERROR_ARGUMENT);
  g_clear_error (&error);
}

int
main (int   argc,
      char *argv[])
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/pairing-crypto/oem-oracle-kats",
                   test_five_oem_oracle_kats);
  g_test_add_func ("/pairing-crypto/qualified-bb010003-bb020003",
                   test_qualified_bb010003_and_bb020003);
  g_test_add_func ("/pairing-crypto/random-determinism",
                   test_random_psks_are_deterministic);
  g_test_add_func ("/pairing-crypto/negative-profile-envelope-kats",
                   test_negative_profile_and_envelope_kats);
  g_test_add_func ("/pairing-crypto/invalid-lengths-clear",
                   test_invalid_lengths_clear_outputs);
  return g_test_run ();
}
