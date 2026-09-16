/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_fdt_irq_policy.h"

#include <stdlib.h>
#include <string.h>

static GoodixFdtFlagsContext
context_for (const gchar *phase,
             guint        irq)
{
  if (strstr (phase, "bootstrap") != NULL)
    return GOODIX_FDT_FLAGS_BASELINE_SAMPLE;
  if (irq == 0x0002u)
    return GOODIX_FDT_FLAGS_FINGER_DOWN;
  if (irq == 0x0100u)
    return GOODIX_FDT_FLAGS_CONTACT_SAMPLE;
  if (irq == 0x0200u)
    return GOODIX_FDT_FLAGS_FINGER_UP;
  g_error ("unexpected corpus IRQ 0x%04x", irq);
}

static void
test_corpus (gconstpointer user_data)
{
  const gchar *path = user_data;
  g_autofree gchar *contents = NULL;
  g_auto(GStrv) lines = NULL;
  gsize length = 0u;
  guint accepted = 0u;
  gboolean saw_live_002f = FALSE;

  g_assert_true (g_file_get_contents (path, &contents, &length, NULL));
  g_assert_cmpuint (length, >, 0u);
  lines = g_strsplit (contents, "\n", -1);
  g_assert_cmpstr (lines[0], ==, "source\tphase\tcontrol\tirq\tflags");
  for (guint i = 1u; lines[i] != NULL && lines[i][0] != '\0'; i++)
    {
      g_auto(GStrv) fields = g_strsplit (lines[i], "\t", 5);
      guint control;
      guint irq;
      guint flags;

      g_assert_cmpuint (g_strv_length (fields), ==, 5u);
      control = (guint) g_ascii_strtoull (fields[2], NULL, 0);
      irq = (guint) g_ascii_strtoull (fields[3], NULL, 0);
      flags = (guint) g_ascii_strtoull (fields[4], NULL, 0);
      g_assert_true (control == 0x32u || control == 0x34u || control == 0x36u);
      g_assert_true (goodix_fdt_irq_flags_valid (
        context_for (fields[1], irq), (guint16) flags));
      if (g_str_equal (fields[0], "D279_57_LIVE_4DE9C34") && flags == 0x002fu)
        saw_live_002f = TRUE;
      accepted++;
    }
  g_assert_cmpuint (accepted, ==, 66u);
  g_assert_true (saw_live_002f);
}

static void
test_rejections (void)
{
  const guint16 invalid_touch[] = { 0x0000u, 0x0040u, 0x006fu, 0xffffu };

  for (guint i = 0u; i < G_N_ELEMENTS (invalid_touch); i++)
    {
      g_assert_false (goodix_fdt_irq_flags_valid (
        GOODIX_FDT_FLAGS_FINGER_DOWN, invalid_touch[i]));
      g_assert_false (goodix_fdt_irq_flags_valid (
        GOODIX_FDT_FLAGS_CONTACT_SAMPLE, invalid_touch[i]));
    }
  g_assert_false (goodix_fdt_irq_flags_valid (
    GOODIX_FDT_FLAGS_FINGER_UP, 0x0001u));
  g_assert_false (goodix_fdt_irq_flags_valid (
    GOODIX_FDT_FLAGS_BASELINE_SAMPLE, 0x003fu));
}

static void
test_all_six_bit_subsets_and_zero_touch_tables (void)
{
  guint8 raw[GOODIX_FDT_RAW_LENGTH];
  guint8 table[GOODIX_FDT_RAW_LENGTH];
  const guint8 delta = 0x1du;

  for (guint i = 0u; i < GOODIX_FDT_CHANNEL_COUNT; i++)
    {
      guint16 word = (guint16) (0x0100u + i * 0x10u);

      raw[i * 2u] = (guint8) word;
      raw[i * 2u + 1u] = (guint8) (word >> 8);
    }

  for (guint16 flags = 1u; flags <= GOODIX_FDT_TOUCH_MASK; flags++)
    {
      g_assert_true (goodix_fdt_irq_flags_valid (
        GOODIX_FDT_FLAGS_FINGER_DOWN, flags));
      g_assert_true (goodix_fdt_irq_flags_valid (
        GOODIX_FDT_FLAGS_CONTACT_SAMPLE, flags));
      g_assert_true (goodix_fdt_derive_up_table (raw, flags, delta, table));
      for (guint i = 0u; i < GOODIX_FDT_CHANNEL_COUNT; i++)
        {
          guint16 word = (guint16) ((guint16) raw[i * 2u] |
                                    ((guint16) raw[i * 2u + 1u] << 8));
          guint expected = (flags & ((guint16) 1u << i)) != 0u ?
            (guint) (word >> 1) + delta : (guint) delta - 2u;

          g_assert_cmphex (table[i * 2u], ==, 0x80u);
          g_assert_cmphex (table[i * 2u + 1u], ==, expected);
        }
      g_assert_false (goodix_fdt_irq_flags_valid (
        GOODIX_FDT_FLAGS_FINGER_DOWN, (guint16) (flags | 0x0040u)));
    }

  g_assert_true (goodix_fdt_derive_baseline_table (raw, 0u, table));
  g_assert_true (goodix_fdt_derive_down_table (raw, 0u, table));
  g_assert_false (goodix_fdt_derive_baseline_table (raw, 1u, table));
  g_assert_false (goodix_fdt_derive_down_table (raw, 1u, table));

  /* An inactive up channel is replaced by the OEM fallback before its raw
   * candidate matters.  The same out-of-range raw remains fatal when active. */
  raw[0] = 0xffu;
  raw[1] = 0xffu;
  g_assert_true (goodix_fdt_derive_up_table (raw, 0x0002u, delta, table));
  g_assert_cmphex (table[0], ==, 0x80u);
  g_assert_cmphex (table[1], ==, delta - 2u);
  g_assert_false (goodix_fdt_derive_up_table (raw, 0x0001u, delta, table));

  /* Finger-up retains the prior range-only contract; bootstrap separately
   * retains its historical rejection of zero/0xff components. */
  raw[0] = 0x00u;
  raw[1] = 0x00u;
  g_assert_true (goodix_fdt_derive_down_table (raw, 0u, table));
  g_assert_cmphex (table[1], ==, 0x00u);
  g_assert_false (goodix_fdt_derive_baseline_table (raw, 0u, table));
  raw[0] = 0xfeu;
  raw[1] = 0x01u;
  g_assert_true (goodix_fdt_derive_down_table (raw, 0u, table));
  g_assert_cmphex (table[1], ==, 0xffu);
  raw[0] = 0x00u;
  raw[1] = 0x02u;
  g_assert_false (goodix_fdt_derive_down_table (raw, 0u, table));
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_assert_cmpint (argc, ==, 2);
  g_test_add_data_func ("/d279-59-fdt-irq-policy/authentic-corpus",
                        argv[1], test_corpus);
  g_test_add_func ("/d279-59-fdt-irq-policy/rejections", test_rejections);
  g_test_add_func ("/d279-59-fdt-irq-policy/all-six-bit-subsets",
                   test_all_six_bit_subsets_and_zero_touch_tables);
  return g_test_run ();
}
