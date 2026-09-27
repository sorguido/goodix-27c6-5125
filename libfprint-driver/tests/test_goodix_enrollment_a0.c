/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Synthetic enrollment protocol regression. No device or biometric fixtures. */
#include "goodix_enrollment_fpi_usb_binding.h"

#include <fpi-image.h>
#include <string.h>

typedef struct
{
  GoodixEnrollmentPostTlsEvents *events; /* Owned by binding. */
  GoodixEnrollmentFpiUsbBinding *binding;
  GoodixFpiUsbBackend *backend;
  GCancellable *cancellable;
  GoodixEnrollmentPostTlsEventsAudit audit;
  GoodixEnrollmentFpiUsbBindingAudit binding_audit;
  guint images;
  guint commands[256];
  guint8 last_control;
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
}

static void
fixture_init (Fixture *f)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 8u,
    .defer_terminal_stage_delivery_until_release_ready = TRUE,
    .defer_intermediate_stage_delivery_until_release_ready = TRUE,
  };
  g_autoptr(GError) error = NULL;
  *f = (Fixture) { 0 };
  f->cancellable = g_cancellable_new ();
  f->backend = goodix_fpi_usb_backend_new (NULL, NULL, 0x81, 0x01, 8192u);
  g_assert_true (goodix_fpi_usb_backend_begin_generation (
    f->backend, 7u, f->cancellable, &error));
  goodix_fpi_usb_backend_set_async_submit_seam (f->backend, submit_seam, f);
  f->events = goodix_enrollment_post_tls_events_new (
    &config, image_ready, timestamp_ready, auxiliary_ready, f, &f->audit, &error);
  f->binding = goodix_enrollment_fpi_usb_binding_new (
    f->events, f->backend, 7u, &f->binding_audit, &error);
  g_assert_no_error (error);
  g_assert_nonnull (f->binding);
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
reject_without_progress (Fixture *f, GBytes *bytes, const gchar *reason)
{
  g_autoptr(GError) error = NULL;
  guint commands[256];
  guint images = f->images;
  memcpy (commands, f->commands, sizeof commands);
  g_assert_false (goodix_enrollment_fpi_usb_binding_handle_a0 (f->binding, bytes, &error));
  g_assert_nonnull (error);
  if (reason != NULL)
    g_assert_nonnull (strstr (error->message, reason));
  g_assert_true (goodix_enrollment_fpi_usb_binding_is_failed (f->binding));
  g_assert_cmpuint (f->images, ==, images);
  g_assert_cmpmem (commands, sizeof commands, f->commands, sizeof f->commands);
  g_assert_cmpuint (f->audit.lifecycle.plan.pipeline.protocol.retry_stage_count, ==, 0u);
  g_assert_cmpuint (f->binding_audit.retry_count, ==, 0u);
  /* A second input cannot revive the failed graph or emit a new command. */
  g_clear_error (&error);
  g_assert_false (goodix_enrollment_fpi_usb_binding_handle_a0 (f->binding, bytes, &error));
  g_assert_cmpmem (commands, sizeof commands, f->commands, sizeof f->commands);
  g_assert_cmpuint (f->images, ==, images);
}

static void
test_zero_flags (gconstpointer data)
{
  guint stage = GPOINTER_TO_UINT (data);
  Fixture f;
  g_autoptr(GBytes) bytes = irq_frame (0x36, 0x0100, 0u, 16u);
  g_autofree gchar *detail = g_strdup_printf (
    "reason=flags-zero policy=contact-sample-nonzero-subset-0x003f contacts=%u stages=%u pending_primary=1",
    stage, stage - 1u);
  reach_sample (&f, stage);
  reject_without_progress (&f, bytes, detail);
  g_assert_cmpint (f.audit.last_mismatch_expected_event, ==, GOODIX_ENROLLMENT_EVENT_IRQ0100);
  g_assert_cmphex (f.audit.last_mismatch_observed_control, ==, 0x36);
  g_assert_cmphex (f.audit.last_mismatch_observed_irq, ==, 0x0100);
  g_assert_cmphex (f.audit.last_mismatch_observed_irq_flags, ==, 0u);
  g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.fpimage_construct_count, ==, stage);
  g_assert_cmpuint (f.audit.lifecycle.plan.pipeline.fpimage_delivery_count, ==, stage - 1u);
  g_assert_cmpuint (f.audit.rejected_inbound_count, ==, 1u);
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
    { bytes = irq_frame (0x34, 0x0100, 0x002f, 16u); reason = "reason=control"; }
  else if (g_str_equal (kind, "irq"))
    { bytes = irq_frame (0x36, 0x0200, 0x002f, 16u); reason = "reason=irq"; }
  else if (g_str_equal (kind, "reserved"))
    { bytes = irq_frame (0x36, 0x0100, 0x0040, 16u); reason = "reason=flags-reserved"; }
  else if (g_str_equal (kind, "body-length"))
    { bytes = irq_frame (0x36, 0x0100, 0x002f, 15u); reason = "reason=body-length"; }
  else if (g_str_equal (kind, "ack"))
    {
      const guint8 body[] = { 0x36, 0x01 };
      bytes = frame (0xb0, body, sizeof body);
      reason = "reason=control";
    }
  else
    {
      g_autoptr(GBytes) valid = irq_frame (0x36, 0x0100, 0x002f, 16u);
      gsize length;
      const guint8 *source = g_bytes_get_data (valid, &length);
      guint8 *copy = g_memdup2 (source, length);
      if (g_str_equal (kind, "checksum"))
        { copy[length - 1u] ^= 1u; reason = "checksum mismatch"; }
      else
        { length--; reason = "outer length is inconsistent"; }
      bytes = g_bytes_new_take (copy, length);
    }
  reject_without_progress (&f, bytes, reason);
  fixture_clear (&f);
}

