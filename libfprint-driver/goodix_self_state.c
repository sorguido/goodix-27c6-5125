/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (c) 2026 sorguido
 *
 * Crash-safe, host-only APP12509 pairing state.  This module deliberately
 * performs no device I/O and never decides to issue a pairing write.
 */
#include "goodix_self_state.h"

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include <openssl/core_names.h>
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/params.h>

#define SECRET_SIZE 48u
#define RECEIPT_PREFIX_SIZE 232u
#define RECEIPT_SIZE 264u

#define RECEIPT_FLAG_PRIOR (1u << 0)
#define RECEIPT_FLAG_FDT (1u << 1)
#define RECEIPT_FLAG_MIGRATED (1u << 2)
#define RECEIPT_FLAG_E0_ATTEMPTED (1u << 3)
#define RECEIPT_FLAG_TERMINAL_PROOF (1u << 4)
#define RECEIPT_FLAG_BB010002_SHA256 (1u << 5)
#define RECEIPT_FLAGS_ALL ((1u << 6) - 1u)

static const guint8 secret_magic[8] = { 'G', 'D', 'X', 'P', 'S', 'K', '2', 0 };
static const guint8 receipt_magic[8] = { 'G', 'D', 'X', 'S', 'T', 'A', '2', 0 };

typedef struct
{
  gboolean final_artifact;
  gboolean temp_artifact;
  gboolean valid;
  GoodixSelfStateBinding binding;
  GoodixSelfStateRecord record;
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];
} Slot;

struct _GoodixSelfState
{
  GoodixSelfStateBinding binding;
  GoodixSelfStateRecord record;
  guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH];
};

static GQuark
self_state_error_quark (void)
{
  return g_quark_from_static_string ("goodix-self-state-error");
}

static void
set_io_error (GError     **error,
              const gchar *operation)
{
  g_set_error (error, self_state_error_quark (), errno,
               "state-v2 %s failed", operation);
}

static void
put_u16_le (guint8 *output,
            guint16 value)
{
  output[0] = (guint8) (value & 0xffu);
  output[1] = (guint8) (value >> 8);
}

static guint16
get_u16_le (const guint8 *input)
{
  return (guint16) ((guint16) input[0] | ((guint16) input[1] << 8));
}

static void
put_u64_le (guint8 *output,
            guint64 value)
{
  for (guint i = 0; i < 8u; i++)
    output[i] = (guint8) (value >> (i * 8u));
}

static guint64
get_u64_le (const guint8 *input)
{
  guint64 value = 0;

  for (guint i = 0; i < 8u; i++)
    value |= ((guint64) input[i]) << (i * 8u);
  return value;
}

static gboolean
hmac_sha256 (const guint8 key[GOODIX_SELF_STATE_PSK_LENGTH],
             const guint8 *input,
             gsize input_length,
             guint8 output[GOODIX_SELF_STATE_DIGEST_LENGTH])
{
  EVP_MAC *mac = NULL;
  EVP_MAC_CTX *context = NULL;
  OSSL_PARAM params[2];
  gchar digest_name[] = "SHA256";
  size_t output_length = 0;
  gboolean ok = FALSE;

  mac = EVP_MAC_fetch (NULL, "HMAC", NULL);
  if (mac == NULL)
    goto out;
  context = EVP_MAC_CTX_new (mac);
  if (context == NULL)
    goto out;
  params[0] = OSSL_PARAM_construct_utf8_string (OSSL_MAC_PARAM_DIGEST,
                                                 digest_name, 0);
  params[1] = OSSL_PARAM_construct_end ();
  if (EVP_MAC_init (context, key, GOODIX_SELF_STATE_PSK_LENGTH, params) != 1 ||
      EVP_MAC_update (context, input, input_length) != 1 ||
      EVP_MAC_final (context, output, &output_length,
                     GOODIX_SELF_STATE_DIGEST_LENGTH) != 1 ||
      output_length != GOODIX_SELF_STATE_DIGEST_LENGTH)
    goto out;
  ok = TRUE;
out:
  EVP_MAC_CTX_free (context);
  EVP_MAC_free (mac);
  return ok;
}

