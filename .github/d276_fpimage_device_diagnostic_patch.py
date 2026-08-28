from pathlib import Path

# D276/02 host-only diagnostic patch.
# This script intentionally mutates only the ephemeral GitHub Actions worktree.
# It is removed once the causally validated fixes are promoted into the branch.

p = Path('libfprint-driver/goodix_fpimage_device.c')
s = p.read_text()

old_fence = '''static void
goodix_device_context_set_terminal_fence (GoodixDeviceContext *ctx)
{
  ctx->terminal_fence = TRUE;
  if (ctx->activation_cancellable != NULL)
    g_cancellable_cancel (ctx->activation_cancellable);
}
'''
new_fence = '''static void
goodix_device_context_set_terminal_fence (GoodixDeviceContext *ctx)
{
  ctx->terminal_fence = TRUE;
}
'''
if s.count(old_fence) != 1:
    raise SystemExit('FAIL_CLOSED: terminal-fence block count mismatch')
s = s.replace(old_fence, new_fence, 1)

old_handler = '''static void
on_activation_cancellable_cancelled (GCancellable *cancellable,
                                     gpointer      user_data)
{
  GoodixDeviceContext *ctx = user_data;
  g_autoptr(GError) error = NULL;

  if (ctx->state != GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING ||
      ctx->activation_completed)
    return;

  /* We are executing this handler; disconnecting it here may wait for the
   * current invocation.  Mark it consumed and let cancellable teardown own
   * the connection. */
  ctx->cancel_handler_id = 0;
  goodix_device_context_set_terminal_fence (ctx);
  ctx->generation = 0;

  if (g_cancellable_set_error_if_cancelled (cancellable, &error))
    {
      goodix_device_context_set_state (ctx,
                                       GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
      ctx->activation_completed = TRUE;
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (ctx->device),
                                          g_steal_pointer (&error));
    }
}
'''
new_handler = '''static gboolean
complete_activation_cancel_idle (gpointer user_data)
{
  GoodixFpImageDevice *self = GOODIX_FPIMAGE_DEVICE (user_data);
  GoodixDeviceContext *ctx = self->ctx;
  g_autoptr(GError) error = NULL;

  if (ctx == NULL ||
      ctx->state != GOODIX_DEVICE_CONTEXT_STATE_INACTIVE ||
      !ctx->activation_completed ||
      ctx->activation_cancellable == NULL)
    return G_SOURCE_REMOVE;

  if (g_cancellable_set_error_if_cancelled (ctx->activation_cancellable,
                                             &error))
    fpi_image_device_activate_complete (FP_IMAGE_DEVICE (self),
                                        g_steal_pointer (&error));

  return G_SOURCE_REMOVE;
}

static void
on_activation_cancellable_cancelled (GCancellable *cancellable,
                                     gpointer      user_data)
{
  GoodixDeviceContext *ctx = user_data;

  (void) cancellable;

  if (ctx->state != GOODIX_DEVICE_CONTEXT_STATE_ACTIVATING ||
      ctx->activation_completed)
    return;

  /* Do not complete the libfprint action from inside the cancellable
   * dispatch.  clear_device_cancel_action() disconnects both the internal
   * and external cancellables; doing that synchronously here can deadlock
   * against the still-running external cancellation callback. */
  ctx->cancel_handler_id = 0;
  goodix_device_context_set_terminal_fence (ctx);
  ctx->generation = 0;
  goodix_device_context_set_state (ctx,
                                   GOODIX_DEVICE_CONTEXT_STATE_INACTIVE);
  ctx->activation_completed = TRUE;

  g_idle_add_full (G_PRIORITY_DEFAULT,
                   complete_activation_cancel_idle,
                   g_object_ref (ctx->device),
                   g_object_unref);
}
'''
if s.count(old_handler) != 1:
    raise SystemExit('FAIL_CLOSED: activation-cancel handler count mismatch')
s = s.replace(old_handler, new_handler, 1)

old_image = '''  /* fpi_image_device_image_captured() takes its own reference as needed. */
  fpi_image_device_image_captured (FP_IMAGE_DEVICE (ctx->device), image);
'''
new_image = '''  /* Transfer an independent reference to FpImageDevice; the pipeline keeps its own. */
  fpi_image_device_image_captured (FP_IMAGE_DEVICE (ctx->device),
                                   g_object_ref (image));
'''
if s.count(old_image) != 1:
    raise SystemExit('FAIL_CLOSED: image handoff block count mismatch')
s = s.replace(old_image, new_image, 1)
p.write_text(s)

