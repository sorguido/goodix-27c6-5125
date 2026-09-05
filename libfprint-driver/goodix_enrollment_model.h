/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_MODEL_H
#define GOODIX_ENROLLMENT_MODEL_H

#include <glib.h>

G_BEGIN_DECLS

/* Metadata-only observations accepted by the host-only enrollment oracle.
 * PRIMARY_B0 is the image-bearing stage boundary exposed to libfprint.
 * AUXILIARY_B0 is the encrypted B0 observed after 0x20.  Its stable position
 * makes it protocol-internal in this model; its possible quality, template or
 * NBIS relevance is deliberately left undetermined. */
typedef enum
{
  GOODIX_ENROLLMENT_EVENT_NONE = 0,
  GOODIX_ENROLLMENT_EVENT_IRQ2,
  GOODIX_ENROLLMENT_EVENT_COMMAND_22,
  GOODIX_ENROLLMENT_EVENT_ACK_22,
  GOODIX_ENROLLMENT_EVENT_PRIMARY_B0,
  GOODIX_ENROLLMENT_EVENT_COMMAND_34,
  GOODIX_ENROLLMENT_EVENT_ACK_34,
  GOODIX_ENROLLMENT_EVENT_IRQ0200,
  GOODIX_ENROLLMENT_EVENT_COMMAND_20,
  GOODIX_ENROLLMENT_EVENT_ACK_20,
  GOODIX_ENROLLMENT_EVENT_AUXILIARY_B0,
  GOODIX_ENROLLMENT_EVENT_COMMAND_32,
  GOODIX_ENROLLMENT_EVENT_ACK_32,
  GOODIX_ENROLLMENT_EVENT_COMMAND_50,
  GOODIX_ENROLLMENT_EVENT_ACK_50,
  GOODIX_ENROLLMENT_EVENT_NAV,
  GOODIX_ENROLLMENT_EVENT_COMMAND_36,
  GOODIX_ENROLLMENT_EVENT_ACK_36,
  GOODIX_ENROLLMENT_EVENT_IRQ0100,
} GoodixEnrollmentEvent;

typedef enum
{
  GOODIX_ENROLLMENT_TRANSITION_NONE = 0,
  GOODIX_ENROLLMENT_TRANSITION_FIRST_NAV,
  GOODIX_ENROLLMENT_TRANSITION_REPEATED_REARM,
  GOODIX_ENROLLMENT_TRANSITION_TERMINAL,
} GoodixEnrollmentTransition;

typedef struct
{
  /* Target/profile input, not a universal OEM constant.  The observed
   * ATTEMPT02 value is 21; the model intentionally accepts other values. */
  guint required_stage_count;
  /* FpImageDevice may complete enrollment as soon as final extraction ends.
   * Defer the final stage callback until terminal IRQ0200 so the caller can
   * immediately report finger-up before that asynchronous completion. */
  gboolean defer_terminal_stage_delivery;
} GoodixEnrollmentModelConfig;

typedef struct
{
  guint configured_required_stage_count;
  gboolean configured_defer_terminal_stage_delivery;
  guint observed_primary_stage_count;
  guint completed_stage_count;
  guint primary_b0_count;
  guint auxiliary_b0_count;
  guint libfprint_stage_report_count;
  guint first_nav_transition_count;
  guint repeated_rearm_transition_count;
  guint terminal_transition_count;
  guint inter_stage_rearm_count;
  guint unexpected_event_count;
  gboolean complete;
  gboolean failed;
} GoodixEnrollmentModelAudit;

typedef struct _GoodixEnrollmentModel GoodixEnrollmentModel;

typedef gboolean (*GoodixEnrollmentStageFunc) (
  GoodixEnrollmentModel *model,
  guint                  stage_index,
  gpointer               user_data,
  GError               **error);

GoodixEnrollmentModel *goodix_enrollment_model_new (
  const GoodixEnrollmentModelConfig *config,
  GoodixEnrollmentStageFunc          stage_ready,
  gpointer                           user_data,
  GoodixEnrollmentModelAudit        *audit,
  GError                           **error);
void goodix_enrollment_model_free (GoodixEnrollmentModel *model);
gboolean goodix_enrollment_model_feed (GoodixEnrollmentModel *model,
                                       GoodixEnrollmentEvent  event,
                                       GError               **error);
GoodixEnrollmentEvent goodix_enrollment_model_get_expected_event (
  const GoodixEnrollmentModel *model);
GoodixEnrollmentTransition goodix_enrollment_model_get_transition (
  const GoodixEnrollmentModel *model);
guint goodix_enrollment_model_get_completed_stage_count (
  const GoodixEnrollmentModel *model);
gboolean goodix_enrollment_model_is_complete (
  const GoodixEnrollmentModel *model);
gboolean goodix_enrollment_model_is_failed (
  const GoodixEnrollmentModel *model);
const gchar *goodix_enrollment_event_name (GoodixEnrollmentEvent event);
const gchar *goodix_enrollment_transition_name (
  GoodixEnrollmentTransition transition);

G_END_DECLS

#endif
