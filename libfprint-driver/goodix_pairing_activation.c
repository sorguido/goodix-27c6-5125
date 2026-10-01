/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Crash-safe production pairing activation for APP12509.
 *
 * Construction performs host-only work: it binds the live preflight evidence,
 * selects or generates the Linux PSK and durably reserves the single E0 in a
 * PREPARED state record.  Device I/O remains caller-owned and is exposed as a
 * bounded E0 -> BB010002 readback -> BB020003 readback graph with no retry.
 */
#include "goodix_pairing_activation.h"

#include "goodix_a0_protocol.h"
#include "goodix_pairing_crypto.h"

#include <string.h>

#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/rand.h>

#define DT_BB010002 0xbb010002u
#define DT_BB020003 0xbb020003u

typedef enum
{
  GOODIX_PAIRING_ACTIVATION_ERROR_ARGUMENT,
  GOODIX_PAIRING_ACTIVATION_ERROR_STATE,
  GOODIX_PAIRING_ACTIVATION_ERROR_PROTOCOL,
  GOODIX_PAIRING_ACTIVATION_ERROR_PROOF,
  GOODIX_PAIRING_ACTIVATION_ERROR_CRYPTO,
} GoodixPairingActivationError;

#define GOODIX_PAIRING_ACTIVATION_ERROR \
  (goodix_pairing_activation_error_quark ())

struct _GoodixPairingActivation
{
  GoodixPairingActivationPhase phase;
  GoodixPairingActivationDisposition disposition;
  gchar *state_directory;
  GoodixSelfStatePolicy state_policy;
  GoodixSelfState *prepared_state;
  GoodixPairingProvision *provision;
  GoodixPairingActivationAudit *audit;
  GoodixSecureSessionMaterial secure_view;
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];
  guint8 envelope[GOODIX_PAIRING_ENVELOPE_LENGTH];
  guint8 validator[GOODIX_PAIRING_VALIDATOR_LENGTH];
  guint8 config90[GOODIX_CONFIG90_LENGTH];
  guint8 a2_response[3];
  guint8 chip_response[4];
  guint8 otp[GOODIX_CONFIG90_OTP_LENGTH];
  guint8 expected_bb010002[GOODIX_BB010002_LENGTH];
  guint8 readback_bb010002[GOODIX_BB010002_LENGTH];
  guint8 readback_validator[GOODIX_PAIRING_VALIDATOR_LENGTH];
  gboolean request_submitted;
  gboolean out_pending;
  gboolean ack_seen;
  gboolean logical_done;
  GError *error;
};

static GQuark
goodix_pairing_activation_error_quark (void)
{
  return g_quark_from_static_string ("goodix-pairing-activation-error");
}

static gboolean
sha256 (const guint8 *input,
        gsize         input_length,
        guint8        output[32])
{
  unsigned int output_length = 0;

  return input != NULL &&
         EVP_Digest (input, input_length, output, &output_length,
                     EVP_sha256 (), NULL) == 1 && output_length == 32u;
}

static gboolean
fail (GoodixPairingActivation      *activation,
      GoodixPairingActivationError  code,
      const gchar                  *message,
      GError                      **error)
{
  if (activation != NULL &&
      activation->phase != GOODIX_PAIRING_ACTIVATION_TERMINAL)
    {
      activation->phase = GOODIX_PAIRING_ACTIVATION_TERMINAL;
      activation->error = g_error_new_literal (
        GOODIX_PAIRING_ACTIVATION_ERROR, code, message);
    }
  if (error != NULL && *error == NULL)
    *error = activation != NULL && activation->error != NULL ?
      g_error_copy (activation->error) :
      g_error_new_literal (GOODIX_PAIRING_ACTIVATION_ERROR, code, message);
  return FALSE;
}

static gboolean
evidence_valid (const GoodixLivePreflightEvidence *evidence)
{
  return evidence != NULL &&
         (evidence->chip_id == 0x2503u || evidence->chip_id == 0x2504u);
}

