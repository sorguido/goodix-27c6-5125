/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Independent host-only model derived from target-local metadata facts. */
#include "goodix_enrollment_model.h"

typedef enum
{
  GOODIX_ENROLLMENT_ERROR_ARGUMENT,
  GOODIX_ENROLLMENT_ERROR_STATE,
  GOODIX_ENROLLMENT_ERROR_PROTOCOL,
  GOODIX_ENROLLMENT_ERROR_STAGE,
} GoodixEnrollmentError;

#define GOODIX_ENROLLMENT_ERROR (goodix_enrollment_error_quark ())

struct _GoodixEnrollmentModel
{
  guint required_stage_count;
  guint observed_stage_count;
  guint completed_stage_count;
  GoodixEnrollmentEvent expected;
  GoodixEnrollmentTransition transition;
  GoodixEnrollmentStageFunc stage_ready;
  gpointer user_data;
  GoodixEnrollmentModelAudit *audit;
  gboolean complete;
  gboolean failed;
  gboolean repeated_after_auxiliary;
  gboolean first_nav_seen;
  gboolean defer_terminal_stage_delivery;
  gboolean terminal_stage_pending;
};

static GQuark
goodix_enrollment_error_quark (void)
{
  return g_quark_from_static_string ("goodix-enrollment-model-error");
}

static gboolean
model_fail (GoodixEnrollmentModel *model,
            GoodixEnrollmentError  code,
            GoodixEnrollmentEvent  observed,
            GError               **error)
{
  GoodixEnrollmentEvent expected = model->expected;

  model->failed = TRUE;
  model->expected = GOODIX_ENROLLMENT_EVENT_NONE;
  if (model->audit != NULL)
    {
      model->audit->failed = TRUE;
      model->audit->unexpected_event_count++;
    }
  g_set_error (error, GOODIX_ENROLLMENT_ERROR, code,
               "unexpected enrollment event: expected %s, observed %s",
               goodix_enrollment_event_name (expected),
               goodix_enrollment_event_name (observed));
  return FALSE;
}

GoodixEnrollmentModel *
goodix_enrollment_model_new (const GoodixEnrollmentModelConfig *config,
                             GoodixEnrollmentStageFunc          stage_ready,
                             gpointer                           user_data,
                             GoodixEnrollmentModelAudit        *audit,
                             GError                           **error)
{
  GoodixEnrollmentModel *model;

  /* The target-observed shape has a distinct first transition followed by a
   * repeated/terminal transition, so fewer than two stages cannot instantiate
   * this profile without inventing an unobserved single-stage shape. */
  if (config == NULL || config->required_stage_count < 2u ||
      stage_ready == NULL)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_ERROR,
                           GOODIX_ENROLLMENT_ERROR_ARGUMENT,
                           "enrollment model requires at least two stages and a callback");
      return NULL;
    }

  model = g_new0 (GoodixEnrollmentModel, 1);
  model->required_stage_count = config->required_stage_count;
  model->defer_terminal_stage_delivery =
    config->defer_terminal_stage_delivery;
  model->expected = GOODIX_ENROLLMENT_EVENT_IRQ2;
  model->stage_ready = stage_ready;
  model->user_data = user_data;
  model->audit = audit;
  if (audit != NULL)
    {
      *audit = (GoodixEnrollmentModelAudit) { 0 };
      audit->configured_required_stage_count = config->required_stage_count;
      audit->configured_defer_terminal_stage_delivery =
        config->defer_terminal_stage_delivery;
    }
  return model;
}

void
goodix_enrollment_model_free (GoodixEnrollmentModel *model)
{
  g_free (model);
}

static void
expect (GoodixEnrollmentModel *model,
        GoodixEnrollmentEvent  event)
{
  model->expected = event;
}

static gboolean
deliver_stage (GoodixEnrollmentModel *model,
               guint                  stage_index,
               GError               **error)
{
  g_autoptr(GError) callback_error = NULL;

  if (!model->stage_ready (model, stage_index, model->user_data,
                           &callback_error))
    {
      model->failed = TRUE;
      model->expected = GOODIX_ENROLLMENT_EVENT_NONE;
      if (model->audit != NULL)
        model->audit->failed = TRUE;
      if (callback_error == NULL)
        callback_error = g_error_new_literal (
          GOODIX_ENROLLMENT_ERROR, GOODIX_ENROLLMENT_ERROR_STAGE,
          "enrollment stage callback rejected without an error");
      g_propagate_error (error, g_steal_pointer (&callback_error));
      return FALSE;
    }
  model->completed_stage_count++;
  if (model->audit != NULL)
    {
      model->audit->completed_stage_count = model->completed_stage_count;
      model->audit->libfprint_stage_report_count++;
    }
  return TRUE;
}

