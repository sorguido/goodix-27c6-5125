/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "goodix_a0_protocol.h"
#include "goodix_pairing_provision.h"

#include <glib.h>
#include <string.h>

static const guint8 provider_guid[16] = {
  0xd0, 0x8c, 0x9d, 0xdf, 0x01, 0x15, 0xd1, 0x11,
  0x8c, 0x7a, 0x00, 0xc0, 0x4f, 0xc2, 0x97, 0xeb
};

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
put_pattern (guint8 *data,
             gsize  *cursor,
             gsize   length,
             guint8  seed)
{
  for (gsize i = 0; i < length; i++)
    data[(*cursor)++] = (guint8) (seed + (guint8) i);
}

static void
make_bb010002 (guint8 data[GOODIX_PAIRING_PROVISION_BB010002_LENGTH])
{
  static const guint8 description[64] = {
    'T', 0, 'h', 0, 'i', 0, 's', 0, ' ', 0, 'i', 0, 's', 0, ' ', 0,
    't', 0, 'h', 0, 'e', 0, ' ', 0, 'd', 0, 'e', 0, 's', 0, 'c', 0,
    'r', 0, 'i', 0, 'p', 0, 't', 0, 'i', 0, 'o', 0, 'n', 0, ' ', 0,
    's', 0, 't', 0, 'r', 0, 'i', 0, 'n', 0, 'g', 0, '.', 0, 0, 0
  };
  gsize cursor = 0;

  memset (data, 0, GOODIX_PAIRING_PROVISION_BB010002_LENGTH);
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
  g_assert_cmpuint (cursor, ==,
                    GOODIX_PAIRING_PROVISION_BB010002_LENGTH);
}

static GBytes *
response (guint8 control,
          const guint8 *body,
          gsize length)
{
  return goodix_a0_build_frame (control, control, body, length, NULL);
}

static GoodixPairingProvision *
fixture (guint8 bb2[GOODIX_PAIRING_PROVISION_BB010002_LENGTH],
         guint8 wb[GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH],
         guint8 validator[GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH],
         GoodixPairingProvisionAudit *audit)
{
  make_bb010002 (bb2);
  memset (wb, 0x33, GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH);
  memset (validator, 0x44, GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH);
  return goodix_pairing_provision_new (
    bb2, GOODIX_PAIRING_PROVISION_BB010002_LENGTH,
    wb, GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH,
    validator, GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH,
    audit, NULL);
}

static void
test_happy_path_and_exact_frame (void)
{
  guint8 bb2[GOODIX_PAIRING_PROVISION_BB010002_LENGTH];
  guint8 wb[GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH];
  guint8 validator[GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH];
  const guint8 ack_body[] = { 0xe0, 0x01 };
  const guint8 done_body[] = { 0x00, 0x03 };
  GoodixPairingProvisionAudit audit = { 0 };
  g_autoptr(GoodixPairingProvision) provision = NULL;
  g_autoptr(GBytes) e0 = NULL;
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GBytes) done = NULL;
  const guint8 *data;
  gsize length;

  provision = fixture (bb2, wb, validator, &audit);
  g_assert_nonnull (provision);
  e0 = goodix_pairing_provision_begin_e0 (provision, NULL);
  g_assert_nonnull (e0);
  data = g_bytes_get_data (e0, &length);
  g_assert_cmpuint (length, ==, GOODIX_PAIRING_PROVISION_E0_FRAME_LENGTH);
  g_assert_cmphex (data[0], ==, 0xa0);
  g_assert_cmphex (data[1], ==, 0xc8);
  g_assert_cmphex (data[2], ==, 0x01);
  g_assert_cmphex (data[3], ==, 0x69);
  g_assert_cmphex (data[4], ==, 0xe0);
  g_assert_cmphex (data[5], ==, 0xc5);
  g_assert_cmphex (data[6], ==, 0x01);
  g_assert_cmphex (data[7], ==, 0x02);
  g_assert_cmphex (data[8], ==, 0x00);
  g_assert_cmphex (data[9], ==, 0x01);
  g_assert_cmphex (data[10], ==, 0xbb);
  g_assert_cmphex (data[11], ==, 0x4c);
  g_assert_cmphex (data[12], ==, 0x01);
  g_assert_cmphex (data[13], ==, 0x00);
  g_assert_cmphex (data[14], ==, 0x00);
  g_assert_cmpmem (data + 15, sizeof bb2, bb2, sizeof bb2);
  g_assert_cmphex (data[347], ==, 0x03);
  g_assert_cmphex (data[348], ==, 0x00);
  g_assert_cmphex (data[349], ==, 0x01);
  g_assert_cmphex (data[350], ==, 0xbb);
  g_assert_cmphex (data[351], ==, 102);
  g_assert_cmpmem (data + 355, sizeof wb, wb, sizeof wb);
  g_assert_cmphex (data[457], ==, 0x00);
  g_assert_cmphex (data[458], ==, 0x00);

  ack = response (0xb0, ack_body, sizeof ack_body);
  done = response (0xe2, done_body, sizeof done_body);
  g_assert_true (goodix_pairing_provision_handle_a0 (provision, ack, NULL));
  g_assert_true (goodix_pairing_provision_handle_a0 (provision, done, NULL));
  g_assert_true (goodix_pairing_provision_check_readback (
    provision, bb2, sizeof bb2, validator, sizeof validator, NULL));
  g_assert_true (goodix_pairing_provision_mark_tls_proven (provision, NULL));
  g_assert_true (goodix_pairing_provision_is_complete (provision));
  g_assert_cmpuint (audit.logical_e0_count, ==, 1u);
  g_assert_cmpuint (audit.persistent_write_count, ==, 1u);
  g_assert_cmpuint (audit.retry_count, ==, 0u);
  g_assert_true (audit.bb010002_unchanged);
  g_assert_true (audit.validator_match);
  g_assert_true (audit.tls_proven);
}

