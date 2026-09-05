/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_command_body.h"

#include <string.h>

typedef enum
{
  GOODIX_ENROLLMENT_BODY_ERROR_ARGUMENT,
  GOODIX_ENROLLMENT_BODY_ERROR_INTENT,
  GOODIX_ENROLLMENT_BODY_ERROR_MATERIAL,
} GoodixEnrollmentBodyError;

#define GOODIX_ENROLLMENT_BODY_ERROR (goodix_enrollment_body_error_quark ())

static GQuark
goodix_enrollment_body_error_quark (void)
{
  return g_quark_from_static_string ("goodix-enrollment-command-body-error");
}

static gboolean
body_fail (GoodixEnrollmentCommandBodyAudit *audit,
           GoodixEnrollmentBodyError         code,
           const gchar                      *message,
           GError                          **error)
{
  if (audit != NULL)
    audit->rejected_material_count++;
  g_set_error_literal (error, GOODIX_ENROLLMENT_BODY_ERROR, code, message);
  return FALSE;
}

static gboolean
intent_contract_valid (const GoodixEnrollmentCommandIntent *intent)
{
  if (intent->stage_index == 0u)
    return FALSE;
  switch (intent->event)
    {
    case GOODIX_ENROLLMENT_EVENT_COMMAND_20:
      return intent->control == 0x20 &&
             intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUXILIARY_TRANSITION &&
             intent->body_class == GOODIX_ENROLLMENT_BODY_SIMPLE_01_00;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_22:
      return intent->control == 0x22 &&
             intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRIMARY_ACQUIRE &&
             intent->body_class == GOODIX_ENROLLMENT_BODY_SIMPLE_01_00;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_32:
      return intent->control == 0x32 &&
             (intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV_PREPARE ||
              intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_INTER_STAGE_REARM) &&
             intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_34:
      return intent->control == 0x34 &&
             (intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRE_AUX_FDT ||
              intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_FINGER_UP) &&
             intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_0A01;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_36:
      return intent->control == 0x36 &&
             intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUX_FDT_SCAN &&
             intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_0901;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_50:
      return intent->control == 0x50 &&
             intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV &&
             intent->body_class == GOODIX_ENROLLMENT_BODY_SIMPLE_01_00;
    case GOODIX_ENROLLMENT_EVENT_NONE:
    case GOODIX_ENROLLMENT_EVENT_IRQ2:
    case GOODIX_ENROLLMENT_EVENT_ACK_22:
    case GOODIX_ENROLLMENT_EVENT_PRIMARY_B0:
    case GOODIX_ENROLLMENT_EVENT_ACK_34:
    case GOODIX_ENROLLMENT_EVENT_IRQ0200:
    case GOODIX_ENROLLMENT_EVENT_ACK_20:
    case GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0:
    case GOODIX_ENROLLMENT_EVENT_ACK_32:
    case GOODIX_ENROLLMENT_EVENT_ACK_50:
    case GOODIX_ENROLLMENT_EVENT_NAV:
    case GOODIX_ENROLLMENT_EVENT_ACK_36:
    case GOODIX_ENROLLMENT_EVENT_IRQ0100:
      return FALSE;
    }
  return FALSE;
}

static gboolean
material_valid (const GoodixEnrollmentCommandIntent   *intent,
                const GoodixEnrollmentCommandMaterial *material,
                GoodixEnrollmentTableRole              role,
                gboolean                               timestamp)
{
  return material != NULL && material->has_fdt_table &&
         material->stage_index == intent->stage_index &&
         material->table_role == role &&
         material->has_timestamp == timestamp;
}

gboolean
goodix_enrollment_command_body_build (
  const GoodixEnrollmentCommandIntent   *intent,
  const GoodixEnrollmentCommandMaterial *material,
  GoodixEnrollmentCommandBody           *body,
  GoodixEnrollmentCommandBodyAudit      *audit,
  GError                               **error)
{
  GoodixEnrollmentTableRole role;

  if (intent == NULL || body == NULL)
    return body_fail (audit, GOODIX_ENROLLMENT_BODY_ERROR_ARGUMENT,
                      "command intent or body output is absent", error);
  goodix_enrollment_command_body_clear (body);
  if (intent->wire_frame_serializable || !intent_contract_valid (intent))
    return body_fail (audit, GOODIX_ENROLLMENT_BODY_ERROR_INTENT,
                      "command intent is not a valid zero-sender plan item",
                      error);

  if (intent->body_class == GOODIX_ENROLLMENT_BODY_SIMPLE_01_00)
    {
      if (material != NULL)
        return body_fail (audit, GOODIX_ENROLLMENT_BODY_ERROR_MATERIAL,
                          "simple command must not carry dynamic material",
                          error);
      body->bytes[0] = 0x01;
      body->bytes[1] = 0x00;
      body->length = 2u;
      if (audit != NULL)
        audit->simple_body_count++;
    }
  else
    {
      role = intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_0901 ?
        GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_AUX_SCAN :
        (intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801 ?
         GOODIX_ENROLLMENT_TABLE_ROLE_TRANSITION_DOWN :
         GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_UP);
      if (!material_valid (intent, material, role,
                           intent->body_class ==
                             GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801))
        return body_fail (audit, GOODIX_ENROLLMENT_BODY_ERROR_MATERIAL,
                          "dynamic material does not match command stage and role",
                          error);
      body->bytes[0] = intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_0A01 ?
        0x0a : (intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_0901 ?
                0x09 : 0x08);
      body->bytes[1] = 0x01;
      memcpy (body->bytes + 2, material->fdt_table,
              GOODIX_ENROLLMENT_FDT_TABLE_LENGTH);
      body->length = 14u;
      if (intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801)
        {
          body->bytes[14] = (guint8) material->timestamp;
          body->bytes[15] = (guint8) (material->timestamp >> 8);
          body->length = 16u;
          if (audit != NULL)
            audit->fdt_timestamp_body_count++;
        }
      else if (audit != NULL)
        audit->fdt_body_count++;
    }
  if (audit != NULL)
    audit->body_build_count++;
  return TRUE;
}

void
goodix_enrollment_command_body_clear (GoodixEnrollmentCommandBody *body)
{
  if (body == NULL)
    return;
  for (gsize i = 0; i < sizeof body->bytes; i++)
    ((volatile guint8 *) body->bytes)[i] = 0;
  body->length = 0u;
}
