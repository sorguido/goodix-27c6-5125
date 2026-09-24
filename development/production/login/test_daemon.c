/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Exercise the real patched fprintd handlers on a private bus. Only libfprint
 * open/close/verify and print loading are synthetic: no FpContext, enumeration,
 * real templates or USB. */
#include <gio/gio.h>
#include <fp-device.h>
#include <fpi-device.h>

static gboolean opened, hold_open;
static GTask *pending_open;
static guint opens, closes, prepares, verifies;
static int verify_outcome = 1; /* 1 MATCH, 0 NO MATCH, -1 hard error, -2 retry, -3 cancel */
static gboolean hold_verify;
static GTask *pending_verify;
static void fake_open (FpDevice *d, GCancellable *c, GAsyncReadyCallback cb, gpointer u)
{
  GTask *t = g_task_new (d, c, cb, u);
  opened = TRUE; opens++;
  if (hold_open) { pending_open = t; return; }
  g_task_return_boolean (t, TRUE); g_object_unref (t);
}
static void fake_close (FpDevice *d, GCancellable *c, GAsyncReadyCallback cb, gpointer u)
{
  GTask *t = g_task_new (d, c, cb, u);
  opened = FALSE; closes++;
  g_task_return_boolean (t, TRUE); g_object_unref (t);
}
static gboolean fake_finish (FpDevice *d, GAsyncResult *r, GError **e)
{ (void)d; return g_task_propagate_boolean (G_TASK (r), e); }
static gboolean fake_is_open (FpDevice *d) { (void)d; return opened; }
static gboolean fake_close_sync (FpDevice *d, GCancellable *c, GError **e)
{ (void)d; (void)c; (void)e; opened = FALSE; closes++; return TRUE; }
static void fake_verify (FpDevice *d, FpPrint *p, GCancellable *c,
                         FpMatchCb cb, gpointer md, GDestroyNotify destroy,
                         GAsyncReadyCallback done_cb, gpointer u)
{
  GTask *t = g_task_new (d, c, done_cb, u);
  verifies++;
  if (verify_outcome >= 0) cb (d, verify_outcome == 1 ? p : NULL, NULL, md, NULL);
  if (destroy) destroy (md);
  if (hold_verify) { pending_verify = t; return; }
  if (verify_outcome < 0)
    g_task_return_new_error (t, verify_outcome == -2 ? FP_DEVICE_RETRY :
                               verify_outcome == -3 ? G_IO_ERROR : FP_DEVICE_ERROR,
                               verify_outcome == -3 ? G_IO_ERROR_CANCELLED : 0,
                            "synthetic failure");
  else
    g_task_return_boolean (t, TRUE);
  g_object_unref (t);
}
static gboolean fake_verify_finish (FpDevice *d, GAsyncResult *r, gboolean *match,
                                    FpPrint **print, GError **e)
{
  (void)d; (void)print; *match = verify_outcome == 1;
  return g_task_propagate_boolean (G_TASK (r), e);
}
#define fp_device_verify fake_verify
#define fp_device_verify_finish fake_verify_finish
#define fp_device_open fake_open
#define fp_device_close fake_close
#define fp_device_open_finish fake_finish
#define fp_device_close_finish fake_finish
#define fp_device_is_open fake_is_open
#define fp_device_close_sync fake_close_sync
#include "device.c"
static int synthetic_print (FpDevice *d, FpFinger finger, const char *user, FpPrint **p)
{ (void)user; *p = fp_print_new (d); fp_print_set_finger (*p, finger); return 0; }
fp_storage store = { .print_data_load = synthetic_print };
GQuark fprint_error_quark (void) { return g_quark_from_static_string ("fprint-error"); }

typedef struct { FpDevice parent; } LoginTestDevice;
typedef struct { FpDeviceClass parent; } LoginTestDeviceClass;
G_DEFINE_TYPE (LoginTestDevice, login_test_device, FP_TYPE_DEVICE)
static gboolean prepare (gpointer d) { (void)d; prepares++; return TRUE; }
static void login_test_device_init (LoginTestDevice *d) { (void)d; }
static void login_test_device_class_init (LoginTestDeviceClass *c)
{
  FpDeviceClass *fc = FP_DEVICE_CLASS (c);
  fc->id = "login_offline"; fc->full_name = "Offline login";
  fc->type = FP_DEVICE_TYPE_VIRTUAL; fc->features = FP_DEVICE_FEATURE_VERIFY;
  g_signal_new_class_handler ("goodix-login-prepare", G_TYPE_FROM_CLASS (c),
      G_SIGNAL_RUN_LAST, G_CALLBACK (prepare), NULL, NULL, NULL, G_TYPE_BOOLEAN, 0);
  g_signal_new ("goodix-login-prepared", G_TYPE_FROM_CLASS (c), G_SIGNAL_RUN_LAST,
      0, NULL, NULL, NULL, G_TYPE_NONE, 2, G_TYPE_BOOLEAN, G_TYPE_STRING);
}

