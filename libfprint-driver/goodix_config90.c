/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Copyright (c) 2026 sorguido
 *
 * The type-12 template and OTP patch mapping are adapted from Rockytkg commit
 * 227eba219fa9e3fbac5bd59aca79f624f67cd11b, src/goodix_init.c and
 * src/goodix_otp.c (GPL-2.0-or-later).  This module deliberately exposes only
 * a pure, fixed-size, fail-closed ChicagoHS derivation.
 */
#include "goodix_config90.h"

#include <string.h>

static const guint8 type12_template[GOODIX_CONFIG90_LENGTH] = {
  0x70, 0x11, 0x74, 0x85, 0x00, 0x85, 0x2c, 0xb1, 0x18, 0xc9, 0x14, 0xdd, 0x00, 0xdd, 0x00, 0xdd,
  0x00, 0xba, 0x00, 0x01, 0x80, 0xca, 0x00, 0x04, 0x00, 0x84, 0x00, 0x15, 0xb3, 0x86, 0x00, 0x00,
  0xc4, 0x88, 0x00, 0x00, 0xba, 0x8a, 0x00, 0x00, 0xb2, 0x8c, 0x00, 0x00, 0xaa, 0x8e, 0x00, 0x00,
  0xc1, 0x90, 0x00, 0xbb, 0xbb, 0x92, 0x00, 0xb1, 0xb1, 0x94, 0x00, 0x00, 0xa8, 0x96, 0x00, 0x00,
  0xb6, 0x98, 0x00, 0x00, 0x00, 0x9a, 0x00, 0x00, 0x00, 0xd2, 0x00, 0x00, 0x00, 0xd4, 0x00, 0x00,
  0x00, 0xd6, 0x00, 0x00, 0x00, 0xd8, 0x00, 0x00, 0x00, 0x50, 0x00, 0x01, 0x05, 0xd0, 0x00, 0x00,
  0x00, 0x70, 0x00, 0x00, 0x00, 0x72, 0x00, 0x78, 0x56, 0x74, 0x00, 0x34, 0x12, 0x20, 0x00, 0x10,
  0x40, 0x5c, 0x00, 0x80, 0x01, 0x20, 0x02, 0x08, 0x08, 0x36, 0x02, 0x80, 0x00, 0x38, 0x02, 0x80,
  0x00, 0x3a, 0x02, 0x80, 0x00, 0x2a, 0x01, 0x82, 0x03, 0x22, 0x00, 0x01, 0x20, 0x24, 0x00, 0x14,
  0x00, 0x80, 0x00, 0x01, 0x00, 0x5c, 0x00, 0x00, 0x01, 0x56, 0x00, 0x04, 0x20, 0x58, 0x00, 0x03,
  0x02, 0x32, 0x00, 0x0c, 0x02, 0x66, 0x00, 0x03, 0x00, 0x7c, 0x00, 0x00, 0x58, 0x82, 0x00, 0x80,
  0x15, 0x2a, 0x01, 0x08, 0x00, 0x54, 0x00, 0x10, 0x01, 0x62, 0x00, 0x04, 0x03, 0x64, 0x00, 0x19,
  0x00, 0x66, 0x00, 0x03, 0x00, 0x7c, 0x00, 0x00, 0x58, 0x2a, 0x01, 0x08, 0x00, 0x52, 0x00, 0x08,
  0x00, 0x54, 0x00, 0x00, 0x01, 0x66, 0x00, 0x03, 0x00, 0x7c, 0x00, 0x00, 0x58, 0x00, 0x00, 0x00,
};

GQuark
goodix_config90_error_quark (void)
{
  return g_quark_from_static_string ("goodix-config90-error");
}

static guint8
otp_crc8 (const guint8 *data,
          gsize         length)
{
  guint8 crc = 0;

  for (gsize i = 0; i < length; i++)
    {
      crc ^= data[i];
      for (guint bit = 0; bit < 8; bit++)
        {
          guint shifted = (guint) crc << 1;

          crc = (guint8) ((crc & 0x80u) != 0u ?
                            shifted ^ 0x07u : shifted);
        }
    }
  return (guint8) ~crc;
}

