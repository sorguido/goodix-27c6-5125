/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (c) 2026 sorguido
 *
 * The PE portion is a bounded C adaptation of the project-authored
 * BSD-2-Clause reference at commit
 * b475a6eca72e340816779afae917334a6146c986, path
 * poc/goodix5125/tools/binding_reference/pe_parser.py.  Its BSD notice and
 * provenance are retained in docs/LICENSING_AND_PROVENANCE.md.  The FDT
 * portion is independently expressed from the neutral D255/D261 cache
 * contract.  Transformations consume inert caller-owned bytes; the optional
 * file adapter reads only two explicit paths under a strict private-file
 * policy and never discovers paths or writes inputs.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "goodix_runtime_inputs.h"

#include <errno.h>
#include <fcntl.h>
#include <openssl/crypto.h>

#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

typedef enum
{
  GOODIX_RUNTIME_INPUTS_ERROR_ARGUMENT,
  GOODIX_RUNTIME_INPUTS_ERROR_HASH,
  GOODIX_RUNTIME_INPUTS_ERROR_PE_FORMAT,
  GOODIX_RUNTIME_INPUTS_ERROR_PE_PATTERN,
  GOODIX_RUNTIME_INPUTS_ERROR_CACHE_LAYOUT,
  GOODIX_RUNTIME_INPUTS_ERROR_CACHE_CRC,
  GOODIX_RUNTIME_INPUTS_ERROR_CACHE_OTP,
  GOODIX_RUNTIME_INPUTS_ERROR_CACHE_FDT,
  GOODIX_RUNTIME_INPUTS_ERROR_FILE_OPEN,
  GOODIX_RUNTIME_INPUTS_ERROR_FILE_METADATA,
  GOODIX_RUNTIME_INPUTS_ERROR_FILE_READ,
} GoodixRuntimeInputsError;

#define GOODIX_RUNTIME_INPUTS_ERROR (goodix_runtime_inputs_error_quark ())

typedef struct
{
  guint32 virtual_size;
  guint32 virtual_address;
  guint32 raw_size;
  guint32 raw_offset;
} GoodixPeSection;

static GQuark
goodix_runtime_inputs_error_quark (void)
{
  return g_quark_from_static_string ("goodix-runtime-inputs-error");
}

const gchar *
goodix_runtime_inputs_error_class (const GError *error)
{
  if (error == NULL || error->domain != GOODIX_RUNTIME_INPUTS_ERROR)
    return "ARGUMENT_OR_POLICY";

  switch ((GoodixRuntimeInputsError) error->code)
    {
    case GOODIX_RUNTIME_INPUTS_ERROR_HASH:
      return "INPUT_HASH";
    case GOODIX_RUNTIME_INPUTS_ERROR_PE_FORMAT:
      return "PE_FORMAT";
    case GOODIX_RUNTIME_INPUTS_ERROR_PE_PATTERN:
      return "PE_PATTERN";
    case GOODIX_RUNTIME_INPUTS_ERROR_CACHE_LAYOUT:
      return "FDT_CACHE_LAYOUT";
    case GOODIX_RUNTIME_INPUTS_ERROR_CACHE_CRC:
      return "FDT_CACHE_CRC";
    case GOODIX_RUNTIME_INPUTS_ERROR_CACHE_OTP:
      return "FDT_CACHE_OTP_BINDING";
    case GOODIX_RUNTIME_INPUTS_ERROR_CACHE_FDT:
      return "FDT_CACHE_SEED";
    case GOODIX_RUNTIME_INPUTS_ERROR_FILE_OPEN:
      return "PRIVATE_INPUT_OPEN";
    case GOODIX_RUNTIME_INPUTS_ERROR_FILE_METADATA:
      return "PRIVATE_INPUT_METADATA";
    case GOODIX_RUNTIME_INPUTS_ERROR_FILE_READ:
      return "PRIVATE_INPUT_READ";
    case GOODIX_RUNTIME_INPUTS_ERROR_ARGUMENT:
    default:
      return "ARGUMENT_OR_POLICY";
    }
}

