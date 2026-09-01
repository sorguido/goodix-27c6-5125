/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Deterministic host-only integration tests for the native D278/01 chain. */
#include "goodix_a0_protocol.h"
#include "goodix_fpi_usb_backend.h"
#include "goodix_fpimage_device.h"
#include "goodix_secure_session.h"
#include "goodix_post_tls_lifecycle.h"
#include "goodix_usb_router.h"

#include <gusb.h>
#include <openssl/ssl.h>
#include <string.h>

/* ASSERT_CMPMEM in some GLib versions stores lengths in int, which trips
 * -Wsign-conversion under -Wconversion.  Use a size_t-safe local wrapper. */
#define ASSERT_CMPMEM(m1, l1, m2, l2) G_STMT_START { \
  gconstpointer __m1 = (m1), __m2 = (m2); \
  gsize __l1 = (l1), __l2 = (l2); \
  g_assert_cmpuint (__l1, ==, __l2); \
  if (__l1 != 0) \
    g_assert_true (memcmp (__m1, __m2, __l1) == 0); \
} G_STMT_END

typedef struct
{
  guint64 generation;
  GBytes *bytes;
} Submission;

typedef struct
{
  GoodixUsbRouter *router;
  GoodixFpiUsbBackend *backend;
  GoodixSecureSession *session;
  GoodixPostTlsLifecycle *post_tls;
  GoodixSecureSessionMaterial material;
  GoodixSecureSessionAudit audit;
  GoodixTlsAudit tls_audit;
  GQueue *out;
  GByteArray *server_record;
  guint64 generation;
  guint in_submit_count;
  guint terminal_count;
  guint post_tls_plaintext_count;
  GBytes *post_tls_plaintext;
  GoodixPostTlsAudit post_audit;
  guint post_image_count;
  guint schedule_count;
  guint64 scheduled_generation;
  gboolean schedule_pending;
  guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH];
  guint8 validator[32];
  guint8 a2[3];
  guint8 chip[4];
  guint8 otp[64];
  guint8 psk[GOODIX_SECURE_SESSION_PSK_LENGTH];
  GoodixFpImageDevice *device;
  GoodixDeviceContext *context;
  GCancellable *operator_cancellable;
  gboolean integrated_context;
} Fixture;

typedef struct
{
  SSL_CTX *context;
  SSL *ssl;
  const guint8 *psk;
  gsize psk_length;
  gboolean wrong_psk;
  gboolean wrong_identity;
} TlsClient;

static void
digest (const guint8 *data,
        gsize length,
        guint8 result[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  gsize result_length = 32;

  g_assert_cmpuint (length, <=, G_MAXSSIZE);
  g_checksum_update (checksum, data, (gssize) length);
  g_checksum_get_digest (checksum, result, &result_length);
  g_assert_cmpuint (result_length, ==, 32);
}

static void
set_config_finalizer (guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH])
{
  guint32 sum = 0;
  guint16 finalizer;

  for (guint i = 0; i < 111; i++)
    {
      guint16 word = (guint16) ((guint16) config[i * 2u] |
                                (guint16) ((guint16) config[i * 2u + 1u] << 8));
      sum += (guint32) word;
    }
  finalizer = (guint16) (0u - 0xa5a5u - sum);
  config[222] = (guint8) finalizer;
  config[223] = (guint8) (finalizer >> 8);
}

static void
material_init (Fixture *fixture)
{
  static const guint8 identity[] = "GF_ST411SEC_APP_12509";
  static const guint8 registers[4][2] = {
    { 0x20, 0x02 }, { 0x36, 0x02 }, { 0x38, 0x02 }, { 0x3a, 0x02 }
  };
  static const guint8 values[4][2] = {
    { 0xd8, 0x0b }, { 0xbe, 0x00 }, { 0xbd, 0x00 }, { 0xbc, 0x00 }
  };
  static const guint offsets[] = { 117, 121, 125, 129 };

  memset (fixture->config, 0, sizeof fixture->config);
  for (guint i = 0; i < 32; i++)
    {
      fixture->validator[i] = (guint8) (0x20u + i);
      fixture->psk[i] = (guint8) (0x80u + i);
    }
  fixture->a2[0] = 0x11;
  fixture->a2[1] = 0x22;
  fixture->a2[2] = 0x33;
  fixture->chip[0] = 0x25;
  fixture->chip[1] = 0x04;
  fixture->chip[2] = 0x12;
  fixture->chip[3] = 0x50;
  for (guint i = 0; i < sizeof fixture->otp; i++)
    fixture->otp[i] = (guint8) (i * 3u + 1u);
  for (guint i = 0; i < 4; i++)
    {
      memcpy (fixture->material.dac_values[i], values[i], 2);
      memcpy (fixture->config + offsets[i], registers[i], 2);
      memcpy (fixture->config + offsets[i] + 2u, values[i], 2);
    }
  set_config_finalizer (fixture->config);

  fixture->material.expected_identity = identity;
  fixture->material.expected_identity_length = sizeof identity;
  fixture->material.e4_validator = fixture->validator;
  fixture->material.e4_validator_length = sizeof fixture->validator;
  fixture->material.config90 = fixture->config;
  fixture->material.config90_length = sizeof fixture->config;
  fixture->material.psk = fixture->psk;
  fixture->material.psk_length = sizeof fixture->psk;
  digest (fixture->validator, sizeof fixture->validator,
          fixture->material.e4_validator_sha256);
  digest (fixture->a2, sizeof fixture->a2,
          fixture->material.a2_response_sha256);
  digest (fixture->chip, sizeof fixture->chip,
          fixture->material.chip82_response_sha256);
  digest (fixture->otp, sizeof fixture->otp,
          fixture->material.otp_a6_response_sha256);
  digest (fixture->config, sizeof fixture->config,
          fixture->material.config90_sha256);
}

static void
a0_consumer (guint8 type,
             GBytes *frame,
             gpointer user_data)
{
  Fixture *fixture = user_data;

  g_assert_cmphex (type, ==, 0xa0);
  if (fixture->post_tls != NULL &&
      goodix_post_tls_lifecycle_get_phase (fixture->post_tls) !=
        GOODIX_POST_TLS_PHASE_NOT_STARTED)
    goodix_post_tls_lifecycle_handle_a0 (fixture->post_tls, frame);
  else
    goodix_secure_session_handle_a0 (fixture->session, frame);
}

static void
b0_consumer (guint8 type,
             GBytes *frame,
             gpointer user_data)
{
  Fixture *fixture = user_data;

  g_assert_cmphex (type, ==, 0xb0);
  goodix_secure_session_handle_b0 (fixture->session, frame);
}

static void
submit_seam (GoodixFpiUsbBackend *backend,
             GoodixUsbDirection direction,
             guint64 generation,
             GBytes *bytes,
             gpointer user_data)
{
  Fixture *fixture = user_data;
  Submission *submission;

  (void) backend;
  g_assert_cmpuint (generation, ==, fixture->generation);
  if (direction == GOODIX_USB_TRANSFER_IN)
    {
      g_assert_null (bytes);
      fixture->in_submit_count++;
      return;
    }
  g_assert_nonnull (bytes);
  submission = g_new0 (Submission, 1);
  submission->generation = generation;
  submission->bytes = g_bytes_ref (bytes);
  g_queue_push_tail (fixture->out, submission);
}

static void
schedule_seam (GoodixSecureSession *session,
               guint64 generation,
               guint delay_ms,
               gpointer user_data)
{
  Fixture *fixture = user_data;

  g_assert_true (session == fixture->session);
  g_assert_cmpuint (delay_ms, ==, GOODIX_SECURE_SESSION_TLS_PACING_MS);
  g_assert_false (fixture->schedule_pending);
  fixture->schedule_pending = TRUE;
  fixture->scheduled_generation = generation;
  fixture->schedule_count++;
}

static void
terminal_seam (GoodixSecureSession *session,
               const GError *error,
               gpointer user_data)
{
  Fixture *fixture = user_data;

  g_assert_true (session == fixture->session);
  g_assert_nonnull (error);
  fixture->terminal_count++;
}

static Fixture *
fixture_new_with_audit (gboolean with_audit)
{
  Fixture *fixture = g_new0 (Fixture, 1);
  g_autoptr(GCancellable) cancellable = g_cancellable_new ();
  g_autoptr(GError) error = NULL;

  fixture->generation = 17;
  fixture->out = g_queue_new ();
  fixture->server_record = g_byte_array_new ();
  material_init (fixture);
  fixture->router = goodix_usb_router_new (a0_consumer, b0_consumer, fixture);
  goodix_usb_router_begin_generation (fixture->router, fixture->generation);
  fixture->backend = goodix_fpi_usb_backend_new (NULL, fixture->router,
                                                  0x81, 0x01, 4096);
  goodix_fpi_usb_backend_set_async_submit_seam (fixture->backend,
                                                 submit_seam, fixture);
  g_assert_true (goodix_fpi_usb_backend_begin_generation (
    fixture->backend, fixture->generation, cancellable, &error));
  g_assert_no_error (error);
  fixture->session = goodix_secure_session_new (
    fixture->backend, fixture->generation, &fixture->material,
    schedule_seam, fixture, terminal_seam, fixture,
    with_audit ? &fixture->audit : NULL, &fixture->tls_audit, &error);
  g_assert_nonnull (fixture->session);
  g_assert_no_error (error);
  return fixture;
}

static Fixture *
fixture_new (void)
{
  return fixture_new_with_audit (TRUE);
}

static Fixture *
fixture_new_integrated_epoch (void)
{
  Fixture *fixture = g_new0 (Fixture, 1);
  g_autoptr(GError) error = NULL;

  fixture->integrated_context = TRUE;
  fixture->out = g_queue_new ();
  fixture->server_record = g_byte_array_new ();
  material_init (fixture);
  fixture->device = goodix_fpimage_device_new ();
  fixture->context = goodix_fpimage_device_get_context (fixture->device);
  fixture->operator_cancellable = g_cancellable_new ();
  goodix_device_context_set_async_usb_submit_seam (
    fixture->context, submit_seam, fixture);
  g_assert_true (goodix_device_context_begin_operator_epoch (
    fixture->context, fixture->operator_cancellable, &error));
  g_assert_no_error (error);
  fixture->generation = goodix_device_context_get_generation (
    fixture->context);
  fixture->router = goodix_device_context_get_usb_router (fixture->context);
  fixture->backend = goodix_device_context_get_fpi_usb_backend (
    fixture->context);
  return fixture;
}

static void
complete_pre_session_sync_timeout (Fixture *fixture)
{
  g_autoptr(GError) timeout = g_error_new_literal (
    G_USB_DEVICE_ERROR, G_USB_DEVICE_ERROR_TIMED_OUT,
    "synthetic GUsb bulk timeout");
  GoodixPreSessionRxSyncAudit sync_audit;

  goodix_device_context_complete_receive (
    fixture->context, fixture->generation, NULL, 0, timeout);
  goodix_device_context_get_pre_session_rx_sync_audit (
    fixture->context, &sync_audit);
  g_assert_cmpint (sync_audit.pre_session_rx_result, ==,
                   GOODIX_PRE_SESSION_RX_SYNC_PASS);
  g_assert_true (sync_audit.pre_session_rx_quiet_boundary);
}

static void
start_integrated_secure_session (Fixture *fixture)
{
  GoodixPostTlsMaterial post_material = { 0 };
  g_autoptr(GError) error = NULL;

  for (guint i = 0; i < 6u; i++)
    {
      post_material.initial_fdt_table[i * 2u] = 0x80;
      post_material.initial_fdt_table[i * 2u + 1u] =
        (guint8) (0x40u + i);
    }
  post_material.af_timestamp = 0x1234;
  post_material.first_arm_timestamp = 0x2345;
  post_material.second_arm_timestamp = 0x3456;
  g_assert_true (goodix_device_context_configure_post_tls_lifecycle (
    fixture->context, &post_material, &fixture->post_audit, &error));
  g_assert_no_error (error);
  g_assert_true (goodix_device_context_start_secure_session (
    fixture->context, &fixture->material, schedule_seam, fixture,
    &fixture->audit, &fixture->tls_audit, &error));
  g_assert_no_error (error);
  fixture->session = goodix_device_context_get_secure_session (
    fixture->context);
}

static Fixture *
fixture_new_integrated_context (void)
{
  Fixture *fixture = fixture_new_integrated_epoch ();
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_device_context_begin_pre_session_rx_sync (
    fixture->context, &error));
  g_assert_no_error (error);
  complete_pre_session_sync_timeout (fixture);
  fixture->in_submit_count = 0;
  start_integrated_secure_session (fixture);
  return fixture;
}