static void
put_le32 (guint8 *output,
          guint32 value)
{
  output[0] = (guint8) value;
  output[1] = (guint8) (value >> 8);
  output[2] = (guint8) (value >> 16);
  output[3] = (guint8) (value >> 24);
}

static gboolean
prepare_secure_view (GoodixPairingActivation        *activation,
                     const GoodixLivePreflightEvidence *evidence,
                     GError                        **error)
{
  static const guint8 identity[] = "GF_ST411SEC_APP_12509";

  memcpy (activation->config90, evidence->config90,
          sizeof activation->config90);
  memcpy (activation->a2_response, evidence->a2_response,
          sizeof activation->a2_response);
  memcpy (activation->chip_response, evidence->chip_response,
          sizeof activation->chip_response);
  memcpy (activation->otp, evidence->otp, sizeof activation->otp);
  activation->secure_view.expected_identity = identity;
  activation->secure_view.expected_identity_length = sizeof identity;
  activation->secure_view.e4_validator = activation->validator;
  activation->secure_view.e4_validator_length = sizeof activation->validator;
  activation->secure_view.config90 = activation->config90;
  activation->secure_view.config90_length = sizeof activation->config90;
  activation->secure_view.psk = activation->psk;
  activation->secure_view.psk_length = sizeof activation->psk;
  if (!sha256 (activation->validator, sizeof activation->validator,
               activation->secure_view.e4_validator_sha256) ||
      !sha256 (activation->config90, sizeof activation->config90,
               activation->secure_view.config90_sha256) ||
      !sha256 (activation->a2_response, sizeof activation->a2_response,
               activation->secure_view.a2_response_sha256) ||
      !sha256 (activation->chip_response, sizeof activation->chip_response,
               activation->secure_view.chip82_response_sha256) ||
      !sha256 (activation->otp, sizeof activation->otp,
               activation->secure_view.otp_a6_response_sha256))
    return fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_CRYPTO,
                 "pairing secure-view digest construction failed", error);
  for (guint i = 0; i < G_N_ELEMENTS (evidence->calibration.dac_registers); i++)
    {
      activation->secure_view.dac_values[i][0] =
        (guint8) evidence->calibration.dac_registers[i];
      activation->secure_view.dac_values[i][1] =
        (guint8) (evidence->calibration.dac_registers[i] >> 8);
    }
  return TRUE;
}

