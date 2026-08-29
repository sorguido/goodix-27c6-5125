/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_D190_BINDER_H
#define GOODIX_D190_BINDER_H

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_D190_SECRET_LENGTH 32u
#define GOODIX_D190_SEED_LENGTH 6u
#define GOODIX_D190_VALIDATOR_LENGTH 32u

/* Derive the D190 E4 validator from one factory-secret origin and the two
 * producer seeds.  @validator is cleared before validation and on failure.
 * Every project-owned intermediate is explicitly cleansed on every path. */
gboolean goodix_d190_bind_validator (
  const guint8 secret[GOODIX_D190_SECRET_LENGTH],
  gsize        secret_length,
  const guint8 seed_a[GOODIX_D190_SEED_LENGTH],
  gsize        seed_a_length,
  const guint8 seed_b[GOODIX_D190_SEED_LENGTH],
  gsize        seed_b_length,
  guint8       validator[GOODIX_D190_VALIDATOR_LENGTH],
  GError     **error);

G_END_DECLS

#endif
