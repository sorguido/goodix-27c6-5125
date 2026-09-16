/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_command_body.h"

#include <string.h>

static GoodixEnrollmentCommandIntent
intent (GoodixEnrollmentEvent          event,
        GoodixEnrollmentCommandPurpose purpose,
        GoodixEnrollmentBodyClass      body_class,
        guint8                         control,
        guint                          stage)
{
  return (GoodixEnrollmentCommandIntent) {
    .event = event,
    .purpose = purpose,
    .body_class = body_class,
    .stage_index = stage,
    .control = control,
    .wire_frame_serializable = FALSE,
  };
}

static GoodixEnrollmentCommandMaterial
material (guint stage,
          GoodixEnrollmentTableRole role,
          gboolean timestamp)
{
  GoodixEnrollmentCommandMaterial value = {
    .stage_index = stage,
    .table_role = role,
    .timestamp = 0x4567,
    .has_fdt_table = TRUE,
    .has_timestamp = timestamp,
  };

  for (guint i = 0; i < GOODIX_ENROLLMENT_FDT_TABLE_LENGTH; i++)
    value.fdt_table[i] = (guint8) (stage * 13u + i);
  return value;
}

static void
assert_build (const GoodixEnrollmentCommandIntent   *command_intent,
              const GoodixEnrollmentCommandMaterial *command_material,
              guint8                                 prefix,
              gsize                                  length,
              GoodixEnrollmentCommandBodyAudit      *audit)
{
  GoodixEnrollmentCommandBody body;
  g_autoptr(GError) error = NULL;

  memset (&body, 0xa5, sizeof body);
  g_assert_true (goodix_enrollment_command_body_build (
    command_intent, command_material, &body, audit, &error));
  g_assert_no_error (error);
  g_assert_cmpuint (body.length, ==, length);
  g_assert_cmphex (body.bytes[0], ==, prefix);
  g_assert_cmphex (body.bytes[1], ==, length == 2u ? 0x00 : 0x01);
  if (command_material != NULL)
    g_assert_true (memcmp (body.bytes + 2, command_material->fdt_table,
                           GOODIX_ENROLLMENT_FDT_TABLE_LENGTH) == 0);
  if (length == 16u)
    {
      g_assert_cmphex (body.bytes[14], ==, 0x67);
      g_assert_cmphex (body.bytes[15], ==, 0x45);
    }
  goodix_enrollment_command_body_clear (&body);
  g_assert_cmpuint (body.length, ==, 0u);
  for (gsize i = 0; i < sizeof body.bytes; i++)
    g_assert_cmphex (body.bytes[i], ==, 0);
}

static void
test_exact_body_contracts (void)
{
  GoodixEnrollmentCommandBodyAudit audit = { 0 };
  GoodixEnrollmentCommandIntent i20 = intent (
    GOODIX_ENROLLMENT_EVENT_COMMAND_20,
    GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUXILIARY_TRANSITION,
    GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, 0x20, 4u);
  GoodixEnrollmentCommandIntent i22 = intent (
    GOODIX_ENROLLMENT_EVENT_COMMAND_22,
    GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRIMARY_ACQUIRE,
    GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, 0x22, 4u);
  GoodixEnrollmentCommandIntent i50 = intent (
    GOODIX_ENROLLMENT_EVENT_COMMAND_50,
    GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV,
    GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, 0x50, 1u);
  GoodixEnrollmentCommandIntent i34 = intent (
    GOODIX_ENROLLMENT_EVENT_COMMAND_34,
    GOODIX_ENROLLMENT_COMMAND_PURPOSE_FINGER_UP,
    GOODIX_ENROLLMENT_BODY_FDT_0A01, 0x34, 4u);
  GoodixEnrollmentCommandIntent i34_pre = intent (
    GOODIX_ENROLLMENT_EVENT_COMMAND_34,
    GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRE_AUX_FDT,
    GOODIX_ENROLLMENT_BODY_FDT_0A01, 0x34, 4u);
  GoodixEnrollmentCommandIntent i36 = intent (
    GOODIX_ENROLLMENT_EVENT_COMMAND_36,
    GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUX_FDT_SCAN,
    GOODIX_ENROLLMENT_BODY_FDT_0901, 0x36, 4u);
  GoodixEnrollmentCommandIntent i32 = intent (
    GOODIX_ENROLLMENT_EVENT_COMMAND_32,
    GOODIX_ENROLLMENT_COMMAND_PURPOSE_INTER_STAGE_REARM,
    GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801, 0x32, 4u);
  GoodixEnrollmentCommandIntent i32_nav = intent (
    GOODIX_ENROLLMENT_EVENT_COMMAND_32,
    GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV_PREPARE,
    GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801, 0x32, 4u);
  GoodixEnrollmentCommandMaterial up = material (
    4u, GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_UP, FALSE);
  GoodixEnrollmentCommandMaterial scan = material (
    4u, GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_AUX_SCAN, FALSE);
  GoodixEnrollmentCommandMaterial down = material (
    4u, GOODIX_ENROLLMENT_TABLE_ROLE_TRANSITION_DOWN, TRUE);

  assert_build (&i20, NULL, 0x01, 2u, &audit);
  assert_build (&i22, NULL, 0x01, 2u, &audit);
  assert_build (&i50, NULL, 0x01, 2u, &audit);
  assert_build (&i34, &up, 0x0a, 14u, &audit);
  assert_build (&i34_pre, &up, 0x0a, 14u, &audit);
  assert_build (&i36, &scan, 0x09, 14u, &audit);
  assert_build (&i32, &down, 0x08, 16u, &audit);
  assert_build (&i32_nav, &down, 0x08, 16u, &audit);
  g_assert_cmpuint (audit.body_build_count, ==, 8u);
  g_assert_cmpuint (audit.simple_body_count, ==, 3u);
  g_assert_cmpuint (audit.fdt_body_count, ==, 3u);
  g_assert_cmpuint (audit.fdt_timestamp_body_count, ==, 2u);
  g_assert_cmpuint (audit.a0_frame_build_count, ==, 0u);
  g_assert_cmpuint (audit.submit_count, ==, 0u);
}

