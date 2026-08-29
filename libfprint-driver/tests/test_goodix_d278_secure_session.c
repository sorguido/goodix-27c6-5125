/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Deterministic host-only integration tests for the native D278/01 chain. */
#include "goodix_a0_protocol.h"
#include "goodix_fpi_usb_backend.h"
#include "goodix_secure_session.h"
#include "goodix_usb_router.h"

#include <openssl/ssl.h>
#include <string.h>

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
  GoodixSecureSessionMaterial material;
  GoodixSecureSessionAudit audit;
  GoodixTlsAudit tls_audit;
  GQueue *out;
  GByteArray *server_record;
  guint64 generation;
  guint in_submit_count;
  guint terminal_count;
  guint schedule_count;
  guint64 scheduled_generation;
  gboolean schedule_pending;
  guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH];
  guint8 validator[32];
  guint8 a2[3];
  guint8 chip[4];
  guint8 otp[64];
  guint8 psk[GOODIX_SECURE_SESSION_PSK_LENGTH];
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
  goodix_secure_session_free (fixture->session);
  goodix_fpi_usb_backend_free (fixture->backend);
  goodix_usb_router_free (fixture->router);
  g_queue_free (fixture->out);
  g_byte_array_unref (fixture->server_record);
  g_free (fixture);
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
    case GOODIX_SECURE_PHASE_A2_1:
    case GOODIX_SECURE_PHASE_A2_2:
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
    case GOODIX_SECURE_PHASE_A2_1:
    case GOODIX_SECURE_PHASE_A2_2: return 0xa2;
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
  if (phase >= GOODIX_SECURE_PHASE_DAC_220 &&
      phase <= GOODIX_SECURE_PHASE_DAC_23A)
    {
      gsize body_length;
      const guint8 *body = g_bytes_get_data (message.body, &body_length);
      guint index = (guint) phase - GOODIX_SECURE_PHASE_DAC_220;
      static const guint8 addresses[4][2] = {
        { 0x20, 0x02 }, { 0x36, 0x02 }, { 0x38, 0x02 }, { 0x3a, 0x02 }
      };
      g_assert_cmpuint (body_length, ==, 5);
      g_assert_cmpmem (body, 2, addresses[index], 2);
      g_assert_cmphex (body[2], ==, 2);
      g_assert_cmpmem (body + 3, 2, fixture->material.dac_values[index], 2);
    }
  goodix_a0_message_clear (&message);
}

static void
respond_valid (Fixture *fixture,
               guint mode,
               guint8 a8_status)
{
  GoodixSecurePhase phase = goodix_secure_session_get_phase (fixture->session);
  g_autoptr(GBytes) ack = NULL;
  g_autoptr(GBytes) typed = NULL;
  Submission *submission = pop_out (fixture);

  assert_command_shape (fixture, phase, submission->bytes);
  complete_submission (fixture, submission, NULL);
  if (phase == GOODIX_SECURE_PHASE_D1)
    return;
  ack = build_ack (control_for_phase (phase),
                   phase == GOODIX_SECURE_PHASE_A8 ? a8_status : 0x01);
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
      g_assert_cmpmem (data, length, expected, expected_length);
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
  g_assert_cmpuint (fixture->audit.command_count, ==, 13);
  g_assert_cmpuint (fixture->audit.ack_count, ==, 12);
  g_assert_cmpuint (fixture->audit.typed_response_count, ==, 7);
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
      g_assert_true (goodix_secure_session_start (fixture->session, &error));
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
        response = build_ack (0xe4, 0x07);       /* 07 must not leak */
      else if (variant == 4)
        response = build_ack (0xe4, 0x02);
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
}

static void
test_typed_length_hash_and_90 (void)
{
  const GoodixSecurePhase phases[] = {
    GOODIX_SECURE_PHASE_A2_1, GOODIX_SECURE_PHASE_CHIP_82,
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
          body = g_memdup2 (valid_body, body_length + 1u);
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
    g_autoptr(GBytes) ack = build_ack (0xa8, 0x01);
    g_autoptr(GBytes) typed = typed_for_phase (fixture,
                                               GOODIX_SECURE_PHASE_A8);
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
  g_test_add_func ("/goodix/d278/d1-client-hello-gate",
                   test_d1_client_hello_gate);
  g_test_add_func ("/goodix/d278/ack-policy-response-failures",
                   test_ack_policy_and_response_failures);
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
