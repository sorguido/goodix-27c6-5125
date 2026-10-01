/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_FDT_IRQ_POLICY_H
#define GOODIX_FDT_IRQ_POLICY_H

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_FDT_CHANNEL_COUNT 6u
#define GOODIX_FDT_RAW_LENGTH 12u
#define GOODIX_FDT_TOUCH_MASK 0x003fu

typedef enum
{
  GOODIX_FDT_FLAGS_BASELINE_SAMPLE,
  GOODIX_FDT_FLAGS_BASELINE_FIRST_SAMPLE,
  GOODIX_FDT_FLAGS_FINGER_DOWN,
  GOODIX_FDT_FLAGS_CONTACT_SAMPLE,
  GOODIX_FDT_FLAGS_FINGER_UP,
} GoodixFdtFlagsContext;

/* The hash-gated APP12509 OEM handler interprets one touch bit per FDT
 * channel.  Contact contexts conservatively require at least one of the six
 * known bits; baseline and finger-up require zero.  Reserved high bits always
 * fail closed.  The first baseline sample instead accepts any subset of the
 * six bits: its reference is the host seed, so a zero or stale reference may
 * legitimately leave touch bits set, and those bits alone neither prove nor
 * exclude a finger. */
gboolean goodix_fdt_irq_flags_valid (GoodixFdtFlagsContext context,
                                     guint16               flags);

/* Derive the OEM FDT-up representation.  Active channels use
 * ((raw >> 1) + delta); inactive channels use (delta - 2). */
gboolean goodix_fdt_derive_up_table (const guint8 raw[GOODIX_FDT_RAW_LENGTH],
                                    guint16       touch_flags,
                                    guint8        delta,
                                    guint8        table[GOODIX_FDT_RAW_LENGTH]);

/* Derive the OEM FDT-down/baseline representation. */
gboolean goodix_fdt_derive_baseline_table (
  const guint8 raw[GOODIX_FDT_RAW_LENGTH],
  guint16       touch_flags,
  guint8        table[GOODIX_FDT_RAW_LENGTH]);
/* Same derivation, but the touch mask may be any subset of the six bits. */
gboolean goodix_fdt_derive_first_baseline_table (
  const guint8 raw[GOODIX_FDT_RAW_LENGTH],
  guint16       touch_flags,
  guint8        table[GOODIX_FDT_RAW_LENGTH]);
gboolean goodix_fdt_derive_down_table (
  const guint8 raw[GOODIX_FDT_RAW_LENGTH],
  guint16       touch_flags,
  guint8        table[GOODIX_FDT_RAW_LENGTH]);

G_END_DECLS

#endif