static GoodixPairingActivation *
activation_new_internal (const GoodixPairingActivationPaths  *paths,
                         const GoodixPairingActivationPolicy *policy,
                         const GoodixLivePreflightEvidence   *evidence,
                         const guint8                        *test_psk,
                         GoodixPairingActivationAudit        *audit,
                         GError                             **error)
{
  GoodixPairingActivation *activation = NULL;
  GoodixSelfStateBinding binding = { 0 };
  GoodixSelfStateRecord record = { 0 };
  GoodixSelfState *loaded = NULL;
  GoodixSelfStateLoadResult load_result;
  GoodixSelfStateReconcile reconciliation =
    GOODIX_SELF_STATE_RECONCILE_RECOVERY_REQUIRED;
  const GoodixSelfStateRecord *loaded_record = NULL;
  guint8 bb010002_sha256[32] = { 0 };
  gboolean needs_e0 = FALSE;

  if (audit != NULL)
    memset (audit, 0, sizeof *audit);
  if (paths == NULL || paths->state_directory == NULL || policy == NULL ||
      !evidence_valid (evidence))
    {
      g_set_error_literal (error, GOODIX_PAIRING_ACTIVATION_ERROR,
                           GOODIX_PAIRING_ACTIVATION_ERROR_ARGUMENT,
                           "pairing activation inputs are invalid");
      return NULL;
    }
  activation = g_new0 (GoodixPairingActivation, 1);
  activation->audit = audit;
  activation->state_directory = g_strdup (paths->state_directory);
  activation->state_policy = policy->state;
  memcpy (activation->expected_bb010002, evidence->bb010002,
          sizeof activation->expected_bb010002);
  if (!sha256 (evidence->otp, sizeof evidence->otp, binding.otp_sha256) ||
      !sha256 (evidence->config90, sizeof evidence->config90,
               binding.config90_sha256) ||
      !sha256 (evidence->bb010002, sizeof evidence->bb010002,
               bb010002_sha256))
    {
      fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_CRYPTO,
            "pairing state binding digest failed", error);
      goto fail;
    }
  binding.vid = 0x27c6u;
  binding.pid = 0x5125u;
  binding.chip_profile = evidence->chip_id;
  g_strlcpy (binding.app, "APP12509", sizeof binding.app);
  load_result = goodix_self_state_load (paths->state_directory, &binding,
                                        &policy->state, &loaded, error);
  if (audit != NULL)
    audit->state_load_result = load_result;
  if (load_result == GOODIX_SELF_STATE_LOAD_ABSENT)
    {
      if (test_psk != NULL)
        memcpy (activation->psk, test_psk, sizeof activation->psk);
      else if (RAND_priv_bytes (activation->psk,
                                sizeof activation->psk) != 1)
        {
          fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_CRYPTO,
                "local pairing PSK generation failed", error);
          goto fail;
        }
      record.generation = 1u;
      activation->disposition =
        GOODIX_PAIRING_ACTIVATION_DISPOSITION_NEW_PSK;
      needs_e0 = TRUE;
    }
  else if (load_result == GOODIX_SELF_STATE_LOAD_VALID)
    {
      loaded_record = goodix_self_state_get_record (loaded);
      reconciliation = goodix_self_state_reconcile (
        loaded, evidence->validator, FALSE);
      if (audit != NULL)
        audit->reconciliation = reconciliation;
      if (reconciliation == GOODIX_SELF_STATE_RECONCILE_ACTIVE_MATCH &&
          loaded_record->bb010002_sha256_present &&
          CRYPTO_memcmp (loaded_record->bb010002_sha256, bb010002_sha256,
                         sizeof bb010002_sha256) == 0 &&
          goodix_self_state_copy_psk (loaded, activation->psk) &&
          goodix_pairing_crypto_derive (
            activation->psk, sizeof activation->psk,
            activation->envelope, activation->validator, error) &&
          CRYPTO_memcmp (activation->validator,
                         loaded_record->expected_validator,
                         sizeof activation->validator) == 0)
        {
          activation->prepared_state = loaded;
          loaded = NULL;
          activation->disposition =
            GOODIX_PAIRING_ACTIVATION_DISPOSITION_REUSE_ACTIVE_TLS;
          activation->phase = GOODIX_PAIRING_ACTIVATION_TLS;
          if (audit != NULL)
            {
              audit->disposition = activation->disposition;
              audit->active_reused_without_e0 = TRUE;
            }
          if (!prepare_secure_view (activation, evidence, error))
            goto fail;
          OPENSSL_cleanse (bb010002_sha256, sizeof bb010002_sha256);
          return activation;
        }
      if (reconciliation == GOODIX_SELF_STATE_RECONCILE_RETRY_TLS &&
          loaded_record->e0_attempted &&
          loaded_record->bb010002_sha256_present &&
          CRYPTO_memcmp (loaded_record->bb010002_sha256, bb010002_sha256,
                         sizeof bb010002_sha256) == 0 &&
          goodix_self_state_copy_psk (loaded, activation->psk) &&
          goodix_pairing_crypto_derive (
            activation->psk, sizeof activation->psk,
            activation->envelope, activation->validator, error) &&
          CRYPTO_memcmp (activation->validator,
                         loaded_record->expected_validator,
                         sizeof activation->validator) == 0)
        {
          activation->prepared_state = loaded;
          loaded = NULL;
          activation->disposition =
            GOODIX_PAIRING_ACTIVATION_DISPOSITION_RECOVER_PREPARED_TLS;
          activation->phase = GOODIX_PAIRING_ACTIVATION_TLS;
          if (audit != NULL)
            {
              audit->disposition = activation->disposition;
              audit->prepared_journaled = TRUE;
              audit->e0_reserved_before_submit = TRUE;
              audit->recovered_without_e0 = TRUE;
            }
          if (!prepare_secure_view (activation, evidence, error))
            goto fail;
          OPENSSL_cleanse (bb010002_sha256, sizeof bb010002_sha256);
          return activation;
        }
      if (reconciliation !=
            GOODIX_SELF_STATE_RECONCILE_EXTERNAL_REPLACEMENT ||
          loaded_record->phase != GOODIX_SELF_STATE_ACTIVE ||
          loaded_record->generation == G_MAXUINT64 ||
          !goodix_self_state_copy_psk (loaded, activation->psk))
        {
          fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_STATE,
                "state-v2 does not authorize a pairing write", error);
          goto fail;
        }
      record.generation = loaded_record->generation + 1u;
      record.fdt_present = loaded_record->fdt_present;
      memcpy (record.fdt_table, loaded_record->fdt_table,
              sizeof record.fdt_table);
      activation->disposition =
        GOODIX_PAIRING_ACTIVATION_DISPOSITION_RESTORE_ACTIVE_PSK;
      needs_e0 = TRUE;
    }
  else
    {
      if (error == NULL || *error == NULL)
        g_set_error_literal (error, GOODIX_PAIRING_ACTIVATION_ERROR,
                             GOODIX_PAIRING_ACTIVATION_ERROR_STATE,
                             "state-v2 is incomplete or target-mismatched");
      goto fail;
    }

  g_assert (needs_e0);
  if (!goodix_pairing_crypto_derive (
        activation->psk, sizeof activation->psk,
        activation->envelope, activation->validator, error))
    goto fail;
  record.phase = GOODIX_SELF_STATE_PREPARED;
  memcpy (record.expected_validator, activation->validator,
          sizeof record.expected_validator);
  record.prior_validator_present = TRUE;
  memcpy (record.prior_validator, evidence->validator,
          sizeof record.prior_validator);
  record.bb010002_sha256_present = TRUE;
  memcpy (record.bb010002_sha256, bb010002_sha256,
          sizeof record.bb010002_sha256);
  /* This durable reservation is intentionally written before begin_e0().  A
   * crash in the narrow pre-submit window therefore requires explicit
   * recovery instead of ever speculating a second write. */
  record.e0_attempted = TRUE;
  if (!goodix_self_state_write_prepared (
        paths->state_directory, &binding, &record, activation->psk,
        &policy->state, error))
    goto fail;
  goodix_self_state_free (loaded);
  loaded = NULL;
  if (goodix_self_state_load (paths->state_directory, &binding, &policy->state,
                              &activation->prepared_state, error) !=
        GOODIX_SELF_STATE_LOAD_VALID ||
      goodix_self_state_get_record (activation->prepared_state)->generation !=
        record.generation ||
      !goodix_self_state_get_record (activation->prepared_state)->e0_attempted)
    {
      fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_STATE,
            "durable PREPARED pairing reservation could not be reloaded",
            error);
      goto fail;
    }
  activation->provision = goodix_pairing_provision_new (
    evidence->bb010002, sizeof evidence->bb010002,
    activation->envelope, sizeof activation->envelope,
    activation->validator, sizeof activation->validator,
    audit != NULL ? &audit->provision : NULL, error);
  if (activation->provision == NULL ||
      !prepare_secure_view (activation, evidence, error))
    goto fail;
  activation->phase = GOODIX_PAIRING_ACTIVATION_E0;
  if (audit != NULL)
    {
      audit->disposition = activation->disposition;
      audit->prepared_journaled = TRUE;
      audit->e0_reserved_before_submit = TRUE;
    }
  OPENSSL_cleanse (bb010002_sha256, sizeof bb010002_sha256);
  return activation;

