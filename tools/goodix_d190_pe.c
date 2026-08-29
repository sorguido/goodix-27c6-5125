/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Copyright (c) 2026 sorguido
 *
 * Bounded, read-only PE producer-seed extraction.  Adapted from the
 * project-authored BSD-2-Clause D190/D191 reference at commit
 * b475a6eca72e340816779afae917334a6146c986, source path
 * poc/goodix5125/tools/binding_reference/pe_parser.py, into the GPL tooling
 * boundary.  No PE image is ever loaded, mapped executable, spawned or passed
 * to Wine.
 */
#include "goodix_d190_pe.h"

#include <openssl/crypto.h>

#include <string.h>

typedef enum
{
  GOODIX_D190_PE_ERROR_ARGUMENT,
  GOODIX_D190_PE_ERROR_HASH,
  GOODIX_D190_PE_ERROR_FORMAT,
  GOODIX_D190_PE_ERROR_PATTERN,
  GOODIX_D190_PE_ERROR_IO,
} GoodixD190PeError;

#define GOODIX_D190_PE_ERROR (goodix_d190_pe_error_quark ())

typedef struct
{
  guint32 virtual_size;
  guint32 virtual_address;
  guint32 raw_size;
  guint32 raw_offset;
} PeSection;

static GQuark
goodix_d190_pe_error_quark (void)
{
  return g_quark_from_static_string ("goodix-d190-pe-error");
}

static guint16
read_le16 (const guint8 *data)
{
  return (guint16) data[0] | ((guint16) data[1] << 8);
}

static guint32
read_le32 (const guint8 *data)
{
  return (guint32) data[0] |
         ((guint32) data[1] << 8) |
         ((guint32) data[2] << 16) |
         ((guint32) data[3] << 24);
}

static gboolean
sha256 (const guint8 *data,
        gsize         length,
        guint8        output[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  gsize output_length = 32;

  if (length > G_MAXSSIZE)
    return FALSE;
  g_checksum_update (checksum, data, (gssize) length);
  g_checksum_get_digest (checksum, output, &output_length);
  return output_length == 32;
}

void
goodix_d190_pe_policy_production (GoodixD190PePolicy *policy)
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
  policy->first_seed_rva = 0x56f030u;
  policy->second_instruction_rva = 0x69d0u;
}

static gboolean
parse_sections (const guint8 *data,
                gsize         length,
                PeSection    *sections,
                guint        *section_count,
                GError      **error)
{
  guint32 pe_offset;
  guint count;
  guint optional_size;
  gsize table;

  if (length < 0x40 || data[0] != 'M' || data[1] != 'Z')
    goto malformed;
  pe_offset = read_le32 (data + 0x3c);
  if ((gsize) pe_offset > length || length - (gsize) pe_offset < 24 ||
      memcmp (data + pe_offset, "PE\0\0", 4) != 0)
    goto malformed;
  count = read_le16 (data + pe_offset + 6);
  optional_size = read_le16 (data + pe_offset + 20);
  if (count == 0 || count > 96)
    goto malformed;
  table = (gsize) pe_offset + 24u + optional_size;
  if (table > length || count > (length - table) / 40u)
    goto malformed;
  for (guint i = 0; i < count; i++)
    {
      const guint8 *entry = data + table + i * 40u;
      sections[i].virtual_size = read_le32 (entry + 8);
      sections[i].virtual_address = read_le32 (entry + 12);
      sections[i].raw_size = read_le32 (entry + 16);
      sections[i].raw_offset = read_le32 (entry + 20);
    }
  *section_count = count;
  return TRUE;

malformed:
  g_set_error_literal (error, GOODIX_D190_PE_ERROR,
                       GOODIX_D190_PE_ERROR_FORMAT,
                       "truncated or malformed PE headers");
  return FALSE;
}

static const guint8 *
at_rva (const guint8    *data,
        gsize            length,
        const PeSection *sections,
        guint            section_count,
        guint32          rva,
        gsize            size,
        GError         **error)
{
  for (guint i = 0; i < section_count; i++)
    {
      guint32 backed = MIN (sections[i].virtual_size, sections[i].raw_size);
      guint64 start = sections[i].virtual_address;
      guint64 end = start + backed;
      guint64 requested_end = (guint64) rva + size;

      if ((guint64) rva >= start && requested_end <= end)
        {
          guint64 offset = (guint64) sections[i].raw_offset +
                           ((guint64) rva - start);
          if (offset <= length && size <= length - (gsize) offset)
            return data + (gsize) offset;
          break;
        }
    }
  g_set_error_literal (error, GOODIX_D190_PE_ERROR,
                       GOODIX_D190_PE_ERROR_FORMAT,
                       "producer RVA is outside file-backed PE ranges");
  return NULL;
}

