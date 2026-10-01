/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Deterministic host-only tests for crash-safe APP12509 state-v2. */
#include "goodix_self_state.h"

#include <errno.h>
#include <fcntl.h>
#include <glib/gstdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

typedef struct
{
  GoodixSelfStateFaultPoint point;
  guint calls;
} Fault;

static void
fill_bytes (guint8 *output,
            gsize   length,
            guint8  start)
{
  for (gsize i = 0; i < length; i++)
    output[i] = (guint8) (start + (guint8) i);
}

static GoodixSelfStateBinding
binding_fixture (void)
{
  GoodixSelfStateBinding binding = { 0 };

  binding.vid = 0x27c6u;
  binding.pid = 0x5125u;
  binding.chip_profile = 0x1259u;
  g_strlcpy (binding.app, "APP12509", sizeof binding.app);
  fill_bytes (binding.otp_sha256, sizeof binding.otp_sha256, 0x10u);
  fill_bytes (binding.config90_sha256, sizeof binding.config90_sha256, 0x60u);
  return binding;
}

static GoodixSelfStateRecord
record_fixture (GoodixSelfStatePhase phase,
                guint64              generation,
                guint8               validator_start)
{
  GoodixSelfStateRecord record = { 0 };

  record.phase = phase;
  record.generation = generation;
  fill_bytes (record.expected_validator, sizeof record.expected_validator,
              validator_start);
  return record;
}

static gchar *
state_directory_new (void)
{
  gchar *directory = g_strdup ("/tmp/goodix-state-v2-test.XXXXXX");

  g_assert_nonnull (g_mkdtemp (directory));
  g_assert_cmpint (g_chmod (directory, 0700), ==, 0);
  return directory;
}

static void
state_directory_free (gchar *directory)
{
  GDir *dir;
  const gchar *name;

  dir = g_dir_open (directory, 0, NULL);
  if (dir != NULL)
    {
      while ((name = g_dir_read_name (dir)) != NULL)
        {
          gchar *path = g_build_filename (directory, name, NULL);

          g_assert_cmpint (g_unlink (path), ==, 0);
          g_free (path);
        }
      g_dir_close (dir);
    }
  g_assert_cmpint (g_rmdir (directory), ==, 0);
  g_free (directory);
}

static GoodixSelfStatePolicy
test_policy (void)
{
  GoodixSelfStatePolicy policy;

  goodix_self_state_policy_for_owner (&policy, getuid (), getgid ());
  return policy;
}

static gboolean
inject_fault (GoodixSelfStateFaultPoint point,
              gpointer                  user_data)
{
  Fault *fault = user_data;

  fault->calls++;
  return point == fault->point;
}

static void
assert_file_policy (const gchar *directory,
                    const gchar *name,
                    goffset      size)
{
  gchar *path = g_build_filename (directory, name, NULL);
  struct stat status;

  g_assert_cmpint (g_lstat (path, &status), ==, 0);
  g_assert_true (S_ISREG (status.st_mode));
  g_assert_cmpuint (status.st_nlink, ==, 1u);
  g_assert_cmpuint (status.st_uid, ==, getuid ());
  g_assert_cmpuint (status.st_gid, ==, getgid ());
  g_assert_cmpuint (status.st_mode & 0777u, ==, 0600u);
  g_assert_cmpint (status.st_size, ==, size);
  g_free (path);
}

static GoodixSelfState *
load_valid (const gchar                  *directory,
            const GoodixSelfStateBinding *binding,
            const GoodixSelfStatePolicy  *policy)
{
  GoodixSelfState *state = NULL;
  GError *error = NULL;

  g_assert_cmpint (goodix_self_state_load (directory, binding, policy,
                                            &state, &error),
                   ==, GOODIX_SELF_STATE_LOAD_VALID);
  g_assert_no_error (error);
  g_assert_nonnull (state);
  return state;
}

