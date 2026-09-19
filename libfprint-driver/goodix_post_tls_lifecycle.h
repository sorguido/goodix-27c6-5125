/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_POST_TLS_LIFECYCLE_H
#define GOODIX_POST_TLS_LIFECYCLE_H

#include <gio/gio.h>
#include <stdint.h>

#include "goodix_fpi_usb_backend.h"
#include "goodix_image_decoder.h"

G_BEGIN_DECLS

typedef enum
{
  GOODIX_POST_TLS_PHASE_NOT_STARTED = 0,
  GOODIX_POST_TLS_PHASE_D4,
  GOODIX_POST_TLS_PHASE_AF,
  GOODIX_POST_TLS_PHASE_FDT36_1,
  GOODIX_POST_TLS_PHASE_FDT_IRQ100_1,
  GOODIX_POST_TLS_PHASE_FDT_NAV_1,
  GOODIX_POST_TLS_PHASE_FDT36_2,
  GOODIX_POST_TLS_PHASE_FDT_IRQ100_2,
  GOODIX_POST_TLS_PHASE_FDT_82,
  GOODIX_POST_TLS_PHASE_FDT_20,
  GOODIX_POST_TLS_PHASE_FDT_B0,
  GOODIX_POST_TLS_PHASE_FDT36_3,
  GOODIX_POST_TLS_PHASE_FDT_IRQ100_3,
  GOODIX_POST_TLS_PHASE_FIRST_ARM,
  GOODIX_POST_TLS_PHASE_FIRST_IRQ2,
  GOODIX_POST_TLS_PHASE_FIRST_22,
  GOODIX_POST_TLS_PHASE_FIRST_B0,
  GOODIX_POST_TLS_PHASE_RELEASE_34,
  GOODIX_POST_TLS_PHASE_RELEASE_IRQ200,
  GOODIX_POST_TLS_PHASE_RELEASE_20,
  GOODIX_POST_TLS_PHASE_RELEASE_B0,
  GOODIX_POST_TLS_PHASE_RELEASE_50,
  GOODIX_POST_TLS_PHASE_RELEASE_NAV,
  GOODIX_POST_TLS_PHASE_REARM_GATE,
  GOODIX_POST_TLS_PHASE_SECOND_ARM,
  GOODIX_POST_TLS_PHASE_SECOND_IRQ2,
  GOODIX_POST_TLS_PHASE_SECOND_22,
  GOODIX_POST_TLS_PHASE_SECOND_B0,
  GOODIX_POST_TLS_PHASE_STOP,
  GOODIX_POST_TLS_PHASE_TERMINAL,
} GoodixPostTlsPhase;

typedef enum
{
  GOODIX_POST_TLS_CAPTURE_PROFILE_TWO_ACQUISITION = 0,
  GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION,
} GoodixPostTlsCaptureProfile;

typedef struct
{
  guint8 initial_fdt_table[12];
  guint16 af_timestamp;
  guint16 first_arm_timestamp;
  guint16 second_arm_timestamp;
  GoodixPostTlsCaptureProfile capture_profile;
} GoodixPostTlsMaterial;

typedef struct
{
  gboolean post_tls_lifecycle_started;
  guint d4_count;
  guint af_count;
  guint fdt36_submit_count;
  guint fdt_irq100_count;
  guint fresh_fdt_count;
  guint fdt_delta_classification_count;
  guint fdt_delta_within_threshold_count;
  guint fdt_delta_outside_threshold_count;
  guint baseline_b0_count;
  guint baseline_decode_count;
  guint first_irq0002_count;
  guint first_image_command_count;
  guint first_image_b0_count;
  guint first_image_decode_count;
  guint first_image_pipeline_count;
  guint release_0x34_count;
  guint irq0200_count;
  guint post_up_0x20_count;
  guint post_up_b0_count;
  guint nav_0x50_count;
  guint nav_response_count;
  guint fresh_down_table_count;
  guint rearm_0x32_count;
  guint second_irq0002_count;
  guint second_image_command_count;
  guint second_b0_count;
  guint second_image_decode_count;
  guint second_image_pipeline_count;
  guint third_cycle_command_count;
  guint command_count;
  guint ack_count;
  guint retry_count;
  guint reopen_count;
  guint device_reset_count;
  guint clear_halt_count;
  guint persistent_device_write_count;
  guint release_tail_complete_count;
  guint single_acquisition_terminal_count;
  guint first_arm_handoff_count;
  guint backend_handoff_count;
  gboolean fresh_down_table;
  gboolean framework_rearm_gate_seen;
  gboolean terminal;
  gboolean backend_drained;
  gboolean terminal_cleanup_completed;
  gboolean rejected_a0_observed;
  GoodixPostTlsPhase rejected_a0_phase;
  gint rejected_a0_control;
  gint rejected_a0_irq;
  gint rejected_a0_flags;
  gssize rejected_a0_body_length;
  guint64 generation;
} GoodixPostTlsAudit;