fail:
  goodix_self_state_free (loaded);
  OPENSSL_cleanse (bb010002_sha256, sizeof bb010002_sha256);
  goodix_pairing_activation_free (activation);
  return NULL;
}

void
goodix_pairing_activation_paths_production (GoodixPairingActivationPaths *paths)
{
  g_return_if_fail (paths != NULL);
  paths->state_directory = "/var/lib/fprint/goodix-5125-state-v2";
}

void
goodix_pairing_activation_policy_production (
  GoodixPairingActivationPolicy *policy)
{
  g_return_if_fail (policy != NULL);
  memset (policy, 0, sizeof *policy);
  goodix_self_state_policy_for_owner (&policy->state, 0u, 0u);
}

GoodixPairingActivation *
goodix_pairing_activation_new (const GoodixPairingActivationPaths  *paths,
                               const GoodixPairingActivationPolicy *policy,
                               const GoodixLivePreflightEvidence   *evidence,
                               GoodixPairingActivationAudit        *audit,
                               GError                             **error)
{
  return activation_new_internal (paths, policy, evidence, NULL, audit, error);
}

#ifdef GOODIX_ENABLE_TEST_SEAMS
GoodixPairingActivation *
goodix_pairing_activation_new_for_test (
  const GoodixPairingActivationPaths  *paths,
  const GoodixPairingActivationPolicy *policy,
  const GoodixLivePreflightEvidence   *evidence,
  const guint8                         psk[GOODIX_SELF_STATE_PSK_LENGTH],
  GoodixPairingActivationAudit        *audit,
  GError                             **error)
{
  if (psk == NULL)
    {
      g_set_error_literal (error, GOODIX_PAIRING_ACTIVATION_ERROR,
                           GOODIX_PAIRING_ACTIVATION_ERROR_ARGUMENT,
                           "test pairing PSK is missing");
      return NULL;
    }
  return activation_new_internal (paths, policy, evidence, psk, audit, error);
}
#endif

