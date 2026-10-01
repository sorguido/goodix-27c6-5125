/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Read-only APP12509 discovery graph used before state reconciliation.
 *
 * The material-driven secure-session graph cannot perform this prefix: it
 * requires an already selected PSK/validator/configuration and continues into
 * runtime writes and TLS.  This graph instead gathers the live inputs needed
 * to select that material.  Both graphs deliberately share the canonical A0
 * codec and USB router; framing and checksum rules do not belong here.
 */
#include "goodix_live_preflight.h"

#include "goodix_a0_protocol.h"

#include <openssl/crypto.h>
#include <string.h>

typedef enum
{
  GOODIX_LIVE_PREFLIGHT_ERROR_STATE,
  GOODIX_LIVE_PREFLIGHT_ERROR_PROTOCOL,
  GOODIX_LIVE_PREFLIGHT_ERROR_TARGET,
  GOODIX_LIVE_PREFLIGHT_ERROR_TRANSPORT,
} GoodixLivePreflightError;

#define GOODIX_LIVE_PREFLIGHT_ERROR (goodix_live_preflight_error_quark ())

struct _GoodixLivePreflight
{
  GoodixLivePreflightPhase phase;
  GoodixLivePreflightEvidence evidence;
  GoodixLivePreflightAudit *audit;
  gboolean request_submitted;
  gboolean out_pending;
  gboolean ack_seen;
  gboolean logical_done;
  GError *error;
};

static GQuark
goodix_live_preflight_error_quark (void)
{
  return g_quark_from_static_string ("goodix-live-preflight-error");
}

static guint8
phase_control (GoodixLivePreflightPhase phase)
{
  switch (phase)
    {
    case GOODIX_LIVE_PREFLIGHT_REENTRY_A2:
    case GOODIX_LIVE_PREFLIGHT_COLD_A2: return 0xa2u;
    case GOODIX_LIVE_PREFLIGHT_APP_A8: return 0xa8u;
    case GOODIX_LIVE_PREFLIGHT_BB010002_E4:
    case GOODIX_LIVE_PREFLIGHT_VALIDATOR_E4: return 0xe4u;
    case GOODIX_LIVE_PREFLIGHT_CHIP_82: return 0x82u;
    case GOODIX_LIVE_PREFLIGHT_OTP_A6: return 0xa6u;
    default: return 0u;
    }
}

static void
preflight_fail (GoodixLivePreflight      *preflight,
                GoodixLivePreflightError code,
                const gchar             *message)
{
  if (preflight == NULL || preflight->phase == GOODIX_LIVE_PREFLIGHT_TERMINAL)
    return;
  preflight->phase = GOODIX_LIVE_PREFLIGHT_TERMINAL;
  preflight->error = g_error_new_literal (GOODIX_LIVE_PREFLIGHT_ERROR,
                                          code, message);
}

static void
maybe_advance (GoodixLivePreflight *preflight)
{
  if (!preflight->logical_done || preflight->out_pending ||
      preflight->phase >= GOODIX_LIVE_PREFLIGHT_STOP)
    return;
  preflight->phase++;
  preflight->request_submitted = FALSE;
  preflight->ack_seen = FALSE;
  preflight->logical_done = FALSE;
  if (preflight->phase == GOODIX_LIVE_PREFLIGHT_STOP &&
      preflight->audit != NULL)
    preflight->audit->complete = TRUE;
}

GoodixLivePreflight *
goodix_live_preflight_new (GoodixLivePreflightAudit *audit)
{
  GoodixLivePreflight *preflight = g_new0 (GoodixLivePreflight, 1);

  preflight->phase = GOODIX_LIVE_PREFLIGHT_REENTRY_A2;
  preflight->audit = audit;
  if (audit != NULL)
    memset (audit, 0, sizeof *audit);
  return preflight;
}

void
goodix_live_preflight_free (GoodixLivePreflight *preflight)
{
  if (preflight == NULL)
    return;
  g_clear_error (&preflight->error);
  OPENSSL_cleanse (&preflight->evidence, sizeof preflight->evidence);
  OPENSSL_cleanse (preflight, sizeof *preflight);
  g_free (preflight);
}

