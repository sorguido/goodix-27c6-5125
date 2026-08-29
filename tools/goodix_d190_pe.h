/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GOODIX_D190_PE_H
#define GOODIX_D190_PE_H

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_D190_PE_SEED_LENGTH 6u

typedef struct
{
  guint8 expected_sha256[32];
  guint32 first_seed_rva;
  guint32 second_instruction_rva;
} GoodixD190PePolicy;

void goodix_d190_pe_policy_production (GoodixD190PePolicy *policy);

/* The DLL is read strictly as inert bytes.  It is never loaded or executed. */
gboolean goodix_d190_pe_extract (
  const gchar *path,
  guint8       seed_a[GOODIX_D190_PE_SEED_LENGTH],
  guint8       seed_b[GOODIX_D190_PE_SEED_LENGTH],
  GError     **error);

/* Explicit test seam: production callers use goodix_d190_pe_extract(). */
gboolean goodix_d190_pe_extract_bytes_with_policy (
  const guint8                 *data,
  gsize                         length,
  const GoodixD190PePolicy     *policy,
  guint8                        seed_a[GOODIX_D190_PE_SEED_LENGTH],
  guint8                        seed_b[GOODIX_D190_PE_SEED_LENGTH],
  GError                      **error);

void goodix_d190_pe_cleanse_seed (guint8 seed[GOODIX_D190_PE_SEED_LENGTH]);

G_END_DECLS

#endif