static void
test_roundtrip_and_promotion (void)
{
  GoodixSelfStateBinding binding = binding_fixture ();
  GoodixSelfStateRecord record = record_fixture (GOODIX_SELF_STATE_PREPARED,
                                                  1u, 0x20u);
  GoodixSelfStatePolicy policy = test_policy ();
  GoodixSelfState *prepared;
  GoodixSelfState *active;
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];
  guint8 copied[GOODIX_SELF_STATE_PSK_LENGTH];
  gchar *directory = state_directory_new ();

  fill_bytes (psk, sizeof psk, 0xa0u);
  record.prior_validator_present = TRUE;
  fill_bytes (record.prior_validator, sizeof record.prior_validator, 0x80u);
  record.fdt_present = TRUE;
  fill_bytes (record.fdt_table, sizeof record.fdt_table, 0x40u);
  record.e0_attempted = TRUE;
  record.bb010002_sha256_present = TRUE;
  fill_bytes (record.bb010002_sha256,
              sizeof record.bb010002_sha256, 0x61u);
  g_assert_true (goodix_self_state_write_prepared (directory, &binding, &record,
                                                    psk, &policy, NULL));
  assert_file_policy (directory, "secret-a.bin", 48);
  assert_file_policy (directory, "receipt-a.bin", 264);
  prepared = load_valid (directory, &binding, &policy);
  g_assert_cmpint (goodix_self_state_get_record (prepared)->phase, ==,
                   GOODIX_SELF_STATE_PREPARED);
  g_assert_true (goodix_self_state_get_record (prepared)->e0_attempted);
  g_assert_true (
    goodix_self_state_get_record (prepared)->bb010002_sha256_present);
  g_assert_cmpmem (goodix_self_state_get_record (prepared)->bb010002_sha256,
                   sizeof record.bb010002_sha256,
                   record.bb010002_sha256,
                   sizeof record.bb010002_sha256);
  g_assert_true (goodix_self_state_copy_psk (prepared, copied));
  g_assert_cmpmem (copied, sizeof copied, psk, sizeof psk);
  g_assert_cmpint (goodix_self_state_reconcile (prepared,
                                                record.expected_validator,
                                                FALSE), ==,
                   GOODIX_SELF_STATE_RECONCILE_RETRY_TLS);
  g_assert_cmpint (goodix_self_state_reconcile (prepared,
                                                record.expected_validator,
                                                TRUE), ==,
                   GOODIX_SELF_STATE_RECONCILE_PROMOTE_ACTIVE);
  g_assert_cmpint (goodix_self_state_reconcile (prepared,
                                                record.prior_validator,
                                                FALSE), ==,
                   GOODIX_SELF_STATE_RECONCILE_USE_PRIOR);
  g_assert_true (goodix_self_state_promote_active (directory, prepared, &policy,
                                                   NULL));
  goodix_self_state_free (prepared);
  assert_file_policy (directory, "secret-b.bin", 48);
  assert_file_policy (directory, "receipt-b.bin", 264);
  active = load_valid (directory, &binding, &policy);
  g_assert_cmpuint (goodix_self_state_get_record (active)->generation, ==, 2u);
  g_assert_true (goodix_self_state_get_record (active)->terminal_proof);
  g_assert_cmpint (goodix_self_state_reconcile (active,
                                                record.expected_validator,
                                                FALSE), ==,
                   GOODIX_SELF_STATE_RECONCILE_ACTIVE_MATCH);
  g_assert_cmpint (goodix_self_state_reconcile (active,
                                                record.prior_validator,
                                                TRUE), ==,
                   GOODIX_SELF_STATE_RECONCILE_EXTERNAL_REPLACEMENT);
  goodix_self_state_free (active);
  state_directory_free (directory);
}