static void
submission_free (Submission *submission)
{
  if (submission == NULL)
    return;
  g_bytes_unref (submission->bytes);
  g_free (submission);
}

static void
fixture_clear_out (Fixture *fixture)
{
  while (!g_queue_is_empty (fixture->out))
    submission_free (g_queue_pop_head (fixture->out));
}

static void
fixture_free (Fixture *fixture)
{
  if (fixture == NULL)
    return;
  fixture_clear_out (fixture);
  g_assert_true (goodix_fpi_usb_backend_is_drained (fixture->backend));
  if (fixture->integrated_context)
    {
      goodix_device_context_stop_operator_epoch (fixture->context);
      g_assert_true (goodix_device_context_operator_epoch_is_drained (
        fixture->context));
      g_clear_object (&fixture->operator_cancellable);
      g_clear_object (&fixture->device);
      g_queue_free (fixture->out);
      g_byte_array_unref (fixture->server_record);
      g_clear_pointer (&fixture->post_tls_plaintext, g_bytes_unref);
      g_free (fixture);
      return;
    }
  goodix_post_tls_lifecycle_free (fixture->post_tls);
  goodix_secure_session_free (fixture->session);
  goodix_fpi_usb_backend_free (fixture->backend);
  goodix_usb_router_free (fixture->router);
  g_queue_free (fixture->out);
  g_byte_array_unref (fixture->server_record);
  g_clear_pointer (&fixture->post_tls_plaintext, g_bytes_unref);
  g_free (fixture);
}

static void
post_tls_plaintext_seam (GBytes   *bytes,
                         gpointer  user_data)
{
  Fixture *fixture = user_data;

  fixture->post_tls_plaintext_count++;
  g_clear_pointer (&fixture->post_tls_plaintext, g_bytes_unref);
  fixture->post_tls_plaintext = g_bytes_ref (bytes);
}

static Submission *
pop_out (Fixture *fixture)
{
  Submission *submission = g_queue_pop_head (fixture->out);

  g_assert_nonnull (submission);
  return submission;
}

static void
complete_submission (Fixture *fixture,
                     Submission *submission,
                     const GError *error)
{
  goodix_fpi_usb_backend_complete_out (fixture->backend,
                                        submission->generation, error);
  submission_free (submission);
}

static GBytes *
build_response (guint8 control,
                const guint8 *body,
                gsize body_length)
{
  g_autoptr(GError) error = NULL;
  GBytes *frame = goodix_a0_build_frame (control, control, body, body_length,
                                         &error);
  g_assert_no_error (error);
  g_assert_nonnull (frame);
  return frame;
}

static GBytes *
build_ack (guint8 echo,
           guint8 status)
{
  guint8 body[2] = { echo, status };
  return build_response (0xb0, body, sizeof body);
}

static void
feed_completion (Fixture *fixture,
                 const guint8 *data,
                 gsize length,
                 guint64 generation)
{
  g_autoptr(GError) error = NULL;

  if (fixture->integrated_context)
    {
      goodix_device_context_complete_receive (fixture->context, generation,
                                               data, length, NULL);
      return;
    }
  g_assert_true (goodix_fpi_usb_backend_arm_receive (
    fixture->backend, fixture->generation, &error));
  g_assert_no_error (error);
  goodix_fpi_usb_backend_complete_receive (fixture->backend, generation,
                                            data, length, NULL);
}

static void
feed_frames (Fixture *fixture,
             GBytes *first,
             GBytes *second,
             guint mode)
{
  gsize first_length;
  const guint8 *first_data = g_bytes_get_data (first, &first_length);

  if (second != NULL && mode == 1)
    {
      gsize second_length;
      const guint8 *second_data = g_bytes_get_data (second, &second_length);
      g_autoptr(GByteArray) combined = g_byte_array_sized_new (
        (guint) (first_length + second_length));
      g_byte_array_append (combined, first_data, (guint) first_length);
      g_byte_array_append (combined, second_data, (guint) second_length);
      feed_completion (fixture, combined->data, combined->len,
                       fixture->generation);
      return;
    }
  if (mode == 2 && first_length > 2)
    {
      feed_completion (fixture, first_data, 2, fixture->generation);
      feed_completion (fixture, first_data + 2, first_length - 2,
                       fixture->generation);
    }
  else
    feed_completion (fixture, first_data, first_length, fixture->generation);
  if (second != NULL)
    {
      gsize second_length;
      const guint8 *second_data = g_bytes_get_data (second, &second_length);
      feed_completion (fixture, second_data, second_length,
                       fixture->generation);
    }
}

static GBytes *
typed_for_phase (Fixture *fixture,
                 GoodixSecurePhase phase)
{
  guint8 e4[41] = { 0x00, 0x03, 0x00, 0x02, 0xbb, 0x20, 0, 0, 0 };
  static const guint8 done90[] = { 1, 0 };

  switch (phase)
    {
    case GOODIX_SECURE_PHASE_A8:
      return build_response (0xa8,
                             fixture->material.expected_identity,
                             fixture->material.expected_identity_length);
    case GOODIX_SECURE_PHASE_E4:
      memcpy (e4 + 9, fixture->validator, sizeof fixture->validator);
      return build_response (0xe4, e4, sizeof e4);
    case GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2:
    case GOODIX_SECURE_PHASE_OEM_COLD_START_A2_1:
    case GOODIX_SECURE_PHASE_OEM_COLD_START_A2_2:
      return build_response (0xa2, fixture->a2, sizeof fixture->a2);
    case GOODIX_SECURE_PHASE_CHIP_82:
      return build_response (0x82, fixture->chip, sizeof fixture->chip);
    case GOODIX_SECURE_PHASE_OTP_A6:
      return build_response (0xa6, fixture->otp, sizeof fixture->otp);
    case GOODIX_SECURE_PHASE_CONFIG_90:
      return build_response (0x90, done90, sizeof done90);
    default:
      return NULL;
    }
}

static guint8
control_for_phase (GoodixSecurePhase phase)
{
  switch (phase)
    {
    case GOODIX_SECURE_PHASE_A8: return 0xa8;
    case GOODIX_SECURE_PHASE_E4: return 0xe4;
    case GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2:
    case GOODIX_SECURE_PHASE_OEM_COLD_START_A2_1:
    case GOODIX_SECURE_PHASE_OEM_COLD_START_A2_2: return 0xa2;
    case GOODIX_SECURE_PHASE_CHIP_82: return 0x82;
    case GOODIX_SECURE_PHASE_OTP_A6: return 0xa6;
    case GOODIX_SECURE_PHASE_MODE_70: return 0x70;
    case GOODIX_SECURE_PHASE_DAC_220:
    case GOODIX_SECURE_PHASE_DAC_236:
    case GOODIX_SECURE_PHASE_DAC_238:
    case GOODIX_SECURE_PHASE_DAC_23A: return 0x80;
    case GOODIX_SECURE_PHASE_CONFIG_90: return 0x90;
    case GOODIX_SECURE_PHASE_D1: return 0xd1;
    default: return 0;
    }
}

static void
assert_command_shape (Fixture *fixture,
                      GoodixSecurePhase phase,
                      GBytes *frame)
{
  GoodixA0Message message = { 0 };
  g_autoptr(GError) error = NULL;
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);
  guint8 checksum_control = phase == GOODIX_SECURE_PHASE_D1 ? 0xd0 :
    control_for_phase (phase);

  g_assert_cmphex (data[0], ==, 0xa0);
  g_assert_cmpuint (length, !=, 64);
  g_assert_true (goodix_a0_parse_frame (frame, checksum_control,
                                        &message, &error));
  g_assert_no_error (error);
  g_assert_cmphex (message.control, ==, control_for_phase (phase));
  if (phase == GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2)
    {
      static const guint8 exact_reentry_body[] = { 0x01, 0x14 };
      gsize body_length;
      const guint8 *body = g_bytes_get_data (message.body, &body_length);

      ASSERT_CMPMEM (body, body_length, exact_reentry_body,
                     sizeof exact_reentry_body);
    }
  else if (phase >= GOODIX_SECURE_PHASE_DAC_220 &&
      phase <= GOODIX_SECURE_PHASE_DAC_23A)
    {
      gsize body_length;
      const guint8 *body = g_bytes_get_data (message.body, &body_length);
      guint index = (guint) phase - GOODIX_SECURE_PHASE_DAC_220;
      static const guint8 addresses[4][2] = {
        { 0x20, 0x02 }, { 0x36, 0x02 }, { 0x38, 0x02 }, { 0x3a, 0x02 }
      };
      g_assert_cmpuint (body_length, ==, 5);
      ASSERT_CMPMEM (body, 2, addresses[index], 2);
      g_assert_cmphex (body[2], ==, 2);
      ASSERT_CMPMEM (body + 3, 2, fixture->material.dac_values[index], 2);
    }
  goodix_a0_message_clear (&message);
}

static void
respond_valid (Fixture *fixture,
               guint mode,
               guint8 ack_status)
{
  GoodixSecurePhase phase = goodix_secure_session_get_phase (fixture->session);
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GBytes) typed = NULL;
  Submission *submission = pop_out (fixture);

  assert_command_shape (fixture, phase, submission->bytes);
  complete_submission (fixture, submission, NULL);
  if (phase == GOODIX_SECURE_PHASE_D1)
    return;
  ack = build_ack (control_for_phase (phase), ack_status);
  typed = typed_for_phase (fixture, phase);
  feed_frames (fixture, ack, typed, mode);
}

static void
start_and_advance_to (Fixture *fixture,
                      GoodixSecurePhase target)
{
  g_autoptr(GError) error = NULL;
  guint mode = 0;

  g_assert_true (goodix_secure_session_start (fixture->session, &error));
  g_assert_no_error (error);
  while (goodix_secure_session_get_phase (fixture->session) < target)
    {
      respond_valid (fixture, mode % 3u, 0x01);
      mode++;
    }
}

static unsigned int
client_psk_cb (SSL *ssl,
               const char *hint,
               char *identity,
               unsigned int identity_max,
               unsigned char *psk,
               unsigned int psk_max)
{
  TlsClient *client = SSL_get_app_data (ssl);

  (void) hint;
  g_strlcpy (identity,
             client->wrong_identity ? "Wrong_identity" : "Client_identity",
             identity_max);
  g_assert_cmpuint (psk_max, >=, client->psk_length);
  memcpy (psk, client->psk, client->psk_length);
  if (client->wrong_psk)
    psk[0] ^= 0xff;
  return (unsigned int) client->psk_length;
}

static void
client_init (TlsClient *client,
             Fixture *fixture)
{
  BIO *input;
  BIO *output;

  memset (client, 0, sizeof *client);
  client->psk = fixture->psk;
  client->psk_length = sizeof fixture->psk;
  client->context = SSL_CTX_new (TLS_client_method ());
  g_assert_nonnull (client->context);
  g_assert_cmpint (SSL_CTX_set_min_proto_version (client->context,
                                                  TLS1_2_VERSION), ==, 1);
  g_assert_cmpint (SSL_CTX_set_max_proto_version (client->context,
                                                  TLS1_2_VERSION), ==, 1);
  g_assert_cmpint (SSL_CTX_set_cipher_list (client->context,
                                             "PSK-AES128-GCM-SHA256"), ==, 1);
  SSL_CTX_set_psk_client_callback (client->context, client_psk_cb);
  client->ssl = SSL_new (client->context);
  g_assert_nonnull (client->ssl);
  SSL_set_app_data (client->ssl, client);
  input = BIO_new (BIO_s_mem ());
  output = BIO_new (BIO_s_mem ());
  g_assert_nonnull (input);
  g_assert_nonnull (output);
  BIO_set_mem_eof_return (input, -1);
  SSL_set_bio (client->ssl, input, output);
  SSL_set_connect_state (client->ssl);
}

static void
client_clear (TlsClient *client)
{
  SSL_free (client->ssl);
  SSL_CTX_free (client->context);
}

static void
feed_client_records (Fixture *fixture,
                     TlsClient *client)
{
  guint8 buffer[8192];
  int read_length;
  g_autoptr(GByteArray) pending = g_byte_array_new ();

  while ((read_length = BIO_read (SSL_get_wbio (client->ssl), buffer,
                                  sizeof buffer)) > 0)
    g_byte_array_append (pending, buffer, (guint) read_length);
  while (pending->len >= 5)
    {
      gsize record_length = 5u + ((gsize) pending->data[3] << 8) +
                            pending->data[4];
      guint8 header[4];
      g_autoptr(GByteArray) b0 = NULL;
      if (pending->len < record_length)
        break;
      if (goodix_secure_session_get_phase (fixture->session) ==
          GOODIX_SECURE_PHASE_TERMINAL)
        {
          g_byte_array_set_size (pending, 0);
          break;
        }
      header[0] = 0xb0;
      header[1] = (guint8) record_length;
      header[2] = (guint8) (record_length >> 8);
      header[3] = (guint8) (header[0] + header[1] + header[2]);
      b0 = g_byte_array_sized_new ((guint) record_length + 4u);
      g_byte_array_append (b0, header, sizeof header);
      g_byte_array_append (b0, pending->data, (guint) record_length);
      feed_completion (fixture, b0->data, b0->len, fixture->generation);
      g_byte_array_remove_range (pending, 0, (guint) record_length);
    }
  g_assert_cmpuint (pending->len, ==, 0);
}

