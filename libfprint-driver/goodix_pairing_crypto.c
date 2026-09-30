/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (c) 2026 sorguido
 *
 * Pure APP12509 pairing cryptography.  This is a focused refactor of the
 * project-authored D190 implementation in goodix_action_binding.c.  The fixed
 * producer key and AAD are protocol constants qualified against the five D190
 * OEM-oracle KATs and the project-authored single-write PoC.  No Rockytkg or
 * OEM source expression is copied here.
 */
#include "goodix_pairing_crypto.h"

#include <openssl/core_names.h>
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/params.h>

#include <string.h>

static const guint8 app12509_kdf_key[32] = {
  0x5c, 0xba, 0x6e, 0x25, 0x81, 0x95, 0x18, 0xde,
  0x2d, 0x53, 0xe9, 0x6d, 0xc0, 0x34, 0x7a, 0xb0,
  0xd4, 0x27, 0xd4, 0x08, 0x4b, 0xda, 0x4f, 0xae,
  0x1b, 0xff, 0x2b, 0x09, 0x11, 0x2a, 0x57, 0xe5
};

static const guint8 app12509_aad[16] = {
  0x52, 0x2d, 0xc1, 0xf0, 0x99, 0x56, 0x7d, 0x07,
  0xf4, 0x7f, 0x37, 0xa3, 0x2a, 0x84, 0x42, 0x7d
};

static const guint8 app12509_header[6] = {
  0x02, 0xff, 0x20, 0x00, 0x00, 0x00
};

GQuark
goodix_pairing_crypto_error_quark (void)
{
  return g_quark_from_static_string ("goodix-pairing-crypto-error");
}

static gboolean
sha256_parts (const guint8 *const *parts,
              const gsize         *lengths,
              gsize                count,
              guint8               output[32])
{
  EVP_MD_CTX *context = EVP_MD_CTX_new ();
  gboolean ok = FALSE;

  if (context == NULL || EVP_DigestInit_ex (context, EVP_sha256 (), NULL) != 1)
    goto out;
  for (gsize i = 0; i < count; i++)
    if (EVP_DigestUpdate (context, parts[i], lengths[i]) != 1)
      goto out;
  {
    unsigned int output_length = 0;

    if (EVP_DigestFinal_ex (context, output, &output_length) != 1 ||
        output_length != 32u)
      goto out;
  }
  ok = TRUE;
out:
  EVP_MD_CTX_free (context);
  return ok;
}

static gboolean
hmac_sha256_parts (const guint8 *key,
                   gsize         key_length,
                   const guint8 *const *parts,
                   const gsize  *lengths,
                   gsize         count,
                   guint8        output[32])
{
  EVP_MAC *mac = NULL;
  EVP_MAC_CTX *context = NULL;
  OSSL_PARAM params[2];
  gchar digest_name[] = "SHA256";
  size_t output_length = 0;
  gboolean ok = FALSE;

  mac = EVP_MAC_fetch (NULL, "HMAC", NULL);
  if (mac == NULL)
    goto out;
  context = EVP_MAC_CTX_new (mac);
  if (context == NULL)
    goto out;
  params[0] = OSSL_PARAM_construct_utf8_string (OSSL_MAC_PARAM_DIGEST,
                                                 digest_name, 0);
  params[1] = OSSL_PARAM_construct_end ();
  if (EVP_MAC_init (context, key, key_length, params) != 1)
    goto out;
  for (gsize i = 0; i < count; i++)
    if (EVP_MAC_update (context, parts[i], lengths[i]) != 1)
      goto out;
  if (EVP_MAC_final (context, output, &output_length, 32) != 1 ||
      output_length != 32u)
    goto out;
  ok = TRUE;
out:
  EVP_MAC_CTX_free (context);
  EVP_MAC_free (mac);
  return ok;
}