static gboolean
finish (GoodixEnrollmentModel *model,
        GError               **error)
{
  if (model->terminal_stage_pending)
    {
      if (!deliver_stage (model, model->observed_stage_count, error))
        return FALSE;
      model->terminal_stage_pending = FALSE;
    }
  model->complete = TRUE;
  model->transition = GOODIX_ENROLLMENT_TRANSITION_TERMINAL;
  model->expected = GOODIX_ENROLLMENT_EVENT_NONE;
  if (model->audit != NULL)
    {
      model->audit->terminal_transition_count++;
      model->audit->complete = TRUE;
    }
  return TRUE;
}

gboolean
goodix_enrollment_model_feed (GoodixEnrollmentModel *model,
                              GoodixEnrollmentEvent  event,
                              GError               **error)
{
  if (model == NULL)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_ERROR,
                           GOODIX_ENROLLMENT_ERROR_ARGUMENT,
                           "enrollment model is absent");
      return FALSE;
    }
  if (model->complete || model->failed)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_ERROR,
                           GOODIX_ENROLLMENT_ERROR_STATE,
                           "enrollment model is already terminal");
      return FALSE;
    }
  if (event != model->expected)
    return model_fail (model, GOODIX_ENROLLMENT_ERROR_PROTOCOL,
                       event, error);

  switch (event)
    {
    case GOODIX_ENROLLMENT_EVENT_IRQ2:
      model->transition = GOODIX_ENROLLMENT_TRANSITION_NONE;
      expect (model, GOODIX_ENROLLMENT_EVENT_COMMAND_22);
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_22:
      expect (model, GOODIX_ENROLLMENT_EVENT_ACK_22);
      break;
    case GOODIX_ENROLLMENT_EVENT_ACK_22:
      expect (model, GOODIX_ENROLLMENT_EVENT_PRIMARY_B0);
      break;
    case GOODIX_ENROLLMENT_EVENT_PRIMARY_B0:
      if (model->observed_stage_count >= model->required_stage_count)
        {
          return model_fail (model, GOODIX_ENROLLMENT_ERROR_PROTOCOL,
                             event, error);
        }
      model->observed_stage_count++;
      if (model->audit != NULL)
        {
          model->audit->observed_primary_stage_count =
            model->observed_stage_count;
          model->audit->primary_b0_count++;
        }
      model->transition = model->observed_stage_count == 1u ?
        GOODIX_ENROLLMENT_TRANSITION_FIRST_NAV :
        (model->observed_stage_count == model->required_stage_count ?
         GOODIX_ENROLLMENT_TRANSITION_TERMINAL :
         GOODIX_ENROLLMENT_TRANSITION_REPEATED_REARM);
      if (model->transition == GOODIX_ENROLLMENT_TRANSITION_TERMINAL &&
          model->defer_terminal_stage_delivery)
        model->terminal_stage_pending = TRUE;
      else if (!deliver_stage (model, model->observed_stage_count, error))
        return FALSE;
      expect (model, GOODIX_ENROLLMENT_EVENT_COMMAND_34);
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_34:
      expect (model, GOODIX_ENROLLMENT_EVENT_ACK_34);
      break;
    case GOODIX_ENROLLMENT_EVENT_ACK_34:
      if (model->transition == GOODIX_ENROLLMENT_TRANSITION_FIRST_NAV ||
          model->repeated_after_auxiliary)
        expect (model, GOODIX_ENROLLMENT_EVENT_IRQ0200);
      else
        expect (model, GOODIX_ENROLLMENT_EVENT_COMMAND_36);
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_36:
      expect (model, GOODIX_ENROLLMENT_EVENT_ACK_36);
      break;
    case GOODIX_ENROLLMENT_EVENT_ACK_36:
      expect (model, GOODIX_ENROLLMENT_EVENT_IRQ0100);
      break;
    case GOODIX_ENROLLMENT_EVENT_IRQ0100:
      expect (model, GOODIX_ENROLLMENT_EVENT_COMMAND_20);
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_20:
      expect (model, GOODIX_ENROLLMENT_EVENT_ACK_20);
      break;
    case GOODIX_ENROLLMENT_EVENT_ACK_20:
      expect (model, GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0);
      break;
    case GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0:
      if (model->audit != NULL)
        model->audit->auxiliary_b0_count++;
      if (model->transition == GOODIX_ENROLLMENT_TRANSITION_FIRST_NAV)
        expect (model, GOODIX_ENROLLMENT_EVENT_COMMAND_32);
      else
        {
          model->repeated_after_auxiliary = TRUE;
          expect (model, GOODIX_ENROLLMENT_EVENT_COMMAND_34);
        }
      break;
    case GOODIX_ENROLLMENT_EVENT_IRQ0200:
      model->repeated_after_auxiliary = FALSE;
      if (model->transition == GOODIX_ENROLLMENT_TRANSITION_FIRST_NAV)
        expect (model, GOODIX_ENROLLMENT_EVENT_COMMAND_20);
      else if (model->transition == GOODIX_ENROLLMENT_TRANSITION_TERMINAL)
        {
          if (!finish (model, error))
            return FALSE;
        }
      else
        expect (model, GOODIX_ENROLLMENT_EVENT_COMMAND_32);
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_32:
      expect (model, GOODIX_ENROLLMENT_EVENT_ACK_32);
      break;
    case GOODIX_ENROLLMENT_EVENT_ACK_32:
      if (model->transition == GOODIX_ENROLLMENT_TRANSITION_FIRST_NAV &&
          !model->first_nav_seen)
        expect (model, GOODIX_ENROLLMENT_EVENT_COMMAND_50);
      else
        {
          if (model->audit != NULL)
            {
              if (model->transition == GOODIX_ENROLLMENT_TRANSITION_FIRST_NAV)
                model->audit->first_nav_transition_count++;
              else
                model->audit->repeated_rearm_transition_count++;
              model->audit->inter_stage_rearm_count++;
            }
          expect (model, GOODIX_ENROLLMENT_EVENT_IRQ2);
        }
      break;
    case GOODIX_ENROLLMENT_EVENT_COMMAND_50:
      expect (model, GOODIX_ENROLLMENT_EVENT_ACK_50);
      break;
    case GOODIX_ENROLLMENT_EVENT_ACK_50:
      expect (model, GOODIX_ENROLLMENT_EVENT_NAV);
      break;
    case GOODIX_ENROLLMENT_EVENT_NAV:
      model->first_nav_seen = TRUE;
      expect (model, GOODIX_ENROLLMENT_EVENT_COMMAND_32);
      break;
    case GOODIX_ENROLLMENT_EVENT_NONE:
      return model_fail (model, GOODIX_ENROLLMENT_ERROR_PROTOCOL,
                         event, error);
    }
  return TRUE;
}

