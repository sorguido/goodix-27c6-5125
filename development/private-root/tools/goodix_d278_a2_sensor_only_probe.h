/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GOODIX_D278_A2_SENSOR_ONLY_PROBE_H
#define GOODIX_D278_A2_SENSOR_ONLY_PROBE_H

#include <gio/gio.h>

G_BEGIN_DECLS

#define GOODIX_D278_09_OUT_TIMEOUT_MS 500u
#define GOODIX_D278_09_ACK_TIMEOUT_MS 500u
#define GOODIX_D278_09_TYPED_TIMEOUT_MS 1000u
#define GOODIX_D278_09_RECEIVE_SIZE 512u

typedef struct _GoodixD278A2SensorOnlyProbe GoodixD278A2SensorOnlyProbe;

typedef enum
{
  GOODIX_D278_A2_TRANSFER_OUT,
  GOODIX_D278_A2_TRANSFER_IN,
} GoodixD278A2Direction;

typedef gboolean (*GoodixD278A2SubmitFunc) (
  GoodixD278A2SensorOnlyProbe *probe,
  GoodixD278A2Direction        direction,
  guint64                      generation,
  GBytes                      *bytes,
  guint                        timeout_ms,
  gpointer                     user_data,
  GError                     **error);

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
  guint physical_in_submit_count;
  guint physical_in_completion_count;

  guint ack_count;
  guint typed_response_count;
  gint ack_echo;
  gint ack_status;
  gint typed_control;
  gint typed_body_length;
  const gchar *typed_result_class;

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
  const gchar *current_context_result;
  gboolean backend_drained;
  gboolean cleanup_completed;
} GoodixD278A2ProbeAudit;

GoodixD278A2SensorOnlyProbe *goodix_d278_a2_sensor_only_probe_new (
  const guint8             expected_typed_sha256[32],
  GoodixD278A2SubmitFunc   submit_func,
  gpointer                 submit_data);
void goodix_d278_a2_sensor_only_probe_free (
  GoodixD278A2SensorOnlyProbe *probe);

GBytes *goodix_d278_a2_sensor_only_build_exact_frame (GError **error);

gboolean goodix_d278_a2_sensor_only_probe_start (
  GoodixD278A2SensorOnlyProbe *probe,
  guint64                      generation,
  GError                     **error);
void goodix_d278_a2_sensor_only_probe_complete (
  GoodixD278A2SensorOnlyProbe *probe,
  GoodixD278A2Direction        direction,
  guint64                      submit_generation,
  const guint8                *data,
  gsize                        length,
  const GError                *error);

gboolean goodix_d278_a2_sensor_only_probe_is_terminal (
  const GoodixD278A2SensorOnlyProbe *probe);
gboolean goodix_d278_a2_sensor_only_probe_succeeded (
  const GoodixD278A2SensorOnlyProbe *probe);
const GoodixD278A2ProbeAudit *goodix_d278_a2_sensor_only_probe_get_audit (
  const GoodixD278A2SensorOnlyProbe *probe);
GoodixD278A2ProbeAudit *goodix_d278_a2_sensor_only_probe_get_mutable_audit (
  GoodixD278A2SensorOnlyProbe *probe);
gchar *goodix_d278_a2_sensor_only_probe_audit_to_json (
  const GoodixD278A2SensorOnlyProbe *probe);

G_END_DECLS

#endif