static void
test_second_e0_is_rejected (void)
{
  guint8 bb2[GOODIX_PAIRING_PROVISION_BB010002_LENGTH];
  guint8 wb[GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH];
  guint8 validator[GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH];
  GoodixPairingProvisionAudit audit = { 0 };
  g_autoptr(GoodixPairingProvision) provision =
    fixture (bb2, wb, validator, &audit);
  g_autoptr(GBytes) first = goodix_pairing_provision_begin_e0 (provision, NULL);
  g_autoptr(GError) error = NULL;

  g_assert_nonnull (first);
  g_assert_null (goodix_pairing_provision_begin_e0 (provision, &error));
  g_assert_error (error, GOODIX_PAIRING_PROVISION_ERROR,
                  GOODIX_PAIRING_PROVISION_ERROR_STATE);
  g_assert_cmpint (goodix_pairing_provision_get_terminal (provision), ==,
                   GOODIX_PAIRING_PROVISION_REJECTED);
  g_assert_cmpuint (audit.logical_e0_count, ==, 1u);
  g_assert_cmpuint (audit.retry_count, ==, 1u);
}

static void
test_result_before_ack_fails_closed (void)
{
  guint8 bb2[GOODIX_PAIRING_PROVISION_BB010002_LENGTH];
  guint8 wb[GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH];
  guint8 validator[GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH];
  const guint8 body[] = { 0x00, 0x02 };
  g_autoptr(GoodixPairingProvision) provision =
    fixture (bb2, wb, validator, NULL);
  g_autoptr(GBytes) e0 = goodix_pairing_provision_begin_e0 (provision, NULL);
  g_autoptr(GBytes) done = response (0xe0, body, sizeof body);

  g_assert_false (goodix_pairing_provision_handle_a0 (provision, done, NULL));
  g_assert_cmpint (goodix_pairing_provision_get_terminal (provision), ==,
                   GOODIX_PAIRING_PROVISION_REJECTED);
}

static void
test_readback_mismatch_fails_closed (void)
{
  guint8 bb2[GOODIX_PAIRING_PROVISION_BB010002_LENGTH];
  guint8 wb[GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH];
  guint8 validator[GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH];
  const guint8 ack_body[] = { 0xe0, 0x07 };
  const guint8 done_body[] = { 0x00, 0x02 };
  g_autoptr(GoodixPairingProvision) provision =
    fixture (bb2, wb, validator, NULL);
  g_autoptr(GBytes) e0 = goodix_pairing_provision_begin_e0 (provision, NULL);
  g_autoptr(GBytes) ack = response (0xb0, ack_body, sizeof ack_body);
  g_autoptr(GBytes) done = response (0xe0, done_body, sizeof done_body);

  g_assert_true (goodix_pairing_provision_handle_a0 (provision, ack, NULL));
  g_assert_true (goodix_pairing_provision_handle_a0 (provision, done, NULL));
  bb2[7] ^= 1u;
  g_assert_false (goodix_pairing_provision_check_readback (
    provision, bb2, sizeof bb2, validator, sizeof validator, NULL));
  g_assert_cmpint (goodix_pairing_provision_get_terminal (provision), ==,
                   GOODIX_PAIRING_PROVISION_REJECTED);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/goodix/pairing-provision/happy",
                   test_happy_path_and_exact_frame);
  g_test_add_func ("/goodix/pairing-provision/one-shot",
                   test_second_e0_is_rejected);
  g_test_add_func ("/goodix/pairing-provision/result-before-ack",
                   test_result_before_ack_fails_closed);
  g_test_add_func ("/goodix/pairing-provision/readback-mismatch",
                   test_readback_mismatch_fails_closed);
  return g_test_run ();
}