static void
test_fault_boundaries_keep_one_read_only_choice (void)
{
  GoodixSelfStateBinding binding = binding_fixture ();
  GoodixSelfStatePolicy base_policy = test_policy ();
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];

  fill_bytes (psk, sizeof psk, 0xb0u);
  for (guint point = GOODIX_SELF_STATE_FAULT_SECRET_TEMP_WRITTEN;
       point <= GOODIX_SELF_STATE_FAULT_RECEIPT_DIRECTORY_SYNCED; point++)
    {
      GoodixSelfStateRecord old_record =
        record_fixture (GOODIX_SELF_STATE_PREPARED, 1u, 0x11u);
      GoodixSelfStateRecord new_record =
        record_fixture (GOODIX_SELF_STATE_PREPARED, 3u, 0x33u);
      GoodixSelfStatePolicy fault_policy = base_policy;
      GoodixSelfState *old_prepared;
      GoodixSelfState *loaded;
      GError *error = NULL;
      Fault fault = { (GoodixSelfStateFaultPoint) point, 0u };
      gchar *directory = state_directory_new ();

      g_assert_true (goodix_self_state_write_prepared (directory, &binding,
                                                        &old_record, psk,
                                                        &base_policy, NULL));
      old_prepared = load_valid (directory, &binding, &base_policy);
      g_assert_true (goodix_self_state_promote_active (directory, old_prepared,
                                                       &base_policy, NULL));
      goodix_self_state_free (old_prepared);
      new_record.prior_validator_present = TRUE;
      memcpy (new_record.prior_validator, old_record.expected_validator,
              sizeof new_record.prior_validator);
      new_record.e0_attempted = TRUE;
      fault_policy.fault = inject_fault;
      fault_policy.fault_data = &fault;
      g_assert_false (goodix_self_state_write_prepared (directory, &binding,
                                                         &new_record, psk,
                                                         &fault_policy, &error));
      g_assert_error (error, g_quark_from_static_string ("goodix-self-state-error"),
                      EINTR);
      g_clear_error (&error);
      g_assert_cmpuint (fault.calls, >, 0u);
      loaded = load_valid (directory, &binding, &base_policy);
      if (point < GOODIX_SELF_STATE_FAULT_RECEIPT_RENAMED)
        {
          g_assert_cmpuint (goodix_self_state_get_record (loaded)->generation,
                            ==, 2u);
          g_assert_cmpint (goodix_self_state_reconcile (
                             loaded, old_record.expected_validator, FALSE), ==,
                           GOODIX_SELF_STATE_RECONCILE_ACTIVE_MATCH);
        }
      else
        {
          g_assert_cmpuint (goodix_self_state_get_record (loaded)->generation,
                            ==, 3u);
          g_assert_true (goodix_self_state_get_record (loaded)->e0_attempted);
          g_assert_cmpint (goodix_self_state_reconcile (
                             loaded, old_record.expected_validator, FALSE), ==,
                           GOODIX_SELF_STATE_RECONCILE_USE_PRIOR);
          g_assert_cmpint (goodix_self_state_reconcile (
                             loaded, new_record.expected_validator, FALSE), ==,
                           GOODIX_SELF_STATE_RECONCILE_RETRY_TLS);
        }
      goodix_self_state_free (loaded);
      state_directory_free (directory);
    }
}

static void
test_initial_faults_are_unambiguous (void)
{
  GoodixSelfStateBinding binding = binding_fixture ();
  GoodixSelfStateRecord record = record_fixture (GOODIX_SELF_STATE_PREPARED,
                                                  1u, 0x22u);
  GoodixSelfStatePolicy base_policy = test_policy ();
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];

  fill_bytes (psk, sizeof psk, 0xc0u);
  for (guint point = GOODIX_SELF_STATE_FAULT_SECRET_TEMP_WRITTEN;
       point <= GOODIX_SELF_STATE_FAULT_RECEIPT_DIRECTORY_SYNCED; point++)
    {
      GoodixSelfStatePolicy fault_policy = base_policy;
      GoodixSelfState *state = NULL;
      Fault fault = { (GoodixSelfStateFaultPoint) point, 0u };
      GError *error = NULL;
      gchar *directory = state_directory_new ();
      GoodixSelfStateLoadResult result;

      fault_policy.fault = inject_fault;
      fault_policy.fault_data = &fault;
      g_assert_false (goodix_self_state_write_prepared (directory, &binding,
                                                         &record, psk,
                                                         &fault_policy, &error));
      g_clear_error (&error);
      result = goodix_self_state_load (directory, &binding, &base_policy,
                                       &state, &error);
      g_assert_no_error (error);
      if (point < GOODIX_SELF_STATE_FAULT_RECEIPT_RENAMED)
        {
          g_assert_cmpint (result, ==, GOODIX_SELF_STATE_LOAD_INCOMPLETE);
          g_assert_null (state);
        }
      else
        {
          g_assert_cmpint (result, ==, GOODIX_SELF_STATE_LOAD_VALID);
          g_assert_nonnull (state);
          g_assert_cmpint (goodix_self_state_reconcile (
                             state, record.expected_validator, FALSE), ==,
                           GOODIX_SELF_STATE_RECONCILE_RETRY_TLS);
        }
      goodix_self_state_free (state);
      state_directory_free (directory);
    }
}

