/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_lifecycle_adapter.h"

#include <fpi-image.h>
#include <string.h>

typedef struct
{
  guint image_count;
  guint timestamp_count;
  guint16 timestamps[32];
} Fixture;

static gboolean
image_ready (GoodixEnrollmentPipeline *pipeline,
             guint                     stage_index,
             FpImage                  *image,
             gpointer                  user_data,
             GError                  **error)
{
  Fixture *fixture = user_data;

  (void) pipeline;
  (void) error;
  g_assert_cmpuint (stage_index, ==, fixture->image_count + 1u);
  g_assert_true (FP_IS_IMAGE (image));
  fixture->image_count++;
  return TRUE;
}

static gboolean
timestamp_ready (guint                           stage_index,
                 GoodixEnrollmentCommandPurpose purpose,
                 guint16                        *timestamp,
                 gpointer                        user_data,
                 GError                        **error)
{
  Fixture *fixture = user_data;

  (void) stage_index;
  (void) purpose;
  (void) error;
  g_assert_cmpuint (fixture->timestamp_count, <,
                    G_N_ELEMENTS (fixture->timestamps));
  *timestamp = (guint16) (0x2000u + fixture->timestamp_count);
  fixture->timestamps[fixture->timestamp_count++] = *timestamp;
  return TRUE;
}

static void
raw_table (guint seed, guint8 raw[GOODIX_ENROLLMENT_FDT_TABLE_LENGTH])
{
  for (guint i = 0u; i < 6u; i++)
    {
      guint16 word = (guint16) (seed + i * 2u);
      raw[i * 2u] = (guint8) word;
      raw[i * 2u + 1u] = (guint8) (word >> 8);
    }
}

static void
assert_derived_table (const guint8 *table,
                      const guint8 *raw,
                      gboolean      up)
{
  for (guint i = 0u; i < 6u; i++)
    {
      guint16 word = (guint16) raw[i * 2u] |
                     ((guint16) raw[i * 2u + 1u] << 8);
      g_assert_cmphex (table[i * 2u], ==, 0x80);
      g_assert_cmphex (table[i * 2u + 1u], ==,
                       (word >> 1) + (up ? 0x1du : 0u));
    }
}

static void
observe_empty (GoodixEnrollmentLifecycleAdapter *adapter,
               GoodixEnrollmentEvent             event)
{
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_enrollment_lifecycle_adapter_observe (
    adapter, event, NULL, 0u, NULL, 0u, 0u, &error));
  g_assert_no_error (error);
}

static void
observe_fdt (GoodixEnrollmentLifecycleAdapter *adapter,
             GoodixEnrollmentEvent             event,
             const guint8                     *raw)
{
  g_autoptr(GError) error = NULL;

  g_assert_true (goodix_enrollment_lifecycle_adapter_observe (
    adapter, event, NULL, 0u, raw, GOODIX_ENROLLMENT_FDT_TABLE_LENGTH,
    event == GOODIX_ENROLLMENT_EVENT_IRQ2 ? 0x003fu : 0x0000u, &error));
  g_assert_no_error (error);
}

static void
observe_primary (GoodixEnrollmentLifecycleAdapter *adapter,
                 guint                             stage)
{
  uint16_t samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];
  g_autoptr(GError) error = NULL;

  for (gsize i = 0u; i < G_N_ELEMENTS (samples); i++)
    samples[i] = (uint16_t) ((i + stage * 71u) & GOODIX_SENSOR_SAMPLE_MAX);
  g_assert_true (goodix_enrollment_lifecycle_adapter_observe (
    adapter, GOODIX_ENROLLMENT_EVENT_PRIMARY_B0, samples,
    G_N_ELEMENTS (samples), NULL, 0u, 0u, &error));
  g_assert_no_error (error);
}

