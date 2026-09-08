/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Host-testable post-TLS lifecycle for APP12509.  It is an independent LGPL
 * implementation from neutral protocol facts and project-owned test vectors.
 */
#include "goodix_post_tls_lifecycle.h"

#include "goodix_a0_protocol.h"

#include <string.h>

typedef enum
{
  GOODIX_POST_TLS_ERROR_ARGUMENT,
  GOODIX_POST_TLS_ERROR_STATE,
  GOODIX_POST_TLS_ERROR_PROTOCOL,
  GOODIX_POST_TLS_ERROR_TRANSPORT,
  GOODIX_POST_TLS_ERROR_IMAGE,
} GoodixPostTlsError;

#define GOODIX_POST_TLS_ERROR (goodix_post_tls_error_quark ())
#define GOODIX_POST_TLS_D4_PRE_SUBMIT_PACING_MS 20u
#define GOODIX_POST_TLS_AF_PRE_SUBMIT_PACING_MS 20u

struct _GoodixPostTlsLifecycle
{
  GoodixFpiUsbBackend *backend;
  guint64 generation;
  GoodixPostTlsMaterial material;
  GoodixPostTlsPhase phase;
  GoodixPostTlsImageFunc image;
  GoodixPostTlsEventFunc finger_down;
  GoodixPostTlsEventFunc release_tail;
  GoodixPostTlsEventFunc finger_up;
  GoodixPostTlsTerminalFunc terminal;
  GoodixPostTlsFirstArmHandoffFunc first_arm_handoff;
  gpointer user_data;
  GoodixPostTlsAudit *audit;
  GError *error;
  gboolean out_pending;
  gboolean backend_callback_owned;
  guint8 expected_ack;
  gboolean ack_seen;
  gboolean framework_await;
  gboolean rearm_submitted;
  gboolean fresh_down_valid;
  guint8 current_fdt_table[12];
  guint8 first_up_table[12];
  guint8 fresh_down_table[12];
  guint16 fdt_raw[3][6];
  guint fdt_raw_count;
  guint8 fdt_threshold;
  gboolean fdt_threshold_valid;
  gboolean fdt_delta_classified;
  uint16_t baseline_samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  gboolean baseline_valid;
  GByteArray *plaintext_pending;
};

static GQuark
goodix_post_tls_error_quark (void)
{
  return g_quark_from_static_string ("goodix-post-tls-lifecycle-error");
}

static void
clear_byte_array (GByteArray *bytes)
{
  if (bytes == NULL)
    return;
  for (gsize i = 0; i < bytes->len; i++)
    ((volatile guint8 *) bytes->data)[i] = 0;
  g_byte_array_set_size (bytes, 0);
}

static void
lifecycle_fail (GoodixPostTlsLifecycle *lifecycle,
                GError                 *error)
{
  if (lifecycle->phase == GOODIX_POST_TLS_PHASE_TERMINAL)
    {
      g_clear_error (&error);
      return;
    }
  if (error == NULL)
    error = g_error_new_literal (GOODIX_POST_TLS_ERROR,
                                 GOODIX_POST_TLS_ERROR_STATE,
                                 "post-TLS lifecycle failed");
  lifecycle->phase = GOODIX_POST_TLS_PHASE_TERMINAL;
  lifecycle->fresh_down_valid = FALSE;
  clear_byte_array (lifecycle->plaintext_pending);
  if (lifecycle->audit != NULL)
    {
      lifecycle->audit->terminal = TRUE;
      lifecycle->audit->fresh_down_table = FALSE;
    }
  lifecycle->error = error;
  goodix_fpi_usb_backend_cancel (lifecycle->backend);
  if (lifecycle->terminal != NULL)
    lifecycle->terminal (lifecycle, lifecycle->error, lifecycle->user_data);
}

static void
lifecycle_fail_literal (GoodixPostTlsLifecycle *lifecycle,
                        GoodixPostTlsError       code,
                        const gchar             *message)
{
  lifecycle_fail (lifecycle,
                  g_error_new_literal (GOODIX_POST_TLS_ERROR, code, message));
}

static GBytes *
fixed64_command (guint8        control,
                 const guint8 *body,
                 gsize         body_length,
                 GError      **error)
{
  g_autoptr(GBytes) logical = NULL;
  g_autoptr(GByteArray) physical = NULL;
  const guint8 *bytes;
  gsize length;
  static const guint8 zeroes[64] = { 0 };

  logical = goodix_a0_build_frame (control, (guint8) (control & 0xfeu),
                                   body, body_length, error);
  if (logical == NULL)
    return NULL;
  bytes = g_bytes_get_data (logical, &length);
  if (length > 64u)
    {
      g_set_error_literal (error, GOODIX_POST_TLS_ERROR,
                           GOODIX_POST_TLS_ERROR_PROTOCOL,
                           "post-TLS command exceeds fixed64");
      return NULL;
    }
  physical = g_byte_array_sized_new (64u);
  g_byte_array_append (physical, bytes, (guint) length);
  g_byte_array_append (physical, zeroes, (guint) (64u - length));
  return g_byte_array_free_to_bytes (g_steal_pointer (&physical));
}

static gboolean
submit_command (GoodixPostTlsLifecycle *lifecycle,
                guint8                  control,
                const guint8           *body,
                gsize                   body_length,
                GoodixPostTlsPhase      next_phase,
                GError                **error)
{
  g_autoptr(GBytes) bytes = NULL;

  if (lifecycle->out_pending ||
      lifecycle->phase == GOODIX_POST_TLS_PHASE_TERMINAL ||
      lifecycle->phase == GOODIX_POST_TLS_PHASE_STOP)
    {
      g_set_error_literal (error, GOODIX_POST_TLS_ERROR,
                           GOODIX_POST_TLS_ERROR_STATE,
                           "post-TLS OUT is duplicated or terminal");
      return FALSE;
    }
  bytes = fixed64_command (control, body, body_length, error);
  if (bytes == NULL)
    return FALSE;
  lifecycle->phase = next_phase;
  lifecycle->expected_ack = control;
  lifecycle->ack_seen = FALSE;
  lifecycle->out_pending = TRUE;
  if (lifecycle->audit != NULL)
    lifecycle->audit->command_count++;
  if (!goodix_fpi_usb_backend_submit_out (lifecycle->backend,
                                          lifecycle->generation, bytes, error))
    {
      lifecycle->out_pending = FALSE;
      return FALSE;
    }
  return TRUE;
}