static GBytes *
take_initial_client_hello (TlsClient *client)
{
  guint8 buffer[8192];
  int result;
  int length;

  result = SSL_do_handshake (client->ssl);
  g_assert_cmpint (result, ==, -1);
  g_assert_cmpint (SSL_get_error (client->ssl, result), ==,
                   SSL_ERROR_WANT_READ);
  length = BIO_read (SSL_get_wbio (client->ssl), buffer, sizeof buffer);
  g_assert_cmpint (length, >, 9);
  g_assert_cmpuint ((gsize) length, ==,
                    5u + ((gsize) buffer[3] << 8) + buffer[4]);
  return g_bytes_new (buffer, (gsize) length);
}

static void
feed_b0_payload (Fixture *fixture,
                 const guint8 *payload,
                 gsize payload_length)
{
  guint8 header[4] = { 0xb0, (guint8) payload_length,
                       (guint8) (payload_length >> 8), 0 };
  g_autoptr(GByteArray) frame = g_byte_array_new ();

  header[3] = (guint8) (header[0] + header[1] + header[2]);
  g_byte_array_append (frame, header, sizeof header);
  g_byte_array_append (frame, payload, (guint) payload_length);
  feed_completion (fixture, frame->data, frame->len, fixture->generation);
}

static void
drain_server_records (Fixture *fixture,
                      TlsClient *client,
                      gboolean exercise_stale_pacing)
{
  while (!g_queue_is_empty (fixture->out) || fixture->schedule_pending)
    {
      Submission *submission;
      gsize length;
      const guint8 *data;

      if (g_queue_is_empty (fixture->out))
        {
          guint64 generation = fixture->scheduled_generation;
          if (exercise_stale_pacing)
            {
              goodix_secure_session_pacing_ready (fixture->session,
                                                   generation - 1u);
              g_assert_true (g_queue_is_empty (fixture->out));
            }
          fixture->schedule_pending = FALSE;
          goodix_secure_session_pacing_ready (fixture->session, generation);
          continue;
        }
      submission = pop_out (fixture);
      data = g_bytes_get_data (submission->bytes, &length);
      if (fixture->integrated_context &&
          goodix_secure_session_get_phase (fixture->session) ==
            GOODIX_SECURE_PHASE_STOP &&
          length != 0 && data[0] == 0xa0)
        {
          g_queue_push_head (fixture->out, submission);
          break;
        }
      g_assert_cmpuint (length, ==, 64);
      g_byte_array_append (fixture->server_record, data, (guint) length);
      if (fixture->server_record->len >= 4)
        {
          guint16 payload_length = (guint16) (
            (guint16) fixture->server_record->data[1] |
            (guint16) ((guint16) fixture->server_record->data[2] << 8));
          gsize logical_length = (gsize) payload_length + 4u;
          if (fixture->server_record->len >= logical_length)
            {
              g_assert_cmphex (fixture->server_record->data[0], ==, 0xb0);
              g_assert_cmphex (fixture->server_record->data[3], ==,
                               (guint8) (0xb0u + fixture->server_record->data[1] +
                                         fixture->server_record->data[2]));
              for (gsize i = logical_length;
                   i < fixture->server_record->len; i++)
                g_assert_cmphex (fixture->server_record->data[i], ==, 0);
              g_assert_cmpint (BIO_write (SSL_get_rbio (client->ssl),
                                          fixture->server_record->data + 4,
                                          payload_length), ==,
                               payload_length);
              g_byte_array_set_size (fixture->server_record, 0);
            }
        }
      complete_submission (fixture, submission, NULL);
    }
  g_assert_cmpuint (fixture->server_record->len, ==, 0);
}

static gboolean
pump_tls (Fixture *fixture,
          TlsClient *client,
          gboolean exercise_stale_pacing)
{
  for (guint iteration = 0; iteration < 64; iteration++)
    {
      int result = SSL_do_handshake (client->ssl);
      if (result != 1)
        {
          int ssl_error = SSL_get_error (client->ssl, result);
          if (ssl_error != SSL_ERROR_WANT_READ &&
              ssl_error != SSL_ERROR_WANT_WRITE)
            return FALSE;
        }
      feed_client_records (fixture, client);
      drain_server_records (fixture, client, exercise_stale_pacing);
      if (SSL_is_init_finished (client->ssl) &&
          goodix_secure_session_get_phase (fixture->session) ==
            GOODIX_SECURE_PHASE_STOP)
        return TRUE;
      if (goodix_secure_session_get_phase (fixture->session) ==
          GOODIX_SECURE_PHASE_TERMINAL)
        return FALSE;
    }
  return FALSE;
}

static guint32
post_crc32_mpeg2 (const guint8 *data,
                  gsize         length)
{
  guint32 crc = UINT32_C (0xffffffff);

  for (gsize i = 0; i < length; i++)
    {
      crc ^= (guint32) data[i] << 24;
      for (guint bit = 0; bit < 8u; bit++)
        crc = (crc & UINT32_C (0x80000000)) != 0 ?
          (crc << 1) ^ UINT32_C (0x04c11db7) : crc << 1;
    }
  return crc;
}

static GBytes *
post_zero_image (void)
{
  g_autoptr(GByteArray) bytes = g_byte_array_sized_new (
    GOODIX_IMAGE_PLAINTEXT_LENGTH);
  static const guint8 header[] = { 0x20, 0x0a, 0x1e };
  static const guint8 prefix[5] = { 0 };
  guint8 packed[GOODIX_IMAGE_PACKED_LENGTH] = { 0 };
  guint32 crc = post_crc32_mpeg2 (packed, sizeof packed);
  guint8 trailer[4] = {
    (guint8) (crc >> 8), (guint8) crc,
    (guint8) (crc >> 24), (guint8) (crc >> 16)
  };
  guint8 no_check = 0x88;

  g_byte_array_append (bytes, header, sizeof header);
  g_byte_array_append (bytes, prefix, sizeof prefix);
  g_byte_array_append (bytes, packed, sizeof packed);
  g_byte_array_append (bytes, trailer, sizeof trailer);
  g_byte_array_append (bytes, &no_check, 1u);
  g_assert_cmpuint (bytes->len, ==, GOODIX_IMAGE_PLAINTEXT_LENGTH);
  return g_byte_array_free_to_bytes (g_steal_pointer (&bytes));
}

static gboolean
post_image_seam (GoodixPostTlsLifecycle *lifecycle,
                 guint                   acquisition_index,
                 const uint16_t          samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT],
                 gpointer                user_data,
                 GError                **error)
{
  Fixture *fixture = user_data;

  (void) lifecycle;
  (void) error;
  g_assert_cmpuint (acquisition_index, ==, fixture->post_image_count + 1u);
  for (gsize i = 0; i < GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT; i++)
    g_assert_cmpuint (samples[i], ==, 0u);
  fixture->post_image_count++;
  return TRUE;
}

static void
post_event_seam (GoodixPostTlsLifecycle *lifecycle,
                 gpointer                user_data)
{
  (void) lifecycle;
  (void) user_data;
}

static void
post_terminal_seam (GoodixPostTlsLifecycle *lifecycle,
                    const GError           *error,
                    gpointer                user_data)
{
  (void) lifecycle;
  (void) user_data;
  g_error ("unexpected post-TLS terminal: %s", error->message);
}

static void
post_plaintext_to_lifecycle (GBytes   *bytes,
                             gpointer  user_data)
{
  Fixture *fixture = user_data;
  goodix_post_tls_lifecycle_handle_plaintext (fixture->post_tls, bytes);
}

static void
post_complete_command (Fixture *fixture,
                       guint8   expected_control)
{
  Submission *submission = pop_out (fixture);
  gsize length;
  const guint8 *data = g_bytes_get_data (submission->bytes, &length);

  g_assert_cmpuint (length, ==, 64u);
  g_assert_cmphex (data[0], ==, 0xa0);
  g_assert_cmphex (data[4], ==, expected_control);
  complete_submission (fixture, submission, NULL);
}

static void
post_feed_response (Fixture      *fixture,
                    guint8        control,
                    const guint8 *body,
                    gsize         body_length)
{
  g_autoptr(GBytes) frame = build_response (control, body, body_length);

  if (control == 0x50 && body_length == 2409u)
    {
      const guint8 *data;
      guint8 *copy;
      gsize length;

      g_assert_cmphex (body[0], ==, 0x50);
      g_assert_cmphex (body[1], ==, 0x01);

      data = g_bytes_get_data (frame, &length);
      copy = g_malloc (length);
      memcpy (copy, data, length);
      copy[length - 1u] = 0x88;

      g_clear_pointer (&frame, g_bytes_unref);
      frame = g_bytes_new_take (copy, length);
    }
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);
  feed_completion (fixture, data, length, fixture->generation);
}

static void
post_feed_ack (Fixture *fixture,
               guint8   control)
{
  const guint8 body[2] = { control, 0x01 };
  post_feed_response (fixture, 0xb0, body, sizeof body);
}

static void
post_feed_event (Fixture *fixture,
                 guint8   control,
                 guint16  irq,
                 guint16  flags,
                 guint16  raw_base)
{
  guint8 body[16];

  body[0] = (guint8) irq;
  body[1] = (guint8) (irq >> 8);
  body[2] = (guint8) flags;
  body[3] = (guint8) (flags >> 8);
  for (guint i = 0; i < 6u; i++)
    {
      guint16 word = (guint16) (raw_base + i * 2u);
      body[4u + i * 2u] = (guint8) word;
      body[5u + i * 2u] = (guint8) (word >> 8);
    }
  post_feed_response (fixture, control, body, sizeof body);
}

static void
post_write_application_data (Fixture    *fixture,
                             TlsClient  *client,
                             const guint8 *data,
                             gsize       length)
{
  g_assert_cmpuint (length, <=, G_MAXINT);
  g_assert_cmpint (SSL_write (client->ssl, data, (gint) length), ==,
                   (gint) length);
  feed_client_records (fixture, client);
}

static void
drive_post_tls_two_acquisitions (Fixture   *fixture,
                                 TlsClient *client)
{
  guint8 af[16] = { 0 };
  guint8 nav[2409] = { 0 };
  static const guint8 typed82[2] = { 0, 0x20 };
  guint8 auxiliary[GOODIX_IMAGE_PLAINTEXT_LENGTH] = { 0 };
  g_autoptr(GBytes) image = post_zero_image ();
  gsize image_length;
  const guint8 *image_data = g_bytes_get_data (image, &image_length);

  nav[0] = 0x50;
  nav[1] = 0x01;

  post_complete_command (fixture, 0xd4);
  post_feed_ack (fixture, 0xd4);
  post_complete_command (fixture, 0xaf);
  af[1] = 0x02;
  post_feed_response (fixture, 0xae, af, sizeof af);

  for (guint cycle = 0; cycle < 3u; cycle++)
    {
      post_complete_command (fixture, 0x36);
      post_feed_ack (fixture, 0x36);
      post_feed_event (fixture, 0x36, 0x0100, 0,
                       (guint16) (0x0100u + cycle * 0x20u));
      if (cycle == 0)
        {
          post_complete_command (fixture, 0x50);
          post_feed_ack (fixture, 0x50);
          post_feed_response (fixture, 0x50, nav, sizeof nav);
        }
      else if (cycle == 1)
        {
          post_complete_command (fixture, 0x82);
          post_feed_ack (fixture, 0x82);
          post_feed_response (fixture, 0x82, typed82, sizeof typed82);
          post_complete_command (fixture, 0x20);
          post_feed_ack (fixture, 0x20);
          post_write_application_data (fixture, client, auxiliary,
                                       sizeof auxiliary);
        }
    }

  post_complete_command (fixture, 0x32);
  post_feed_ack (fixture, 0x32);
  post_feed_event (fixture, 0x32, 0x0002, 0x003f, 0x0180);
  post_complete_command (fixture, 0x22);
  post_feed_ack (fixture, 0x22);
  post_write_application_data (fixture, client, image_data, image_length);
  post_complete_command (fixture, 0x34);
  post_feed_ack (fixture, 0x34);
  post_feed_event (fixture, 0x34, 0x0200, 0, 0x0120);
  post_complete_command (fixture, 0x20);
  post_feed_ack (fixture, 0x20);
  post_write_application_data (fixture, client, auxiliary, sizeof auxiliary);
  post_complete_command (fixture, 0x50);
  post_feed_ack (fixture, 0x50);
  post_feed_response (fixture, 0x50, nav, sizeof nav);
  goodix_post_tls_lifecycle_set_framework_await_finger_on (
    fixture->post_tls, fixture->generation, TRUE);
  post_complete_command (fixture, 0x32);
  post_feed_ack (fixture, 0x32);
  post_feed_event (fixture, 0x32, 0x0002, 0x003f, 0x0180);
  post_complete_command (fixture, 0x22);
  post_feed_ack (fixture, 0x22);
  post_write_application_data (fixture, client, image_data, image_length);
}

