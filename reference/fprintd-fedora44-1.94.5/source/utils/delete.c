/*
 * fprintd example to delete fingerprints
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

static gboolean
delete_user_prints (FprintDBusDevice *dev,
                    const char       *fingername,
                    GError          **error)
{
  if (fingername)
    return fprint_dbus_device_call_delete_enrolled_finger_sync (dev, fingername,
                                                                G_DBUS_CALL_FLAGS_ALLOW_INTERACTIVE_AUTHORIZATION,
                                                                -1, NULL, error);
  else
    return fprint_dbus_device_call_delete_enrolled_fingers2_sync (dev,
                                                                  G_DBUS_CALL_FLAGS_ALLOW_INTERACTIVE_AUTHORIZATION,
                                                                  -1, NULL, error);
}

static void
delete_fingerprints (FprintDBusDevice *dev,
                     const char       *username,
                     const char       *fingername)
{
  g_autoptr(GError) error = NULL;

  if (!fprint_dbus_device_call_claim_sync (dev, username,
                                           G_DBUS_CALL_FLAGS_ALLOW_INTERACTIVE_AUTHORIZATION,
                                           -1, NULL, &error))
    {
      g_print ("failed to claim device: %s\n", error->message);
      exit (1);
    }

  if (!delete_user_prints (dev, fingername, &error))
    {
      gboolean ignore_error = FALSE;
      if (g_dbus_error_is_remote_error (error))
        {
          g_autofree char *dbus_error =
            g_dbus_error_get_remote_error (error);
          if (g_str_equal (dbus_error,
                           "net.reactivated.Fprint.Error.NoEnrolledPrints"))
            {
              g_print ("No fingerprints to delete on %s\n",
                       fprint_dbus_device_get_name (dev));
              ignore_error = TRUE;
            }
        }
      if (!ignore_error)
        {
          g_print ("Failed to delete fingerprints: %s\n",
                   error->message);
          exit (1);
        }
      else
        {
          g_print ("No fingerprints to delete on %s\n",
                   fprint_dbus_device_get_name (dev));
        }
    }
  else
    {
      if (fingername)
        g_print ("Fingerprint %s of user %s deleted on %s\n",
                 fingername, username,
                 fprint_dbus_device_get_name (dev));
      else
        g_print ("Fingerprints of user %s deleted on %s\n", username,
                 fprint_dbus_device_get_name (dev));
    }
  g_clear_error (&error);

  if (!fprint_dbus_device_call_release_sync (dev,
                                             G_DBUS_CALL_FLAGS_ALLOW_INTERACTIVE_AUTHORIZATION,
                                             -1, NULL, &error))
    {
      g_print ("ReleaseDevice failed: %s\n", error->message);
      exit (1);
    }
}

static void
process_devices (guint argc, char **argv)
{
  g_autoptr(GOptionContext) option_context = NULL;
  g_autoptr(GError) error = NULL;
  g_auto(GStrv) devices = NULL;
  char *fingername = NULL;
  char *path;
  guint num_devices;
  guint i;

  if (!fprint_dbus_manager_call_get_devices_sync (manager,
                                                  G_DBUS_CALL_FLAGS_ALLOW_INTERACTIVE_AUTHORIZATION,
                                                  -1, &devices, NULL, &error))
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


  const GOptionEntry user_options[] = {
    { "finger", 'f',  0, G_OPTION_ARG_STRING, &fingername, "Finger selected to verify (default is automatic)", NULL },
    { NULL }
  };

  option_context = g_option_context_new (NULL);
  g_option_context_add_main_entries (option_context, user_options, NULL);

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
        {
          const char *username = argv[j];
          fingername = NULL;

          if (argc > j + 1 && argv[j + 1][0] == '-')
            {
              g_autoptr(GError) local_error = NULL;
              g_autoptr(GPtrArray) user_args = NULL;

              user_args = g_ptr_array_new_full (3, NULL);
              g_ptr_array_add (user_args, argv[j]);
              g_ptr_array_add (user_args, argv[j + 1]);

              if (argc > j + 2)
                g_ptr_array_add (user_args, argv[j + 2]);

              int new_argc = user_args->len;
              char **new_argv = (char **) user_args->pdata;

              if (!g_option_context_parse (option_context, &new_argc,
                                           &new_argv, &local_error))
                {
                  g_print ("couldn't parse command-line options: %s\n",
                           local_error->message);
                  j += 1;
                  continue;
                }

              j += 2;
            }

          delete_fingerprints (dev, username, fingername);
        }
    }
}

int
main (int argc, char **argv)
{
  g_autoptr(GOptionContext) option_context = NULL;
  g_autoptr(GError) local_error = NULL;

  option_context = g_option_context_new ("Delete fingerprints");

  setlocale (LC_ALL, "");

  g_option_context_set_ignore_unknown_options (option_context, TRUE);
  g_option_context_set_summary (option_context,
                                "<username> [-f finger-name [usernames [-f finger-name  ]...]");

  if (!g_option_context_parse (option_context, &argc, &argv, &local_error))
    {
      g_print ("couldn't parse command-line options: %s\n", local_error->message);
      return EXIT_FAILURE;
    }

  if (argc < 2)
    {
      g_autofree char *usage = NULL;

      usage = g_option_context_get_help (option_context, FALSE, NULL);
      g_print ("%s", usage);
      return EXIT_FAILURE;
    }

  create_manager ();
  process_devices (argc, argv);

  return 0;
}