static GVariant *reply;
static GError *call_error;
static gboolean done;
static void called (GObject *o, GAsyncResult *r, gpointer u)
{
  (void)u; reply = g_dbus_connection_call_finish (G_DBUS_CONNECTION (o), r, &call_error);
  done = TRUE;
}
static void iterate_until (gboolean *condition)
{
  gint64 deadline = g_get_monotonic_time () + 2000000;
  while (!*condition && g_get_monotonic_time () < deadline)
    { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
  g_assert_true (*condition);
}
static void request (GDBusConnection *client, GDBusConnection *server,
                     const char *method, GVariant *args)
{
  g_clear_pointer (&reply, g_variant_unref); g_clear_error (&call_error); done = FALSE;
  g_dbus_connection_call (client, g_dbus_connection_get_unique_name (server),
    "/net/reactivated/Fprint/Device/0", "net.reactivated.Fprint.Device", method,
    args, NULL, G_DBUS_CALL_FLAGS_NONE, 2000, NULL, called, NULL);
}
/* Authorization is separate from the handler tests: supply the same qdata
 * produced by the normal PolicyKit/user check, without involving the host. */
static gboolean test_auth (GDBusInterfaceSkeleton *i, GDBusMethodInvocation *v, gpointer u)
{
  (void)i; (void)u;
  if (strstr (g_dbus_method_invocation_get_method_name (v), "Claim"))
    g_object_set_qdata_full (G_OBJECT (v), quark_auth_user, g_strdup ("offline"), g_free);
  return TRUE;
}
static GDBusConnection *connection (const char *address)
{
  GError *e = NULL;
  GDBusConnection *c = g_dbus_connection_new_for_address_sync (address,
    G_DBUS_CONNECTION_FLAGS_AUTHENTICATION_CLIENT | G_DBUS_CONNECTION_FLAGS_MESSAGE_BUS_CONNECTION,
    NULL, NULL, &e);
  g_assert_no_error (e); return c;
}
static gboolean suspend_done;
static void suspended (GObject *o, GAsyncResult *res, gpointer data)
{
  GError *error = NULL;
  (void)data;
  fprint_device_suspend_finish (FPRINT_DEVICE (o), res, &error);
  g_assert_no_error (error);
  suspend_done = TRUE;
}
/* Ordinary Claim passes NULL as cancellable: owner-loss drains the open and
 * then closes it. Verify has a cancellable and must receive cancellation. */
static gboolean finish_cancelled (gpointer unused)
{
  (void)unused;
  if (pending_open)
    {
      g_task_return_boolean (pending_open, TRUE);
      g_clear_object (&pending_open);
      return G_SOURCE_REMOVE;
    }
  GTask *task = pending_open ? pending_open : pending_verify;
  if (!task || !g_cancellable_is_cancelled (g_task_get_cancellable (task))) return G_SOURCE_CONTINUE;
  g_task_return_new_error (task, G_IO_ERROR, G_IO_ERROR_CANCELLED, "offline owner disappeared");
  g_clear_object (&pending_open); g_clear_object (&pending_verify);
  return G_SOURCE_REMOVE;
}
int main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  GTestDBus *bus = g_test_dbus_new (G_TEST_DBUS_NONE);
  g_test_dbus_up (bus);
  g_setenv ("DBUS_SYSTEM_BUS_ADDRESS", g_test_dbus_get_bus_address (bus), TRUE);
  GDBusConnection *server = connection (g_test_dbus_get_bus_address (bus));
  GDBusConnection *client = connection (g_test_dbus_get_bus_address (bus));
  FpDevice *d = g_object_new (login_test_device_get_type (), NULL);
  FprintDevice *rdev = fprint_device_new (d);
  FprintDevicePrivate *priv = fprint_device_get_instance_private (rdev);
  g_signal_handlers_disconnect_by_func (rdev, action_authorization_handler, NULL);
  g_signal_connect (rdev, "g-authorize-method", G_CALLBACK (test_auth), NULL);
  GError *e = NULL;
  g_assert_true (g_dbus_interface_skeleton_export (G_DBUS_INTERFACE_SKELETON (rdev), server,
    "/net/reactivated/Fprint/Device/0", &e));
  g_assert_no_error (e);

  /* No preparation: ClaimLogin fails, without opening a device. */
  request (client, server, "ClaimLogin", g_variant_new ("(s)", "offline"));
  iterate_until (&done); g_assert_nonnull (call_error); g_assert_cmpuint (opens, ==, 0);

  request (client, server, "PrepareLogin", NULL);
  gint64 end = g_get_monotonic_time () + 2000000;
  while (!prepares && g_get_monotonic_time () < end)
    { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
  g_assert_cmpuint (prepares, ==, 1); g_assert_false (done); g_assert_false (priv->login_ready);
  g_signal_emit_by_name (d, "goodix-login-prepared", TRUE, "first32 ACK");
  iterate_until (&done); g_assert_no_error (call_error);
  gboolean ready; g_variant_get (reply, "(b)", &ready); g_assert_true (ready);
  g_assert_cmpuint (opens, ==, 1);

  request (client, server, "ClaimLogin", g_variant_new ("(s)", "offline"));
  iterate_until (&done); g_assert_no_error (call_error);
  g_assert_true (priv->login_claim); g_assert_true (priv->login_used);
  g_assert_cmpuint (opens, ==, 1); g_assert_cmpuint (closes, ==, 0);
  g_assert_cmpuint (verifies, ==, 0);
  request (client, server, "EnrollStart", g_variant_new ("(s)", "right-index-finger"));
  iterate_until (&done); g_assert_nonnull (call_error); g_assert_cmpuint (verifies, ==, 0);
  request (client, server, "VerifyStart", g_variant_new ("(s)", "right-index-finger"));
  iterate_until (&done); g_assert_no_error (call_error);
  while (priv->current_cancellable) g_main_context_iteration (NULL, TRUE);
  g_assert_cmpuint (verifies, ==, 1); g_assert_cmpuint (opens, ==, 1);
  g_assert_false (priv->login_ready);
  request (client, server, "VerifyStop", NULL);
  iterate_until (&done); g_assert_no_error (call_error);
  request (client, server, "VerifyStart", g_variant_new ("(s)", "right-index-finger"));
  iterate_until (&done); g_assert_nonnull (call_error);
  g_assert_cmpuint (verifies, ==, 1);
  /* Release following Verify must close exactly the prepared epoch. */
  request (client, server, "Release", NULL);
  iterate_until (&done); g_assert_no_error (call_error);
  g_assert_false (opened); g_assert_cmpuint (closes, ==, 1);
  request (client, server, "ClaimLogin", g_variant_new ("(s)", "offline"));
  iterate_until (&done); g_assert_nonnull (call_error); g_assert_cmpuint (opens, ==, 1);

  /* Ordinary sudo/enroll claim can proceed even during Plasma's 5 s exit tail. */
  request (client, server, "Claim", g_variant_new ("(s)", "offline"));
  iterate_until (&done); g_assert_no_error (call_error);
  g_assert_false (priv->login_claim); g_assert_cmpuint (opens, ==, 2);
  request (client, server, "Release", NULL);
  iterate_until (&done); g_assert_no_error (call_error);

  /* New physical greeter lifetime; expired/early contact must close, not retry. */
  char *old_owner = g_strdup (priv->login_owner);
  _fprint_device_client_vanished (client, old_owner, rdev);
  g_free (old_owner);
  request (client, server, "PrepareLogin", NULL);
  end = g_get_monotonic_time () + 2000000;
  while (prepares != 2 && g_get_monotonic_time () < end)
    { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
  g_assert_cmpuint (prepares, ==, 2);
  g_signal_emit_by_name (d, "goodix-login-prepared", FALSE, "timeout / early contact");
  iterate_until (&done); g_assert_no_error (call_error);
  g_variant_get (reply, "(b)", &ready); g_assert_false (ready);
  while (priv->current_action != ACTION_NONE || opened)
    g_main_context_iteration (NULL, TRUE);
  g_assert_cmpuint (opens, ==, 3); g_assert_cmpuint (closes, ==, 3);
  request (client, server, "ClaimLogin", g_variant_new ("(s)", "offline"));
  iterate_until (&done); g_assert_nonnull (call_error); g_assert_cmpuint (opens, ==, 3);

  old_owner = g_strdup (priv->login_owner);
  _fprint_device_client_vanished (client, old_owner, rdev); g_free (old_owner);
  request (client, server, "PrepareLogin", NULL);
  end = g_get_monotonic_time () + 2000000;
  while (prepares != 3 && g_get_monotonic_time () < end)
    { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
  g_assert_cmpuint (prepares, ==, 3);
  fprint_device_suspend (rdev, suspended, NULL);
  iterate_until (&suspend_done); iterate_until (&done);
  g_assert_no_error (call_error); g_assert_false (opened);
  g_assert_cmpuint (closes, ==, 4); g_assert_cmpuint (opens, ==, 4);
  g_assert_null (priv->login_suspend_task);

  g_assert_true (fp_device_resume_sync (d, NULL, &e)); g_assert_no_error (e);

  /* Suspend races with the asynchronous open: no preparation may start late. */
  old_owner = g_strdup (priv->login_owner);
  _fprint_device_client_vanished (client, old_owner, rdev); g_free (old_owner);
  hold_open = TRUE;
  request (client, server, "PrepareLogin", NULL);
  end = g_get_monotonic_time () + 2000000;
  while (!pending_open && g_get_monotonic_time () < end)
    { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
  g_assert_nonnull (pending_open);
  suspend_done = FALSE;
  fprint_device_suspend (rdev, suspended, NULL);
  g_task_return_boolean (pending_open, TRUE); g_clear_object (&pending_open);
  hold_open = FALSE;
  iterate_until (&suspend_done); iterate_until (&done);
  g_assert_no_error (call_error);
  g_assert_cmpuint (prepares, ==, 3);  /* Never arm after suspend invalidation. */
  g_assert_cmpuint (opens, ==, 5); g_assert_cmpuint (closes, ==, 5);

  g_assert_true (fp_device_resume_sync (d, NULL, &e)); g_assert_no_error (e);

  /* READY owner disappearing closes the session, without reopening it. */
  old_owner = g_strdup (priv->login_owner);
  _fprint_device_client_vanished (client, old_owner, rdev); g_free (old_owner);
  request (client, server, "PrepareLogin", NULL);
  end = g_get_monotonic_time () + 2000000;
  while (prepares != 4 && g_get_monotonic_time () < end)
    { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
  g_assert_cmpuint (prepares, ==, 4);
  g_signal_emit_by_name (d, "goodix-login-prepared", TRUE, "first32 ACK");
  iterate_until (&done); g_assert_no_error (call_error);
  old_owner = g_strdup (priv->login_owner);
  _fprint_device_client_vanished (client, old_owner, rdev); g_free (old_owner);
  end = g_get_monotonic_time () + 2000000;
  while (opened && g_get_monotonic_time () < end)
    { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
  g_assert_false (opened); g_assert_cmpuint (closes, ==, 6);
  g_assert_false (priv->login_ready); g_assert_cmpuint (opens, ==, 6);

  /* Real handlers: each NO MATCH permits only a new explicit VerifyStart.
   * Hold completion to prove early match reporting cannot cancel release. */
  const int cases[][3] = {{0,1,1}, {0,0,1}, {0,0,0}, {-1,1,1},
                          {0,-1,1}, {-2,1,1}, {0,-2,1}, {-3,1,1}, {0,-3,1}};
  for (guint scenario = 0; scenario < G_N_ELEMENTS (cases); scenario++)
    {
      old_owner = g_strdup (priv->login_owner);
      if (old_owner) _fprint_device_client_vanished (client, old_owner, rdev);
      g_free (old_owner);
      guint prior_prepares = prepares, prior_opens = opens, prior_verifies = verifies;
      request (client, server, "PrepareLogin", NULL);
      while (prepares == prior_prepares) g_main_context_iteration (NULL, TRUE);
      g_signal_emit_by_name (d, "goodix-login-prepared", TRUE, "READY");
      iterate_until (&done); g_assert_no_error (call_error);
      request (client, server, "ClaimLogin", g_variant_new ("(s)", "offline"));
      iterate_until (&done); g_assert_no_error (call_error);
      g_assert_cmpuint (priv->login_attempts, ==, 0);
      guint attempted = 0;
      for (guint i = 0; i < 3; i++)
        {
          verify_outcome = cases[scenario][i];
          hold_verify = TRUE;
          request (client, server, "VerifyStart", g_variant_new ("(s)", "right-index-finger"));
          iterate_until (&done); g_assert_no_error (call_error);
          g_assert_nonnull (pending_verify);
          g_autoptr(SessionData) session = session_data_get (priv);
          g_assert_cmpint (session->verify_status_reported, ==, verify_outcome == 1);
          g_assert_false (priv->login_ready);
          hold_verify = FALSE;
          if (verify_outcome < 0)
            {
              if (verify_outcome != -3)
                {
                  g_test_expect_message (NULL, G_LOG_LEVEL_MESSAGE, "GOODIX_LOGIN_RESULT*");
                  g_test_expect_message (NULL, G_LOG_LEVEL_WARNING, "*Device reported an error during verify*");
                }
              g_task_return_new_error (pending_verify,
                verify_outcome == -2 ? FP_DEVICE_RETRY : verify_outcome == -3 ? G_IO_ERROR : FP_DEVICE_ERROR,
                verify_outcome == -3 ? G_IO_ERROR_CANCELLED : 0, "synthetic failure");
            }
          else g_task_return_boolean (pending_verify, TRUE);
          g_clear_object (&pending_verify);
          while (priv->current_cancellable) g_main_context_iteration (NULL, TRUE);
          if (verify_outcome < 0 && verify_outcome != -3) g_test_assert_expected_messages ();
          attempted++;
          g_assert_cmpuint (verifies, ==, prior_verifies + attempted);
          g_assert_cmpuint (priv->login_attempts, ==, attempted);
          g_assert_cmpuint (opens, ==, prior_opens + 1);
          request (client, server, "VerifyStop", NULL);
          iterate_until (&done); g_assert_no_error (call_error);
          if (verify_outcome != 0) break;
        }
      request (client, server, "VerifyStart", g_variant_new ("(s)", "right-index-finger"));
      iterate_until (&done); g_assert_nonnull (call_error);
      g_assert_cmpuint (verifies, ==, prior_verifies + attempted);
      request (client, server, "Release", NULL);
      iterate_until (&done); g_assert_no_error (call_error);
      g_assert_false (opened);
    }
  g_assert_cmpuint (opens, ==, closes);
  g_test_message ("LOGIN_THREE_ATTEMPTS=PASS no_match_then_match=2,3 max=3 hard_error=1,2 no_hidden_restart=1");

  /* Polkit parent cancellation closes the PAM child's connection. Exercise
   * the actual name-owner watcher on ordinary Claim (not ClaimLogin), during
   * pending open, claimed idle, and pending Verify. No real libfprint I/O. */
  for (int phase = 0; phase < 3; phase++)
    {
      guint before_opens = opens, before_verifies = verifies;
      hold_open = phase == 0;
      hold_verify = phase == 2;
      verify_outcome = 0;
      request (client, server, "Claim", g_variant_new ("(s)", "offline"));
      if (hold_open)
        {
          end = g_get_monotonic_time () + 2000000;
          while (!pending_open && g_get_monotonic_time () < end)
            { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
          g_assert_nonnull (pending_open);
        }
      else
        {
          iterate_until (&done); g_assert_no_error (call_error);
          if (hold_verify)
            {
              request (client, server, "VerifyStart", g_variant_new ("(s)", "right-index-finger"));
              iterate_until (&done); g_assert_no_error (call_error);
              g_assert_nonnull (pending_verify);
            }
        }
      if (hold_open || hold_verify) g_idle_add (finish_cancelled, NULL);
      g_dbus_connection_close_sync (client, NULL, NULL);
      end = g_get_monotonic_time () + 2000000;
      while ((opened || priv->_session || !done) && g_get_monotonic_time () < end)
        { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
      g_assert_false (opened); g_assert_null (priv->_session);
      g_assert_null (priv->current_cancellable);
      g_assert_cmpint (priv->current_action, ==, ACTION_NONE);
      g_assert_cmpuint (opens, ==, before_opens + 1);
      g_assert_cmpuint (verifies, ==, before_verifies + (phase == 2));
      g_object_unref (client);
      client = connection (g_test_dbus_get_bus_address (bus));
    }
  g_test_message ("POLKIT_OWNER_LOSS=PASS ordinary_claim_pending_idle_verify no_hidden_reopen=1");

  /* All ordered consumer pairs: sudo/Polkit/KScreenLocker use Claim; login
   * uses PrepareLogin + ClaimLogin. A denied peer cannot stop/steal the owner. */
  const char *consumers[] = {"sudo", "polkit", "kscreenlocker", "login"};
  for (guint owner = 0; owner < 4; owner++)
    for (guint peer = 0; peer < 4; peer++)
      {
        if (owner == peer) continue;
        guint initial_opens = opens, initial_verifies = verifies;
        hold_open = FALSE; hold_verify = TRUE; verify_outcome = 0;
        if (owner == 3)
          {
            guint initial_prepares = prepares;
            request (client, server, "PrepareLogin", NULL);
            while (prepares == initial_prepares) g_main_context_iteration (NULL, TRUE);
            g_signal_emit_by_name (d, "goodix-login-prepared", TRUE, "offline ready");
            iterate_until (&done); g_assert_no_error (call_error);
          }
        request (client, server, owner == 3 ? "ClaimLogin" : "Claim", g_variant_new ("(s)", "offline"));
        iterate_until (&done); g_assert_no_error (call_error);
        request (client, server, "VerifyStart", g_variant_new ("(s)", "right-index-finger"));
        iterate_until (&done); g_assert_no_error (call_error); g_assert_nonnull (pending_verify);
        GDBusConnection *other = connection (g_test_dbus_get_bus_address (bus));
        request (other, server, peer == 3 ? "ClaimLogin" : "Claim", g_variant_new ("(s)", "offline"));
        iterate_until (&done); g_assert_nonnull (call_error);
        request (other, server, "VerifyStop", NULL);
        iterate_until (&done); g_assert_nonnull (call_error);
        g_dbus_connection_close_sync (other, NULL, NULL); g_object_unref (other);
        end = g_get_monotonic_time () + 20000;
        while (g_get_monotonic_time () < end) { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
        g_assert_nonnull (pending_verify);
        g_assert_false (g_cancellable_is_cancelled (g_task_get_cancellable (pending_verify)));
        g_assert_cmpuint (opens, ==, initial_opens + 1);
        g_assert_cmpuint (verifies, ==, initial_verifies + 1);
        g_idle_add (finish_cancelled, NULL);
        g_dbus_connection_close_sync (client, NULL, NULL);
        end = g_get_monotonic_time () + 2000000;
        while ((opened || priv->_session || priv->current_cancellable) && g_get_monotonic_time () < end)
          { g_main_context_iteration (NULL, FALSE); g_usleep (1000); }
        g_assert_false (opened); g_assert_null (priv->_session);
        g_assert_null (priv->current_cancellable); g_assert_cmpint (priv->current_action, ==, ACTION_NONE);
        g_assert_cmpuint (opens, ==, closes);
        g_assert_cmpuint (verifies, ==, initial_verifies + 1);
        g_object_unref (client); client = connection (g_test_dbus_get_bus_address (bus));
        g_test_message ("CROSS_CONSUMER owner=%s blocked=%s busy_no_reopen=1 owner_loss_cleanup=1", consumers[owner], consumers[peer]);
      }
  /* Ordinary consumer retry errors must not trigger another device action. */
  hold_verify = FALSE; verify_outcome = -2;
  guint initial_verifies = verifies;
  request (client, server, "Claim", g_variant_new ("(s)", "offline"));
  iterate_until (&done); g_assert_no_error (call_error);
  g_test_expect_message (NULL, G_LOG_LEVEL_WARNING, "*Device reported an error during verify*");
  request (client, server, "VerifyStart", g_variant_new ("(s)", "right-index-finger"));
  iterate_until (&done); g_assert_no_error (call_error);
  while (priv->current_cancellable) g_main_context_iteration (NULL, TRUE);
  g_test_assert_expected_messages ();
  g_assert_cmpuint (verifies, ==, initial_verifies + 1);
  request (client, server, "Release", NULL); iterate_until (&done); g_assert_no_error (call_error);
  g_assert_cmpuint (opens, ==, closes);
  g_test_message ("ORDINARY_RETRY_ERROR_TERMINAL=PASS additional_action=0");

  g_dbus_interface_skeleton_unexport (G_DBUS_INTERFACE_SKELETON (rdev));
  g_object_unref (rdev); g_object_unref (d);
  g_dbus_connection_close_sync (client, NULL, NULL); g_object_unref (client);
  g_dbus_connection_close_sync (server, NULL, NULL); g_object_unref (server);
  g_clear_pointer (&reply, g_variant_unref); g_clear_error (&call_error);
  g_test_dbus_down (bus); g_object_unref (bus);
  g_print ("LOGIN_DAEMON_OFFLINE=PASS opens=%u closes=%u same_claim_open=0 retries=0 suspend_cleanup=1\n", opens, closes);
  return 0;
}
