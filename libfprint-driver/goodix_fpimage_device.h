/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_FPIMAGE_DEVICE_H
#define GOODIX_FPIMAGE_DEVICE_H

#include <fpi-image-device.h>
#include <glib-object.h>
#include <stdint.h>
#include "goodix_tls_server.h"
#include "goodix_fpi_usb_backend.h"
#include "goodix_secure_session.h"
#include "goodix_post_tls_lifecycle.h"
#include "goodix_runtime_material.h"
#include "goodix_enrollment_fpi_usb_binding.h"

G_BEGIN_DECLS

#define GOODIX_TYPE_FPIMAGE_DEVICE (goodix_fpimage_device_get_type ())
G_DECLARE_DERIVABLE_TYPE (GoodixFpImageDevice, goodix_fpimage_device,
                          GOODIX, FPIMAGE_DEVICE, FpImageDevice)

struct _GoodixFpImageDeviceClass
{
  FpImageDeviceClass parent_class;
};

typedef enum
{
  GOODIX_DEVICE_CONTEXT_STATE_CLOSED = 0,
  GOODIX_DEVICE_CONTEXT_STATE_OPENING,
  GOODIX_DEVICE_CONTEXT_STATE_INACTIVE,
  GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING,
  GOODIX_DEVICE_CONTEXT_STATE_ACTIVE,
  GOODIX_DEVICE_CONTEXT_STATE_DEACTIVATING,
  GOODIX_DEVICE_CONTEXT_STATE_POISONED,
  GOODIX_DEVICE_CONTEXT_STATE_CLOSING,
} GoodixDeviceContextState;

typedef struct _GoodixDeviceContext GoodixDeviceContext;
typedef struct _GoodixInMemoryBackend GoodixInMemoryBackend;
typedef struct _GoodixUsbRouter GoodixUsbRouter;
typedef struct _GUsbDevice GUsbDevice;

#define GOODIX_PRE_SESSION_RX_QUIET_TIMEOUT_MS 250u
#define GOODIX_PRE_SESSION_RX_MAX_COMPLETIONS 16u
#define GOODIX_PRE_SESSION_RX_MAX_BYTES 65536u
#define GOODIX_PRE_SESSION_RX_MAX_TOTAL_MS 2000u

/* Successful primary stages observed for this exact target/profile in
 * D279/10 ATTEMPT02.  This is retained as the authentic wire/regression
 * profile, not as the final biometric policy or a universal firmware
 * constant. */
#define GOODIX_TARGET_LOCAL_ENROLL_STAGES 21u

/* D279/56 replayed the exact Rockytkg selector over ATTEMPT02 and reached its
 * maximum with eight distinct accepted samples.  D279/57 stages that maximum
 * as the production candidate for the separate APP12509 early-terminal
 * hardware boundary.  It is not yet target-live validated. */
#define GOODIX_SIGFM_ENROLL_MAX_STAGES 8u

typedef enum
{
  GOODIX_PRE_SESSION_RX_SYNC_NOT_STARTED = 0,
  GOODIX_PRE_SESSION_RX_SYNC_ACTIVE,
  GOODIX_PRE_SESSION_RX_SYNC_PASS,
  GOODIX_PRE_SESSION_RX_SYNC_FAIL_CLOSED,
} GoodixPreSessionRxSyncResult;

typedef struct
{
  gboolean pre_session_rx_sync_started;
  gboolean pre_session_rx_sync_completed;
  /* A host bulk-IN deadline expired with no bytes in that completion.  This
   * legacy field name does not assert device-side timeout or quiescence. */
  gboolean pre_session_rx_quiet_boundary;
  guint64 pre_session_rx_discarded_completion_count;
  guint64 pre_session_rx_discarded_byte_count;
  guint64 pre_session_rx_timeout_count;
  guint64 pre_session_rx_non_timeout_error_count;
  guint pre_session_rx_max_outstanding;
  guint64 pre_session_rx_elapsed_ms;
  GoodixPreSessionRxSyncResult pre_session_rx_result;
  gboolean first_protocol_out_after_rx_sync;
} GoodixPreSessionRxSyncAudit;