static void
test_initial_partial_is_preserved_in_other_slot (void)
{
  GoodixSelfStateBinding binding = binding_fixture ();
  GoodixSelfStateRecord first = record_fixture (GOODIX_SELF_STATE_PREPARED,
                                                 1u, 0x23u);
  GoodixSelfStateRecord second = record_fixture (GOODIX_SELF_STATE_PREPARED,
                                                  2u, 0x24u);
  GoodixSelfStatePolicy policy = test_policy ();
  GoodixSelfStatePolicy fault_policy = policy;
  GoodixSelfState *state;
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];
  Fault fault = { GOODIX_SELF_STATE_FAULT_SECRET_RENAMED, 0u };
  gchar *directory = state_directory_new ();
  gchar *partial = g_build_filename (directory, "secret-a.bin", NULL);
  gchar *preserved = NULL;
  gsize preserved_length = 0;

  fill_bytes (psk, sizeof psk, 0xc4u);
  fault_policy.fault = inject_fault;
  fault_policy.fault_data = &fault;
  g_assert_false (goodix_self_state_write_prepared (directory, &binding, &first,
                                                     psk, &fault_policy, NULL));
  g_assert_true (g_file_get_contents (partial, &preserved, &preserved_length,
                                      NULL));
  g_assert_true (goodix_self_state_write_prepared (directory, &binding, &second,
                                                    psk, &policy, NULL));
  state = load_valid (directory, &binding, &policy);
  g_assert_cmpuint (goodix_self_state_get_record (state)->generation, ==, 2u);
  goodix_self_state_free (state);
  {
    gchar *after = NULL;
    gsize after_length = 0;

    g_assert_true (g_file_get_contents (partial, &after, &after_length, NULL));
    g_assert_cmpuint (after_length, ==, preserved_length);
    g_assert_cmpmem (after, after_length, preserved, preserved_length);
    g_free (after);
  }
  g_free (preserved);
  g_free (partial);
  state_directory_free (directory);
}

static void
test_binding_uses_all_target_identity (void)
{
  GoodixSelfStateBinding binding = binding_fixture ();
  GoodixSelfStateRecord record = record_fixture (GOODIX_SELF_STATE_PREPARED,
                                                  1u, 0x44u);
  GoodixSelfStatePolicy policy = test_policy ();
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];
  gchar *directory = state_directory_new ();

  fill_bytes (psk, sizeof psk, 0xd0u);
  g_assert_true (goodix_self_state_write_prepared (directory, &binding, &record,
                                                    psk, &policy, NULL));
  for (guint variant = 0; variant < 6u; variant++)
    {
      GoodixSelfStateBinding changed = binding;
      GoodixSelfState *state = NULL;

      switch (variant)
        {
        case 0: changed.vid ^= 1u; break;
        case 1: changed.pid ^= 1u; break;
        case 2: changed.chip_profile ^= 1u; break;
        case 3: changed.app[3] = 'X'; break;
        case 4: changed.otp_sha256[7] ^= 1u; break;
        case 5: changed.config90_sha256[9] ^= 1u; break;
        default: g_assert_not_reached ();
        }
      g_assert_cmpint (goodix_self_state_load (directory, &changed, &policy,
                                               &state, NULL), ==,
                       GOODIX_SELF_STATE_LOAD_BINDING_MISMATCH);
      g_assert_null (state);
    }
  state_directory_free (directory);
}

