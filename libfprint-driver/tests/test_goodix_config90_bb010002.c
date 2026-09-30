/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "goodix_bb010002.h"
#include "goodix_config90.h"

#include <glib.h>
#include <string.h>

static const guint8 provider_guid[16] = {
  0xd0, 0x8c, 0x9d, 0xdf, 0x01, 0x15, 0xd1, 0x11,
  0x8c, 0x7a, 0x00, 0xc0, 0x4f, 0xc2, 0x97, 0xeb
};

static const guint8 description[64] = {
  'T', 0, 'h', 0, 'i', 0, 's', 0, ' ', 0, 'i', 0, 's', 0, ' ', 0,
  't', 0, 'h', 0, 'e', 0, ' ', 0, 'd', 0, 'e', 0, 's', 0, 'c', 0,
  'r', 0, 'i', 0, 'p', 0, 't', 0, 'i', 0, 'o', 0, 'n', 0, ' ', 0,
  's', 0, 't', 0, 'r', 0, 'i', 0, 'n', 0, 'g', 0, '.', 0, 0, 0
};

static guint8
crc8 (const guint8 *data,
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

static void
refresh_group_crcs (guint8 otp[GOODIX_CONFIG90_OTP_LENGTH])
{
  guint8 buffer[27] = { 0 };

  memcpy (buffer, otp, 11);
  memcpy (buffer + 11, otp + 36, 4);
  otp[60] = crc8 (buffer, 15);
  memcpy (buffer, otp + 11, 9);
  buffer[9] = otp[28];
  memcpy (buffer + 10, otp + 50, 4);
  memcpy (buffer + 14, otp + 56, 4);
  buffer[18] = otp[62];
  otp[61] = crc8 (buffer, 19);
  memcpy (buffer, otp + 20, 8);
  memcpy (buffer + 8, otp + 29, 7);
  memcpy (buffer + 15, otp + 40, 10);
  memcpy (buffer + 25, otp + 54, 2);
  otp[63] = crc8 (buffer, 27);
}

static void
make_otp (guint8 otp[GOODIX_CONFIG90_OTP_LENGTH])
{
  for (guint i = 0; i < GOODIX_CONFIG90_OTP_LENGTH; i++)
    otp[i] = (guint8) (i * 7u + 3u);
  otp[27] = 0x22u;
  otp[42] = 0x42u;
  otp[43] = 0xbdu;
  otp[45] = 0x42u;
  otp[50] = 0x21u;
  otp[51] = 0x31u;
  otp[52] = 0x41u;
  otp[53] = 0x51u;
  otp[62] = crc8 (otp + 50, 4);
  refresh_group_crcs (otp);
}

static guint16
read_le16 (const guint8 *data)
{
  return (guint16) data[0] | ((guint16) data[1] << 8);
}

static guint16
config_value (const guint8 config[GOODIX_CONFIG90_LENGTH],
              guint        section,
              guint16      reg)
{
  guint offset = config[2u * section + 1u];
  guint count = config[2u * section + 2u];

  for (guint i = 0; i < count; i += 4u)
    if (read_le16 (config + offset + i) == reg)
      return read_le16 (config + offset + i + 2u);
  g_assert_not_reached ();
}

static void
assert_finalizer (const guint8 config[GOODIX_CONFIG90_LENGTH])
{
  guint16 sum = 0xa5a5u;

  for (guint i = 0; i < GOODIX_CONFIG90_LENGTH; i += 2u)
    sum = (guint16) (sum + read_le16 (config + i));
  g_assert_cmpuint (sum, ==, 0u);
}

static void
test_config90_synthetic_kat (void)
{
  static const gchar expected_sha256[] =
    "3e52885163a9e5b15c7206ed41e2035aeea8051250ce90ccec391e5b53347276";
  guint8 otp[GOODIX_CONFIG90_OTP_LENGTH];
  guint8 output_a[GOODIX_CONFIG90_LENGTH] = { 0 };
  guint8 output_b[GOODIX_CONFIG90_LENGTH] = { 0 };
  GoodixConfig90Calibration calibration = { 0 };
  GError *error = NULL;
  gchar *digest;

  make_otp (otp);
  g_assert_true (goodix_config90_derive (0x2504u, otp, sizeof otp,
                                         output_a, &calibration, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (calibration.dac_registers[0], ==, 0x0218u);
  g_assert_cmpuint (calibration.dac_registers[1], ==, 0x0031u);
  g_assert_cmpuint (calibration.dac_registers[2], ==, 0x0041u);
  g_assert_cmpuint (calibration.dac_registers[3], ==, 0x0051u);
  g_assert_cmpuint (calibration.tcode, ==, 144u);
  g_assert_cmpuint (calibration.delta, ==, 14u);
  g_assert_cmpuint (calibration.fdt_offset, ==, 2u);
  g_assert_cmpuint (config_value (output_a, 0u, 0x0220u), ==, 0x0218u);
  g_assert_cmpuint (config_value (output_a, 0u, 0x005cu), ==, 144u);
  g_assert_cmpuint (config_value (output_a, 2u, 0x0082u) >> 8, ==, 14u);
  g_assert_cmpuint (config_value (output_a, 2u, 0x0056u) & 0xffu, ==, 6u);
  assert_finalizer (output_a);
  digest = g_compute_checksum_for_data (G_CHECKSUM_SHA256,
                                        output_a, sizeof output_a);
  g_assert_cmpstr (digest, ==, expected_sha256);
  g_free (digest);

  g_assert_true (goodix_config90_derive (0x2503u, otp, sizeof otp,
                                         output_b, &calibration, &error));
  g_assert_no_error (error);
  g_assert_cmpmem (output_a, sizeof output_a, output_b, sizeof output_b);
}

static void
assert_config_rejected (guint16       chip_id,
                        const guint8 *otp,
                        gsize         length)
{
  guint8 output[GOODIX_CONFIG90_LENGTH];
  GoodixConfig90Calibration calibration;
  GError *error = NULL;

  memset (output, 0xa5, sizeof output);
  memset (&calibration, 0xa5, sizeof calibration);
  g_assert_false (goodix_config90_derive (chip_id, otp, length, output,
                                          &calibration, &error));
  g_assert_nonnull (error);
  g_clear_error (&error);
  for (gsize i = 0; i < sizeof output; i++)
    g_assert_cmpuint (output[i], ==, 0u);
  g_assert_cmpmem (&calibration, sizeof calibration,
                   &(GoodixConfig90Calibration) { 0 }, sizeof calibration);
}

static void
test_config90_fail_closed (void)
{
  guint8 otp[GOODIX_CONFIG90_OTP_LENGTH];
  guint8 changed[GOODIX_CONFIG90_OTP_LENGTH];

  make_otp (otp);
  assert_config_rejected (0x2505u, otp, sizeof otp);
  assert_config_rejected (0x2504u, otp, sizeof otp - 1u);
  memcpy (changed, otp, sizeof changed);
  changed[0] ^= 1u;
  assert_config_rejected (0x2504u, changed, sizeof changed);
  memcpy (changed, otp, sizeof changed);
  changed[62] ^= 1u;
  refresh_group_crcs (changed);
  assert_config_rejected (0x2504u, changed, sizeof changed);
  memcpy (changed, otp, sizeof changed);
  changed[42] = 1u;
  changed[43] = 1u;
  changed[45] = 2u;
  refresh_group_crcs (changed);
  assert_config_rejected (0x2504u, changed, sizeof changed);
  memcpy (changed, otp, sizeof changed);
  changed[27] = 0x10u;
  refresh_group_crcs (changed);
  assert_config_rejected (0x2504u, changed, sizeof changed);
  assert_config_rejected (0x2504u, NULL, sizeof otp);
}

static void
put_u32 (guint8 *data,
         gsize  *cursor,
         guint32 value)
{
  data[(*cursor)++] = (guint8) value;
  data[(*cursor)++] = (guint8) (value >> 8);
  data[(*cursor)++] = (guint8) (value >> 16);
  data[(*cursor)++] = (guint8) (value >> 24);
}

static void
put_bytes (guint8       *data,
           gsize        *cursor,
           const guint8 *value,
           gsize         length)
{
  memcpy (data + *cursor, value, length);
  *cursor += length;
}

static void
put_pattern (guint8 *data,
             gsize  *cursor,
             gsize   length,
             guint8  seed)
{
  for (gsize i = 0; i < length; i++)
    data[(*cursor)++] = (guint8) (seed + (guint8) i);
}

static void
make_bb010002 (guint8 data[GOODIX_BB010002_LENGTH])
{
  gsize cursor = 0;

  memset (data, 0, GOODIX_BB010002_LENGTH);
  put_u32 (data, &cursor, 1u);
  put_bytes (data, &cursor, provider_guid, sizeof provider_guid);
  put_u32 (data, &cursor, 1u);
  put_pattern (data, &cursor, 16u, 0x31u);
  put_u32 (data, &cursor, 4u);
  put_u32 (data, &cursor, sizeof description);
  put_bytes (data, &cursor, description, sizeof description);
  put_u32 (data, &cursor, 0x6610u);
  put_u32 (data, &cursor, 256u);
  put_u32 (data, &cursor, 32u);
  put_pattern (data, &cursor, 32u, 0x51u);
  put_u32 (data, &cursor, 0u);
  put_u32 (data, &cursor, 0x800eu);
  put_u32 (data, &cursor, 512u);
  put_u32 (data, &cursor, 32u);
  put_pattern (data, &cursor, 32u, 0x71u);
  put_u32 (data, &cursor, 48u);
  put_pattern (data, &cursor, 48u, 0x91u);
  put_u32 (data, &cursor, 64u);
  put_pattern (data, &cursor, 64u, 0xb1u);
  g_assert_cmpuint (cursor, ==, 324u);
  put_pattern (data, &cursor, 8u, 0xf1u);
  g_assert_cmpuint (cursor, ==, GOODIX_BB010002_LENGTH);
}

static void
test_bb010002_synthetic_valid (void)
{
  guint8 data[GOODIX_BB010002_LENGTH];
  guint8 original[GOODIX_BB010002_LENGTH];
  GoodixBb010002Info info = { 0 };
  GError *error = NULL;

  make_bb010002 (data);
  memcpy (original, data, sizeof original);
  g_assert_true (goodix_bb010002_validate (data, sizeof data, &info, &error));
  g_assert_no_error (error);
  g_assert_cmpmem (data, sizeof data, original, sizeof original);
  g_assert_cmpuint (info.blob_version, ==, 1u);
  g_assert_cmpuint (info.masterkey_version, ==, 1u);
  g_assert_cmpuint (info.flags, ==, 4u);
  g_assert_cmpuint (info.crypt_algorithm, ==, 0x6610u);
  g_assert_cmpuint (info.crypt_bits, ==, 256u);
  g_assert_cmpuint (info.hash_algorithm, ==, 0x800eu);
  g_assert_cmpuint (info.hash_bits, ==, 512u);
  g_assert_cmpuint (info.blob_length, ==, 324u);
  g_assert_cmpuint (info.trailer_length, ==, 8u);

  memset (data + 324, 0, 8);
  g_assert_true (goodix_bb010002_validate (data, sizeof data, &info, &error));
  g_assert_no_error (error);
}

static void
assert_bb_rejected (const guint8 *data,
                    gsize         length)
{
  GoodixBb010002Info info;
  GError *error = NULL;

  memset (&info, 0xa5, sizeof info);
  g_assert_false (goodix_bb010002_validate (data, length, &info, &error));
  g_assert_nonnull (error);
  g_clear_error (&error);
  g_assert_cmpmem (&info, sizeof info,
                   &(GoodixBb010002Info) { 0 }, sizeof info);
}

static void
test_bb010002_fail_closed (void)
{
  static const gsize tag_offsets[] = {
    0u, 4u, 20u, 40u, 44u, 48u, 112u, 116u, 120u, 156u,
    160u, 164u, 168u, 204u, 256u
  };
  guint8 data[GOODIX_BB010002_LENGTH];
  guint8 changed[GOODIX_BB010002_LENGTH];

  make_bb010002 (data);
  assert_bb_rejected (NULL, sizeof data);
  assert_bb_rejected (data, sizeof data - 1u);
  assert_bb_rejected (data, sizeof data + 1u);
  for (guint i = 0; i < G_N_ELEMENTS (tag_offsets); i++)
    {
      memcpy (changed, data, sizeof changed);
      changed[tag_offsets[i]] ^= 1u;
      assert_bb_rejected (changed, sizeof changed);
    }
  memcpy (changed, data, sizeof changed);
  memset (changed + 24, 0, 16);
  assert_bb_rejected (changed, sizeof changed);

  /* Opaque protected regions and the trailer are not reinterpreted. */
  memcpy (changed, data, sizeof changed);
  changed[124] ^= 1u;
  changed[172] ^= 1u;
  changed[208] ^= 1u;
  changed[260] ^= 1u;
  changed[324] ^= 1u;
  {
    GoodixBb010002Info info = { 0 };
    GError *error = NULL;

    g_assert_true (goodix_bb010002_validate (changed, sizeof changed,
                                             &info, &error));
    g_assert_no_error (error);
  }
}

int
main (int argc,
      char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/goodix/config90/synthetic-kat", test_config90_synthetic_kat);
  g_test_add_func ("/goodix/config90/fail-closed", test_config90_fail_closed);
  g_test_add_func ("/goodix/bb010002/synthetic-valid", test_bb010002_synthetic_valid);
  g_test_add_func ("/goodix/bb010002/fail-closed", test_bb010002_fail_closed);
  return g_test_run ();
}
