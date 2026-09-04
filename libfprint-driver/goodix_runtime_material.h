/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_RUNTIME_MATERIAL_H
#define GOODIX_RUNTIME_MATERIAL_H

#include <glib.h>

#include "goodix_runtime_inputs.h"
#include "goodix_target_material.h"

G_BEGIN_DECLS

typedef struct _GoodixRuntimeMaterial GoodixRuntimeMaterial;

typedef struct
{
  const gchar *directory_path;
  const gchar *manifest_path;
  const gchar *transport_path;
  const gchar *config90_path;
  const gchar *pe_path;
  const gchar *fdt_cache_path;
} GoodixRuntimeMaterialPaths;

typedef struct
{
  uid_t directory_owner_uid;
  gid_t directory_owner_gid;
  mode_t directory_mode;
  GoodixTargetMaterialPolicy target;
  GoodixRuntimePePolicy pe;
  GoodixRuntimeFdtPolicy fdt;
  GoodixRuntimeInputFilePolicy private_files;
} GoodixRuntimeMaterialPolicy;

typedef struct
{
  GoodixTargetMaterialAudit target;
  GoodixRuntimeInputFileAudit private_files;
  guint directory_open_count;
  guint producer_seed_cleanse_count;
  guint owner_free_count;
  gboolean directory_verified;
  gboolean producer_seeds_cleansed;
  gboolean descriptor_cleansed;
  gboolean fdt_seed_cleansed;
} GoodixRuntimeMaterialAudit;

void goodix_runtime_material_policy_production (
  GoodixRuntimeMaterialPolicy *policy);

/* Authorized production layout.  This only publishes inert path constants;
 * it never creates, discovers, opens or reads any file. */
void goodix_runtime_material_paths_production (
  GoodixRuntimeMaterialPaths *paths);

/* Audit storage, when non-NULL, must outlive the returned owner. */
GoodixRuntimeMaterial *goodix_runtime_material_load (
  const GoodixRuntimeMaterialPaths  *paths,
  const GoodixRuntimeMaterialPolicy *policy,
  GoodixRuntimeMaterialAudit        *audit,
  GError                           **error);

/* Returned descriptors borrow storage from the owner.  The caller must not
 * retain them after goodix_runtime_material_free() and should clear local
 * descriptor copies immediately after configuring their consumer. */
gboolean goodix_runtime_material_get_secure_view (
  GoodixRuntimeMaterial       *material,
  GoodixSecureSessionMaterial *view,
  GError                     **error);

gboolean goodix_runtime_material_get_fdt_seed (
  GoodixRuntimeMaterial *material,
  guint8 output[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GError **error);

void goodix_runtime_material_free (GoodixRuntimeMaterial *material);

G_END_DECLS

#endif
