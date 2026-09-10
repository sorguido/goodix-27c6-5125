/*
 * fprintd example to list enrolled fingerprints
 * Copyright (C) 2008 Daniel Drake <dsd@gentoo.org>
 * Copyright (C) 2020 Marco Trevisan <marco.trevisan@canonical.com>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */

#include <stdio.h>
#include <stdlib.h>
#include <locale.h>
#include "fprintd-dbus.h"

static FprintDBusManager *manager = NULL;
static GDBusConnection *connection = NULL;

static void
create_manager (void)
{
  g_autoptr(GError) error = NULL;

  connection = g_bus_get_sync (G_BUS_TYPE_SYSTEM, NULL, &error);
  if (connection == NULL)
    {
      g_print ("Failed to connect to session bus: %s\n", error->message);
      exit (1);
    }

  manager = fprint_dbus_manager_proxy_new_sync (connection,
                                                G_DBUS_PROXY_FLAGS_NONE,
                                                "net.reactivated.Fprint",
                                                "/net/reactivated/Fprint/Manager",
                                                NULL, &error);
  if (manager == NULL)
    {
      g_print ("Failed to get Fprintd manager: %s\n", error->message);
      exit (1);
    }
}

static void
list_fingerprints (FprintDBusDevice *dev, const char *username)
{
  g_autoptr(GError) error = NULL;
  g_auto(GStrv) fingers = NULL;
  guint i;

  if (!fprint_dbus_device_call_list_enrolled_fingers_sync (dev, username,
                                                           G_DBUS_CALL_FLAGS_ALLOW_INTERACTIVE_AUTHORIZATION,
                                                           -1, &fingers, NULL,
                                                           &error))
    {
      gboolean ignore_error = FALSE;
      if (g_dbus_error_is_remote_error (error))
        {
          g_autofree char *dbus_error =
            g_dbus_error_get_remote_error (error);
          if (g_str_equal (dbus_error,
                           "net.reactivated.Fprint.Error.NoEnrolledPrints"))
            ignore_error = TRUE;
        }

      if (!ignore_error)
        {
          g_print ("ListEnrolledFingers failed: %s\n", error->message);
          exit (1);
        }
    }

  if (fingers == NULL || g_strv_length (fingers) == 0)
    {
      g_print ("User %s has no fingers enrolled for %s.\n", username,
               fprint_dbus_device_get_name (dev));
      return;
    }

  g_print ("Fingerprints for user %s on %s (%s):\n",
           username,
           fprint_dbus_device_get_name (dev),
           fprint_dbus_device_get_scan_type (dev));

  for (i = 0; fingers[i] != NULL; i++)
    g_print (" - #%d: %s\n", i, fingers[i]);
}

static void
process_devices (char **argv)
{
  g_auto(GStrv) devices = NULL;
  g_autoptr(GError) error = NULL;
  char *path;
  guint num_devices;
  guint i;

  if (!fprint_dbus_manager_call_get_devices_sync (manager,
                                                  G_DBUS_CALL_FLAGS_ALLOW_INTERACTIVE_AUTHORIZATION,
                                                  -1,
                                                  &devices, NULL, &error))
    {
      g_print ("Impossible to get devices: %s\n", error->message);
      exit (1);
    }

  num_devices = g_strv_length (devices);
  if (num_devices == 0)
    {
      g_print ("No devices available\n");
      exit (1);
    }

  g_print ("found %u devices\n", num_devices);
  for (i = 0; devices[i] != NULL; i++)
    {
      path = devices[i];
      g_print ("Device at %s\n", path);
    }

  for (i = 0; devices[i] != NULL; i++)
    {
      g_autoptr(FprintDBusDevice) dev = NULL;
      guint j;

      path = devices[i];
      g_print ("Using device %s\n", path);

      /* NOTE: We should handle error cases! */
      dev = fprint_dbus_device_proxy_new_sync (connection,
                                               G_DBUS_PROXY_FLAGS_NONE,
                                               "net.reactivated.Fprint",
                                               path, NULL, NULL);

      for (j = 1; argv[j] != NULL; j++)
        list_fingerprints (dev, argv[j]);
    }
}

int
main (int argc, char **argv)
{
  setlocale (LC_ALL, "");

  create_manager ();

  if (argc < 2)
    {
      g_print ("Usage: %s <username> [usernames...]\n", argv[0]);
      return 1;
    }

  process_devices (argv);

  return 0;
}