static gboolean
binding_valid (const GoodixSelfStateBinding *binding)
{
  return binding != NULL &&
         strnlen (binding->app, GOODIX_SELF_STATE_APP_MAX) > 0u &&
         strnlen (binding->app, GOODIX_SELF_STATE_APP_MAX) <
           GOODIX_SELF_STATE_APP_MAX;
}

static gboolean
policy_valid (const GoodixSelfStatePolicy *policy)
{
  if (policy == NULL || policy->directory_mode != 0700u ||
      policy->file_mode != 0600u)
    return FALSE;
#ifndef GOODIX_ENABLE_TEST_SEAMS
  if (policy->owner_uid != 0u || policy->owner_gid != 0u ||
      policy->fault != NULL || policy->fault_data != NULL)
    return FALSE;
#endif
  return TRUE;
}

static gboolean
binding_equal (const GoodixSelfStateBinding *left,
               const GoodixSelfStateBinding *right)
{
  return left->vid == right->vid && left->pid == right->pid &&
         left->chip_profile == right->chip_profile &&
         strcmp (left->app, right->app) == 0 &&
         CRYPTO_memcmp (left->otp_sha256, right->otp_sha256,
                        GOODIX_SELF_STATE_DIGEST_LENGTH) == 0 &&
         CRYPTO_memcmp (left->config90_sha256, right->config90_sha256,
                        GOODIX_SELF_STATE_DIGEST_LENGTH) == 0;
}

static gboolean
record_valid (const GoodixSelfStateRecord *record)
{
  return record != NULL && record->generation != 0u &&
         (record->phase == GOODIX_SELF_STATE_PREPARED ||
          record->phase == GOODIX_SELF_STATE_ACTIVE ||
          record->phase == GOODIX_SELF_STATE_RECOVERY_REQUIRED) &&
         !(record->migrated_legacy && record->bb010002_sha256_present) &&
         (record->terminal_proof ==
          (record->phase == GOODIX_SELF_STATE_ACTIVE));
}

