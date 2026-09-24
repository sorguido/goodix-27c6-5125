/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (c) 2026 sorguido
 *
 * Native D190 cryptographic binding only.  This is a bounded C adaptation of
 * the project-authored BSD-2-Clause D190 reference at commit
 * b475a6eca72e340816779afae917334a6146c986, source path
 * poc/goodix5125/tools/binding_reference/crypto_reference.py.  Filesystem,
 * PE, protected-store, USB and orchestration concerns deliberately remain
 * outside this LGPL unit.
 */
#include "goodix_action_binding.h"

#include <openssl/core_names.h>
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/params.h>

#include <string.h>

typedef enum
{
  GOODIX_D190_ERROR_ARGUMENT,
  GOODIX_D190_ERROR_CRYPTO,
} GoodixD190Error;

#define GOODIX_D190_ERROR (goodix_d190_error_quark ())

static GQuark
goodix_d190_error_quark (void)
{
  return g_quark_from_static_string ("goodix-d190-error");
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
aes_ecb_block (const guint8 *key,
               gsize         key_length,
               const guint8  input[16],
               gboolean      decrypt,
               guint8        output[16])
{
  const EVP_CIPHER *cipher = NULL;
  EVP_CIPHER_CTX *context = NULL;
  int first = 0;
  int final = 0;
  gboolean ok = FALSE;

  if (key_length == 16)
    cipher = EVP_aes_128_ecb ();
  else if (key_length == 24)
    cipher = EVP_aes_192_ecb ();
  else if (key_length == 32)
    cipher = EVP_aes_256_ecb ();
  else
    return FALSE;
  context = EVP_CIPHER_CTX_new ();
  if (context == NULL ||
      EVP_CipherInit_ex (context, cipher, NULL, key, NULL,
                         decrypt ? 0 : 1) != 1 ||
      EVP_CIPHER_CTX_set_padding (context, 0) != 1 ||
      EVP_CipherUpdate (context, output, &first, input, 16) != 1 ||
      EVP_CipherFinal_ex (context, output + first, &final) != 1 ||
      first + final != 16)
    goto out;
  ok = TRUE;
out:
  EVP_CIPHER_CTX_free (context);
  return ok;
}

static guint8
ror8 (guint8 value,
      guint  count)
{
  return (guint8) ((value >> count) | (guint8) (value << (8u - count)));
}

static guint32
d190_crc (const guint8 *data,
          gsize         length)
{
  guint32 value = 0xffffffffu;

  for (gsize i = 0; i < length; i++)
    {
      value ^= (guint32) data[i] << 24;
      for (guint bit = 0; bit < 8; bit++)
        value = (value << 1) ^ ((value & 0x80000000u) ? 0x04c11db7u : 0u);
    }
  return value;
}

static gboolean
derive_half (const guint8 seed[6],
             guint8       half[16])
{
  static const guint rotations[] = { 1, 3, 5, 7 };
  static const gsize key_lengths[] = { 16, 16, 32, 24 };
  static const gboolean decrypt[] = { TRUE, FALSE, TRUE, FALSE };
  static const guint8 hmac_key[16] = {
    '1', '2', '3', '4', '5', '6', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
  };
  guint8 expanded[24] = { 0 };
  guint8 block[16] = { 0 };
  guint8 transformed[16] = { 0 };
  guint8 zero_key[32] = { 0 };
  guint8 digest[32] = { 0 };
  const guint8 *parts[1];
  gsize lengths[1];
  guint32 crc;
  gboolean ok = FALSE;

  memset (half, 0, 16);
  for (guint rotation = 0; rotation < G_N_ELEMENTS (rotations); rotation++)
    for (guint i = 0; i < 6; i++)
      expanded[rotation * 6u + i] = ror8 (seed[i], rotations[rotation]);

  parts[0] = expanded;
  lengths[0] = 3;
  if (!sha256_parts (parts, lengths, 1, digest))
    goto out;
  memcpy (half, digest, 2);

  for (guint i = 0; i < 4; i++)
    {
      memset (block, 0xcc, sizeof block);
      memcpy (block, expanded + (i + 1u) * 3u, 3);
      memset (transformed, 0, sizeof transformed);
      if (!aes_ecb_block (zero_key, key_lengths[i], block, decrypt[i],
                          transformed))
        goto out;
      memcpy (half + 2u + i * 2u, transformed, 2);
      OPENSSL_cleanse (block, sizeof block);
      OPENSSL_cleanse (transformed, sizeof transformed);
    }

  parts[0] = expanded + 15;
  lengths[0] = 3;
  if (!hmac_sha256_parts (hmac_key, sizeof hmac_key, parts, lengths, 1,
                          digest))
    goto out;
  memcpy (half + 10, digest, 2);
  crc = d190_crc (expanded + 18, 3);
  half[12] = (guint8) (crc >> 24);
  half[13] = (guint8) (crc >> 16);
  parts[0] = expanded + 21;
  if (!sha256_parts (parts, lengths, 1, digest))
    goto out;
  memcpy (half + 14, digest, 2);
  ok = TRUE;

out:
  if (!ok)
    OPENSSL_cleanse (half, 16);
  OPENSSL_cleanse (expanded, sizeof expanded);
  OPENSSL_cleanse (block, sizeof block);
  OPENSSL_cleanse (transformed, sizeof transformed);
  OPENSSL_cleanse (zero_key, sizeof zero_key);
  OPENSSL_cleanse (digest, sizeof digest);
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

gboolean
goodix_d190_bind_validator (const guint8 secret[32],
                            gsize        secret_length,
                            const guint8 seed_a[6],
                            gsize        seed_a_length,
                            const guint8 seed_b[6],
                            gsize        seed_b_length,
                            guint8       validator[32],
                            GError     **error)
{
  static const guint8 fixed_aad[16] = {
    0x52, 0x2d, 0xc1, 0xf0, 0x99, 0x56, 0x7d, 0x07,
    0xf4, 0x7f, 0x37, 0xa3, 0x2a, 0x84, 0x42, 0x7d
  };
  static const guint8 label[] = {
    'k','g','o','o','d','w','i','x','g',0,
    'k','a','e','l','r','g','n','o','e','r','l','i','t','h','m'
  };
  static const guint8 header[6] = { 0x02, 0xff, 0x20, 0, 0, 0 };
  guint8 half_a[16] = { 0 };
  guint8 half_b[16] = { 0 };
  guint8 producer_key[32] = { 0 };
  guint8 derived[48] = { 0 };
  guint8 hmac_output[32] = { 0 };
  guint8 inner_input[78] = { 0 };
  guint8 nonce[16] = { 0 };
  guint8 ciphertext[32] = { 0 };
  guint8 tag[16] = { 0 };
  guint8 outer[32] = { 0 };
  guint8 envelope[102] = { 0 };
  guint8 counter[4];
  guint8 length_be[4] = { 0, 0, 0x01, 0x80 };
  const guint8 *parts[4];
  gsize lengths[4];
  gboolean ok = FALSE;

  if (validator != NULL)
    OPENSSL_cleanse (validator, 32);
  if (secret == NULL || seed_a == NULL || seed_b == NULL || validator == NULL ||
      secret_length != 32 || seed_a_length != 6 || seed_b_length != 6)
    {
      g_set_error_literal (error, GOODIX_D190_ERROR, GOODIX_D190_ERROR_ARGUMENT,
                           "D190 requires secret[32], seed_a[6], seed_b[6]");
      goto out;
    }
  if (!derive_half (seed_a, half_a) || !derive_half (seed_b, half_b))
    goto crypto_error;
  memcpy (producer_key, half_a, 16);
  memcpy (producer_key + 16, half_b, 16);

  parts[1] = label;
  lengths[1] = sizeof label;
  parts[2] = length_be;
  lengths[2] = sizeof length_be;
  for (guint round = 1; round <= 2; round++)
    {
      counter[0] = 0;
      counter[1] = 0;
      counter[2] = 0;
      counter[3] = (guint8) round;
      parts[0] = counter;
      lengths[0] = sizeof counter;
      if (!hmac_sha256_parts (producer_key, sizeof producer_key,
                              parts, lengths, 3, hmac_output))
        goto crypto_error;
      if (round == 1)
        memcpy (derived, hmac_output, 32);
      else
        memcpy (derived + 32, hmac_output, 16);
      OPENSSL_cleanse (hmac_output, sizeof hmac_output);
    }

  memcpy (inner_input, header, sizeof header);
  memcpy (inner_input + sizeof header, secret, 8);
  for (guint i = 0; i < 16; i++)
    {
      gsize offset = sizeof header + 8u + i * 4u;
      inner_input[offset] = 3;
    }
  parts[0] = inner_input;
  lengths[0] = sizeof inner_input;
  if (!sha256_parts (parts, lengths, 1, hmac_output))
    goto crypto_error;
  memcpy (nonce, hmac_output, sizeof nonce);
  OPENSSL_cleanse (hmac_output, sizeof hmac_output);
  if (!aes256_gcm_encrypt (derived, nonce, fixed_aad, secret,
                           ciphertext, tag))
    goto crypto_error;

  parts[0] = header;
  lengths[0] = sizeof header;
  parts[1] = ciphertext;
  lengths[1] = sizeof ciphertext;
  parts[2] = tag;
  lengths[2] = sizeof tag;
  if (!hmac_sha256_parts (derived + 16, 32, parts, lengths, 3, outer))
    goto crypto_error;
  memcpy (envelope, outer, 32);
  memcpy (envelope + 32, header, sizeof header);
  memcpy (envelope + 38, nonce, sizeof nonce);
  memcpy (envelope + 54, ciphertext, sizeof ciphertext);
  memcpy (envelope + 86, tag, sizeof tag);
  parts[0] = envelope;
  lengths[0] = sizeof envelope;
  if (!sha256_parts (parts, lengths, 1, validator))
    goto crypto_error;
  ok = TRUE;
  goto out;

crypto_error:
  g_set_error_literal (error, GOODIX_D190_ERROR, GOODIX_D190_ERROR_CRYPTO,
                       "D190 OpenSSL operation failed");
out:
  if (!ok && validator != NULL)
    OPENSSL_cleanse (validator, 32);
  OPENSSL_cleanse (half_a, sizeof half_a);
  OPENSSL_cleanse (half_b, sizeof half_b);
  OPENSSL_cleanse (producer_key, sizeof producer_key);
  OPENSSL_cleanse (derived, sizeof derived);
  OPENSSL_cleanse (hmac_output, sizeof hmac_output);
  OPENSSL_cleanse (inner_input, sizeof inner_input);
  OPENSSL_cleanse (nonce, sizeof nonce);
  OPENSSL_cleanse (ciphertext, sizeof ciphertext);
  OPENSSL_cleanse (tag, sizeof tag);
  OPENSSL_cleanse (outer, sizeof outer);
  OPENSSL_cleanse (envelope, sizeof envelope);
  OPENSSL_cleanse (counter, sizeof counter);
  return ok;
}
