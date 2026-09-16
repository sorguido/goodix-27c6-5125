/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_outbound_frame.h"

#include <string.h>

static void
clear_prepared (GoodixEnrollmentPreparedCommand *prepared)
{
  goodix_enrollment_command_body_clear (&prepared->body);
  memset (&prepared->intent, 0, sizeof prepared->intent);
}

static GoodixEnrollmentEvent
event_for_control (guint8 control)
{
  switch (control)
    {
    case 0x20: return GOODIX_ENROLLMENT_EVENT_COMMAND_20;
    case 0x22: return GOODIX_ENROLLMENT_EVENT_COMMAND_22;
    case 0x32: return GOODIX_ENROLLMENT_EVENT_COMMAND_32;
    case 0x34: return GOODIX_ENROLLMENT_EVENT_COMMAND_34;
    case 0x36: return GOODIX_ENROLLMENT_EVENT_COMMAND_36;
    case 0x50: return GOODIX_ENROLLMENT_EVENT_COMMAND_50;
    default: g_assert_not_reached ();
    }
}

static void
assert_frame (const GoodixEnrollmentPreparedCommand *prepared,
              GoodixEnrollmentOutboundFrameAudit    *audit)
{
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) physical = goodix_enrollment_outbound_frame_build (
    prepared, audit, &error);
  GoodixA0Message parsed = { 0 };
  const guint8 *data;
  const guint8 *body;
  gsize length;
  gsize body_length;
  guint16 payload_length;
  gsize logical_length;

  g_assert_no_error (error);
  g_assert_nonnull (physical);
  data = g_bytes_get_data (physical, &length);
  g_assert_cmpuint (length, ==, GOODIX_ENROLLMENT_FIXED64_LENGTH);
  payload_length = (guint16) ((guint16) data[1] |
                              ((guint16) data[2] << 8));
  logical_length = (gsize) payload_length + 4u;
  for (gsize i = logical_length; i < length; i++)
    g_assert_cmphex (data[i], ==, 0x00);
  {
    g_autoptr(GBytes) logical = g_bytes_new (data, logical_length);

    g_assert_true (goodix_a0_parse_frame (
      logical, (guint8) (prepared->intent.control & 0xfeu),
      &parsed, &error));
  }
  g_assert_no_error (error);
  g_assert_cmphex (parsed.control, ==, prepared->intent.control);
  body = g_bytes_get_data (parsed.body, &body_length);
  g_assert_cmpuint (body_length, ==, prepared->body.length);
  g_assert_cmpint (memcmp (body, prepared->body.bytes, body_length), ==, 0);
  goodix_a0_message_clear (&parsed);
}

static GoodixEnrollmentPreparedCommand
make_prepared (guint8                         control,
               GoodixEnrollmentCommandPurpose purpose,
               GoodixEnrollmentBodyClass      body_class,
               guint                          stage)
{
  GoodixEnrollmentPreparedCommand prepared = { 0 };
  GoodixEnrollmentCommandMaterial material = { 0 };
  const GoodixEnrollmentCommandMaterial *material_ptr = NULL;
  g_autoptr(GError) error = NULL;

  prepared.intent.event = event_for_control (control);
  prepared.intent.control = control;
  prepared.intent.purpose = purpose;
  prepared.intent.body_class = body_class;
  prepared.intent.stage_index = stage;
  prepared.intent.wire_frame_serializable = FALSE;
  if (body_class != GOODIX_ENROLLMENT_BODY_SIMPLE_01_00)
    {
      material.stage_index = stage;
      material.table_role = body_class == GOODIX_ENROLLMENT_BODY_FDT_0A01 ?
        GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_UP :
        (body_class == GOODIX_ENROLLMENT_BODY_FDT_0901 ?
         GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_AUX_SCAN :
         GOODIX_ENROLLMENT_TABLE_ROLE_TRANSITION_DOWN);
      for (guint i = 0u; i < GOODIX_ENROLLMENT_FDT_TABLE_LENGTH; i++)
        material.fdt_table[i] = (guint8) (0x30u + i + stage);
      material.has_fdt_table = TRUE;
      if (body_class == GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801)
        {
          material.timestamp = (guint16) (0x4000u + stage);
          material.has_timestamp = TRUE;
        }
      material_ptr = &material;
    }
  g_assert_true (goodix_enrollment_command_body_build (
    &prepared.intent, material_ptr, &prepared.body, NULL, &error));
  g_assert_no_error (error);
  return prepared;
}

