/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Bounded APP12509 pairing-write transaction.
 *
 * The frame layout and response contract are adapted from the project-owned
 * qualified writer in development/psk.  This module deliberately owns no USB
 * device and no retry mechanism: its caller may submit exactly the one frame
 * returned by begin_e0(), then must supply independent readback and TLS proof.
 */
#include "goodix_pairing_provision.h"

#include "goodix_a0_protocol.h"
#include "goodix_bb010002.h"

#include <openssl/crypto.h>
#include <string.h>

#define DT_BB010002 0xbb010002u
#define DT_BB010003 0xbb010003u

struct _GoodixPairingProvision
{
  guint8 bb010002[GOODIX_PAIRING_PROVISION_BB010002_LENGTH];
  guint8 envelope[GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH];
  guint8 validator[GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH];
  GoodixPairingProvisionTerminal terminal;
  gboolean begun;
  gboolean ack_seen;
  gboolean readback_proven;
  gboolean tls_proven;
  GoodixPairingProvisionAudit *audit;
};

GQuark
goodix_pairing_provision_error_quark (void)
{
  return g_quark_from_static_string ("goodix-pairing-provision-error");
}

static void
put_le32 (guint8 *out,
          guint32 value)
{
  out[0] = (guint8) value;
  out[1] = (guint8) (value >> 8);
  out[2] = (guint8) (value >> 16);
  out[3] = (guint8) (value >> 24);
}

static void
reject (GoodixPairingProvision *provision)
{
  if (provision != NULL)
    provision->terminal = GOODIX_PAIRING_PROVISION_REJECTED;
}

static gboolean
fail (GoodixPairingProvision      *provision,
      GoodixPairingProvisionError  code,
      const gchar                 *message,
      GError                     **error)
{
  if (provision != NULL)
    reject (provision);
  g_set_error_literal (error, GOODIX_PAIRING_PROVISION_ERROR, code, message);
  return FALSE;
}

GoodixPairingProvision *
goodix_pairing_provision_new (
  const guint8                 bb010002[GOODIX_PAIRING_PROVISION_BB010002_LENGTH],
  gsize                        bb010002_length,
  const guint8                 envelope[GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH],
  gsize                        envelope_length,
  const guint8                 validator[GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH],
  gsize                        validator_length,
  GoodixPairingProvisionAudit *audit,
  GError                     **error)
{
  GoodixPairingProvision *provision;
  GoodixBb010002Info bb010002_info = { 0 };

  if (bb010002 == NULL ||
      bb010002_length != GOODIX_PAIRING_PROVISION_BB010002_LENGTH ||
      envelope == NULL ||
      envelope_length != GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH ||
      validator == NULL ||
      validator_length != GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH)
    {
      g_set_error_literal (error, GOODIX_PAIRING_PROVISION_ERROR,
                           GOODIX_PAIRING_PROVISION_ERROR_ARGUMENT,
                           "pairing provision material has an invalid length");
      return NULL;
    }
  if (!goodix_bb010002_validate (bb010002, bb010002_length,
                                 &bb010002_info, error))
    return NULL;
  provision = g_new0 (GoodixPairingProvision, 1);
  memcpy (provision->bb010002, bb010002, sizeof provision->bb010002);
  memcpy (provision->envelope, envelope, sizeof provision->envelope);
  memcpy (provision->validator, validator, sizeof provision->validator);
  provision->audit = audit;
  if (audit != NULL)
    memset (audit, 0, sizeof *audit);
  return provision;
}

void
goodix_pairing_provision_free (GoodixPairingProvision *provision)
{
  if (provision == NULL)
    return;
  OPENSSL_cleanse (provision, sizeof *provision);
  g_free (provision);
}

GBytes *
goodix_pairing_provision_begin_e0 (GoodixPairingProvision *provision,
                                   GError                **error)
{
  guint8 body[GOODIX_PAIRING_PROVISION_E0_BODY_LENGTH] = { 0 };
  g_autoptr(GBytes) frame = NULL;
  gsize offset = 0;

  if (provision == NULL || provision->begun ||
      provision->terminal != GOODIX_PAIRING_PROVISION_WAITING)
    {
      if (provision != NULL && provision->audit != NULL)
        provision->audit->retry_count++;
      fail (provision, GOODIX_PAIRING_PROVISION_ERROR_STATE,
            "a pairing transaction permits exactly one logical E0", error);
      return NULL;
    }

  put_le32 (body + offset, DT_BB010002);
  offset += 4u;
  put_le32 (body + offset, GOODIX_PAIRING_PROVISION_BB010002_LENGTH);
  offset += 4u;
  memcpy (body + offset, provision->bb010002, sizeof provision->bb010002);
  offset += sizeof provision->bb010002;
  put_le32 (body + offset, DT_BB010003);
  offset += 4u;
  put_le32 (body + offset, GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH);
  offset += 4u;
  memcpy (body + offset, provision->envelope, sizeof provision->envelope);
  offset += sizeof provision->envelope;
  while ((offset & 3u) != 0u)
    body[offset++] = 0;
  if (offset != sizeof body)
    {
      OPENSSL_cleanse (body, sizeof body);
      fail (provision, GOODIX_PAIRING_PROVISION_ERROR_STATE,
            "E0 body construction violated its fixed boundary", error);
      return NULL;
    }
  frame = goodix_a0_build_frame (0xe0u, 0xe0u, body, sizeof body, error);
  OPENSSL_cleanse (body, sizeof body);
  if (frame == NULL ||
      g_bytes_get_size (frame) != GOODIX_PAIRING_PROVISION_E0_FRAME_LENGTH)
    {
      reject (provision);
      return NULL;
    }
  provision->begun = TRUE;
  if (provision->audit != NULL)
    {
      provision->audit->logical_e0_count = 1u;
      provision->audit->persistent_write_count = 1u;
    }
  return g_steal_pointer (&frame);
}

