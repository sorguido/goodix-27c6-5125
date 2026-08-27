/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_FPIMAGE_DEVICE_H
#define GOODIX_FPIMAGE_DEVICE_H

#include <fpi-image-device.h>
#include <glib-object.h>
#include <stdint.h>

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

GoodixDeviceContext * goodix_fpimage_device_get_context (GoodixFpImageDevice *dev);

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

G_END_DECLS

#endif