static void
test_wrong_state (void)
{
  Fixture f;
  g_autoptr(GBytes) bytes = irq_frame (0x36, 0x0100, 0x002f, 16u);
  fixture_init (&f);
  reject_without_progress (&f, bytes, "expected IRQ2");
  g_assert_cmpuint (f.images, ==, 0u);
  fixture_clear (&f);
}

#ifdef GOODIX_ENABLE_ZERO_MASK_PROBE
static void
test_probe_entry (gconstpointer data)
{
  const gchar *kind = data;
  Fixture f;
  g_autoptr(GBytes) bytes = NULL;
  g_autoptr(GError) error = NULL;
  gboolean target = g_str_equal (kind, "target");
  if (g_str_equal (kind, "state")) fixture_init (&f);
  else reach_sample (&f, 2u);
  goodix_enrollment_fpi_usb_binding_enable_probe (f.binding);
  bytes = irq_frame (g_str_equal (kind, "control") ? 0x34 : 0x36,
                     g_str_equal (kind, "irq") ? 0x0200 : 0x0100,
                     g_str_equal (kind, "flags") ? 0x40 : 0,
                     g_str_equal (kind, "length") ? 15u : 16u);
  if (g_str_equal (kind, "checksum") || g_str_equal (kind, "raw"))
    {
      gsize n;
      const guint8 *src = g_bytes_get_data (bytes, &n);
      guint8 *copy = g_memdup2 (src, n);
      if (g_str_equal (kind, "checksum")) copy[n - 1u] ^= 1u;
      else
        {
          copy[n - 1u] = (guint8) (copy[n - 1u] + copy[11] + copy[12]);
          copy[11] = copy[12] = 0;
        }
      g_clear_pointer (&bytes, g_bytes_unref);
      bytes = g_bytes_new_take (copy, n);
    }
  if (g_str_equal (kind, "out-pending"))
    {
      guint8 command[64] = { 0 };
      g_autoptr(GBytes) pending = g_bytes_new (command, sizeof command);
      g_assert_true (goodix_fpi_usb_backend_submit_out (f.backend, 7u, pending, &error));
    }
  gboolean accepted = goodix_enrollment_fpi_usb_binding_handle_a0 (f.binding, bytes, &error);
  g_assert_cmpint (accepted, ==, target);
  g_assert_cmpint (goodix_enrollment_fpi_usb_binding_probe_audit (f.binding)->zero_seen, ==, target);
  if (target)
    {
      g_assert_cmpuint (f.images, ==, 1u);
      g_assert_cmpint (goodix_enrollment_post_tls_events_get_expected_event (f.events), ==,
                       GOODIX_ENROLLMENT_EVENT_IRQ0100);
      g_assert_false (goodix_enrollment_fpi_usb_binding_submit_next (f.binding, &error));
      g_clear_error (&error);
      g_assert_false (goodix_enrollment_fpi_usb_binding_handle_plaintext_chunk (f.binding, bytes, &error));
      g_clear_error (&error);
      g_assert_false (goodix_fpi_usb_backend_begin_generation (f.backend, 8u, f.cancellable, &error));
      g_assert_cmpuint (f.images, ==, 1u);
    }
  fixture_clear (&f);
  /* New binding starts disabled and retains the production rejection. */
  reach_sample (&f, 2u);
  g_clear_pointer (&bytes, g_bytes_unref);
  bytes = irq_frame (0x36, 0x0100, 0, 16u);
  reject_without_progress (&f, bytes, "flags-zero");
  fixture_clear (&f);
}
#endif

int
main (int argc, char **argv)
{
  const guint stages[] = { 2u, 4u, 7u, 8u };
  const guint flags[] = { 0x0001u, 0x002fu, 0x003fu };
  static const gchar *invalid[] = {
    "control", "irq", "reserved", "body-length", "ack", "checksum", "outer-length"
  };
  g_test_init (&argc, &argv, NULL);
#ifdef GOODIX_ENABLE_ZERO_MASK_PROBE
  const gchar *entry[] = { "target", "state", "control", "irq", "flags",
                          "length", "checksum", "raw", "out-pending" };
  for (guint i = 0; i < G_N_ELEMENTS (entry); i++)
    {
      g_autofree gchar *path = g_strdup_printf ("/zero-mask-probe/entry/%s", entry[i]);
      g_test_add_data_func (path, entry[i], test_probe_entry);
    }
#endif

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
  for (guint i = 0; i < G_N_ELEMENTS (invalid); i++)
    {
      g_autofree gchar *path = g_strdup_printf ("/enrollment-a0/invalid/%s", invalid[i]);
      g_test_add_data_func (path, invalid[i], test_invalid);
    }
  g_test_add_func ("/enrollment-a0/invalid/state", test_wrong_state);
  return g_test_run ();
}