static gboolean
validate_group_crcs (const guint8 otp[GOODIX_CONFIG90_OTP_LENGTH])
{
  guint8 buffer[27] = { 0 };

  memcpy (buffer, otp, 11);
  memcpy (buffer + 11, otp + 36, 4);
  if (otp_crc8 (buffer, 15) != otp[60])
    return FALSE;

  memcpy (buffer, otp + 11, 9);
  buffer[9] = otp[28];
  memcpy (buffer + 10, otp + 50, 4);
  memcpy (buffer + 14, otp + 56, 4);
  buffer[18] = otp[62];
  if (otp_crc8 (buffer, 19) != otp[61])
    return FALSE;

  memcpy (buffer, otp + 20, 8);
  memcpy (buffer + 8, otp + 29, 7);
  memcpy (buffer + 15, otp + 40, 10);
  memcpy (buffer + 25, otp + 54, 2);
  return otp_crc8 (buffer, 27) == otp[63];
}

static guint16
read_le16 (const guint8 *data)
{
  return (guint16) data[0] | ((guint16) data[1] << 8);
}

static gboolean
patch_unique (guint8  config[GOODIX_CONFIG90_LENGTH],
              guint   section,
              guint16 reg,
              guint16 value,
              guint   byte_mode)
{
  guint offset;
  guint count;
  guint match = G_MAXUINT;

  if (section > 7u)
    return FALSE;
  offset = config[2u * section + 1u];
  count = config[2u * section + 2u];
  if (count == 0u || count % 4u != 0u ||
      offset > GOODIX_CONFIG90_LENGTH ||
      count > GOODIX_CONFIG90_LENGTH - offset)
    return FALSE;
  for (guint i = 0; i < count; i += 4u)
    if (read_le16 (config + offset + i) == reg)
      {
        if (match != G_MAXUINT)
          return FALSE;
        match = offset + i + 2u;
      }
  if (match == G_MAXUINT)
    return FALSE;

  if (byte_mode == 0u || byte_mode == 1u)
    config[match] = (guint8) value;
  if (byte_mode == 0u || byte_mode == 2u)
    config[match + 1u] = (guint8) (value >> 8);
  return TRUE;
}

static void
fix_finalizer (guint8 config[GOODIX_CONFIG90_LENGTH])
{
  guint16 sum = 0xa5a5u;

  for (guint i = 0; i < 111u; i++)
    sum = (guint16) (sum + read_le16 (config + 2u * i));
  sum = (guint16) (0u - sum);
  config[222] = (guint8) sum;
  config[223] = (guint8) (sum >> 8);
}

static gboolean
decode_fdt_offset (guint8  encoded,
                   guint8 *offset)
{
  guint8 low;
  guint8 high;
  guint8 inverted;

  if (encoded == 0u)
    {
      *offset = 0u;
      return TRUE;
    }
  low = encoded & 3u;
  high = (encoded >> 4) & 3u;
  inverted = ((guint8) ~encoded >> 2) & 3u;
  if (low == high || low == inverted)
    *offset = low;
  else if (high == inverted)
    *offset = high;
  else
    return FALSE;
  return TRUE;
}

