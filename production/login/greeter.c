/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Runtime startup barrier, not a test launcher. The bus connection remains
 * alive until the greeter exits. No device access outside fprintd. */
#include <gio/gio.h>
#include <glib-unix.h>
#include <signal.h>

#ifndef GOODIX_GREETER_EXEC
#define GOODIX_GREETER_EXEC "/usr/libexec/plasma-login-greeter"
#endif
static GMainLoop *loop;
static GSubprocess *greeter;
static int result;

static gboolean
terminate (gpointer unused)
{
  (void) unused;
  g_subprocess_send_signal (greeter, SIGTERM);
  return G_SOURCE_CONTINUE;
}

static void
exited (GObject *source, GAsyncResult *res, gpointer unused)
{
  g_autoptr(GError) error = NULL;
  (void) unused;
  result = g_subprocess_wait_finish (G_SUBPROCESS (source), res, &error) &&
           g_subprocess_get_successful (G_SUBPROCESS (source)) ? 0 : 1;
  g_main_loop_quit (loop);
}

int
main (void)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GDBusConnection) bus = g_bus_get_sync (G_BUS_TYPE_SYSTEM, NULL, &error);
  g_autoptr(GVariant) device = NULL;
  g_autoptr(GVariant) reply = NULL;
  gboolean ready = FALSE;
  if (bus)
    device = g_dbus_connection_call_sync (
      bus, "net.reactivated.Fprint", "/net/reactivated/Fprint/Manager",
      "net.reactivated.Fprint.Manager", "GetDefaultDevice", NULL,
      G_VARIANT_TYPE ("(o)"), G_DBUS_CALL_FLAGS_NONE, 2000, NULL, &error);
  if (device)
    {
      const char *path;
      g_variant_get (device, "(&o)", &path);
      reply = g_dbus_connection_call_sync (
        bus, "net.reactivated.Fprint", path, "net.reactivated.Fprint.Device",
        "PrepareLogin", NULL, G_VARIANT_TYPE ("(b)"),
        G_DBUS_CALL_FLAGS_NONE, 12000, NULL, &error);
      if (reply)
        g_variant_get (reply, "(b)", &ready);
    }
  if (!ready && bus)
    {
      /* Abandon any delayed open/prepare. Do not retry on hotplug/restart. */
      g_dbus_connection_close_sync (bus, NULL, NULL);
      g_clear_object (&bus);
    }
  g_message ("GOODIX_GREETER_BARRIER ready=%d password_available=1%s%s", ready,
             error ? " error=" : "", error ? error->message : "");
  g_clear_error (&error);
  /* There is no interactive greeter process before the barrier above. */
  greeter = g_subprocess_new (G_SUBPROCESS_FLAGS_NONE, &error,
                              GOODIX_GREETER_EXEC, NULL);
  if (!greeter)
    {
      g_printerr ("Cannot start Plasma login: %s\n", error->message);
      return 1;
    }
  loop = g_main_loop_new (NULL, FALSE);
  g_unix_signal_add (SIGTERM, terminate, NULL);
  g_unix_signal_add (SIGINT, terminate, NULL);
  g_subprocess_wait_async (greeter, NULL, exited, NULL);
  g_main_loop_run (loop);
  if (bus)
    g_dbus_connection_close_sync (bus, NULL, NULL);
  g_object_unref (greeter);
  g_main_loop_unref (loop);
  return result;
}