static gboolean
submit_simple (GoodixPostTlsLifecycle *lifecycle,
               guint8                  control,
               GoodixPostTlsPhase      next_phase,
               GError                **error)
{
  static const guint8 body[] = { 0x01, 0x00 };
  return submit_command (lifecycle, control, body, sizeof body, next_phase,
                         error);
}

static gboolean
derive_fdt (const guint8 raw[12],
            gboolean     finger_up,
            guint8       table[12])
{
  for (guint i = 0; i < 6u; i++)
    {
      guint16 word = (guint16) raw[i * 2u] |
                     ((guint16) raw[i * 2u + 1u] << 8);
      guint value = (guint) (word >> 1) + (finger_up ? 0x1du : 0u);
      if (value > G_MAXUINT8)
        return FALSE;
      table[i * 2u] = 0x80;
      table[i * 2u + 1u] = (guint8) value;
    }
  return TRUE;
}

static gboolean
derive_fdt_baseline (const guint8 raw[12],
                     guint8       table[12])
{
  for (guint i = 0; i < 6u; i++)
    {
      guint16 word = (guint16) raw[i * 2u] |
                     ((guint16) raw[i * 2u + 1u] << 8);
      guint8 component = (guint8) ((word >> 1) & 0xffu);

      if (component == 0x00 || component == 0xff)
        return FALSE;

      table[i * 2u] = 0x80;
      table[i * 2u + 1u] = component;
    }
  return TRUE;
}

static gboolean
record_fdt_raw (GoodixPostTlsLifecycle *lifecycle,
                const guint8            raw[12])
{
  if (lifecycle->fdt_raw_count >= 3u)
    return FALSE;
  for (guint i = 0; i < 6u; i++)
    lifecycle->fdt_raw[lifecycle->fdt_raw_count][i] =
      (guint16) ((guint16) raw[i * 2u] |
                 (guint16) ((guint16) raw[i * 2u + 1u] << 8));
  lifecycle->fdt_raw_count++;
  return TRUE;
}

static gboolean
classify_fdt_delta (GoodixPostTlsLifecycle *lifecycle,
                    guint                   older,
                    guint                   newer)
{
  gboolean within = TRUE;

  if (!lifecycle->fdt_threshold_valid || newer >= lifecycle->fdt_raw_count ||
      older >= newer)
    return FALSE;
  for (guint i = 0; i < 6u; i++)
    {
      guint16 a = lifecycle->fdt_raw[older][i];
      guint16 b = lifecycle->fdt_raw[newer][i];
      guint difference = a >= b ? (guint) (a - b) : (guint) (b - a);
      if (difference > lifecycle->fdt_threshold)
        within = FALSE;
    }
  lifecycle->fdt_delta_classified = TRUE;
  if (lifecycle->audit != NULL)
    {
      lifecycle->audit->fdt_delta_classification_count++;
      if (within)
        lifecycle->audit->fdt_delta_within_threshold_count++;
      else
        lifecycle->audit->fdt_delta_outside_threshold_count++;
    }
  return within;
}

static gboolean
submit_fdt36 (GoodixPostTlsLifecycle *lifecycle,
              GoodixPostTlsPhase      next_phase,
              GError                **error)
{
  guint8 body[14] = { 0x09, 0x01 };
  memcpy (body + 2, lifecycle->current_fdt_table, 12);
  if (lifecycle->audit != NULL)
    lifecycle->audit->fdt36_submit_count++;
  return submit_command (lifecycle, 0x36, body, sizeof body, next_phase, error);
}

static gboolean
submit_arm (GoodixPostTlsLifecycle *lifecycle,
            gboolean                second,
            GError                **error)
{
  guint8 body[16] = { 0x08, 0x01 };
  guint16 timestamp = second ? lifecycle->material.second_arm_timestamp :
                               lifecycle->material.first_arm_timestamp;
  const guint8 *table = second ? lifecycle->fresh_down_table :
                                 lifecycle->current_fdt_table;
  memcpy (body + 2, table, 12);
  body[14] = (guint8) timestamp;
  body[15] = (guint8) (timestamp >> 8);
  if (second && lifecycle->audit != NULL)
    lifecycle->audit->rearm_0x32_count++;
  return submit_command (lifecycle, 0x32, body, sizeof body,
                         second ? GOODIX_POST_TLS_PHASE_SECOND_ARM :
                                  GOODIX_POST_TLS_PHASE_FIRST_ARM,
                         error);
}

static void
backend_out_complete (GoodixFpiUsbBackend *backend,
                      guint64               generation,
                      const GError         *error,
                      gpointer              user_data)
{
  GoodixPostTlsLifecycle *lifecycle = user_data;

  (void) backend;
  if (generation != lifecycle->generation || !lifecycle->out_pending ||
      lifecycle->phase == GOODIX_POST_TLS_PHASE_TERMINAL)
    return;
  lifecycle->out_pending = FALSE;
  if (error != NULL)
    lifecycle_fail (lifecycle, g_error_copy (error));
}

static gboolean
parse_message (GoodixPostTlsLifecycle *lifecycle,
               GBytes                 *frame,
               GoodixA0Message        *message)
{
  const guint8 *bytes;
  gsize length;
  g_autoptr(GError) error = NULL;

  bytes = g_bytes_get_data (frame, &length);
  if (length < 5u ||
      !goodix_a0_parse_frame (frame, bytes[4], message, &error))
    {
      lifecycle_fail (lifecycle, g_steal_pointer (&error));
      return FALSE;
    }
  return TRUE;
}

