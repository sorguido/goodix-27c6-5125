/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_a0_protocol.h"
#include "goodix_live_preflight.h"

#include <glib.h>
#include <string.h>

static const guint8 provider_guid[16] = {
  0xd0, 0x8c, 0x9d, 0xdf, 0x01, 0x15, 0xd1, 0x11,
  0x8c, 0x7a, 0x00, 0xc0, 0x4f, 0xc2, 0x97, 0xeb
};

static guint8
crc8 (const guint8 *data,
      gsize length)
{
  guint8 crc = 0;
  for (gsize i = 0; i < length; i++)
    {
      crc ^= data[i];
      for (guint bit = 0; bit < 8; bit++)
        crc = (guint8) ((crc & 0x80u) != 0u ?
                        ((guint) crc << 1) ^ 0x07u : (guint) crc << 1);
    }
  return (guint8) ~crc;
}

static void
make_otp (guint8 otp[GOODIX_CONFIG90_OTP_LENGTH])
{
  guint8 group[27] = { 0 };
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
  memcpy (group, otp, 11);
  memcpy (group + 11, otp + 36, 4);
  otp[60] = crc8 (group, 15);
  memcpy (group, otp + 11, 9);
  group[9] = otp[28];
  memcpy (group + 10, otp + 50, 4);
  memcpy (group + 14, otp + 56, 4);
  group[18] = otp[62];
  otp[61] = crc8 (group, 19);
  memcpy (group, otp + 20, 8);
  memcpy (group + 8, otp + 29, 7);
  memcpy (group + 15, otp + 40, 10);
  memcpy (group + 25, otp + 54, 2);
  otp[63] = crc8 (group, 27);
}

static void
put_u32 (guint8 *data,
         gsize *cursor,
         guint32 value)
{
  data[(*cursor)++] = (guint8) value;
  data[(*cursor)++] = (guint8) (value >> 8);
  data[(*cursor)++] = (guint8) (value >> 16);
  data[(*cursor)++] = (guint8) (value >> 24);
}

static void
put_pattern (guint8 *data,
             gsize *cursor,
             gsize length,
             guint8 seed)
{
  for (gsize i = 0; i < length; i++)
    data[(*cursor)++] = (guint8) (seed + (guint8) i);
}

static void
make_bb010002 (guint8 data[GOODIX_BB010002_LENGTH])
{
  static const guint8 description[64] = {
    'T', 0, 'h', 0, 'i', 0, 's', 0, ' ', 0, 'i', 0, 's', 0, ' ', 0,
    't', 0, 'h', 0, 'e', 0, ' ', 0, 'd', 0, 'e', 0, 's', 0, 'c', 0,
    'r', 0, 'i', 0, 'p', 0, 't', 0, 'i', 0, 'o', 0, 'n', 0, ' ', 0,
    's', 0, 't', 0, 'r', 0, 'i', 0, 'n', 0, 'g', 0, '.', 0, 0, 0
  };
  gsize cursor = 0;

  memset (data, 0, GOODIX_BB010002_LENGTH);
  put_u32 (data, &cursor, 1u);
  memcpy (data + cursor, provider_guid, sizeof provider_guid);
  cursor += sizeof provider_guid;
  put_u32 (data, &cursor, 1u);
  put_pattern (data, &cursor, 16u, 0x31u);
  put_u32 (data, &cursor, 4u);
  put_u32 (data, &cursor, sizeof description);
  memcpy (data + cursor, description, sizeof description);
  cursor += sizeof description;
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
  put_pattern (data, &cursor, 8u, 0xf1u);
  g_assert_cmpuint (cursor, ==, GOODIX_BB010002_LENGTH);
}

static GBytes *
frame (guint8 control,
       const guint8 *body,
       gsize length)
{
  return goodix_a0_build_frame (control, control, body, length, NULL);
}

static void
put_le32 (guint8 out[4],
          guint32 value)
{
  out[0] = (guint8) value;
  out[1] = (guint8) (value >> 8);
  out[2] = (guint8) (value >> 16);
  out[3] = (guint8) (value >> 24);
}

static void
complete_phase (GoodixLivePreflight *preflight,
                const guint8        *typed_body,
                gsize                typed_length,
                gboolean             response_before_out)
{
  g_autoptr(GBytes) request = goodix_live_preflight_next_request (preflight, NULL);
  const guint8 *request_data = g_bytes_get_data (request, NULL);
  guint8 ack_body[] = { request_data[4], 0x01 };
  g_autoptr(GBytes) ack = frame (0xb0, ack_body, sizeof ack_body);
  g_autoptr(GBytes) typed = frame (request_data[4], typed_body, typed_length);

  if (!response_before_out)
    goodix_live_preflight_out_complete (preflight, NULL);
  g_assert_true (goodix_live_preflight_handle_a0 (preflight, ack, NULL));
  g_assert_true (goodix_live_preflight_handle_a0 (preflight, typed, NULL));
  if (response_before_out)
    goodix_live_preflight_out_complete (preflight, NULL);
}

