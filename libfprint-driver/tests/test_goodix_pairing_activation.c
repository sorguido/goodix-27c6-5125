/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_a0_protocol.h"
#include "goodix_pairing_activation.h"
#include "goodix_pairing_crypto.h"

#include <glib.h>
#include <glib/gstdio.h>
#include <string.h>
#include <unistd.h>

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

static GoodixLivePreflightEvidence
evidence_fixture (void)
{
  GoodixLivePreflightEvidence evidence = { 0 };

  evidence.chip_id = 0x2504u;
  evidence.a2_response[0] = 0x11u;
  evidence.a2_response[1] = 0x22u;
  evidence.a2_response[2] = 0x33u;
  evidence.chip_response[0] = 0x82u;
  evidence.chip_response[1] = 0x04u;
  evidence.chip_response[2] = 0x25u;
  evidence.chip_response[3] = 0x7eu;
  for (guint i = 0; i < sizeof evidence.otp; i++)
    evidence.otp[i] = (guint8) (i + 1u);
  for (guint i = 0; i < sizeof evidence.config90; i++)
    evidence.config90[i] = (guint8) (0xa5u ^ i);
  for (guint i = 0; i < sizeof evidence.validator; i++)
    evidence.validator[i] = (guint8) (0x70u + i);
  for (guint i = 0;
       i < G_N_ELEMENTS (evidence.calibration.dac_registers); i++)
    evidence.calibration.dac_registers[i] = (guint16) (0x0200u + i);
  make_bb010002 (evidence.bb010002);
  return evidence;
}

static GBytes *
response (guint8 control,
          const guint8 *body,
          gsize length)
{
  return goodix_a0_build_frame (control, control, body, length, NULL);
}

static GBytes *
e4_response (guint32 type,
             const guint8 *payload,
             gsize payload_length)
{
  g_autofree guint8 *body = g_malloc0 (9u + payload_length);
  gsize cursor = 1u;

  put_u32 (body, &cursor, type);
  put_u32 (body, &cursor, (guint32) payload_length);
  memcpy (body + cursor, payload, payload_length);
  return response (0xe4u, body, 9u + payload_length);
}

static gchar *
new_state_directory (void)
{
  gchar *directory = g_dir_make_tmp ("goodix-pairing-activation.XXXXXX", NULL);

  g_assert_nonnull (directory);
  g_assert_cmpint (g_chmod (directory, 0700), ==, 0);
  return directory;
}

static void
remove_state_directory (const gchar *directory)
{
  GDir *dir = g_dir_open (directory, 0, NULL);
  const gchar *name;

  g_assert_nonnull (dir);
  while ((name = g_dir_read_name (dir)) != NULL)
    {
      g_autofree gchar *path = g_build_filename (directory, name, NULL);
      g_assert_cmpint (g_unlink (path), ==, 0);
    }
  g_dir_close (dir);
  g_assert_cmpint (g_rmdir (directory), ==, 0);
}