GBytes *
goodix_pairing_activation_next_request (GoodixPairingActivation *activation,
                                        GError                 **error)
{
  guint8 body[8] = { 0 };
  GBytes *request;

  if (activation == NULL ||
      activation->phase >= GOODIX_PAIRING_ACTIVATION_TLS ||
      activation->request_submitted || activation->out_pending)
    return NULL;
  if (activation->phase == GOODIX_PAIRING_ACTIVATION_E0)
    request = goodix_pairing_provision_begin_e0 (activation->provision, error);
  else
    {
      put_le32 (body,
                activation->phase == GOODIX_PAIRING_ACTIVATION_READ_BB010002 ?
                  DT_BB010002 : DT_BB020003);
      request = goodix_a0_build_frame (0xe4u, 0xe4u, body, sizeof body, error);
      if (request != NULL && activation->audit != NULL)
        activation->audit->readback_command_count++;
    }
  if (request == NULL)
    {
      fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_STATE,
            "pairing request construction failed", error);
      return NULL;
    }
  activation->request_submitted = TRUE;
  activation->out_pending = TRUE;
  if (activation->phase == GOODIX_PAIRING_ACTIVATION_E0 &&
      activation->audit != NULL)
    activation->audit->persistent_write_count = 1u;
  return request;
}

static void
reset_for_next_phase (GoodixPairingActivation *activation)
{
  activation->request_submitted = FALSE;
  activation->out_pending = FALSE;
  activation->ack_seen = FALSE;
  activation->logical_done = FALSE;
}

