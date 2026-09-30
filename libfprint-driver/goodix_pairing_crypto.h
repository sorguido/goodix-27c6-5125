/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_PAIRING_CRYPTO_H
#define GOODIX_PAIRING_CRYPTO_H

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_PAIRING_PSK_LENGTH 32u
#define GOODIX_PAIRING_ENVELOPE_LENGTH 102u
#define GOODIX_PAIRING_VALIDATOR_LENGTH 32u

typedef enum
{
  GOODIX_PAIRING_CRYPTO_ERROR_ARGUMENT,
  GOODIX_PAIRING_CRYPTO_ERROR_CRYPTO,
  GOODIX_PAIRING_CRYPTO_ERROR_MISMATCH,
} GoodixPairingCryptoError;

#define GOODIX_PAIRING_CRYPTO_ERROR (goodix_pairing_crypto_error_quark ())

GQuark goodix_pairing_crypto_error_quark (void);

/* Pure APP12509 mapping from a local 32-byte PSK to the BB010003 envelope and
 * its BB020003 SHA-256 validator.  Outputs are cleared before validation and
 * on every failure. */
gboolean goodix_pairing_crypto_derive (
  const guint8 psk[GOODIX_PAIRING_PSK_LENGTH],
  gsize        psk_length,
  guint8       envelope[GOODIX_PAIRING_ENVELOPE_LENGTH],
  guint8       validator[GOODIX_PAIRING_VALIDATOR_LENGTH],
  GError     **error);

/* Recompute the fixed APP12509 mapping and compare both values in constant
 * time.  This function never decrypts or accepts alternate profiles. */
gboolean goodix_pairing_crypto_validate (
  const guint8 psk[GOODIX_PAIRING_PSK_LENGTH],
  gsize        psk_length,
  const guint8 envelope[GOODIX_PAIRING_ENVELOPE_LENGTH],
  gsize        envelope_length,
  const guint8 validator[GOODIX_PAIRING_VALIDATOR_LENGTH],
  gsize        validator_length,
  GError     **error);

#ifdef GOODIX_ENABLE_TEST_SEAMS
/* Host-only negative-KAT seam.  Production code has no alternate-profile
 * entry point and production builds must not export this symbol. */
gboolean goodix_pairing_crypto_derive_profile_for_test (
  const guint8 psk[GOODIX_PAIRING_PSK_LENGTH],
  gsize        psk_length,
  const guint8 kdf_key[32],
  gsize        kdf_key_length,
  const guint8 aad[16],
  gsize        aad_length,
  const guint8 header[6],
  gsize        header_length,
  guint8       envelope[GOODIX_PAIRING_ENVELOPE_LENGTH],
  guint8       validator[GOODIX_PAIRING_VALIDATOR_LENGTH],
  GError     **error);
#endif

G_END_DECLS

#endif