static void
feed_successful_write_and_readback (GoodixPairingActivation *activation,
                                    const guint8             validator[32])
{
  const guint8 e0_ack_body[] = { 0xe0u, 0x01u };
  const guint8 e0_done_body[] = { 0x00u, 0x03u };
  const guint8 e4_ack_body[] = { 0xe4u, 0x01u };
  g_autoptr(GBytes) request = NULL;
  g_autoptr(GBytes) e0_ack = response (0xb0u, e0_ack_body,
                                       sizeof e0_ack_body);
  g_autoptr(GBytes) e0_done = response (0xe0u, e0_done_body,
                                        sizeof e0_done_body);
  g_autoptr(GBytes) e4_ack = response (0xb0u, e4_ack_body,
                                       sizeof e4_ack_body);
  g_autoptr(GBytes) typed = NULL;

  request = goodix_pairing_activation_next_request (activation, NULL);
  g_assert_nonnull (request);
  g_assert_cmpuint (g_bytes_get_size (request), ==,
                    GOODIX_PAIRING_PROVISION_E0_FRAME_LENGTH);
  goodix_pairing_activation_out_complete (activation, NULL);
  g_assert_true (goodix_pairing_activation_handle_a0 (activation, e0_ack,
                                                       NULL));
  g_assert_true (goodix_pairing_activation_handle_a0 (activation, e0_done,
                                                       NULL));
  g_clear_pointer (&request, g_bytes_unref);

  request = goodix_pairing_activation_next_request (activation, NULL);
  g_assert_nonnull (request);
  goodix_pairing_activation_out_complete (activation, NULL);
  g_assert_true (goodix_pairing_activation_handle_a0 (activation, e4_ack,
                                                       NULL));
  typed = e4_response (0xbb010002u,
                       ((GoodixLivePreflightEvidence) evidence_fixture ()).bb010002,
                       GOODIX_BB010002_LENGTH);
  g_assert_true (goodix_pairing_activation_handle_a0 (activation, typed, NULL));
  g_clear_pointer (&typed, g_bytes_unref);
  g_clear_pointer (&request, g_bytes_unref);

  request = goodix_pairing_activation_next_request (activation, NULL);
  g_assert_nonnull (request);
  goodix_pairing_activation_out_complete (activation, NULL);
  g_assert_true (goodix_pairing_activation_handle_a0 (activation, e4_ack,
                                                       NULL));
  typed = e4_response (0xbb020003u, validator, 32u);
  g_assert_true (goodix_pairing_activation_handle_a0 (activation, typed, NULL));
  g_assert_cmpint (goodix_pairing_activation_get_phase (activation), ==,
                   GOODIX_PAIRING_ACTIVATION_TLS);
}

static void
test_journal_write_readback_tls_and_recovery (void)
{
  GoodixLivePreflightEvidence evidence = evidence_fixture ();
  GoodixPairingActivationPaths paths = { 0 };
  GoodixPairingActivationPolicy policy = { 0 };
  GoodixPairingActivationAudit audit;
  GoodixPairingActivationAudit recovery_audit;
  GoodixPairingActivationAudit reopen_audit;
  g_autofree gchar *directory = new_state_directory ();
  g_autoptr(GoodixPairingActivation) activation = NULL;
  g_autoptr(GoodixPairingActivation) recovery = NULL;
  g_autoptr(GoodixPairingActivation) reopen = NULL;
  guint8 psk[32];
  guint8 envelope[102];
  guint8 validator[32];
  GoodixSelfStateBinding binding = { 0 };
  GoodixSelfState *state = NULL;

  for (guint i = 0; i < sizeof psk; i++)
    psk[i] = (guint8) (0x20u + i);
  g_assert_true (goodix_pairing_crypto_derive (psk, sizeof psk, envelope,
                                               validator, NULL));
  paths.state_directory = directory;
  goodix_self_state_policy_for_owner (&policy.state, getuid (), getgid ());
  activation = goodix_pairing_activation_new_for_test (
    &paths, &policy, &evidence, psk, &audit, NULL);
  g_assert_nonnull (activation);
  g_assert_true (audit.prepared_journaled);
  g_assert_true (audit.e0_reserved_before_submit);
  g_assert_cmpuint (audit.persistent_write_count, ==, 0u);
  feed_successful_write_and_readback (activation, validator);
  g_assert_cmpuint (audit.persistent_write_count, ==, 1u);
  g_assert_true (audit.bb010002_readback_match);
  g_assert_true (audit.validator_readback_match);

  /* Simulate a crash after the verified write/readback but before TLS/ACTIVE. */
  g_clear_pointer (&activation, goodix_pairing_activation_free);
  memcpy (evidence.validator, validator, sizeof evidence.validator);
  recovery = goodix_pairing_activation_new_for_test (
    &paths, &policy, &evidence, psk, &recovery_audit, NULL);
  g_assert_nonnull (recovery);
  g_assert_cmpint (recovery_audit.disposition, ==,
                   GOODIX_PAIRING_ACTIVATION_DISPOSITION_RECOVER_PREPARED_TLS);
  g_assert_true (recovery_audit.recovered_without_e0);
  g_assert_null (goodix_pairing_activation_next_request (recovery, NULL));
  g_assert_true (goodix_pairing_activation_mark_tls_and_promote (recovery,
                                                                 NULL));
  g_assert_true (recovery_audit.tls_proven);
  g_assert_true (recovery_audit.active_promoted);
  g_clear_pointer (&recovery, goodix_pairing_activation_free);

  reopen = goodix_pairing_activation_new_for_test (
    &paths, &policy, &evidence, psk, &reopen_audit, NULL);
  g_assert_nonnull (reopen);
  g_assert_cmpint (reopen_audit.disposition, ==,
                   GOODIX_PAIRING_ACTIVATION_DISPOSITION_REUSE_ACTIVE_TLS);
  g_assert_true (reopen_audit.active_reused_without_e0);
  g_assert_null (goodix_pairing_activation_next_request (reopen, NULL));
  g_assert_true (goodix_pairing_activation_mark_tls_and_promote (reopen,
                                                                 NULL));
  g_assert_false (reopen_audit.active_promoted);

  binding.vid = 0x27c6u;
  binding.pid = 0x5125u;
  binding.chip_profile = evidence.chip_id;
  g_strlcpy (binding.app, "APP12509", sizeof binding.app);
  {
    g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
    gsize length = 32u;
    g_checksum_update (checksum, evidence.otp, sizeof evidence.otp);
    g_checksum_get_digest (checksum, binding.otp_sha256, &length);
    g_checksum_reset (checksum);
    length = 32u;
    g_checksum_update (checksum, evidence.config90, sizeof evidence.config90);
    g_checksum_get_digest (checksum, binding.config90_sha256, &length);
  }
  g_assert_cmpint (goodix_self_state_load (directory, &binding, &policy.state,
                                           &state, NULL), ==,
                   GOODIX_SELF_STATE_LOAD_VALID);
  g_assert_cmpint (goodix_self_state_get_record (state)->phase, ==,
                   GOODIX_SELF_STATE_ACTIVE);
  goodix_self_state_free (state);
  g_clear_pointer (&reopen, goodix_pairing_activation_free);
  remove_state_directory (directory);
}