GBytes *
goodix_live_preflight_next_request (GoodixLivePreflight *preflight,
                                    GError             **error)
{
  static const guint8 a2[] = { 0x01, 0x14 };
  static const guint8 a8[] = { 0x00, 0x00 };
  static const guint8 bb2[] = { 0x02, 0x00, 0x01, 0xbb, 0, 0, 0, 0 };
  static const guint8 validator[] = { 0x03, 0x00, 0x02, 0xbb, 0, 0, 0, 0 };
  static const guint8 chip[] = { 0, 0, 0, 4, 0 };
  static const guint8 zero2[] = { 0, 0 };
  const guint8 *body = NULL;
  gsize body_length = 0;
  guint8 control;
  GBytes *request;

  if (preflight == NULL || preflight->phase == GOODIX_LIVE_PREFLIGHT_TERMINAL)
    {
      g_set_error_literal (error, GOODIX_LIVE_PREFLIGHT_ERROR,
                           GOODIX_LIVE_PREFLIGHT_ERROR_STATE,
                           "live preflight is unavailable");
      return NULL;
    }
  if (preflight->phase == GOODIX_LIVE_PREFLIGHT_STOP ||
      preflight->request_submitted || preflight->out_pending)
    return NULL;
  switch (preflight->phase)
    {
    case GOODIX_LIVE_PREFLIGHT_REENTRY_A2:
    case GOODIX_LIVE_PREFLIGHT_COLD_A2:
      body = a2; body_length = sizeof a2; break;
    case GOODIX_LIVE_PREFLIGHT_APP_A8:
      body = a8; body_length = sizeof a8; break;
    case GOODIX_LIVE_PREFLIGHT_BB010002_E4:
      body = bb2; body_length = sizeof bb2; break;
    case GOODIX_LIVE_PREFLIGHT_VALIDATOR_E4:
      body = validator; body_length = sizeof validator; break;
    case GOODIX_LIVE_PREFLIGHT_CHIP_82:
      body = chip; body_length = sizeof chip; break;
    case GOODIX_LIVE_PREFLIGHT_OTP_A6:
      body = zero2; body_length = sizeof zero2; break;
    default:
      g_assert_not_reached ();
    }
  control = phase_control (preflight->phase);
  request = goodix_a0_build_frame (control, control, body, body_length, error);
  if (request == NULL)
    {
      preflight_fail (preflight, GOODIX_LIVE_PREFLIGHT_ERROR_STATE,
                      "live preflight request construction failed");
      return NULL;
    }
  preflight->request_submitted = TRUE;
  preflight->out_pending = TRUE;
  if (preflight->audit != NULL)
    preflight->audit->command_count++;
  return request;
}

void
goodix_live_preflight_out_complete (GoodixLivePreflight *preflight,
                                    const GError        *error)
{
  if (preflight == NULL || preflight->phase >= GOODIX_LIVE_PREFLIGHT_STOP ||
      !preflight->out_pending)
    return;
  preflight->out_pending = FALSE;
  if (error != NULL)
    {
      preflight_fail (preflight, GOODIX_LIVE_PREFLIGHT_ERROR_TRANSPORT,
                      error->message);
      return;
    }
  maybe_advance (preflight);
}

static gboolean
parse_e4 (GoodixLivePreflight *preflight,
          const guint8        *body,
          gsize                body_length)
{
  GoodixBb010002Info bb010002_info = { 0 };
  guint32 expected_type;
  gsize expected_length;
  guint8 *destination;

  if (preflight->phase == GOODIX_LIVE_PREFLIGHT_BB010002_E4)
    {
      expected_type = 0xbb010002u;
      expected_length = GOODIX_BB010002_LENGTH;
      destination = preflight->evidence.bb010002;
    }
  else
    {
      expected_type = 0xbb020003u;
      expected_length = sizeof preflight->evidence.validator;
      destination = preflight->evidence.validator;
    }
  if (body_length != 9u + expected_length || body[0] != 0u ||
      ((guint32) body[1] | ((guint32) body[2] << 8) |
       ((guint32) body[3] << 16) | ((guint32) body[4] << 24)) != expected_type ||
      ((guint32) body[5] | ((guint32) body[6] << 8) |
       ((guint32) body[7] << 16) | ((guint32) body[8] << 24)) != expected_length)
    return FALSE;
  memcpy (destination, body + 9u, expected_length);
  if (preflight->phase == GOODIX_LIVE_PREFLIGHT_BB010002_E4)
    {
      if (!goodix_bb010002_validate (destination, expected_length,
                                     &bb010002_info, NULL))
        return FALSE;
      if (preflight->audit != NULL)
        preflight->audit->bb010002_valid = TRUE;
    }
  return TRUE;
}