static guint16
read_le16 (const guint8 *bytes)
{
  return (guint16) bytes[0] | ((guint16) bytes[1] << 8);
}

static guint32
read_le32 (const guint8 *bytes)
{
  return (guint32) bytes[0] |
         ((guint32) bytes[1] << 8) |
         ((guint32) bytes[2] << 16) |
         ((guint32) bytes[3] << 24);
}

static gboolean
sha256 (const guint8 *bytes,
        gsize         length,
        guint8        output[32])
{
  g_autoptr(GChecksum) checksum = NULL;
  gsize output_length = 32;

  if (bytes == NULL || length > G_MAXSSIZE)
    return FALSE;
  checksum = g_checksum_new (G_CHECKSUM_SHA256);
  g_checksum_update (checksum, bytes, (gssize) length);
  g_checksum_get_digest (checksum, output, &output_length);
  return output_length == 32;
}

static guint32
crc32_mpeg2 (const guint8 *bytes,
             gsize         length)
{
  guint32 crc = 0xffffffffu;

  for (gsize i = 0; i < length; i++)
    {
      crc ^= (guint32) bytes[i] << 24;
      for (guint bit = 0; bit < 8u; bit++)
        crc = (crc & 0x80000000u) != 0u ?
          (crc << 1) ^ 0x04c11db7u : crc << 1;
    }
  return crc;
}

void
goodix_runtime_pe_policy_production (GoodixRuntimePePolicy *policy)
{
  static const guint8 hash[32] = {
    0x90,0x4e,0xab,0x1d,0x9d,0xbf,0xab,0x26,
    0x09,0xda,0x36,0x1a,0xa6,0xdd,0xba,0x54,
    0x9a,0x9d,0x50,0x3f,0x85,0xb4,0xe4,0x39,
    0xb0,0x29,0x49,0x08,0xf4,0xcb,0xc7,0xe2
  };

  g_return_if_fail (policy != NULL);
  memset (policy, 0, sizeof *policy);
  memcpy (policy->expected_sha256, hash, sizeof hash);
  policy->file_length = 5771496u;
  policy->first_seed_rva = 0x56f030u;
  policy->second_instruction_rva = 0x69d0u;
}

void
goodix_runtime_fdt_policy_production (GoodixRuntimeFdtPolicy *policy)
{
  static const guint8 cache_hash[32] = {
    0x9f,0x53,0x27,0x73,0x1c,0xff,0x30,0x46,
    0xe3,0x1d,0x18,0x35,0x6a,0x63,0x34,0xc9,
    0xe1,0x49,0x43,0x30,0xf4,0x34,0xf3,0xfe,
    0x75,0xad,0x0a,0x4c,0x80,0xdb,0x09,0xe2
  };
  static const guint8 otp_hash[32] = {
    0xd7,0xe8,0x1a,0x41,0x5a,0xa5,0xe7,0xb0,
    0x16,0x8c,0x9a,0x63,0x27,0x56,0xd1,0xdc,
    0x8b,0x7b,0x47,0x34,0x6c,0xc0,0xa4,0x4d,
    0xc6,0x87,0x96,0xf8,0x54,0xc2,0xb9,0x2b
  };

  g_return_if_fail (policy != NULL);
  memset (policy, 0, sizeof *policy);
  memcpy (policy->expected_sha256, cache_hash, sizeof cache_hash);
  memcpy (policy->expected_otp_sha256, otp_hash, sizeof otp_hash);
  policy->cache_length = 13520u;
  policy->crc_offset = 13516u;
  policy->otp_length = 64u;
  policy->fdt_offset = 64u;
}

void
goodix_runtime_input_file_policy_production (
  GoodixRuntimeInputFilePolicy *policy)
{
  g_return_if_fail (policy != NULL);
  memset (policy, 0, sizeof *policy);
  policy->owner_uid = 0;
  policy->mode = 0600;
}

