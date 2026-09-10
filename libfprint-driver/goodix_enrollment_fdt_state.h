/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_FDT_STATE_H
#define GOODIX_ENROLLMENT_FDT_STATE_H

#include "goodix_enrollment_command_body.h"
#include "goodix_fdt_irq_policy.h"

G_BEGIN_DECLS

typedef struct _GoodixEnrollmentFdtState GoodixEnrollmentFdtState;

typedef struct
{
  gboolean required;
  GoodixEnrollmentCommandMaterial material;
} GoodixEnrollmentResolvedMaterial;

typedef struct
{
  guint irq2_up_derivation_count;
  guint irq0200_down_derivation_count;
  guint stage_up_resolution_count;
  guint previous_down_resolution_count;
  guint current_down_resolution_count;
  guint rejected_resolution_count;
  guint retry_count;
  guint submit_count;
} GoodixEnrollmentFdtStateAudit;

GoodixEnrollmentFdtState *goodix_enrollment_fdt_state_new (
  GoodixEnrollmentFdtStateAudit *audit);
void goodix_enrollment_fdt_state_free (GoodixEnrollmentFdtState *state);

gboolean goodix_enrollment_fdt_state_observe_irq2 (
  GoodixEnrollmentFdtState *state,
  guint                     stage_index,
  guint16                   touch_flags,
  const guint8              raw[GOODIX_ENROLLMENT_FDT_TABLE_LENGTH],
  GError                  **error);
gboolean goodix_enrollment_fdt_state_observe_irq0200 (
  GoodixEnrollmentFdtState *state,
  guint                     stage_index,
  guint16                   touch_flags,
  const guint8              raw[GOODIX_ENROLLMENT_FDT_TABLE_LENGTH],
  GError                  **error);

gboolean goodix_enrollment_fdt_state_resolve (
  GoodixEnrollmentFdtState          *state,
  const GoodixEnrollmentCommandIntent *intent,
  guint16                            timestamp,
  gboolean                           timestamp_available,
  GoodixEnrollmentResolvedMaterial  *resolved,
  GError                           **error);
void goodix_enrollment_resolved_material_clear (
  GoodixEnrollmentResolvedMaterial *resolved);

G_END_DECLS

#endif