static void
prepare_commit (GoodixEnrollmentLifecycleAdapter *adapter,
                Fixture                          *fixture,
                GoodixEnrollmentEvent             event,
                guint                             stage,
                const guint8                     *expected_raw,
                gboolean                          expected_up)
{
  GoodixEnrollmentPreparedCommand first = { 0 };
  GoodixEnrollmentPreparedCommand second = { 0 };
  guint timestamps_before = fixture->timestamp_count;
  g_autoptr(GError) error = NULL;

  if (!goodix_enrollment_lifecycle_adapter_prepare (adapter, &first, &error))
    g_error ("prepare failed for event %s stage %u: %s",
             goodix_enrollment_event_name (event), stage,
             error != NULL ? error->message : "no error");
  g_assert_no_error (error);
  g_assert_cmpint (first.intent.event, ==, event);
  g_assert_cmpuint (first.intent.stage_index, ==, stage);
  g_assert_false (first.intent.wire_frame_serializable);
  g_assert_true (goodix_enrollment_lifecycle_adapter_prepare (
    adapter, &second, &error));
  g_assert_no_error (error);
  g_assert_cmpint (memcmp (&first, &second, sizeof first), ==, 0);

  if (event == GOODIX_ENROLLMENT_EVENT_COMMAND_20 ||
      event == GOODIX_ENROLLMENT_EVENT_COMMAND_22 ||
      event == GOODIX_ENROLLMENT_EVENT_COMMAND_50)
    {
      g_assert_cmpuint (first.body.length, ==, 2u);
      g_assert_cmphex (first.body.bytes[0], ==, 0x01);
      g_assert_cmphex (first.body.bytes[1], ==, 0x00);
      g_assert_cmpuint (fixture->timestamp_count, ==, timestamps_before);
    }
  else
    {
      g_assert_nonnull (expected_raw);
      g_assert_cmphex (first.body.bytes[0], ==,
                       event == GOODIX_ENROLLMENT_EVENT_COMMAND_34 ? 0x0a :
                       (event == GOODIX_ENROLLMENT_EVENT_COMMAND_36 ? 0x09 :
                                                                        0x08));
      g_assert_cmphex (first.body.bytes[1], ==, 0x01);
      assert_derived_table (first.body.bytes + 2u, expected_raw, expected_up);
      if (event == GOODIX_ENROLLMENT_EVENT_COMMAND_32)
        {
          guint16 body_timestamp = (guint16) (
            (guint16) first.body.bytes[14] |
            ((guint16) first.body.bytes[15] << 8));
          g_assert_cmpuint (first.body.length, ==, 16u);
          g_assert_cmpuint (fixture->timestamp_count, ==,
                            timestamps_before + 1u);
          g_assert_cmphex (body_timestamp, ==,
                           fixture->timestamps[timestamps_before]);
        }
      else
        {
          g_assert_cmpuint (first.body.length, ==, 14u);
          g_assert_cmpuint (fixture->timestamp_count, ==,
                            timestamps_before);
        }
    }
  g_assert_true (goodix_enrollment_lifecycle_adapter_commit (
    adapter, event, &error));
  g_assert_no_error (error);
  goodix_enrollment_prepared_command_clear (&first);
  goodix_enrollment_prepared_command_clear (&second);
}