GoodixEnrollmentEvent
goodix_enrollment_model_get_expected_event (const GoodixEnrollmentModel *model)
{
  return model != NULL ? model->expected : GOODIX_ENROLLMENT_EVENT_NONE;
}

GoodixEnrollmentTransition
goodix_enrollment_model_get_transition (const GoodixEnrollmentModel *model)
{
  return model != NULL ? model->transition :
                         GOODIX_ENROLLMENT_TRANSITION_NONE;
}

guint
goodix_enrollment_model_get_completed_stage_count (
  const GoodixEnrollmentModel *model)
{
  return model != NULL ? model->completed_stage_count : 0u;
}

gboolean
goodix_enrollment_model_is_complete (const GoodixEnrollmentModel *model)
{
  return model != NULL && model->complete;
}

gboolean
goodix_enrollment_model_is_failed (const GoodixEnrollmentModel *model)
{
  return model == NULL || model->failed;
}

const gchar *
goodix_enrollment_event_name (GoodixEnrollmentEvent event)
{
  static const gchar *const names[] = {
    "NONE", "IRQ2", "COMMAND_22", "ACK_22", "PRIMARY_B0",
    "COMMAND_34", "ACK_34", "IRQ0200", "COMMAND_20", "ACK_20",
    "AUXILIARY_B0", "COMMAND_32", "ACK_32", "COMMAND_50", "ACK_50",
    "NAV", "COMMAND_36", "ACK_36", "IRQ0100"
  };
  return (guint) event < G_N_ELEMENTS (names) ? names[event] : "UNKNOWN";
}

const gchar *
goodix_enrollment_transition_name (GoodixEnrollmentTransition transition)
{
  static const gchar *const names[] = {
    "NONE", "FIRST_NAV", "REPEATED_REARM", "TERMINAL"
  };
  return (guint) transition < G_N_ELEMENTS (names) ? names[transition] :
                                                    "UNKNOWN";
}