/* Target-observed 0x50 NAV responses use the OEM 0x88 no-check marker
 * instead of the ordinary additive A0 checksum.  Accept this shape only
 * in the two lifecycle slots that explicitly expect the NAV response. */
static gboolean
parse_nav_no_check (GBytes          *frame,
                    GoodixA0Message *message)
{
  const guint8 *data;
  gsize length;
  guint16 outer_length;
  guint16 inner_length;

  if (frame == NULL || message == NULL)
    return FALSE;

  message->control = 0;
  message->body = NULL;
  data = g_bytes_get_data (frame, &length);

  if (length != 2417u || data[0] != 0xa0)
    return FALSE;

  outer_length = (guint16) data[1] | ((guint16) data[2] << 8);
  if (outer_length != 2413u ||
      data[3] != (guint8) (data[0] + data[1] + data[2]) ||
      data[4] != 0x50)
    return FALSE;

  inner_length = (guint16) data[5] | ((guint16) data[6] << 8);
  if (inner_length != 2410u ||
      data[length - 1u] != 0x88 ||
      data[7] != 0x50 ||
      data[8] != 0x01)
    return FALSE;

  message->control = 0x50;
  message->body = g_bytes_new (data + 7, 2409u);
  return TRUE;
}

static gboolean
accept_ack (GoodixPostTlsLifecycle *lifecycle,
            const GoodixA0Message  *message)
{
  const guint8 *body;
  gsize length;

  if (message->control != 0xb0)
    return FALSE;
  body = g_bytes_get_data (message->body, &length);
  if (lifecycle->ack_seen || length != 2u ||
      body[0] != lifecycle->expected_ack || body[1] != 0x01)
    {
      lifecycle_fail_literal (lifecycle, GOODIX_POST_TLS_ERROR_PROTOCOL,
                              "post-TLS ACK contract mismatch");
      return FALSE;
    }
  lifecycle->ack_seen = TRUE;
  if (lifecycle->audit != NULL)
    lifecycle->audit->ack_count++;
  return TRUE;
}

static gboolean
event_fields (const GoodixA0Message *message,
              guint16               *irq,
              guint16               *flags,
              const guint8         **raw)
{
  const guint8 *body;
  gsize length;

  body = g_bytes_get_data (message->body, &length);
  if (length != 16u)
    return FALSE;
  *irq = (guint16) body[0] | ((guint16) body[1] << 8);
  *flags = (guint16) body[2] | ((guint16) body[3] << 8);
  *raw = body + 4;
  return TRUE;
}

static void
submit_or_fail (GoodixPostTlsLifecycle *lifecycle,
                gboolean                submitted,
                GError                **error)
{
  if (!submitted)
    lifecycle_fail (lifecycle, g_steal_pointer (error));
  else
    g_clear_error (error);
}

static void
maybe_submit_rearm (GoodixPostTlsLifecycle *lifecycle)
{
  g_autoptr(GError) error = NULL;

  if (lifecycle->phase != GOODIX_POST_TLS_PHASE_REARM_GATE ||
      !lifecycle->framework_await || !lifecycle->fresh_down_valid ||
      lifecycle->rearm_submitted)
    return;
  lifecycle->rearm_submitted = TRUE;
  submit_or_fail (lifecycle, submit_arm (lifecycle, TRUE, &error),
                  &error);
}

GoodixPostTlsLifecycle *
goodix_post_tls_lifecycle_new (
  GoodixFpiUsbBackend         *backend,
  guint64                      generation,
  const GoodixPostTlsMaterial *material,
  GoodixPostTlsImageFunc       image,
  GoodixPostTlsEventFunc       finger_down,
  GoodixPostTlsEventFunc       release_tail,
  GoodixPostTlsEventFunc       finger_up,
  GoodixPostTlsTerminalFunc    terminal,
  gpointer                     user_data,
  GoodixPostTlsAudit          *audit,
  GError                     **error)
{
  GoodixPostTlsLifecycle *lifecycle;

  if (backend == NULL || generation == 0 || material == NULL || image == NULL)
    {
      g_set_error_literal (error, GOODIX_POST_TLS_ERROR,
                           GOODIX_POST_TLS_ERROR_ARGUMENT,
                           "post-TLS lifecycle material or owner is absent");
      return NULL;
    }
  if (material->capture_profile <
        GOODIX_POST_TLS_CAPTURE_PROFILE_TWO_ACQUISITION ||
      material->capture_profile >
        GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION)
    {
      g_set_error_literal (error, GOODIX_POST_TLS_ERROR,
                           GOODIX_POST_TLS_ERROR_ARGUMENT,
                           "unsupported post-TLS capture profile");
      return NULL;
    }
  lifecycle = g_new0 (GoodixPostTlsLifecycle, 1);
  lifecycle->backend = backend;
  lifecycle->generation = generation;
  lifecycle->material = *material;
  lifecycle->phase = GOODIX_POST_TLS_PHASE_NOT_STARTED;
  lifecycle->image = image;
  lifecycle->finger_down = finger_down;
  lifecycle->release_tail = release_tail;
  lifecycle->finger_up = finger_up;
  lifecycle->terminal = terminal;
  lifecycle->user_data = user_data;
  lifecycle->audit = audit;
  lifecycle->plaintext_pending = g_byte_array_new ();
  memcpy (lifecycle->current_fdt_table, material->initial_fdt_table, 12);
  if (audit != NULL)
    {
      memset (audit, 0, sizeof *audit);
      audit->generation = generation;
    }
  return lifecycle;
}