static void
run_profile (guint stages)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = stages,
    .defer_terminal_stage_delivery = TRUE,
  };
  GoodixEnrollmentLifecycleAdapterAudit audit;
  Fixture fixture = { 0 };
  guint8 irq2[21][GOODIX_ENROLLMENT_FDT_TABLE_LENGTH];
  guint8 irq0200[21][GOODIX_ENROLLMENT_FDT_TABLE_LENGTH];
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentLifecycleAdapter *adapter =
    goodix_enrollment_lifecycle_adapter_new (
      &config, image_ready, timestamp_ready, &fixture, &audit, &error);

  g_assert_nonnull (adapter);
  g_assert_no_error (error);
  g_assert_cmpuint (stages, <=, G_N_ELEMENTS (irq2));
  for (guint stage = 1u; stage <= stages; stage++)
    {
      raw_table (0x80u + stage * 8u, irq2[stage - 1u]);
      raw_table (0x40u + stage * 8u, irq0200[stage - 1u]);
      observe_fdt (adapter, GOODIX_ENROLLMENT_EVENT_IRQ2,
                   irq2[stage - 1u]);
      prepare_commit (adapter, &fixture, GOODIX_ENROLLMENT_EVENT_COMMAND_22,
                      stage, NULL, FALSE);
      observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_ACK_22);
      observe_primary (adapter, stage);

      prepare_commit (adapter, &fixture, GOODIX_ENROLLMENT_EVENT_COMMAND_34,
                      stage, irq2[stage - 1u], TRUE);
      observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_ACK_34);
      if (stage == 1u)
        {
          observe_fdt (adapter, GOODIX_ENROLLMENT_EVENT_IRQ0200,
                       irq0200[stage - 1u]);
          prepare_commit (adapter, &fixture,
                          GOODIX_ENROLLMENT_EVENT_COMMAND_20, stage,
                          NULL, FALSE);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_ACK_20);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0);
          prepare_commit (adapter, &fixture,
                          GOODIX_ENROLLMENT_EVENT_COMMAND_32, stage,
                          irq0200[stage - 1u], FALSE);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_ACK_32);
          prepare_commit (adapter, &fixture,
                          GOODIX_ENROLLMENT_EVENT_COMMAND_50, stage,
                          NULL, FALSE);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_ACK_50);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_NAV);
          prepare_commit (adapter, &fixture,
                          GOODIX_ENROLLMENT_EVENT_COMMAND_32, stage,
                          irq0200[stage - 1u], FALSE);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_ACK_32);
          g_assert_cmphex (fixture.timestamps[0], !=, fixture.timestamps[1]);
        }
      else
        {
          prepare_commit (adapter, &fixture,
                          GOODIX_ENROLLMENT_EVENT_COMMAND_36, stage,
                          irq0200[stage - 2u], FALSE);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_ACK_36);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_IRQ0100);
          prepare_commit (adapter, &fixture,
                          GOODIX_ENROLLMENT_EVENT_COMMAND_20, stage,
                          NULL, FALSE);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_ACK_20);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0);
          prepare_commit (adapter, &fixture,
                          GOODIX_ENROLLMENT_EVENT_COMMAND_34, stage,
                          irq2[stage - 1u], TRUE);
          observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_ACK_34);
          observe_fdt (adapter, GOODIX_ENROLLMENT_EVENT_IRQ0200,
                       irq0200[stage - 1u]);
          if (stage < stages)
            {
              prepare_commit (adapter, &fixture,
                              GOODIX_ENROLLMENT_EVENT_COMMAND_32, stage,
                              irq0200[stage - 1u], FALSE);
              observe_empty (adapter, GOODIX_ENROLLMENT_EVENT_ACK_32);
            }
        }
    }

  g_assert_true (goodix_enrollment_lifecycle_adapter_is_complete (adapter));
  g_assert_false (goodix_enrollment_lifecycle_adapter_is_failed (adapter));
  g_assert_cmpuint (fixture.image_count, ==, stages);
  g_assert_cmpuint (fixture.timestamp_count, ==, stages);
  g_assert_cmpuint (audit.prepared_command_count, ==, 6u * stages - 1u);
  g_assert_cmpuint (audit.committed_prepared_command_count, ==,
                    audit.prepared_command_count);
  g_assert_cmpuint (audit.prepared_cache_hit_count, ==,
                    audit.prepared_command_count);
  g_assert_cmpuint (audit.timestamp_request_count, ==, stages);
  g_assert_cmpuint (audit.fdt.irq2_up_derivation_count, ==, stages);
  g_assert_cmpuint (audit.fdt.irq0200_down_derivation_count, ==, stages);
  g_assert_cmpuint (audit.fdt.stage_up_resolution_count, ==,
                    2u * stages - 1u);
  g_assert_cmpuint (audit.fdt.previous_down_resolution_count, ==,
                    stages - 1u);
  g_assert_cmpuint (audit.fdt.current_down_resolution_count, ==, stages);
  g_assert_cmpuint (audit.body.body_build_count, ==, 6u * stages - 1u);
  g_assert_cmpuint (audit.retry_count, ==, 0u);
  g_assert_cmpuint (audit.a0_frame_build_count, ==, 0u);
  g_assert_cmpuint (audit.submit_count, ==, 0u);
  goodix_enrollment_lifecycle_adapter_free (adapter);
}

