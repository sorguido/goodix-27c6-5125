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

G_BEGIN_DECLS

#define GOODIX_TYPE_FPIMAGE_DEVICE (goodix_fpimage_device_get_type ())
G_DECLARE_FINAL_TYPE (GoodixFpImageDevice, goodix_fpimage_device,
                      GOODIX, FPIMAGE_DEVICE, FpImageDevice)

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
typedef void (*GoodixDeviceContextSecurePhaseObserver) (
  GoodixSecurePhase phase,
  guint64           generation,
  gpointer          user_data);

typedef struct
{
  void (*arm)    (GoodixDeviceContext *ctx, gpointer user_data);
  void (*disarm) (GoodixDeviceContext *ctx, gpointer user_data);
  void (*rearm)  (GoodixDeviceContext *ctx, gpointer user_data);
} GoodixBackendVTable;

/*
 * Host-only instantiation.  The returned device is a real FpImageDevice
 * subclass, but it is not registered in any production id table.
 */
GoodixFpImageDevice * goodix_fpimage_device_new (void);
/* Harness-only construction over an already selected GUsbDevice.  The class
 * remains absent from every production id table. */
GoodixFpImageDevice * goodix_fpimage_device_new_for_usb (GUsbDevice *usb_device);

GoodixDeviceContext * goodix_fpimage_device_get_context (GoodixFpImageDevice *dev);
GoodixUsbRouter *      goodix_device_context_get_usb_router (GoodixDeviceContext *ctx);
GoodixTlsServer *      goodix_device_context_get_tls_server (GoodixDeviceContext *ctx);
GoodixFpiUsbBackend *  goodix_device_context_get_fpi_usb_backend (GoodixDeviceContext *ctx);
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
GoodixSecureSession *goodix_device_context_get_secure_session (GoodixDeviceContext *ctx);
GoodixPostTlsLifecycle *goodix_device_context_get_post_tls_lifecycle (
  GoodixDeviceContext *ctx);
void goodix_device_context_set_usb_submit_seam (GoodixDeviceContext *ctx,
                                                 GoodixUsbSubmitSeam seam,
                                                 gpointer user_data);
void goodix_device_context_set_async_usb_submit_seam (GoodixDeviceContext *ctx,
                                                       GoodixUsbSubmitSeam seam,
                                                       gpointer user_data);
gboolean goodix_device_context_arm_receive (GoodixDeviceContext *ctx, GError **error);
void goodix_device_context_complete_receive (GoodixDeviceContext *ctx,
                                              guint64 submit_generation,
                                              const guint8 *data, gsize length,
                                              const GError *error);
void goodix_device_context_set_post_tls_await_finger_on (
  GoodixDeviceContext *ctx,
  gboolean             awaiting);
void goodix_device_context_set_secure_phase_observer (
  GoodixDeviceContext                    *ctx,
  GoodixDeviceContextSecurePhaseObserver  observer,
  gpointer                                user_data);

/* Bounded operator-harness epoch.  This is activation plumbing only: all
 * protocol/TLS/FDT/image semantics remain in the objects owned by @ctx. */
gboolean goodix_device_context_begin_operator_epoch (
  GoodixDeviceContext *ctx,
  GCancellable        *cancellable,
  GError             **error);
void goodix_device_context_stop_operator_epoch (GoodixDeviceContext *ctx);
gboolean goodix_device_context_operator_epoch_is_drained (
  GoodixDeviceContext *ctx);

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
void goodix_device_context_emit_release_tail_complete (GoodixDeviceContext *ctx);
void goodix_device_context_emit_finger_up_ready      (GoodixDeviceContext *ctx);
void goodix_device_context_emit_cancelled            (GoodixDeviceContext *ctx);
void goodix_device_context_emit_terminal_error       (GoodixDeviceContext *ctx,
                                                      GError              *error);
void goodix_device_context_emit_finger_down_for_generation (GoodixDeviceContext *ctx,
                                                            guint64 generation);

G_END_DECLS

#endif
