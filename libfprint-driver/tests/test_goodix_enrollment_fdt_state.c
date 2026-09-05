/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_fdt_state.h"

#include <string.h>

static GoodixEnrollmentCommandIntent
make_intent (guint stage,
             GoodixEnrollmentEvent event,
             GoodixEnrollmentCommandPurpose purpose,
             GoodixEnrollmentBodyClass body_class,
             guint8 control)
{
  return (GoodixEnrollmentCommandIntent) {
    .event = event, .purpose = purpose, .body_class = body_class,
    .stage_index = stage, .control = control,
  };
}

static void
raw_table (guint seed, guint8 raw[12])
{
  for (guint i = 0; i < 6u; i++)
    {
      guint16 word = (guint16) (seed + i * 2u);
      raw[i * 2u] = (guint8) word;
      raw[i * 2u + 1u] = (guint8) (word >> 8);
    }
}

static void
assert_table (const guint8 *table, const guint8 *raw, gboolean up)
{
  for (guint i = 0; i < 6u; i++)
    {
      guint16 word = (guint16) raw[i * 2u] | ((guint16) raw[i * 2u + 1u] << 8);
      g_assert_cmphex (table[i * 2u], ==, 0x80);
      g_assert_cmphex (table[i * 2u + 1u], ==,
                       (word >> 1) + (up ? 0x1du : 0u));
    }
}

static void
test_twenty_one_stage_dynamic_relations (void)
{
  GoodixEnrollmentFdtStateAudit audit;
  GoodixEnrollmentFdtState *state = goodix_enrollment_fdt_state_new (&audit);
  guint8 irq2[21][12];
  guint8 irq200[21][12];
  guint8 previous_down[12] = { 0 };

  for (guint stage = 1u; stage <= 21u; stage++)
    {
      GoodixEnrollmentResolvedMaterial resolved;
      GoodixEnrollmentCommandIntent i34 = make_intent (
        stage, GOODIX_ENROLLMENT_EVENT_COMMAND_34,
        GOODIX_ENROLLMENT_COMMAND_PURPOSE_FINGER_UP,
        GOODIX_ENROLLMENT_BODY_FDT_0A01, 0x34);
      GoodixEnrollmentCommandIntent i36 = make_intent (
        stage, GOODIX_ENROLLMENT_EVENT_COMMAND_36,
        GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUX_FDT_SCAN,
        GOODIX_ENROLLMENT_BODY_FDT_0901, 0x36);
      GoodixEnrollmentCommandIntent i32 = make_intent (
        stage, GOODIX_ENROLLMENT_EVENT_COMMAND_32,
        GOODIX_ENROLLMENT_COMMAND_PURPOSE_INTER_STAGE_REARM,
        GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801, 0x32);
      g_autoptr(GError) error = NULL;

      raw_table (0x80u + stage * 8u, irq2[stage - 1u]);
      raw_table (0x40u + stage * 8u, irq200[stage - 1u]);
      g_assert_true (goodix_enrollment_fdt_state_observe_irq2 (
        state, stage, irq2[stage - 1u], &error));
      g_assert_true (goodix_enrollment_fdt_state_resolve (
        state, &i34, 0u, FALSE, &resolved, &error));
      assert_table (resolved.material.fdt_table, irq2[stage - 1u], TRUE);
      goodix_enrollment_resolved_material_clear (&resolved);
      if (stage > 1u)
        {
          g_assert_true (goodix_enrollment_fdt_state_resolve (
            state, &i36, 0u, FALSE, &resolved, &error));
          g_assert_true (memcmp (resolved.material.fdt_table, previous_down,
                                 sizeof previous_down) == 0);
          goodix_enrollment_resolved_material_clear (&resolved);
        }
      g_assert_true (goodix_enrollment_fdt_state_observe_irq0200 (
        state, stage, irq200[stage - 1u], &error));
      g_assert_true (goodix_enrollment_fdt_state_resolve (
        state, &i32, (guint16) (0x1200u + stage), TRUE, &resolved, &error));
      assert_table (resolved.material.fdt_table, irq200[stage - 1u], FALSE);
      g_assert_true (resolved.material.has_timestamp);
      memcpy (previous_down, resolved.material.fdt_table, sizeof previous_down);
      goodix_enrollment_resolved_material_clear (&resolved);
      g_assert_no_error (error);
    }
  g_assert_cmpuint (audit.irq2_up_derivation_count, ==, 21u);
  g_assert_cmpuint (audit.irq0200_down_derivation_count, ==, 21u);
  g_assert_cmpuint (audit.stage_up_resolution_count, ==, 21u);
  g_assert_cmpuint (audit.previous_down_resolution_count, ==, 20u);
  g_assert_cmpuint (audit.current_down_resolution_count, ==, 21u);
  g_assert_cmpuint (audit.retry_count, ==, 0u);
  g_assert_cmpuint (audit.submit_count, ==, 0u);
  goodix_enrollment_fdt_state_free (state);
}

static void
test_stale_stage_fails_closed (void)
{
  GoodixEnrollmentFdtStateAudit audit;
  GoodixEnrollmentFdtState *state = goodix_enrollment_fdt_state_new (&audit);
  guint8 raw[12];
  g_autoptr(GError) error = NULL;

  raw_table (0x80u, raw);
  g_assert_true (goodix_enrollment_fdt_state_observe_irq2 (state, 1u, raw, &error));
  g_assert_false (goodix_enrollment_fdt_state_observe_irq2 (state, 1u, raw, &error));
  g_assert_nonnull (error);
  g_assert_cmpuint (audit.rejected_resolution_count, ==, 1u);
  goodix_enrollment_fdt_state_free (state);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d279-12-fdt-state/twenty-one-stage-relations",
                   test_twenty_one_stage_dynamic_relations);
  g_test_add_func ("/d279-12-fdt-state/stale-stage-fails-closed",
                   test_stale_stage_fails_closed);
  return g_test_run ();
}
