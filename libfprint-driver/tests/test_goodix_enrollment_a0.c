/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Synthetic enrollment protocol regression. No device or biometric fixtures. */
#include "goodix_enrollment_fpi_usb_binding.h"
#include "goodix_usb_router.h"

#include <fpi-image.h>
#include <string.h>

typedef struct
{
  GoodixEnrollmentPostTlsEvents *events; /* Owned by binding. */
  GoodixEnrollmentFpiUsbBinding *binding;
  GoodixFpiUsbBackend *backend;
  GoodixUsbRouter *router;
  GCancellable *cancellable;
  GoodixEnrollmentPostTlsEventsAudit audit;
  GoodixEnrollmentFpiUsbBindingAudit binding_audit;
  guint images;
  guint commands[256];
  guint8 last_control;
  guint8 last_out[64];
  guint reject_from_stage;
  guint fail_stage;
} Fixture;

static gboolean
image_ready (GoodixEnrollmentPipeline *pipeline, guint stage,
             FpImage *image, gpointer user_data, GError **error)
{
  Fixture *f = user_data;
  (void) pipeline;
  (void) error;
  g_assert_true (FP_IS_IMAGE (image));
  g_assert_cmpuint (stage, ==, f->images + 1u);
  f->images++;
  if (stage == f->fail_stage)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA, "synthetic quality failure");
      return FALSE;
    }
  if (f->reject_from_stage != 0u && stage >= f->reject_from_stage)
    return goodix_enrollment_pipeline_retry_current_stage (pipeline, error);
  return TRUE;
}

static gboolean
timestamp_ready (guint stage, GoodixEnrollmentCommandPurpose purpose,
                 guint16 *timestamp, gpointer user_data, GError **error)
{
  (void) purpose;
  (void) user_data;
  (void) error;
  *timestamp = (guint16) (0x3000u + stage);
  return TRUE;
}

static gboolean
auxiliary_ready (GBytes *plaintext, gpointer user_data, GError **error)
{
  (void) user_data;
  (void) error;
  g_assert_nonnull (plaintext);
  return TRUE;
}

static void
submit_seam (GoodixFpiUsbBackend *backend, GoodixUsbDirection direction,
             guint64 generation, GBytes *bytes, gpointer user_data)
{
  Fixture *f = user_data;
  gsize length;
  const guint8 *data = g_bytes_get_data (bytes, &length);
  (void) backend;
  g_assert_cmpint (direction, ==, GOODIX_USB_TRANSFER_OUT);
  g_assert_cmpuint (generation, ==, 7u);
  g_assert_cmpuint (length, ==, GOODIX_ENROLLMENT_FIXED64_LENGTH);
  f->last_control = data[4];
  f->commands[data[4]]++;
  memcpy (f->last_out, data, sizeof f->last_out);
}

static void
fixture_init_config (Fixture *f, guint max_contacts, gboolean recovery)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 8u,
    .max_physical_stage_count = max_contacts,
    .defer_terminal_stage_delivery_until_release_ready = TRUE,
    .defer_intermediate_stage_delivery_until_release_ready = TRUE,
  };
  g_autoptr(GError) error = NULL;
  *f = (Fixture) { 0 };
  f->cancellable = g_cancellable_new ();
  f->router = goodix_usb_router_new (NULL, NULL, NULL);
  goodix_usb_router_begin_generation (f->router, 7u);
  f->backend = goodix_fpi_usb_backend_new (NULL, f->router, 0x81, 0x01, 8192u);
  g_assert_true (goodix_fpi_usb_backend_begin_generation (
    f->backend, 7u, f->cancellable, &error));
  goodix_fpi_usb_backend_set_async_submit_seam (f->backend, submit_seam, f);
  f->events = goodix_enrollment_post_tls_events_new (
    &config, image_ready, timestamp_ready, auxiliary_ready, f, &f->audit, &error);
  if (recovery)
    goodix_enrollment_post_tls_events_enable_zero_recovery (f->events);
  f->binding = goodix_enrollment_fpi_usb_binding_new (
    f->events, f->backend, 7u, &f->binding_audit, &error);
  g_assert_no_error (error);
  g_assert_nonnull (f->binding);
}

static void
fixture_init (Fixture *f)
{
  fixture_init_config (f, 0u, FALSE);
}

