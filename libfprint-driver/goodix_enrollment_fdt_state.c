/* SPDX-License-Identifier: LGPL-2.1-or-later */
#include "goodix_enrollment_fdt_state.h"

#include <string.h>

typedef enum
{
  GOODIX_ENROLLMENT_FDT_ERROR_ARGUMENT,
  GOODIX_ENROLLMENT_FDT_ERROR_ORDER,
  GOODIX_ENROLLMENT_FDT_ERROR_RANGE,
  GOODIX_ENROLLMENT_FDT_ERROR_MATERIAL,
} GoodixEnrollmentFdtError;

#define GOODIX_ENROLLMENT_FDT_ERROR (goodix_enrollment_fdt_error_quark ())

struct _GoodixEnrollmentFdtState
{
  guint current_stage;
  guint up_stage;
  guint down_stage;
  guint8 up_table[GOODIX_ENROLLMENT_FDT_TABLE_LENGTH];
  guint8 down_table[GOODIX_ENROLLMENT_FDT_TABLE_LENGTH];
  GoodixEnrollmentFdtStateAudit internal_audit;
  GoodixEnrollmentFdtStateAudit *audit;
  gboolean failed;
};

static GQuark
goodix_enrollment_fdt_error_quark (void)
{
  return g_quark_from_static_string ("goodix-enrollment-fdt-state-error");
}

static gboolean
fail (GoodixEnrollmentFdtState *state,
      GoodixEnrollmentFdtError  code,
      const gchar              *message,
      GError                  **error)
{
  if (state != NULL)
    {
      state->failed = TRUE;
      state->audit->rejected_resolution_count++;
    }
  g_set_error_literal (error, GOODIX_ENROLLMENT_FDT_ERROR, code, message);
  return FALSE;
}

GoodixEnrollmentFdtState *
goodix_enrollment_fdt_state_new (GoodixEnrollmentFdtStateAudit *audit)
{
  GoodixEnrollmentFdtState *state = g_new0 (GoodixEnrollmentFdtState, 1);

  state->audit = audit != NULL ? audit : &state->internal_audit;
  *state->audit = (GoodixEnrollmentFdtStateAudit) { 0 };
  return state;
}

void
goodix_enrollment_fdt_state_free (GoodixEnrollmentFdtState *state)
{
  if (state == NULL)
    return;
  memset (state->up_table, 0, sizeof state->up_table);
  memset (state->down_table, 0, sizeof state->down_table);
  g_free (state);
}

gboolean
goodix_enrollment_fdt_state_observe_irq2 (
  GoodixEnrollmentFdtState *state,
  guint                     stage_index,
  guint16                   touch_flags,
  const guint8              raw[GOODIX_ENROLLMENT_FDT_TABLE_LENGTH],
  GError                  **error)
{
  if (state == NULL || raw == NULL || stage_index == 0u)
    return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_ARGUMENT,
                 "IRQ2 FDT observation is incomplete", error);
  if (state->failed || stage_index != state->current_stage + 1u)
    return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_ORDER,
                 "IRQ2 FDT stage is stale or non-consecutive", error);
  if (!goodix_fdt_derive_up_table (raw, touch_flags, 0x1du,
                                   state->up_table))
    return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_RANGE,
                 "IRQ2 flags or up-table material are invalid", error);
  state->current_stage = stage_index;
  state->up_stage = stage_index;
  state->audit->irq2_up_derivation_count++;
  return TRUE;
}

gboolean
goodix_enrollment_fdt_state_observe_irq0200 (
  GoodixEnrollmentFdtState *state,
  guint                     stage_index,
  guint16                   touch_flags,
  const guint8              raw[GOODIX_ENROLLMENT_FDT_TABLE_LENGTH],
  GError                  **error)
{
  if (state == NULL || raw == NULL || stage_index == 0u)
    return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_ARGUMENT,
                 "IRQ0200 FDT observation is incomplete", error);
  if (state->failed || stage_index != state->current_stage ||
      state->up_stage != stage_index || state->down_stage >= stage_index)
    return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_ORDER,
                 "IRQ0200 FDT stage is stale or out of order", error);
  if (!goodix_fdt_derive_down_table (raw, touch_flags, state->down_table))
    return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_RANGE,
                 "IRQ0200 flags or down-table material are invalid", error);
  state->down_stage = stage_index;
  state->audit->irq0200_down_derivation_count++;
  return TRUE;
}

gboolean
goodix_enrollment_fdt_state_resolve (
  GoodixEnrollmentFdtState            *state,
  const GoodixEnrollmentCommandIntent *intent,
  guint16                              timestamp,
  gboolean                             timestamp_available,
  GoodixEnrollmentResolvedMaterial    *resolved,
  GError                             **error)
{
  const guint8 *table = NULL;
  GoodixEnrollmentTableRole role = GOODIX_ENROLLMENT_TABLE_ROLE_NONE;

  if (state == NULL || intent == NULL || resolved == NULL)
    return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_ARGUMENT,
                 "FDT material resolution arguments are incomplete", error);
  goodix_enrollment_resolved_material_clear (resolved);
  if (state->failed || intent->stage_index != state->current_stage)
    return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_ORDER,
                 "command intent does not match current FDT stage", error);
  if (intent->body_class == GOODIX_ENROLLMENT_BODY_SIMPLE_01_00)
    {
      if (timestamp_available)
        return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_MATERIAL,
                     "simple command received an unused timestamp", error);
      return TRUE;
    }
  if (intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_0A01)
    {
      if (state->up_stage != intent->stage_index || timestamp_available)
        return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_MATERIAL,
                     "stage-up table is unavailable or timestamp is extraneous", error);
      table = state->up_table;
      role = GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_UP;
      state->audit->stage_up_resolution_count++;
    }
  else if (intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_0901)
    {
      if (intent->stage_index < 2u || state->down_stage + 1u != intent->stage_index ||
          timestamp_available)
        return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_MATERIAL,
                     "previous-stage down table is unavailable", error);
      table = state->down_table;
      role = GOODIX_ENROLLMENT_TABLE_ROLE_STAGE_AUX_SCAN;
      state->audit->previous_down_resolution_count++;
    }
  else if (intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801)
    {
      if (state->down_stage != intent->stage_index || !timestamp_available)
        return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_MATERIAL,
                     "current-stage down table or timestamp is unavailable", error);
      table = state->down_table;
      role = GOODIX_ENROLLMENT_TABLE_ROLE_TRANSITION_DOWN;
      state->audit->current_down_resolution_count++;
    }
  else
    return fail (state, GOODIX_ENROLLMENT_FDT_ERROR_MATERIAL,
                 "unknown FDT body class", error);

  resolved->required = TRUE;
  resolved->material.stage_index = intent->stage_index;
  resolved->material.table_role = role;
  memcpy (resolved->material.fdt_table, table, sizeof resolved->material.fdt_table);
  resolved->material.has_fdt_table = TRUE;
  resolved->material.timestamp = timestamp;
  resolved->material.has_timestamp =
    intent->body_class == GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801;
  return TRUE;
}

void
goodix_enrollment_resolved_material_clear (
  GoodixEnrollmentResolvedMaterial *resolved)
{
  if (resolved == NULL)
    return;
  memset (resolved, 0, sizeof *resolved);
}