static gboolean
open_directory (const gchar                 *directory,
                const GoodixSelfStatePolicy *policy,
                int                         *directory_fd,
                gboolean                     absent_ok,
                GError                     **error)
{
  struct stat status;
  int fd;

  fd = open (directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
  if (fd < 0)
    {
      if (absent_ok && errno == ENOENT)
        return TRUE;
      set_io_error (error, "directory open");
      return FALSE;
    }
  if (fstat (fd, &status) != 0)
    {
      set_io_error (error, "directory stat");
      close (fd);
      return FALSE;
    }
  if (!S_ISDIR (status.st_mode) || status.st_uid != policy->owner_uid ||
      status.st_gid != policy->owner_gid ||
      (status.st_mode & 07777u) != policy->directory_mode)
    {
      g_set_error_literal (error, self_state_error_quark (), EPERM,
                           "state-v2 directory policy mismatch");
      close (fd);
      return FALSE;
    }
  *directory_fd = fd;
  return TRUE;
}

static gboolean
artifact_exists (int          directory_fd,
                 const gchar *name)
{
  struct stat status;

  return fstatat (directory_fd, name, &status, AT_SYMLINK_NOFOLLOW) == 0;
}

static gboolean
read_exact_file (int                          directory_fd,
                 const gchar                 *name,
                 guint8                      *output,
                 gsize                        output_length,
                 const GoodixSelfStatePolicy *policy)
{
  struct stat status;
  gsize offset = 0;
  int fd;

  fd = openat (directory_fd, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (fd < 0)
    return FALSE;
  if (fstat (fd, &status) != 0 || !S_ISREG (status.st_mode) ||
      status.st_nlink != 1 || status.st_uid != policy->owner_uid ||
      status.st_gid != policy->owner_gid ||
      (status.st_mode & 07777u) != policy->file_mode ||
      status.st_size < 0 || (guint64) status.st_size != output_length)
    {
      close (fd);
      return FALSE;
    }
  while (offset < output_length)
    {
      ssize_t count = read (fd, output + offset, output_length - offset);

      if (count < 0 && errno == EINTR)
        continue;
      if (count <= 0)
        {
          close (fd);
          return FALSE;
        }
      offset += (gsize) count;
    }
  {
    guint8 extra;
    ssize_t count;

    do
      count = read (fd, &extra, 1u);
    while (count < 0 && errno == EINTR);
    if (count != 0)
      {
        close (fd);
        return FALSE;
      }
  }
  return close (fd) == 0;
}

static gboolean
decode_receipt (const guint8 receipt[RECEIPT_SIZE],
                const guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH],
                GoodixSelfStateBinding *binding,
                GoodixSelfStateRecord *record)
{
  guint8 expected_hmac[GOODIX_SELF_STATE_DIGEST_LENGTH] = { 0 };
  guint8 flags;
  guint8 app_length;

  if (memcmp (receipt, receipt_magic, sizeof receipt_magic) != 0 ||
      receipt[8] != 2u || receipt[11] != 0u || receipt[27] != 0u)
    return FALSE;
  flags = receipt[10];
  app_length = receipt[26];
  if ((flags & ~RECEIPT_FLAGS_ALL) != 0u || app_length == 0u ||
      app_length >= GOODIX_SELF_STATE_APP_MAX)
    return FALSE;
  if (!hmac_sha256 (psk, receipt, RECEIPT_PREFIX_SIZE, expected_hmac))
    {
      OPENSSL_cleanse (expected_hmac, sizeof expected_hmac);
      return FALSE;
    }
  if (CRYPTO_memcmp (expected_hmac, receipt + RECEIPT_PREFIX_SIZE,
                     sizeof expected_hmac) != 0)
    {
      OPENSSL_cleanse (expected_hmac, sizeof expected_hmac);
      return FALSE;
    }
  OPENSSL_cleanse (expected_hmac, sizeof expected_hmac);

  memset (binding, 0, sizeof *binding);
  memset (record, 0, sizeof *record);
  binding->vid = get_u16_le (receipt + 20);
  binding->pid = get_u16_le (receipt + 22);
  binding->chip_profile = get_u16_le (receipt + 24);
  memcpy (binding->app, receipt + 28, app_length);
  if (receipt[28 + app_length] != 0u)
    return FALSE;
  memcpy (binding->otp_sha256, receipt + 60, GOODIX_SELF_STATE_DIGEST_LENGTH);
  memcpy (binding->config90_sha256, receipt + 92,
          GOODIX_SELF_STATE_DIGEST_LENGTH);
  record->phase = (GoodixSelfStatePhase) receipt[9];
  record->generation = get_u64_le (receipt + 12);
  memcpy (record->expected_validator, receipt + 124,
          GOODIX_SELF_STATE_DIGEST_LENGTH);
  record->prior_validator_present = (flags & RECEIPT_FLAG_PRIOR) != 0u;
  memcpy (record->prior_validator, receipt + 156,
          GOODIX_SELF_STATE_DIGEST_LENGTH);
  record->fdt_present = (flags & RECEIPT_FLAG_FDT) != 0u;
  memcpy (record->fdt_table, receipt + 188, GOODIX_SELF_STATE_FDT_LENGTH);
  record->migrated_legacy = (flags & RECEIPT_FLAG_MIGRATED) != 0u;
  record->bb010002_sha256_present =
    (flags & RECEIPT_FLAG_BB010002_SHA256) != 0u;
  if (record->bb010002_sha256_present)
    memcpy (record->bb010002_sha256, receipt + 200,
            GOODIX_SELF_STATE_DIGEST_LENGTH);
  else
    memcpy (record->legacy_source_sha256, receipt + 200,
            GOODIX_SELF_STATE_DIGEST_LENGTH);
  record->e0_attempted = (flags & RECEIPT_FLAG_E0_ATTEMPTED) != 0u;
  record->terminal_proof = (flags & RECEIPT_FLAG_TERMINAL_PROOF) != 0u;
  return binding_valid (binding) && record_valid (record);
}

static gboolean
encode_receipt (const GoodixSelfStateBinding *binding,
                const GoodixSelfStateRecord *record,
                const guint8 psk[GOODIX_SELF_STATE_PSK_LENGTH],
                guint8 receipt[RECEIPT_SIZE])
{
  gsize app_length = strlen (binding->app);
  guint8 flags = 0;

  memset (receipt, 0, RECEIPT_SIZE);
  memcpy (receipt, receipt_magic, sizeof receipt_magic);
  receipt[8] = 2u;
  receipt[9] = (guint8) record->phase;
  if (record->prior_validator_present)
    flags |= RECEIPT_FLAG_PRIOR;
  if (record->fdt_present)
    flags |= RECEIPT_FLAG_FDT;
  if (record->migrated_legacy)
    flags |= RECEIPT_FLAG_MIGRATED;
  if (record->e0_attempted)
    flags |= RECEIPT_FLAG_E0_ATTEMPTED;
  if (record->terminal_proof)
    flags |= RECEIPT_FLAG_TERMINAL_PROOF;
  if (record->bb010002_sha256_present)
    flags |= RECEIPT_FLAG_BB010002_SHA256;
  receipt[10] = flags;
  put_u64_le (receipt + 12, record->generation);
  put_u16_le (receipt + 20, binding->vid);
  put_u16_le (receipt + 22, binding->pid);
  put_u16_le (receipt + 24, binding->chip_profile);
  receipt[26] = (guint8) app_length;
  memcpy (receipt + 28, binding->app, app_length);
  memcpy (receipt + 60, binding->otp_sha256, GOODIX_SELF_STATE_DIGEST_LENGTH);
  memcpy (receipt + 92, binding->config90_sha256,
          GOODIX_SELF_STATE_DIGEST_LENGTH);
  memcpy (receipt + 124, record->expected_validator,
          GOODIX_SELF_STATE_DIGEST_LENGTH);
  memcpy (receipt + 156, record->prior_validator,
          GOODIX_SELF_STATE_DIGEST_LENGTH);
  memcpy (receipt + 188, record->fdt_table, GOODIX_SELF_STATE_FDT_LENGTH);
  if (record->bb010002_sha256_present)
    memcpy (receipt + 200, record->bb010002_sha256,
            GOODIX_SELF_STATE_DIGEST_LENGTH);
  else
    memcpy (receipt + 200, record->legacy_source_sha256,
            GOODIX_SELF_STATE_DIGEST_LENGTH);
  return hmac_sha256 (psk, receipt, RECEIPT_PREFIX_SIZE,
                      receipt + RECEIPT_PREFIX_SIZE);
}

static void
load_slot (int                          directory_fd,
           guint                        index,
           const GoodixSelfStatePolicy *policy,
           Slot                        *slot)
{
  static const gchar *const secret_names[2] = { "secret-a.bin", "secret-b.bin" };
  static const gchar *const receipt_names[2] = { "receipt-a.bin", "receipt-b.bin" };
  static const gchar *const secret_temps[2] = { ".secret-a.tmp", ".secret-b.tmp" };
  static const gchar *const receipt_temps[2] = { ".receipt-a.tmp", ".receipt-b.tmp" };
  guint8 secret[SECRET_SIZE];
  guint8 receipt[RECEIPT_SIZE];

  memset (slot, 0, sizeof *slot);
  slot->final_artifact = artifact_exists (directory_fd, secret_names[index]) ||
                         artifact_exists (directory_fd, receipt_names[index]);
  slot->temp_artifact = artifact_exists (directory_fd, secret_temps[index]) ||
                        artifact_exists (directory_fd, receipt_temps[index]);
  if (!read_exact_file (directory_fd, secret_names[index], secret,
                        sizeof secret, policy) ||
      !read_exact_file (directory_fd, receipt_names[index], receipt,
                        sizeof receipt, policy) ||
      memcmp (secret, secret_magic, sizeof secret_magic) != 0)
    goto out;
  slot->record.generation = get_u64_le (secret + 8);
  memcpy (slot->psk, secret + 16, sizeof slot->psk);
  if (!decode_receipt (receipt, slot->psk, &slot->binding, &slot->record) ||
      get_u64_le (secret + 8) != slot->record.generation)
    goto out;
  slot->valid = TRUE;
out:
  OPENSSL_cleanse (secret, sizeof secret);
  OPENSSL_cleanse (receipt, sizeof receipt);
}

static gboolean
fault_now (const GoodixSelfStatePolicy *policy,
           GoodixSelfStateFaultPoint    point,
           GError                     **error)
{
  if (policy->fault == NULL || !policy->fault (point, policy->fault_data))
    return FALSE;
  g_set_error_literal (error, self_state_error_quark (), EINTR,
                       "state-v2 simulated interruption");
  return TRUE;
}

static gboolean
write_all (int           fd,
           const guint8 *input,
           gsize         input_length)
{
  gsize offset = 0;

  while (offset < input_length)
    {
      ssize_t count = write (fd, input + offset, input_length - offset);

      if (count < 0 && errno == EINTR)
        continue;
      if (count <= 0)
        return FALSE;
      offset += (gsize) count;
    }
  return TRUE;
}

static gboolean
write_component (int                          directory_fd,
                 const gchar                 *temp_name,
                 const gchar                 *final_name,
                 const guint8                *contents,
                 gsize                        contents_length,
                 GoodixSelfStateFaultPoint    written_point,
                 GoodixSelfStateFaultPoint    synced_point,
                 GoodixSelfStateFaultPoint    renamed_point,
                 GoodixSelfStateFaultPoint    directory_synced_point,
                 const GoodixSelfStatePolicy *policy,
                 GError                     **error)
{
  int fd;

  if (unlinkat (directory_fd, temp_name, 0) != 0 && errno != ENOENT)
    {
      set_io_error (error, "stale temporary removal");
      return FALSE;
    }
  fd = openat (directory_fd, temp_name,
               O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
               policy->file_mode);
  if (fd < 0)
    {
      set_io_error (error, "temporary create");
      return FALSE;
    }
  if (fchmod (fd, policy->file_mode) != 0 ||
      !write_all (fd, contents, contents_length))
    {
      set_io_error (error, "temporary write");
      close (fd);
      return FALSE;
    }
  if (fault_now (policy, written_point, error))
    {
      close (fd);
      return FALSE;
    }
  if (fsync (fd) != 0)
    {
      set_io_error (error, "file sync");
      close (fd);
      return FALSE;
    }
  if (close (fd) != 0)
    {
      set_io_error (error, "file close");
      return FALSE;
    }
  if (fault_now (policy, synced_point, error))
    return FALSE;
  if (renameat (directory_fd, temp_name, directory_fd, final_name) != 0)
    {
      set_io_error (error, "atomic rename");
      return FALSE;
    }
  if (fault_now (policy, renamed_point, error))
    return FALSE;
  if (fsync (directory_fd) != 0)
    {
      set_io_error (error, "directory sync");
      return FALSE;
    }
  return !fault_now (policy, directory_synced_point, error);
}

static gboolean
write_state (const gchar                  *directory,
             const GoodixSelfStateBinding *binding,
             const GoodixSelfStateRecord  *record,
             const guint8                  psk[GOODIX_SELF_STATE_PSK_LENGTH],
             const GoodixSelfStatePolicy  *policy,
             GError                      **error)
{
  static const gchar *const secret_names[2] = { "secret-a.bin", "secret-b.bin" };
  static const gchar *const receipt_names[2] = { "receipt-a.bin", "receipt-b.bin" };
  static const gchar *const secret_temps[2] = { ".secret-a.tmp", ".secret-b.tmp" };
  static const gchar *const receipt_temps[2] = { ".receipt-a.tmp", ".receipt-b.tmp" };
  Slot slots[2];
  guint8 secret[SECRET_SIZE];
  guint8 receipt[RECEIPT_SIZE];
  guint target = 0;
  int directory_fd = -1;
  gboolean ok = FALSE;

  if (directory == NULL || !binding_valid (binding) || !record_valid (record) ||
      psk == NULL || !policy_valid (policy))
    {
      g_set_error_literal (error, self_state_error_quark (), EINVAL,
                           "invalid state-v2 input");
      return FALSE;
    }
  if (!open_directory (directory, policy, &directory_fd, FALSE, error))
    return FALSE;
  load_slot (directory_fd, 0u, policy, &slots[0]);
  load_slot (directory_fd, 1u, policy, &slots[1]);
  if ((slots[0].valid && !binding_equal (&slots[0].binding, binding)) ||
      (slots[1].valid && !binding_equal (&slots[1].binding, binding)))
    {
      g_set_error_literal (error, self_state_error_quark (), EPERM,
                           "state-v2 binding mismatch");
      goto out;
    }
  if (slots[0].valid && slots[1].valid)
    target = slots[0].record.generation <= slots[1].record.generation ? 0u : 1u;
  else if (slots[0].valid)
    target = 1u;
  else if (slots[1].valid)
    target = 0u;
  else if ((slots[0].final_artifact || slots[0].temp_artifact) &&
           (slots[1].final_artifact || slots[1].temp_artifact))
    {
      g_set_error_literal (error, self_state_error_quark (), EIO,
                           "state-v2 has no unambiguous writable slot");
      goto out;
    }
  else if (slots[0].final_artifact || slots[0].temp_artifact)
    target = 1u;
  if ((slots[0].valid && record->generation <= slots[0].record.generation) ||
      (slots[1].valid && record->generation <= slots[1].record.generation))
    {
      g_set_error_literal (error, self_state_error_quark (), EINVAL,
                           "state-v2 generation is not monotonic");
      goto out;
    }
  memset (secret, 0, sizeof secret);
  memcpy (secret, secret_magic, sizeof secret_magic);
  put_u64_le (secret + 8, record->generation);
  memcpy (secret + 16, psk, GOODIX_SELF_STATE_PSK_LENGTH);
  if (!encode_receipt (binding, record, psk, receipt))
    {
      g_set_error_literal (error, self_state_error_quark (), EIO,
                           "state-v2 receipt authentication failed");
      goto out;
    }
  if (!write_component (directory_fd, secret_temps[target], secret_names[target],
                        secret, sizeof secret,
                        GOODIX_SELF_STATE_FAULT_SECRET_TEMP_WRITTEN,
                        GOODIX_SELF_STATE_FAULT_SECRET_FILE_SYNCED,
                        GOODIX_SELF_STATE_FAULT_SECRET_RENAMED,
                        GOODIX_SELF_STATE_FAULT_SECRET_DIRECTORY_SYNCED,
                        policy, error) ||
      !write_component (directory_fd, receipt_temps[target], receipt_names[target],
                        receipt, sizeof receipt,
                        GOODIX_SELF_STATE_FAULT_RECEIPT_TEMP_WRITTEN,
                        GOODIX_SELF_STATE_FAULT_RECEIPT_FILE_SYNCED,
                        GOODIX_SELF_STATE_FAULT_RECEIPT_RENAMED,
                        GOODIX_SELF_STATE_FAULT_RECEIPT_DIRECTORY_SYNCED,
                        policy, error))
    goto out;
  ok = TRUE;
out:
  if (directory_fd >= 0)
    close (directory_fd);
  OPENSSL_cleanse (slots, sizeof slots);
  OPENSSL_cleanse (secret, sizeof secret);
  OPENSSL_cleanse (receipt, sizeof receipt);
  return ok;
}

void
goodix_self_state_policy_for_owner (GoodixSelfStatePolicy *policy,
                                    uid_t                  uid,
                                    gid_t                  gid)
{
  g_return_if_fail (policy != NULL);
  memset (policy, 0, sizeof *policy);
  policy->owner_uid = uid;
  policy->owner_gid = gid;
  policy->directory_mode = 0700u;
  policy->file_mode = 0600u;
}

GoodixSelfStateLoadResult
goodix_self_state_load (const gchar                  *directory,
                        const GoodixSelfStateBinding *binding,
                        const GoodixSelfStatePolicy  *policy,
                        GoodixSelfState             **state,
                        GError                      **error)
{
  Slot slots[2];
  Slot *selected = NULL;
  gboolean any_artifact;
  gboolean any_valid;
  int directory_fd = -1;

  if (state != NULL)
    *state = NULL;
  if (directory == NULL || !binding_valid (binding) || !policy_valid (policy) ||
      state == NULL)
    {
      g_set_error_literal (error, self_state_error_quark (), EINVAL,
                           "invalid state-v2 load input");
      return GOODIX_SELF_STATE_LOAD_INCOMPLETE;
    }
  if (!open_directory (directory, policy, &directory_fd, TRUE, error))
    return GOODIX_SELF_STATE_LOAD_INCOMPLETE;
  if (directory_fd < 0)
    return GOODIX_SELF_STATE_LOAD_ABSENT;
  load_slot (directory_fd, 0u, policy, &slots[0]);
  load_slot (directory_fd, 1u, policy, &slots[1]);
  close (directory_fd);
  any_artifact = slots[0].final_artifact || slots[0].temp_artifact ||
                 slots[1].final_artifact || slots[1].temp_artifact;
  any_valid = slots[0].valid || slots[1].valid;
  if ((slots[0].valid && !binding_equal (&slots[0].binding, binding)) ||
      (slots[1].valid && !binding_equal (&slots[1].binding, binding)))
    {
      OPENSSL_cleanse (slots, sizeof slots);
      return GOODIX_SELF_STATE_LOAD_BINDING_MISMATCH;
    }
  for (guint i = 0; i < 2u; i++)
    if (slots[i].valid && binding_equal (&slots[i].binding, binding) &&
        (selected == NULL ||
         slots[i].record.generation > selected->record.generation))
      selected = &slots[i];
  if (selected == NULL)
    {
      OPENSSL_cleanse (slots, sizeof slots);
      if (any_valid)
        return GOODIX_SELF_STATE_LOAD_BINDING_MISMATCH;
      return any_artifact ? GOODIX_SELF_STATE_LOAD_INCOMPLETE :
                            GOODIX_SELF_STATE_LOAD_ABSENT;
    }
  *state = g_new0 (GoodixSelfState, 1);
  (*state)->binding = selected->binding;
  (*state)->record = selected->record;
  memcpy ((*state)->psk, selected->psk, sizeof (*state)->psk);
  OPENSSL_cleanse (slots, sizeof slots);
  return GOODIX_SELF_STATE_LOAD_VALID;
}

gboolean
goodix_self_state_write_prepared (const gchar                  *directory,
                                  const GoodixSelfStateBinding *binding,
                                  const GoodixSelfStateRecord  *record,
                                  const guint8                  psk[GOODIX_SELF_STATE_PSK_LENGTH],
                                  const GoodixSelfStatePolicy  *policy,
                                  GError                      **error)
{
  if (record == NULL || record->phase != GOODIX_SELF_STATE_PREPARED ||
      record->terminal_proof)
    {
      g_set_error_literal (error, self_state_error_quark (), EINVAL,
                           "state-v2 prepared record required");
      return FALSE;
    }
  return write_state (directory, binding, record, psk, policy, error);
}

gboolean
goodix_self_state_import_legacy (const gchar                  *directory,
                                 const GoodixSelfStateBinding *binding,
                                 const guint8                  psk[GOODIX_SELF_STATE_PSK_LENGTH],
                                 const guint8                  validator[GOODIX_SELF_STATE_DIGEST_LENGTH],
                                 const guint8                  legacy_source_sha256[GOODIX_SELF_STATE_DIGEST_LENGTH],
                                 const guint8                 *fdt_table,
                                 const GoodixSelfStatePolicy  *policy,
                                 GError                      **error)
{
  GoodixSelfStateRecord record = { 0 };

  if (validator == NULL || legacy_source_sha256 == NULL)
    {
      g_set_error_literal (error, self_state_error_quark (), EINVAL,
                           "invalid legacy import input");
      return FALSE;
    }
  record.phase = GOODIX_SELF_STATE_PREPARED;
  record.generation = 1u;
  memcpy (record.expected_validator, validator, sizeof record.expected_validator);
  record.fdt_present = fdt_table != NULL;
  if (fdt_table != NULL)
    memcpy (record.fdt_table, fdt_table, sizeof record.fdt_table);
  record.migrated_legacy = TRUE;
  memcpy (record.legacy_source_sha256, legacy_source_sha256,
          sizeof record.legacy_source_sha256);
  return goodix_self_state_write_prepared (directory, binding, &record, psk,
                                           policy, error);
}

GoodixSelfStateReconcile
goodix_self_state_reconcile (const GoodixSelfState *state,
                             const guint8           live_validator[GOODIX_SELF_STATE_DIGEST_LENGTH],
                             gboolean               tls_proven)
{
  const GoodixSelfStateRecord *record;

  g_return_val_if_fail (state != NULL && live_validator != NULL,
                        GOODIX_SELF_STATE_RECONCILE_RECOVERY_REQUIRED);
  record = &state->record;
  if (record->phase == GOODIX_SELF_STATE_ACTIVE)
    return CRYPTO_memcmp (record->expected_validator, live_validator,
                          GOODIX_SELF_STATE_DIGEST_LENGTH) == 0 ?
             GOODIX_SELF_STATE_RECONCILE_ACTIVE_MATCH :
             GOODIX_SELF_STATE_RECONCILE_EXTERNAL_REPLACEMENT;
  if (record->phase != GOODIX_SELF_STATE_PREPARED)
    return GOODIX_SELF_STATE_RECONCILE_RECOVERY_REQUIRED;
  if (CRYPTO_memcmp (record->expected_validator, live_validator,
                     GOODIX_SELF_STATE_DIGEST_LENGTH) == 0)
    return tls_proven ? GOODIX_SELF_STATE_RECONCILE_PROMOTE_ACTIVE :
                        GOODIX_SELF_STATE_RECONCILE_RETRY_TLS;
  if (record->prior_validator_present &&
      CRYPTO_memcmp (record->prior_validator, live_validator,
                     GOODIX_SELF_STATE_DIGEST_LENGTH) == 0)
    return GOODIX_SELF_STATE_RECONCILE_USE_PRIOR;
  return GOODIX_SELF_STATE_RECONCILE_RECOVERY_REQUIRED;
}

gboolean
goodix_self_state_promote_active (const gchar                 *directory,
                                  const GoodixSelfState       *prepared,
                                  const GoodixSelfStatePolicy *policy,
                                  GError                     **error)
{
  GoodixSelfStateRecord record;

  if (prepared == NULL || prepared->record.phase != GOODIX_SELF_STATE_PREPARED ||
      prepared->record.generation == G_MAXUINT64)
    {
      g_set_error_literal (error, self_state_error_quark (), EINVAL,
                           "state-v2 promotable record required");
      return FALSE;
    }
  record = prepared->record;
  record.phase = GOODIX_SELF_STATE_ACTIVE;
  record.generation++;
  record.terminal_proof = TRUE;
  return write_state (directory, &prepared->binding, &record, prepared->psk,
                      policy, error);
}

const GoodixSelfStateRecord *
goodix_self_state_get_record (const GoodixSelfState *state)
{
  return state == NULL ? NULL : &state->record;
}

const GoodixSelfStateBinding *
goodix_self_state_get_binding (const GoodixSelfState *state)
{
  return state == NULL ? NULL : &state->binding;
}

gboolean
goodix_self_state_copy_psk (const GoodixSelfState *state,
                            guint8                  psk[GOODIX_SELF_STATE_PSK_LENGTH])
{
  if (state == NULL || psk == NULL)
    return FALSE;
  memcpy (psk, state->psk, GOODIX_SELF_STATE_PSK_LENGTH);
  return TRUE;
}

void
goodix_self_state_free (GoodixSelfState *state)
{
  if (state == NULL)
    return;
  OPENSSL_cleanse (state, sizeof *state);
  g_free (state);
}
