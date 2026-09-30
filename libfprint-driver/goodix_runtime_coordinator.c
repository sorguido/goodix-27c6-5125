/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Read-only runtime source coordinator for APP12509.
 *
 * This file has no USB transport and intentionally exports no state writer or
 * pairing operation.  It only validates host state and prepares an immutable
 * secure-session handoff after a separate caller supplies live evidence.
 */
#include "goodix_runtime_coordinator.h"

#include <errno.h>
#include <string.h>
#include <sys/stat.h>

#include <openssl/crypto.h>
#include <openssl/evp.h>

typedef enum
{
  PATH_ABSENT,
  PATH_DIRECTORY,
  PATH_INVALID,
} PathState;

struct _GoodixRuntimeCoordinator
{
  GoodixRuntimeCoordinatorSource source;
  GoodixRuntimeMaterial *legacy;
  GoodixRuntimeCoordinatorLegacyReleaseFunc legacy_release;
  gpointer legacy_user_data;
  GoodixSelfState *state;
  GoodixSecureSessionMaterial secure_view;
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];
  guint8 validator[GOODIX_SELF_STATE_DIGEST_LENGTH];
  guint8 config90[GOODIX_CONFIG90_LENGTH];
  guint8 fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH];
};

static GQuark
coordinator_error_quark (void)
{
  return g_quark_from_static_string ("goodix-runtime-coordinator-error");
}

static void
set_decision_error (GoodixRuntimeCoordinatorAudit    *audit,
                    GoodixRuntimeCoordinatorDecision  decision,
                    const gchar                      *message,
                    GError                          **error)
{
  if (audit != NULL)
    audit->decision = decision;
  g_set_error_literal (error, coordinator_error_quark (), decision, message);
}

static PathState
inspect_directory (const gchar *path,
                   uid_t        owner_uid,
                   gid_t        owner_gid,
                   mode_t       mode)
{
  struct stat status;

  if (path == NULL || !g_path_is_absolute (path))
    return PATH_INVALID;
  if (lstat (path, &status) != 0)
    return errno == ENOENT ? PATH_ABSENT : PATH_INVALID;
  if (!S_ISDIR (status.st_mode) || status.st_uid != owner_uid ||
      status.st_gid != owner_gid || (status.st_mode & 07777u) != mode)
    return PATH_INVALID;
  return PATH_DIRECTORY;
}

static gboolean
sha256 (const guint8 *input,
        gsize         input_length,
        guint8        output[GOODIX_SELF_STATE_DIGEST_LENGTH])
{
  unsigned int length = 0;

  return input != NULL &&
         EVP_Digest (input, input_length, output, &length, EVP_sha256 (),
                     NULL) == 1 &&
         length == GOODIX_SELF_STATE_DIGEST_LENGTH;
}

static gboolean
live_evidence_valid (const GoodixRuntimeCoordinatorLiveEvidence *live)
{
  return live != NULL && live->vid == 0x27c6u && live->pid == 0x5125u &&
         live->chip_id != 0u && live->app != NULL &&
         g_str_equal (live->app, "APP12509") &&
         live->a2_response != NULL && live->a2_response_length > 0u &&
         live->chip_response != NULL && live->chip_response_length > 0u &&
         live->otp != NULL && live->otp_length == GOODIX_CONFIG90_OTP_LENGTH &&
         live->live_validator != NULL &&
         live->live_validator_length == GOODIX_SELF_STATE_DIGEST_LENGTH;
}