static void
fixture_clear (Fixture *f)
{
  g_assert_cmpuint (goodix_fpi_usb_backend_get_real_submit_count (f->backend), ==, 0u);
  goodix_enrollment_fpi_usb_binding_cancel (f->binding, "synthetic cleanup");
  if (!goodix_fpi_usb_backend_is_drained (f->backend))
    {
      g_autoptr(GError) error = g_error_new_literal (
        G_IO_ERROR, G_IO_ERROR_CANCELLED, "synthetic OUT cancelled");
      goodix_fpi_usb_backend_complete_out (f->backend, 7u, error);
    }
  g_assert_true (goodix_fpi_usb_backend_is_drained (f->backend));
  g_assert_true (goodix_enrollment_fpi_usb_binding_can_free (f->binding));
  goodix_enrollment_fpi_usb_binding_free (f->binding);
  goodix_fpi_usb_backend_free (f->backend);
  goodix_usb_router_free (f->router);
  g_object_unref (f->cancellable);
}

static GBytes *
frame (guint8 control, const guint8 *body, gsize length)
{
  g_autoptr(GError) error = NULL;
  GBytes *bytes = goodix_a0_build_frame (control, control, body, length, &error);
  g_assert_no_error (error);
  return bytes;
}

static GBytes *
irq_frame (guint8 control, guint16 irq, guint16 flags, gsize body_length)
{
  guint8 body[17] = { 0 };
  body[0] = (guint8) irq;
  body[1] = (guint8) (irq >> 8);
  body[2] = (guint8) flags;
  body[3] = (guint8) (flags >> 8);
  for (guint i = 0; i < 6u; i++)
    body[4u + i * 2u] = (guint8) (0x88u + i * 2u);
  return frame (control, body, body_length);
}

static GBytes *
zero_mask_raw_frame (guint index, guint16 word)
{
  guint8 body[16] = { 0, 0x01 };
  g_assert_cmpuint (index, <, 6u);
  for (guint i = 0; i < 6u; i++)
    body[4u + i * 2u] = (guint8) (0x88u + i * 2u);
  body[4u + index * 2u] = (guint8) word;
  body[5u + index * 2u] = (guint8) (word >> 8);
  return frame (0x36, body, sizeof body);
}

static void
accept_a0 (Fixture *f, GBytes *bytes)
{
  g_autoptr(GError) error = NULL;
  g_assert_true (goodix_enrollment_fpi_usb_binding_handle_a0 (f->binding, bytes, &error));
  g_assert_no_error (error);
}

static void
accept_irq (Fixture *f, guint8 control, guint16 irq, guint16 flags)
{
  g_autoptr(GBytes) bytes = irq_frame (control, irq, flags, 16u);
  accept_a0 (f, bytes);
}

static void
ack (Fixture *f, guint8 control)
{
  const guint8 body[] = { control, 0x01 };
  g_autoptr(GBytes) bytes = frame (0xb0, body, sizeof body);
  g_assert_true (goodix_enrollment_fpi_usb_binding_has_pending (f->binding));
  g_assert_cmphex (f->last_control, ==, control);
  goodix_fpi_usb_backend_complete_out (f->backend, 7u, NULL);
  accept_a0 (f, bytes);
}

static GBytes *
primary (void)
{
  guint8 bytes[GOODIX_IMAGE_PLAINTEXT_LENGTH] = { 0x20, 0x0a, 0x1e };
  guint32 crc = 0xffffffffu;
  for (guint i = 0; i < GOODIX_IMAGE_PACKED_LENGTH; i++)
    {
      crc ^= (guint32) bytes[8u + i] << 24;
      for (guint bit = 0; bit < 8u; bit++)
        crc = (crc & 0x80000000u) ? (crc << 1) ^ 0x04c11db7u : crc << 1;
    }
  bytes[7688] = (guint8) (crc >> 8);
  bytes[7689] = (guint8) crc;
  bytes[7690] = (guint8) (crc >> 24);
  bytes[7691] = (guint8) (crc >> 16);
  bytes[7692] = 0x88;
  return g_bytes_new (bytes, sizeof bytes);
}

static void
feed_b0 (Fixture *f, gboolean image)
{
  static const guint8 opaque[] = { 0x20, 0x01, 0x00, 0x00 };
  g_autoptr(GBytes) bytes = image ? primary () : g_bytes_new_static (opaque, sizeof opaque);
  g_autoptr(GError) error = NULL;
  g_assert_true (goodix_enrollment_fpi_usb_binding_handle_plaintext_chunk (f->binding, bytes, &error));
  g_assert_no_error (error);
}