static gboolean
parse_pe_sections (const guint8  *bytes,
                   gsize          length,
                   GoodixPeSection sections[96],
                   guint         *section_count,
                   GError       **error)
{
  guint32 pe_offset;
  guint count;
  guint optional_size;
  gsize table_offset;

  if (length < 0x40u || bytes[0] != 'M' || bytes[1] != 'Z')
    goto malformed;
  pe_offset = read_le32 (bytes + 0x3cu);
  if ((gsize) pe_offset > length || length - (gsize) pe_offset < 24u ||
      memcmp (bytes + pe_offset, "PE\0\0", 4u) != 0)
    goto malformed;
  count = read_le16 (bytes + pe_offset + 6u);
  optional_size = read_le16 (bytes + pe_offset + 20u);
  if (count == 0u || count > 96u)
    goto malformed;
  table_offset = (gsize) pe_offset + 24u + optional_size;
  if (table_offset > length || count > (length - table_offset) / 40u)
    goto malformed;

  for (guint i = 0; i < count; i++)
    {
      const guint8 *entry = bytes + table_offset + i * 40u;
      sections[i].virtual_size = read_le32 (entry + 8u);
      sections[i].virtual_address = read_le32 (entry + 12u);
      sections[i].raw_size = read_le32 (entry + 16u);
      sections[i].raw_offset = read_le32 (entry + 20u);
    }
  *section_count = count;
  return TRUE;

malformed:
  g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                       GOODIX_RUNTIME_INPUTS_ERROR_PE_FORMAT,
                       "truncated or malformed PE headers");
  return FALSE;
}

static const guint8 *
pe_rva_bytes (const guint8         *bytes,
              gsize                length,
              const GoodixPeSection sections[96],
              guint                section_count,
              guint32              rva,
              gsize                wanted,
              GError             **error)
{
  for (guint i = 0; i < section_count; i++)
    {
      guint64 start = sections[i].virtual_address;
      guint64 backed = MIN (sections[i].virtual_size, sections[i].raw_size);
      guint64 requested_end = (guint64) rva + wanted;

      if ((guint64) rva >= start && requested_end <= start + backed)
        {
          guint64 offset = sections[i].raw_offset + ((guint64) rva - start);
          if (offset <= length && wanted <= length - (gsize) offset)
            return bytes + (gsize) offset;
          break;
        }
    }
  g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                       GOODIX_RUNTIME_INPUTS_ERROR_PE_FORMAT,
                       "producer RVA is outside file-backed PE ranges");
  return NULL;
}

static gboolean
instruction_is_unique (const guint8 *bytes,
                       gsize         length,
                       const guint8  instruction[14])
{
  guint matches = 0;

  if (length < 12u || instruction[0] != 0xc7u ||
      instruction[1] != 0x45u || instruction[2] != 0x9fu ||
      instruction[7] != 0xc7u || instruction[8] != 0x45u ||
      instruction[9] != 0xa3u)
    return FALSE;
  for (gsize offset = 0; offset <= length - 12u; offset++)
    if (memcmp (bytes + offset, instruction, 12u) == 0)
      {
        matches++;
        if (matches > 1u)
          return FALSE;
      }
  return matches == 1u;
}