static GoodixRuntimeCoordinator *
acquire_state (const GoodixRuntimeCoordinatorPaths        *paths,
               const GoodixRuntimeCoordinatorPolicy       *policy,
               const GoodixRuntimeCoordinatorLiveEvidence *live,
               GoodixRuntimeCoordinatorAudit              *audit,
               GError                                    **error)
{
  static const guint8 identity[] = "GF_ST411SEC_APP_12509";
  GoodixRuntimeCoordinator *coordinator = NULL;
  GoodixConfig90Calibration calibration = { 0 };
  GoodixSelfStateBinding binding = { 0 };
  GoodixSelfStateReconcile reconciliation;
  GoodixSelfStateLoadResult load_result;
  const GoodixSelfStateRecord *record;
  guint8 otp_sha256[GOODIX_SELF_STATE_DIGEST_LENGTH] = { 0 };
  guint8 config_sha256[GOODIX_SELF_STATE_DIGEST_LENGTH] = { 0 };

  if (audit != NULL)
    audit->state_load_attempted = TRUE;
  if (!live_evidence_valid (live))
    {
      set_decision_error (audit,
                          GOODIX_RUNTIME_COORDINATOR_DECISION_FAIL_CLOSED,
                          "state-v2 live evidence is incomplete", error);
      return NULL;
    }
  coordinator = g_new0 (GoodixRuntimeCoordinator, 1);
  if (!goodix_config90_derive (live->chip_id, live->otp, live->otp_length,
                               coordinator->config90, &calibration, error) ||
      !sha256 (live->otp, live->otp_length, otp_sha256) ||
      !sha256 (coordinator->config90, sizeof coordinator->config90,
               config_sha256))
    goto fail_closed;
  binding.vid = live->vid;
  binding.pid = live->pid;
  binding.chip_profile = live->chip_id;
  g_strlcpy (binding.app, live->app, sizeof binding.app);
  memcpy (binding.otp_sha256, otp_sha256, sizeof binding.otp_sha256);
  memcpy (binding.config90_sha256, config_sha256,
          sizeof binding.config90_sha256);
  load_result = goodix_self_state_load (paths->state_directory, &binding,
                                        &policy->state, &coordinator->state,
                                        error);
  if (audit != NULL)
    audit->state_load_result = load_result;
  if (load_result != GOODIX_SELF_STATE_LOAD_VALID)
    {
      if (audit != NULL)
        audit->decision = GOODIX_RUNTIME_COORDINATOR_DECISION_FAIL_CLOSED;
      if (error == NULL || *error == NULL)
        set_decision_error (
          audit, GOODIX_RUNTIME_COORDINATOR_DECISION_FAIL_CLOSED,
          load_result == GOODIX_SELF_STATE_LOAD_BINDING_MISMATCH ?
            "state-v2 binding does not match live evidence" :
            "state-v2 is incomplete or unavailable", error);
      goto fail;
    }
  reconciliation = goodix_self_state_reconcile (
    coordinator->state, live->live_validator, live->tls_proven);
  if (audit != NULL)
    audit->reconciliation = reconciliation;
  switch (reconciliation)
    {
    case GOODIX_SELF_STATE_RECONCILE_ACTIVE_MATCH:
      if (audit != NULL)
        audit->decision = GOODIX_RUNTIME_COORDINATOR_DECISION_READY_ACTIVE;
      break;
    case GOODIX_SELF_STATE_RECONCILE_RETRY_TLS:
      if (audit != NULL)
        audit->decision = GOODIX_RUNTIME_COORDINATOR_DECISION_READY_RETRY_TLS;
      break;
    case GOODIX_SELF_STATE_RECONCILE_PROMOTE_ACTIVE:
      set_decision_error (
        audit, GOODIX_RUNTIME_COORDINATOR_DECISION_PROMOTION_REQUIRED,
        "state-v2 requires a later host-only promotion", error);
      goto fail;
    case GOODIX_SELF_STATE_RECONCILE_USE_PRIOR:
      set_decision_error (
        audit, GOODIX_RUNTIME_COORDINATOR_DECISION_USE_PRIOR_REQUIRED,
        "state-v2 requires the preserved prior generation", error);
      goto fail;
    case GOODIX_SELF_STATE_RECONCILE_EXTERNAL_REPLACEMENT:
      set_decision_error (
        audit, GOODIX_RUNTIME_COORDINATOR_DECISION_EXTERNAL_REPLACEMENT,
        "live pairing validator was replaced externally", error);
      goto fail;
    case GOODIX_SELF_STATE_RECONCILE_RECOVERY_REQUIRED:
    default:
      set_decision_error (
        audit, GOODIX_RUNTIME_COORDINATOR_DECISION_RECOVERY_REQUIRED,
        "state-v2 reconciliation requires explicit recovery", error);
      goto fail;
    }
  record = goodix_self_state_get_record (coordinator->state);
  if (!goodix_self_state_copy_psk (coordinator->state, coordinator->psk) ||
      !sha256 (live->live_validator, live->live_validator_length,
               coordinator->secure_view.e4_validator_sha256) ||
      !sha256 (live->a2_response, live->a2_response_length,
               coordinator->secure_view.a2_response_sha256) ||
      !sha256 (live->chip_response, live->chip_response_length,
               coordinator->secure_view.chip82_response_sha256) ||
      !sha256 (live->otp, live->otp_length,
               coordinator->secure_view.otp_a6_response_sha256))
    goto fail_closed;
  memcpy (coordinator->validator, live->live_validator,
          sizeof coordinator->validator);
  coordinator->secure_view.expected_identity = identity;
  coordinator->secure_view.expected_identity_length = sizeof identity;
  coordinator->secure_view.e4_validator = coordinator->validator;
  coordinator->secure_view.e4_validator_length = sizeof coordinator->validator;
  coordinator->secure_view.config90 = coordinator->config90;
  coordinator->secure_view.config90_length = sizeof coordinator->config90;
  memcpy (coordinator->secure_view.config90_sha256, config_sha256,
          sizeof coordinator->secure_view.config90_sha256);
  coordinator->secure_view.psk = coordinator->psk;
  coordinator->secure_view.psk_length = sizeof coordinator->psk;
  for (guint i = 0; i < G_N_ELEMENTS (calibration.dac_registers); i++)
    {
      coordinator->secure_view.dac_values[i][0] =
        (guint8) (calibration.dac_registers[i] & 0xffu);
      coordinator->secure_view.dac_values[i][1] =
        (guint8) (calibration.dac_registers[i] >> 8);
    }
  if (record->fdt_present)
    memcpy (coordinator->fdt_seed, record->fdt_table,
            sizeof coordinator->fdt_seed);
  else if (audit != NULL)
    audit->zero_fdt_seed = TRUE;
  coordinator->source = GOODIX_RUNTIME_COORDINATOR_SOURCE_STATE_V2;
  if (audit != NULL)
    audit->source = coordinator->source;
  OPENSSL_cleanse (otp_sha256, sizeof otp_sha256);
  OPENSSL_cleanse (config_sha256, sizeof config_sha256);
  OPENSSL_cleanse (&calibration, sizeof calibration);
  return coordinator;

fail_closed:
  if (audit != NULL)
    audit->decision = GOODIX_RUNTIME_COORDINATOR_DECISION_FAIL_CLOSED;
  if (error == NULL || *error == NULL)
    set_decision_error (audit,
                        GOODIX_RUNTIME_COORDINATOR_DECISION_FAIL_CLOSED,
                        "state-v2 material derivation failed closed", error);
fail:
  OPENSSL_cleanse (otp_sha256, sizeof otp_sha256);
  OPENSSL_cleanse (config_sha256, sizeof config_sha256);
  OPENSSL_cleanse (&calibration, sizeof calibration);
  goodix_runtime_coordinator_free (coordinator);
  return NULL;
}

