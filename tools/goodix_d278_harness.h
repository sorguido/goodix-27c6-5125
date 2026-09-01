/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GOODIX_D278_HARNESS_H
#define GOODIX_D278_HARNESS_H

#include <gio/gio.h>

#include "goodix_secure_session.h"
#include "goodix_d190_pe.h"
#include "goodix_target_material.h"

G_BEGIN_DECLS

typedef struct _GoodixD278Watchdog GoodixD278Watchdog;
typedef struct _GoodixD278Harness GoodixD278Harness;

typedef struct
{
  const gchar *failure_stage;
  const gchar *failure_class;
} GoodixD278PreflightFailure;

GoodixTargetMaterial *goodix_d278_prepare_target_material (
  const gchar                      *manifest_path,
  const gchar                      *transport_path,
  const gchar                      *config90_path,
  const gchar                      *dll_path,
  const GoodixTargetMaterialPolicy *material_policy,
  const GoodixD190PePolicy         *pe_policy,
  GoodixTargetMaterialAudit        *audit,
  GoodixSecureSessionMaterial      *view,
  GoodixD278PreflightFailure       *failure,
  GError                          **error);

typedef void (*GoodixD278WatchdogTimeoutFunc) (GoodixSecurePhase phase,
                                               guint64           generation,
                                               gpointer          user_data);

GoodixD278Watchdog *goodix_d278_watchdog_new (
  gboolean                         deterministic_test_mode,
  GoodixD278WatchdogTimeoutFunc    timeout,
  gpointer                         user_data);
void goodix_d278_watchdog_progress (GoodixD278Watchdog *watchdog,
                                    GoodixSecurePhase   phase,
                                    guint64             generation);
void goodix_d278_watchdog_invalidate (GoodixD278Watchdog *watchdog);
void goodix_d278_watchdog_free (GoodixD278Watchdog *watchdog);
guint goodix_d278_watchdog_timeout_for_phase (GoodixSecurePhase phase);
guint64 goodix_d278_watchdog_get_serial (const GoodixD278Watchdog *watchdog);
void goodix_d278_watchdog_fire_for_test (GoodixD278Watchdog *watchdog,
                                         guint64             generation,
                                         guint64             serial);

typedef struct
{
  gchar result[16];
  gchar failure_class[96];
  GoodixSecurePhase reached_phase;
  gboolean current_live_authorized;
  gboolean live_authorization_consumed;
  guint usb_open_attempt_count;
  guint usb_open_count;
  guint usb_claim_count;
  guint usb_release_count;
  guint usb_close_count;
  guint64 real_usb_submit_count;
  guint64 physical_in_submit_count;
  guint64 physical_in_completion_count;
  guint64 physical_out_submit_count;
  guint64 physical_out_completion_count;
  guint max_outstanding_bulk_in;
  guint max_outstanding_bulk_out;
  guint command_count;
  guint ack_count;
  guint typed_response_count;
  guint reentry_recovery_a2_submit_count;
  guint reentry_recovery_a2_ack_count;
  guint reentry_recovery_a2_typed_count;
  gboolean reentry_pre_ack_typed_observed;
  gboolean reentry_pre_ack_typed_pin_match;
  guint reentry_pre_ack_typed_discard_count;
  gchar reentry_recovery_a2_result_class[32];
  guint a8_submit_count;
  guint a8_ack_count;
  guint a8_typed_count;
  gboolean a8_app12509_pin_match;
  guint e4_submit_count;
  guint oem_cold_start_a2_1_submit_count;
  guint oem_cold_start_a2_2_submit_count;
  gboolean e4_binding_match;
  guint tls_handshake_count;
  gboolean tls_established;
  guint secret_handoff_count;
  gboolean project_secret_zeroized;
  guint retry_count;
  guint transport_reopen_count;
  guint device_reset_count;
  guint clear_halt_count;
  guint persistent_device_write_count;
  gboolean d4_reachable;
  guint application_data_count;
  guint finger_wait_count;
  guint image_count;
  gboolean backend_drained;
  gboolean terminal_cleanup_completed;
  guint synthetic_in_submit_count;
  guint synthetic_out_submit_count;
  gchar protocol_failure_kind[64];
  GoodixSecurePhase protocol_failure_phase;
  gint observed_outer_type;
  gint observed_a0_control;
  gint observed_ack_echo;
  gint observed_ack_status;
  gssize observed_body_length;
} GoodixD278Telemetry;

typedef void (*GoodixD278SyntheticSubmitFunc) (GoodixD278Harness  *harness,
                                               GoodixUsbDirection direction,
                                               guint64            generation,
                                               GBytes            *bytes,
                                               gpointer           user_data);
typedef void (*GoodixD278SyntheticPacingFunc) (GoodixD278Harness *harness,
                                               guint64           generation,
                                               guint             delay_ms,
                                               gpointer          user_data);

void goodix_d278_telemetry_init (GoodixD278Telemetry *telemetry,
                                 gboolean             live_mode);

GoodixD278Harness *goodix_d278_harness_new (
  FpDevice                           *device,
  const GoodixSecureSessionMaterial *material,
  gboolean                            synthetic_transport,
  gboolean                            deterministic_watchdog,
  GoodixD278SyntheticSubmitFunc       submit,
  GoodixD278SyntheticPacingFunc       pacing,
  gpointer                            user_data,
  GoodixD278Telemetry                *telemetry,
  GError                            **error);
gboolean goodix_d278_harness_start (GoodixD278Harness *harness,
                                    GError            **error);
void goodix_d278_harness_complete_receive (GoodixD278Harness *harness,
                                           guint64            generation,
                                           const guint8      *data,
                                           gsize              length,
                                           const GError      *error);
void goodix_d278_harness_complete_out (GoodixD278Harness *harness,
                                       guint64            generation,
                                       const GError      *error);
void goodix_d278_harness_pacing_ready (GoodixD278Harness *harness,
                                       guint64            generation);
void goodix_d278_harness_cancel (GoodixD278Harness *harness,
                                 const gchar       *failure_class);
void goodix_d278_harness_force_synthetic_drain (GoodixD278Harness *harness);
void goodix_d278_harness_run_main_loop (GoodixD278Harness *harness);
void goodix_d278_harness_seal (GoodixD278Harness *harness);
void goodix_d278_harness_free (GoodixD278Harness *harness);

GoodixSecureSession *goodix_d278_harness_get_session (GoodixD278Harness *harness);
GoodixFpiUsbBackend *goodix_d278_harness_get_backend (GoodixD278Harness *harness);
GoodixD278Watchdog *goodix_d278_harness_get_watchdog (GoodixD278Harness *harness);
const GoodixSecureSessionAudit *goodix_d278_harness_get_session_audit (
  GoodixD278Harness *harness);
guint64 goodix_d278_harness_get_generation (GoodixD278Harness *harness);
const gchar *goodix_d278_harness_get_phase_trace (GoodixD278Harness *harness);
gboolean goodix_d278_harness_is_terminal (GoodixD278Harness *harness);

gchar *goodix_d278_telemetry_to_json (GoodixD278Harness   *harness,
                                      GoodixD278Telemetry *telemetry);
gchar *goodix_d278_boundary_telemetry_to_json (
  const GoodixD278Telemetry *telemetry);

G_END_DECLS

#endif
