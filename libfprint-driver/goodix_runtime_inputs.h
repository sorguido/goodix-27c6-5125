/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_RUNTIME_INPUTS_H
#define GOODIX_RUNTIME_INPUTS_H

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_RUNTIME_PRODUCER_SEED_LENGTH 6u
#define GOODIX_RUNTIME_FDT_SEED_LENGTH 12u

typedef struct
{
  guint8 expected_sha256[32];
  guint32 first_seed_rva;
  guint32 second_instruction_rva;
} GoodixRuntimePePolicy;

typedef struct
{
  guint8 expected_sha256[32];
  guint8 expected_otp_sha256[32];
  gsize cache_length;
  gsize crc_offset;
  gsize otp_length;
  gsize fdt_offset;
} GoodixRuntimeFdtPolicy;

void goodix_runtime_pe_policy_production (GoodixRuntimePePolicy *policy);
void goodix_runtime_fdt_policy_production (GoodixRuntimeFdtPolicy *policy);

/* Both providers operate only on caller-owned inert bytes.  They do not open,
 * load, execute, map, discover or write any file or device. */
gboolean goodix_runtime_extract_producer_seeds (
  const guint8                *pe_bytes,
  gsize                        pe_length,
  const GoodixRuntimePePolicy *policy,
  guint8                       seed_a[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH],
  guint8                       seed_b[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH],
  GError                     **error);

gboolean goodix_runtime_extract_fdt_seed (
  const guint8                 *cache_bytes,
  gsize                         cache_length,
  const GoodixRuntimeFdtPolicy *policy,
  guint8                        fdt_seed[GOODIX_RUNTIME_FDT_SEED_LENGTH],
  GError                      **error);

const gchar *goodix_runtime_inputs_error_class (const GError *error);
void goodix_runtime_cleanse_producer_seed (
  guint8 seed[GOODIX_RUNTIME_PRODUCER_SEED_LENGTH]);

G_END_DECLS

#endif
