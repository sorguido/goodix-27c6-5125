/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_SECURE_SESSION_H
#define GOODIX_SECURE_SESSION_H

#include <gio/gio.h>

#include "goodix_fpi_usb_backend.h"
#include "goodix_tls_server.h"

G_BEGIN_DECLS

#define GOODIX_SECURE_SESSION_PSK_LENGTH 32u
#define GOODIX_SECURE_SESSION_CONFIG90_LENGTH 224u
#define GOODIX_SECURE_SESSION_TLS_PACING_MS 10u

typedef enum
{
  GOODIX_SECURE_PHASE_REENTRY_RECOVERY_A2 = 0,
  GOODIX_SECURE_PHASE_A8,
  GOODIX_SECURE_PHASE_E4,
  GOODIX_SECURE_PHASE_OEM_COLD_START_A2_1,
  GOODIX_SECURE_PHASE_CHIP_82,
  GOODIX_SECURE_PHASE_OTP_A6,
  GOODIX_SECURE_PHASE_OEM_COLD_START_A2_2,
  GOODIX_SECURE_PHASE_MODE_70,
  GOODIX_SECURE_PHASE_DAC_220,
  GOODIX_SECURE_PHASE_DAC_236,
  GOODIX_SECURE_PHASE_DAC_238,
  GOODIX_SECURE_PHASE_DAC_23A,
  GOODIX_SECURE_PHASE_CONFIG_90,
  GOODIX_SECURE_PHASE_D1,
  GOODIX_SECURE_PHASE_TLS,
  GOODIX_SECURE_PHASE_STOP,
  GOODIX_SECURE_PHASE_TERMINAL,
} GoodixSecurePhase;

typedef enum
{
  GOODIX_PROTOCOL_FAILURE_NONE = 0,
  GOODIX_PROTOCOL_FAILURE_ACK_STATUS_REJECTED,
  GOODIX_PROTOCOL_FAILURE_ACK_ECHO_MISMATCH,
  GOODIX_PROTOCOL_FAILURE_ACK_SHAPE_MISMATCH,
  GOODIX_PROTOCOL_FAILURE_TYPED_CONTROL_MISMATCH,
  GOODIX_PROTOCOL_FAILURE_TYPED_SHAPE_MISMATCH,
  GOODIX_PROTOCOL_FAILURE_UNEXPECTED_OUTER_CLASS,
  GOODIX_PROTOCOL_FAILURE_MALFORMED_FRAME,
} GoodixProtocolFailureKind;

typedef enum
{
  GOODIX_REENTRY_RECOVERY_A2_NOT_STARTED = 0,
  GOODIX_REENTRY_RECOVERY_A2_SUBMITTED,
  GOODIX_REENTRY_RECOVERY_A2_ACK_STRICT,
  GOODIX_REENTRY_RECOVERY_A2_STRICT_MATCH,
  GOODIX_REENTRY_RECOVERY_A2_FAIL_CLOSED,
} GoodixReentryRecoveryA2ResultClass;

typedef struct
{
  const guint8 *expected_identity;
  gsize expected_identity_length;
  const guint8 *e4_validator;
  gsize e4_validator_length;
  guint8 e4_validator_sha256[32];
  guint8 a2_response_sha256[32];
  guint8 chip82_response_sha256[32];
  guint8 otp_a6_response_sha256[32];
  guint8 dac_values[4][2];
  const guint8 *config90;
  gsize config90_length;
  guint8 config90_sha256[32];
  const guint8 *psk;
  gsize psk_length;
} GoodixSecureSessionMaterial;