void
goodix_post_tls_lifecycle_free (GoodixPostTlsLifecycle *lifecycle)
{
  if (lifecycle == NULL)
    return;
  g_return_if_fail (goodix_fpi_usb_backend_is_drained (lifecycle->backend));
  if (lifecycle->audit != NULL)
    {
      lifecycle->audit->backend_drained = TRUE;
      lifecycle->audit->terminal_cleanup_completed = TRUE;
    }
  if (lifecycle->backend_callback_owned)
    goodix_fpi_usb_backend_set_out_completed_callback (lifecycle->backend,
                                                        NULL, NULL);
  g_clear_error (&lifecycle->error);
  memset (&lifecycle->material, 0, sizeof lifecycle->material);
  memset (lifecycle->current_fdt_table, 0, sizeof lifecycle->current_fdt_table);
  memset (lifecycle->first_up_table, 0, sizeof lifecycle->first_up_table);
  memset (lifecycle->fresh_down_table, 0, sizeof lifecycle->fresh_down_table);
  memset (lifecycle->fdt_raw, 0, sizeof lifecycle->fdt_raw);
  for (gsize i = 0; i < sizeof lifecycle->baseline_samples; i++)
    ((volatile guint8 *) lifecycle->baseline_samples)[i] = 0;
  lifecycle->baseline_valid = FALSE;
  clear_byte_array (lifecycle->plaintext_pending);
  g_byte_array_unref (lifecycle->plaintext_pending);
  g_free (lifecycle);
}

gboolean
goodix_post_tls_lifecycle_set_first_arm_handoff (
  GoodixPostTlsLifecycle           *lifecycle,
  GoodixPostTlsFirstArmHandoffFunc  handoff,
  GError                          **error)
{
  if (lifecycle == NULL || handoff == NULL ||
      lifecycle->phase != GOODIX_POST_TLS_PHASE_NOT_STARTED ||
      lifecycle->first_arm_handoff != NULL)
    {
      g_set_error_literal (error, GOODIX_POST_TLS_ERROR,
                           GOODIX_POST_TLS_ERROR_STATE,
                           "first-arm handoff must be configured once before start");
      return FALSE;
    }
  lifecycle->first_arm_handoff = handoff;
  return TRUE;
}

gboolean
goodix_post_tls_lifecycle_start (GoodixPostTlsLifecycle *lifecycle,
                                 GError                **error)
{
  static const guint8 d4_body[] = { 0x00, 0x00 };

  if (lifecycle == NULL || lifecycle->phase != GOODIX_POST_TLS_PHASE_NOT_STARTED)
    {
      g_set_error_literal (error, GOODIX_POST_TLS_ERROR,
                           GOODIX_POST_TLS_ERROR_STATE,
                           "post-TLS lifecycle cannot start twice");
      return FALSE;
    }
  goodix_fpi_usb_backend_set_out_completed_callback (lifecycle->backend,
                                                      backend_out_complete,
                                                      lifecycle);
  lifecycle->backend_callback_owned = TRUE;

  /* D246 live evidence on this target established a 20 ms quiet interval
   * between cryptographic TLS completion and the canonical fixed64 D4 OUT.
   * Preserve that proven transport timing here; this is a single bounded
   * pre-submit pacing delay, not a retry or recovery action. */
  g_usleep ((gulong) GOODIX_POST_TLS_D4_PRE_SUBMIT_PACING_MS * 1000u);

  if (lifecycle->audit != NULL)
    {
      lifecycle->audit->post_tls_lifecycle_started = TRUE;
      lifecycle->audit->d4_count++;
    }
  return submit_command (lifecycle, 0xd4, d4_body, sizeof d4_body,
                         GOODIX_POST_TLS_PHASE_D4, error);
}

