/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Exercise the real patched fprintd handlers on a private bus. Only libfprint
 * open/close/verify and print loading are synthetic: no FpContext, enumeration,
 * real templates or USB. */
#include <gio/gio.h>
#include <fp-device.h>
#include <fpi-device.h>

static gboolean opened;
static guint opens, closes, prepares, verifies;
static void fake_open (FpDevice *d, GCancellable *c, GAsyncReadyCallback cb, gpointer u)
{
  GTask *t = g_task_new (d, c, cb, u);
  opened = TRUE; opens++;
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
static void fake_verify (FpDevice *d, FpPrint *p, GCancellable *c,
                         FpMatchCb cb, gpointer md, GDestroyNotify destroy,
                         GAsyncReadyCallback done_cb, gpointer u)
{
  GTask *t = g_task_new (d, c, done_cb, u);
  verifies++; cb (d, p, NULL, md, NULL);
  if (destroy) destroy (md);
  g_task_return_boolean (t, TRUE); g_object_unref (t);
}
static gboolean fake_verify_finish (FpDevice *d, GAsyncResult *r, gboolean *match,
                                    FpPrint **print, GError **e)
{
  (void)d; (void)print; *match = TRUE;
  return g_task_propagate_boolean (G_TASK (r), e);
}
#define fp_device_verify fake_verify
#define fp_device_verify_finish fake_verify_finish
#define fp_device_open fake_open
#define fp_device_close fake_close
#define fp_device_open_finish fake_finish
#define fp_device_close_finish fake_finish
#define fp_device_is_open fake_is_open
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

  g_dbus_interface_skeleton_unexport (G_DBUS_INTERFACE_SKELETON (rdev));
  g_object_unref (rdev); g_object_unref (d);
  g_dbus_connection_close_sync (client, NULL, NULL); g_object_unref (client);
  g_dbus_connection_close_sync (server, NULL, NULL); g_object_unref (server);
  g_clear_pointer (&reply, g_variant_unref); g_clear_error (&call_error);
  g_test_dbus_down (bus); g_object_unref (bus);
  g_print ("LOGIN_DAEMON_OFFLINE=PASS opens=4 closes=4 same_claim_open=0 retries=0 suspend_cleanup=1\n");
  return 0;
}
