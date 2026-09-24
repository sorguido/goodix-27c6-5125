/* SPDX-License-Identifier: GPL-2.0-or-later */
/* USB-free material validation using the production loader and crypto binder. */
#include "goodix_runtime_material.h"
#include <stdio.h>
#include <sys/resource.h>

int
main (int argc, char **argv)
{
  GoodixRuntimeMaterialPolicy policy;
  GoodixRuntimeMaterialPaths paths;
  GoodixRuntimeMaterial *material;
  gboolean valid;
  GError *error = NULL;
  struct rlimit no_core = { 0, 0 };
  gchar *names[5];
  const gchar *const filenames[] = {
    "target-material-manifest.json", "transport-material.bin",
    "target-config-90.bin", "gfusb.dll", "fdt-cache.bin"
  };

  if (argc != 2 || argv[1][0] != '/')
    {
      fputs ("Usage: check-material /absolute/protected-material-directory\n", stderr);
      return 2;
    }
  if (setrlimit (RLIMIT_CORE, &no_core) != 0)
    {
      fputs ("MATERIAL_CHECK=FAIL cannot disable core dumps\n", stderr);
      return 1;
    }
  for (guint i = 0; i < G_N_ELEMENTS (names); i++)
    names[i] = g_build_filename (argv[1], filenames[i], NULL);
  goodix_runtime_material_policy_production (&policy);
  paths = (GoodixRuntimeMaterialPaths) {
    .directory_path = argv[1], .manifest_path = names[0],
    .transport_path = names[1], .config90_path = names[2],
    .pe_path = names[3], .fdt_cache_path = names[4]
  };
  material = goodix_runtime_material_load (&paths, &policy, NULL, &error);
  valid = material != NULL;
  if (material == NULL)
    fprintf (stderr, "MATERIAL_CHECK=FAIL %s\n", error != NULL ? error->message : "validation failed");
  else
    puts ("MATERIAL_CHECK=PASS USB_ACCESSED=false");
  goodix_runtime_material_free (material);
  g_clear_error (&error);
  for (guint i = 0; i < G_N_ELEMENTS (names); i++)
    g_free (names[i]);
  return valid ? 0 : 1;
}
