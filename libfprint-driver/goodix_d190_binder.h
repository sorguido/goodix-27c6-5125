/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_D190_BINDER_H
#define GOODIX_D190_BINDER_H
#include <glib.h>
G_BEGIN_DECLS
#define GOODIX_D190_SECRET_LENGTH 32u
#define GOODIX_D190_SEED_LENGTH 6u
#define GOODIX_D190_VALIDATOR_LENGTH 32u
gboolean goodix_d190_bind_validator (const guint8 secret[32],
                                     const guint8 seed_a[6],
                                     const guint8 seed_b[6],
                                     guint8 validator[32], GError **error);
void goodix_d190_clear (gpointer data, gsize length);
G_END_DECLS
#endif