gboolean
goodix_config90_derive (guint16                    chip_id,
                        const guint8              *otp,
                        gsize                      otp_length,
                        guint8                     output[GOODIX_CONFIG90_LENGTH],
                        GoodixConfig90Calibration *calibration,
                        GError                   **error)
{
  GoodixConfig90Calibration result = { 0 };
  guint8 candidate[GOODIX_CONFIG90_LENGTH] = { 0 };
  guint8 dac[4] = { 0 };
  guint8 tcode_diff = 0;

  if (output != NULL)
    memset (output, 0, GOODIX_CONFIG90_LENGTH);
  if (calibration != NULL)
    memset (calibration, 0, sizeof *calibration);
  g_return_val_if_fail (error == NULL || *error == NULL, FALSE);
  if (otp == NULL || output == NULL || calibration == NULL)
    {
      g_set_error_literal (error, GOODIX_CONFIG90_ERROR,
                           GOODIX_CONFIG90_ERROR_ARGUMENT,
                           "invalid CONFIG90 argument");
      return FALSE;
    }
  if (chip_id != 0x2503u && chip_id != 0x2504u)
    {
      g_set_error_literal (error, GOODIX_CONFIG90_ERROR,
                           GOODIX_CONFIG90_ERROR_PROFILE,
                           "unsupported CONFIG90 chip/profile");
      return FALSE;
    }
  if (otp_length != GOODIX_CONFIG90_OTP_LENGTH ||
      !validate_group_crcs (otp))
    {
      g_set_error_literal (error, GOODIX_CONFIG90_ERROR,
                           GOODIX_CONFIG90_ERROR_OTP,
                           "malformed OTP or group CRC mismatch");
      return FALSE;
    }
  if (otp[50] == 0u || otp[51] == 0u || otp[52] == 0u || otp[53] == 0u ||
      otp_crc8 (otp + 50, 4) != otp[62])
    {
      g_set_error_literal (error, GOODIX_CONFIG90_ERROR,
                           GOODIX_CONFIG90_ERROR_OTP,
                           "invalid factory-test DAC calibration");
      return FALSE;
    }
  memcpy (dac, otp + 50, sizeof dac);

  if (otp[42] != 0u && otp[42] == (guint8) ~otp[43])
    tcode_diff = otp[42];
  else if (otp[45] != 0u && otp[45] == (guint8) ~otp[43])
    tcode_diff = otp[45];
  else if (otp[42] != 0u && otp[45] == otp[42])
    tcode_diff = otp[42];
  else
    {
      g_set_error_literal (error, GOODIX_CONFIG90_ERROR,
                           GOODIX_CONFIG90_ERROR_OTP,
                           "ambiguous OTP tcode calibration");
      return FALSE;
    }
  if (!decode_fdt_offset (otp[27], &result.fdt_offset))
    {
      g_set_error_literal (error, GOODIX_CONFIG90_ERROR,
                           GOODIX_CONFIG90_ERROR_OTP,
                           "ambiguous OTP FDT offset");
      return FALSE;
    }

  result.dac_registers[0] = (guint16) (16u * dac[0] | 8u);
  result.dac_registers[1] = dac[1];
  result.dac_registers[2] = dac[2];
  result.dac_registers[3] = dac[3];
  result.tcode = (guint16) (16u * (((tcode_diff >> 4) & 0x0fu) + 1u) + 64u);
  result.delta = (guint8) (((100u * ((tcode_diff & 0x0fu) + 2u) << 8) /
                            result.tcode / 3u) >> 4);

  memcpy (candidate, type12_template, sizeof candidate);
  if (!patch_unique (candidate, 0u, 0x0220u, result.dac_registers[0], 0u) ||
      !patch_unique (candidate, 0u, 0x0236u, result.dac_registers[1], 0u) ||
      !patch_unique (candidate, 0u, 0x0238u, result.dac_registers[2], 0u) ||
      !patch_unique (candidate, 0u, 0x023au, result.dac_registers[3], 0u) ||
      !patch_unique (candidate, 0u, 0x005cu, result.tcode, 0u) ||
      !patch_unique (candidate, 2u, 0x0082u,
                     (guint16) ((guint16) result.delta << 8), 2u) ||
      (result.fdt_offset != 0u &&
       !patch_unique (candidate, 2u, 0x0056u,
                      (guint16) result.fdt_offset + 4u, 1u)))
    {
      g_set_error_literal (error, GOODIX_CONFIG90_ERROR,
                           GOODIX_CONFIG90_ERROR_TEMPLATE,
                           "type-12 template structure mismatch");
      return FALSE;
    }
  fix_finalizer (candidate);
  memcpy (output, candidate, sizeof candidate);
  *calibration = result;
  return TRUE;
}