static void
test_policy_bounds_and_nofollow (void)
{
  GoodixSelfStateBinding binding = binding_fixture ();
  GoodixSelfStatePolicy policy = test_policy ();
  GoodixSelfState *state = NULL;
  gchar *directory = state_directory_new ();
  gchar *secret = g_build_filename (directory, "secret-a.bin", NULL);
  gchar *target = g_build_filename (directory, "outside", NULL);
  GError *error = NULL;

  g_assert_true (g_file_set_contents (target, "not state", -1, &error));
  g_assert_no_error (error);
  g_assert_cmpint (symlink (target, secret), ==, 0);
  g_assert_cmpint (goodix_self_state_load (directory, &binding, &policy, &state,
                                           &error), ==,
                   GOODIX_SELF_STATE_LOAD_INCOMPLETE);
  g_assert_no_error (error);
  g_assert_null (state);
  g_assert_cmpint (g_unlink (secret), ==, 0);
  g_assert_cmpint (g_unlink (target), ==, 0);
  g_assert_cmpint (g_chmod (directory, 0755), ==, 0);
  g_assert_cmpint (goodix_self_state_load (directory, &binding, &policy, &state,
                                           &error), ==,
                   GOODIX_SELF_STATE_LOAD_INCOMPLETE);
  g_assert_error (error, g_quark_from_static_string ("goodix-self-state-error"),
                  EPERM);
  g_clear_error (&error);
  g_assert_cmpint (g_chmod (directory, 0700), ==, 0);
  g_free (secret);
  g_free (target);
  state_directory_free (directory);
}

static void
test_authenticated_corruption_falls_back (void)
{
  GoodixSelfStateBinding binding = binding_fixture ();
  GoodixSelfStateRecord record = record_fixture (GOODIX_SELF_STATE_PREPARED,
                                                  1u, 0x27u);
  GoodixSelfStatePolicy policy = test_policy ();
  GoodixSelfState *state;
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];
  gchar *directory = state_directory_new ();
  gchar *receipt = g_build_filename (directory, "receipt-b.bin", NULL);
  int fd;
  guint8 byte;

  fill_bytes (psk, sizeof psk, 0x91u);
  g_assert_true (goodix_self_state_write_prepared (directory, &binding, &record,
                                                    psk, &policy, NULL));
  state = load_valid (directory, &binding, &policy);
  g_assert_true (goodix_self_state_promote_active (directory, state, &policy,
                                                   NULL));
  goodix_self_state_free (state);
  fd = g_open (receipt, O_RDWR | O_CLOEXEC, 0);
  g_assert_cmpint (fd, >=, 0);
  g_assert_cmpint (lseek (fd, 124, SEEK_SET), ==, 124);
  g_assert_cmpint (read (fd, &byte, 1u), ==, 1);
  byte ^= 1u;
  g_assert_cmpint (lseek (fd, 124, SEEK_SET), ==, 124);
  g_assert_cmpint (write (fd, &byte, 1u), ==, 1);
  g_assert_cmpint (close (fd), ==, 0);
  state = load_valid (directory, &binding, &policy);
  g_assert_cmpuint (goodix_self_state_get_record (state)->generation, ==, 1u);
  g_assert_cmpint (goodix_self_state_get_record (state)->phase, ==,
                   GOODIX_SELF_STATE_PREPARED);
  goodix_self_state_free (state);
  g_free (receipt);
  state_directory_free (directory);
}