gboolean
goodix_runtime_extract_producer_seeds (
  const guint8                *pe_bytes,
  gsize                        pe_length,
  const GoodixRuntimePePolicy *policy,
  guint8                       seed_a[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH],
  guint8                       seed_b[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH],
  GError                     **error)
{
  GoodixPeSection sections[96];
  guint section_count = 0;
  guint8 actual_hash[32] = { 0 };
  const guint8 *first = NULL;
  const guint8 *instruction = NULL;
  gboolean ok = FALSE;

  if (seed_a != NULL)
    OPENSSL_cleanse (seed_a, GOODIX_RUNTIME_PRODUCER_SEED_LENGTH);
  if (seed_b != NULL)
    OPENSSL_cleanse (seed_b, GOODIX_RUNTIME_PRODUCER_SEED_LENGTH);
  if (pe_bytes == NULL || policy == NULL || seed_a == NULL || seed_b == NULL)
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_ARGUMENT,
                           "PE provider argument is absent");
      goto out;
    }
  if (!sha256 (pe_bytes, pe_length, actual_hash) ||
      CRYPTO_memcmp (actual_hash, policy->expected_sha256, 32u) != 0)
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_HASH,
                           "canonical PE SHA-256 mismatch");
      goto out;
    }
  if (!parse_pe_sections (pe_bytes, pe_length, sections, &section_count,
                          error))
    goto out;
  first = pe_rva_bytes (pe_bytes, pe_length, sections, section_count,
                        policy->first_seed_rva, 6u, error);
  if (first == NULL)
    goto out;
  instruction = pe_rva_bytes (pe_bytes, pe_length, sections, section_count,
                              policy->second_instruction_rva, 14u, error);
  if (instruction == NULL)
    goto out;
  if (!instruction_is_unique (pe_bytes, pe_length, instruction))
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_PE_PATTERN,
                           "producer instruction pattern missing or ambiguous");
      goto out;
    }

  memcpy (seed_a, first, 6u);
  memcpy (seed_b, instruction + 3u, 4u);
  memcpy (seed_b + 4u, instruction + 10u, 2u);
  ok = TRUE;

out:
  if (!ok)
    {
      if (seed_a != NULL)
        OPENSSL_cleanse (seed_a, GOODIX_RUNTIME_PRODUCER_SEED_LENGTH);
      if (seed_b != NULL)
        OPENSSL_cleanse (seed_b, GOODIX_RUNTIME_PRODUCER_SEED_LENGTH);
    }
  OPENSSL_cleanse (actual_hash, sizeof actual_hash);
  OPENSSL_cleanse (sections, sizeof sections);
  return ok;
}

gboolean
goodix_runtime_extract_fdt_seed (
  const guint8                 *cache_bytes,
  gsize                         cache_length,
  const GoodixRuntimeFdtPolicy *policy,
  guint8                        fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GError                      **error)
{
  guint8 actual_hash[32] = { 0 };
  guint8 otp_hash[32] = { 0 };
  guint32 stored_crc;
  gboolean present = FALSE;
  gboolean ok = FALSE;

  if (fdt_seed != NULL)
    memset (fdt_seed, 0, GOODIX_RUNTIME_FDT_SEED_LENGTH);
  if (cache_bytes == NULL || policy == NULL || fdt_seed == NULL ||
      policy->cache_length != cache_length || policy->otp_length == 0u ||
      policy->crc_offset > cache_length ||
      cache_length - policy->crc_offset != 4u ||
      policy->fdt_offset > policy->crc_offset ||
      GOODIX_RUNTIME_FDT_SEED_LENGTH > policy->crc_offset - policy->fdt_offset ||
      policy->otp_length > policy->fdt_offset)
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_CACHE_LAYOUT,
                           "FDT cache layout or argument is invalid");
      goto out;
    }
  if (!sha256 (cache_bytes, cache_length, actual_hash) ||
      CRYPTO_memcmp (actual_hash, policy->expected_sha256, 32u) != 0)
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_HASH,
                           "canonical FDT cache SHA-256 mismatch");
      goto out;
    }
  stored_crc = read_le32 (cache_bytes + policy->crc_offset);
  if (stored_crc != crc32_mpeg2 (cache_bytes, policy->crc_offset))
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_CACHE_CRC,
                           "FDT cache CRC-32/MPEG-2 mismatch");
      goto out;
    }
  if (!sha256 (cache_bytes, policy->otp_length, otp_hash) ||
      CRYPTO_memcmp (otp_hash, policy->expected_otp_sha256, 32u) != 0)
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_CACHE_OTP,
                           "FDT cache OTP binding mismatch");
      goto out;
    }

  memcpy (fdt_seed, cache_bytes + policy->fdt_offset,
          GOODIX_RUNTIME_FDT_SEED_LENGTH);
  for (guint i = 0; i < GOODIX_RUNTIME_FDT_SEED_LENGTH; i++)
    present = present || fdt_seed[i] != 0u;
  if (!present)
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_CACHE_FDT,
                           "FDT cache seed is absent");
      goto out;
    }
  ok = TRUE;