void
goodix_post_tls_lifecycle_handle_a0 (GoodixPostTlsLifecycle *lifecycle,
                                     GBytes                 *frame)
{
  GoodixA0Message message = { 0 };
  const guint8 *body;
  const guint8 *raw;
  gsize length;
  guint16 irq;
  guint16 flags;
  GoodixPostTlsPhase phase_at_entry;
  g_autoptr(GError) error = NULL;

  if (lifecycle == NULL || frame == NULL ||
      lifecycle->phase == GOODIX_POST_TLS_PHASE_TERMINAL ||
      lifecycle->phase == GOODIX_POST_TLS_PHASE_STOP)
    return;

  phase_at_entry = lifecycle->phase;
  if ((lifecycle->phase == GOODIX_POST_TLS_PHASE_FDT_NAV_1 &&
       lifecycle->ack_seen) ||
      lifecycle->phase == GOODIX_POST_TLS_PHASE_RELEASE_NAV)
    {
      if (!parse_nav_no_check (frame, &message))
        {
          lifecycle_fail_literal (lifecycle, GOODIX_POST_TLS_ERROR_PROTOCOL,
                                  "OEM NAV no-check response mismatch");
          return;
        }
    }
  else if (!parse_message (lifecycle, frame, &message))
    return;

  body = g_bytes_get_data (message.body, &length);

  switch (lifecycle->phase)
    {
    case GOODIX_POST_TLS_PHASE_D4:
      if (!accept_ack (lifecycle, &message))
        goto unexpected;
      {
        guint8 af_body[5] = {
          0x55, (guint8) lifecycle->material.af_timestamp,
          (guint8) (lifecycle->material.af_timestamp >> 8), 0x00, 0x00
        };
        /* D251 live evidence retained a bounded 20 ms quiet interval
         * after the exact D4/01 ACK and before the fixed64 AF OUT. */
        g_usleep ((gulong) GOODIX_POST_TLS_AF_PRE_SUBMIT_PACING_MS * 1000u);
        if (lifecycle->audit != NULL)
          lifecycle->audit->af_count++;
        submit_or_fail (lifecycle,
                        submit_command (lifecycle, 0xaf, af_body,
                                        sizeof af_body,
                                        GOODIX_POST_TLS_PHASE_AF, &error),
                        &error);
      }
      break;
    case GOODIX_POST_TLS_PHASE_AF:
      if (message.control != 0xae || length != 16u ||
          (body[1] & 0x01u) != 0 || (body[1] & 0x02u) == 0)
        goto unexpected;
      submit_or_fail (lifecycle,
                      submit_fdt36 (lifecycle,
                                    GOODIX_POST_TLS_PHASE_FDT36_1, &error),
                      &error);
      break;
    case GOODIX_POST_TLS_PHASE_FDT36_1:
    case GOODIX_POST_TLS_PHASE_FDT36_2:
    case GOODIX_POST_TLS_PHASE_FDT36_3:
      if (!accept_ack (lifecycle, &message))
        goto unexpected;
      lifecycle->phase = lifecycle->phase == GOODIX_POST_TLS_PHASE_FDT36_1 ?
        GOODIX_POST_TLS_PHASE_FDT_IRQ100_1 :
        (lifecycle->phase == GOODIX_POST_TLS_PHASE_FDT36_2 ?
         GOODIX_POST_TLS_PHASE_FDT_IRQ100_2 :
         GOODIX_POST_TLS_PHASE_FDT_IRQ100_3);
      break;
    case GOODIX_POST_TLS_PHASE_FDT_IRQ100_1:
    case GOODIX_POST_TLS_PHASE_FDT_IRQ100_2:
    case GOODIX_POST_TLS_PHASE_FDT_IRQ100_3:
      if (message.control != 0x36 ||
          !event_fields (&message, &irq, &flags, &raw) ||
          irq != 0x0100 || flags != 0 ||
          !record_fdt_raw (lifecycle, raw) ||
          !derive_fdt_baseline (raw, lifecycle->current_fdt_table))
        goto unexpected;
      if (lifecycle->audit != NULL)
        lifecycle->audit->fdt_irq100_count++;
      if (lifecycle->phase == GOODIX_POST_TLS_PHASE_FDT_IRQ100_1)
        submit_or_fail (lifecycle,
                        submit_simple (lifecycle, 0x50,
                                       GOODIX_POST_TLS_PHASE_FDT_NAV_1,
                                       &error), &error);
      else if (lifecycle->phase == GOODIX_POST_TLS_PHASE_FDT_IRQ100_2)
        {
          static const guint8 body82[] = { 0x00, 0x82, 0x00, 0x02, 0x00 };
          submit_or_fail (lifecycle,
                          submit_command (lifecycle, 0x82, body82,
                                          sizeof body82,
                                          GOODIX_POST_TLS_PHASE_FDT_82,
                                          &error), &error);
        }
      else
        {
          if (!lifecycle->fdt_delta_classified ||
              !classify_fdt_delta (lifecycle, 1u, 2u))
            goto unexpected;
          if (lifecycle->audit != NULL)
            lifecycle->audit->fresh_fdt_count++;
          submit_or_fail (lifecycle, submit_arm (lifecycle, FALSE, &error),
                          &error);
        }
      break;
    case GOODIX_POST_TLS_PHASE_FDT_NAV_1:
      if (!lifecycle->ack_seen)
        {
          if (!accept_ack (lifecycle, &message))
            goto unexpected;
        }
      else
        {
          if (message.control != 0x50 || length != 2409u)
            goto unexpected;
          submit_or_fail (lifecycle,
                          submit_fdt36 (lifecycle,
                                        GOODIX_POST_TLS_PHASE_FDT36_2,
                                        &error), &error);
        }
      break;
    case GOODIX_POST_TLS_PHASE_FDT_82:
      if (!lifecycle->ack_seen)
        {
          if (!accept_ack (lifecycle, &message))
            goto unexpected;
        }
      else
        {
          if (message.control != 0x82 || length != 2u)
            goto unexpected;
          lifecycle->fdt_threshold = body[1];
          lifecycle->fdt_threshold_valid = TRUE;
          if (!classify_fdt_delta (lifecycle, 0u, 1u))
            goto unexpected;
          submit_or_fail (lifecycle,
                          submit_simple (lifecycle, 0x20,
                                         GOODIX_POST_TLS_PHASE_FDT_20,
                                         &error), &error);
        }
      break;
    case GOODIX_POST_TLS_PHASE_FDT_20:
      if (!accept_ack (lifecycle, &message))
        goto unexpected;
      lifecycle->phase = GOODIX_POST_TLS_PHASE_FDT_B0;
      break;
    case GOODIX_POST_TLS_PHASE_FIRST_ARM:
      if (!accept_ack (lifecycle, &message))
        goto unexpected;
      if (lifecycle->first_arm_handoff != NULL)
        {
          if (lifecycle->out_pending ||
              goodix_fpi_usb_backend_get_out_outstanding (
                lifecycle->backend) != 0u ||
              !lifecycle->backend_callback_owned)
            goto unexpected;
          goodix_fpi_usb_backend_set_out_completed_callback (
            lifecycle->backend, NULL, NULL);
          lifecycle->backend_callback_owned = FALSE;
          lifecycle->phase = GOODIX_POST_TLS_PHASE_STOP;
          if (lifecycle->audit != NULL)
            {
              lifecycle->audit->first_arm_handoff_count++;
              lifecycle->audit->backend_handoff_count++;
            }
          if (!lifecycle->first_arm_handoff (
                lifecycle, lifecycle->backend, lifecycle->generation,
                lifecycle->user_data, &error))
            lifecycle_fail (lifecycle, g_steal_pointer (&error));
          break;
        }
      lifecycle->phase = GOODIX_POST_TLS_PHASE_FIRST_IRQ2;
      break;
    case GOODIX_POST_TLS_PHASE_FIRST_IRQ2:
    case GOODIX_POST_TLS_PHASE_SECOND_IRQ2:
      if (message.control != 0x32 ||
          !event_fields (&message, &irq, &flags, &raw) ||
          irq != 0x0002 || flags != 0x003f)
        goto unexpected;
      if (lifecycle->phase == GOODIX_POST_TLS_PHASE_FIRST_IRQ2)
        {
          if (!derive_fdt (raw, TRUE, lifecycle->first_up_table))
            goto unexpected;
          if (lifecycle->audit != NULL)
            lifecycle->audit->first_irq0002_count++;
          if (lifecycle->finger_down != NULL)
            lifecycle->finger_down (lifecycle, lifecycle->user_data);
          if (lifecycle->audit != NULL)
            lifecycle->audit->first_image_command_count++;
          submit_or_fail (lifecycle,
                          submit_simple (lifecycle, 0x22,
                                         GOODIX_POST_TLS_PHASE_FIRST_22,
                                         &error), &error);
        }
      else
        {
          if (lifecycle->audit != NULL)
            {
              lifecycle->audit->second_irq0002_count++;
              lifecycle->audit->second_image_command_count++;
            }
          if (lifecycle->finger_down != NULL)
            lifecycle->finger_down (lifecycle, lifecycle->user_data);
          submit_or_fail (lifecycle,
                          submit_simple (lifecycle, 0x22,
                                         GOODIX_POST_TLS_PHASE_SECOND_22,
                                         &error), &error);
        }
      break;
    case GOODIX_POST_TLS_PHASE_FIRST_22:
      if (!accept_ack (lifecycle, &message))
        goto unexpected;
      lifecycle->phase = GOODIX_POST_TLS_PHASE_FIRST_B0;
      break;
    case GOODIX_POST_TLS_PHASE_RELEASE_34:
      if (!accept_ack (lifecycle, &message))
        goto unexpected;
      lifecycle->phase = GOODIX_POST_TLS_PHASE_RELEASE_IRQ200;
      break;
    case GOODIX_POST_TLS_PHASE_RELEASE_IRQ200:
      if (message.control != 0x34 ||
          !event_fields (&message, &irq, &flags, &raw) ||
          irq != 0x0200 || flags != 0 ||
          !derive_fdt (raw, FALSE, lifecycle->fresh_down_table))
        goto unexpected;
      lifecycle->fresh_down_valid = TRUE;
      if (lifecycle->audit != NULL)
        {
          lifecycle->audit->irq0200_count++;
          lifecycle->audit->fresh_down_table_count++;
          lifecycle->audit->fresh_down_table = TRUE;
          lifecycle->audit->post_up_0x20_count++;
        }
      submit_or_fail (lifecycle,
                      submit_simple (lifecycle, 0x20,
                                     GOODIX_POST_TLS_PHASE_RELEASE_20,
                                     &error), &error);
      break;
    case GOODIX_POST_TLS_PHASE_RELEASE_20:
      if (!accept_ack (lifecycle, &message))
        goto unexpected;
      lifecycle->phase = GOODIX_POST_TLS_PHASE_RELEASE_B0;
      break;
    case GOODIX_POST_TLS_PHASE_RELEASE_50:
      if (!accept_ack (lifecycle, &message))
        goto unexpected;
      lifecycle->phase = GOODIX_POST_TLS_PHASE_RELEASE_NAV;
      break;
    case GOODIX_POST_TLS_PHASE_RELEASE_NAV:
      if (message.control != 0x50 || length != 2409u)
        goto unexpected;
      lifecycle->phase =
        lifecycle->material.capture_profile ==
          GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION ?
          GOODIX_POST_TLS_PHASE_STOP : GOODIX_POST_TLS_PHASE_REARM_GATE;
      if (lifecycle->audit != NULL)
        {
          lifecycle->audit->nav_response_count++;
          lifecycle->audit->release_tail_complete_count++;
          if (lifecycle->phase == GOODIX_POST_TLS_PHASE_STOP)
            lifecycle->audit->single_acquisition_terminal_count++;
        }
      if (lifecycle->release_tail != NULL)
        lifecycle->release_tail (lifecycle, lifecycle->user_data);
      if (lifecycle->finger_up != NULL)
        lifecycle->finger_up (lifecycle, lifecycle->user_data);
      maybe_submit_rearm (lifecycle);
      break;
    case GOODIX_POST_TLS_PHASE_SECOND_ARM:
      if (!accept_ack (lifecycle, &message))
        goto unexpected;
      lifecycle->phase = GOODIX_POST_TLS_PHASE_SECOND_IRQ2;
      break;
    case GOODIX_POST_TLS_PHASE_SECOND_22:
      if (!accept_ack (lifecycle, &message))
        goto unexpected;
      lifecycle->phase = GOODIX_POST_TLS_PHASE_SECOND_B0;
      break;
    default:
      goto unexpected;
    }
  goodix_a0_message_clear (&message);
  return;

unexpected:
  if (lifecycle->audit != NULL)
    {
      const guint8 *rejected_body = NULL;
      const guint8 *rejected_raw = NULL;
      gsize rejected_length = 0;
      guint16 rejected_irq = 0;
      guint16 rejected_flags = 0;

      if (message.body != NULL)
        rejected_body = g_bytes_get_data (message.body, &rejected_length);

      lifecycle->audit->rejected_a0_observed = TRUE;
      lifecycle->audit->rejected_a0_phase = phase_at_entry;
      lifecycle->audit->rejected_a0_control = message.control;
      lifecycle->audit->rejected_a0_body_length =
        message.body != NULL ? (gssize) rejected_length : (gssize) -1;
      lifecycle->audit->rejected_a0_irq = -1;
      lifecycle->audit->rejected_a0_flags = -1;

      if (rejected_body != NULL &&
          event_fields (&message, &rejected_irq,
                        &rejected_flags, &rejected_raw))
        {
          lifecycle->audit->rejected_a0_irq = rejected_irq;
          lifecycle->audit->rejected_a0_flags = rejected_flags;
        }
    }

  goodix_a0_message_clear (&message);
  lifecycle_fail_literal (lifecycle, GOODIX_POST_TLS_ERROR_PROTOCOL,
                          "unexpected post-TLS A0 frame or state");
}

