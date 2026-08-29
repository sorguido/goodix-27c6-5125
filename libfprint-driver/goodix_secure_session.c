/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Production-shaped, host-testable secure-session sequencer for APP12509.
 * This is an independent LGPL implementation from neutral protocol facts and
 * canonical project vectors.  GPL implementations were not copied, adapted or
 * mechanically translated.
 */
#include "goodix_secure_session.h"

#include "goodix_a0_protocol.h"

#include <openssl/crypto.h>
#include <string.h>

typedef enum
{
  GOODIX_SECURE_ERROR_MATERIAL,
  GOODIX_SECURE_ERROR_STATE,
  GOODIX_SECURE_ERROR_PROTOCOL,
  GOODIX_SECURE_ERROR_TRANSPORT,
  GOODIX_SECURE_ERROR_TLS,
} GoodixSecureError;

typedef enum
{
  OUT_KIND_NONE,
  OUT_KIND_A0,
  OUT_KIND_B0,
} OutKind;

#define GOODIX_SECURE_ERROR (goodix_secure_error_quark ())

static const guint8 app12509_identity[] = "GF_ST411SEC_APP_12509";
static const guint16 dac_registers[] = { 0x0220, 0x0236, 0x0238, 0x023a };
static const guint config_dac_offsets[] = { 117, 121, 125, 129 };

typedef struct
{
  GoodixSecurePhase phase;
  guint8 allowed_statuses[2];
} PhaseAckPolicy;

/* D238 is the canonical cold-start/pre-D1 ACK authority.  Every row is
 * explicit so future phases cannot inherit this bounded allowlist by opcode
 * accident.  D1 is intentionally absent because it transitions directly to
 * B0/TLS and never accepts an A0 ACK. */
