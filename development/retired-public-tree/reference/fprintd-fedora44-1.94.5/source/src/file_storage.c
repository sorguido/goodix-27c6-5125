/*
 * Simple file storage for fprintd
 * Copyright (C) 2007 Daniel Drake <dsd@gentoo.org>
 * Copyright (C) 2008 Vasily Khoruzhick <anarsoul@gmail.com>
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
 *
 */


/* FIXME:
 * This file almost duplicate data.c from libfprint
 * Maybe someday data.c will be upgraded to this one ;)
 */

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>

#include <glib.h>
#include <glib/gstdio.h>

#include <fprint.h>

#include "file_storage.h"

#define FILE_STORAGE_PATH "/var/lib/fprint"
#define DIR_PERMS 0700

static char *storage_path = NULL;

static const char *
get_storage_path (void)
{
  const char *path = NULL;

  if (storage_path != NULL)
    return storage_path;

  /* set by systemd >= 240 to an absolute path
   * taking into account the StateDirectory
   * unit file setting */
  path = g_getenv ("STATE_DIRECTORY");
  if (path != NULL)
    {
      /* If multiple directories are set, then in the environment variable
       * the paths are concatenated with colon (":"). */
      if (strchr (path, ':'))
        {
          g_auto(GStrv) elems = NULL;
          elems = g_strsplit (path, ":", -1);
          storage_path = g_strdup (elems[0]);
        }
      else if (*path)
        {
          storage_path = g_strdup (path);
        }
    }

  if (storage_path == NULL)
    storage_path = g_strdup (FILE_STORAGE_PATH);

  return storage_path;
}

static char *
get_path_to_storedir (const char *driver, const char * device_id, char *base_store)
{
  return g_build_filename (base_store, driver, device_id, NULL);
}

static char *
__get_path_to_print (const char *driver, const char * device_id,
                     FpFinger finger, char *base_store)
{
  g_autofree char *dirpath = NULL;
  char *path;
  char fingername[2];

  g_snprintf (fingername, 2, "%x", finger);

  dirpath = get_path_to_storedir (driver, device_id, base_store);
  path = g_build_filename (dirpath, fingername, NULL);
  return path;
}

static char *
get_path_to_print (FpDevice *dev, FpFinger finger, char *base_store)
{
  return __get_path_to_print (fp_device_get_driver (dev),
                              fp_device_get_device_id (dev),
                              finger,
                              base_store);
}

static char *
get_path_to_print_dscv (FpDevice *dev, FpFinger finger, char *base_store)
{
  return __get_path_to_print (fp_device_get_driver (dev),
                              fp_device_get_device_id (dev),
                              finger,
                              base_store);
}

static char *
file_storage_get_basestore_for_username (const char *username)
{
  return g_build_filename (get_storage_path (), username, NULL);
}

int
file_storage_print_data_save (FpPrint *print)
{
  g_autoptr(GError) err = NULL;
  g_autofree char *path = NULL;
  g_autofree char *dirpath = NULL;
  g_autofree char *base_store = NULL;
  g_autofree char *buf = NULL;
  gsize len;
  int r;

  base_store = file_storage_get_basestore_for_username (fp_print_get_username (print));

  if (!fp_print_serialize (print, (guchar **) &buf, &len, &err))
    {
      g_warning ("Error serializing data: %s", err->message);
      return -ENOMEM;
    }

  path = __get_path_to_print (fp_print_get_driver (print),
                              fp_print_get_device_id (print),
                              fp_print_get_finger (print),
                              base_store);
  dirpath = g_path_get_dirname (path);
  r = g_mkdir_with_parents (dirpath, DIR_PERMS);
  if (r < 0)
    {
      g_debug ("file_storage_print_data_save(): could not mkdir(\"%s\"): %s",
               dirpath, g_strerror (r));
      return r;
    }

  g_file_set_contents (path, buf, len, &err);
  if (err)
    {
      g_debug ("file_storage_print_data_save(): could not save '%s': %s",
               path, err->message);
      /* FIXME interpret error codes */
      return err->code;
    }

  g_debug ("file_storage_print_data_save(): print saved to %s", path);

  return 0;
}

static int
load_from_file (char *path, FpPrint **print)
{
  g_autoptr(GError) err = NULL;
  gsize length;
  g_autofree char *contents = NULL;
  FpPrint *new;

  g_file_get_contents (path, &contents, &length, &err);
  if (err)
    {
      int r = err->code;
      /* FIXME interpret more error codes */
      if (r == G_FILE_ERROR_NOENT)
        return -ENOENT;
      else
        return r;
    }

  new = fp_print_deserialize ((guchar *) contents, length, &err);
  if (!new)
    {
      g_print ("Error deserializing data: %s", err->message);
      return -EIO;
    }

  *print = new;
  return 0;
}