static void
test_a0_vectors_and_malformed (void)
{
  static const struct
  {
    guint8 wire;
    guint8 checksum;
    const guint8 *body;
    gsize body_length;
    const gchar *hex;
  } vectors[] = {
    { 0xa8, 0xa8, (const guint8 *) "\0\0", 2,
      "a00600a6a803000000ff" },
    { 0xe4, 0xe4, (const guint8 *) "\x03\0\x02\xbb\0\0\0\0", 8,
      "a00c00ace40900030002bb00000000fd" },
    { 0xd1, 0xd0, (const guint8 *) "\0\0", 2,
      "a00600a6d103000000d7" },
  };

  for (guint i = 0; i < G_N_ELEMENTS (vectors); i++)
    {
      g_autoptr(GError) error = NULL;
      g_autoptr(GBytes) frame = goodix_a0_build_frame (
        vectors[i].wire, vectors[i].checksum, vectors[i].body,
        vectors[i].body_length, &error);
      g_autofree guint8 *expected = NULL;
      gsize expected_length = 0;
      gsize length;
      const guint8 *data = g_bytes_get_data (frame, &length);
      g_assert_no_error (error);
      expected = g_malloc (strlen (vectors[i].hex) / 2u);
      for (gsize j = 0; j < strlen (vectors[i].hex) / 2u; j++)
        {
          gchar pair[3] = { vectors[i].hex[j * 2u],
                            vectors[i].hex[j * 2u + 1u], 0 };
          expected[j] = (guint8) g_ascii_strtoull (pair, NULL, 16);
          expected_length++;
        }
      ASSERT_CMPMEM (data, length, expected, expected_length);
    }

  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) valid = goodix_a0_build_frame (
    0xa8, 0xa8, (const guint8 *) "\0\0", 2, &error);
  gsize length;
  const guint8 *valid_data = g_bytes_get_data (valid, &length);
  for (guint field = 0; field < 3; field++)
    {
      g_autofree guint8 *bad = g_memdup2 (valid_data, length);
      GoodixA0Message message = { 0 };
      g_autoptr(GBytes) bad_frame = NULL;
      if (field == 0)
        bad[2]++;
      else if (field == 1)
        bad[3]++;
      else
        bad[length - 1u]++;
      bad_frame = g_bytes_new_take (g_steal_pointer (&bad), length);
      g_assert_false (goodix_a0_parse_frame (bad_frame, 0xa8,
                                             &message, &error));
      g_assert_nonnull (error);
      g_clear_error (&error);
    }
}

static void
test_happy_path (void)
{
  Fixture *fixture = fixture_new ();
  TlsClient client;

  start_and_advance_to (fixture, GOODIX_SECURE_PHASE_D1);
  respond_valid (fixture, 0, 0x01);
  client_init (&client, fixture);
  g_assert_true (pump_tls (fixture, &client, TRUE));
  g_assert_cmpstr (goodix_tls_server_get_protocol (
                     goodix_secure_session_get_tls_server (fixture->session)),
                   ==, "TLSv1.2");
  g_assert_cmpstr (goodix_tls_server_get_cipher (
                     goodix_secure_session_get_tls_server (fixture->session)),
                   ==, "PSK-AES128-GCM-SHA256");
  g_assert_cmpuint (fixture->audit.command_count, ==, 14);
  g_assert_cmpuint (fixture->audit.ack_count, ==, 13);
  g_assert_cmpuint (fixture->audit.typed_response_count, ==, 8);
  g_assert_cmpuint (fixture->audit.reentry_recovery_a2_submit_count, ==, 1);
  g_assert_cmpuint (fixture->audit.reentry_recovery_a2_ack_count, ==, 1);
  g_assert_cmpuint (fixture->audit.reentry_recovery_a2_typed_count, ==, 1);
  g_assert_cmpint (fixture->audit.reentry_recovery_a2_result_class, ==,
                   GOODIX_REENTRY_RECOVERY_A2_STRICT_MATCH);
  g_assert_true (fixture->audit.secure_session_target_prefix_completed);
  g_assert_cmpuint (fixture->audit.a8_submit_count, ==, 1);
  g_assert_cmpuint (fixture->audit.a8_ack_count, ==, 1);
  g_assert_cmpuint (fixture->audit.a8_typed_count, ==, 1);
  g_assert_true (fixture->audit.a8_app12509_pin_match);
  g_assert_cmpuint (fixture->audit.e4_submit_count, ==, 1);
  g_assert_cmpuint (fixture->audit.oem_cold_start_a2_1_submit_count, ==, 1);
  g_assert_cmpuint (fixture->audit.oem_cold_start_a2_2_submit_count, ==, 1);
  g_assert_cmpuint (fixture->audit.retry_count, ==, 0);
  g_assert_cmpuint (fixture->audit.transport_reopen_count, ==, 0);
  g_assert_cmpuint (fixture->audit.device_reset_count, ==, 0);
  g_assert_cmpuint (fixture->audit.persistent_write_count, ==, 0);
  g_assert_false (fixture->audit.d4_reachable);
  g_assert_true (fixture->audit.tls_established);
  g_assert_cmpuint (fixture->tls_audit.handshake_count, ==, 1);
  g_assert_cmpuint (fixture->tls_audit.secret_handoff_count, ==, 1);
  g_assert_true (fixture->tls_audit.project_secret_zeroized);
  g_assert_false (goodix_tls_server_test_second_handoff (
    goodix_secure_session_get_tls_server (fixture->session)));
  g_assert_true (fixture->tls_audit.second_handoff_rejected);
  g_assert_cmpuint (fixture->audit.b0_physical_submit_count, >, 0);
  g_assert_cmpuint (fixture->audit.tls_record_count, >, 0);
  g_assert_cmpuint (fixture->schedule_count, >, 0);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (
                     fixture->backend), ==, 0);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_max_outstanding (
                     fixture->backend), ==, 1);
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_STOP);
  {
    g_autoptr(GBytes) forbidden_after_stop = build_ack (0xd4, 0x01);
    goodix_secure_session_handle_a0 (fixture->session, forbidden_after_stop);
    g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                     GOODIX_SECURE_PHASE_TERMINAL);
  }
  client_clear (&client);
  fixture_free (fixture);

  /* Audit telemetry is optional and must not control TLS-record pacing. */
  fixture = fixture_new_with_audit (FALSE);
  start_and_advance_to (fixture, GOODIX_SECURE_PHASE_D1);
  respond_valid (fixture, 0, 0x01);
  client_init (&client, fixture);
  g_assert_true (pump_tls (fixture, &client, FALSE));
  g_assert_cmpuint (fixture->schedule_count, >, 0);
  client_clear (&client);
  fixture_free (fixture);
}

static void
test_retained_tls_post_handshake_handoff (void)
{
  static const guint8 application_data[] = "post-tls-same-owner";
  Fixture *fixture = fixture_new ();
  TlsClient client;
  g_autoptr(GError) error = NULL;
  gsize plaintext_length;
  const guint8 *plaintext;

  start_and_advance_to (fixture, GOODIX_SECURE_PHASE_D1);
  respond_valid (fixture, 0, 0x01);
  client_init (&client, fixture);
  g_assert_true (pump_tls (fixture, &client, FALSE));
  GoodixTlsServer *retained = goodix_secure_session_get_tls_server (
    fixture->session);
  goodix_secure_session_set_post_tls_plaintext_callback (
    fixture->session, post_tls_plaintext_seam, fixture);
  g_assert_true (goodix_secure_session_handoff_backend (fixture->session,
                                                        &error));
  g_assert_no_error (error);
  g_assert_true (retained == goodix_secure_session_get_tls_server (
                            fixture->session));
  g_assert_cmpint (SSL_write (client.ssl, application_data,
                              sizeof application_data), ==,
                   (gint) sizeof application_data);
  feed_client_records (fixture, &client);
  g_assert_cmpuint (fixture->post_tls_plaintext_count, ==, 1u);
  plaintext = g_bytes_get_data (fixture->post_tls_plaintext,
                                &plaintext_length);
  ASSERT_CMPMEM (plaintext, plaintext_length, application_data,
                 sizeof application_data);
  g_assert_cmpuint (fixture->tls_audit.handshake_count, ==, 1u);
  g_assert_cmpuint (fixture->tls_audit.secret_handoff_count, ==, 1u);
  g_assert_true (fixture->tls_audit.project_secret_zeroized);
  client_clear (&client);
  fixture_free (fixture);
}

static void
test_reentry_tls_to_two_acquisitions_composed (void)
{
  Fixture *fixture = fixture_new ();
  TlsClient client;
  GoodixPostTlsMaterial material = { 0 };
  GoodixTlsServer *retained;
  g_autoptr(GError) error = NULL;

  for (guint i = 0; i < 6u; i++)
    {
      material.initial_fdt_table[i * 2u] = 0x80;
      material.initial_fdt_table[i * 2u + 1u] = (guint8) (0x40u + i);
    }
  material.af_timestamp = 0x1234;
  material.first_arm_timestamp = 0x2345;
  material.second_arm_timestamp = 0x3456;

  start_and_advance_to (fixture, GOODIX_SECURE_PHASE_D1);
  respond_valid (fixture, 0, 0x01);
  client_init (&client, fixture);
  g_assert_true (pump_tls (fixture, &client, FALSE));
  retained = goodix_secure_session_get_tls_server (fixture->session);
  fixture->post_tls = goodix_post_tls_lifecycle_new (
    fixture->backend, fixture->generation, &material, post_image_seam,
    post_event_seam, post_event_seam, post_event_seam, post_terminal_seam,
    fixture, &fixture->post_audit, &error);
  g_assert_nonnull (fixture->post_tls);
  g_assert_no_error (error);
  goodix_secure_session_set_post_tls_plaintext_callback (
    fixture->session, post_plaintext_to_lifecycle, fixture);
  g_assert_true (goodix_secure_session_handoff_backend (fixture->session,
                                                        &error));
  g_assert_no_error (error);
  g_assert_true (goodix_post_tls_lifecycle_start (fixture->post_tls, &error));
  g_assert_no_error (error);

  drive_post_tls_two_acquisitions (fixture, &client);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->post_tls), ==,
                   GOODIX_POST_TLS_PHASE_STOP);
  g_assert_true (retained == goodix_secure_session_get_tls_server (
                            fixture->session));
  g_assert_cmpuint (fixture->audit.command_count, ==, 14u);
  g_assert_true (fixture->audit.secure_session_target_prefix_completed);
  g_assert_cmpuint (fixture->tls_audit.handshake_count, ==, 1u);
  g_assert_cmpuint (fixture->tls_audit.secret_handoff_count, ==, 1u);
  g_assert_cmpuint (fixture->post_image_count, ==, 2u);
  g_assert_cmpuint (fixture->post_audit.command_count, ==, 15u);
  g_assert_cmpuint (fixture->post_audit.first_image_pipeline_count, ==, 1u);
  g_assert_cmpuint (fixture->post_audit.second_image_pipeline_count, ==, 1u);
  g_assert_cmpuint (fixture->post_audit.post_up_b0_count, ==, 1u);
  g_assert_cmpuint (fixture->post_audit.second_b0_count, ==, 1u);
  g_assert_cmpuint (fixture->post_audit.third_cycle_command_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.retry_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.reopen_count, ==, 0u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_max_outstanding (
                     fixture->backend), ==, 1u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_max_out_outstanding (
                     fixture->backend), ==, 1u);
  client_clear (&client);
  fixture_free (fixture);
}

/* Regression for D278/14 attempt-2: the production real-USB path invokes
 * goodix_fpi_usb_backend_complete_receive() directly, not the context-level
 * helper.  The registered in-completed callback must therefore be the single
 * place that re-arms receive after an ACK so a later typed response can be
 * received on the second IN. */