static gboolean
unique_instruction (const guint8 *data,
                    gsize         length,
                    const guint8  instruction[14])
{
  guint matches = 0;

  if (instruction[0] != 0xc7 || instruction[1] != 0x45 ||
      instruction[2] != 0x9f || instruction[7] != 0xc7 ||
      instruction[8] != 0x45 || instruction[9] != 0xa3 || length < 12)
    return FALSE;
  for (gsize i = 0; i <= length - 12; i++)
    if (memcmp (data + i, instruction, 12) == 0 && ++matches > 1)
      return FALSE;
  return matches == 1;
}

gboolean
goodix_d190_pe_extract_bytes_with_policy (const guint8             *data,
                                          gsize                     length,
                                          const GoodixD190PePolicy *policy,
                                          guint8                    seed_a[6],
                                          guint8                    seed_b[6],
                                          GError                  **error)
{
  PeSection sections[96];
  guint section_count = 0;
  guint8 actual_hash[32] = { 0 };
  const guint8 *first;
  const guint8 *instruction;
  gboolean ok = FALSE;

  if (seed_a != NULL)
    OPENSSL_cleanse (seed_a, 6);
  if (seed_b != NULL)
    OPENSSL_cleanse (seed_b, 6);
  if (data == NULL || policy == NULL || seed_a == NULL || seed_b == NULL)
    {
      g_set_error_literal (error, GOODIX_D190_PE_ERROR,
                           GOODIX_D190_PE_ERROR_ARGUMENT,
                           "PE extraction argument is absent");
      goto out;
    }
  if (!sha256 (data, length, actual_hash) ||
      CRYPTO_memcmp (actual_hash, policy->expected_sha256, 32) != 0)
    {
      g_set_error_literal (error, GOODIX_D190_PE_ERROR,
                           GOODIX_D190_PE_ERROR_HASH,
                           "canonical gfusb.dll SHA-256 mismatch");
      goto out;
    }
  if (!parse_sections (data, length, sections, &section_count, error))
    goto out;
  first = at_rva (data, length, sections, section_count,
                  policy->first_seed_rva, 6, error);
  if (first == NULL)
    goto out;
  instruction = at_rva (data, length, sections, section_count,
                        policy->second_instruction_rva, 14, error);
  if (instruction == NULL)
    goto out;
  if (!unique_instruction (data, length, instruction))
    {
      g_set_error_literal (error, GOODIX_D190_PE_ERROR,
                           GOODIX_D190_PE_ERROR_PATTERN,
                           "producer instruction pattern missing or ambiguous");
      goto out;
    }
  memcpy (seed_a, first, 6);
  memcpy (seed_b, instruction + 3, 4);
  memcpy (seed_b + 4, instruction + 10, 2);
  ok = TRUE;
out:
  if (!ok)
    {
      if (seed_a != NULL)
        OPENSSL_cleanse (seed_a, 6);
      if (seed_b != NULL)
        OPENSSL_cleanse (seed_b, 6);
    }
  OPENSSL_cleanse (actual_hash, sizeof actual_hash);
  OPENSSL_cleanse (sections, sizeof sections);
  return ok;
}

gboolean
goodix_d190_pe_extract (const gchar *path,
                        guint8       seed_a[6],
                        guint8       seed_b[6],
                        GError     **error)
{
  g_autofree gchar *contents = NULL;
  gsize length = 0;
  GoodixD190PePolicy policy;

  if (path == NULL || !g_file_get_contents (path, &contents, &length, error))
    {
      if (error != NULL && *error == NULL)
        g_set_error_literal (error, GOODIX_D190_PE_ERROR,
                             GOODIX_D190_PE_ERROR_IO,
                             "canonical gfusb.dll could not be read");
      return FALSE;
    }
  goodix_d190_pe_policy_production (&policy);
  return goodix_d190_pe_extract_bytes_with_policy ((const guint8 *) contents,
                                                    length, &policy,
                                                    seed_a, seed_b, error);
}

void
goodix_d190_pe_cleanse_seed (guint8 seed[6])
{
  if (seed != NULL)
    OPENSSL_cleanse (seed, 6);
}