static gboolean
finish_readback (GoodixPairingActivation *activation,
                 GError                 **error)
{
  if (!goodix_pairing_provision_check_readback (
        activation->provision,
        activation->readback_bb010002,
        sizeof activation->readback_bb010002,
        activation->readback_validator,
        sizeof activation->readback_validator, error))
    return fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_PROOF,
                 "post-E0 readback proof failed", error);
  if (activation->audit != NULL)
    {
      activation->audit->bb010002_readback_match = TRUE;
      activation->audit->validator_readback_match = TRUE;
    }
  reset_for_next_phase (activation);
  activation->phase = GOODIX_PAIRING_ACTIVATION_TLS;
  return TRUE;
}

static gboolean
maybe_advance (GoodixPairingActivation *activation,
               GError                 **error)
{
  if (activation->out_pending)
    return TRUE;
  if (activation->phase == GOODIX_PAIRING_ACTIVATION_E0)
    {
      if (goodix_pairing_provision_get_terminal (activation->provision) !=
            GOODIX_PAIRING_PROVISION_ACCEPTED)
        return TRUE;
      reset_for_next_phase (activation);
      activation->phase = GOODIX_PAIRING_ACTIVATION_READ_BB010002;
      return TRUE;
    }
  if (!activation->logical_done)
    return TRUE;
  if (activation->phase == GOODIX_PAIRING_ACTIVATION_READ_BB010002)
    {
      reset_for_next_phase (activation);
      activation->phase = GOODIX_PAIRING_ACTIVATION_READ_VALIDATOR;
      return TRUE;
    }
  return finish_readback (activation, error);
}

void
goodix_pairing_activation_out_complete (GoodixPairingActivation *activation,
                                        const GError            *error)
{
  if (activation == NULL || !activation->out_pending ||
      activation->phase >= GOODIX_PAIRING_ACTIVATION_TLS)
    return;
  activation->out_pending = FALSE;
  if (error != NULL)
    {
      fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_PROTOCOL,
            "pairing USB OUT failed; do not retry E0", NULL);
      return;
    }
  (void) maybe_advance (activation, NULL);
}

static gboolean
handle_readback_a0 (GoodixPairingActivation *activation,
                    GBytes                 *frame,
                    GError                **error)
{
  GoodixA0Message message = { 0 };
  const guint8 *body;
  guint8 *destination;
  guint32 expected_type;
  gsize body_length;
  gsize expected_length;
  gboolean result = FALSE;

  if (!goodix_a0_parse_frame (
        frame, ((const guint8 *) g_bytes_get_data (frame, NULL))[4],
        &message, error))
    return fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_PROTOCOL,
                 "malformed pairing readback frame", error);
  body = g_bytes_get_data (message.body, &body_length);
  if (message.control == 0xb0u)
    {
      if (activation->ack_seen || body_length != 2u || body[0] != 0xe4u ||
          (body[1] != 0x01u && body[1] != 0x07u))
        goto invalid;
      activation->ack_seen = TRUE;
      if (activation->audit != NULL)
        activation->audit->readback_ack_count++;
      result = TRUE;
      goto out;
    }
  expected_type =
    activation->phase == GOODIX_PAIRING_ACTIVATION_READ_BB010002 ?
      DT_BB010002 : DT_BB020003;
  expected_length =
    activation->phase == GOODIX_PAIRING_ACTIVATION_READ_BB010002 ?
      sizeof activation->readback_bb010002 :
      sizeof activation->readback_validator;
  destination =
    activation->phase == GOODIX_PAIRING_ACTIVATION_READ_BB010002 ?
      activation->readback_bb010002 : activation->readback_validator;
  if (!activation->ack_seen || message.control != 0xe4u ||
      body_length != 9u + expected_length || body[0] != 0u ||
      ((guint32) body[1] | ((guint32) body[2] << 8) |
       ((guint32) body[3] << 16) | ((guint32) body[4] << 24)) !=
        expected_type ||
      ((guint32) body[5] | ((guint32) body[6] << 8) |
       ((guint32) body[7] << 16) | ((guint32) body[8] << 24)) !=
        expected_length)
    goto invalid;
  memcpy (destination, body + 9u, expected_length);
  activation->logical_done = TRUE;
  if (activation->audit != NULL)
    activation->audit->readback_typed_count++;
  result = maybe_advance (activation, error);
  goto out;

