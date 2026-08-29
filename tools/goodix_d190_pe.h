/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GOODIX_D190_PE_H
#define GOODIX_D190_PE_H
#include <glib.h>
gboolean goodix_d190_extract_seeds (const gchar *path, guint8 a[6], guint8 b[6], GError **error);
#endif
