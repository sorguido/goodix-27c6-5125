/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Synthetic test only. Run by the unprivileged builder, never installed.
 * This exercises the unmodified production loader with only two test seams:
 * the caller's UID/GID and the SHA of test_materials.py's generated OEM image.
 * Its production length/RVAs, all format checks and E4 crypto remain enabled.
 *
 * Build with this source and goodix_{runtime_material,target_material,
 * runtime_inputs,action_binding}.c, -Ilibfprint-driver, and pkg-config flags for
 * glib-2.0 openssl. Run via GOODIX_MATERIAL_TEST_NATIVE in test_materials.py.
 */
#include "goodix_runtime_material.h"
#include <stdio.h>
#include <unistd.h>

int
main (int argc, char **argv)
{
  const gchar *const filenames[] = {
    "target-material-manifest.json", "transport-material.bin",
    "target-config-90.bin", "gfusb.dll", "fdt-cache.bin"
  };
  static const guint8 fixture_dll_sha256[32] = {
    0x54, 0xc5, 0xb9, 0x7c, 0x40, 0xc4, 0x51, 0xe2,
    0xcd, 0x22, 0xac, 0xaa, 0xa5, 0xa4, 0x4e, 0x55,
    0x15, 0xa9, 0xc1, 0x4b, 0x16, 0xeb, 0x9e, 0x4a,
    0x7f, 0x94, 0x2a, 0x8a, 0x00, 0xfe, 0xce, 0x44
  };
  GoodixRuntimeMaterialPolicy policy;
  GoodixRuntimeMaterialPaths paths;
  GoodixRuntimeMaterialAudit audit;
  GoodixRuntimeMaterial *material;
  GError *error = NULL;
  gchar *names[5];
  gboolean valid;

  if (argc != 2 || argv[1][0] != '/' || getuid () == 0)
    {
      fputs ("Usage (unprivileged synthetic tests only): test-material-native /fixture-directory\n", stderr);
      return 2;
    }
  for (guint i = 0; i < G_N_ELEMENTS (names); i++)
    names[i] = g_build_filename (argv[1], filenames[i], NULL);
  goodix_runtime_material_policy_production (&policy);
  policy.directory_owner_uid = policy.target.owner_uid = policy.private_files.owner_uid = getuid ();
  policy.directory_owner_gid = policy.target.owner_gid = policy.private_files.owner_gid = getgid ();
  memcpy (policy.pe.expected_sha256, fixture_dll_sha256, sizeof fixture_dll_sha256);
  paths = (GoodixRuntimeMaterialPaths) {
    .directory_path = argv[1], .manifest_path = names[0],
    .transport_path = names[1], .config90_path = names[2],
    .pe_path = names[3], .fdt_cache_path = names[4]
  };
  material = goodix_runtime_material_load (&paths, &policy, &audit, &error);
  valid = material != NULL && audit.directory_verified && audit.target.e4_binding_match;
  if (valid)
    puts ("SYNTHETIC_NATIVE_MATERIAL=PASS E4_BINDING=PASS USB_ACCESSED=false");
  else
    fprintf (stderr, "SYNTHETIC_NATIVE_MATERIAL=FAIL %s\n", error != NULL ? error->message : "binding failed");
  goodix_runtime_material_free (material);
  g_clear_error (&error);
  for (guint i = 0; i < G_N_ELEMENTS (names); i++)
    g_free (names[i]);
  return valid ? 0 : 1;
}
