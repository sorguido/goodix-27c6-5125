/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Zero-sender command intent layer derived from ATTEMPT02 metadata. */
#include "goodix_enrollment_command_plan.h"

typedef enum
{
  GOODIX_ENROLLMENT_PLAN_ERROR_ARGUMENT,
  GOODIX_ENROLLMENT_PLAN_ERROR_STATE,
  GOODIX_ENROLLMENT_PLAN_ERROR_PROTOCOL,
} GoodixEnrollmentPlanError;

#define GOODIX_ENROLLMENT_PLAN_ERROR (goodix_enrollment_plan_error_quark ())

struct _GoodixEnrollmentCommandPlan
{
  GoodixEnrollmentPipeline *pipeline;
  GoodixEnrollmentCommandPlanAudit internal_audit;
  GoodixEnrollmentCommandPlanAudit *audit;
  GoodixEnrollmentEvent last_event;
  guint required_stage_count;
  gboolean failed;
};

static GQuark
goodix_enrollment_plan_error_quark (void)
{
  return g_quark_from_static_string ("goodix-enrollment-command-plan-error");
}

static gboolean
is_command_event (GoodixEnrollmentEvent event)
{
  return event == GOODIX_ENROLLMENT_EVENT_COMMAND_20 ||
         event == GOODIX_ENROLLMENT_EVENT_COMMAND_22 ||
         event == GOODIX_ENROLLMENT_EVENT_COMMAND_32 ||
         event == GOODIX_ENROLLMENT_EVENT_COMMAND_34 ||
         event == GOODIX_ENROLLMENT_EVENT_COMMAND_36 ||
         event == GOODIX_ENROLLMENT_EVENT_COMMAND_50;
}

static gboolean
plan_fail (GoodixEnrollmentCommandPlan *plan,
           GoodixEnrollmentPlanError    code,
           const gchar                 *message,
           GError                     **error)
{
  if (plan != NULL)
    {
      plan->failed = TRUE;
      plan->audit->failed = TRUE;
    }
  g_set_error_literal (error, GOODIX_ENROLLMENT_PLAN_ERROR, code, message);
  return FALSE;
}

GoodixEnrollmentCommandPlan *
goodix_enrollment_command_plan_new (
  const GoodixEnrollmentModelConfig *config,
  GoodixEnrollmentImageFunc          image_ready,
  gpointer                           user_data,
  GoodixEnrollmentCommandPlanAudit  *audit,
  GError                           **error)
{
  GoodixEnrollmentCommandPlan *plan;

  if (config == NULL || image_ready == NULL)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_PLAN_ERROR,
                           GOODIX_ENROLLMENT_PLAN_ERROR_ARGUMENT,
                           "enrollment command plan requires config and image callback");
      return NULL;
    }
  plan = g_new0 (GoodixEnrollmentCommandPlan, 1);
  plan->audit = audit != NULL ? audit : &plan->internal_audit;
  plan->required_stage_count = config->required_stage_count;
  *plan->audit = (GoodixEnrollmentCommandPlanAudit) { 0 };
  plan->pipeline = goodix_enrollment_pipeline_new (
    config, image_ready, user_data, &plan->audit->pipeline, error);
  if (plan->pipeline == NULL)
    {
      g_free (plan);
      return NULL;
    }
  return plan;
}

void
goodix_enrollment_command_plan_free (GoodixEnrollmentCommandPlan *plan)
{
  if (plan == NULL)
    return;
  goodix_enrollment_pipeline_free (plan->pipeline);
  g_free (plan);
}

gboolean
goodix_enrollment_command_plan_observe (GoodixEnrollmentCommandPlan *plan,
                                        GoodixEnrollmentEvent        event,
                                        const uint16_t              *samples,
                                        size_t                       sample_count,
                                        GError                     **error)
{
  if (plan == NULL)
    return plan_fail (NULL, GOODIX_ENROLLMENT_PLAN_ERROR_ARGUMENT,
                      "enrollment command plan is absent", error);
  if (plan->failed || goodix_enrollment_pipeline_is_complete (plan->pipeline))
    return plan_fail (plan, GOODIX_ENROLLMENT_PLAN_ERROR_STATE,
                      "enrollment command plan is already terminal", error);
  if (is_command_event (event) || event == GOODIX_ENROLLMENT_EVENT_NONE)
    return plan_fail (plan, GOODIX_ENROLLMENT_PLAN_ERROR_ARGUMENT,
                      "command events must use command-plan commit", error);
  if (!goodix_enrollment_pipeline_feed (plan->pipeline, event, samples,
                                        sample_count, error))
    {
      plan->failed = TRUE;
      plan->audit->failed = TRUE;
      return FALSE;
    }
  plan->last_event = event;
  return TRUE;
}