static gboolean
accept_typed (GoodixLivePreflight *preflight,
              const guint8        *body,
              gsize                body_length)
{
  static const guint8 app[] = "GF_ST411SEC_APP_12509";
  GoodixConfig90Calibration calibration = { 0 };
  guint16 chip_id;

  switch (preflight->phase)
    {
    case GOODIX_LIVE_PREFLIGHT_REENTRY_A2:
      if (body_length != sizeof preflight->evidence.a2_response)
        return FALSE;
      memcpy (preflight->evidence.a2_response, body, body_length);
      return TRUE;
    case GOODIX_LIVE_PREFLIGHT_APP_A8:
      if (body_length != sizeof app || memcmp (body, app, sizeof app) != 0)
        return FALSE;
      if (preflight->audit != NULL)
        preflight->audit->exact_app = TRUE;
      return TRUE;
    case GOODIX_LIVE_PREFLIGHT_BB010002_E4:
    case GOODIX_LIVE_PREFLIGHT_VALIDATOR_E4:
      return parse_e4 (preflight, body, body_length);
    case GOODIX_LIVE_PREFLIGHT_COLD_A2:
      return body_length == sizeof preflight->evidence.a2_response &&
             CRYPTO_memcmp (body, preflight->evidence.a2_response,
                            body_length) == 0;
    case GOODIX_LIVE_PREFLIGHT_CHIP_82:
      if (body_length != sizeof preflight->evidence.chip_response ||
          body[0] != 0u || body[3] != 0u)
        return FALSE;
      chip_id = (guint16) body[1] | ((guint16) body[2] << 8);
      if (chip_id != 0x2503u && chip_id != 0x2504u)
        return FALSE;
      memcpy (preflight->evidence.chip_response, body, body_length);
      preflight->evidence.chip_id = chip_id;
      if (preflight->audit != NULL)
        preflight->audit->supported_chip_profile = TRUE;
      return TRUE;
    case GOODIX_LIVE_PREFLIGHT_OTP_A6:
      if (body_length != sizeof preflight->evidence.otp)
        return FALSE;
      if (!goodix_config90_derive (
            preflight->evidence.chip_id, body, body_length,
            preflight->evidence.config90, &calibration, NULL))
        return FALSE;
      memcpy (preflight->evidence.otp, body, body_length);
      preflight->evidence.calibration = calibration;
      OPENSSL_cleanse (&calibration, sizeof calibration);
      if (preflight->audit != NULL)
        {
          preflight->audit->otp_valid = TRUE;
          preflight->audit->config90_derived = TRUE;
        }
      return TRUE;
    default:
      return FALSE;
    }
}

gboolean
goodix_live_preflight_handle_a0 (GoodixLivePreflight *preflight,
                                 GBytes              *frame,
                                 GError             **error)
{
  GoodixA0Message message = { 0 };
  const guint8 *body;
  gsize body_length;
  guint8 expected;

  if (preflight == NULL || frame == NULL ||
      preflight->phase >= GOODIX_LIVE_PREFLIGHT_STOP ||
      !preflight->request_submitted || preflight->logical_done ||
      g_bytes_get_size (frame) < 5u)
    {
      preflight_fail (preflight, GOODIX_LIVE_PREFLIGHT_ERROR_STATE,
                      "A0 response is outside the live preflight phase");
      if (preflight != NULL && preflight->error != NULL)
        g_propagate_error (error, g_error_copy (preflight->error));
      return FALSE;
    }
  if (!goodix_a0_parse_frame (
        frame, ((const guint8 *) g_bytes_get_data (frame, NULL))[4],
        &message, error))
    {
      preflight_fail (preflight, GOODIX_LIVE_PREFLIGHT_ERROR_PROTOCOL,
                      "malformed live preflight A0 frame");
      return FALSE;
    }
  body = g_bytes_get_data (message.body, &body_length);
  expected = phase_control (preflight->phase);
  if (message.control == 0xb0u)
    {
      if (preflight->ack_seen || body_length != 2u || body[0] != expected ||
          (body[1] != 0x01u && body[1] != 0x07u))
        goto invalid;
      preflight->ack_seen = TRUE;
      if (preflight->audit != NULL)
        preflight->audit->ack_count++;
      goodix_a0_message_clear (&message);
      return TRUE;
    }
  if (!preflight->ack_seen || message.control != expected ||
      !accept_typed (preflight, body, body_length))
    goto invalid;
  preflight->logical_done = TRUE;
  if (preflight->audit != NULL)
    preflight->audit->typed_response_count++;
  maybe_advance (preflight);
  goodix_a0_message_clear (&message);
  return TRUE;

invalid:
  goodix_a0_message_clear (&message);
  preflight_fail (preflight, GOODIX_LIVE_PREFLIGHT_ERROR_TARGET,
                  "live preflight response failed its target boundary");
  g_propagate_error (error, g_error_copy (preflight->error));
  return FALSE;
}

GoodixLivePreflightPhase
goodix_live_preflight_get_phase (const GoodixLivePreflight *preflight)
{
  return preflight == NULL ? GOODIX_LIVE_PREFLIGHT_TERMINAL : preflight->phase;
}

const GError *
goodix_live_preflight_get_error (const GoodixLivePreflight *preflight)
{
  return preflight == NULL ? NULL : preflight->error;
}

gboolean
goodix_live_preflight_copy_evidence (const GoodixLivePreflight *preflight,
                                     GoodixLivePreflightEvidence *evidence)
{
  if (evidence != NULL)
    memset (evidence, 0, sizeof *evidence);
  if (preflight == NULL || evidence == NULL ||
      preflight->phase != GOODIX_LIVE_PREFLIGHT_STOP)
    return FALSE;
  *evidence = preflight->evidence;
  return TRUE;
}

gboolean
goodix_live_preflight_needs_receive (const GoodixLivePreflight *preflight)
{
  return preflight != NULL &&
         preflight->phase < GOODIX_LIVE_PREFLIGHT_STOP;
}
