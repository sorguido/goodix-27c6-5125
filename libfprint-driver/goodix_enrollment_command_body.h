/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_COMMAND_BODY_H
#define GOODIX_ENROLLMENT_COMMAND_BODY_H

#include "goodix_enrollment_command_plan.h"

G_BEGIN_DECLS

#define GOODIX_ENROLLMENT_FDT_TABLE_LENGTH 12u
#define GOODIX_ENROLLMENT_COMMAND_BODY_MAX_LENGTH 16u

typedef enum
{
  GOODIX_ENROLLMENT_TABLE_ROLE_NONE,
  GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_UP,
  GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_AUX_SCAN,
  GOODIX_ENROLLMENT_TABLE_ROLE_TRANSITION_DOWN,
} GoodixEnrollmentTableRole;

typedef struct
{
  guint stage_index;
  GoodixEnrollmentTableRole table_role;
  guint8 fdt_table[GOODIX_ENROLLMENT_FDT_TABLE_LENGTH];
  guint16 timestamp;
  gboolean has_fdt_table;
  gboolean has_timestamp;
} GoodixEnrollmentCommandMaterial;

typedef struct
{
  guint8 bytes[GOODIX_ENROLLMENT_COMMAND_BODY_MAX_LENGTH];
  gsize length;
} GoodixEnrollmentCommandBody;

typedef struct
{
  guint body_build_count;
  guint simple_body_count;
  guint fdt_body_count;
  guint fdt_timestamp_body_count;
  guint rejected_material_count;
  guint a0_frame_build_count;
  guint submit_count;
} GoodixEnrollmentCommandBodyAudit;

/* Builds only the inner command body. It has no A0/fixed64 serializer and no
 * transport. Dynamic FDT provenance and timestamp production remain caller
 * responsibilities and are bound to the exact stage/role here. */
gboolean goodix_enrollment_command_body_build (
  const GoodixEnrollmentCommandIntent   *intent,
  const GoodixEnrollmentCommandMaterial *material,
  GoodixEnrollmentCommandBody           *body,
  GoodixEnrollmentCommandBodyAudit      *audit,
  GError                               **error);

void goodix_enrollment_command_body_clear (GoodixEnrollmentCommandBody *body);

G_END_DECLS

#endif