static void
test_all_enrollment_command_purposes (void)
{
  GoodixEnrollmentOutboundFrameAudit audit = { 0 };
  GoodixEnrollmentPreparedCommand commands[] = {
    make_prepared (0x22, GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRIMARY_ACQUIRE,
                   GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, 1u),
    make_prepared (0x34, GOODIX_ENROLLMENT_COMMAND_PURPOSE_FINGER_UP,
                   GOODIX_ENROLLMENT_BODY_FDT_0A01, 1u),
    make_prepared (0x20, GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUXILIARY_TRANSITION,
                   GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, 1u),
    make_prepared (0x32, GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV_PREPARE,
                   GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801, 1u),
    make_prepared (0x50, GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV,
                   GOODIX_ENROLLMENT_BODY_SIMPLE_01_00, 1u),
    make_prepared (0x32, GOODIX_ENROLLMENT_COMMAND_PURPOSE_INTER_STAGE_REARM,
                   GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801, 1u),
    make_prepared (0x34, GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRE_AUX_FDT,
                   GOODIX_ENROLLMENT_BODY_FDT_0A01, 2u),
    make_prepared (0x36, GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUX_FDT_SCAN,
                   GOODIX_ENROLLMENT_BODY_FDT_0901, 2u),
  };

  for (guint i = 0u; i < G_N_ELEMENTS (commands); i++)
    {
      assert_frame (&commands[i], &audit);
      clear_prepared (&commands[i]);
    }
  g_assert_cmpuint (audit.frame_build_count, ==, G_N_ELEMENTS (commands));
  g_assert_cmpuint (audit.command_20_count, ==, 1u);
  g_assert_cmpuint (audit.command_22_count, ==, 1u);
  g_assert_cmpuint (audit.command_32_count, ==, 2u);
  g_assert_cmpuint (audit.command_34_count, ==, 2u);
  g_assert_cmpuint (audit.command_36_count, ==, 1u);
  g_assert_cmpuint (audit.command_50_count, ==, 1u);
  g_assert_cmpuint (audit.persistent_family_count, ==, 0u);
  g_assert_cmpuint (audit.retry_count, ==, 0u);
  g_assert_cmpuint (audit.submit_count, ==, 0u);
}

static void
test_tampered_body_fails_closed (void)
{
  GoodixEnrollmentOutboundFrameAudit audit = { 0 };
  GoodixEnrollmentPreparedCommand prepared = make_prepared (
    0x34, GOODIX_ENROLLMENT_COMMAND_PURPOSE_FINGER_UP,
    GOODIX_ENROLLMENT_BODY_FDT_0A01, 1u);
  g_autoptr(GError) error = NULL;
  g_autoptr(GBytes) frame = NULL;

  prepared.body.bytes[0] = 0x09;
  frame = goodix_enrollment_outbound_frame_build (&prepared, &audit, &error);
  g_assert_null (frame);
  g_assert_nonnull (error);
  g_assert_cmpuint (audit.rejected_prepared_count, ==, 1u);
  g_assert_cmpuint (audit.frame_build_count, ==, 0u);
  g_assert_cmpuint (audit.submit_count, ==, 0u);
  clear_prepared (&prepared);
}

int
main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  g_test_add_func ("/d279-16-outbound/all-enrollment-command-purposes",
                   test_all_enrollment_command_purposes);
  g_test_add_func ("/d279-16-outbound/tampered-body-fails-closed",
                   test_tampered_body_fails_closed);
  return g_test_run ();
}