static void
begin_contact (Fixture *f, guint stage)
{
  accept_irq (f, 0x32, 0x0002, 0x002f);
  ack (f, 0x22);
  feed_b0 (f, TRUE);
  g_assert_cmpuint (f->images, ==, stage - 1u);
  ack (f, 0x34);
  if (stage > 1u)
    {
      ack (f, 0x36);
      g_assert_cmpint (goodix_enrollment_post_tls_events_get_expected_event (f->events),
                       ==, GOODIX_ENROLLMENT_EVENT_IRQ0100);
      g_assert_cmpuint (f->images, ==, stage - 1u);
    }
}

static void
finish_contact (Fixture *f, guint stage, guint16 flags)
{
  if (stage > 1u)
    {
      accept_irq (f, 0x36, 0x0100, flags);
      ack (f, 0x20);
      feed_b0 (f, FALSE);
      ack (f, 0x34);
    }
  g_assert_cmpuint (f->images, ==, stage);
  accept_irq (f, 0x34, 0x0200, 0u);
  if (stage == 1u)
    {
      guint8 body[2409] = { 0x50, 0x01 };
      g_autoptr(GBytes) additive = frame (0x50, body, sizeof body);
      gsize length;
      const guint8 *data = g_bytes_get_data (additive, &length);
      guint8 *copy = g_memdup2 (data, length);
      g_autoptr(GBytes) nav = NULL;
      copy[length - 1u] = 0x88;
      nav = g_bytes_new_take (copy, length);
      ack (f, 0x20);
      feed_b0 (f, FALSE);
      ack (f, 0x32);
      ack (f, 0x50);
      accept_a0 (f, nav);
    }
  if (stage < 8u)
    ack (f, 0x32);
}

static void
reach_sample (Fixture *f, guint stage)
{
  fixture_init (f);
  for (guint contact = 1u; contact < stage; contact++)
    {
      begin_contact (f, contact);
      finish_contact (f, contact, 0x002f);
    }
  begin_contact (f, stage);
}

static void
reject_without_progress (Fixture *f, GBytes *bytes, const gchar *reason,
                         gboolean unusable_contact)
{
  g_autoptr(GError) error = NULL;
  guint commands[256];
  guint images = f->images;
  guint parsed;
  guint rejected;
  memcpy (commands, f->commands, sizeof commands);
  g_assert_false (goodix_enrollment_fpi_usb_binding_handle_a0 (f->binding, bytes, &error));
  g_assert_nonnull (error);
  g_assert_cmpint (goodix_enrollment_post_tls_events_error_is_unusable_contact (error),
                   ==, unusable_contact);
  if (reason != NULL)
    g_assert_nonnull (strstr (error->message, reason));
  g_assert_true (goodix_enrollment_fpi_usb_binding_is_failed (f->binding));
  g_assert_cmpuint (f->images, ==, images);
  g_assert_cmpmem (commands, sizeof commands, f->commands, sizeof f->commands);
  g_assert_cmpuint (f->audit.lifecycle.plan.pipeline.protocol.retry_stage_count, ==, 0u);
  g_assert_cmpuint (f->binding_audit.retry_count, ==, 0u);
  parsed = f->audit.parsed_a0_count;
  rejected = f->audit.rejected_inbound_count;
  /* A second input cannot revive the failed graph or emit a new command. */
  g_clear_error (&error);
  g_assert_false (goodix_enrollment_fpi_usb_binding_handle_a0 (f->binding, bytes, &error));
  g_assert_nonnull (error);
  g_assert_cmpmem (commands, sizeof commands, f->commands, sizeof f->commands);
  g_assert_cmpuint (f->images, ==, images);
  g_assert_cmpuint (f->audit.parsed_a0_count, ==, parsed);
  g_assert_cmpuint (f->audit.rejected_inbound_count, ==, rejected);
}