static const PhaseAckPolicy phase_ack_policies[] = {
  { GOODIX_SECURE_PHASE_A8,        { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_E4,        { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_A2_1,      { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_CHIP_82,   { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_OTP_A6,    { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_A2_2,      { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_MODE_70,   { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_DAC_220,   { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_DAC_236,   { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_DAC_238,   { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_DAC_23A,   { 0x01, 0x07 } },
  { GOODIX_SECURE_PHASE_CONFIG_90, { 0x01, 0x07 } },
};

struct _GoodixSecureSession
{
  GoodixFpiUsbBackend *backend;
  guint64 generation;
  GoodixSecurePhase phase;
  GoodixSecureSessionMaterial material;
  guint8 *e4_validator;
  guint8 *config90;
  GoodixTlsServer *tls;
  GoodixSecureSessionScheduleFunc schedule;
  gpointer schedule_data;
  GoodixSecureSessionTerminalFunc terminal;
  gpointer terminal_data;
  GoodixSecureSessionPhaseFunc phase_callback;
  gpointer phase_data;
  GoodixSecureSessionAudit *audit;
  GoodixTlsAudit *tls_audit;
  GError *error;

  gboolean started;
  gboolean ack_seen;
  gboolean logical_done;
  gboolean command_submitted;
  gboolean out_pending;
  OutKind out_kind;

  GQueue *tls_records;
  guint tls_record_count;
  GBytes *b0_logical;
  gsize b0_offset;
  gboolean pace_pending;
  gboolean d1_server_flight_seen;
  guint pace_source_id;
  guint64 pace_generation;
};

static GQuark
goodix_secure_error_quark (void)
{
  return g_quark_from_static_string ("goodix-secure-session-error");
}

static gboolean try_submit_phase (GoodixSecureSession *session,
                                  GError **error);
static void maybe_finish_tls (GoodixSecureSession *session);
static void maybe_start_b0 (GoodixSecureSession *session);

static void
notify_phase (GoodixSecureSession *session)
{
  if (session->phase_callback != NULL)
    session->phase_callback (session, session->phase, session->generation,
                             session->phase_data);
}

const gchar *
goodix_secure_phase_name (GoodixSecurePhase phase)
{
  static const gchar *const names[] = {
    "A8", "E4", "A2_1", "CHIP_82", "OTP_A6", "A2_2", "MODE_70",
    "DAC_220", "DAC_236", "DAC_238", "DAC_23A", "CONFIG_90", "D1",
    "TLS", "STOP", "TERMINAL"
  };

  return (guint) phase < G_N_ELEMENTS (names) ? names[phase] : "INVALID";
}

const gchar *
goodix_protocol_failure_kind_name (GoodixProtocolFailureKind kind)
{
  static const gchar *const names[] = {
    "none",
    "ACK_STATUS_REJECTED",
    "ACK_ECHO_MISMATCH",
    "ACK_SHAPE_MISMATCH",
    "TYPED_CONTROL_MISMATCH",
    "TYPED_SHAPE_MISMATCH",
    "UNEXPECTED_OUTER_CLASS",
    "MALFORMED_FRAME",
  };

  return (guint) kind < G_N_ELEMENTS (names) ? names[kind] : "INVALID";
}

static gboolean
phase_ack_status_allowed (GoodixSecurePhase phase,
                          guint8            status)
{
  for (guint i = 0; i < G_N_ELEMENTS (phase_ack_policies); i++)
    if (phase_ack_policies[i].phase == phase)
      return status == phase_ack_policies[i].allowed_statuses[0] ||
             status == phase_ack_policies[i].allowed_statuses[1];
  return FALSE;
}

static void
record_protocol_failure (GoodixSecureSession      *session,
                         GoodixProtocolFailureKind kind,
                         gint                      outer_type,
                         gint                      a0_control,
                         gint                      ack_echo,
                         gint                      ack_status,
                         gssize                    body_length)
{
  if (session->audit == NULL || session->audit->protocol_failure_recorded)
    return;
  session->audit->protocol_failure_recorded = TRUE;
  session->audit->protocol_failure_phase = session->phase;
  session->audit->protocol_failure_kind = kind;
  session->audit->observed_outer_type = outer_type;
  session->audit->observed_a0_control = a0_control;
  session->audit->observed_ack_echo = ack_echo;
  session->audit->observed_ack_status = ack_status;
  session->audit->observed_body_length = body_length;
}

static void
record_malformed_frame (GoodixSecureSession *session,
                        GBytes              *frame)
{
  gsize length;
  const guint8 *data = g_bytes_get_data (frame, &length);

  record_protocol_failure (session, GOODIX_PROTOCOL_FAILURE_MALFORMED_FRAME,
                           length >= 1 ? data[0] : -1,
                           length >= 5 ? data[4] : -1,
                           -1, -1, -1);
}

static gboolean
digest_matches (const guint8 *data,
                gsize         length,
                const guint8  expected[32])
{
  g_autoptr(GChecksum) checksum = g_checksum_new (G_CHECKSUM_SHA256);
  guint8 actual[32];
  gsize actual_length = sizeof actual;

  g_return_val_if_fail (length <= G_MAXSSIZE, FALSE);
  g_checksum_update (checksum, data, (gssize) length);
  g_checksum_get_digest (checksum, actual, &actual_length);
  return actual_length == sizeof actual &&
         CRYPTO_memcmp (actual, expected, sizeof actual) == 0;
}

static gboolean
digest_present (const guint8 digest[32])
{
  guint8 aggregate = 0;

  for (guint i = 0; i < 32; i++)
    aggregate |= digest[i];
  return aggregate != 0;
}

static gboolean
validate_config_finalizer (const guint8 config[GOODIX_SECURE_SESSION_CONFIG90_LENGTH])
{
  guint32 sum = 0;
  guint16 expected;
  guint16 actual;

  for (guint i = 0; i < 111; i++)
    {
      guint16 word = (guint16) ((guint16) config[i * 2u] |
                                (guint16) ((guint16) config[i * 2u + 1u] << 8));
      sum += (guint32) word;
    }
  expected = (guint16) (0u - 0xa5a5u - sum);
  actual = (guint16) config[222] | ((guint16) config[223] << 8);
  return actual == expected;
}

static gboolean
validate_material (const GoodixSecureSessionMaterial *material,
                   GError                           **error)
{
  if (material == NULL || material->expected_identity == NULL ||
      material->expected_identity_length != sizeof app12509_identity ||
      memcmp (material->expected_identity, app12509_identity,
              sizeof app12509_identity) != 0)
    goto invalid_identity;
  if (material->e4_validator == NULL || material->e4_validator_length != 32 ||
      !digest_present (material->e4_validator_sha256) ||
      !digest_matches (material->e4_validator, 32,
                       material->e4_validator_sha256))
    goto invalid_validator;
  if (!digest_present (material->a2_response_sha256) ||
      !digest_present (material->chip82_response_sha256) ||
      !digest_present (material->otp_a6_response_sha256))
    goto invalid_response_pin;
  if (material->config90 == NULL ||
      material->config90_length != GOODIX_SECURE_SESSION_CONFIG90_LENGTH ||
      !digest_present (material->config90_sha256) ||
      !digest_matches (material->config90, material->config90_length,
                       material->config90_sha256))
    goto invalid_config;
  if (!validate_config_finalizer (material->config90))
    goto invalid_finalizer;
  for (guint i = 0; i < G_N_ELEMENTS (dac_registers); i++)
    {
      guint offset = config_dac_offsets[i];
      if (material->config90[offset] != (guint8) dac_registers[i] ||
          material->config90[offset + 1u] != (guint8) (dac_registers[i] >> 8) ||
          material->config90[offset + 2u] != material->dac_values[i][0] ||
          material->config90[offset + 3u] != material->dac_values[i][1])
        goto invalid_correlation;
    }
  if (material->psk == NULL ||
      material->psk_length != GOODIX_SECURE_SESSION_PSK_LENGTH)
    goto invalid_psk;
  return TRUE;

invalid_identity:
  g_set_error_literal (error, GOODIX_SECURE_ERROR, GOODIX_SECURE_ERROR_MATERIAL,
                       "expected APP12509 identity material is invalid");
  return FALSE;
invalid_validator:
  g_set_error_literal (error, GOODIX_SECURE_ERROR, GOODIX_SECURE_ERROR_MATERIAL,
                       "E4 validator material or pin is invalid");
  return FALSE;
invalid_response_pin:
  g_set_error_literal (error, GOODIX_SECURE_ERROR, GOODIX_SECURE_ERROR_MATERIAL,
                       "a typed-response pin is missing");
  return FALSE;
invalid_config:
  g_set_error_literal (error, GOODIX_SECURE_ERROR, GOODIX_SECURE_ERROR_MATERIAL,
                       "CONFIG_90 length or SHA-256 is invalid");
  return FALSE;
invalid_finalizer:
  g_set_error_literal (error, GOODIX_SECURE_ERROR, GOODIX_SECURE_ERROR_MATERIAL,
                       "CONFIG_90 finalizer is invalid");
  return FALSE;
invalid_correlation:
  g_set_error_literal (error, GOODIX_SECURE_ERROR, GOODIX_SECURE_ERROR_MATERIAL,
                       "DAC and CONFIG_90 material are inconsistent");
  return FALSE;
invalid_psk:
  g_set_error_literal (error, GOODIX_SECURE_ERROR, GOODIX_SECURE_ERROR_MATERIAL,
                       "target PSK length must be exactly 32 bytes");
  return FALSE;
}

static void
clear_record_queue (GoodixSecureSession *session)
{
  while (!g_queue_is_empty (session->tls_records))
    g_bytes_unref (g_queue_pop_head (session->tls_records));
  g_clear_pointer (&session->b0_logical, g_bytes_unref);
  session->b0_offset = 0;
}

static void
session_fail_error (GoodixSecureSession *session,
                    GError              *error)
{
  if (session->phase == GOODIX_SECURE_PHASE_TERMINAL)
    {
      g_clear_error (&error);
      return;
    }
  session->phase = GOODIX_SECURE_PHASE_TERMINAL;
  notify_phase (session);
  if (session->error == NULL)
    session->error = error;
  else
    g_clear_error (&error);
  if (session->pace_source_id != 0)
    {
      g_source_remove (session->pace_source_id);
      session->pace_source_id = 0;
    }
  session->pace_pending = FALSE;
  clear_record_queue (session);
  goodix_tls_server_cancel (session->tls);
  goodix_fpi_usb_backend_cancel (session->backend);
  if (session->terminal != NULL)
    session->terminal (session, session->error, session->terminal_data);
}

static void
session_fail_literal (GoodixSecureSession *session,
                      GoodixSecureError    code,
                      const gchar         *message)
{
  session_fail_error (session,
                      g_error_new_literal (GOODIX_SECURE_ERROR, code, message));
}

static gboolean
phase_ack_only (GoodixSecurePhase phase)
{
  return phase == GOODIX_SECURE_PHASE_MODE_70 ||
         (phase >= GOODIX_SECURE_PHASE_DAC_220 &&
          phase <= GOODIX_SECURE_PHASE_DAC_23A);
}

static guint8
phase_control (GoodixSecurePhase phase)
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

static GBytes *
build_phase_frame (GoodixSecureSession *session,
                   GError             **error)
{
  static const guint8 a8[] = { 0x00, 0x00 };
  static const guint8 e4[] = { 0x03, 0x00, 0x02, 0xbb, 0, 0, 0, 0 };
  static const guint8 a2[] = { 0x01, 0x14 };
  static const guint8 chip[] = { 0, 0, 0, 4, 0 };
  static const guint8 zero2[] = { 0, 0 };
  static const guint8 mode[] = { 0x14, 0 };
  guint8 dac[5];
  const guint8 *body = NULL;
  gsize body_length = 0;
  guint8 wire_control = phase_control (session->phase);
  guint8 checksum_control = wire_control;

  switch (session->phase)
    {
    case GOODIX_SECURE_PHASE_A8: body = a8; body_length = sizeof a8; break;
    case GOODIX_SECURE_PHASE_E4: body = e4; body_length = sizeof e4; break;
    case GOODIX_SECURE_PHASE_A2_1:
    case GOODIX_SECURE_PHASE_A2_2: body = a2; body_length = sizeof a2; break;
    case GOODIX_SECURE_PHASE_CHIP_82: body = chip; body_length = sizeof chip; break;
    case GOODIX_SECURE_PHASE_OTP_A6: body = zero2; body_length = sizeof zero2; break;
    case GOODIX_SECURE_PHASE_MODE_70: body = mode; body_length = sizeof mode; break;
    case GOODIX_SECURE_PHASE_DAC_220:
    case GOODIX_SECURE_PHASE_DAC_236:
    case GOODIX_SECURE_PHASE_DAC_238:
    case GOODIX_SECURE_PHASE_DAC_23A:
      {
        guint index = (guint) session->phase - GOODIX_SECURE_PHASE_DAC_220;
        dac[0] = (guint8) dac_registers[index];
        dac[1] = (guint8) (dac_registers[index] >> 8);
        dac[2] = 2;
        dac[3] = session->material.dac_values[index][0];
        dac[4] = session->material.dac_values[index][1];
        body = dac;
        body_length = sizeof dac;
        break;
      }
    case GOODIX_SECURE_PHASE_CONFIG_90:
      body = session->config90;
      body_length = GOODIX_SECURE_SESSION_CONFIG90_LENGTH;
      break;
    case GOODIX_SECURE_PHASE_D1:
      body = zero2;
      body_length = sizeof zero2;
      checksum_control = 0xd0;
      break;
    default:
      g_set_error_literal (error, GOODIX_SECURE_ERROR, GOODIX_SECURE_ERROR_STATE,
                           "phase has no A0 request");
      return NULL;
    }
  return goodix_a0_build_frame (wire_control, checksum_control, body,
                                body_length, error);
}

static void
advance_phase (GoodixSecureSession *session)
{
  if (!session->logical_done || session->out_pending)
    return;
  if (session->phase == GOODIX_SECURE_PHASE_D1)
    session->phase = GOODIX_SECURE_PHASE_TLS;
  else if (session->phase < GOODIX_SECURE_PHASE_D1)
    session->phase++;
  else
    return;
  notify_phase (session);
  session->ack_seen = FALSE;
  session->logical_done = FALSE;
  session->command_submitted = FALSE;
  if (session->phase < GOODIX_SECURE_PHASE_TLS)
    {
      g_autoptr(GError) error = NULL;
      if (!try_submit_phase (session, &error))
        session_fail_error (session, g_steal_pointer (&error));
    }
  else
    {
      maybe_start_b0 (session);
      maybe_finish_tls (session);
    }
}

static gboolean
try_submit_phase (GoodixSecureSession *session,
                  GError             **error)
{
  g_autoptr(GBytes) frame = NULL;

  if (session->phase >= GOODIX_SECURE_PHASE_TLS || session->command_submitted)
    return TRUE;
  if (session->out_pending)
    return TRUE;
  frame = build_phase_frame (session, error);
  if (frame == NULL)
    return FALSE;
  /* Publish ownership before submission so the explicitly supported
   * synchronous backend seam cannot complete before our state is visible. */
  session->out_pending = TRUE;
  session->out_kind = OUT_KIND_A0;
  session->command_submitted = TRUE;
  if (session->audit != NULL)
    session->audit->command_count++;
  if (!goodix_fpi_usb_backend_submit_out (session->backend,
                                          session->generation, frame, error))
    {
      session->out_pending = FALSE;
      session->out_kind = OUT_KIND_NONE;
      session->command_submitted = FALSE;
      if (session->audit != NULL)
        session->audit->command_count--;
      return FALSE;
    }
  if (session->phase == GOODIX_SECURE_PHASE_TERMINAL)
    {
      if (session->error != NULL)
        g_propagate_error (error, g_error_copy (session->error));
      return FALSE;
    }
  return TRUE;
}

static gboolean
pace_timeout_cb (gpointer user_data)
{
  GoodixSecureSession *session = user_data;
  guint64 generation = session->pace_generation;

  session->pace_source_id = 0;
  goodix_secure_session_pacing_ready (session, generation);
  return G_SOURCE_REMOVE;
}

static void
schedule_next_record (GoodixSecureSession *session)
{
  if (session->pace_pending || session->phase == GOODIX_SECURE_PHASE_TERMINAL)
    return;
  session->pace_pending = TRUE;
  session->pace_generation = session->generation;
  if (session->audit != NULL)
    session->audit->pacing_schedule_count++;
  if (session->schedule != NULL)
    session->schedule (session, session->generation,
                       GOODIX_SECURE_SESSION_TLS_PACING_MS,
                       session->schedule_data);
  else
    session->pace_source_id =
      g_timeout_add_full (G_PRIORITY_DEFAULT,
                          GOODIX_SECURE_SESSION_TLS_PACING_MS,
                          pace_timeout_cb, session, NULL);
}

static gboolean
submit_b0_chunk (GoodixSecureSession *session,
                 GError             **error)
{
  guint8 physical[64] = { 0 };
  gsize logical_length;
  const guint8 *logical;
  gsize remaining;
  gsize copied;
  g_autoptr(GBytes) bytes = NULL;

  if (session->b0_logical == NULL || session->out_pending)
    return TRUE;
  logical = g_bytes_get_data (session->b0_logical, &logical_length);
  remaining = logical_length - session->b0_offset;
  copied = MIN (remaining, sizeof physical);
  memcpy (physical, logical + session->b0_offset, copied);
  bytes = g_bytes_new (physical, sizeof physical);
  session->b0_offset += copied;
  session->out_pending = TRUE;
  session->out_kind = OUT_KIND_B0;
  if (session->audit != NULL)
    session->audit->b0_physical_submit_count++;
  if (!goodix_fpi_usb_backend_submit_out (session->backend,
                                          session->generation, bytes, error))
    {
      session->b0_offset -= copied;
      session->out_pending = FALSE;
      session->out_kind = OUT_KIND_NONE;
      if (session->audit != NULL)
        session->audit->b0_physical_submit_count--;
      return FALSE;
    }
  return TRUE;
}

static void
start_next_record_now (GoodixSecureSession *session)
{
  g_autoptr(GByteArray) frame = NULL;
  GBytes *record;
  gsize length;
  const guint8 *data;
  guint8 header[4];
  g_autoptr(GError) error = NULL;

  if (session->b0_logical != NULL || session->out_pending ||
      g_queue_is_empty (session->tls_records) || session->pace_pending ||
      session->phase == GOODIX_SECURE_PHASE_TERMINAL)
    return;
  record = g_queue_pop_head (session->tls_records);
  data = g_bytes_get_data (record, &length);
  if (length == 0 || length > G_MAXUINT16)
    {
      g_bytes_unref (record);
      session_fail_literal (session, GOODIX_SECURE_ERROR_TLS,
                            "TLS record length cannot be wrapped in B0");
      return;
    }
  header[0] = 0xb0;
  header[1] = (guint8) length;
  header[2] = (guint8) (length >> 8);
  header[3] = (guint8) (header[0] + header[1] + header[2]);
  frame = g_byte_array_sized_new ((guint) length + 4u);
  g_byte_array_append (frame, header, sizeof header);
  g_byte_array_append (frame, data, (guint) length);
  session->b0_logical =
    g_byte_array_free_to_bytes (g_steal_pointer (&frame));
  session->b0_offset = 0;
  g_bytes_unref (record);
  if (!submit_b0_chunk (session, &error))
    session_fail_error (session, g_steal_pointer (&error));
}

static void
maybe_start_b0 (GoodixSecureSession *session)
{
  if (session->phase < GOODIX_SECURE_PHASE_TLS || session->out_pending ||
      session->b0_logical != NULL || g_queue_is_empty (session->tls_records))
    return;
  if (session->tls_record_count != 0)
    schedule_next_record (session);
  else
    start_next_record_now (session);
}

static void
backend_out_complete (GoodixFpiUsbBackend *backend,
                      guint64               generation,
                      const GError         *error,
                      gpointer              user_data)
{
  GoodixSecureSession *session = user_data;
  OutKind completed_kind;

  (void) backend;
  if (generation != session->generation || !session->out_pending ||
      session->phase == GOODIX_SECURE_PHASE_TERMINAL)
    return;
  completed_kind = session->out_kind;
  session->out_pending = FALSE;
  session->out_kind = OUT_KIND_NONE;
  if (error != NULL)
    {
      session_fail_error (session, g_error_copy (error));
      return;
    }
  if (completed_kind == OUT_KIND_A0)
    {
      advance_phase (session);
      if (session->phase == GOODIX_SECURE_PHASE_TLS)
        maybe_start_b0 (session);
      return;
    }
  if (completed_kind == OUT_KIND_B0)
    {
      gsize logical_length = g_bytes_get_size (session->b0_logical);
      if (session->b0_offset < logical_length)
        {
          g_autoptr(GError) submit_error = NULL;
          if (!submit_b0_chunk (session, &submit_error))
            session_fail_error (session, g_steal_pointer (&submit_error));
          return;
        }
      g_clear_pointer (&session->b0_logical, g_bytes_unref);
      session->b0_offset = 0;
      session->tls_record_count++;
      if (session->audit != NULL)
        {
          session->audit->tls_record_count = session->tls_record_count;
          if (!g_queue_is_empty (session->tls_records))
            schedule_next_record (session);
        }
      else if (!g_queue_is_empty (session->tls_records))
        schedule_next_record (session);
      maybe_finish_tls (session);
    }
}

static void
tls_output (GBytes *record,
            gpointer user_data)
{
  GoodixSecureSession *session = user_data;

  if (session->phase == GOODIX_SECURE_PHASE_TERMINAL ||
      session->phase == GOODIX_SECURE_PHASE_STOP)
    return;
  if (session->phase == GOODIX_SECURE_PHASE_D1)
    session->d1_server_flight_seen = TRUE;
  g_queue_push_tail (session->tls_records, g_bytes_ref (record));
  /* SSL_do_handshake() invokes this callback synchronously.  D1 egress must
   * wait until the caller has established that the push itself succeeded. */
  if (session->phase != GOODIX_SECURE_PHASE_D1)
    maybe_start_b0 (session);
}

static void
tls_plaintext (GBytes *bytes,
               gpointer user_data)
{
  GoodixSecureSession *session = user_data;

  (void) bytes;
  session_fail_literal (session, GOODIX_SECURE_ERROR_TLS,
                        "TLS application data is outside D278/01");
}

GoodixSecureSession *
goodix_secure_session_new (GoodixFpiUsbBackend                *backend,
                           guint64                             generation,
                           const GoodixSecureSessionMaterial *material,
                           GoodixSecureSessionScheduleFunc    schedule,
                           gpointer                           schedule_data,
                           GoodixSecureSessionTerminalFunc    terminal,
                           gpointer                           terminal_data,
                           GoodixSecureSessionAudit          *audit,
                           GoodixTlsAudit                    *tls_audit,
                           GError                           **error)
{
  GoodixSecureSession *session;

  if (backend == NULL || generation == 0 ||
      !validate_material (material, error))
    return NULL;
  session = g_new0 (GoodixSecureSession, 1);
  session->backend = backend;
  session->generation = generation;
  session->phase = GOODIX_SECURE_PHASE_A8;
  session->material = *material;
  session->e4_validator = g_memdup2 (material->e4_validator, 32);
  session->config90 = g_memdup2 (material->config90,
                                 GOODIX_SECURE_SESSION_CONFIG90_LENGTH);
  session->material.e4_validator = session->e4_validator;
  session->material.config90 = session->config90;
  session->material.psk = NULL;
  session->material.psk_length = 0;
  session->schedule = schedule;
  session->schedule_data = schedule_data;
  session->terminal = terminal;
  session->terminal_data = terminal_data;
  session->audit = audit;
  session->tls_audit = tls_audit;
  session->tls_records = g_queue_new ();
  if (audit != NULL)
    {
      memset (audit, 0, sizeof *audit);
      audit->generation = generation;
      audit->d4_reachable = FALSE;
      audit->protocol_failure_phase = GOODIX_SECURE_PHASE_TERMINAL;
      audit->observed_outer_type = -1;
      audit->observed_a0_control = -1;
      audit->observed_ack_echo = -1;
      audit->observed_ack_status = -1;
      audit->observed_body_length = -1;
    }
  session->tls = goodix_tls_server_new (material->psk, material->psk_length,
                                        tls_output, tls_plaintext, session,
                                        tls_audit, error);
  if (session->tls == NULL)
    {
      goodix_secure_session_free (session);
      return NULL;
    }
  goodix_fpi_usb_backend_set_out_completed_callback (backend,
                                                      backend_out_complete,
                                                      session);
  return session;
}

void
goodix_secure_session_free (GoodixSecureSession *session)
{
  if (session == NULL)
    return;
  g_return_if_fail (goodix_fpi_usb_backend_is_drained (session->backend));
  goodix_fpi_usb_backend_set_out_completed_callback (session->backend,
                                                      NULL, NULL);
  if (session->pace_source_id != 0)
    g_source_remove (session->pace_source_id);
  clear_record_queue (session);
  g_queue_free (session->tls_records);
  goodix_tls_server_free (session->tls);
  g_clear_error (&session->error);
  if (session->e4_validator != NULL)
    {
      OPENSSL_cleanse (session->e4_validator, 32);
      if (session->audit != NULL)
        session->audit->e4_validator_cleanse_count++;
      g_clear_pointer (&session->e4_validator, g_free);
    }
  if (session->config90 != NULL)
    {
      OPENSSL_cleanse (session->config90,
                       GOODIX_SECURE_SESSION_CONFIG90_LENGTH);
      if (session->audit != NULL)
        session->audit->config90_cleanse_count++;
      g_clear_pointer (&session->config90, g_free);
    }
  OPENSSL_cleanse (&session->material, sizeof session->material);
  if (session->audit != NULL)
    {
      session->audit->material_descriptor_cleanse_count++;
      session->audit->project_material_zeroized = TRUE;
    }
  g_free (session);
}

gboolean
goodix_secure_session_start (GoodixSecureSession *session,
                             GError             **error)
{
  if (session == NULL || session->started ||
      session->phase != GOODIX_SECURE_PHASE_A8)
    {
      g_set_error_literal (error, GOODIX_SECURE_ERROR, GOODIX_SECURE_ERROR_STATE,
                           "secure session cannot be started twice");
      return FALSE;
    }
  session->started = TRUE;
  notify_phase (session);
  return try_submit_phase (session, error);
}

static gboolean
validate_typed (GoodixSecureSession *session,
                guint8               control,
                const guint8        *body,
                gsize                body_length)
{
  static const guint8 e4_prefix[] = {
    0x00, 0x03, 0x00, 0x02, 0xbb, 0x20, 0x00, 0x00, 0x00
  };
  guint8 expected_control = phase_control (session->phase);

  if (control != expected_control)
    return FALSE;
  switch (session->phase)
    {
    case GOODIX_SECURE_PHASE_A8:
      return body_length == sizeof app12509_identity &&
             memcmp (body, app12509_identity, body_length) == 0;
    case GOODIX_SECURE_PHASE_E4:
      return body_length == sizeof e4_prefix + 32u &&
             memcmp (body, e4_prefix, sizeof e4_prefix) == 0 &&
             CRYPTO_memcmp (body + sizeof e4_prefix,
                            session->e4_validator, 32) == 0 &&
             digest_matches (body + sizeof e4_prefix, 32,
                             session->material.e4_validator_sha256);
    case GOODIX_SECURE_PHASE_A2_1:
    case GOODIX_SECURE_PHASE_A2_2:
      return body_length == 3 &&
             digest_matches (body, body_length,
                             session->material.a2_response_sha256);
    case GOODIX_SECURE_PHASE_CHIP_82:
      return body_length == 4 &&
             digest_matches (body, body_length,
                             session->material.chip82_response_sha256);
    case GOODIX_SECURE_PHASE_OTP_A6:
      return body_length == 64 &&
             digest_matches (body, body_length,
                             session->material.otp_a6_response_sha256);
    case GOODIX_SECURE_PHASE_CONFIG_90:
      return body_length == 2 && body[0] == 1 && body[1] == 0;
    default:
      return FALSE;
    }
}

void
goodix_secure_session_handle_a0 (GoodixSecureSession *session,
                                 GBytes             *frame)
{
  GoodixA0Message message = { 0 };
  g_autoptr(GError) error = NULL;
  gsize body_length;
  const guint8 *body;
  guint8 expected;

  if (session == NULL || frame == NULL ||
      session->phase == GOODIX_SECURE_PHASE_TERMINAL)
    return;
  if (session->phase >= GOODIX_SECURE_PHASE_D1)
    {
      gsize length;
      const guint8 *data = g_bytes_get_data (frame, &length);
      record_protocol_failure (
        session, GOODIX_PROTOCOL_FAILURE_UNEXPECTED_OUTER_CLASS,
        length >= 1 ? data[0] : -1, length >= 5 ? data[4] : -1,
        -1, -1, -1);
      session_fail_literal (session, GOODIX_SECURE_ERROR_PROTOCOL,
                            "A0 is forbidden after D1");
      return;
    }
  if (session->logical_done)
    {
      gsize length;
      const guint8 *data = g_bytes_get_data (frame, &length);
      record_protocol_failure (
        session, GOODIX_PROTOCOL_FAILURE_TYPED_SHAPE_MISMATCH,
        length >= 1 ? data[0] : -1, length >= 5 ? data[4] : -1,
        -1, -1, -1);
      session_fail_literal (session, GOODIX_SECURE_ERROR_PROTOCOL,
                            "duplicate A0 response for completed phase");
      return;
    }
  if (g_bytes_get_size (frame) < 5)
    {
      record_malformed_frame (session, frame);
      session_fail_literal (session, GOODIX_SECURE_ERROR_PROTOCOL,
                            "truncated A0 response");
      return;
    }
  /* Ordinary response controls use their wire value as checksum coordinate. */
  if (!goodix_a0_parse_frame (frame,
                              ((const guint8 *) g_bytes_get_data (frame, NULL))[4],
                              &message, &error))
    {
      record_malformed_frame (session, frame);
      session_fail_error (session, g_steal_pointer (&error));
      return;
    }
  body = g_bytes_get_data (message.body, &body_length);
  expected = phase_control (session->phase);
  if (message.control == 0xb0)
    {
      if (session->ack_seen || body_length != 2)
        {
          record_protocol_failure (
            session, GOODIX_PROTOCOL_FAILURE_ACK_SHAPE_MISMATCH,
            0xa0, message.control, body_length >= 1 ? body[0] : -1,
            body_length >= 2 ? body[1] : -1, (gssize) body_length);
          goto invalid_response;
        }
      if (body[0] != expected)
        {
          record_protocol_failure (
            session, GOODIX_PROTOCOL_FAILURE_ACK_ECHO_MISMATCH,
            0xa0, message.control, body[0], body[1], (gssize) body_length);
          goto invalid_response;
        }
      if (!phase_ack_status_allowed (session->phase, body[1]))
        {
          record_protocol_failure (
            session, GOODIX_PROTOCOL_FAILURE_ACK_STATUS_REJECTED,
            0xa0, message.control, body[0], body[1], (gssize) body_length);
          goto invalid_response;
        }
      session->ack_seen = TRUE;
      if (session->audit != NULL)
        session->audit->ack_count++;
      if (phase_ack_only (session->phase))
        {
          session->logical_done = TRUE;
          advance_phase (session);
        }
      goodix_a0_message_clear (&message);
      return;
    }
  if (!session->ack_seen || phase_ack_only (session->phase))
    {
      record_protocol_failure (
        session, GOODIX_PROTOCOL_FAILURE_TYPED_SHAPE_MISMATCH,
        0xa0, message.control, -1, -1, (gssize) body_length);
      goto invalid_response;
    }
  if (message.control != expected)
    {
      record_protocol_failure (
        session, GOODIX_PROTOCOL_FAILURE_TYPED_CONTROL_MISMATCH,
        0xa0, message.control, -1, -1, (gssize) body_length);
      goto invalid_response;
    }
  if (!validate_typed (session, message.control, body, body_length))
    {
      record_protocol_failure (
        session, GOODIX_PROTOCOL_FAILURE_TYPED_SHAPE_MISMATCH,
        0xa0, message.control, -1, -1, (gssize) body_length);
      goto invalid_response;
    }
  if (session->audit != NULL)
    session->audit->typed_response_count++;
  session->logical_done = TRUE;
  advance_phase (session);
  goodix_a0_message_clear (&message);
  return;

invalid_response:
  goodix_a0_message_clear (&message);
  session_fail_literal (session, GOODIX_SECURE_ERROR_PROTOCOL,
                        "phase-specific A0 response contract failed");
}

static void
maybe_finish_tls (GoodixSecureSession *session)
{
  if (session->phase != GOODIX_SECURE_PHASE_TLS ||
      goodix_tls_server_get_state (session->tls) !=
        GOODIX_TLS_STATE_ESTABLISHED)
    return;
  if (session->audit != NULL)
    session->audit->tls_established = TRUE;
  if (!session->out_pending && session->b0_logical == NULL &&
      g_queue_is_empty (session->tls_records) && !session->pace_pending)
    {
      session->phase = GOODIX_SECURE_PHASE_STOP;
      notify_phase (session);
    }
}

void
goodix_secure_session_handle_b0 (GoodixSecureSession *session,
                                 GBytes             *frame)
{
  gsize length;
  const guint8 *data;
  guint16 payload_length;
  g_autoptr(GError) error = NULL;

  if (session == NULL || frame == NULL ||
      session->phase == GOODIX_SECURE_PHASE_TERMINAL)
    return;
  if (session->phase < GOODIX_SECURE_PHASE_D1 ||
      session->phase == GOODIX_SECURE_PHASE_STOP)
    {
      gsize observed_length;
      const guint8 *observed = g_bytes_get_data (frame, &observed_length);
      record_protocol_failure (
        session, GOODIX_PROTOCOL_FAILURE_UNEXPECTED_OUTER_CLASS,
        observed_length >= 1 ? observed[0] : -1, -1, -1, -1, -1);
      session_fail_literal (session, GOODIX_SECURE_ERROR_PROTOCOL,
                            "B0 is forbidden in the current phase");
      return;
    }
  data = g_bytes_get_data (frame, &length);
  if (length < 9 || data[0] != 0xb0)
    goto malformed;
  payload_length = (guint16) data[1] | ((guint16) data[2] << 8);
  if ((gsize) payload_length + 4u != length ||
      data[3] != (guint8) (data[0] + data[1] + data[2]))
    goto malformed;
  if (!goodix_tls_server_push (session->tls, data + 4, payload_length, &error))
    {
      session_fail_error (session, g_steal_pointer (&error));
      return;
    }
  if (session->phase == GOODIX_SECURE_PHASE_D1 &&
      session->d1_server_flight_seen)
    {
      session->logical_done = TRUE;
      advance_phase (session);
    }
  maybe_start_b0 (session);
  maybe_finish_tls (session);
  return;

malformed:
  record_malformed_frame (session, frame);
  session_fail_literal (session, GOODIX_SECURE_ERROR_PROTOCOL,
                        "malformed B0 wrapper");
}

void
goodix_secure_session_pacing_ready (GoodixSecureSession *session,
                                    guint64              generation)
{
  if (session == NULL || !session->pace_pending ||
      generation != session->generation ||
      generation != session->pace_generation ||
      session->phase == GOODIX_SECURE_PHASE_TERMINAL)
    return;
  session->pace_pending = FALSE;
  session->pace_generation = 0;
  start_next_record_now (session);
  maybe_finish_tls (session);
}

void
goodix_secure_session_cancel (GoodixSecureSession *session,
                              const gchar         *reason)
{
  if (session == NULL)
    return;
  session_fail_literal (session, GOODIX_SECURE_ERROR_STATE,
                        reason != NULL ? reason : "secure session cancelled");
}

void
goodix_secure_session_set_phase_callback (GoodixSecureSession          *session,
                                          GoodixSecureSessionPhaseFunc  callback,
                                          gpointer                      user_data)
{
  g_return_if_fail (session != NULL);
  session->phase_callback = callback;
  session->phase_data = user_data;
}

GoodixSecurePhase
goodix_secure_session_get_phase (const GoodixSecureSession *session)
{
  return session != NULL ? session->phase : GOODIX_SECURE_PHASE_TERMINAL;
}

const GError *
goodix_secure_session_get_error (const GoodixSecureSession *session)
{
  return session != NULL ? session->error : NULL;
}

GoodixTlsServer *
goodix_secure_session_get_tls_server (GoodixSecureSession *session)
{
  return session != NULL ? session->tls : NULL;
}

gboolean
goodix_secure_session_needs_receive (const GoodixSecureSession *session)
{
  return session != NULL && session->started &&
         session->phase != GOODIX_SECURE_PHASE_STOP &&
         session->phase != GOODIX_SECURE_PHASE_TERMINAL;
}
