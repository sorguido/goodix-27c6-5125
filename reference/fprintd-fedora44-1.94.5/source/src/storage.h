/*
 * Simple file storage for fprintd
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

#pragma once

typedef int (*storage_print_data_save)(FpPrint *print);
typedef int (*storage_print_data_load)(FpDevice   *dev,
                                       FpFinger    finger,
                                       const char *username,
                                       FpPrint   **print);
typedef int (*storage_print_data_delete)(FpDevice   *dev,
                                         FpFinger    finger,
                                         const char *username);
typedef GSList *(*storage_discover_prints)(FpDevice   *dev,
                                           const char *username);
typedef GSList *(*storage_discover_users)(void);
typedef int (*storage_init)(void);
typedef int (*storage_deinit)(void);

struct storage
{
  storage_init              init;
  storage_deinit            deinit;
  storage_print_data_save   print_data_save;
  storage_print_data_load   print_data_load;
  storage_print_data_delete print_data_delete;
  storage_discover_prints   discover_prints;
  storage_discover_users    discover_users;
};

typedef struct storage fp_storage;

/* The currently setup store */
extern fp_storage store;
