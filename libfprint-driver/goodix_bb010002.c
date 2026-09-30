/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Copyright (c) 2026 sorguido */
#include "goodix_bb010002.h"

#include <string.h>

#define DPAPI_BLOB_LENGTH 324u

static const guint8 dpapi_provider_guid[16] = {
  0xd0, 0x8c, 0x9d, 0xdf, 0x01, 0x15, 0xd1, 0x11,
  0x8c, 0x7a, 0x00, 0xc0, 0x4f, 0xc2, 0x97, 0xeb
};

static const guint8 expected_description[64] = {
  'T', 0, 'h', 0, 'i', 0, 's', 0, ' ', 0, 'i', 0, 's', 0, ' ', 0,
  't', 0, 'h', 0, 'e', 0, ' ', 0, 'd', 0, 'e', 0, 's', 0, 'c', 0,
  'r', 0, 'i', 0, 'p', 0, 't', 0, 'i', 0, 'o', 0, 'n', 0, ' ', 0,
  's', 0, 't', 0, 'r', 0, 'i', 0, 'n', 0, 'g', 0, '.', 0, 0, 0
};

GQuark
goodix_bb010002_error_quark (void)
{
  return g_quark_from_static_string ("goodix-bb010002-error");
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
is_all_zero (const guint8 *data,
             gsize         length)
{
  guint8 combined = 0;

  for (gsize i = 0; i < length; i++)
    combined |= data[i];
  return combined == 0u;
}

static gboolean
expect_u32 (const guint8 *data,
            gsize        *cursor,
            guint32       expected)
{
  if (*cursor > DPAPI_BLOB_LENGTH - 4u || read_le32 (data + *cursor) != expected)
    return FALSE;
  *cursor += 4u;
  return TRUE;
}

static gboolean
expect_bytes (const guint8 *data,
              gsize        *cursor,
              const guint8 *expected,
              gsize         length)
{
  if (*cursor > DPAPI_BLOB_LENGTH || length > DPAPI_BLOB_LENGTH - *cursor ||
      memcmp (data + *cursor, expected, length) != 0)
    return FALSE;
  *cursor += length;
  return TRUE;
}

static gboolean
skip_bytes (gsize *cursor,
            gsize  length)
{
  if (*cursor > DPAPI_BLOB_LENGTH || length > DPAPI_BLOB_LENGTH - *cursor)
    return FALSE;
  *cursor += length;
  return TRUE;
}

gboolean
goodix_bb010002_validate (const guint8        *data,
                          gsize                length,
                          GoodixBb010002Info *info,
                          GError             **error)
{
  GoodixBb010002Info result = { 0 };
  gsize cursor = 0;

  if (info != NULL)
    memset (info, 0, sizeof *info);
  g_return_val_if_fail (error == NULL || *error == NULL, FALSE);
  if (data == NULL || info == NULL)
    {
      g_set_error_literal (error, GOODIX_BB010002_ERROR,
                           GOODIX_BB010002_ERROR_ARGUMENT,
                           "invalid BB010002 argument");
      return FALSE;
    }
  if (length != GOODIX_BB010002_LENGTH)
    {
      g_set_error_literal (error, GOODIX_BB010002_ERROR,
                           GOODIX_BB010002_ERROR_LENGTH,
                           "BB010002 must be exactly 332 bytes");
      return FALSE;
    }

  result.blob_version = 1u;
  result.masterkey_version = 1u;
  result.flags = 4u;
  result.crypt_algorithm = 0x6610u;
  result.crypt_bits = 256u;
  result.hash_algorithm = 0x800eu;
  result.hash_bits = 512u;
  result.blob_length = DPAPI_BLOB_LENGTH;
  result.trailer_length = GOODIX_BB010002_LENGTH - DPAPI_BLOB_LENGTH;

  if (!expect_u32 (data, &cursor, result.blob_version) ||
      !expect_bytes (data, &cursor, dpapi_provider_guid,
                     sizeof dpapi_provider_guid) ||
      !expect_u32 (data, &cursor, result.masterkey_version) ||
      cursor > DPAPI_BLOB_LENGTH - 16u || is_all_zero (data + cursor, 16u) ||
      !skip_bytes (&cursor, 16u) ||
      !expect_u32 (data, &cursor, result.flags) ||
      !expect_u32 (data, &cursor, sizeof expected_description) ||
      !expect_bytes (data, &cursor, expected_description,
                     sizeof expected_description) ||
      !expect_u32 (data, &cursor, result.crypt_algorithm) ||
      !expect_u32 (data, &cursor, result.crypt_bits) ||
      !expect_u32 (data, &cursor, 32u) ||
      !skip_bytes (&cursor, 32u) ||
      !expect_u32 (data, &cursor, 0u) ||
      !expect_u32 (data, &cursor, result.hash_algorithm) ||
      !expect_u32 (data, &cursor, result.hash_bits) ||
      !expect_u32 (data, &cursor, 32u) ||
      !skip_bytes (&cursor, 32u) ||
      !expect_u32 (data, &cursor, 48u) ||
      !skip_bytes (&cursor, 48u) ||
      !expect_u32 (data, &cursor, 64u) ||
      !skip_bytes (&cursor, 64u) ||
      cursor != DPAPI_BLOB_LENGTH)
    {
      g_set_error_literal (error, GOODIX_BB010002_ERROR,
                           GOODIX_BB010002_ERROR_STRUCTURE,
                           "BB010002 DPAPI envelope structure mismatch");
      return FALSE;
    }

  *info = result;
  return TRUE;
}