static void
test_zero_flags (gconstpointer data)
{
  guint stage = GPOINTER_TO_UINT (data);
  Fixture f;
  g_autoptr(GBytes) bytes = irq_frame (0x36, 0x0100, 0u, 16u);
  reach_sample (&f, stage);
  guint parsed = f.audit.parsed_a0_count;
  reject_without_progress (&f, bytes, "zero-mask contact unusable", TRUE);
  g_assert_cmpuint (f.audit.parsed_a0_count, ==, parsed + 1u);
  g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.fpimage_construct_count, ==, stage);
  g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.fpimage_delivery_count, ==, stage - 1u);
  g_assert_cmpuint (f.audit.rejected_inbound_count, ==, 0u);
  g_assert_cmpint (goodix_enrollment_post_tls_events_get_expected_event (f.events),
                   ==, GOODIX_ENROLLMENT_EVENT_NONE);
  fixture_clear (&f);
}

static void
test_zero_raw_valid_boundary (gconstpointer data)
{
  guint16 word = (guint16) GPOINTER_TO_UINT (data);
  for (guint index = 0; index < 6u; index++)
    {
      Fixture f;
      g_autoptr(GBytes) bytes = zero_mask_raw_frame (index, word);
      reach_sample (&f, 2u);
      reject_without_progress (&f, bytes, "zero-mask contact unusable", TRUE);
      g_assert_cmpuint (f.audit.rejected_inbound_count, ==, 0u);
      g_assert_cmpuint (f.images, ==, 1u);
      fixture_clear (&f);
    }
}

static void
test_zero_raw_invalid (gconstpointer data)
{
  guint index = GPOINTER_TO_UINT (data);
  const guint16 words[] = { 0x0000u, 0x0001u, 0x01feu, 0x01ffu, 0xffffu };
  for (guint i = 0; i < G_N_ELEMENTS (words); i++)
    {
      Fixture f;
      g_autoptr(GBytes) bytes = zero_mask_raw_frame (index, words[i]);
      reach_sample (&f, 2u);
      reject_without_progress (&f, bytes, NULL, FALSE);
      g_assert_cmpuint (f.audit.rejected_inbound_count, ==, 1u);
      g_assert_cmpuint (f.images, ==, 1u);
      fixture_clear (&f);
    }
}

static void
test_cancel_before_zero (void)
{
  Fixture f;
  g_autoptr(GBytes) bytes = irq_frame (0x36, 0x0100, 0u, 16u);
  reach_sample (&f, 2u);
  guint parsed = f.audit.parsed_a0_count;
  goodix_enrollment_fpi_usb_binding_cancel (f.binding, "cancel before zero-mask");
  reject_without_progress (&f, bytes, NULL, FALSE);
  g_assert_cmpuint (f.audit.parsed_a0_count, ==, parsed);
  g_assert_cmpuint (f.audit.rejected_inbound_count, ==, 0u);
  g_assert_cmpuint (f.images, ==, 1u);
  fixture_clear (&f);
}

static void
test_zero_after_terminal (void)
{
  Fixture f;
  g_autoptr(GBytes) zero = irq_frame (0x36, 0x0100, 0u, 16u);
  g_autoptr(GBytes) other = irq_frame (0x34, 0x0200, 0u, 16u);
  reach_sample (&f, 2u);
  reject_without_progress (&f, zero, "zero-mask contact unusable", TRUE);
  guint parsed = f.audit.parsed_a0_count;
  /* Late release and repeated zero cannot resume the terminal graph. */
  reject_without_progress (&f, other, NULL, FALSE);
  reject_without_progress (&f, zero, NULL, FALSE);
  g_assert_cmpuint (f.audit.parsed_a0_count, ==, parsed);
  g_assert_cmpuint (f.audit.rejected_inbound_count, ==, 0u);
  g_assert_cmpuint (f.images, ==, 1u);
  fixture_clear (&f);
}

static void
test_valid_flags (gconstpointer data)
{
  guint16 flags = (guint16) GPOINTER_TO_UINT (data);
  Fixture f;
  fixture_init (&f);
  for (guint stage = 1u; stage <= 8u; stage++)
    {
      begin_contact (&f, stage);
      finish_contact (&f, stage, flags);
    }
  g_assert_true (goodix_enrollment_fpi_usb_binding_is_complete (f.binding));
  g_assert_cmpuint (f.audit.rejected_inbound_count, ==, 0u);
  g_assert_cmpuint (f.images, ==, 8u);
  g_assert_cmpuint (f.commands[0x20], ==, 8u);
  g_assert_cmpuint (f.commands[0x32], ==, 8u); /* First NAV prepare plus seven rearms. */
  g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.protocol.terminal_transition_count, ==, 1u);
  g_assert_false (goodix_enrollment_fpi_usb_binding_has_pending (f.binding));
  fixture_clear (&f);
}

