/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_PAIRING_ACTIVATION_H
#define GOODIX_PAIRING_ACTIVATION_H

#include <glib.h>

#include "goodix_live_preflight.h"
#include "goodix_pairing_provision.h"
#include "goodix_secure_session.h"
#include "goodix_self_state.h"

G_BEGIN_DECLS

typedef enum
{
  GOODIX_PAIRING_ACTIVATION_E0 = 0,
  GOODIX_PAIRING_ACTIVATION_READ_BB010002,
  GOODIX_PAIRING_ACTIVATION_READ_VALIDATOR,
  GOODIX_PAIRING_ACTIVATION_TLS,
  GOODIX_PAIRING_ACTIVATION_COMPLETE,
  GOODIX_PAIRING_ACTIVATION_TERMINAL,
} GoodixPairingActivationPhase;

typedef enum
{
  GOODIX_PAIRING_ACTIVATION_DISPOSITION_NONE = 0,
  GOODIX_PAIRING_ACTIVATION_DISPOSITION_NEW_PSK,
  GOODIX_PAIRING_ACTIVATION_DISPOSITION_RESTORE_ACTIVE_PSK,
  GOODIX_PAIRING_ACTIVATION_DISPOSITION_RECOVER_PREPARED_TLS,
  GOODIX_PAIRING_ACTIVATION_DISPOSITION_REUSE_ACTIVE_TLS,
} GoodixPairingActivationDisposition;

typedef struct
{
  const gchar *state_directory;
} GoodixPairingActivationPaths;

typedef struct
{
  GoodixSelfStatePolicy state;
} GoodixPairingActivationPolicy;

typedef struct
{
  GoodixPairingActivationDisposition disposition;
  GoodixSelfStateLoadResult state_load_result;
  GoodixSelfStateReconcile reconciliation;
  GoodixPairingProvisionAudit provision;
  guint readback_command_count;
  guint readback_ack_count;
  guint readback_typed_count;
  guint retry_count;
  guint persistent_write_count;
  gboolean prepared_journaled;
  gboolean e0_reserved_before_submit;
  gboolean bb010002_readback_match;
  gboolean validator_readback_match;
  gboolean tls_proven;
  gboolean active_promoted;
  gboolean recovered_without_e0;
  gboolean active_reused_without_e0;
} GoodixPairingActivationAudit;

typedef struct _GoodixPairingActivation GoodixPairingActivation;

void goodix_pairing_activation_paths_production (
  GoodixPairingActivationPaths *paths);
void goodix_pairing_activation_policy_production (
  GoodixPairingActivationPolicy *policy);

GoodixPairingActivation *goodix_pairing_activation_new (
  const GoodixPairingActivationPaths  *paths,
  const GoodixPairingActivationPolicy *policy,
  const GoodixLivePreflightEvidence   *evidence,
  GoodixPairingActivationAudit        *audit,
  GError                             **error);

#ifdef GOODIX_ENABLE_TEST_SEAMS
GoodixPairingActivation *goodix_pairing_activation_new_for_test (
  const GoodixPairingActivationPaths  *paths,
  const GoodixPairingActivationPolicy *policy,
  const GoodixLivePreflightEvidence   *evidence,
  const guint8                         psk[GOODIX_SELF_STATE_PSK_LENGTH],
  GoodixPairingActivationAudit        *audit,
  GError                             **error);
#endif

GBytes *goodix_pairing_activation_next_request (
  GoodixPairingActivation *activation,
  GError                 **error);
void goodix_pairing_activation_out_complete (
  GoodixPairingActivation *activation,
  const GError            *error);
gboolean goodix_pairing_activation_handle_a0 (
  GoodixPairingActivation *activation,
  GBytes                  *frame,
  GError                 **error);
gboolean goodix_pairing_activation_needs_receive (
  const GoodixPairingActivation *activation);
GoodixPairingActivationPhase goodix_pairing_activation_get_phase (
  const GoodixPairingActivation *activation);
const GError *goodix_pairing_activation_get_error (
  const GoodixPairingActivation *activation);

gboolean goodix_pairing_activation_get_secure_view (
  GoodixPairingActivation   *activation,
  GoodixSecureSessionMaterial *view,
  GError                   **error);
gboolean goodix_pairing_activation_mark_tls_and_promote (
  GoodixPairingActivation *activation,
  GError                 **error);
void goodix_pairing_activation_free (GoodixPairingActivation *activation);

G_DEFINE_AUTOPTR_CLEANUP_FUNC (GoodixPairingActivation,
                               goodix_pairing_activation_free)

G_END_DECLS

#endif