static GoodixEnrollmentLifecycleAdapter *
new_two_stage_adapter (Fixture                               *fixture,
                       GoodixEnrollmentLifecycleAdapterAudit *audit)
{
  GoodixEnrollmentModelConfig config = {
    .required_stage_count = 2u,
    .defer_terminal_stage_delivery = TRUE,
  };
  g_autoptr(GError) error = NULL;
  GoodixEnrollmentLifecycleAdapter *adapter =
    goodix_enrollment_lifecycle_adapter_new (
      &config, image_ready, timestamp_ready, fixture, audit, &error);

  g_assert_nonnull (adapter);
  g_assert_no_error (error);
  return adapter;
}

static void
test_configurable_profiles (void)
{
  run_profile (2u);
  run_profile (3u);
  run_profile (21u);
}

static void
test_observe_with_pending_command_fails_closed (void)
{
  Fixture fixture = { 0 };
  GoodixEnrollmentLifecycleAdapterAudit audit;
  GoodixEnrollmentLifecycleAdapter *adapter =
    new_two_stage_adapter (&fixture, &audit);
  GoodixEnrollmentPreparedCommand prepared = { 0 };
  guint8 irq2[GOODIX_ENROLLMENT_FDT_TABLE_LENGTH];
  g_autoptr(GError) error = NULL;

  raw_table (0x88u, irq2);
  observe_fdt (adapter, GOODIX_ENROLLMENT_EVENT_IRQ2, irq2);
  g_assert_true (goodix_enrollment_lifecycle_adapter_prepare (
    adapter, &prepared, &error));
  g_assert_false (goodix_enrollment_lifecycle_adapter_observe (
    adapter, GOODIX_ENROLLMENT_EVENT_ACK_22, NULL, 0u, NULL, 0u, 0u, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_lifecycle_adapter_is_failed (adapter));
  g_assert_cmpuint (audit.plan.committed_command_count, ==, 0u);
  g_assert_cmpuint (audit.submit_count, ==, 0u);
  goodix_enrollment_prepared_command_clear (&prepared);
  goodix_enrollment_lifecycle_adapter_free (adapter);
}

static void
test_wrong_commit_fails_closed (void)
{
  Fixture fixture = { 0 };
  GoodixEnrollmentLifecycleAdapterAudit audit;
  GoodixEnrollmentLifecycleAdapter *adapter =
    new_two_stage_adapter (&fixture, &audit);
  GoodixEnrollmentPreparedCommand prepared = { 0 };
  guint8 irq2[GOODIX_ENROLLMENT_FDT_TABLE_LENGTH];
  g_autoptr(GError) error = NULL;

  raw_table (0x88u, irq2);
  observe_fdt (adapter, GOODIX_ENROLLMENT_EVENT_IRQ2, irq2);
  g_assert_true (goodix_enrollment_lifecycle_adapter_prepare (
    adapter, &prepared, &error));
  g_assert_false (goodix_enrollment_lifecycle_adapter_commit (
    adapter, GOODIX_ENROLLMENT_EVENT_COMMAND_34, &error));
  g_assert_nonnull (error);
  g_assert_true (goodix_enrollment_lifecycle_adapter_is_failed (adapter));
  g_assert_cmpuint (audit.plan.committed_command_count, ==, 0u);
  g_assert_cmpuint (audit.submit_count, ==, 0u);
  goodix_enrollment_prepared_command_clear (&prepared);
  goodix_enrollment_lifecycle_adapter_free (adapter);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d279-13-lifecycle-adapter/configurable-profiles",
                   test_configurable_profiles);
  g_test_add_func ("/d279-13-lifecycle-adapter/pending-observe-fails-closed",
                   test_observe_with_pending_command_fails_closed);
  g_test_add_func ("/d279-13-lifecycle-adapter/wrong-commit-fails-closed",
                   test_wrong_commit_fails_closed);
  return g_test_run ();
}