static void
test_backend_in_completion_rearms_receive (void)
{
  Fixture *fixture = fixture_new_integrated_context ();
  g_autoptr(GBytes) ack = build_ack (0xa2, 0x01);
  gsize ack_length;
  const guint8 *ack_data = g_bytes_get_data (ack, &ack_length);

  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (fixture->backend),
                    ==, 1u);
  g_assert_cmpuint (fixture->in_submit_count, ==, 1u);

  /* Complete the physical A2 command OUT first; advance_phase() is gated on
   * out_pending being clear, exactly as on real USB. */
  {
    Submission *submission = pop_out (fixture);
    g_assert_nonnull (submission);
    complete_submission (fixture, submission, NULL);
  }

  /* Production-shaped backend-level IN completion. */
  goodix_fpi_usb_backend_complete_receive (fixture->backend,
                                           fixture->generation,
                                           ack_data, ack_length, NULL);

  /* The in-completed callback must have re-armed a fresh IN. */
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (fixture->backend),
                    ==, 1u);
  g_assert_cmpuint (fixture->in_submit_count, ==, 2u);
  g_assert_cmpuint (fixture->audit.ack_count, ==, 1u);

  /* Feed the typed A2 on the re-armed IN. */
  {
    g_autoptr(GBytes) typed = typed_for_phase (
      fixture, GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2);
    gsize typed_length;
    const guint8 *typed_data = g_bytes_get_data (typed, &typed_length);
    goodix_fpi_usb_backend_complete_receive (fixture->backend,
                                             fixture->generation,
                                             typed_data, typed_length, NULL);
  }
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_A8);
  g_assert_cmpuint (fixture->audit.typed_response_count, ==, 1u);
  g_assert_cmpuint (g_queue_get_length (fixture->out), ==, 1u);

  /* Cancel the session and drain the backend so fixture_free() succeeds. */
  goodix_secure_session_cancel (
    goodix_device_context_get_secure_session (fixture->context),
    "test closure");
  while (!g_queue_is_empty (fixture->out))
    {
      Submission *submission = pop_out (fixture);
      goodix_fpi_usb_backend_complete_out (fixture->backend,
                                           submission->generation, NULL);
      submission_free (submission);
    }
  if (goodix_fpi_usb_backend_get_outstanding (fixture->backend) != 0u)
    goodix_device_context_complete_receive (
      fixture->context, fixture->generation, NULL, 0, NULL);

  fixture_free (fixture);
}

static void
complete_backend_a0 (Fixture *fixture,
                     GBytes  *frame)
{
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);

  goodix_fpi_usb_backend_complete_receive (fixture->backend,
                                           fixture->generation,
                                           data, length, NULL);
}

static void
test_backend_pre_ack_typed_fail_closed (void)
{
  Fixture *fixture = fixture_new_integrated_context ();
  g_autoptr(GBytes) typed = typed_for_phase (
    fixture, GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2);
  Submission *submission = pop_out (fixture);

  complete_submission (fixture, submission, NULL);
  complete_backend_a0 (fixture, typed);
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_TERMINAL);
  g_assert_cmpint (fixture->audit.protocol_failure_kind, ==,
                   GOODIX_PROTOCOL_FAILURE_TYPED_SHAPE_MISMATCH);
  g_assert_cmpuint (fixture->audit.ack_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.typed_response_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.reentry_pre_ack_typed_discard_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.retry_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.transport_reopen_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.device_reset_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.clear_halt_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.persistent_write_count, ==, 0u);
  fixture_free (fixture);
}

static void
close_started_integrated_fixture (Fixture *fixture)
{
  goodix_secure_session_cancel (fixture->session, "integrated test closure");
  while (!g_queue_is_empty (fixture->out))
    {
      Submission *submission = pop_out (fixture);
      complete_submission (fixture, submission, NULL);
    }
  if (goodix_fpi_usb_backend_get_outstanding (fixture->backend) != 0u)
    goodix_device_context_complete_receive (
      fixture->context, fixture->generation, NULL, 0, NULL);
  fixture_free (fixture);
}

static void
assert_sync_pass_and_start_a2 (Fixture *fixture)
{
  GoodixPreSessionRxSyncAudit sync_audit;

  complete_pre_session_sync_timeout (fixture);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_delivery_count (
                     fixture->backend), ==, 0u);
  g_assert_cmpuint (g_queue_get_length (fixture->out), ==, 0u);
  start_integrated_secure_session (fixture);
  goodix_device_context_get_pre_session_rx_sync_audit (
    fixture->context, &sync_audit);
  g_assert_true (sync_audit.first_protocol_out_after_rx_sync);
  g_assert_cmpuint (g_queue_get_length (fixture->out), ==, 1u);
}

static void
complete_current_a2_to_a8 (Fixture *fixture)
{
  g_autoptr(GBytes) ack = build_ack (0xa2, 0x01);
  g_autoptr(GBytes) typed = typed_for_phase (
    fixture, GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2);
  Submission *submission = pop_out (fixture);

  complete_submission (fixture, submission, NULL);
  complete_backend_a0 (fixture, ack);
  complete_backend_a0 (fixture, typed);
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_A8);
}

static void
test_pre_session_rx_sync_clean_start (void)
{
  Fixture *fixture = fixture_new_integrated_epoch ();
  GoodixPreSessionRxSyncAudit sync_audit;
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_device_context_begin_pre_session_rx_sync (
    fixture->context, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (fixture->in_submit_count, ==, 1u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_last_in_timeout_ms (
                     fixture->backend), ==,
                   GOODIX_PRE_SESSION_RX_QUIET_TIMEOUT_MS);
  g_assert_cmpint (goodix_fpi_usb_backend_get_receive_purpose (
                    fixture->backend), ==,
                   GOODIX_USB_RECEIVE_PRE_SESSION_SYNC_RX);
  assert_sync_pass_and_start_a2 (fixture);
  goodix_device_context_get_pre_session_rx_sync_audit (
    fixture->context, &sync_audit);
  g_assert_true (sync_audit.pre_session_rx_sync_started);
  g_assert_true (sync_audit.pre_session_rx_sync_completed);
  g_assert_true (sync_audit.pre_session_rx_quiet_boundary);
  g_assert_cmpuint (sync_audit.pre_session_rx_discarded_completion_count,
                    ==, 0u);
  g_assert_cmpuint (sync_audit.pre_session_rx_discarded_byte_count, ==, 0u);
  g_assert_cmpuint (sync_audit.pre_session_rx_timeout_count, ==, 1u);
  g_assert_cmpuint (sync_audit.pre_session_rx_max_outstanding, ==, 1u);
  g_assert_cmpuint (fixture->audit.command_count, ==, 1u);
  complete_current_a2_to_a8 (fixture);
  close_started_integrated_fixture (fixture);
}

static void
test_pre_session_rx_sync_residue_chain (void)
{
  Fixture *fixture = fixture_new_integrated_epoch ();
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) typed = typed_for_phase (
    fixture, GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2);
  g_autoptr(GBytes) ack = build_ack (0xa2, 0x01);
  gsize typed_length;
  gsize ack_length;
  const guint8 *typed_data = g_bytes_get_data (typed, &typed_length);
  const guint8 *ack_data = g_bytes_get_data (ack, &ack_length);
  g_autoptr(GByteArray) combined = g_byte_array_sized_new (
    (guint) (typed_length + ack_length + typed_length));
  GoodixPreSessionRxSyncAudit sync_audit;

  g_byte_array_append (combined, typed_data, (guint) typed_length);
  g_byte_array_append (combined, ack_data, (guint) ack_length);
  g_byte_array_append (combined, typed_data, (guint) typed_length);
  g_assert_true (goodix_device_context_begin_pre_session_rx_sync (
    fixture->context, &error));
  g_assert_no_error (error);

  goodix_device_context_complete_receive (
    fixture->context, fixture->generation, typed_data, typed_length, NULL);
  goodix_device_context_complete_receive (
    fixture->context, fixture->generation, ack_data, ack_length, NULL);
  goodix_device_context_complete_receive (
    fixture->context, fixture->generation, typed_data, typed_length, NULL);
  goodix_device_context_complete_receive (
    fixture->context, fixture->generation, combined->data, combined->len, NULL);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_delivery_count (
                     fixture->backend), ==, 0u);
  g_assert_cmpuint (fixture->audit.command_count, ==, 0u);
  g_assert_cmpuint (g_queue_get_length (fixture->out), ==, 0u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_outstanding (
                     fixture->backend), ==, 1u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_max_outstanding (
                     fixture->backend), ==, 1u);
  assert_sync_pass_and_start_a2 (fixture);
  goodix_device_context_get_pre_session_rx_sync_audit (
    fixture->context, &sync_audit);
  g_assert_cmpuint (sync_audit.pre_session_rx_discarded_completion_count,
                    ==, 4u);
  g_assert_cmpuint (sync_audit.pre_session_rx_discarded_byte_count, ==,
                    typed_length * 4u + ack_length * 2u);
  complete_current_a2_to_a8 (fixture);
  close_started_integrated_fixture (fixture);
}

static gint64
synthetic_sync_clock (gpointer user_data)
{
  return *(gint64 *) user_data;
}

static void
test_pre_session_rx_sync_negative_bounds (void)
{
  /* A non-timeout GUsb transport error is terminal before A2. */
  {
    Fixture *fixture = fixture_new_integrated_epoch ();
    g_autoptr(GError) error = NULL;
    g_autoptr(GError) io_error = g_error_new_literal (
      G_USB_DEVICE_ERROR, G_USB_DEVICE_ERROR_IO, "synthetic USB I/O error");
    GoodixPreSessionRxSyncAudit audit;

    g_assert_true (goodix_device_context_begin_pre_session_rx_sync (
      fixture->context, &error));
    goodix_device_context_complete_receive (
      fixture->context, fixture->generation, NULL, 0, io_error);
    goodix_device_context_get_pre_session_rx_sync_audit (
      fixture->context, &audit);
    g_assert_cmpint (audit.pre_session_rx_result, ==,
                     GOODIX_PRE_SESSION_RX_SYNC_FAIL_CLOSED);
    g_assert_cmpuint (audit.pre_session_rx_non_timeout_error_count, ==, 1u);
    g_assert_cmpuint (g_queue_get_length (fixture->out), ==, 0u);
    fixture_free (fixture);
  }

  /* A seventeenth non-empty completion exceeds the explicit count bound. */
  {
    Fixture *fixture = fixture_new_integrated_epoch ();
    g_autoptr(GError) error = NULL;
    const guint8 byte = 0x5a;

    g_assert_true (goodix_device_context_begin_pre_session_rx_sync (
      fixture->context, &error));
    for (guint i = 0; i <= GOODIX_PRE_SESSION_RX_MAX_COMPLETIONS; i++)
      goodix_device_context_complete_receive (
        fixture->context, fixture->generation, &byte, 1, NULL);
    g_assert_cmpint (goodix_device_context_get_pre_session_rx_sync_result (
                      fixture->context), ==,
                     GOODIX_PRE_SESSION_RX_SYNC_FAIL_CLOSED);
    g_assert_cmpuint (g_queue_get_length (fixture->out), ==, 0u);
    fixture_free (fixture);
  }

  /* Byte and total-duration bounds fail independently and before A2. */
  {
    Fixture *fixture = fixture_new_integrated_epoch ();
    g_autoptr(GError) error = NULL;
    g_autofree guint8 *large = g_malloc0 (
      GOODIX_PRE_SESSION_RX_MAX_BYTES + 1u);

    g_assert_true (goodix_device_context_begin_pre_session_rx_sync (
      fixture->context, &error));
    goodix_device_context_complete_receive (
      fixture->context, fixture->generation, large,
      GOODIX_PRE_SESSION_RX_MAX_BYTES + 1u, NULL);
    g_assert_cmpint (goodix_device_context_get_pre_session_rx_sync_result (
                      fixture->context), ==,
                     GOODIX_PRE_SESSION_RX_SYNC_FAIL_CLOSED);
    fixture_free (fixture);
  }
  {
    Fixture *fixture = fixture_new_integrated_epoch ();
    g_autoptr(GError) error = NULL;
    gint64 now = 1000000;
    const guint8 byte = 0x5a;

    goodix_device_context_set_pre_session_rx_sync_clock (
      fixture->context, synthetic_sync_clock, &now);
    g_assert_true (goodix_device_context_begin_pre_session_rx_sync (
      fixture->context, &error));
    now += (GOODIX_PRE_SESSION_RX_MAX_TOTAL_MS -
            GOODIX_PRE_SESSION_RX_QUIET_TIMEOUT_MS + 1u) * 1000u;
    goodix_device_context_complete_receive (
      fixture->context, fixture->generation, &byte, 1, NULL);
    g_assert_cmpint (goodix_device_context_get_pre_session_rx_sync_result (
                      fixture->context), ==,
                     GOODIX_PRE_SESSION_RX_SYNC_FAIL_CLOSED);
    fixture_free (fixture);
  }
  {
    Fixture *fixture = fixture_new_integrated_epoch ();
    g_autoptr(GError) error = NULL;
    g_autoptr(GError) timeout = g_error_new_literal (
      G_USB_DEVICE_ERROR, G_USB_DEVICE_ERROR_TIMED_OUT,
      "synthetic late GUsb bulk timeout");
    gint64 now = 1000000;

    goodix_device_context_set_pre_session_rx_sync_clock (
      fixture->context, synthetic_sync_clock, &now);
    g_assert_true (goodix_device_context_begin_pre_session_rx_sync (
      fixture->context, &error));
    now += (GOODIX_PRE_SESSION_RX_MAX_TOTAL_MS + 1u) * 1000u;
    goodix_device_context_complete_receive (
      fixture->context, fixture->generation, NULL, 0, timeout);
    g_assert_cmpint (goodix_device_context_get_pre_session_rx_sync_result (
                      fixture->context), ==,
                     GOODIX_PRE_SESSION_RX_SYNC_FAIL_CLOSED);
    g_assert_cmpuint (g_queue_get_length (fixture->out), ==, 0u);
    fixture_free (fixture);
  }
}