void
goodix_post_tls_lifecycle_handle_plaintext (GoodixPostTlsLifecycle *lifecycle,
                                            GBytes                 *plaintext)
{
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  GoodixImageDecodeAudit decode_audit;
  g_autoptr(GBytes) assembled = NULL;
  g_autoptr(GError) error = NULL;

  if (lifecycle == NULL || plaintext == NULL ||
      lifecycle->phase == GOODIX_POST_TLS_PHASE_TERMINAL ||
      lifecycle->phase == GOODIX_POST_TLS_PHASE_STOP)
    return;
  if (lifecycle->phase == GOODIX_POST_TLS_PHASE_RELEASE_B0)
    {
      if (lifecycle->audit != NULL)
        {
          lifecycle->audit->post_up_b0_count++;
          lifecycle->audit->nav_0x50_count++;
        }
      submit_or_fail (lifecycle,
                      submit_simple (lifecycle, 0x50,
                                     GOODIX_POST_TLS_PHASE_RELEASE_50,
                                     &error), &error);
      return;
    }
  if (lifecycle->phase != GOODIX_POST_TLS_PHASE_FDT_B0 &&
      lifecycle->phase != GOODIX_POST_TLS_PHASE_FIRST_B0 &&
      lifecycle->phase != GOODIX_POST_TLS_PHASE_SECOND_B0)
    {
      lifecycle_fail_literal (lifecycle, GOODIX_POST_TLS_ERROR_PROTOCOL,
                              "TLS plaintext arrived outside a B0 slot");
      return;
    }
  {
    gsize chunk_length;
    const guint8 *chunk = g_bytes_get_data (plaintext, &chunk_length);
    guint16 declared_length;
    gsize expected_length;

    if (chunk_length > GOODIX_IMAGE_PLAINTEXT_LENGTH ||
        (gsize) lifecycle->plaintext_pending->len >
          (gsize) GOODIX_IMAGE_PLAINTEXT_LENGTH - chunk_length)
      {
        lifecycle_fail_literal (lifecycle, GOODIX_POST_TLS_ERROR_IMAGE,
                                "image plaintext reassembly overflow");
        return;
      }
    g_byte_array_append (lifecycle->plaintext_pending, chunk,
                         (guint) chunk_length);
    if (lifecycle->plaintext_pending->len < 3u)
      return;
    declared_length = (guint16) (
      (guint16) lifecycle->plaintext_pending->data[1] |
      (guint16) ((guint16) lifecycle->plaintext_pending->data[2] << 8));
    expected_length = (gsize) declared_length + 3u;
    if (expected_length != GOODIX_IMAGE_PLAINTEXT_LENGTH ||
        lifecycle->plaintext_pending->len > expected_length)
      {
        lifecycle_fail_literal (lifecycle, GOODIX_POST_TLS_ERROR_IMAGE,
                                "image plaintext reassembly shape mismatch");
        return;
      }
    if (lifecycle->plaintext_pending->len < expected_length)
      return;
    assembled = g_bytes_new_static (lifecycle->plaintext_pending->data,
                                    lifecycle->plaintext_pending->len);
  }
  if (!goodix_image_decode_plaintext (assembled, samples, &decode_audit,
                                      &error))
    {
      clear_byte_array (lifecycle->plaintext_pending);
      lifecycle_fail (lifecycle, g_steal_pointer (&error));
      return;
    }
  clear_byte_array (lifecycle->plaintext_pending);
  if (lifecycle->phase == GOODIX_POST_TLS_PHASE_FDT_B0)
    {
      memcpy (lifecycle->baseline_samples, samples, sizeof samples);
      lifecycle->baseline_valid = TRUE;
      if (lifecycle->audit != NULL)
        {
          lifecycle->audit->baseline_b0_count++;
          lifecycle->audit->baseline_decode_count++;
        }
      lifecycle->phase = GOODIX_POST_TLS_PHASE_FDT36_3;
      submit_or_fail (lifecycle,
                      submit_fdt36 (lifecycle,
                                    GOODIX_POST_TLS_PHASE_FDT36_3, &error),
                      &error);
      return;
    }
  if (lifecycle->phase == GOODIX_POST_TLS_PHASE_FIRST_B0)
    {
      guint8 body34[14] = { 0x0a, 0x01 };
      if (lifecycle->audit != NULL)
        {
          lifecycle->audit->first_image_b0_count++;
          lifecycle->audit->first_image_decode_count++;
        }
      if (!lifecycle->image (lifecycle, 1u, samples, lifecycle->user_data,
                             &error))
        {
          lifecycle_fail (lifecycle, g_steal_pointer (&error));
          return;
        }
      if (lifecycle->audit != NULL)
        {
          lifecycle->audit->first_image_pipeline_count++;
          lifecycle->audit->release_0x34_count++;
        }
      memcpy (body34 + 2, lifecycle->first_up_table, 12);
      submit_or_fail (lifecycle,
                      submit_command (lifecycle, 0x34, body34, sizeof body34,
                                      GOODIX_POST_TLS_PHASE_RELEASE_34,
                                      &error), &error);
      return;
    }

  if (lifecycle->audit != NULL)
    {
      lifecycle->audit->second_b0_count++;
      lifecycle->audit->second_image_decode_count++;
    }
  if (!lifecycle->image (lifecycle, 2u, samples, lifecycle->user_data, &error))
    {
      lifecycle_fail (lifecycle, g_steal_pointer (&error));
      return;
    }
  if (lifecycle->audit != NULL)
    lifecycle->audit->second_image_pipeline_count++;
  lifecycle->phase = GOODIX_POST_TLS_PHASE_STOP;
}