out:
  if (!ok && fdt_seed != NULL)
    memset (fdt_seed, 0, GOODIX_RUNTIME_FDT_SEED_LENGTH);
  OPENSSL_cleanse (actual_hash, sizeof actual_hash);
  OPENSSL_cleanse (otp_hash, sizeof otp_hash);
  return ok;
}

void
goodix_runtime_cleanse_producer_seed (
  guint8 seed[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH])
{
  if (seed != NULL)
    OPENSSL_cleanse (seed, GOODIX_RUNTIME_PRODUCER_SEED_LENGTH);
}

static gboolean
private_metadata_valid (const struct stat                  *status,
                        const GoodixRuntimeInputFilePolicy *policy,
                        gsize                               expected_length)
{
  return S_ISREG (status->st_mode) && status->st_uid == policy->owner_uid &&
         (status->st_mode & 07777u) == policy->mode && status->st_size >= 0 &&
         (guint64) status->st_size == expected_length;
}

static guint8 *
read_private_exact (const gchar                        *path,
                    gsize                               expected_length,
                    const GoodixRuntimeInputFilePolicy *policy,
                    GoodixRuntimeInputFileAudit        *audit,
                    GError                            **error)
{
  struct stat before;
  struct stat after;
  guint8 *bytes = NULL;
  gsize offset = 0;
  gint fd = -1;

  fd = open (path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (fd < 0)
    {
      g_set_error (error, GOODIX_RUNTIME_INPUTS_ERROR,
                   GOODIX_RUNTIME_INPUTS_ERROR_FILE_OPEN,
                   "private runtime input open failed: %s",
                   g_strerror (errno));
      goto fail;
    }
  if (audit != NULL)
    audit->open_count++;
  if (fstat (fd, &before) != 0 ||
      !private_metadata_valid (&before, policy, expected_length))
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_FILE_METADATA,
                           "private runtime input metadata mismatch");
      goto fail;
    }

  bytes = g_malloc0 (expected_length);
  if (audit != NULL)
    audit->buffer_allocation_count++;
  while (offset < expected_length)
    {
      ssize_t count = read (fd, bytes + offset, expected_length - offset);
      if (count < 0 && errno == EINTR)
        continue;
      if (count <= 0)
        {
          g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                               GOODIX_RUNTIME_INPUTS_ERROR_FILE_READ,
                               "private runtime input short/error read");
          goto fail;
        }
      offset += (gsize) count;
    }
  if (policy->after_read != NULL)
    policy->after_read (path, fd, policy->after_read_data);
  if (fstat (fd, &after) != 0 || before.st_dev != after.st_dev ||
      before.st_ino != after.st_ino || before.st_size != after.st_size ||
      before.st_mtim.tv_sec != after.st_mtim.tv_sec ||
      before.st_mtim.tv_nsec != after.st_mtim.tv_nsec ||
      !private_metadata_valid (&after, policy, expected_length))
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_FILE_METADATA,
                           "private runtime input changed during read");
      goto fail;
    }
  if (audit != NULL)
    audit->read_count++;
  close (fd);
  return bytes;

fail:
  if (fd >= 0)
    close (fd);
  if (bytes != NULL)
    {
      OPENSSL_cleanse (bytes, expected_length);
      if (policy->cleanse_observer != NULL)
        policy->cleanse_observer (bytes, expected_length,
                                  policy->cleanse_observer_data);
      if (audit != NULL)
        audit->buffer_cleanse_count++;
      g_free (bytes);
    }
  return NULL;
}

