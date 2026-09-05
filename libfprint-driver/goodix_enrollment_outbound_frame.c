/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Enrollment-only A0/fixed64 serializer. No backend or submit path. */
#include "goodix_enrollment_outbound_frame.h"

#include <string.h>

typedef enum
{
  GOODIX_ENROLLMENT_OUTBOUND_ERROR_ARGUMENT,
  GOODIX_ENROLLMENT_OUTBOUND_ERROR_CONTRACT,
  GOODIX_ENROLLMENT_OUTBOUND_ERROR_LENGTH,
} GoodixEnrollmentOutboundError;

#define GOODIX_ENROLLMENT_OUTBOUND_ERROR \
  (goodix_enrollment_outbound_error_quark ())

static GQuark
goodix_enrollment_outbound_error_quark (void)
{
  return g_quark_from_static_string ("goodix-enrollment-outbound-frame-error");
}

static GBytes *
outbound_fail (GoodixEnrollmentOutboundFrameAudit *audit,
               GoodixEnrollmentOutboundError       code,
               const gchar                        *message,
               GError                            **error)
{
  if (audit != NULL)
    audit->rejected_prepared_count++;
  if (error == NULL || *error == NULL)
    g_set_error_literal (error, GOODIX_ENROLLMENT_OUTBOUND_ERROR, code,
                         message);
  return NULL;
}

static gboolean
allowlisted_control (guint8 control)
{
  return control == 0x20 || control == 0x22 || control == 0x32 ||
         control == 0x34 || control == 0x36 || control == 0x50;
}

static gboolean
prepared_body_valid (const GoodixEnrollmentPreparedCommand *prepared)
{
  GoodixEnrollmentCommandMaterial material = { 0 };
  GoodixEnrollmentCommandBody rebuilt = { 0 };
  const GoodixEnrollmentCommandMaterial *material_ptr = NULL;
  g_autoptr(GError) error = NULL;
  gboolean valid;

  if (prepared->intent.body_class != GOODIX_ENROLLMENT_BODY_SIMPLE_01_00)
    {
      gsize required_length =
        prepared->intent.body_class ==
          GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801 ? 16u : 14u;

      if (prepared->body.length != required_length)
        return FALSE;
      material.stage_index = prepared->intent.stage_index;
      material.table_role =
        prepared->intent.body_class == GOODIX_ENROLLMENT_BODY_FDT_0A01 ?
          GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_UP :
        (prepared->intent.body_class == GOODIX_ENROLLMENT_BODY_FDT_0901 ?
          GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_AUX_SCAN :
          GOODIX_ENROLLMENT_TABLE_ROLE_TRANSITION_DOWN);
      memcpy (material.fdt_table, prepared->body.bytes + 2u,
              GOODIX_ENROLLMENT_FDT_TABLE_LENGTH);
      material.has_fdt_table = TRUE;
      if (required_length == 16u)
        {
          material.timestamp = (guint16) (
            (guint16) prepared->body.bytes[14] |
            ((guint16) prepared->body.bytes[15] << 8));
          material.has_timestamp = TRUE;
        }
      material_ptr = &material;
    }
  valid = goodix_enrollment_command_body_build (
    &prepared->intent, material_ptr, &rebuilt, NULL, &error) &&
    rebuilt.length == prepared->body.length &&
    memcmp (rebuilt.bytes, prepared->body.bytes, rebuilt.length) == 0;
  goodix_enrollment_command_body_clear (&rebuilt);
  memset (&material, 0, sizeof material);
  return valid;
}

static void
record_control (GoodixEnrollmentOutboundFrameAudit *audit,
                guint8                              control)
{
  if (audit == NULL)
    return;
  switch (control)
    {
    case 0x20: audit->command_20_count++; break;
    case 0x22: audit->command_22_count++; break;
    case 0x32: audit->command_32_count++; break;
    case 0x34: audit->command_34_count++; break;
    case 0x36: audit->command_36_count++; break;
    case 0x50: audit->command_50_count++; break;
    default: g_assert_not_reached ();
    }
}

GBytes *
goodix_enrollment_outbound_frame_build (
  const GoodixEnrollmentPreparedCommand *prepared,
  GoodixEnrollmentOutboundFrameAudit    *audit,
  GError                               **error)
{
  g_autoptr(GBytes) logical = NULL;
  g_autoptr(GByteArray) physical = NULL;
  const guint8 *logical_data;
  gsize logical_length;
  static const guint8 zeroes[GOODIX_ENROLLMENT_FIXED64_LENGTH] = { 0 };

  if (prepared == NULL)
    return outbound_fail (audit, GOODIX_ENROLLMENT_OUTBOUND_ERROR_ARGUMENT,
                          "prepared enrollment command is absent", error);
  if (!allowlisted_control (prepared->intent.control) ||
      prepared->intent.wire_frame_serializable ||
      !prepared_body_valid (prepared))
    return outbound_fail (audit, GOODIX_ENROLLMENT_OUTBOUND_ERROR_CONTRACT,
                          "prepared enrollment command violates its contract",
                          error);
  logical = goodix_a0_build_frame (
    prepared->intent.control,
    (guint8) (prepared->intent.control & 0xfeu),
    prepared->body.bytes, prepared->body.length, error);
  if (logical == NULL)
    return outbound_fail (audit, GOODIX_ENROLLMENT_OUTBOUND_ERROR_CONTRACT,
                          "A0 enrollment frame construction failed", error);
  logical_data = g_bytes_get_data (logical, &logical_length);
  if (logical_length > GOODIX_ENROLLMENT_FIXED64_LENGTH)
    return outbound_fail (audit, GOODIX_ENROLLMENT_OUTBOUND_ERROR_LENGTH,
                          "A0 enrollment frame exceeds fixed64", error);

  physical = g_byte_array_sized_new (GOODIX_ENROLLMENT_FIXED64_LENGTH);
  g_byte_array_append (physical, logical_data, (guint) logical_length);
  g_byte_array_append (physical, zeroes,
                       (guint) (GOODIX_ENROLLMENT_FIXED64_LENGTH -
                                logical_length));
  if (audit != NULL)
    {
      audit->frame_build_count++;
      record_control (audit, prepared->intent.control);
    }
  return g_byte_array_free_to_bytes (g_steal_pointer (&physical));
}