void
goodix_runtime_coordinator_paths_production (
  GoodixRuntimeCoordinatorPaths *paths)
{
  g_return_if_fail (paths != NULL);
  memset (paths, 0, sizeof *paths);
  paths->state_directory = "/var/lib/fprint/goodix-5125-state-v2";
  goodix_runtime_material_paths_production (&paths->legacy);
}

void
goodix_runtime_coordinator_policy_production (
  GoodixRuntimeCoordinatorPolicy *policy)
{
  g_return_if_fail (policy != NULL);
  memset (policy, 0, sizeof *policy);
  goodix_self_state_policy_for_owner (&policy->state, 0u, 0u);
  goodix_runtime_material_policy_production (&policy->legacy);
}

GoodixRuntimeCoordinator *
goodix_runtime_coordinator_acquire (
  const GoodixRuntimeCoordinatorPaths        *paths,
  const GoodixRuntimeCoordinatorPolicy       *policy,
  const GoodixRuntimeCoordinatorLiveEvidence *live,
  GoodixRuntimeCoordinatorLegacyAcquireFunc   legacy_acquire,
  GoodixRuntimeCoordinatorLegacyReleaseFunc   legacy_release,
  gpointer                                    legacy_user_data,
  GoodixRuntimeMaterialAudit                  *legacy_audit,
  GoodixRuntimeCoordinatorAudit               *audit,
  GError                                     **error)
{
  GoodixRuntimeCoordinator *coordinator;
  PathState state_path;
  PathState legacy_path;

  if (audit != NULL)
    {
      memset (audit, 0, sizeof *audit);
      audit->state_load_result = GOODIX_SELF_STATE_LOAD_ABSENT;
      audit->writer_enabled = FALSE;
      audit->pairing_write_count = 0u;
    }
  if (paths == NULL || policy == NULL || paths->state_directory == NULL ||
      paths->legacy.directory_path == NULL || legacy_acquire == NULL ||
      legacy_release == NULL)
    {
      set_decision_error (audit,
                          GOODIX_RUNTIME_COORDINATOR_DECISION_FAIL_CLOSED,
                          "runtime coordinator arguments are invalid", error);
      return NULL;
    }
  state_path = inspect_directory (paths->state_directory,
                                  policy->state.owner_uid,
                                  policy->state.owner_gid,
                                  policy->state.directory_mode);
  legacy_path = inspect_directory (paths->legacy.directory_path,
                                   policy->legacy.directory_owner_uid,
                                   policy->legacy.directory_owner_gid,
                                   policy->legacy.directory_mode);
  if (state_path == PATH_INVALID || legacy_path == PATH_INVALID)
    {
      set_decision_error (audit,
                          GOODIX_RUNTIME_COORDINATOR_DECISION_FAIL_CLOSED,
                          "runtime coordinator directory policy mismatch",
                          error);
      return NULL;
    }
  if (audit != NULL)
    {
      audit->state_present = state_path == PATH_DIRECTORY;
      audit->legacy_present = legacy_path == PATH_DIRECTORY;
      audit->coexistence_observed = audit->state_present &&
                                    audit->legacy_present;
    }
  if (live != NULL && state_path == PATH_DIRECTORY)
    {
      coordinator = acquire_state (paths, policy, live, audit, error);
      if (coordinator != NULL)
        return coordinator;
      /* An empty, policy-correct state root is expected while an installed
       * legacy set is still the migration source.  Any partial, mismatched or
       * invalid state remains authoritative and fails closed. */
      if (audit == NULL ||
          audit->state_load_result != GOODIX_SELF_STATE_LOAD_ABSENT ||
          legacy_path != PATH_DIRECTORY)
        return NULL;
      if (error != NULL)
        g_clear_error (error);
      audit->decision = GOODIX_RUNTIME_COORDINATOR_DECISION_NONE;
    }
  if (legacy_path == PATH_DIRECTORY)
    {
      coordinator = g_new0 (GoodixRuntimeCoordinator, 1);
      coordinator->legacy_release = legacy_release;
      coordinator->legacy_user_data = legacy_user_data;
      if (audit != NULL)
        audit->legacy_load_attempted = TRUE;
      if (!legacy_acquire (&coordinator->legacy,
                           &coordinator->secure_view,
                           coordinator->fdt_seed, legacy_audit,
                           legacy_user_data, error) ||
          coordinator->legacy == NULL)
        {
          if (audit != NULL)
            audit->decision = GOODIX_RUNTIME_COORDINATOR_DECISION_FAIL_CLOSED;
          goodix_runtime_coordinator_free (coordinator);
          return NULL;
        }
      coordinator->source = GOODIX_RUNTIME_COORDINATOR_SOURCE_LEGACY;
      if (audit != NULL)
        {
          audit->source = coordinator->source;
          audit->decision = GOODIX_RUNTIME_COORDINATOR_DECISION_READY_LEGACY;
        }
      return coordinator;
    }
  if (state_path == PATH_DIRECTORY)
    set_decision_error (
      audit, GOODIX_RUNTIME_COORDINATOR_DECISION_NEEDS_LIVE_PREFLIGHT,
      "state-v2 requires the bounded read-only live preflight", error);
  else
    set_decision_error (
      audit, GOODIX_RUNTIME_COORDINATOR_DECISION_NEEDS_INITIALIZATION,
      "reader runtime state is not initialized", error);
  return NULL;
}