typedef struct _GoodixPostTlsLifecycle GoodixPostTlsLifecycle;

typedef gboolean (*GoodixPostTlsImageFunc) (
  GoodixPostTlsLifecycle *lifecycle,
  guint                   acquisition_index,
  const uint16_t          samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT],
  gpointer                user_data,
  GError                **error);
typedef void (*GoodixPostTlsEventFunc) (GoodixPostTlsLifecycle *lifecycle,
                                        gpointer user_data);
typedef void (*GoodixPostTlsTerminalFunc) (GoodixPostTlsLifecycle *lifecycle,
                                           const GError *error,
                                           gpointer user_data);
typedef gboolean (*GoodixPostTlsFirstArmHandoffFunc) (
  GoodixPostTlsLifecycle *lifecycle,
  GoodixFpiUsbBackend    *backend,
  guint64                 generation,
  gpointer                user_data,
  GError                **error);

GoodixPostTlsLifecycle *goodix_post_tls_lifecycle_new (
  GoodixFpiUsbBackend          *backend,
  guint64                       generation,
  const GoodixPostTlsMaterial  *material,
  GoodixPostTlsImageFunc        image,
  GoodixPostTlsEventFunc        finger_down,
  GoodixPostTlsEventFunc        release_tail,
  GoodixPostTlsEventFunc        finger_up,
  GoodixPostTlsTerminalFunc     terminal,
  gpointer                      user_data,
  GoodixPostTlsAudit           *audit,
  GError                      **error);
void goodix_post_tls_lifecycle_free (GoodixPostTlsLifecycle *lifecycle);
gboolean goodix_post_tls_lifecycle_set_first_arm_handoff (
  GoodixPostTlsLifecycle            *lifecycle,
  GoodixPostTlsFirstArmHandoffFunc   handoff,
  GError                           **error);
gboolean goodix_post_tls_lifecycle_start (GoodixPostTlsLifecycle *lifecycle,
                                          GError **error);
void goodix_post_tls_lifecycle_handle_a0 (GoodixPostTlsLifecycle *lifecycle,
                                          GBytes *frame);
void goodix_post_tls_lifecycle_handle_plaintext (
  GoodixPostTlsLifecycle *lifecycle,
  GBytes                 *plaintext);
void goodix_post_tls_lifecycle_set_framework_await_finger_on (
  GoodixPostTlsLifecycle *lifecycle,
  guint64                 generation,
  gboolean                awaiting);
void goodix_post_tls_lifecycle_cancel (GoodixPostTlsLifecycle *lifecycle,
                                       const gchar *reason);
const gchar *goodix_post_tls_phase_name (GoodixPostTlsPhase phase);
GoodixPostTlsPhase goodix_post_tls_lifecycle_get_phase (
  const GoodixPostTlsLifecycle *lifecycle);
GoodixPostTlsCaptureProfile goodix_post_tls_lifecycle_get_capture_profile (
  const GoodixPostTlsLifecycle *lifecycle);
const GError *goodix_post_tls_lifecycle_get_error (
  const GoodixPostTlsLifecycle *lifecycle);
gboolean goodix_post_tls_lifecycle_needs_receive (
  const GoodixPostTlsLifecycle *lifecycle);
gboolean goodix_post_tls_lifecycle_copy_baseline (
  const GoodixPostTlsLifecycle *lifecycle,
  uint16_t                      samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT]);

/* Login-only gate. Configure before start; authorize only at first arm ACK.
 * All ordinary capture/enrollment callers retain their existing behavior. */
void goodix_post_tls_lifecycle_prepare_login (GoodixPostTlsLifecycle *lifecycle,
                                              GoodixPostTlsEventFunc ready);
gboolean goodix_post_tls_lifecycle_authorize_login (GoodixPostTlsLifecycle *lifecycle);

G_END_DECLS

#endif