static void
test_pre_session_rx_sync_out_and_start_gates (void)
{
  Fixture *fixture = fixture_new_integrated_epoch ();
  g_autoptr(GError) error = NULL;
  g_autoptr(GError) gate_error = NULL;
  g_autoptr(GBytes) bytes = g_bytes_new_static ("x", 1);

  g_assert_true (goodix_device_context_begin_pre_session_rx_sync (
    fixture->context, &error));
  g_assert_false (goodix_fpi_usb_backend_submit_out (
    fixture->backend, fixture->generation, bytes, &gate_error));
  g_assert_error (gate_error,
                  g_quark_from_static_string ("goodix-fpi-usb-backend-error"),
                  2);
  g_clear_error (&gate_error);
  g_assert_false (goodix_device_context_start_secure_session (
    fixture->context, &fixture->material, schedule_seam, fixture,
    &fixture->audit, &fixture->tls_audit, &gate_error));
  g_assert_error (gate_error, G_IO_ERROR, G_IO_ERROR_CLOSED);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_submit_count (
                     fixture->backend), ==, 0u);
  g_assert_null (goodix_device_context_get_secure_session (fixture->context));
  complete_pre_session_sync_timeout (fixture);
  fixture_free (fixture);
}

static void
test_strict_protocol_after_pre_session_sync (void)
{
  /* Duplicate ACK after sync is terminal. */
  {
    Fixture *fixture = fixture_new_integrated_context ();
    g_autoptr(GBytes) ack = build_ack (0xa2, 0x01);
    Submission *submission = pop_out (fixture);

    complete_submission (fixture, submission, NULL);
    complete_backend_a0 (fixture, ack);
    complete_backend_a0 (fixture, ack);
    g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                     GOODIX_SECURE_PHASE_TERMINAL);
    g_assert_cmpint (fixture->audit.protocol_failure_kind, ==,
                     GOODIX_PROTOCOL_FAILURE_ACK_SHAPE_MISMATCH);
    fixture_free (fixture);
  }

  /* Wrong ACK status after sync is terminal. */
  {
    Fixture *fixture = fixture_new_integrated_context ();
    g_autoptr(GBytes) ack = build_ack (0xa2, 0x02);
    Submission *submission = pop_out (fixture);

    complete_submission (fixture, submission, NULL);
    complete_backend_a0 (fixture, ack);
    g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                     GOODIX_SECURE_PHASE_TERMINAL);
    g_assert_cmpint (fixture->audit.protocol_failure_kind, ==,
                     GOODIX_PROTOCOL_FAILURE_ACK_STATUS_REJECTED);
    fixture_free (fixture);
  }

  /* Wrong typed pin after a valid current ACK is terminal. */
  {
    Fixture *fixture = fixture_new_integrated_context ();
    g_autoptr(GBytes) ack = build_ack (0xa2, 0x01);
    guint8 wrong[3];
    g_autoptr(GBytes) typed = NULL;
    Submission *submission = pop_out (fixture);

    memcpy (wrong, fixture->a2, sizeof wrong);
    wrong[0] ^= 0xff;
    typed = build_response (0xa2, wrong, sizeof wrong);
    complete_submission (fixture, submission, NULL);
    complete_backend_a0 (fixture, ack);
    complete_backend_a0 (fixture, typed);
    g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                     GOODIX_SECURE_PHASE_TERMINAL);
    g_assert_cmpint (fixture->audit.protocol_failure_kind, ==,
                     GOODIX_PROTOCOL_FAILURE_TYPED_SHAPE_MISMATCH);
    fixture_free (fixture);
  }
}

static void
test_integrated_context_live_binding_host_only (void)
{
  Fixture *fixture = fixture_new_integrated_context ();
  TlsClient client;
  GoodixTlsServer *retained;

  while (goodix_secure_session_get_phase (fixture->session) <
         GOODIX_SECURE_PHASE_D1)
    respond_valid (fixture, 0, 0x01);
  respond_valid (fixture, 0, 0x01);
  client_init (&client, fixture);
  g_assert_true (pump_tls (fixture, &client, FALSE));
  retained = goodix_secure_session_get_tls_server (fixture->session);
  fixture->post_tls = goodix_device_context_get_post_tls_lifecycle (
    fixture->context);
  g_assert_nonnull (fixture->post_tls);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->post_tls), ==,
                   GOODIX_POST_TLS_PHASE_D4);

  drive_post_tls_two_acquisitions (fixture, &client);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->post_tls), ==,
                   GOODIX_POST_TLS_PHASE_STOP);
  g_assert_true (retained == goodix_device_context_get_tls_server (
                            fixture->context));
  g_assert_true (fixture->backend ==
                 goodix_device_context_get_fpi_usb_backend (fixture->context));
  g_assert_true (fixture->router ==
                 goodix_device_context_get_usb_router (fixture->context));
  g_assert_cmpuint (fixture->audit.command_count, ==, 14u);
  g_assert_cmpuint (fixture->tls_audit.handshake_count, ==, 1u);
  g_assert_cmpuint (fixture->tls_audit.secret_handoff_count, ==, 1u);
  g_assert_cmpuint (fixture->post_audit.first_image_pipeline_count, ==, 1u);
  g_assert_cmpuint (fixture->post_audit.second_image_pipeline_count, ==, 1u);
  g_assert_cmpuint (fixture->post_audit.rearm_0x32_count, ==, 1u);
  g_assert_cmpuint (fixture->post_audit.third_cycle_command_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.retry_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.reopen_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.device_reset_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.clear_halt_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.persistent_device_write_count, ==, 0u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (
                     fixture->backend), ==, 0u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_max_outstanding (
                     fixture->backend), ==, 1u);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_max_out_outstanding (
                     fixture->backend), ==, 1u);
  client_clear (&client);
  fixture_free (fixture);
}

static void
cancel_and_drain_integrated_context (Fixture *fixture)
{
  g_autoptr(GError) cancelled = g_error_new_literal (
    G_IO_ERROR, G_IO_ERROR_CANCELLED, "host-only operator cancellation");

  goodix_device_context_stop_operator_epoch (fixture->context);
  while (!g_queue_is_empty (fixture->out))
    complete_submission (fixture, pop_out (fixture), cancelled);
  if (goodix_fpi_usb_backend_get_outstanding (fixture->backend) != 0u)
    goodix_device_context_complete_receive (
      fixture->context, fixture->generation, NULL, 0, cancelled);
  g_assert_true (goodix_device_context_operator_epoch_is_drained (
    fixture->context));
}

static void
test_integrated_context_cancel_secure (void)
{
  Fixture *fixture = fixture_new_integrated_context ();

  cancel_and_drain_integrated_context (fixture);
  g_assert_true (goodix_device_context_get_terminal_fence (fixture->context));
  g_assert_cmpuint (fixture->audit.retry_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.transport_reopen_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.device_reset_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.clear_halt_count, ==, 0u);
  g_assert_cmpuint (fixture->audit.persistent_write_count, ==, 0u);
  fixture_free (fixture);
}

static void
test_integrated_context_cancel_post_tls (void)
{
  Fixture *fixture = fixture_new_integrated_context ();
  TlsClient client;

  while (goodix_secure_session_get_phase (fixture->session) <
         GOODIX_SECURE_PHASE_D1)
    respond_valid (fixture, 0, 0x01);
  respond_valid (fixture, 0, 0x01);
  client_init (&client, fixture);
  g_assert_true (pump_tls (fixture, &client, FALSE));
  fixture->post_tls = goodix_device_context_get_post_tls_lifecycle (
    fixture->context);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->post_tls), ==,
                   GOODIX_POST_TLS_PHASE_D4);
  cancel_and_drain_integrated_context (fixture);
  g_assert_cmpint (goodix_post_tls_lifecycle_get_phase (fixture->post_tls), ==,
                   GOODIX_POST_TLS_PHASE_TERMINAL);
  g_assert_cmpuint (fixture->post_audit.retry_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.reopen_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.device_reset_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.clear_halt_count, ==, 0u);
  g_assert_cmpuint (fixture->post_audit.persistent_device_write_count, ==, 0u);
  client_clear (&client);
  fixture_free (fixture);
}

static void
test_d1_client_hello_gate (void)
{
  const gsize split_points[] = { 5u, 11u };

  for (guint i = 0; i < G_N_ELEMENTS (split_points); i++)
    {
      Fixture *fixture = fixture_new ();
      TlsClient client;
      g_autoptr(GBytes) hello = NULL;
      gsize hello_length;
      const guint8 *hello_data;

      start_and_advance_to (fixture, GOODIX_SECURE_PHASE_D1);
      respond_valid (fixture, 0, 0x01);
      client_init (&client, fixture);
      hello = take_initial_client_hello (&client);
      hello_data = g_bytes_get_data (hello, &hello_length);
      g_assert_cmpuint (split_points[i], <, hello_length);

      feed_b0_payload (fixture, hello_data, split_points[i]);
      g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                       GOODIX_SECURE_PHASE_D1);
      g_assert_true (g_queue_is_empty (fixture->out));
      g_assert_cmpuint (fixture->audit.b0_physical_submit_count, ==, 0);
      g_assert_cmpuint (fixture->audit.retry_count, ==, 0);
      g_assert_cmpuint (fixture->audit.transport_reopen_count, ==, 0);
      g_assert_cmpuint (fixture->audit.device_reset_count, ==, 0);

      feed_b0_payload (fixture, hello_data + split_points[i],
                       hello_length - split_points[i]);
      g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                       GOODIX_SECURE_PHASE_TLS);
      g_assert_false (g_queue_is_empty (fixture->out));
      drain_server_records (fixture, &client, FALSE);
      g_assert_true (pump_tls (fixture, &client, FALSE));
      g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                       GOODIX_SECURE_PHASE_STOP);
      client_clear (&client);
      fixture_free (fixture);
    }

  {
    Fixture *fixture = fixture_new ();
    static const guint8 malformed[] = { 0x16, 0x03, 0x03, 0, 4,
                                        0xff, 0, 0, 0 };
    start_and_advance_to (fixture, GOODIX_SECURE_PHASE_D1);
    respond_valid (fixture, 0, 0x01);
    feed_b0_payload (fixture, malformed, sizeof malformed);
    g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                     GOODIX_SECURE_PHASE_TERMINAL);
    g_assert_cmpuint (fixture->audit.b0_physical_submit_count, ==, 0);
    g_assert_cmpuint (fixture->audit.retry_count, ==, 0);
    g_assert_cmpuint (fixture->audit.transport_reopen_count, ==, 0);
    g_assert_cmpuint (fixture->audit.device_reset_count, ==, 0);
    g_assert_false (fixture->audit.d4_reachable);
    fixture_free (fixture);
  }
}

