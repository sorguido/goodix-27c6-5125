/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GOODIX_D278_PRECOMMAND_OBSERVER_H
#define GOODIX_D278_PRECOMMAND_OBSERVER_H

#include <gio/gio.h>

G_BEGIN_DECLS

#define GOODIX_D278_06_OBSERVATION_TIMEOUT_MS 1000u
#define GOODIX_D278_06_RECEIVE_SIZE 32768u

typedef struct _GoodixD278PrecommandObserver GoodixD278PrecommandObserver;

typedef enum
{
  GOODIX_D278_PRECOMMAND_TRANSFER_IN,
  GOODIX_D278_PRECOMMAND_TRANSFER_OUT,
} GoodixD278PrecommandDirection;

typedef gboolean (*GoodixD278PrecommandSubmitFunc) (
  GoodixD278PrecommandObserver  *observer,
  GoodixD278PrecommandDirection  direction,
  guint64                        generation,
  gpointer                       user_data,
  GError                       **error);

typedef struct
{
  const gchar *identity_preflight_result;
  guint usb_open_count;
  guint usb_claim_count;
  guint usb_release_count;
  guint usb_close_count;

  guint64 observation_generation;
  guint physical_in_submit_count;
  guint physical_in_completion_count;
  gsize received_byte_count;

  guint out_submit_count;
  guint goodix_command_count;
  guint secure_session_start_count;
  guint tls_handshake_count;

  const gchar *completion_class;
  guint timeout_count;
  guint cancel_count;
  const gchar *error_class;

  const gchar *frame_class;
  gboolean frame_complete;
  gboolean frame_partial;
  gboolean extra_or_concatenated_data;
  gint observed_outer_type;
  gint observed_control;
  gint observed_ack_echo;
  gint observed_ack_status;
  gint observed_body_length;

  guint retry_count;
  guint reopen_count;
  guint device_reset_count;
  guint clear_halt_count;
  guint persistent_device_write_count;

  guint stale_callback_count;
  guint prohibited_out_attempt_count;
  gboolean backend_drained;
  gboolean cleanup_completed;
} GoodixD278PrecommandAudit;

GoodixD278PrecommandObserver *goodix_d278_precommand_observer_new (
  GoodixD278PrecommandSubmitFunc submit_func,
  gpointer                       submit_data);
void goodix_d278_precommand_observer_free (
  GoodixD278PrecommandObserver *observer);

gboolean goodix_d278_precommand_observer_start (
  GoodixD278PrecommandObserver *observer,
  guint64                       generation,
  GError                      **error);
void goodix_d278_precommand_observer_complete (
  GoodixD278PrecommandObserver *observer,
  guint64                       submit_generation,
  const guint8                 *data,
  gsize                         length,
  const GError                 *error);

/* The production observer has no OUT submit function.  This guard exists so
 * host-only seams can prove that any attempted OUT direction fails closed. */
gboolean goodix_d278_precommand_observer_guard_direction (
  GoodixD278PrecommandObserver  *observer,
  GoodixD278PrecommandDirection  direction,
  GError                       **error);

gboolean goodix_d278_precommand_observer_is_terminal (
  const GoodixD278PrecommandObserver *observer);
const GoodixD278PrecommandAudit *goodix_d278_precommand_observer_get_audit (
  const GoodixD278PrecommandObserver *observer);
GoodixD278PrecommandAudit *goodix_d278_precommand_observer_get_mutable_audit (
  GoodixD278PrecommandObserver *observer);
gchar *goodix_d278_precommand_observer_audit_to_json (
  const GoodixD278PrecommandObserver *observer);

G_END_DECLS

#endif
