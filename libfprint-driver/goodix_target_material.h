/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_TARGET_MATERIAL_H
#define GOODIX_TARGET_MATERIAL_H

#include <sys/types.h>

#include <glib.h>

#include "goodix_secure_session.h"

G_BEGIN_DECLS

#define GOODIX_TARGET_MANIFEST_LENGTH 2305u
#define GOODIX_TARGET_TRANSPORT_LENGTH 88u

typedef struct _GoodixTargetMaterial GoodixTargetMaterial;

typedef void (*GoodixTargetMaterialAfterReadFunc) (const gchar *path,
                                                   gint         fd,
                                                   gpointer     user_data);
typedef void (*GoodixTargetMaterialCleanseObserver) (const gchar  *label,
                                                     const guint8 *bytes,
                                                     gsize         length,
                                                     gpointer      user_data);

typedef struct
{
  uid_t owner_uid;
  mode_t mode;
  gsize manifest_length;
  gsize transport_length;
  gsize config90_length;
  guint8 manifest_sha256[32];
  guint8 transport_sha256[32];
  guint8 config90_sha256[32];
  guint8 config90_finalizer[2];
  guint8 e4_validator_sha256[32];
  guint8 a2_response_sha256[32];
  guint8 chip82_response_sha256[32];
  guint8 otp_a6_response_sha256[32];
  guint16 dac_registers[4];
  guint8 dac_values[4][2];
  guint dac_offsets[4];

  /* Explicit host-only test seams.  Production policy leaves these NULL. */
  GoodixTargetMaterialAfterReadFunc after_read;
  gpointer after_read_data;
  GoodixTargetMaterialCleanseObserver cleanse_observer;
  gpointer cleanse_observer_data;
} GoodixTargetMaterialPolicy;

typedef struct
{
  guint protected_open_count;
  guint protected_read_count;
  guint owner_free_count;
  guint bind_count;
  guint psk_scratch_cleanse_count;
  guint owner_psk_cleanse_count;
  guint validator_cleanse_count;
  guint config90_cleanse_count;
  gboolean psk_scratch_cleansed;
  gboolean project_secret_zeroized;
  gboolean e4_binding_match;
} GoodixTargetMaterialAudit;

void goodix_target_material_policy_production (GoodixTargetMaterialPolicy *policy);

/* Stable redacted classification for this module's GError provenance. */
const gchar *goodix_target_material_error_class (const GError *error);

GoodixTargetMaterial *goodix_target_material_load (
  const gchar                      *manifest_path,
  const gchar                      *transport_path,
  const gchar                      *config90_path,
  const GoodixTargetMaterialPolicy *policy,
  GoodixTargetMaterialAudit        *audit,
  GError                          **error);

/* Bind from caller-owned producer seeds.  The caller remains responsible for
 * cleansing the seeds immediately after this call. */
gboolean goodix_target_material_bind (GoodixTargetMaterial *material,
                                      const guint8          seed_a[6],
                                      const guint8          seed_b[6],
                                      GError              **error);

gboolean goodix_target_material_get_secure_session_material (
  GoodixTargetMaterial        *material,
  GoodixSecureSessionMaterial *view,
  GError                     **error);

void goodix_target_material_free (GoodixTargetMaterial *material);

G_END_DECLS

#endif