void
goodix_post_tls_lifecycle_set_framework_await_finger_on (
  GoodixPostTlsLifecycle *lifecycle,
  guint64                 generation,
  gboolean                awaiting)
{
  if (lifecycle == NULL || generation != lifecycle->generation ||
      lifecycle->phase == GOODIX_POST_TLS_PHASE_TERMINAL ||
      lifecycle->phase == GOODIX_POST_TLS_PHASE_STOP)
    return;
  lifecycle->framework_await = awaiting;
  if (awaiting && lifecycle->audit != NULL)
    lifecycle->audit->framework_rearm_gate_seen = TRUE;
  maybe_submit_rearm (lifecycle);
}

void
goodix_post_tls_lifecycle_cancel (GoodixPostTlsLifecycle *lifecycle,
                                  const gchar            *reason)
{
  if (lifecycle == NULL || lifecycle->phase == GOODIX_POST_TLS_PHASE_TERMINAL)
    return;
  lifecycle_fail_literal (lifecycle, GOODIX_POST_TLS_ERROR_STATE,
                          reason != NULL ? reason :
                                           "post-TLS lifecycle cancelled");
}

const gchar *
goodix_post_tls_phase_name (GoodixPostTlsPhase phase)
{
  switch (phase)
    {
    case GOODIX_POST_TLS_PHASE_NOT_STARTED:
      return "NOT_STARTED";
    case GOODIX_POST_TLS_PHASE_D4:
      return "D4";
    case GOODIX_POST_TLS_PHASE_AF:
      return "AF";
    case GOODIX_POST_TLS_PHASE_FDT36_1:
      return "FDT36_1";
    case GOODIX_POST_TLS_PHASE_FDT_IRQ100_1:
      return "FDT_IRQ100_1";
    case GOODIX_POST_TLS_PHASE_FDT_NAV_1:
      return "FDT_NAV_1";
    case GOODIX_POST_TLS_PHASE_FDT36_2:
      return "FDT36_2";
    case GOODIX_POST_TLS_PHASE_FDT_IRQ100_2:
      return "FDT_IRQ100_2";
    case GOODIX_POST_TLS_PHASE_FDT_82:
      return "FDT_82";
    case GOODIX_POST_TLS_PHASE_FDT_20:
      return "FDT_20";
    case GOODIX_POST_TLS_PHASE_FDT_B0:
      return "FDT_B0";
    case GOODIX_POST_TLS_PHASE_FDT36_3:
      return "FDT36_3";
    case GOODIX_POST_TLS_PHASE_FDT_IRQ100_3:
      return "FDT_IRQ100_3";
    case GOODIX_POST_TLS_PHASE_FIRST_ARM:
      return "FIRST_ARM";
    case GOODIX_POST_TLS_PHASE_FIRST_IRQ2:
      return "FIRST_IRQ2";
    case GOODIX_POST_TLS_PHASE_FIRST_22:
      return "FIRST_22";
    case GOODIX_POST_TLS_PHASE_FIRST_B0:
      return "FIRST_B0";
    case GOODIX_POST_TLS_PHASE_RELEASE_34:
      return "RELEASE_34";
    case GOODIX_POST_TLS_PHASE_RELEASE_IRQ200:
      return "RELEASE_IRQ200";
    case GOODIX_POST_TLS_PHASE_RELEASE_20:
      return "RELEASE_20";
    case GOODIX_POST_TLS_PHASE_RELEASE_B0:
      return "RELEASE_B0";
    case GOODIX_POST_TLS_PHASE_RELEASE_50:
      return "RELEASE_50";
    case GOODIX_POST_TLS_PHASE_RELEASE_NAV:
      return "RELEASE_NAV";
    case GOODIX_POST_TLS_PHASE_REARM_GATE:
      return "REARM_GATE";
    case GOODIX_POST_TLS_PHASE_SECOND_ARM:
      return "SECOND_ARM";
    case GOODIX_POST_TLS_PHASE_SECOND_IRQ2:
      return "SECOND_IRQ2";
    case GOODIX_POST_TLS_PHASE_SECOND_22:
      return "SECOND_22";
    case GOODIX_POST_TLS_PHASE_SECOND_B0:
      return "SECOND_B0";
    case GOODIX_POST_TLS_PHASE_STOP:
      return "STOP";
    case GOODIX_POST_TLS_PHASE_TERMINAL:
      return "TERMINAL";
    }
  return "UNKNOWN";
}