typedef struct
{
  guint production_action;
  guint production_action_attempt_count;
  guint production_rejected_action_count;
  gboolean production_action_consumed;
  /* Host lifecycle rollover performed for a new explicit VerifyStart.  This
   * is not a secure-session retry or a sensor-side automatic acquisition. */
  guint production_explicit_verify_reopen_count;
  guint auxiliary_b0_observed_count;
  guint terminal_enroll_completion_hold_count;
  guint terminal_enroll_completion_release_count;
  guint terminal_enroll_completion_abort_count;
  gboolean terminal_enroll_completion_held;
  GoodixPreSessionRxSyncAudit pre_session_rx_sync;
  GoodixRuntimeMaterialAudit runtime_material;
  GoodixSecureSessionAudit secure;
  GoodixTlsAudit tls;
  GoodixPostTlsAudit post_tls;
  GoodixEnrollmentPostTlsEventsAudit enrollment_events;
  GoodixEnrollmentFpiUsbBindingAudit enrollment_binding;
  guint64 usb_real_submit_count;
  guint64 usb_out_submit_count;
  guint64 usb_in_completion_count;
  guint64 usb_out_completion_count;
  guint usb_outstanding_count;
  guint usb_out_outstanding_count;
  guint usb_max_in_outstanding_count;
  guint usb_max_out_outstanding_count;
  gboolean usb_interface_claimed;
  gboolean usb_backend_drained;
  gboolean runtime_material_present;
  gboolean runtime_handoff_views_cleared;
  gboolean sigfm_normalization_baseline_pinned;
  gboolean sigfm_normalization_baseline_reused;
  gboolean context_closed;
} GoodixProductionEnrollmentAudit;

typedef gint64 (*GoodixPreSessionRxSyncClockFunc) (gpointer user_data);
typedef void (*GoodixDeviceContextSecurePhaseObserver) (
  GoodixSecurePhase phase,
  guint64           generation,
  gpointer          user_data);

#ifdef GOODIX_ENABLE_TEST_SEAMS
/* Offline-test seams for the production img_open/img_close boundary. */
typedef gboolean (*GoodixRuntimeMaterialAcquireSeam) (
  GoodixRuntimeMaterial       **owner,
  GoodixSecureSessionMaterial  *secure_view,
  guint8                        fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GoodixRuntimeMaterialAudit   *audit,
  gpointer                      user_data,
  GError                      **error);
typedef void (*GoodixRuntimeMaterialReleaseSeam) (
  GoodixRuntimeMaterial *owner,
  gpointer               user_data);
typedef gboolean (*GoodixUsbInterfaceSeam) (
  GUsbDevice *usb_device,
  guint8      interface_number,
  gpointer    user_data,
  GError    **error);
#endif

typedef struct
{
  void (*arm)    (GoodixDeviceContext *ctx, gpointer user_data);
  void (*disarm) (GoodixDeviceContext *ctx, gpointer user_data);
  void (*rearm)  (GoodixDeviceContext *ctx, gpointer user_data);
} GoodixBackendVTable;

/*
 * Host-only instantiation.  The returned device is the virtual base type and
 * is never selected by the production USB registry.
 */
GoodixFpImageDevice * goodix_fpimage_device_new (void);
/* Physical construction over an already selected GUsbDevice.  A thin
 * transport-typing subclass supplies FP_DEVICE_TYPE_USB while reusing the
 * exact same GoodixDeviceContext implementation.  Construction submits no USB
 * traffic. */
GoodixFpImageDevice * goodix_fpimage_device_new_for_usb (GUsbDevice *usb_device);

/* Entry point consumed by libfprint's generated standard driver registry. */
GType fpi_device_goodix_27c6_5125_get_type (void) G_GNUC_CONST;

GoodixDeviceContext * goodix_fpimage_device_get_context (GoodixFpImageDevice *dev);
#ifdef GOODIX_ENABLE_TEST_SEAMS
void goodix_fpimage_device_set_production_open_seams (
  GoodixFpImageDevice               *dev,
  GoodixRuntimeMaterialAcquireSeam   acquire_material,
  GoodixRuntimeMaterialReleaseSeam   release_material,
  GoodixUsbInterfaceSeam             claim_interface,
  GoodixUsbInterfaceSeam             release_interface,
  gpointer                           user_data);