typedef struct
{
  guint command_count;
  guint ack_count;
  guint typed_response_count;
  guint reentry_recovery_a2_submit_count;
  guint reentry_recovery_a2_ack_count;
  guint reentry_recovery_a2_typed_count;
  GoodixReentryRecoveryA2ResultClass reentry_recovery_a2_result_class;
  guint a8_submit_count;
  guint a8_ack_count;
  guint a8_typed_count;
  gboolean a8_app12509_pin_match;
  guint e4_submit_count;
  guint oem_cold_start_a2_1_submit_count;
  guint oem_cold_start_a2_2_submit_count;
  guint tls_record_count;
  guint b0_physical_submit_count;
  guint pacing_schedule_count;
  guint retry_count;
  guint transport_reopen_count;
  guint device_reset_count;
  guint clear_halt_count;
  guint persistent_write_count;
  guint e4_validator_cleanse_count;
  guint config90_cleanse_count;
  guint material_descriptor_cleanse_count;
  gboolean project_material_zeroized;
  gboolean tls_established;
  gboolean d4_reachable;
  guint64 generation;
  gboolean protocol_failure_recorded;
  GoodixSecurePhase protocol_failure_phase;
  GoodixProtocolFailureKind protocol_failure_kind;
  gint observed_outer_type;
  gint observed_a0_control;
  gint observed_ack_echo;
  gint observed_ack_status;
  gssize observed_body_length;
} GoodixSecureSessionAudit;

typedef struct _GoodixSecureSession GoodixSecureSession;

/* The test seam records the owned pacing action and later calls
 * goodix_secure_session_pacing_ready().  A NULL seam uses a cancellable GLib
 * timeout source owned by the session. */
typedef void (*GoodixSecureSessionScheduleFunc) (GoodixSecureSession *session,
                                                 guint64 generation,
                                                 guint delay_ms,
                                                 gpointer user_data);
typedef void (*GoodixSecureSessionTerminalFunc) (GoodixSecureSession *session,
                                                 const GError *error,
                                                 gpointer user_data);
typedef void (*GoodixSecureSessionPhaseFunc) (GoodixSecureSession *session,
                                              GoodixSecurePhase    phase,
                                              guint64              generation,
                                              gpointer             user_data);

GoodixSecureSession *goodix_secure_session_new (
  GoodixFpiUsbBackend                  *backend,
  guint64                               generation,
  const GoodixSecureSessionMaterial   *material,
  GoodixSecureSessionScheduleFunc      schedule,
  gpointer                             schedule_data,
  GoodixSecureSessionTerminalFunc      terminal,
  gpointer                             terminal_data,
  GoodixSecureSessionAudit            *audit,
  GoodixTlsAudit                      *tls_audit,
  GError                             **error);
void     goodix_secure_session_free (GoodixSecureSession *session);
gboolean goodix_secure_session_start (GoodixSecureSession *session,
                                      GError **error);
void     goodix_secure_session_handle_a0 (GoodixSecureSession *session,
                                          GBytes *frame);
void     goodix_secure_session_handle_b0 (GoodixSecureSession *session,
                                          GBytes *frame);
void     goodix_secure_session_pacing_ready (GoodixSecureSession *session,
                                             guint64 generation);
void     goodix_secure_session_cancel (GoodixSecureSession *session,
                                       const gchar *reason);
void     goodix_secure_session_set_phase_callback (
  GoodixSecureSession          *session,
  GoodixSecureSessionPhaseFunc  callback,
  gpointer                      user_data);

GoodixSecurePhase goodix_secure_session_get_phase (const GoodixSecureSession *session);
const GError     *goodix_secure_session_get_error (const GoodixSecureSession *session);
GoodixTlsServer  *goodix_secure_session_get_tls_server (GoodixSecureSession *session);
gboolean          goodix_secure_session_needs_receive (const GoodixSecureSession *session);
const gchar      *goodix_secure_phase_name (GoodixSecurePhase phase);
const gchar      *goodix_protocol_failure_kind_name (
  GoodixProtocolFailureKind kind);
const gchar      *goodix_reentry_recovery_a2_result_class_name (
  GoodixReentryRecoveryA2ResultClass result_class);

G_END_DECLS

#endif