GoodixPostTlsPhase
goodix_post_tls_lifecycle_get_phase (const GoodixPostTlsLifecycle *lifecycle)
{
  return lifecycle != NULL ? lifecycle->phase :
                             GOODIX_POST_TLS_PHASE_TERMINAL;
}

GoodixPostTlsCaptureProfile
goodix_post_tls_lifecycle_get_capture_profile (
  const GoodixPostTlsLifecycle *lifecycle)
{
  return lifecycle != NULL ? lifecycle->material.capture_profile :
                             GOODIX_POST_TLS_CAPTURE_PROFILE_TWO_ACQUISITION;
}

const GError *
goodix_post_tls_lifecycle_get_error (const GoodixPostTlsLifecycle *lifecycle)
{
  return lifecycle != NULL ? lifecycle->error : NULL;
}

gboolean
goodix_post_tls_lifecycle_needs_receive (
  const GoodixPostTlsLifecycle *lifecycle)
{
  return lifecycle != NULL &&
         lifecycle->phase != GOODIX_POST_TLS_PHASE_NOT_STARTED &&
         lifecycle->phase != GOODIX_POST_TLS_PHASE_STOP &&
         lifecycle->phase != GOODIX_POST_TLS_PHASE_TERMINAL;
}

gboolean
goodix_post_tls_lifecycle_copy_baseline (
  const GoodixPostTlsLifecycle *lifecycle,
  uint16_t                      samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT])
{
  if (lifecycle == NULL || samples == NULL || !lifecycle->baseline_valid)
    return FALSE;
  memcpy (samples, lifecycle->baseline_samples,
          sizeof lifecycle->baseline_samples);
  return TRUE;
}