static void
test_ack07_phase_policy (void)
{
  Fixture *fixture = fixture_new ();
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_secure_session_start (fixture->session, &error));
  g_assert_no_error (error);
  respond_valid (fixture, 0, 0x01);
  respond_valid (fixture, 0, 0x01);
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_E4);

  /* Direct D236 evidence: E4 ACK 0x07 plus the valid typed E4 response
   * advances exactly once and submits exactly one OEM cold-start A2. */
  respond_valid (fixture, 1, 0x07);
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_OEM_COLD_START_A2_1);
  g_assert_cmpuint (fixture->audit.command_count, ==, 4);

  /* Direct D236 evidence: OEM cold-start A2_1 ACK 0x07 plus the valid typed response
   * advances exactly once and submits exactly one CHIP_82 command. */
  respond_valid (fixture, 2, 0x07);
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_CHIP_82);
  g_assert_cmpuint (fixture->audit.command_count, ==, 5);

  /* D238's bounded cross-control inference covers every remaining
   * ACK-bearing pre-D1 phase. */
  while (goodix_secure_session_get_phase (fixture->session) <
         GOODIX_SECURE_PHASE_D1)
    respond_valid (fixture, 0, 0x07);
  g_assert_cmpuint (fixture->audit.ack_count, ==, 13);
  g_assert_cmpuint (fixture->audit.typed_response_count, ==, 8);
  g_assert_cmpuint (fixture->audit.command_count, ==, 14);
  {
    Submission *submission = pop_out (fixture);
    goodix_secure_session_cancel (fixture->session, "ACK07 matrix closure");
    complete_submission (fixture, submission, NULL);
  }
  fixture_free (fixture);
}

static void
test_ack_policy_and_response_failures (void)
{
  for (guint status_index = 0; status_index < 2; status_index++)
    {
      Fixture *fixture = fixture_new ();
      g_autoptr(GError) error = NULL;
      guint8 status = status_index == 0 ? 0x01 : 0x07;
      g_autoptr(GBytes) ack = NULL;
      g_autoptr(GBytes) typed = NULL;
      Submission *submission;
      start_and_advance_to (fixture, GOODIX_SECURE_PHASE_A8);
      submission = pop_out (fixture);
      complete_submission (fixture, submission, NULL);
      ack = build_ack (0xa8, status);
      typed = typed_for_phase (fixture, GOODIX_SECURE_PHASE_A8);
      feed_frames (fixture, ack, typed, 1);
      g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                       GOODIX_SECURE_PHASE_E4);
      submission = pop_out (fixture);
      complete_submission (fixture, submission, NULL);
      goodix_secure_session_cancel (fixture->session, "test closure");
      fixture_free (fixture);
    }

  for (guint variant = 0; variant < 8; variant++)
    {
      Fixture *fixture = fixture_new ();
      GoodixSecurePhase target = variant < 3 ? GOODIX_SECURE_PHASE_A8 :
                                                GOODIX_SECURE_PHASE_E4;
      g_autoptr(GBytes) response = NULL;
      Submission *submission;
      start_and_advance_to (fixture, target);
      submission = pop_out (fixture);
      complete_submission (fixture, submission, NULL);
      if (variant == 0)
        response = build_ack (0xa2, 0x01);       /* wrong echo */
      else if (variant == 1)
        response = build_ack (0xa8, 0x02);       /* bad A8 status */
      else if (variant == 2)
        response = build_response (0xa8, fixture->a2, 3); /* typed before ACK */
      else if (variant == 3)
        response = build_ack (0xe4, 0x02);
      else if (variant == 4)
        {
          static const guint8 short_ack[] = { 0xe4 };
          response = build_response (0xb0, short_ack, sizeof short_ack);
        }
      else
        {
          g_autoptr(GBytes) ack = build_ack (0xe4, 0x01);
          feed_frames (fixture, ack, NULL, 0);
          if (variant == 5)
            response = build_response (0xa2, fixture->a2, 3);
          else
            {
              guint8 e4[41] = {
                0x00, 0x03, 0x00, 0x02, 0xbb, 0x20, 0, 0, 0
              };
              memcpy (e4 + 9, fixture->validator, 32);
              if (variant == 6)
                e4[0] ^= 1;                    /* prefix */
              else
                e4[9] ^= 1;                    /* validator */
              response = build_response (0xe4, e4, sizeof e4);
            }
        }
      feed_frames (fixture, response, NULL, 0);
      g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                       GOODIX_SECURE_PHASE_TERMINAL);
      g_assert_cmpuint (fixture->terminal_count, ==, 1);
      fixture_free (fixture);
    }

  /* ACK alone cannot complete an ACK+typed phase. */
  {
    Fixture *fixture = fixture_new ();
    g_autoptr(GBytes) ack = NULL;
    Submission *submission;

    start_and_advance_to (fixture, GOODIX_SECURE_PHASE_E4);
    submission = pop_out (fixture);
    complete_submission (fixture, submission, NULL);
    ack = build_ack (0xe4, 0x07);
    feed_frames (fixture, ack, NULL, 0);
    g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                     GOODIX_SECURE_PHASE_E4);
    g_assert_cmpuint (fixture->audit.command_count, ==, 3);
    goodix_secure_session_cancel (fixture->session, "ACK-only test closure");
    fixture_free (fixture);
  }

  /* ACK-only phases reject an additional typed response. */
  {
    Fixture *fixture = fixture_new ();
    g_autoptr(GBytes) ack = NULL;
    g_autoptr(GBytes) typed = NULL;
    Submission *submission;

    start_and_advance_to (fixture, GOODIX_SECURE_PHASE_MODE_70);
    submission = pop_out (fixture);
    complete_submission (fixture, submission, NULL);
    ack = build_ack (0x70, 0x01);
    typed = build_response (0x70, fixture->a2, sizeof fixture->a2);
    feed_frames (fixture, ack, typed, 1);
    g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                     GOODIX_SECURE_PHASE_TERMINAL);
    fixture_clear_out (fixture);
    if (goodix_fpi_usb_backend_get_out_outstanding (fixture->backend) != 0)
      goodix_fpi_usb_backend_complete_out (fixture->backend,
                                            fixture->generation, NULL);
    fixture_free (fixture);
  }
}

static void
assert_reentry_stopped_before_a8 (Fixture *fixture)
{
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_TERMINAL);
  g_assert_cmpuint (fixture->audit.command_count, ==, 1);
  g_assert_cmpuint (fixture->audit.reentry_recovery_a2_submit_count, ==, 1);
  g_assert_cmpuint (fixture->audit.a8_submit_count, ==, 0);
  g_assert_cmpuint (fixture->audit.e4_submit_count, ==, 0);
  g_assert_cmpuint (fixture->audit.oem_cold_start_a2_1_submit_count, ==, 0);
  g_assert_cmpuint (fixture->audit.oem_cold_start_a2_2_submit_count, ==, 0);
  g_assert_cmpuint (fixture->audit.retry_count, ==, 0);
  g_assert_cmpuint (fixture->audit.transport_reopen_count, ==, 0);
  g_assert_cmpuint (fixture->audit.device_reset_count, ==, 0);
  g_assert_cmpuint (fixture->audit.clear_halt_count, ==, 0);
  g_assert_cmpuint (fixture->audit.persistent_write_count, ==, 0);
  g_assert_cmpint (fixture->audit.reentry_recovery_a2_result_class, ==,
                   GOODIX_REENTRY_RECOVERY_A2_FAIL_CLOSED);
}

static void
test_reentry_recovery_failure_boundary (void)
{
  /* R2: ACK timeout is ambiguous and terminal; no next command. */
  {
    Fixture *fixture = fixture_new ();
    g_autoptr(GError) error = NULL;
    Submission *submission;

    g_assert_true (goodix_secure_session_start (fixture->session, &error));
    submission = pop_out (fixture);
    complete_submission (fixture, submission, NULL);
    goodix_secure_session_cancel (fixture->session, "reentry ACK timeout");
    assert_reentry_stopped_before_a8 (fixture);
    fixture_free (fixture);
  }

  /* R3: ACK mismatch/status rejection is terminal. */
  for (guint variant = 0; variant < 2; variant++)
    {
      Fixture *fixture = fixture_new ();
      g_autoptr(GError) error = NULL;
      g_autoptr(GBytes) bad_ack = NULL;
      Submission *submission;

      g_assert_true (goodix_secure_session_start (fixture->session, &error));
      submission = pop_out (fixture);
      complete_submission (fixture, submission, NULL);
      bad_ack = build_ack (variant == 0 ? 0xa8 : 0xa2,
                           variant == 0 ? 0x01 : 0x02);
      feed_frames (fixture, bad_ack, NULL, 0);
      assert_reentry_stopped_before_a8 (fixture);
      fixture_free (fixture);
    }

  /* R4/R5: typed timeout or target-pin mismatch after a strict ACK stops. */
  for (guint variant = 0; variant < 2; variant++)
    {
      Fixture *fixture = fixture_new ();
      g_autoptr(GError) error = NULL;
      g_autoptr(GBytes) ack = NULL;
      Submission *submission;

      g_assert_true (goodix_secure_session_start (fixture->session, &error));
      submission = pop_out (fixture);
      complete_submission (fixture, submission, NULL);
      ack = build_ack (0xa2, 0x07);
      feed_frames (fixture, ack, NULL, 0);
      if (variant == 0)
        goodix_secure_session_cancel (fixture->session,
                                      "reentry typed timeout");
      else
        {
          guint8 bad_body[3] = { 0, 0, 0 };
          g_autoptr(GBytes) bad_typed = build_response (
            0xa2, bad_body, sizeof bad_body);
          feed_frames (fixture, bad_typed, NULL, 0);
        }
      assert_reentry_stopped_before_a8 (fixture);
      fixture_free (fixture);
    }

  /* R6: an E4-shaped response is evidence, not a discard candidate. */
  {
    Fixture *fixture = fixture_new ();
    g_autoptr(GError) error = NULL;
    guint8 e4[41] = { 0x00, 0x03, 0x00, 0x02, 0xbb, 0x20, 0, 0, 0 };
    g_autoptr(GBytes) unexpected_e4 = NULL;
    Submission *submission;

    memcpy (e4 + 9, fixture->validator, sizeof fixture->validator);
    g_assert_true (goodix_secure_session_start (fixture->session, &error));
    submission = pop_out (fixture);
    complete_submission (fixture, submission, NULL);
    unexpected_e4 = build_response (0xe4, e4, sizeof e4);
    feed_frames (fixture, unexpected_e4, NULL, 0);
    assert_reentry_stopped_before_a8 (fixture);
    fixture_free (fixture);
  }

  /* R7/R8: A8 failure or a duplicate recovery completion cannot reach E4. */
  for (guint duplicate = 0; duplicate < 2; duplicate++)
    {
      Fixture *fixture = fixture_new ();
      g_autoptr(GError) error = NULL;
      g_autoptr(GBytes) duplicate_or_bad = NULL;
      Submission *reentry_submission;
      Submission *a8_submission;

      g_assert_true (goodix_secure_session_start (fixture->session, &error));
      reentry_submission = pop_out (fixture);
      complete_submission (fixture, reentry_submission, NULL);
      {
        g_autoptr(GBytes) ack = build_ack (0xa2, 0x07);
        g_autoptr(GBytes) typed = typed_for_phase (
          fixture, GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2);
        feed_frames (fixture, ack, typed, 1);
      }
      g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                       GOODIX_SECURE_PHASE_A8);
      a8_submission = pop_out (fixture);
      complete_submission (fixture, a8_submission, NULL);
      duplicate_or_bad = duplicate ?
        typed_for_phase (fixture, GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2) :
        build_ack (0xa8, 0x02);
      feed_frames (fixture, duplicate_or_bad, NULL, 0);
      g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                       GOODIX_SECURE_PHASE_TERMINAL);
      g_assert_cmpuint (fixture->audit.command_count, ==, 2);
      g_assert_cmpuint (fixture->audit.a8_submit_count, ==, 1);
      g_assert_cmpuint (fixture->audit.e4_submit_count, ==, 0);
      g_assert_cmpuint (fixture->audit.oem_cold_start_a2_1_submit_count, ==, 0);
      g_assert_cmpuint (fixture->audit.retry_count, ==, 0);
      fixture_free (fixture);
    }

  /* R9: the one start attempt is the only recovery attempt. */
  {
    Fixture *fixture = fixture_new ();
    g_autoptr(GError) error = NULL;
    g_autoptr(GError) second_error = NULL;
    Submission *submission;

    g_assert_true (goodix_secure_session_start (fixture->session, &error));
    submission = pop_out (fixture);
    g_assert_false (goodix_secure_session_start (fixture->session,
                                                  &second_error));
    g_assert_nonnull (second_error);
    g_assert_cmpuint (fixture->audit.command_count, ==, 1);
    g_assert_cmpuint (fixture->audit.reentry_recovery_a2_submit_count, ==, 1);
    g_assert_cmpuint (fixture->audit.a8_submit_count, ==, 0);
    g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                     GOODIX_SECURE_PHASE_TERMINAL);
    complete_submission (fixture, submission, NULL);
    fixture_free (fixture);
  }
}