gboolean
goodix_pairing_provision_handle_a0 (GoodixPairingProvision *provision,
                                    GBytes                 *frame,
                                    GError                **error)
{
  GoodixA0Message message = { 0 };
  const guint8 *body;
  gsize body_length;
  gboolean result = FALSE;

  if (provision == NULL || frame == NULL || !provision->begun ||
      provision->terminal != GOODIX_PAIRING_PROVISION_WAITING)
    return fail (provision, GOODIX_PAIRING_PROVISION_ERROR_STATE,
                 "E0 response is outside the active transaction", error);
  if (g_bytes_get_size (frame) < 5u)
    return fail (provision, GOODIX_PAIRING_PROVISION_ERROR_PROTOCOL,
                 "E0 response frame is truncated", error);
  if (!goodix_a0_parse_frame (
        frame, ((const guint8 *) g_bytes_get_data (frame, NULL))[4],
        &message, error))
    {
      reject (provision);
      return FALSE;
    }
  body = g_bytes_get_data (message.body, &body_length);
  if (message.control == 0xb0u)
    {
      if (provision->ack_seen || body_length != 2u || body[0] != 0xe0u ||
          (body[1] != 0x01u && body[1] != 0x07u))
        {
          fail (provision, GOODIX_PAIRING_PROVISION_ERROR_PROTOCOL,
                "E0 ACK contract failed", error);
          goto out;
        }
      provision->ack_seen = TRUE;
      if (provision->audit != NULL)
        {
          provision->audit->ack_count = 1u;
          provision->audit->ack_status = body[1];
        }
      result = TRUE;
      goto out;
    }
  if (!provision->ack_seen ||
      (message.control != 0xe0u && message.control != 0xe2u) ||
      body_length != 2u || body[0] != 0x00u ||
      (body[1] != 0x02u && body[1] != 0x03u))
    {
      fail (provision, GOODIX_PAIRING_PROVISION_ERROR_PROTOCOL,
            "E0 completion contract failed", error);
      goto out;
    }
  provision->terminal = GOODIX_PAIRING_PROVISION_ACCEPTED;
  if (provision->audit != NULL)
    {
      provision->audit->completion_count = 1u;
      provision->audit->result_control = message.control;
      provision->audit->result_code = body[1];
    }
  result = TRUE;

out:
  goodix_a0_message_clear (&message);
  return result;
}

gboolean
goodix_pairing_provision_check_readback (
  GoodixPairingProvision *provision,
  const guint8           *bb010002,
  gsize                   bb010002_length,
  const guint8           *validator,
  gsize                   validator_length,
  GError                **error)
{
  if (provision == NULL ||
      provision->terminal != GOODIX_PAIRING_PROVISION_ACCEPTED ||
      provision->readback_proven)
    return fail (provision, GOODIX_PAIRING_PROVISION_ERROR_STATE,
                 "pairing readback is outside the accepted E0 transaction",
                 error);
  if (bb010002 == NULL ||
      bb010002_length != sizeof provision->bb010002 ||
      CRYPTO_memcmp (bb010002, provision->bb010002,
                     sizeof provision->bb010002) != 0)
    return fail (provision, GOODIX_PAIRING_PROVISION_ERROR_PROOF,
                 "BB010002 changed across the E0 transaction", error);
  if (provision->audit != NULL)
    provision->audit->bb010002_unchanged = TRUE;
  if (validator == NULL || validator_length != sizeof provision->validator ||
      CRYPTO_memcmp (validator, provision->validator,
                     sizeof provision->validator) != 0)
    return fail (provision, GOODIX_PAIRING_PROVISION_ERROR_PROOF,
                 "post-E0 validator does not match the local envelope", error);
  provision->readback_proven = TRUE;
  if (provision->audit != NULL)
    provision->audit->validator_match = TRUE;
  return TRUE;
}

gboolean
goodix_pairing_provision_mark_tls_proven (GoodixPairingProvision *provision,
                                          GError                **error)
{
  if (provision == NULL ||
      provision->terminal != GOODIX_PAIRING_PROVISION_ACCEPTED ||
      !provision->readback_proven || provision->tls_proven)
    return fail (provision, GOODIX_PAIRING_PROVISION_ERROR_STATE,
                 "TLS proof requires one accepted E0 and both readbacks",
                 error);
  provision->tls_proven = TRUE;
  if (provision->audit != NULL)
    provision->audit->tls_proven = TRUE;
  return TRUE;
}

gboolean
goodix_pairing_provision_is_complete (const GoodixPairingProvision *provision)
{
  return provision != NULL &&
         provision->terminal == GOODIX_PAIRING_PROVISION_ACCEPTED &&
         provision->readback_proven && provision->tls_proven;
}

GoodixPairingProvisionTerminal
goodix_pairing_provision_get_terminal (const GoodixPairingProvision *provision)
{
  return provision == NULL ? GOODIX_PAIRING_PROVISION_REJECTED :
                             provision->terminal;
}
