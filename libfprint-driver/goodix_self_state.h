/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_SELF_STATE_H
#define GOODIX_SELF_STATE_H

#include <sys/types.h>

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_SELF_STATE_PSK_LENGTH 32u
#define GOODIX_SELF_STATE_DIGEST_LENGTH 32u
#define GOODIX_SELF_STATE_FDT_LENGTH 12u
#define GOODIX_SELF_STATE_APP_MAX 32u

typedef enum
{
  GOODIX_SELF_STATE_PREPARED = 1,
  GOODIX_SELF_STATE_ACTIVE = 2,
  GOODIX_SELF_STATE_RECOVERY_REQUIRED = 3,
} GoodixSelfStatePhase;

typedef enum
{
  GOODIX_SELF_STATE_LOAD_ABSENT,
  GOODIX_SELF_STATE_LOAD_VALID,
  GOODIX_SELF_STATE_LOAD_INCOMPLETE,
  GOODIX_SELF_STATE_LOAD_BINDING_MISMATCH,
} GoodixSelfStateLoadResult;

typedef enum
{
  GOODIX_SELF_STATE_RECONCILE_ACTIVE_MATCH,
  GOODIX_SELF_STATE_RECONCILE_EXTERNAL_REPLACEMENT,
  GOODIX_SELF_STATE_RECONCILE_RETRY_TLS,
  GOODIX_SELF_STATE_RECONCILE_PROMOTE_ACTIVE,
  GOODIX_SELF_STATE_RECONCILE_USE_PRIOR,
  GOODIX_SELF_STATE_RECONCILE_RECOVERY_REQUIRED,
} GoodixSelfStateReconcile;

typedef enum
{
  GOODIX_SELF_STATE_FAULT_SECRET_TEMP_WRITTEN,
  GOODIX_SELF_STATE_FAULT_SECRET_FILE_SYNCED,
  GOODIX_SELF_STATE_FAULT_SECRET_RENAMED,
  GOODIX_SELF_STATE_FAULT_SECRET_DIRECTORY_SYNCED,
  GOODIX_SELF_STATE_FAULT_RECEIPT_TEMP_WRITTEN,
  GOODIX_SELF_STATE_FAULT_RECEIPT_FILE_SYNCED,
  GOODIX_SELF_STATE_FAULT_RECEIPT_RENAMED,
  GOODIX_SELF_STATE_FAULT_RECEIPT_DIRECTORY_SYNCED,
} GoodixSelfStateFaultPoint;

typedef gboolean (*GoodixSelfStateFaultFunc) (GoodixSelfStateFaultPoint point,
                                               gpointer                  data);

typedef struct
{
  guint16 vid;
  guint16 pid;
  guint16 chip_profile;
  gchar app[GOODIX_SELF_STATE_APP_MAX];
  guint8 otp_sha256[GOODIX_SELF_STATE_DIGEST_LENGTH];
  guint8 config90_sha256[GOODIX_SELF_STATE_DIGEST_LENGTH];
} GoodixSelfStateBinding;

typedef struct
{
  uid_t owner_uid;
  gid_t owner_gid;
  mode_t directory_mode;
  mode_t file_mode;
  GoodixSelfStateFaultFunc fault;
  gpointer fault_data;
} GoodixSelfStatePolicy;

typedef struct
{
  GoodixSelfStatePhase phase;
  guint64 generation;
  guint8 expected_validator[GOODIX_SELF_STATE_DIGEST_LENGTH];
  gboolean prior_validator_present;
  guint8 prior_validator[GOODIX_SELF_STATE_DIGEST_LENGTH];
  gboolean fdt_present;
  guint8 fdt_table[GOODIX_SELF_STATE_FDT_LENGTH];
  gboolean migrated_legacy;
  guint8 legacy_source_sha256[GOODIX_SELF_STATE_DIGEST_LENGTH];
  gboolean bb010002_sha256_present;
  guint8 bb010002_sha256[GOODIX_SELF_STATE_DIGEST_LENGTH];
  gboolean e0_attempted;
  gboolean terminal_proof;
} GoodixSelfStateRecord;

typedef struct _GoodixSelfState GoodixSelfState;

void goodix_self_state_policy_for_owner (GoodixSelfStatePolicy *policy,
                                         uid_t                  uid,
                                         gid_t                  gid);

GoodixSelfStateLoadResult goodix_self_state_load (
  const gchar                  *directory,
  const GoodixSelfStateBinding *binding,
  const GoodixSelfStatePolicy  *policy,
  GoodixSelfState             **state,
  GError                      **error);

gboolean goodix_self_state_write_prepared (
  const gchar                  *directory,
  const GoodixSelfStateBinding *binding,
  const GoodixSelfStateRecord  *record,
  const guint8                  psk[GOODIX_SELF_STATE_PSK_LENGTH],
  const GoodixSelfStatePolicy  *policy,
  GError                      **error);

/* Side-by-side migration seam. The caller must obtain these values from the
 * already qualified legacy loader and supply a digest covering that immutable
 * source set. This function never opens, rewrites or removes legacy files. */
gboolean goodix_self_state_import_legacy (
  const gchar                  *directory,
  const GoodixSelfStateBinding *binding,
  const guint8                  psk[GOODIX_SELF_STATE_PSK_LENGTH],
  const guint8                  validator[GOODIX_SELF_STATE_DIGEST_LENGTH],
  const guint8                  legacy_source_sha256[GOODIX_SELF_STATE_DIGEST_LENGTH],
  const guint8                 *fdt_table,
  const GoodixSelfStatePolicy  *policy,
  GError                      **error);

GoodixSelfStateReconcile goodix_self_state_reconcile (
  const GoodixSelfState *state,
  const guint8           live_validator[GOODIX_SELF_STATE_DIGEST_LENGTH],
  gboolean               tls_proven);

gboolean goodix_self_state_promote_active (
  const gchar                 *directory,
  const GoodixSelfState       *prepared,
  const GoodixSelfStatePolicy *policy,
  GError                     **error);

const GoodixSelfStateRecord *goodix_self_state_get_record (
  const GoodixSelfState *state);
const GoodixSelfStateBinding *goodix_self_state_get_binding (
  const GoodixSelfState *state);
gboolean goodix_self_state_copy_psk (
  const GoodixSelfState *state,
  guint8                  psk[GOODIX_SELF_STATE_PSK_LENGTH]);
void goodix_self_state_free (GoodixSelfState *state);

G_END_DECLS

#endif
