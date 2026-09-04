/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_runtime_material.h"

#include <openssl/crypto.h>

#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

typedef enum
{
  GOODIX_RUNTIME_MATERIAL_ERROR_ARGUMENT,
  GOODIX_RUNTIME_MATERIAL_ERROR_LAYOUT,
  GOODIX_RUNTIME_MATERIAL_ERROR_STATE,
} GoodixRuntimeMaterialError;

#define GOODIX_RUNTIME_MATERIAL_ERROR (goodix_runtime_material_error_quark ())

struct _GoodixRuntimeMaterial
{
  GoodixTargetMaterial *target_owner;
  GoodixSecureSessionMaterial secure_view;
  guint8 fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH];
  GoodixRuntimeMaterialAudit *audit;
};

static GQuark
goodix_runtime_material_error_quark (void)
{
  return g_quark_from_static_string ("goodix-runtime-material-error");
}

void
goodix_runtime_material_policy_production (GoodixRuntimeMaterialPolicy *policy)
{
  g_return_if_fail (policy != NULL);
  memset (policy, 0, sizeof *policy);
  policy->directory_owner_uid = 0;
  policy->directory_owner_gid = 0;
  policy->directory_mode = 0700;
  goodix_target_material_policy_production (&policy->target);
  goodix_runtime_pe_policy_production (&policy->pe);
  goodix_runtime_fdt_policy_production (&policy->fdt);
  goodix_runtime_input_file_policy_production (&policy->private_files);
}

void
goodix_runtime_material_paths_production (GoodixRuntimeMaterialPaths *paths)
{
  static const gchar directory[] = "/var/lib/goodix-5125-poc";

  g_return_if_fail (paths != NULL);
  *paths = (GoodixRuntimeMaterialPaths) {
    .directory_path = directory,
    .manifest_path = "/var/lib/goodix-5125-poc/target-material-manifest.json",
    .transport_path = "/var/lib/goodix-5125-poc/transport-material.bin",
    .config90_path = "/var/lib/goodix-5125-poc/target-config-90.bin",
    .pe_path = "/var/lib/goodix-5125-poc/gfusb.dll",
    .fdt_cache_path = "/var/lib/goodix-5125-poc/fdt-cache.bin",
  };
}

static gboolean
path_is_direct_child (const gchar *directory,
                      const gchar *path)
{
  g_autofree gchar *parent = NULL;

  if (directory == NULL || path == NULL || !g_path_is_absolute (directory) ||
      !g_path_is_absolute (path))
    return FALSE;
  parent = g_path_get_dirname (path);
  return g_str_equal (parent, directory);
}

static gboolean
paths_valid (const GoodixRuntimeMaterialPaths *paths)
{
  return paths != NULL && paths->directory_path != NULL &&
         path_is_direct_child (paths->directory_path, paths->manifest_path) &&
         path_is_direct_child (paths->directory_path, paths->transport_path) &&
         path_is_direct_child (paths->directory_path, paths->config90_path) &&
         path_is_direct_child (paths->directory_path, paths->pe_path) &&
         path_is_direct_child (paths->directory_path, paths->fdt_cache_path) &&
         paths->transport_path != NULL && paths->config90_path != NULL &&
         paths->pe_path != NULL && paths->fdt_cache_path != NULL;
}

static gboolean
directory_metadata_valid (const struct stat                 *status,
                          const GoodixRuntimeMaterialPolicy *policy)
{
  return S_ISDIR (status->st_mode) &&
         status->st_uid == policy->directory_owner_uid &&
         status->st_gid == policy->directory_owner_gid &&
         (status->st_mode & 07777u) == policy->directory_mode;
}

static gboolean
policy_layout_valid (const GoodixRuntimeMaterialPolicy *policy)
{
  return policy != NULL && policy->directory_mode == 0700 &&
         policy->target.owner_uid == policy->directory_owner_uid &&
         policy->target.owner_gid == policy->directory_owner_gid &&
         policy->private_files.owner_uid == policy->directory_owner_uid &&
         policy->private_files.owner_gid == policy->directory_owner_gid;
}

static gboolean
directory_unchanged (const gchar                       *path,
                     gint                               fd,
                     const struct stat                 *before,
                     const GoodixRuntimeMaterialPolicy *policy)
{
  struct stat held;
  struct stat current;

  return fstat (fd, &held) == 0 && lstat (path, &current) == 0 &&
         held.st_dev == before->st_dev && held.st_ino == before->st_ino &&
         current.st_dev == before->st_dev && current.st_ino == before->st_ino &&
         directory_metadata_valid (&held, policy) &&
         directory_metadata_valid (&current, policy);
}

