/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GOODIX_D278_A2_A8_REENTRY_PROBE_H
#define GOODIX_D278_A2_A8_REENTRY_PROBE_H

#include <gio/gio.h>

G_BEGIN_DECLS

#define GOODIX_D278_10_OUT_TIMEOUT_MS 500u
#define GOODIX_D278_10_ACK_TIMEOUT_MS 500u
#define GOODIX_D278_10_TYPED_TIMEOUT_MS 1000u
#define GOODIX_D278_10_RECEIVE_SIZE 512u

typedef struct _GoodixD278A2A8ReentryProbe GoodixD278A2A8ReentryProbe;

typedef enum
{
  GOODIX_D278_10_TRANSFER_OUT,
  GOODIX_D278_10_TRANSFER_IN,
} GoodixD278A2A8Direction;

typedef gboolean (*GoodixD278A2A8SubmitFunc) (
  GoodixD278A2A8ReentryProbe *probe,
  GoodixD278A2A8Direction     direction,
  guint64                     generation,
  GBytes                     *bytes,
  guint                       timeout_ms,
  gpointer                    user_data,
  GError                    **error);

typedef struct
{
  const gchar *approved_baseline;
  const gchar *identity_preflight_result;

  guint usb_open_count;
  guint usb_claim_count;
  guint usb_release_count;
  guint usb_close_count;

  guint goodix_command_count;
  guint out_submit_count;

  guint a2_sensor_only_submit_count;
  guint a2_ack_count;
  guint a2_typed_response_count;
  gint a2_ack_echo;
  gint a2_ack_status;
  const gchar *a2_typed_result_class;

  guint a8_submit_count;
  guint a8_ack_count;
  guint a8_typed_response_count;
  gint a8_ack_echo;
  gint a8_ack_status;
  const gchar *a8_typed_result_class;
  gboolean a8_app12509_pin_match;

  guint physical_in_submit_count;
  guint physical_in_completion_count;

  guint timeout_count;
  guint retry_count;
  guint reopen_count;
  guint device_reset_count;
  guint clear_halt_count;
  guint persistent_device_write_count;
  guint tls_handshake_count;
  guint unexpected_frame_count;
  guint stale_callback_count;
  guint prohibited_second_command_count;

  const gchar *completion_class;
  const gchar *error_class;
  const gchar *reentry_result_class;
  gboolean backend_drained;
  gboolean cleanup_completed;
} GoodixD278A2A8Audit;

GoodixD278A2A8ReentryProbe *goodix_d278_a2_a8_reentry_probe_new (
  const guint8                 expected_a2_typed_sha256[32],
  GoodixD278A2A8SubmitFunc     submit_func,
  gpointer                     submit_data);
void goodix_d278_a2_a8_reentry_probe_free (
  GoodixD278A2A8ReentryProbe *probe);

GBytes *goodix_d278_10_build_exact_a2_frame (GError **error);
GBytes *goodix_d278_10_build_exact_a8_frame (GError **error);

gboolean goodix_d278_a2_a8_reentry_probe_start (
  GoodixD278A2A8ReentryProbe *probe,
  guint64                     generation,
  GError                    **error);
void goodix_d278_a2_a8_reentry_probe_complete (
  GoodixD278A2A8ReentryProbe *probe,
  GoodixD278A2A8Direction     direction,
  guint64                     submit_generation,
  const guint8               *data,
  gsize                       length,
  const GError               *error);

gboolean goodix_d278_a2_a8_reentry_probe_is_terminal (
  const GoodixD278A2A8ReentryProbe *probe);
gboolean goodix_d278_a2_a8_reentry_probe_succeeded (
  const GoodixD278A2A8ReentryProbe *probe);
const GoodixD278A2A8Audit *goodix_d278_a2_a8_reentry_probe_get_audit (
  const GoodixD278A2A8ReentryProbe *probe);
GoodixD278A2A8Audit *goodix_d278_a2_a8_reentry_probe_get_mutable_audit (
  GoodixD278A2A8ReentryProbe *probe);
gchar *goodix_d278_a2_a8_reentry_probe_audit_to_json (
  const GoodixD278A2A8ReentryProbe *probe);

G_END_DECLS

#endif