static void
test_out_failure_is_terminal_and_never_retries (void)
{
  GoodixLivePreflightEvidence evidence = evidence_fixture ();
  GoodixPairingActivationPaths paths = { 0 };
  GoodixPairingActivationPolicy policy = { 0 };
  GoodixPairingActivationAudit audit;
  g_autofree gchar *directory = new_state_directory ();
  g_autoptr(GoodixPairingActivation) activation = NULL;
  g_autoptr(GBytes) request = NULL;
  g_autoptr(GError) transfer_error = g_error_new_literal (
    G_IO_ERROR, G_IO_ERROR_FAILED, "synthetic E0 OUT failure");
  guint8 psk[32];

  memset (psk, 0x5au, sizeof psk);
  paths.state_directory = directory;
  goodix_self_state_policy_for_owner (&policy.state, getuid (), getgid ());
  activation = goodix_pairing_activation_new_for_test (
    &paths, &policy, &evidence, psk, &audit, NULL);
  g_assert_nonnull (activation);
  request = goodix_pairing_activation_next_request (activation, NULL);
  g_assert_nonnull (request);
  goodix_pairing_activation_out_complete (activation, transfer_error);
  g_assert_cmpint (goodix_pairing_activation_get_phase (activation), ==,
                   GOODIX_PAIRING_ACTIVATION_TERMINAL);
  g_assert_null (goodix_pairing_activation_next_request (activation, NULL));
  g_assert_cmpuint (audit.provision.logical_e0_count, ==, 1u);
  g_assert_cmpuint (audit.persistent_write_count, ==, 1u);
  g_clear_pointer (&activation, goodix_pairing_activation_free);
  remove_state_directory (directory);
}

int
main (int argc,
      char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/goodix/pairing-activation/journal-write-recovery",
                   test_journal_write_readback_tls_and_recovery);
  g_test_add_func ("/goodix/pairing-activation/no-retry-after-out-failure",
                   test_out_failure_is_terminal_and_never_retries);
  return g_test_run ();
}