static void
assert_rejected (GoodixEnrollmentCommandIntent   *command_intent,
                 GoodixEnrollmentCommandMaterial *command_material,
                 GoodixEnrollmentCommandBodyAudit *audit)
{
  GoodixEnrollmentCommandBody body;
  g_autoptr(GError) error = NULL;

  memset (&body, 0xa5, sizeof body);
  g_assert_false (goodix_enrollment_command_body_build (
    command_intent, command_material, &body, audit, &error));
  g_assert_nonnull (error);
  g_assert_cmpuint (body.length, ==, 0u);
  for (gsize i = 0; i < sizeof body.bytes; i++)
    g_assert_cmphex (body.bytes[i], ==, 0);
}

static void
test_fail_closed_material_binding (void)
{
  GoodixEnrollmentCommandBodyAudit audit = { 0 };
  GoodixEnrollmentCommandIntent i32 = intent (
    GOODIX_ENROLLMENT_EVENT_COMMAND_32,
    GOODIX_ENROLLMENT_COMMAND_PURPOSE_INTER_STAGE_REARM,
    GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801, 0x32, 7u);
  GoodixEnrollmentCommandMaterial wrong_stage = material (
    6u, GOODIX_ENROLLMENT_TABLE_ROLE_TRANSITION_DOWN, TRUE);
  GoodixEnrollmentCommandMaterial wrong_role = material (
    7u, GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_UP, TRUE);
  GoodixEnrollmentCommandMaterial no_timestamp = material (
    7u, GOODIX_ENROLLMENT_TABLE_ROLE_TRANSITION_DOWN, FALSE);
  GoodixEnrollmentCommandMaterial unused = material (
    7u, GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_UP, FALSE);
  GoodixEnrollmentCommandIntent i20 = intent (
    GOODIX_ENROLLMENT_EVENT_COMMAND_20,
    GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUXILIARY_TRANSITION,
    GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, 0x20, 7u);

  assert_rejected (&i32, &wrong_stage, &audit);
  assert_rejected (&i32, &wrong_role, &audit);
  assert_rejected (&i32, &no_timestamp, &audit);
  i32.wire_frame_serializable = TRUE;
  assert_rejected (&i32, NULL, &audit);
  assert_rejected (&i20, &unused, &audit);
  i20.stage_index = 0u;
  assert_rejected (&i20, NULL, &audit);
  g_assert_cmpuint (audit.rejected_material_count, ==, 6u);
  g_assert_cmpuint (audit.body_build_count, ==, 0u);
  g_assert_cmpuint (audit.a0_frame_build_count, ==, 0u);
  g_assert_cmpuint (audit.submit_count, ==, 0u);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d279-11-command-body/exact-contracts",
                   test_exact_body_contracts);
  g_test_add_func ("/d279-11-command-body/fail-closed-material-binding",
                   test_fail_closed_material_binding);
  return g_test_run ();
}
