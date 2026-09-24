/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Offline check of the versioned, non-secret D232 analysis manifest only. */
#include "goodix_target_material.h"

#include <glib/gstdio.h>
#include <string.h>
#include <unistd.h>

static void
check_manifest (const gchar *directory,
                const gchar *bytes,
                gsize        length,
                const gchar *expected_class)
{
  GoodixTargetMaterialPolicy policy;
  GoodixTargetMaterialAudit audit;
  g_autoptr(GError) error = NULL;
  g_autofree gchar *path = g_build_filename (directory, "manifest", NULL);
  g_autofree gchar *missing = g_build_filename (directory, "absent-input", NULL);

  g_assert_true (g_file_set_contents (path, bytes, (gssize) length, &error));
  g_assert_no_error (error);
  g_assert_cmpint (g_chmod (path, 0600), ==, 0);
  goodix_target_material_policy_production (&policy);
  g_assert_cmpuint (policy.manifest_length, ==, 0u);
  /* Only ownership changes for the unprivileged synthetic directory. */
  policy.owner_uid = getuid ();
  policy.owner_gid = getgid ();
  g_assert_null (goodix_target_material_load (
    path, missing, missing, &policy, &audit, &error));
  g_assert_nonnull (error);
  g_assert_cmpstr (goodix_target_material_error_class (error), ==, expected_class);
  g_assert_cmpuint (audit.protected_open_count, ==, 1u);
  g_assert_cmpuint (audit.protected_read_count, ==, 1u);
  g_assert_cmpuint (audit.bind_count, ==, 0u);
  g_assert_cmpint (g_remove (path), ==, 0);
}

int
main (int argc, char **argv)
{
  g_autoptr(GError) error = NULL;
  g_autofree gchar *historical = NULL;
  g_autofree gchar *converted = NULL;
  g_autofree gchar *directory = NULL;
  g_autoptr(GString) canonical = g_string_new (NULL);
  gchar digest[65];
  gsize length = 0;

  if (argc != 3 || geteuid () == 0)
    return 2;
  g_assert_true (g_file_get_contents (argv[1], &historical, &length, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (length, ==, 2305u);
  directory = g_dir_make_tmp ("goodix-manifest-boundary.XXXXXX", &error);
  g_assert_no_error (error);
  g_assert_nonnull (directory);

  check_manifest (directory, historical, length, "PROTECTED_CONTENT");
  g_print ("VERSIONED_D232_MANIFEST_REJECTED_BEFORE_TRANSPORT=PASS\n");

  memset (digest, '0', sizeof digest - 1u);
  digest[64] = '\0';
  g_string_printf (canonical,
    "{\"schema\":\"goodix-5125-device-materials-v1\","
    "\"vid\":\"27c6\",\"pid\":\"5125\",\"app\":\"GF_ST411SEC_APP_12509\","
    "\"transport_sha256\":\"%s\",\"config90_sha256\":\"%s\","
    "\"fdt_cache_sha256\":\"%s\",\"a2_response_sha256\":\"%s\","
    "\"chip82_response_sha256\":\"%s\",\"otp_a6_response_sha256\":\"%s\"}",
    digest, digest, digest, digest, digest, digest);
  g_assert_cmpuint (canonical->len, <, length);
  while (canonical->len < length)
    g_string_append_c (canonical, ' ');
  /* Identical file length and permissions; parsing succeeds, absent transport
   * then fails open. This is not a valid bundle or evidence about the host. */
  check_manifest (directory, canonical->str, canonical->len, "PROTECTED_OPEN");
  g_print ("SAME_SIZE_SYNTHETIC_V1_REACHES_ABSENT_TRANSPORT=PASS\n");
  g_assert_true (g_file_get_contents (argv[2], &converted, &length, &error));
  g_assert_no_error (error);
  check_manifest (directory, converted, length, "PROTECTED_OPEN");
  g_print ("CONVERTED_HISTORICAL_MANIFEST_ACCEPTED_BY_PRODUCTION_PARSER=PASS\n");
  g_assert_cmpint (g_rmdir (directory), ==, 0);
  return 0;
}