static void
test_invalid (gconstpointer data)
{
  const gchar *kind = data;
  const gchar *reason = NULL;
  Fixture f;
  g_autoptr(GBytes) bytes = NULL;
  reach_sample (&f, 2u);
  if (g_str_equal (kind, "control"))
    { bytes = irq_frame (0x34, 0x0100, 0u, 16u); reason = "reason=control"; }
  else if (g_str_equal (kind, "irq"))
    { bytes = irq_frame (0x36, 0x0200, 0u, 16u); reason = "reason=irq"; }
  else if (g_str_equal (kind, "reserved"))
    { bytes = irq_frame (0x36, 0x0100, 0x0040, 16u); reason = "reason=flags-reserved"; }
  else if (g_str_equal (kind, "body-length"))
    { bytes = irq_frame (0x36, 0x0100, 0u, 15u); reason = "reason=body-length"; }
  else if (g_str_equal (kind, "ack"))
    {
      const guint8 body[] = { 0x36, 0x01 };
      bytes = frame (0xb0, body, sizeof body);
      reason = "reason=control";
    }
  else
    {
      g_autoptr(GBytes) valid = irq_frame (0x36, 0x0100, 0u, 16u);
      gsize length;
      const guint8 *source = g_bytes_get_data (valid, &length);
      guint8 *copy = g_memdup2 (source, length);
      if (g_str_equal (kind, "checksum"))
        { copy[length - 1u] ^= 1u; reason = "checksum mismatch"; }
      else
        { length--; reason = "outer length is inconsistent"; }
      bytes = g_bytes_new_take (copy, length);
    }
  reject_without_progress (&f, bytes, reason, FALSE);
  g_assert_cmpuint (f.audit.rejected_inbound_count, ==, 1u);
  fixture_clear (&f);
}

static void
test_wrong_state (void)
{
  Fixture f;
  g_autoptr(GBytes) bytes = irq_frame (0x36, 0x0100, 0u, 16u);
  fixture_init (&f);
  reject_without_progress (&f, bytes, "expected IRQ2", FALSE);
  g_assert_cmpuint (f.audit.rejected_inbound_count, ==, 1u);
  g_assert_cmpuint (f.images, ==, 0u);
  fixture_clear (&f);
}


static void
reach_recovery (Fixture *f, guint stage, guint max_contacts)
{
  fixture_init_config (f, max_contacts, TRUE);
  for (guint contact = 1u; contact < stage; contact++)
    {
      begin_contact (f, contact);
      finish_contact (f, contact, 0x002f);
    }
  begin_contact (f, stage);
}

static void
request_sample (Fixture *f)
{
  g_autoptr(GError) error = NULL;
  g_assert_true (goodix_enrollment_fpi_usb_binding_request_zero_sample (f->binding, &error));
  g_assert_no_error (error);
}

static void
test_recovery_stage (gconstpointer data)
{
  guint stage = GPOINTER_TO_UINT (data);
  Fixture f;
  reach_recovery (&f, stage, 0u);
  guint commands[256];
  memcpy (commands, f.commands, sizeof commands);
  guint aux = f.audit.auxiliary_b0_count;
  accept_irq (&f, 0x36, 0x0100, 0u);
  const GoodixZeroMaskRecoveryAudit *z = goodix_enrollment_fpi_usb_binding_zero_audit (f.binding);
  g_assert_cmpuint (z->recovered_count, ==, 1u);
  g_assert_cmpuint (f.images, ==, stage);
  g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.fpimage_delivery_count, ==, stage);
  g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.protocol.completed_stage_count, ==, stage);
  g_assert_cmpuint (f.audit.auxiliary_b0_count, ==, aux);
  g_assert_cmpmem (commands, sizeof commands, f.commands, sizeof f.commands);
  if (stage == 8u)
    {
      g_assert_true (goodix_enrollment_fpi_usb_binding_is_complete (f.binding));
      g_assert_false (z->stale_window_open);
      g_assert_false (z->awaiting_sample_request);
    }
  else
    {
      g_assert_true (z->stale_window_open);
      g_assert_true (z->awaiting_sample_request);
      request_sample (&f);
      commands[0x32]++;
      g_assert_cmpmem (commands, sizeof commands, f.commands, sizeof f.commands);
      ack (&f, 0x32);
      g_assert_cmpuint (z->rearm32_count, ==, 1u);
      begin_contact (&f, stage + 1u);
      g_assert_false (z->stale_window_open);
      finish_contact (&f, stage + 1u, 0x002f);
      g_assert_cmpuint (f.images, ==, stage + 1u);
      g_assert_cmpuint (z->rearm32_count, ==, 1u);
    }
  fixture_clear (&f);
  fixture_init_config (&f, 0u, TRUE);
  z = goodix_enrollment_fpi_usb_binding_zero_audit (f.binding);
  g_assert_cmpuint (z->recovered_count, ==, 0u);
  g_assert_false (z->stale_window_open);
  fixture_clear (&f);
}