gboolean
goodix_enrollment_command_plan_peek (const GoodixEnrollmentCommandPlan *plan,
                                     GoodixEnrollmentCommandIntent     *intent)
{
  GoodixEnrollmentEvent event;
  GoodixEnrollmentTransition transition;
  guint observed;

  if (plan == NULL || intent == NULL || plan->failed ||
      goodix_enrollment_pipeline_is_complete (plan->pipeline))
    return FALSE;
  event = goodix_enrollment_pipeline_get_expected_event (plan->pipeline);
  if (!is_command_event (event))
    return FALSE;

  *intent = (GoodixEnrollmentCommandIntent) { 0 };
  intent->event = event;
  intent->wire_frame_serializable = FALSE;
  observed = plan->audit->pipeline.protocol.observed_primary_stage_count;
  intent->stage_index = event == GOODIX_ENROLLMENT_EVENT_COMMAND_22 ?
    observed + 1u : observed;
  transition = observed == 1u ? GOODIX_ENROLLMENT_TRANSITION_FIRST_NAV :
    (observed == plan->required_stage_count ?
     GOODIX_ENROLLMENT_TRANSITION_TERMINAL :
     GOODIX_ENROLLMENT_TRANSITION_REPEATED_REARM);

  switch (event)
    {
    case GOODIX_ENROLLMENT_EVENT_COMMAND_20:
      intent->control = 0x20;
      intent->purpose = GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUXILIARY_TRANSITION;
      intent->body_class = GOODIX_ENROLLMENT_BODY_SIMPLE_01_00;
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_22:
      intent->control = 0x22;
      intent->purpose = GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRIMARY_ACQUIRE;
      intent->body_class = GOODIX_ENROLLMENT_BODY_SIMPLE_01_00;
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_32:
      intent->control = 0x32;
      intent->purpose = transition == GOODIX_ENROLLMENT_TRANSITION_FIRST_NAV &&
                        plan->audit->command_50_count == 0u ?
        GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV_PREPARE :
        GOODIX_ENROLLMENT_COMMAND_PURPOSE_INTER_STAGE_REARM;
      intent->body_class = GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801;
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_34:
      intent->control = 0x34;
      intent->purpose = transition != GOODIX_ENROLLMENT_TRANSITION_FIRST_NAV &&
                        plan->last_event == GOODIX_ENROLLMENT_EVENT_PRIMARY_B0 ?
        GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRE_AUX_FDT :
        GOODIX_ENROLLMENT_COMMAND_PURPOSE_FINGER_UP;
      intent->body_class = GOODIX_ENROLLMENT_BODY_FDT_0A01;
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_36:
      intent->control = 0x36;
      intent->purpose = GOODIX_ENROLLMENT_COMMAND_PURPOSE_AUX_FDT_SCAN;
      intent->body_class = GOODIX_ENROLLMENT_BODY_FDT_0901;
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_50:
      intent->control = 0x50;
      intent->purpose = GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV;
      intent->body_class = GOODIX_ENROLLMENT_BODY_SIMPLE_01_00;
      break;
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
      g_assert_not_reached ();
    }
  return TRUE;
}

static void
record_intent (GoodixEnrollmentCommandPlan       *plan,
               const GoodixEnrollmentCommandIntent *intent)
{
  plan->audit->committed_command_count++;
  switch (intent->control)
    {
    case 0x20: plan->audit->command_20_count++; break;
    case 0x22: plan->audit->command_22_count++; break;
    case 0x32: plan->audit->command_32_count++; break;
    case 0x34: plan->audit->command_34_count++; break;
    case 0x36: plan->audit->command_36_count++; break;
    case 0x50: plan->audit->command_50_count++; break;
    default: g_assert_not_reached ();
    }
  if (intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_PRE_AUX_FDT)
    plan->audit->pre_aux_fdt_count++;
  else if (intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_FINGER_UP)
    plan->audit->finger_up_count++;
  else if (intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_FIRST_NAV_PREPARE)
    plan->audit->first_nav_prepare_count++;
  else if (intent->purpose == GOODIX_ENROLLMENT_COMMAND_PURPOSE_INTER_STAGE_REARM)
    plan->audit->inter_stage_rearm_count++;
}

gboolean
goodix_enrollment_command_plan_commit (GoodixEnrollmentCommandPlan *plan,
                                       GoodixEnrollmentEvent        command_event,
                                       GError                     **error)
{
  GoodixEnrollmentCommandIntent intent;

  if (plan == NULL)
    return plan_fail (NULL, GOODIX_ENROLLMENT_PLAN_ERROR_ARGUMENT,
                      "enrollment command plan is absent", error);
  if (!goodix_enrollment_command_plan_peek (plan, &intent))
    return plan_fail (plan, GOODIX_ENROLLMENT_PLAN_ERROR_STATE,
                      "no enrollment command is currently planned", error);
  if (command_event != intent.event)
    {
      (void) goodix_enrollment_pipeline_feed (plan->pipeline, command_event,
                                              NULL, 0u, NULL);
      return plan_fail (plan, GOODIX_ENROLLMENT_PLAN_ERROR_PROTOCOL,
                        "committed command differs from the planned event",
                        error);
    }
  if (!goodix_enrollment_pipeline_feed (plan->pipeline, command_event,
                                        NULL, 0u, error))
    {
      plan->failed = TRUE;
      plan->audit->failed = TRUE;
      return FALSE;
    }
  record_intent (plan, &intent);
  plan->last_event = command_event;
  return TRUE;
}

gboolean
goodix_enrollment_command_plan_is_complete (
  const GoodixEnrollmentCommandPlan *plan)
{
  return plan != NULL && !plan->failed &&
         goodix_enrollment_pipeline_is_complete (plan->pipeline);
}

gboolean
goodix_enrollment_command_plan_is_failed (
  const GoodixEnrollmentCommandPlan *plan)
{
  return plan == NULL || plan->failed ||
         goodix_enrollment_pipeline_is_failed (plan->pipeline);
}

GoodixEnrollmentEvent
goodix_enrollment_command_plan_get_expected_event (
  const GoodixEnrollmentCommandPlan *plan)
{
  return plan != NULL && !plan->failed ?
    goodix_enrollment_pipeline_get_expected_event (plan->pipeline) :
    GOODIX_ENROLLMENT_EVENT_NONE;
}
