/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_fdt_irq_policy.h"

gboolean
goodix_fdt_irq_flags_valid (GoodixFdtFlagsContext context,
                            guint16               flags)
{
  switch (context)
    {
    case GOODIX_FDT_FLAGS_BASELINE_SAMPLE:
    case GOODIX_FDT_FLAGS_FINGER_UP:
      return flags == 0u;
    case GOODIX_FDT_FLAGS_FINGER_DOWN:
    case GOODIX_FDT_FLAGS_CONTACT_SAMPLE:
      return flags != 0u && (flags & (guint16) ~GOODIX_FDT_TOUCH_MASK) == 0u;
    }
  return FALSE;
}

gboolean
goodix_fdt_derive_up_table (const guint8 raw[GOODIX_FDT_RAW_LENGTH],
                            guint16       touch_flags,
                            guint8        delta,
                            guint8        table[GOODIX_FDT_RAW_LENGTH])
{
  if (raw == NULL || table == NULL || delta < 2u ||
      !goodix_fdt_irq_flags_valid (GOODIX_FDT_FLAGS_FINGER_DOWN, touch_flags))
    return FALSE;

  for (guint i = 0u; i < GOODIX_FDT_CHANNEL_COUNT; i++)
    {
      guint16 word = (guint16) raw[i * 2u] |
                     ((guint16) raw[i * 2u + 1u] << 8);
      guint value;

      if ((touch_flags & ((guint16) 1u << i)) != 0u)
        value = (guint) (word >> 1) + delta;
      else
        value = (guint) delta - 2u;
      if (value > G_MAXUINT8)
        return FALSE;
      table[i * 2u] = 0x80u;
      table[i * 2u + 1u] = (guint8) value;
    }
  return TRUE;
}

static gboolean
derive_zero_touch_table (const guint8 raw[GOODIX_FDT_RAW_LENGTH],
                         guint8       table[GOODIX_FDT_RAW_LENGTH])
{
  if (raw == NULL || table == NULL)
    return FALSE;

  for (guint i = 0u; i < GOODIX_FDT_CHANNEL_COUNT; i++)
    {
      guint16 word = (guint16) raw[i * 2u] |
                     ((guint16) raw[i * 2u + 1u] << 8);
      guint value = (guint) (word >> 1);

      if (value > G_MAXUINT8)
        return FALSE;
      table[i * 2u] = 0x80u;
      table[i * 2u + 1u] = (guint8) value;
    }
  return TRUE;
}

gboolean
goodix_fdt_derive_baseline_table (const guint8 raw[GOODIX_FDT_RAW_LENGTH],
                                  guint16       touch_flags,
                                  guint8        table[GOODIX_FDT_RAW_LENGTH])
{
  if (raw == NULL || table == NULL ||
      !goodix_fdt_irq_flags_valid (GOODIX_FDT_FLAGS_BASELINE_SAMPLE,
                                   touch_flags))
    return FALSE;
  for (guint i = 0u; i < GOODIX_FDT_CHANNEL_COUNT; i++)
    {
      guint16 word = (guint16) raw[i * 2u] |
                     ((guint16) raw[i * 2u + 1u] << 8);
      guint8 component = (guint8) ((word >> 1) & 0xffu);

      if (component == 0u || component == 0xffu)
        return FALSE;
      table[i * 2u] = 0x80u;
      table[i * 2u + 1u] = component;
    }
  return TRUE;
}

gboolean
goodix_fdt_derive_down_table (const guint8 raw[GOODIX_FDT_RAW_LENGTH],
                              guint16       touch_flags,
                              guint8        table[GOODIX_FDT_RAW_LENGTH])
{
  return goodix_fdt_irq_flags_valid (GOODIX_FDT_FLAGS_FINGER_UP,
                                     touch_flags) &&
         derive_zero_touch_table (raw, table);
}