int
file_storage_print_data_load (FpDevice   *dev,
                              FpFinger    finger,
                              const char *username,
                              FpPrint   **print)
{
  g_autofree gchar *path = NULL;
  g_autofree gchar *base_store = NULL;

  g_autoptr(FpPrint) new = NULL;
  int r;

  base_store = file_storage_get_basestore_for_username (username);

  path = get_path_to_print (dev, finger, base_store);
  r = load_from_file (path, &new);
  g_debug ("file_storage_print_data_load(): loaded '%s' %s",
           path, g_strerror (r));
  if (r)
    return r;

  /* Make sure the username/finger matches our expectations. */
  if (fp_print_get_finger (new) != finger)
    return -EINVAL;

  if (g_strcmp0 (fp_print_get_username (new), username) != 0)
    return -EINVAL;

  /* And that the print is compatible with the device. */
  if (!fp_print_compatible (new, dev))
    return -EINVAL;

  *print = g_steal_pointer (&new);
  return 0;
}

int
file_storage_print_data_delete (FpDevice *dev, FpFinger finger, const char *username)
{
  g_autoptr(GSList) prints = NULL;
  g_autofree gchar *base_store = NULL;
  g_autofree gchar *path = NULL;
  int r;

  base_store = file_storage_get_basestore_for_username (username);

  path = get_path_to_print_dscv (dev, finger, base_store);

  if (!g_file_test (path, G_FILE_TEST_EXISTS))
    return 0;

  r = g_unlink (path);
  g_debug ("file_storage_print_data_delete(): unlink(\"%s\") %s",
           path, g_strerror (r));

  prints = file_storage_discover_prints (dev, username);
  if (!prints)
    {
      g_autofree char *dir = g_steal_pointer (&path);

      do
        {
          g_autofree char *tmp = g_steal_pointer (&dir);
          dir = g_path_get_dirname (tmp);
        }
      while (g_str_has_prefix (dir, base_store) && g_rmdir (dir) == 0);
    }

  return r;
}

static GSList *
scan_dev_storedir (char   *devpath,
                   GSList *list)
{
  g_autoptr(GError) err = NULL;
  const gchar *ent;

  GDir *dir = g_dir_open (devpath, 0, &err);

  if (!dir)
    {
      g_debug ("scan_dev_storedir(): opendir(\"%s\") failed: %s", devpath, err->message);
      return list;
    }

  while ((ent = g_dir_read_name (dir)))
    {
      /* ent is an 1 hex character fp_finger code */
      guint64 val;
      gchar *endptr;

      if (*ent == 0 || strlen (ent) != 1)
        continue;

      val = g_ascii_strtoull (ent, &endptr, 16);
      if (endptr == ent || !FP_FINGER_IS_VALID (val))
        {
          g_debug ("scan_dev_storedir(): skipping print file '%s'", ent);
          continue;
        }

      list = g_slist_prepend (list, GUINT_TO_POINTER (val));
    }

  g_dir_close (dir);
  return list;
}

GSList *
file_storage_discover_prints (FpDevice *dev, const char *username)
{
  GSList *list = NULL;
  g_autofree gchar *base_store = NULL;
  g_autofree gchar *storedir = NULL;

  base_store = file_storage_get_basestore_for_username (username);

  storedir = get_path_to_storedir (fp_device_get_driver (dev),
                                   fp_device_get_device_id (dev),
                                   base_store);

  g_debug ("file_storage_discover_prints() for user '%s' in '%s'",
           username, storedir);

  list = scan_dev_storedir (storedir, list);

  return list;
}

GSList *
file_storage_discover_users (void)
{
  g_autoptr(GError) err = NULL;
  GSList *list = NULL;
  const gchar *ent;
  GDir *dir = g_dir_open (get_storage_path (), 0, &err);

  if (!dir)
    return list;

  while ((ent = g_dir_read_name (dir)))
    {
      /* ent is a username */
      if (*ent == 0)
        continue;

      list = g_slist_prepend (list, g_strdup (ent));
    }

  g_dir_close (dir);
  return list;
}

int
file_storage_init (void)
{
  /* Nothing to do */
  return 0;
}

int
file_storage_deinit (void)
{
  g_clear_pointer (&storage_path, g_free);
  return 0;
}