static void
test_legacy_import_preserves_source (void)
{
  static const guint8 legacy_bundle[] = {
    0x47, 0x44, 0x58, 0x2d, 0x4c, 0x45, 0x47, 0x41, 0x43, 0x59,
    0x00, 0xff, 0x33, 0x71, 0x19, 0xa5
  };
  GoodixSelfStateBinding binding = binding_fixture ();
  GoodixSelfStatePolicy policy = test_policy ();
  GoodixSelfState *state;
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];
  guint8 validator[GOODIX_SELF_STATE_DIGEST_LENGTH];
  guint8 digest[GOODIX_SELF_STATE_DIGEST_LENGTH];
  guint8 fdt[GOODIX_SELF_STATE_FDT_LENGTH];
  gchar *directory = state_directory_new ();
  gchar *legacy_path = g_build_filename (directory, "legacy-bundle.bin", NULL);
  gchar *after = NULL;
  gsize after_length = 0;
  GChecksum *checksum = g_checksum_new (G_CHECKSUM_SHA256);
  gsize digest_length = sizeof digest;

  fill_bytes (psk, sizeof psk, 0xe0u);
  fill_bytes (validator, sizeof validator, 0x51u);
  fill_bytes (fdt, sizeof fdt, 0x31u);
  g_checksum_update (checksum, legacy_bundle, sizeof legacy_bundle);
  g_checksum_get_digest (checksum, digest, &digest_length);
  g_checksum_free (checksum);
  g_assert_true (g_file_set_contents (legacy_path, (const gchar *) legacy_bundle,
                                      sizeof legacy_bundle, NULL));
  g_assert_true (goodix_self_state_import_legacy (directory, &binding, psk,
                                                   validator, digest, fdt,
                                                   &policy, NULL));
  state = load_valid (directory, &binding, &policy);
  g_assert_true (goodix_self_state_get_record (state)->migrated_legacy);
  g_assert_false (goodix_self_state_get_record (state)->e0_attempted);
  g_assert_true (goodix_self_state_get_record (state)->fdt_present);
  g_assert_cmpmem (goodix_self_state_get_record (state)->legacy_source_sha256,
                   sizeof digest, digest, sizeof digest);
  g_assert_cmpint (goodix_self_state_reconcile (state, validator, TRUE), ==,
                   GOODIX_SELF_STATE_RECONCILE_PROMOTE_ACTIVE);
  g_assert_true (g_file_get_contents (legacy_path, &after, &after_length, NULL));
  g_assert_cmpuint (after_length, ==, sizeof legacy_bundle);
  g_assert_cmpmem (after, after_length, legacy_bundle, sizeof legacy_bundle);
  goodix_self_state_free (state);
  g_free (after);
  g_assert_cmpint (g_unlink (legacy_path), ==, 0);
  g_free (legacy_path);
  state_directory_free (directory);
}

static void
test_error_does_not_disclose_secret (void)
{
  GoodixSelfStateBinding binding = binding_fixture ();
  GoodixSelfStateRecord record = record_fixture (GOODIX_SELF_STATE_PREPARED,
                                                  1u, 0x55u);
  GoodixSelfStatePolicy policy = test_policy ();
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];
  GError *error = NULL;

  memset (psk, 0xaau, sizeof psk);
  g_assert_false (goodix_self_state_write_prepared ("/does/not/exist", &binding,
                                                     &record, psk, &policy,
                                                     &error));
  g_assert_nonnull (error);
  g_assert_null (strstr (error->message, "aa"));
  g_assert_null (strstr (error->message, "55"));
  g_clear_error (&error);
}

int
main (int argc,
      char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/goodix/state-v2/roundtrip-promotion",
                   test_roundtrip_and_promotion);
  g_test_add_func ("/goodix/state-v2/fault-boundaries",
                   test_fault_boundaries_keep_one_read_only_choice);
  g_test_add_func ("/goodix/state-v2/initial-faults",
                   test_initial_faults_are_unambiguous);
  g_test_add_func ("/goodix/state-v2/initial-partial-preserved",
                   test_initial_partial_is_preserved_in_other_slot);
  g_test_add_func ("/goodix/state-v2/full-binding",
                   test_binding_uses_all_target_identity);
  g_test_add_func ("/goodix/state-v2/policy-nofollow",
                   test_policy_bounds_and_nofollow);
  g_test_add_func ("/goodix/state-v2/authenticated-fallback",
                   test_authenticated_corruption_falls_back);
  g_test_add_func ("/goodix/state-v2/legacy-preserved",
                   test_legacy_import_preserves_source);
  g_test_add_func ("/goodix/state-v2/no-secret-errors",
                   test_error_does_not_disclose_secret);
  return g_test_run ();
}