static void
test_typed_length_hash_and_90 (void)
{
  const GoodixSecurePhase phases[] = {
    GOODIX_SECURE_PHASE_OEM_COLD_START_A2_1, GOODIX_SECURE_PHASE_CHIP_82,
    GOODIX_SECURE_PHASE_OTP_A6, GOODIX_SECURE_PHASE_CONFIG_90
  };

  for (guint i = 0; i < G_N_ELEMENTS (phases); i++)
    for (guint wrong_length = 0; wrong_length < 2; wrong_length++)
      {
        Fixture *fixture = fixture_new ();
        GoodixSecurePhase phase = phases[i];
        g_autoptr(GBytes) ack = NULL;
        g_autoptr(GBytes) bad = NULL;
        g_autofree guint8 *body = NULL;
        gsize body_length;
        const guint8 *valid_body;
        g_autoptr(GBytes) valid = NULL;
        Submission *submission;
        start_and_advance_to (fixture, phase);
        submission = pop_out (fixture);
        complete_submission (fixture, submission, NULL);
        ack = build_ack (control_for_phase (phase), 0x01);
        feed_frames (fixture, ack, NULL, 0);
        valid = typed_for_phase (fixture, phase);
        {
          GoodixA0Message message = { 0 };
          g_autoptr(GError) error = NULL;
          g_assert_true (goodix_a0_parse_frame (valid,
                                                control_for_phase (phase),
                                                &message, &error));
          valid_body = g_bytes_get_data (message.body, &body_length);
          body = g_memdup2 (valid_body, body_length);
          if (wrong_length != 0)
            body_length--;
          else
            body[0] ^= 1;
          bad = build_response (control_for_phase (phase), body, body_length);
          goodix_a0_message_clear (&message);
        }
        feed_frames (fixture, bad, NULL, 0);
        g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                         GOODIX_SECURE_PHASE_TERMINAL);
        fixture_free (fixture);
      }
}

static void
test_unexpected_classes_and_terminal (void)
{
  Fixture *fixture = fixture_new ();
  static const guint8 tls_like[] = { 0x16, 0x03, 0x03, 0, 1, 0 };
  guint8 header[4] = { 0xb0, sizeof tls_like, 0,
                       (guint8) (0xb0u + sizeof tls_like) };
  g_autoptr(GByteArray) b0 = g_byte_array_new ();
  g_byte_array_append (b0, header, sizeof header);
  g_byte_array_append (b0, tls_like, sizeof tls_like);
  g_autoptr(GError) error = NULL;
  g_assert_true (goodix_secure_session_start (fixture->session, &error));
  {
    Submission *submission = pop_out (fixture);
    complete_submission (fixture, submission, NULL);
  }
  feed_completion (fixture, b0->data, b0->len, fixture->generation);
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_TERMINAL);
  fixture_free (fixture);

  fixture = fixture_new ();
  start_and_advance_to (fixture, GOODIX_SECURE_PHASE_D1);
  respond_valid (fixture, 0, 0x01);
  {
    g_autoptr(GBytes) a0 = build_ack (0xd1, 0x01);
    gsize length;
    const guint8 *data = g_bytes_get_data (a0, &length);
    feed_completion (fixture, data, length, fixture->generation);
  }
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_TERMINAL);
  fixture_free (fixture);

  fixture = fixture_new ();
  {
    g_autoptr(GError) start_error = NULL;
    g_autoptr(GBytes) ack = build_ack (0xa2, 0x01);
    g_autoptr(GBytes) typed = typed_for_phase (fixture,
      GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2);
    Submission *submission;

    g_assert_true (goodix_secure_session_start (fixture->session,
                                                 &start_error));
    submission = pop_out (fixture);
    /* Complete the logical response before its physical OUT completion, then
     * prove a duplicate typed response fails closed. */
    feed_frames (fixture, ack, typed, 1);
    feed_frames (fixture, typed, NULL, 0);
    g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                     GOODIX_SECURE_PHASE_TERMINAL);
    complete_submission (fixture, submission, NULL);
  }
  fixture_free (fixture);
}

static void
test_material_gates (void)
{
  for (guint variant = 0; variant < 7; variant++)
    {
      Fixture *fixture = fixture_new ();
      GoodixSecureSessionMaterial material = fixture->material;
      g_autoptr(GError) error = NULL;
      GoodixSecureSession *rejected;

      goodix_secure_session_free (fixture->session);
      fixture->session = NULL;
      if (variant == 0)
        material.config90_length--;
      else if (variant == 1)
        material.config90_sha256[0] ^= 1;
      else if (variant == 2)
        {
          fixture->config[222] ^= 1;
          digest (fixture->config, sizeof fixture->config,
                  material.config90_sha256);
        }
      else if (variant == 3)
        {
          fixture->config[119] ^= 1;
          set_config_finalizer (fixture->config);
          digest (fixture->config, sizeof fixture->config,
                  material.config90_sha256);
        }
      else if (variant == 4)
        memset (material.a2_response_sha256, 0, 32);
      else if (variant == 5)
        material.psk_length = 31;
      else
        material.e4_validator = NULL;
      rejected = goodix_secure_session_new (
        fixture->backend, fixture->generation, &material,
        schedule_seam, fixture, terminal_seam, fixture,
        &fixture->audit, &fixture->tls_audit, &error);
      g_assert_null (rejected);
      g_assert_nonnull (error);
      fixture_free (fixture);
    }
}

static void
test_cancel_generation_and_out_order (void)
{
  Fixture *fixture = fixture_new ();
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) extra = g_bytes_new_static ("x", 1);
  Submission *submission;

  g_assert_true (goodix_secure_session_start (fixture->session, &error));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_outstanding (
                     fixture->backend), ==, 1);
  g_assert_false (goodix_fpi_usb_backend_submit_out (
    fixture->backend, fixture->generation, extra, &error));
  g_assert_nonnull (error);
  g_clear_error (&error);
  submission = pop_out (fixture);
  goodix_secure_session_cancel (fixture->session, "cancel during A8");
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_TERMINAL);
  goodix_fpi_usb_backend_complete_out (fixture->backend,
                                        fixture->generation - 1u, NULL);
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_outstanding (
                     fixture->backend), ==, 1);
  complete_submission (fixture, submission, NULL);
  g_assert_true (goodix_fpi_usb_backend_is_drained (fixture->backend));
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_TERMINAL);
  fixture_free (fixture);

  /* The backend also exposes a synchronous host seam.  Completion must see
   * session ownership even when it fires inside submit_out(). */
  fixture = fixture_new ();
  goodix_fpi_usb_backend_set_submit_seam (fixture->backend,
                                           submit_seam, fixture);
  g_assert_true (goodix_secure_session_start (fixture->session, &error));
  g_assert_cmpuint (goodix_fpi_usb_backend_get_out_outstanding (
                     fixture->backend), ==, 0);
  submission = pop_out (fixture);
  assert_command_shape (fixture, GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2,
                        submission->bytes);
  submission_free (submission);
  {
    g_autoptr(GBytes) ack = build_ack (0xa2, 0x01);
    g_autoptr(GBytes) typed = typed_for_phase (fixture,
      GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2);
    feed_frames (fixture, ack, typed, 1);
  }
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_A8);
  submission = pop_out (fixture);
  assert_command_shape (fixture, GOODIX_SECURE_PHASE_A8, submission->bytes);
  submission_free (submission);
  {
    g_autoptr(GBytes) ack = build_ack (0xa8, 0x01);
    g_autoptr(GBytes) typed = typed_for_phase (fixture,
                                               GOODIX_SECURE_PHASE_A8);
    feed_frames (fixture, ack, typed, 1);
  }
  g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                   GOODIX_SECURE_PHASE_E4);
  submission = pop_out (fixture);
  assert_command_shape (fixture, GOODIX_SECURE_PHASE_E4, submission->bytes);
  submission_free (submission);
  goodix_secure_session_cancel (fixture->session, "sync-seam test closure");
  fixture_free (fixture);
}

static void
test_cancel_major_phases (void)
{
  const GoodixSecurePhase phases[] = {
    GOODIX_SECURE_PHASE_A8,
    GOODIX_SECURE_PHASE_E4,
    GOODIX_SECURE_PHASE_CONFIG_90,
    GOODIX_SECURE_PHASE_D1,
  };

  for (guint i = 0; i < G_N_ELEMENTS (phases); i++)
    {
      Fixture *fixture = fixture_new ();
      Submission *submission;
      start_and_advance_to (fixture, phases[i]);
      submission = pop_out (fixture);
      goodix_secure_session_cancel (fixture->session, "major-phase cancel");
      g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                       GOODIX_SECURE_PHASE_TERMINAL);
      complete_submission (fixture, submission, NULL);
      g_assert_true (goodix_fpi_usb_backend_is_drained (fixture->backend));
      fixture_free (fixture);
    }
}

static void
test_wrong_tls_credentials (void)
{
  for (guint variant = 0; variant < 2; variant++)
    {
      Fixture *fixture = fixture_new ();
      TlsClient client;
      start_and_advance_to (fixture, GOODIX_SECURE_PHASE_D1);
      respond_valid (fixture, 0, 0x01);
      client_init (&client, fixture);
      client.wrong_identity = variant == 0;
      client.wrong_psk = variant == 1;
      g_assert_false (pump_tls (fixture, &client, FALSE));
      g_assert_cmpint (goodix_secure_session_get_phase (fixture->session), ==,
                       GOODIX_SECURE_PHASE_TERMINAL);
      fixture_clear_out (fixture);
      if (goodix_fpi_usb_backend_get_out_outstanding (fixture->backend) != 0)
        goodix_fpi_usb_backend_complete_out (fixture->backend,
                                              fixture->generation, NULL);
      client_clear (&client);
      fixture_free (fixture);
    }
}

int
main (int argc,
      char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/goodix/d278/a0-vectors-malformed",
                   test_a0_vectors_and_malformed);
  g_test_add_func ("/goodix/d278/happy-path-real-tls", test_happy_path);
  g_test_add_func ("/goodix/d278/retained-tls-post-handshake-handoff",
                   test_retained_tls_post_handshake_handoff);
  g_test_add_func ("/goodix/d278/reentry-tls-to-two-acquisitions-composed",
                   test_reentry_tls_to_two_acquisitions_composed);
  g_test_add_func ("/goodix/d278/backend-in-completion-rearms-receive",
                   test_backend_in_completion_rearms_receive);
  g_test_add_func ("/goodix/d278/backend-pre-ack-typed-fail-closed",
                   test_backend_pre_ack_typed_fail_closed);
  g_test_add_func ("/goodix/d278/pre-session-rx-sync-clean-start",
                   test_pre_session_rx_sync_clean_start);
  g_test_add_func ("/goodix/d278/pre-session-rx-sync-residue-chain",
                   test_pre_session_rx_sync_residue_chain);
  g_test_add_func ("/goodix/d278/pre-session-rx-sync-negative-bounds",
                   test_pre_session_rx_sync_negative_bounds);
  g_test_add_func ("/goodix/d278/pre-session-rx-sync-out-start-gates",
                   test_pre_session_rx_sync_out_and_start_gates);
  g_test_add_func ("/goodix/d278/strict-protocol-after-pre-session-sync",
                   test_strict_protocol_after_pre_session_sync);
  g_test_add_func ("/goodix/d278/integrated-context-live-binding-host-only",
                   test_integrated_context_live_binding_host_only);
  g_test_add_func ("/goodix/d278/integrated-context-cancel-secure",
                   test_integrated_context_cancel_secure);
  g_test_add_func ("/goodix/d278/integrated-context-cancel-post-tls",
                   test_integrated_context_cancel_post_tls);
  g_test_add_func ("/goodix/d278/d1-client-hello-gate",
                   test_d1_client_hello_gate);
  g_test_add_func ("/goodix/d278/ack07-phase-policy",
                   test_ack07_phase_policy);
  g_test_add_func ("/goodix/d278/ack-policy-response-failures",
                   test_ack_policy_and_response_failures);
  g_test_add_func ("/goodix/d278/reentry-recovery-failure-boundary",
                   test_reentry_recovery_failure_boundary);
  g_test_add_func ("/goodix/d278/typed-length-hash-90",
                   test_typed_length_hash_and_90);
  g_test_add_func ("/goodix/d278/unexpected-classes-terminal",
                   test_unexpected_classes_and_terminal);
  g_test_add_func ("/goodix/d278/material-gates", test_material_gates);
  g_test_add_func ("/goodix/d278/cancel-generation-out-order",
                   test_cancel_generation_and_out_order);
  g_test_add_func ("/goodix/d278/cancel-major-phases",
                   test_cancel_major_phases);
  g_test_add_func ("/goodix/d278/wrong-tls-credentials",
                   test_wrong_tls_credentials);
  return g_test_run ();
}