static gboolean
aes256_gcm_encrypt (const guint8 key[32],
                    const guint8 nonce[16],
                    const guint8 aad[16],
                    const guint8 plaintext[32],
                    guint8       ciphertext[32],
                    guint8       tag[16])
{
  EVP_CIPHER_CTX *context = EVP_CIPHER_CTX_new ();
  int count = 0;
  int total = 0;
  gboolean ok = FALSE;

  if (context == NULL ||
      EVP_EncryptInit_ex (context, EVP_aes_256_gcm (), NULL, NULL, NULL) != 1 ||
      EVP_CIPHER_CTX_ctrl (context, EVP_CTRL_GCM_SET_IVLEN, 16, NULL) != 1 ||
      EVP_EncryptInit_ex (context, NULL, NULL, key, nonce) != 1 ||
      EVP_EncryptUpdate (context, NULL, &count, aad, 16) != 1 ||
      EVP_EncryptUpdate (context, ciphertext, &count, plaintext, 32) != 1)
    goto out;
  total = count;
  if (EVP_EncryptFinal_ex (context, ciphertext + total, &count) != 1)
    goto out;
  total += count;
  if (total != 32 ||
      EVP_CIPHER_CTX_ctrl (context, EVP_CTRL_GCM_GET_TAG, 16, tag) != 1)
    goto out;
  ok = TRUE;
out:
  EVP_CIPHER_CTX_free (context);
  return ok;
}

static gboolean
derive_profile (const guint8 psk[32],
                const guint8 kdf_key[32],
                const guint8 aad[16],
                const guint8 header[6],
                guint8       envelope[102],
                guint8       validator[32])
{
  static const guint8 label[] = {
    'k', 'g', 'o', 'o', 'd', 'w', 'i', 'x', 'g', 0,
    'k', 'a', 'e', 'l', 'r', 'g', 'n', 'o', 'e', 'r', 'l', 'i', 't', 'h', 'm'
  };
  static const guint8 length_be[4] = { 0x00, 0x00, 0x01, 0x80 };
  static const guint8 word_three[4] = { 0x03, 0x00, 0x00, 0x00 };
  guint8 derived[48] = { 0 };
  guint8 digest[32] = { 0 };
  guint8 nonce[16] = { 0 };
  guint8 ciphertext[32] = { 0 };
  guint8 tag[16] = { 0 };
  guint8 outer[32] = { 0 };
  guint8 counter[4] = { 0 };
  const guint8 *parts[18];
  gsize lengths[18];
  gboolean ok = FALSE;

  parts[1] = label;
  lengths[1] = sizeof label;
  parts[2] = length_be;
  lengths[2] = sizeof length_be;
  for (guint round = 1; round <= 2; round++)
    {
      counter[3] = (guint8) round;
      parts[0] = counter;
      lengths[0] = sizeof counter;
      if (!hmac_sha256_parts (kdf_key, 32, parts, lengths, 3, digest))
        goto out;
      memcpy (derived + ((round - 1u) * 32u), digest,
              round == 1u ? 32u : 16u);
      OPENSSL_cleanse (digest, sizeof digest);
    }

  parts[0] = header;
  lengths[0] = 6;
  parts[1] = psk;
  lengths[1] = 8;
  for (guint i = 0; i < 16; i++)
    {
      parts[2u + i] = word_three;
      lengths[2u + i] = sizeof word_three;
    }
  if (!sha256_parts (parts, lengths, 18, digest))
    goto out;
  memcpy (nonce, digest, sizeof nonce);
  OPENSSL_cleanse (digest, sizeof digest);

  if (!aes256_gcm_encrypt (derived, nonce, aad, psk, ciphertext, tag))
    goto out;
  parts[0] = header;
  lengths[0] = 6;
  parts[1] = ciphertext;
  lengths[1] = sizeof ciphertext;
  parts[2] = tag;
  lengths[2] = sizeof tag;
  if (!hmac_sha256_parts (derived + 16, 32, parts, lengths, 3, outer))
    goto out;

  memcpy (envelope, outer, 32);
  memcpy (envelope + 32, header, 6);
  memcpy (envelope + 38, nonce, 16);
  memcpy (envelope + 54, ciphertext, 32);
  memcpy (envelope + 86, tag, 16);
  parts[0] = envelope;
  lengths[0] = 102;
  if (!sha256_parts (parts, lengths, 1, validator))
    goto out;
  ok = TRUE;

out:
  OPENSSL_cleanse (derived, sizeof derived);
  OPENSSL_cleanse (digest, sizeof digest);
  OPENSSL_cleanse (nonce, sizeof nonce);
  OPENSSL_cleanse (ciphertext, sizeof ciphertext);
  OPENSSL_cleanse (tag, sizeof tag);
  OPENSSL_cleanse (outer, sizeof outer);
  OPENSSL_cleanse (counter, sizeof counter);
  return ok;
}