GoodixRuntimeMaterial *
goodix_runtime_material_load (const GoodixRuntimeMaterialPaths  *paths,
                              const GoodixRuntimeMaterialPolicy *policy,
                              GoodixRuntimeMaterialAudit        *audit,
                              GError                           **error)
{
  GoodixRuntimeMaterial *material = NULL;
  guint8 seed_a[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH] = { 0 };
  guint8 seed_b[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH] = { 0 };
  guint8 fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH] = { 0 };
  struct stat directory_before;
  gint directory_fd = -1;

  if (audit != NULL)
    memset (audit, 0, sizeof *audit);
  if (!paths_valid (paths) || !policy_layout_valid (policy))
    {
      g_set_error_literal (error, GOODIX_RUNTIME_MATERIAL_ERROR,
                           GOODIX_RUNTIME_MATERIAL_ERROR_ARGUMENT,
                           "runtime material paths or policy are invalid");
      goto fail;
    }

  directory_fd = open (paths->directory_path,
                       O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
  if (directory_fd < 0)
    {
      g_set_error (error, GOODIX_RUNTIME_MATERIAL_ERROR,
                   GOODIX_RUNTIME_MATERIAL_ERROR_LAYOUT,
                   "runtime material directory open failed: %s",
                   g_strerror (errno));
      goto fail;
    }
  if (audit != NULL)
    audit->directory_open_count++;
  if (fstat (directory_fd, &directory_before) != 0 ||
      !directory_metadata_valid (&directory_before, policy))
    {
      g_set_error_literal (error, GOODIX_RUNTIME_MATERIAL_ERROR,
                           GOODIX_RUNTIME_MATERIAL_ERROR_LAYOUT,
                           "runtime material directory uid/gid/mode mismatch");
      goto fail;
    }

  if (!goodix_runtime_extract_inputs_from_files (
        paths->pe_path, paths->fdt_cache_path, &policy->pe, &policy->fdt,
        &policy->private_files, seed_a, seed_b, fdt_seed,
        audit != NULL ? &audit->private_files : NULL, error))
    goto fail;

  material = g_new0 (GoodixRuntimeMaterial, 1);
  material->audit = audit;
  material->target_owner = goodix_target_material_load (
    paths->manifest_path, paths->transport_path, paths->config90_path,
    &policy->target, audit != NULL ? &audit->target : NULL, error);
  if (material->target_owner == NULL ||
      !goodix_target_material_bind (material->target_owner, seed_a, seed_b,
                                    error) ||
      !goodix_target_material_get_secure_session_material (
        material->target_owner, &material->secure_view, error))
    goto fail;
  memcpy (material->fdt_seed, fdt_seed, sizeof material->fdt_seed);

  if (!directory_unchanged (paths->directory_path, directory_fd,
                            &directory_before, policy))
    {
      g_set_error_literal (error, GOODIX_RUNTIME_MATERIAL_ERROR,
                           GOODIX_RUNTIME_MATERIAL_ERROR_LAYOUT,
                           "runtime material directory changed during load");
      goto fail;
    }
  close (directory_fd);
  directory_fd = -1;
  if (audit != NULL)
    audit->directory_verified = TRUE;

  goodix_runtime_cleanse_producer_seed (seed_a);
  goodix_runtime_cleanse_producer_seed (seed_b);
  memset (fdt_seed, 0, sizeof fdt_seed);
  if (audit != NULL)
    {
      audit->producer_seed_cleanse_count = 2u;
      audit->producer_seeds_cleansed = TRUE;
    }
  return material;

fail:
  if (directory_fd >= 0)
    close (directory_fd);
  goodix_runtime_cleanse_producer_seed (seed_a);
  goodix_runtime_cleanse_producer_seed (seed_b);
  memset (fdt_seed, 0, sizeof fdt_seed);
  if (audit != NULL)
    {
      audit->producer_seed_cleanse_count = 2u;
      audit->producer_seeds_cleansed = TRUE;
    }
  goodix_runtime_material_free (material);
  return NULL;
}

gboolean
goodix_runtime_material_get_secure_view (GoodixRuntimeMaterial       *material,
                                         GoodixSecureSessionMaterial *view,
                                         GError                     **error)
{
  if (material == NULL || material->target_owner == NULL || view == NULL)
    {
      g_set_error_literal (error, GOODIX_RUNTIME_MATERIAL_ERROR,
                           GOODIX_RUNTIME_MATERIAL_ERROR_STATE,
                           "runtime secure material is unavailable");
      return FALSE;
    }
  *view = material->secure_view;
  return TRUE;
}

gboolean
goodix_runtime_material_get_fdt_seed (
  GoodixRuntimeMaterial *material,
  guint8 output[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GError **error)
{
  if (material == NULL || material->target_owner == NULL || output == NULL)
    {
      g_set_error_literal (error, GOODIX_RUNTIME_MATERIAL_ERROR,
                           GOODIX_RUNTIME_MATERIAL_ERROR_STATE,
                           "runtime FDT seed is unavailable");
      return FALSE;
    }
  memcpy (output, material->fdt_seed, GOODIX_RUNTIME_FDT_SEED_LENGTH);
  return TRUE;
}

void
goodix_runtime_material_free (GoodixRuntimeMaterial *material)
{
  if (material == NULL)
    return;
  memset (&material->secure_view, 0, sizeof material->secure_view);
  if (material->audit != NULL)
    material->audit->descriptor_cleansed = TRUE;
  goodix_target_material_free (material->target_owner);
  material->target_owner = NULL;
  OPENSSL_cleanse (material->fdt_seed, sizeof material->fdt_seed);
  if (material->audit != NULL)
    {
      material->audit->fdt_seed_cleansed = TRUE;
      material->audit->owner_free_count++;
    }
  OPENSSL_cleanse (material, sizeof *material);
  g_free (material);
}