invalid:
  fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_PROOF,
        "pairing readback failed its exact typed-response contract", error);
out:
  goodix_a0_message_clear (&message);
  return result;
}

gboolean
goodix_pairing_activation_handle_a0 (GoodixPairingActivation *activation,
                                     GBytes                  *frame,
                                     GError                 **error)
{
  gboolean result;

  if (activation == NULL || frame == NULL || !activation->request_submitted ||
      activation->phase >= GOODIX_PAIRING_ACTIVATION_TLS ||
      g_bytes_get_size (frame) < 5u)
    return fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_STATE,
                 "A0 response is outside the pairing transaction", error);
  if (activation->phase != GOODIX_PAIRING_ACTIVATION_E0)
    return handle_readback_a0 (activation, frame, error);
  result = goodix_pairing_provision_handle_a0 (activation->provision,
                                                frame, error);
  if (!result)
    return fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_PROTOCOL,
                 "E0 response failed its qualified contract", error);
  return maybe_advance (activation, error);
}

gboolean
goodix_pairing_activation_needs_receive (
  const GoodixPairingActivation *activation)
{
  return activation != NULL &&
         activation->phase < GOODIX_PAIRING_ACTIVATION_TLS;
}

GoodixPairingActivationPhase
goodix_pairing_activation_get_phase (const GoodixPairingActivation *activation)
{
  return activation == NULL ? GOODIX_PAIRING_ACTIVATION_TERMINAL :
                              activation->phase;
}

const GError *
goodix_pairing_activation_get_error (const GoodixPairingActivation *activation)
{
  return activation == NULL ? NULL : activation->error;
}

gboolean
goodix_pairing_activation_get_secure_view (
  GoodixPairingActivation    *activation,
  GoodixSecureSessionMaterial *view,
  GError                    **error)
{
  if (activation == NULL || view == NULL ||
      activation->phase != GOODIX_PAIRING_ACTIVATION_TLS)
    return fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_STATE,
                 "pairing secure material is not readback-qualified", error);
  *view = activation->secure_view;
  return TRUE;
}

gboolean
goodix_pairing_activation_mark_tls_and_promote (
  GoodixPairingActivation *activation,
  GError                 **error)
{
  if (activation == NULL ||
      activation->phase != GOODIX_PAIRING_ACTIVATION_TLS ||
      activation->prepared_state == NULL)
    return fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_STATE,
                 "pairing state is not awaiting TLS proof", error);
  if (activation->provision != NULL &&
      !goodix_pairing_provision_mark_tls_proven (activation->provision, error))
    return fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_PROOF,
                 "pairing TLS proof was rejected", error);
  if (activation->disposition !=
        GOODIX_PAIRING_ACTIVATION_DISPOSITION_REUSE_ACTIVE_TLS &&
      !goodix_self_state_promote_active (activation->state_directory,
                                         activation->prepared_state,
                                         &activation->state_policy, error))
    return fail (activation, GOODIX_PAIRING_ACTIVATION_ERROR_STATE,
                 "pairing ACTIVE promotion failed", error);
  activation->phase = GOODIX_PAIRING_ACTIVATION_COMPLETE;
  if (activation->audit != NULL)
    {
      activation->audit->tls_proven = TRUE;
      activation->audit->active_promoted =
        activation->disposition !=
          GOODIX_PAIRING_ACTIVATION_DISPOSITION_REUSE_ACTIVE_TLS;
    }
  return TRUE;
}

void
goodix_pairing_activation_free (GoodixPairingActivation *activation)
{
  if (activation == NULL)
    return;
  g_clear_error (&activation->error);
  goodix_pairing_provision_free (activation->provision);
  goodix_self_state_free (activation->prepared_state);
  g_free (activation->state_directory);
  OPENSSL_cleanse (activation, sizeof *activation);
  g_free (activation);
}