t = Path('libfprint-driver/tests/test_goodix_fpimage_device.c')
s = t.read_text()

old_enroll = 'fp_device_enroll (FP_DEVICE (f->device), template, cancellable,'
new_enroll = 'fp_device_enroll (FP_DEVICE (f->device), g_steal_pointer (&template), cancellable,'
if s.count(old_enroll) != 2:
    raise SystemExit(f'FAIL_CLOSED: expected 2 floating-template handoffs, found {s.count(old_enroll)}')
s = s.replace(old_enroll, new_enroll)

old_deactivating = '''  goodix_device_context_set_deactivation_held (f->ctx, TRUE);
  g_cancellable_cancel (cancellable);

  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_DEACTIVATING);
'''
new_deactivating = '''  goodix_device_context_set_deactivation_held (f->ctx, TRUE);
  g_cancellable_cancel (cancellable);

  /* libfprint forwards external cancellation through an idle source.
   * Give that source a chance to invoke the driver's deactivate vfunc;
   * deactivation_held keeps the driver in DEACTIVATING until the test
   * explicitly completes it below. */
  while (g_main_context_pending (NULL))
    g_main_context_iteration (NULL, FALSE);

  g_assert_cmpint (goodix_device_context_get_state (f->ctx), ==,
                   GOODIX_DEVICE_CONTEXT_STATE_DEACTIVATING);
'''
if s.count(old_deactivating) != 1:
    raise SystemExit('FAIL_CLOSED: deactivating-test block count mismatch')
s = s.replace(old_deactivating, new_deactivating, 1)

old_stale_capture = '''  old_generation = goodix_device_context_get_generation (f->ctx);
  commands_before = goodix_device_context_get_backend_command_count (f->ctx);

  /* Complete the action, invalidating the generation. */
'''
new_stale_capture = '''  old_generation = goodix_device_context_get_generation (f->ctx);

  /* Complete the action, invalidating the generation. */
'''
if s.count(old_stale_capture) != 1:
    raise SystemExit('FAIL_CLOSED: stale baseline capture block count mismatch')
s = s.replace(old_stale_capture, new_stale_capture, 1)

old_stale_assert = '''  /* An N-1 callback is ignored while generation N remains active. */
  goodix_device_context_emit_finger_down_for_generation (f->ctx,
                                                         old_generation);
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_before + 1 /* second arm */);
'''
new_stale_assert = '''  /* An N-1 callback must cause zero new backend commands. */
  commands_before = goodix_device_context_get_backend_command_count (f->ctx);
  goodix_device_context_emit_finger_down_for_generation (f->ctx,
                                                         old_generation);
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_before);
'''
if s.count(old_stale_assert) != 1:
    raise SystemExit('FAIL_CLOSED: stale callback assertion block count mismatch')
s = s.replace(old_stale_assert, new_stale_assert, 1)

old_terminal_decl = '''  g_autoptr(GError) terminal = NULL;
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
'''
new_terminal_decl = '''  g_autoptr(GError) terminal = NULL;
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  guint commands_after_error;
'''
if s.count(old_terminal_decl) != 1:
    raise SystemExit('FAIL_CLOSED: terminal-error declaration block count mismatch')
s = s.replace(old_terminal_decl, new_terminal_decl, 1)

old_terminal_assert = '''  /* No further commands accepted after the terminal fence. */
  goodix_device_context_emit_finger_up_ready (f->ctx);
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, 1 /* arm */);
'''
new_terminal_assert = '''  /* fpi_image_device_session_error() deactivates the framework session, so
   * the expected teardown is exactly ARM + DISARM, with no REARM. */
  g_assert_cmpuint (goodix_device_context_get_backend_arm_count (f->ctx), ==, 1);
  g_assert_cmpuint (goodix_device_context_get_backend_disarm_count (f->ctx), ==, 1);
  g_assert_cmpuint (goodix_device_context_get_backend_rearm_count (f->ctx), ==, 0);
  commands_after_error = goodix_device_context_get_backend_command_count (f->ctx);

  /* No further commands accepted after the terminal fence. */
  goodix_device_context_emit_finger_up_ready (f->ctx);
  g_assert_cmpuint (goodix_device_context_get_backend_command_count (f->ctx),
                    ==, commands_after_error);
'''
if s.count(old_terminal_assert) != 1:
    raise SystemExit('FAIL_CLOSED: terminal-error assertion block count mismatch')
s = s.replace(old_terminal_assert, new_terminal_assert, 1)

t.write_text(s)
