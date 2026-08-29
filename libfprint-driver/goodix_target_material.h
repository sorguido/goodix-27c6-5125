/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_TARGET_MATERIAL_H
#define GOODIX_TARGET_MATERIAL_H
#include "goodix_d190_binder.h"
#include "goodix_secure_session.h"
G_BEGIN_DECLS
typedef struct _GoodixTargetMaterial GoodixTargetMaterial;
typedef struct {
  uid_t required_uid;
  mode_t required_mode;
  guint8 manifest_sha256[32], transport_sha256[32], config_sha256[32], validator_sha256[32];
} GoodixTargetMaterialPolicy;
void goodix_target_material_policy_production (GoodixTargetMaterialPolicy *policy);
GoodixTargetMaterial *goodix_target_material_load (const gchar *manifest_path,
                                                   const gchar *transport_path,
                                                   const gchar *config_path,
                                                   const guint8 seed_a[6],
                                                   const guint8 seed_b[6],
                                                   const GoodixTargetMaterialPolicy *policy,
                                                   GError **error);
const GoodixSecureSessionMaterial *goodix_target_material_session (GoodixTargetMaterial *owner);
void goodix_target_material_free (GoodixTargetMaterial *owner);
G_END_DECLS
#endif
