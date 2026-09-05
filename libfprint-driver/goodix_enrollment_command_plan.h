/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_COMMAND_PLAN_H
#define GOODIX_ENROLLMENT_COMMAND_PLAN_H

#include "goodix_enrollment_pipeline.h"

G_BEGIN_DECLS

typedef struct _GoodixEnrollmentCommandPlan GoodixEnrollmentCommandPlan;

typedef enum
{
  GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRIMARY_ACQUIRE,
  GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRE_AUX_FDT,
  GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUX_FDT_SCAN,
  GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUXILIARY_TRANSITION,
  GOODIX_ENROLLMENT_COMMAND_PURPOSE_FINGER_UP,
  GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV_PREPARE,
  GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV,
  GOODIX_ENROLLMENT_COMMAND_PURPOSE_INTER_STAGE_REARM,
} GoodixEnrollmentCommandPurpose;

typedef enum
{
  GOODIX_ENROLLMENT_BODY_SIMPLE_01_00,
  GOODIX_ENROLLMENT_BODY_FDT_0A01,
  GOODIX_ENROLLMENT_BODY_FDT_0901,
  GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801,
} GoodixEnrollmentBodyClass;

typedef struct
{
  GoodixEnrollmentEvent event;
  GoodixEnrollmentCommandPurpose purpose;
  GoodixEnrollmentBodyClass body_class;
  guint stage_index;
  guint8 control;
  /* This layer deliberately has no body bytes or wire-frame serializer. */
  gboolean wire_frame_serializable;
} GoodixEnrollmentCommandIntent;

typedef struct
{
  GoodixEnrollmentPipelineAudit pipeline;
  guint committed_command_count;
  guint command_20_count;
  guint command_22_count;
  guint command_32_count;
  guint command_34_count;
  guint command_36_count;
  guint command_50_count;
  guint pre_aux_fdt_count;
  guint finger_up_count;
  guint first_nav_prepare_count;
  guint inter_stage_rearm_count;
  guint retry_count;
  guint serialized_command_count;
  gboolean failed;
} GoodixEnrollmentCommandPlanAudit;

GoodixEnrollmentCommandPlan *goodix_enrollment_command_plan_new (
  const GoodixEnrollmentModelConfig *config,
  GoodixEnrollmentImageFunc          image_ready,
  gpointer                           user_data,
  GoodixEnrollmentCommandPlanAudit  *audit,
  GError                           **error);
void goodix_enrollment_command_plan_free (GoodixEnrollmentCommandPlan *plan);

/* Observations never send data. Samples are accepted only for PRIMARY_B0. */
gboolean goodix_enrollment_command_plan_observe (
  GoodixEnrollmentCommandPlan *plan,
  GoodixEnrollmentEvent        event,
  const uint16_t              *samples,
  size_t                       sample_count,
  GError                     **error);

/* Returns the next typed intent. It never contains serializable body bytes. */
gboolean goodix_enrollment_command_plan_peek (
  const GoodixEnrollmentCommandPlan *plan,
  GoodixEnrollmentCommandIntent     *intent);

/* Records that the caller accepted the exact planned command event. This
 * function does not serialize or submit anything. */
gboolean goodix_enrollment_command_plan_commit (
  GoodixEnrollmentCommandPlan *plan,
  GoodixEnrollmentEvent        command_event,
  GError                     **error);

gboolean goodix_enrollment_command_plan_is_complete (
  const GoodixEnrollmentCommandPlan *plan);
gboolean goodix_enrollment_command_plan_is_failed (
  const GoodixEnrollmentCommandPlan *plan);
GoodixEnrollmentEvent goodix_enrollment_command_plan_get_expected_event (
  const GoodixEnrollmentCommandPlan *plan);

G_END_DECLS

#endif