static gboolean
derive_checked (const guint8 *psk,
                gsize         psk_length,
                const guint8 *kdf_key,
                gsize         kdf_key_length,
                const guint8 *aad,
                gsize         aad_length,
                const guint8 *header,
                gsize         header_length,
                guint8       *envelope,
                guint8       *validator,
                GError      **error)
{
  gboolean ok = FALSE;

  if (envelope != NULL)
    OPENSSL_cleanse (envelope, GOODIX_PAIRING_ENVELOPE_LENGTH);
  if (validator != NULL)
    OPENSSL_cleanse (validator, GOODIX_PAIRING_VALIDATOR_LENGTH);
  if (psk == NULL || psk_length != GOODIX_PAIRING_PSK_LENGTH ||
      kdf_key == NULL || kdf_key_length != 32u ||
      aad == NULL || aad_length != 16u ||
      header == NULL || header_length != 6u ||
      envelope == NULL || validator == NULL)
    {
      g_set_error_literal (error, GOODIX_PAIRING_CRYPTO_ERROR,
                           GOODIX_PAIRING_CRYPTO_ERROR_ARGUMENT,
                           "pairing crypto requires exact fixed-size inputs and outputs");
      goto out;
    }
  if (!derive_profile (psk, kdf_key, aad, header, envelope, validator))
    {
      g_set_error_literal (error, GOODIX_PAIRING_CRYPTO_ERROR,
                           GOODIX_PAIRING_CRYPTO_ERROR_CRYPTO,
                           "APP12509 pairing derivation failed");
      goto out;
    }
  ok = TRUE;
out:
  if (!ok)
    {
      if (envelope != NULL)
        OPENSSL_cleanse (envelope, GOODIX_PAIRING_ENVELOPE_LENGTH);
      if (validator != NULL)
        OPENSSL_cleanse (validator, GOODIX_PAIRING_VALIDATOR_LENGTH);
    }
  return ok;
}

gboolean
goodix_pairing_crypto_derive (const guint8 psk[32],
                              gsize        psk_length,
                              guint8       envelope[102],
                              guint8       validator[32],
                              GError     **error)
{
  return derive_checked (psk, psk_length,
                         app12509_kdf_key, sizeof app12509_kdf_key,
                         app12509_aad, sizeof app12509_aad,
                         app12509_header, sizeof app12509_header,
                         envelope, validator, error);
}

gboolean
goodix_pairing_crypto_validate (const guint8 psk[32],
                                gsize        psk_length,
                                const guint8 envelope[102],
                                gsize        envelope_length,
                                const guint8 validator[32],
                                gsize        validator_length,
                                GError     **error)
{
  guint8 expected_envelope[102] = { 0 };
  guint8 expected_validator[32] = { 0 };
  int envelope_difference;
  int validator_difference;
  gboolean ok = FALSE;

  if (envelope == NULL || envelope_length != sizeof expected_envelope ||
      validator == NULL || validator_length != sizeof expected_validator)
    {
      g_set_error_literal (error, GOODIX_PAIRING_CRYPTO_ERROR,
                           GOODIX_PAIRING_CRYPTO_ERROR_ARGUMENT,
                           "pairing validation requires envelope[102] and validator[32]");
      goto out;
    }
  if (!goodix_pairing_crypto_derive (psk, psk_length, expected_envelope,
                                     expected_validator, error))
    goto out;
  envelope_difference = CRYPTO_memcmp (envelope, expected_envelope,
                                       sizeof expected_envelope);
  validator_difference = CRYPTO_memcmp (validator, expected_validator,
                                        sizeof expected_validator);
  if ((envelope_difference | validator_difference) != 0)
    {
      g_set_error_literal (error, GOODIX_PAIRING_CRYPTO_ERROR,
                           GOODIX_PAIRING_CRYPTO_ERROR_MISMATCH,
                           "pairing envelope or validator mismatch");
      goto out;
    }
  ok = TRUE;
out:
  OPENSSL_cleanse (expected_envelope, sizeof expected_envelope);
  OPENSSL_cleanse (expected_validator, sizeof expected_validator);
  return ok;
}

#ifdef GOODIX_ENABLE_TEST_SEAMS
gboolean
goodix_pairing_crypto_derive_profile_for_test (const guint8 psk[32],
                                               gsize        psk_length,
                                               const guint8 kdf_key[32],
                                               gsize        kdf_key_length,
                                               const guint8 aad[16],
                                               gsize        aad_length,
                                               const guint8 header[6],
                                               gsize        header_length,
                                               guint8       envelope[102],
                                               guint8       validator[32],
                                               GError     **error)
{
  return derive_checked (psk, psk_length, kdf_key, kdf_key_length,
                         aad, aad_length, header, header_length,
                         envelope, validator, error);
}
#endif