static void
test_recovery_late (gconstpointer data)
{
  guint mode = GPOINTER_TO_UINT (data);
  Fixture f;
  g_autoptr(GBytes) late = irq_frame (0x34, 0x0200, 0, 16u);
  g_autoptr(GError) error = NULL;
  reach_recovery (&f, 2u, 0u);
  accept_irq (&f, 0x36, 0x0100, 0u);
  const GoodixZeroMaskRecoveryAudit *z = goodix_enrollment_fpi_usb_binding_zero_audit (f.binding);
  guint commands[256];
  if (mode != 0u && mode != 4u && mode != 5u)
    request_sample (&f);
  if (mode == 2u)
    goodix_fpi_usb_backend_complete_out (f.backend, 7u, NULL);
  if (mode == 3u || mode == 6u)
    ack (&f, 0x32);
  if (mode == 6u)
    accept_irq (&f, 0x32, 0x0002, 0x002f);
  memcpy (commands, f.commands, sizeof commands);
  if (mode == 5u)
    {
      gsize n; const guint8 *b = g_bytes_get_data (late, &n);
      guint8 *bad = g_memdup2 (b, n); bad[n - 1u] ^= 1u;
      g_clear_pointer (&late, g_bytes_unref); late = g_bytes_new_take (bad, n);
    }
  if (mode == 5u || mode == 6u)
    g_assert_false (goodix_enrollment_fpi_usb_binding_handle_a0 (f.binding, late, &error));
  else
    {
      accept_a0 (&f, late);
      g_assert_true (z->late_seen);
      g_assert_cmpuint (z->late_release_count, ==, 1u);
      if (mode == 4u)
        g_assert_false (goodix_enrollment_fpi_usb_binding_handle_a0 (f.binding, late, &error));
    }
  g_assert_cmpmem (commands, sizeof commands, f.commands, sizeof f.commands);
  g_assert_cmpuint (f.images, ==, 2u);
  g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.protocol.completed_stage_count, ==, 2u);
  g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.protocol.retry_stage_count, ==, 0u);
  if (mode == 4u || mode == 5u || mode == 6u)
    {
      g_assert_nonnull (error);
      g_assert_true (goodix_enrollment_fpi_usb_binding_is_failed (f.binding));
      g_assert_false (z->stale_window_open);
    }
  else
    {
      /* Passive release does not request a sample or change the prepared FDT. */
      if (mode == 0u) request_sample (&f);
      if (mode == 2u)
        { const guint8 b[] = {0x32, 1}; g_autoptr(GBytes) a = frame (0xb0, b, 2); accept_a0 (&f, a); }
      else if (mode != 3u) ack (&f, 0x32);
      begin_contact (&f, 3u);
      g_assert_false (z->stale_window_open);
      finish_contact (&f, 3u, 0x002f);
    }
  fixture_clear (&f);
}