gboolean
goodix_runtime_coordinator_get_secure_view (
  GoodixRuntimeCoordinator    *coordinator,
  GoodixSecureSessionMaterial *view,
  GError                     **error)
{
  if (coordinator == NULL || view == NULL ||
      coordinator->source == GOODIX_RUNTIME_COORDINATOR_SOURCE_NONE)
    {
      g_set_error_literal (error, coordinator_error_quark (), EINVAL,
                           "runtime coordinator secure view is unavailable");
      return FALSE;
    }
  *view = coordinator->secure_view;
  return TRUE;
}

gboolean
goodix_runtime_coordinator_get_fdt_seed (
  GoodixRuntimeCoordinator *coordinator,
  guint8 output[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GError **error)
{
  if (coordinator == NULL || output == NULL ||
      coordinator->source == GOODIX_RUNTIME_COORDINATOR_SOURCE_NONE)
    {
      g_set_error_literal (error, coordinator_error_quark (), EINVAL,
                           "runtime coordinator FDT seed is unavailable");
      return FALSE;
    }
  memcpy (output, coordinator->fdt_seed, GOODIX_RUNTIME_FDT_SEED_LENGTH);
  return TRUE;
}

GoodixRuntimeCoordinatorSource
goodix_runtime_coordinator_get_source (
  const GoodixRuntimeCoordinator *coordinator)
{
  return coordinator == NULL ? GOODIX_RUNTIME_COORDINATOR_SOURCE_NONE :
                               coordinator->source;
}

void
goodix_runtime_coordinator_free (GoodixRuntimeCoordinator *coordinator)
{
  if (coordinator == NULL)
    return;
  if (coordinator->legacy != NULL && coordinator->legacy_release != NULL)
    coordinator->legacy_release (coordinator->legacy,
                                 coordinator->legacy_user_data);
  goodix_self_state_free (coordinator->state);
  OPENSSL_cleanse (coordinator, sizeof *coordinator);
  g_free (coordinator);
}
