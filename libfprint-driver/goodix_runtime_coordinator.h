/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_RUNTIME_COORDINATOR_H
#define GOODIX_RUNTIME_COORDINATOR_H

#include <glib.h>

#include "goodix_config90.h"
#include "goodix_runtime_material.h"
#include "goodix_self_state.h"

G_BEGIN_DECLS

typedef enum
{
  GOODIX_RUNTIME_COORDINATOR_SOURCE_NONE = 0,
  GOODIX_RUNTIME_COORDINATOR_SOURCE_LEGACY,
  GOODIX_RUNTIME_COORDINATOR_SOURCE_STATE_V2,
} GoodixRuntimeCoordinatorSource;

typedef enum
{
  GOODIX_RUNTIME_COORDINATOR_DECISION_NONE = 0,
  GOODIX_RUNTIME_COORDINATOR_DECISION_READY_LEGACY,
  GOODIX_RUNTIME_COORDINATOR_DECISION_READY_ACTIVE,
  GOODIX_RUNTIME_COORDINATOR_DECISION_READY_RETRY_TLS,
  GOODIX_RUNTIME_COORDINATOR_DECISION_NEEDS_LIVE_PREFLIGHT,
  GOODIX_RUNTIME_COORDINATOR_DECISION_NEEDS_INITIALIZATION,
  GOODIX_RUNTIME_COORDINATOR_DECISION_PROMOTION_REQUIRED,
  GOODIX_RUNTIME_COORDINATOR_DECISION_USE_PRIOR_REQUIRED,
  GOODIX_RUNTIME_COORDINATOR_DECISION_EXTERNAL_REPLACEMENT,
  GOODIX_RUNTIME_COORDINATOR_DECISION_RECOVERY_REQUIRED,
  GOODIX_RUNTIME_COORDINATOR_DECISION_FAIL_CLOSED,
} GoodixRuntimeCoordinatorDecision;

typedef struct
{
  const gchar *state_directory;
  GoodixRuntimeMaterialPaths legacy;
} GoodixRuntimeCoordinatorPaths;

typedef struct
{
  GoodixSelfStatePolicy state;
  GoodixRuntimeMaterialPolicy legacy;
} GoodixRuntimeCoordinatorPolicy;

/* Evidence collected by the bounded P6 read-only preflight.  P5 accepts this
 * shape and resolves it host-side, but deliberately contains no code that can
 * collect it from a device. */
typedef struct
{
  guint16 vid;
  guint16 pid;
  guint16 chip_id;
  const gchar *app;
  const guint8 *a2_response;
  gsize a2_response_length;
  const guint8 *chip_response;
  gsize chip_response_length;
  const guint8 *otp;
  gsize otp_length;
  const guint8 *live_validator;
  gsize live_validator_length;
  const guint8 *bb010002;
  gsize bb010002_length;
  gboolean tls_proven;
} GoodixRuntimeCoordinatorLiveEvidence;

typedef struct
{
  GoodixRuntimeCoordinatorSource source;
  GoodixRuntimeCoordinatorDecision decision;
  GoodixSelfStateLoadResult state_load_result;
  GoodixSelfStateReconcile reconciliation;
  gboolean state_present;
  gboolean legacy_present;
  gboolean coexistence_observed;
  gboolean state_load_attempted;
  gboolean legacy_load_attempted;
  gboolean writer_enabled;
  guint pairing_write_count;
  gboolean zero_fdt_seed;
} GoodixRuntimeCoordinatorAudit;

typedef struct _GoodixRuntimeCoordinator GoodixRuntimeCoordinator;

typedef gboolean (*GoodixRuntimeCoordinatorLegacyAcquireFunc) (
  GoodixRuntimeMaterial       **owner,
  GoodixSecureSessionMaterial  *secure_view,
  guint8                        fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GoodixRuntimeMaterialAudit   *audit,
  gpointer                      user_data,
  GError                      **error);

typedef void (*GoodixRuntimeCoordinatorLegacyReleaseFunc) (
  GoodixRuntimeMaterial *owner,
  gpointer               user_data);

void goodix_runtime_coordinator_paths_production (
  GoodixRuntimeCoordinatorPaths *paths);
void goodix_runtime_coordinator_policy_production (
  GoodixRuntimeCoordinatorPolicy *policy);

GoodixRuntimeCoordinator *goodix_runtime_coordinator_acquire (
  const GoodixRuntimeCoordinatorPaths        *paths,
  const GoodixRuntimeCoordinatorPolicy       *policy,
  const GoodixRuntimeCoordinatorLiveEvidence *live,
  GoodixRuntimeCoordinatorLegacyAcquireFunc   legacy_acquire,
  GoodixRuntimeCoordinatorLegacyReleaseFunc   legacy_release,
  gpointer                                    legacy_user_data,
  GoodixRuntimeMaterialAudit                  *legacy_audit,
  GoodixRuntimeCoordinatorAudit               *audit,
  GError                                     **error);

gboolean goodix_runtime_coordinator_get_secure_view (
  GoodixRuntimeCoordinator   *coordinator,
  GoodixSecureSessionMaterial *view,
  GError                     **error);
gboolean goodix_runtime_coordinator_get_fdt_seed (
  GoodixRuntimeCoordinator *coordinator,
  guint8 output[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GError **error);
gboolean goodix_runtime_coordinator_promote_after_tls (
  GoodixRuntimeCoordinator *coordinator,
  GError **error);
GoodixRuntimeCoordinatorSource goodix_runtime_coordinator_get_source (
  const GoodixRuntimeCoordinator *coordinator);
void goodix_runtime_coordinator_free (GoodixRuntimeCoordinator *coordinator);

G_END_DECLS

#endif