static void
test_recovery_bounds (gconstpointer data)
{
  guint16 word = (guint16) GPOINTER_TO_UINT (data);
  gboolean valid = word >= 2u && word <= 0x01fdu;
  for (guint i = 0; i < 6u; i++)
    {
      Fixture f;
      g_autoptr(GError) error = NULL;
      g_autoptr(GBytes) bytes = zero_mask_raw_frame (i, word);
      reach_recovery (&f, 2u, 0u);
      guint before = f.commands[0x32];
      g_assert_cmpint (goodix_enrollment_fpi_usb_binding_handle_a0 (f.binding, bytes, &error), ==, valid);
      g_assert_cmpuint (f.commands[0x32], ==, before);
      if (valid)
        {
          request_sample (&f);
          /* A0 inner body begins at7: 0801 then twelve candidate bytes. */
          g_assert_cmphex (f.last_out[9u + i*2u], ==, 0x80);
          g_assert_cmphex (f.last_out[10u + i*2u], ==, word >> 1);
        }
      else
        {
          g_assert_nonnull (error);
          g_assert_cmpuint (f.images, ==, 1u);
        }
      fixture_clear (&f);
    }
}

static void
test_recovery_failures (gconstpointer data)
{
  const gchar *kind = data;
  Fixture f;
  g_autoptr(GError) error = NULL;
  reach_recovery (&f, 2u, 0u);
  guint before = f.commands[0x32];
  if (g_str_equal (kind, "quality")) f.fail_stage = 2u;
  if (g_str_equal (kind, "reserved"))
    { g_autoptr(GBytes) b = irq_frame (0x36, 0x0100, 0x40, 16u);
      g_assert_false (goodix_enrollment_fpi_usb_binding_handle_a0 (f.binding, b, &error)); }
  else if (g_str_equal (kind, "quality"))
    { g_autoptr(GBytes) b = irq_frame (0x36, 0x0100, 0, 16u);
      g_assert_false (goodix_enrollment_fpi_usb_binding_handle_a0 (f.binding, b, &error)); }
  else
    {
      accept_irq (&f, 0x36, 0x0100, 0u);
      if (g_str_equal (kind, "out32-error"))
        {
          request_sample (&f);
          before++;
          g_autoptr(GError) failure = g_error_new_literal (G_IO_ERROR, G_IO_ERROR_FAILED, "OUT32 failed");
          goodix_fpi_usb_backend_complete_out (f.backend, 7u, failure);
          g_assert_false (goodix_enrollment_fpi_usb_binding_zero_audit (f.binding)->stale_window_open);
          g_assert_false (goodix_enrollment_fpi_usb_binding_request_zero_sample (f.binding, &error));
        }
      else if (g_str_equal (kind, "aux"))
        { g_autoptr(GBytes) b = primary ();
          g_assert_false (goodix_enrollment_fpi_usb_binding_handle_plaintext_chunk (f.binding, b, &error)); }
      else if (g_str_equal (kind, "early-irq2"))
        { g_autoptr(GBytes) b = irq_frame (0x32, 2, 0x2f, 16u);
          g_assert_false (goodix_enrollment_fpi_usb_binding_handle_a0 (f.binding, b, &error)); }
      else if (g_str_equal (kind, "direct-out"))
        g_assert_false (goodix_enrollment_fpi_usb_binding_submit_next (f.binding, &error));
      else
        {
          goodix_enrollment_fpi_usb_binding_cancel (f.binding, "cancel after zero");
          g_assert_false (goodix_enrollment_fpi_usb_binding_request_zero_sample (f.binding, &error));
        }
    }
  g_assert_nonnull (error);
  g_assert_cmpuint (f.commands[0x32], ==, before);
  g_assert_true (goodix_enrollment_fpi_usb_binding_is_failed (f.binding));
  fixture_clear (&f);
}

static void
test_recovery_contact_bound (void)
{
  Fixture f;
  reach_recovery (&f, 2u, 20u);
  f.reject_from_stage = 2u;
  for (guint stage = 2u; stage <= 20u; stage++)
    {
      g_autoptr(GBytes) zero = irq_frame (0x36, 0x0100, 0, 16u);
      g_autoptr(GError) error = NULL;
      guint before = f.commands[0x32];
      gboolean ok = goodix_enrollment_fpi_usb_binding_handle_a0 (f.binding, zero, &error);
      g_assert_cmpint (ok, ==, stage < 20u);
      g_assert_cmpuint (f.commands[0x32], ==, before);
      g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.protocol.completed_stage_count, ==, 1u);
      if (stage < 20u)
        {
          request_sample (&f);
          ack (&f, 0x32);
          begin_contact (&f, stage + 1u);
        }
      else
        { g_assert_nonnull (strstr (error->message, "bound exhausted")); }
    }
  g_assert_cmpuint (f.images, ==, 20u);
  g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.protocol.retry_stage_count, ==, 18u);
  g_assert_cmpuint (goodix_enrollment_fpi_usb_binding_zero_audit (f.binding)->rearm32_count, ==, 18u);
  fixture_clear (&f);
}