#endif
gboolean goodix_device_context_has_runtime_material (GoodixDeviceContext *ctx);
gboolean goodix_device_context_has_usb_claim (GoodixDeviceContext *ctx);
gboolean goodix_device_context_runtime_handoff_views_cleared (
  GoodixDeviceContext *ctx);
void goodix_device_context_get_production_enrollment_audit (
  GoodixDeviceContext              *ctx,
  GoodixProductionEnrollmentAudit *audit);
/* Read-only, sanitized operator telemetry. It submits no work and returns the
 * final snapshot after close when the live context has already been freed. */
void goodix_fpimage_device_get_production_enrollment_audit (
  GoodixFpImageDevice             *dev,
  GoodixProductionEnrollmentAudit *audit);
GoodixUsbRouter *      goodix_device_context_get_usb_router (GoodixDeviceContext *ctx);
GoodixTlsServer *      goodix_device_context_get_tls_server (GoodixDeviceContext *ctx);
GoodixFpiUsbBackend *  goodix_device_context_get_fpi_usb_backend (GoodixDeviceContext *ctx);
gboolean goodix_device_context_adopt_dormant_enrollment_binding (
  GoodixDeviceContext           *ctx,
  GoodixEnrollmentFpiUsbBinding *binding,
  GError                       **error);
gboolean goodix_device_context_has_dormant_enrollment_binding (
  GoodixDeviceContext *ctx);
gboolean goodix_device_context_configure_tls (GoodixDeviceContext *ctx,
                                                        const guint8 *psk,
                                                        gsize psk_length,
                                                        GoodixTlsPlaintextFunc plaintext,
                                                        gpointer user_data,
                                                        GoodixTlsAudit *audit,
                                                        GError **error);
gboolean goodix_device_context_start_secure_session (
  GoodixDeviceContext                  *ctx,
  const GoodixSecureSessionMaterial    *material,
  GoodixSecureSessionScheduleFunc       schedule,
  gpointer                              schedule_data,
  GoodixSecureSessionAudit             *audit,
  GoodixTlsAudit                       *tls_audit,
  GError                              **error);
gboolean goodix_device_context_configure_post_tls_lifecycle (
  GoodixDeviceContext          *ctx,
  const GoodixPostTlsMaterial  *material,
  GoodixPostTlsAudit           *audit,
  GError                      **error);
/* Offline integration seam. It prepares a parametric graph and installs the
 * first-arm handoff, but does not start either lifecycle. */
gboolean goodix_device_context_configure_enrollment_graph (
  GoodixDeviceContext                    *ctx,
  const GoodixEnrollmentModelConfig      *config,
  GoodixEnrollmentAuxiliaryB0Func         auxiliary_ready,
  gpointer                                auxiliary_data,
  GoodixEnrollmentPostTlsEventsAudit     *events_audit,
  GoodixEnrollmentFpiUsbBindingAudit     *binding_audit,
  GError                                **error);
gboolean goodix_device_context_has_pending_enrollment_graph (
  GoodixDeviceContext *ctx);
GoodixSecureSession *goodix_device_context_get_secure_session (GoodixDeviceContext *ctx);
GoodixPostTlsLifecycle *goodix_device_context_get_post_tls_lifecycle (
  GoodixDeviceContext *ctx);
#ifdef GOODIX_ENABLE_TEST_SEAMS
void goodix_device_context_set_usb_submit_seam (GoodixDeviceContext *ctx,
                                                 GoodixUsbSubmitSeam seam,
                                                 gpointer user_data);
void goodix_device_context_set_async_usb_submit_seam (GoodixDeviceContext *ctx,
                                                       GoodixUsbSubmitSeam seam,
                                                       gpointer user_data);
#endif
gboolean goodix_device_context_arm_receive (GoodixDeviceContext *ctx, GError **error);
#ifdef GOODIX_ENABLE_TEST_SEAMS
void goodix_device_context_complete_receive (GoodixDeviceContext *ctx,
                                              guint64 submit_generation,
                                              const guint8 *data, gsize length,
                                              const GError *error);
#endif
void goodix_device_context_set_post_tls_await_finger_on (
  GoodixDeviceContext *ctx,
  gboolean             awaiting);
void goodix_device_context_set_secure_phase_observer (
  GoodixDeviceContext                    *ctx,
  GoodixDeviceContextSecurePhaseObserver  observer,
  gpointer                                user_data);