static void
test_complete_read_only_graph (void)
{
  static const guint8 a2[] = { 0x00, 0x00, 0x00 };
  static const guint8 app[] = "GF_ST411SEC_APP_12509";
  static const guint8 chip[] = { 0x00, 0x04, 0x25, 0x00 };
  guint8 bb2[GOODIX_BB010002_LENGTH];
  guint8 validator[32];
  guint8 otp[GOODIX_CONFIG90_OTP_LENGTH];
  guint8 e4_bb2[9 + GOODIX_BB010002_LENGTH] = { 0 };
  guint8 e4_validator[9 + sizeof validator] = { 0 };
  GoodixLivePreflightAudit audit = { 0 };
  GoodixLivePreflightEvidence evidence = { 0 };
  g_autoptr(GoodixLivePreflight) preflight = goodix_live_preflight_new (&audit);

  make_bb010002 (bb2);
  memset (validator, 0xa5, sizeof validator);
  make_otp (otp);
  put_le32 (e4_bb2 + 1, 0xbb010002u);
  put_le32 (e4_bb2 + 5, sizeof bb2);
  memcpy (e4_bb2 + 9, bb2, sizeof bb2);
  put_le32 (e4_validator + 1, 0xbb020003u);
  put_le32 (e4_validator + 5, sizeof validator);
  memcpy (e4_validator + 9, validator, sizeof validator);

  complete_phase (preflight, a2, sizeof a2, FALSE);
  complete_phase (preflight, app, sizeof app, TRUE);
  complete_phase (preflight, e4_bb2, sizeof e4_bb2, FALSE);
  complete_phase (preflight, e4_validator, sizeof e4_validator, FALSE);
  complete_phase (preflight, a2, sizeof a2, FALSE);
  complete_phase (preflight, chip, sizeof chip, FALSE);
  complete_phase (preflight, otp, sizeof otp, FALSE);

  g_assert_cmpint (goodix_live_preflight_get_phase (preflight), ==,
                   GOODIX_LIVE_PREFLIGHT_STOP);
  g_assert_true (goodix_live_preflight_copy_evidence (preflight, &evidence));
  g_assert_cmpuint (evidence.chip_id, ==, 0x2504u);
  g_assert_cmpmem (evidence.bb010002, sizeof evidence.bb010002,
                   bb2, sizeof bb2);
  g_assert_cmpmem (evidence.validator, sizeof evidence.validator,
                   validator, sizeof validator);
  g_assert_cmpmem (evidence.otp, sizeof evidence.otp, otp, sizeof otp);
  g_assert_cmpuint (audit.command_count, ==, 7u);
  g_assert_cmpuint (audit.ack_count, ==, 7u);
  g_assert_cmpuint (audit.typed_response_count, ==, 7u);
  g_assert_cmpuint (audit.retry_count, ==, 0u);
  g_assert_cmpuint (audit.persistent_write_count, ==, 0u);
  g_assert_true (audit.exact_app);
  g_assert_true (audit.supported_chip_profile);
  g_assert_true (audit.otp_valid);
  g_assert_true (audit.bb010002_valid);
  g_assert_true (audit.config90_derived);
  g_assert_true (audit.complete);
}

static void
test_unsupported_chip_fails_closed (void)
{
  static const guint8 a2[] = { 0x00, 0x00, 0x00 };
  static const guint8 app[] = "GF_ST411SEC_APP_12509";
  static const guint8 chip[] = { 0x00, 0x05, 0x25, 0x00 };
  guint8 bb2[GOODIX_BB010002_LENGTH];
  guint8 validator[32] = { 0 };
  guint8 e4_bb2[9 + GOODIX_BB010002_LENGTH] = { 0 };
  guint8 e4_validator[9 + sizeof validator] = { 0 };
  g_autoptr(GoodixLivePreflight) preflight = goodix_live_preflight_new (NULL);
  g_autoptr(GBytes) request = NULL;
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GBytes) typed = NULL;
  guint8 ack_body[2];

  make_bb010002 (bb2);
  put_le32 (e4_bb2 + 1, 0xbb010002u);
  put_le32 (e4_bb2 + 5, sizeof bb2);
  memcpy (e4_bb2 + 9, bb2, sizeof bb2);
  put_le32 (e4_validator + 1, 0xbb020003u);
  put_le32 (e4_validator + 5, sizeof validator);
  memcpy (e4_validator + 9, validator, sizeof validator);
  complete_phase (preflight, a2, sizeof a2, FALSE);
  complete_phase (preflight, app, sizeof app, FALSE);
  complete_phase (preflight, e4_bb2, sizeof e4_bb2, FALSE);
  complete_phase (preflight, e4_validator, sizeof e4_validator, FALSE);
  complete_phase (preflight, a2, sizeof a2, FALSE);

  request = goodix_live_preflight_next_request (preflight, NULL);
  g_assert_nonnull (request);
  ack_body[0] = 0x82;
  ack_body[1] = 0x01;
  ack = frame (0xb0, ack_body, sizeof ack_body);
  typed = frame (0x82, chip, sizeof chip);
  goodix_live_preflight_out_complete (preflight, NULL);
  g_assert_true (goodix_live_preflight_handle_a0 (preflight, ack, NULL));
  g_assert_false (goodix_live_preflight_handle_a0 (preflight, typed, NULL));
  g_assert_cmpint (goodix_live_preflight_get_phase (preflight), ==,
                   GOODIX_LIVE_PREFLIGHT_TERMINAL);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/goodix/live-preflight/complete",
                   test_complete_read_only_graph);
  g_test_add_func ("/goodix/live-preflight/unsupported-chip",
                   test_unsupported_chip_fails_closed);
  return g_test_run ();
}