int
main (int argc, char **argv)
{
  const guint stages[] = { 2u, 4u, 7u, 8u };
  const guint flags[] = { 0x0001u, 0x002fu, 0x003fu };
  static const gchar *invalid[] = {
    "control", "irq", "reserved", "body-length", "ack", "checksum", "outer-length"
  };
  g_test_init (&argc, &argv, NULL);
  const guint recovery_stages[] = {2, 4, 7, 8};
  for (guint i = 0; i < G_N_ELEMENTS (recovery_stages); i++)
    { g_autofree gchar *p = g_strdup_printf ("/recovery/stage-%u", recovery_stages[i]);
      g_test_add_data_func (p, GUINT_TO_POINTER (recovery_stages[i]), test_recovery_stage); }
  const gchar *late_names[] = {"before-request", "pending-out32", "before-ack32", "after-ack32", "duplicate", "malformed", "after-irq2"};
  for (guint i = 0; i < G_N_ELEMENTS (late_names); i++)
    { g_autofree gchar *p = g_strdup_printf ("/recovery/late/%s", late_names[i]);
      g_test_add_data_func (p, GUINT_TO_POINTER (i), test_recovery_late); }
  const guint recovery_words[] = {0x0002u, 0x01fdu, 0u, 1u, 0x01feu, 0x01ffu, 0xffffu};
  for (guint i = 0; i < G_N_ELEMENTS (recovery_words); i++)
    { g_autofree gchar *p = g_strdup_printf ("/recovery/raw/%04x", recovery_words[i]);
      g_test_add_data_func (p, GUINT_TO_POINTER (recovery_words[i]), test_recovery_bounds); }
  const gchar *failures[] = {"quality", "reserved", "aux", "early-irq2", "direct-out", "cancel", "out32-error"};
  for (guint i = 0; i < G_N_ELEMENTS (failures); i++)
    { g_autofree gchar *p = g_strdup_printf ("/recovery/fail/%s", failures[i]);
      g_test_add_data_func (p, failures[i], test_recovery_failures); }
  g_test_add_func ("/recovery/contact-limit-20", test_recovery_contact_bound);


  for (guint i = 0; i < G_N_ELEMENTS (stages); i++)
    {
      g_autofree gchar *path = g_strdup_printf ("/enrollment-a0/zero-flags/contact-%u", stages[i]);
      g_test_add_data_func (path, GUINT_TO_POINTER (stages[i]), test_zero_flags);
    }
  for (guint i = 0; i < G_N_ELEMENTS (flags); i++)
    {
      g_autofree gchar *path = g_strdup_printf ("/enrollment-a0/valid-flags/0x%04x", flags[i]);
      g_test_add_data_func (path, GUINT_TO_POINTER (flags[i]), test_valid_flags);
    }
  const guint valid_zero_raw[] = { 0x0002u, 0x01fdu };
  for (guint i = 0; i < G_N_ELEMENTS (valid_zero_raw); i++)
    {
      g_autofree gchar *path = g_strdup_printf (
        "/enrollment-a0/zero-raw-valid-boundary/0x%04x", valid_zero_raw[i]);
      g_test_add_data_func (path, GUINT_TO_POINTER (valid_zero_raw[i]), test_zero_raw_valid_boundary);
    }
  for (guint i = 0; i < 6u; i++)
    {
      g_autofree gchar *path = g_strdup_printf ("/enrollment-a0/zero-raw-invalid/word-%u", i);
      g_test_add_data_func (path, GUINT_TO_POINTER (i), test_zero_raw_invalid);
    }
  g_test_add_func ("/enrollment-a0/cancel-before-zero", test_cancel_before_zero);
  g_test_add_func ("/enrollment-a0/zero-after-terminal", test_zero_after_terminal);
  for (guint i = 0; i < G_N_ELEMENTS (invalid); i++)
    {
      g_autofree gchar *path = g_strdup_printf ("/enrollment-a0/invalid/%s", invalid[i]);
      g_test_add_data_func (path, invalid[i], test_invalid);
    }
  g_test_add_func ("/enrollment-a0/invalid/state", test_wrong_state);
  return g_test_run ();
}