#ifdef GOODIX_ENABLE_TEST_SEAMS
/* Bounded host-only operator-harness epoch.  This API is absent from the
 * production libfprint build. */
gboolean goodix_device_context_begin_operator_epoch (
  GoodixDeviceContext *ctx,
  GCancellable        *cancellable,
  GError             **error);
#endif
gboolean goodix_device_context_begin_pre_session_rx_sync (
  GoodixDeviceContext *ctx,
  GError             **error);
GoodixPreSessionRxSyncResult goodix_device_context_get_pre_session_rx_sync_result (
  GoodixDeviceContext *ctx);
void goodix_device_context_get_pre_session_rx_sync_audit (
  GoodixDeviceContext          *ctx,
  GoodixPreSessionRxSyncAudit  *audit);
const gchar *goodix_pre_session_rx_sync_result_name (
  GoodixPreSessionRxSyncResult result);
#ifdef GOODIX_ENABLE_TEST_SEAMS
/* Deterministic host-only bound testing; set only while no sync is active. */
void goodix_device_context_set_pre_session_rx_sync_clock (
  GoodixDeviceContext                *ctx,
  GoodixPreSessionRxSyncClockFunc     clock_func,
  gpointer                            user_data);
void goodix_device_context_stop_operator_epoch (GoodixDeviceContext *ctx);
gboolean goodix_device_context_operator_epoch_is_drained (
  GoodixDeviceContext *ctx);
#endif

/* --- Context read-only accessors (test instrumentation) --- */
GoodixDeviceContextState goodix_device_context_get_state (GoodixDeviceContext *ctx);
guint64                  goodix_device_context_get_generation (GoodixDeviceContext *ctx);
gboolean                 goodix_device_context_get_terminal_fence (GoodixDeviceContext *ctx);
gboolean                 goodix_device_context_get_release_tail_complete (GoodixDeviceContext *ctx);
gboolean                 goodix_device_context_get_fresh_down_table (GoodixDeviceContext *ctx);
gboolean                 goodix_device_context_get_poisoned (GoodixDeviceContext *ctx);
const GError *           goodix_device_context_get_terminal_error (GoodixDeviceContext *ctx);

/* --- Backend command record (test assertions) --- */
guint        goodix_device_context_get_backend_command_count (GoodixDeviceContext *ctx);
guint        goodix_in_memory_backend_get_arm_count    (GoodixDeviceContext *ctx);
guint        goodix_in_memory_backend_get_disarm_count (GoodixDeviceContext *ctx);
guint        goodix_in_memory_backend_get_rearm_count  (GoodixDeviceContext *ctx);
const gchar *goodix_in_memory_backend_get_last_command (GoodixDeviceContext *ctx);

/* --- Test-only gate controls --- */
void goodix_device_context_set_fresh_down_table (GoodixDeviceContext *ctx,
                                                 gboolean             fresh);
void goodix_device_context_set_deactivation_held (GoodixDeviceContext *ctx,
                                                  gboolean             held);
void goodix_device_context_complete_deactivation (GoodixDeviceContext *ctx);

/* --- Host-only fake backend event injection --- */
void goodix_device_context_emit_arm_complete         (GoodixDeviceContext *ctx,
                                                      GError              *error);
void goodix_device_context_emit_finger_down          (GoodixDeviceContext *ctx);
void goodix_device_context_emit_image_ready          (GoodixDeviceContext *ctx,
                                                      const uint16_t      *samples,
                                                      size_t               sample_count);
#ifdef GOODIX_LIBFPRINT_SIGFM
void goodix_device_context_emit_sigfm_image_ready    (GoodixDeviceContext *ctx,
                                                      const uint16_t      *baseline,
                                                      const uint16_t      *samples,
                                                      size_t               sample_count);
#endif
void goodix_device_context_emit_release_tail_complete (GoodixDeviceContext *ctx);
void goodix_device_context_emit_finger_up_ready      (GoodixDeviceContext *ctx);
void goodix_device_context_emit_cancelled            (GoodixDeviceContext *ctx);
void goodix_device_context_emit_terminal_error       (GoodixDeviceContext *ctx,
                                                      GError              *error);
void goodix_device_context_emit_finger_down_for_generation (GoodixDeviceContext *ctx,
                                                            guint64 generation);

G_END_DECLS

#endif