gboolean
goodix_runtime_extract_inputs_from_files (
  const gchar                        *pe_path,
  const gchar                        *cache_path,
  const GoodixRuntimePePolicy        *pe_policy,
  const GoodixRuntimeFdtPolicy       *fdt_policy,
  const GoodixRuntimeInputFilePolicy *file_policy,
  guint8 seed_a[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH],
  guint8 seed_b[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH],
  guint8 fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GoodixRuntimeInputFileAudit        *audit,
  GError                            **error)
{
  guint8 *pe_bytes = NULL;
  guint8 *cache_bytes = NULL;
  guint8 local_a[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH] = { 0 };
  guint8 local_b[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH] = { 0 };
  guint8 local_fdt[GOODIX_RUNTIME_FDT_SEED_LENGTH] = { 0 };
  gboolean ok = FALSE;

  if (audit != NULL)
    memset (audit, 0, sizeof *audit);
  if (seed_a != NULL)
    OPENSSL_cleanse (seed_a, GOODIX_RUNTIME_PRODUCER_SEED_LENGTH);
  if (seed_b != NULL)
    OPENSSL_cleanse (seed_b, GOODIX_RUNTIME_PRODUCER_SEED_LENGTH);
  if (fdt_seed != NULL)
    memset (fdt_seed, 0, GOODIX_RUNTIME_FDT_SEED_LENGTH);
  if (pe_path == NULL || cache_path == NULL || pe_policy == NULL ||
      fdt_policy == NULL || file_policy == NULL || seed_a == NULL ||
      seed_b == NULL || fdt_seed == NULL || pe_policy->file_length == 0u ||
      file_policy->mode != 0600)
    {
      g_set_error_literal (error, GOODIX_RUNTIME_INPUTS_ERROR,
                           GOODIX_RUNTIME_INPUTS_ERROR_ARGUMENT,
                           "private runtime input policy or output is invalid");
      goto out;
    }

  pe_bytes = read_private_exact (pe_path, pe_policy->file_length, file_policy,
                                 audit, error);
  if (pe_bytes == NULL ||
      !goodix_runtime_extract_producer_seeds (
        pe_bytes, pe_policy->file_length, pe_policy, local_a, local_b, error))
    goto out;
  cache_bytes = read_private_exact (cache_path, fdt_policy->cache_length,
                                    file_policy, audit, error);
  if (cache_bytes == NULL ||
      !goodix_runtime_extract_fdt_seed (cache_bytes, fdt_policy->cache_length,
                                       fdt_policy, local_fdt, error))
    goto out;

  memcpy (seed_a, local_a, sizeof local_a);
  memcpy (seed_b, local_b, sizeof local_b);
  memcpy (fdt_seed, local_fdt, sizeof local_fdt);
  ok = TRUE;

out:
  OPENSSL_cleanse (local_a, sizeof local_a);
  OPENSSL_cleanse (local_b, sizeof local_b);
  memset (local_fdt, 0, sizeof local_fdt);
  if (pe_bytes != NULL)
    {
      OPENSSL_cleanse (pe_bytes, pe_policy->file_length);
      if (file_policy->cleanse_observer != NULL)
        file_policy->cleanse_observer (pe_bytes, pe_policy->file_length,
                                       file_policy->cleanse_observer_data);
      if (audit != NULL)
        audit->buffer_cleanse_count++;
      g_free (pe_bytes);
    }
  if (cache_bytes != NULL)
    {
      OPENSSL_cleanse (cache_bytes, fdt_policy->cache_length);
      if (file_policy->cleanse_observer != NULL)
        file_policy->cleanse_observer (cache_bytes, fdt_policy->cache_length,
                                       file_policy->cleanse_observer_data);
      if (audit != NULL)
        audit->buffer_cleanse_count++;
      g_free (cache_bytes);
    }
  if (!ok)
    {
      if (seed_a != NULL)
        OPENSSL_cleanse (seed_a, GOODIX_RUNTIME_PRODUCER_SEED_LENGTH);
      if (seed_b != NULL)
        OPENSSL_cleanse (seed_b, GOODIX_RUNTIME_PRODUCER_SEED_LENGTH);
      if (fdt_seed != NULL)
        memset (fdt_seed, 0, GOODIX_RUNTIME_FDT_SEED_LENGTH);
    }
  if (audit != NULL)
    audit->all_buffers_cleansed =
      audit->buffer_cleanse_count == audit->buffer_allocation_count;
  return ok;
}
