/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Host-only transactional composition: oracle + FDT state + inner body. */
#include "goodix_enrollment_lifecycle_adapter.h"

#include <string.h>

typedef enum
{
  GOODIX_ENROLLMENT_ADAPTER_ERROR_ARGUMENT,
  GOODIX_ENROLLMENT_ADAPTER_ERROR_STATE,
  GOODIX_ENROLLMENT_ADAPTER_ERROR_PAYLOAD,
  GOODIX_ENROLLMENT_ADAPTER_ERROR_TIMESTAMP,
  GOODIX_ENROLLMENT_ADAPTER_ERROR_PROTOCOL,
} GoodixEnrollmentAdapterError;

#define GOODIX_ENROLLMENT_ADAPTER_ERROR \
  (goodix_enrollment_adapter_error_quark ())

struct _GoodixEnrollmentLifecycleAdapter
{
  GoodixEnrollmentCommandPlan *plan;
  GoodixEnrollmentFdtState *fdt;
  GoodixEnrollmentTimestampFunc timestamp_ready;
  gpointer user_data;
  GoodixEnrollmentLifecycleAdapterAudit internal_audit;
  GoodixEnrollmentLifecycleAdapterAudit *audit;
  GoodixEnrollmentPreparedCommand cached;
  gboolean has_cached;
  gboolean failed;
};

static GQuark
goodix_enrollment_adapter_error_quark (void)
{
  return g_quark_from_static_string ("goodix-enrollment-lifecycle-adapter-error");
}

static gboolean
adapter_fail (GoodixEnrollmentLifecycleAdapter *adapter,
              GoodixEnrollmentAdapterError      code,
              const gchar                      *message,
              GError                          **error)
{
  if (adapter != NULL)
    {
      adapter->failed = TRUE;
      adapter->audit->failed = TRUE;
      adapter->audit->rejected_operation_count++;
      goodix_enrollment_prepared_command_clear (&adapter->cached);
      adapter->has_cached = FALSE;
    }
  if (error == NULL || *error == NULL)
    g_set_error_literal (error, GOODIX_ENROLLMENT_ADAPTER_ERROR, code,
                         message);
  return FALSE;
}

GoodixEnrollmentLifecycleAdapter *
goodix_enrollment_lifecycle_adapter_new (
  const GoodixEnrollmentModelConfig     *config,
  GoodixEnrollmentImageFunc              image_ready,
  GoodixEnrollmentTimestampFunc          timestamp_ready,
  gpointer                               user_data,
  GoodixEnrollmentLifecycleAdapterAudit *audit,
  GError                               **error)
{
  GoodixEnrollmentLifecycleAdapter *adapter;

  if (config == NULL || image_ready == NULL || timestamp_ready == NULL)
    {
      g_set_error_literal (error, GOODIX_ENROLLMENT_ADAPTER_ERROR,
                           GOODIX_ENROLLMENT_ADAPTER_ERROR_ARGUMENT,
                           "lifecycle adapter requires config and callbacks");
      return NULL;
    }
  adapter = g_new0 (GoodixEnrollmentLifecycleAdapter, 1);
  adapter->audit = audit != NULL ? audit : &adapter->internal_audit;
  *adapter->audit = (GoodixEnrollmentLifecycleAdapterAudit) { 0 };
  adapter->timestamp_ready = timestamp_ready;
  adapter->user_data = user_data;
  adapter->plan = goodix_enrollment_command_plan_new (
    config, image_ready, user_data, &adapter->audit->plan, error);
  if (adapter->plan == NULL)
    {
      g_free (adapter);
      return NULL;
    }
  adapter->fdt = goodix_enrollment_fdt_state_new (&adapter->audit->fdt);
  return adapter;
}

void
goodix_enrollment_lifecycle_adapter_free (
  GoodixEnrollmentLifecycleAdapter *adapter)
{
  if (adapter == NULL)
    return;
  goodix_enrollment_prepared_command_clear (&adapter->cached);
  goodix_enrollment_fdt_state_free (adapter->fdt);
  goodix_enrollment_command_plan_free (adapter->plan);
  g_free (adapter);
}

static gboolean
payload_contract_valid (GoodixEnrollmentEvent event,
                        const uint16_t        *samples,
                        size_t                 sample_count,
                        const guint8          *fdt_raw,
                        gsize                  fdt_raw_length)
{
  if (event == GOODIX_ENROLLMENT_EVENT_IRQ2 ||
      event == GOODIX_ENROLLMENT_EVENT_IRQ0200)
    return samples == NULL && sample_count == 0u && fdt_raw != NULL &&
           fdt_raw_length == GOODIX_ENROLLMENT_FDT_TABLE_LENGTH;
  if (event == GOODIX_ENROLLMENT_EVENT_PRIMARY_B0)
    return samples != NULL && sample_count > 0u && fdt_raw == NULL &&
           fdt_raw_length == 0u;
  return samples == NULL && sample_count == 0u && fdt_raw == NULL &&
         fdt_raw_length == 0u;
}

gboolean
goodix_enrollment_lifecycle_adapter_observe (
  GoodixEnrollmentLifecycleAdapter *adapter,
  GoodixEnrollmentEvent             event,
  const uint16_t                   *samples,
  size_t                            sample_count,
  const guint8                     *fdt_raw,
  gsize                             fdt_raw_length,
  GError                          **error)
{
  guint stage;

  if (adapter == NULL)
    return adapter_fail (NULL, GOODIX_ENROLLMENT_ADAPTER_ERROR_ARGUMENT,
                         "lifecycle adapter is absent", error);
  if (adapter->failed || adapter->has_cached ||
      goodix_enrollment_command_plan_is_complete (adapter->plan))
    return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_STATE,
                         "adapter is terminal or has an uncommitted command",
                         error);
  if (!payload_contract_valid (event, samples, sample_count,
                               fdt_raw, fdt_raw_length))
    return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_PAYLOAD,
                         "observation payload does not match its event", error);

  stage = adapter->audit->plan.pipeline.protocol.observed_primary_stage_count;
  if (event == GOODIX_ENROLLMENT_EVENT_IRQ2)
    {
      if (!goodix_enrollment_fdt_state_observe_irq2 (
            adapter->fdt, stage + 1u, fdt_raw, error))
        return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_PROTOCOL,
                             "IRQ2 FDT state rejected the observation", error);
    }
  else if (event == GOODIX_ENROLLMENT_EVENT_IRQ0200)
    {
      if (!goodix_enrollment_fdt_state_observe_irq0200 (
            adapter->fdt, stage, fdt_raw, error))
        return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_PROTOCOL,
                             "IRQ0200 FDT state rejected the observation", error);
    }
  if (!goodix_enrollment_command_plan_observe (
        adapter->plan, event, samples, sample_count, error))
    return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_PROTOCOL,
                         "command plan rejected the observation", error);
  return TRUE;
}

gboolean
goodix_enrollment_lifecycle_adapter_prepare (
  GoodixEnrollmentLifecycleAdapter *adapter,
  GoodixEnrollmentPreparedCommand  *prepared,
  GError                          **error)
{
  GoodixEnrollmentResolvedMaterial resolved = { 0 };
  guint16 timestamp = 0u;
  gboolean timestamp_available = FALSE;

  if (adapter == NULL || prepared == NULL)
    return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_ARGUMENT,
                         "adapter or prepared-command output is absent", error);
  goodix_enrollment_prepared_command_clear (prepared);
  if (adapter->failed ||
      goodix_enrollment_command_plan_is_complete (adapter->plan))
    return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_STATE,
                         "adapter is already terminal", error);
  if (adapter->has_cached)
    {
      *prepared = adapter->cached;
      adapter->audit->prepared_cache_hit_count++;
      return TRUE;
    }
  if (!goodix_enrollment_command_plan_peek (adapter->plan,
                                            &adapter->cached.intent))
    return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_STATE,
                         "no command is ready for preparation", error);
  if (adapter->cached.intent.body_class ==
      GOODIX_ENROLLMENT_BODY_FDT_TIMESTAMP_0801)
    {
      adapter->audit->timestamp_request_count++;
      if (!adapter->timestamp_ready (adapter->cached.intent.stage_index,
                                     adapter->cached.intent.purpose,
                                     &timestamp, adapter->user_data, error))
        return adapter_fail (adapter,
                             GOODIX_ENROLLMENT_ADAPTER_ERROR_TIMESTAMP,
                             "timestamp callback rejected the command", error);
      timestamp_available = TRUE;
    }
  if (!goodix_enrollment_fdt_state_resolve (
        adapter->fdt, &adapter->cached.intent, timestamp,
        timestamp_available, &resolved, error))
    return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_PROTOCOL,
                         "FDT state cannot resolve command material", error);
  if (!goodix_enrollment_command_body_build (
        &adapter->cached.intent,
        resolved.required ? &resolved.material : NULL,
        &adapter->cached.body, &adapter->audit->body, error))
    {
      goodix_enrollment_resolved_material_clear (&resolved);
      return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_PROTOCOL,
                           "inner command body construction failed", error);
    }
  goodix_enrollment_resolved_material_clear (&resolved);
  adapter->has_cached = TRUE;
  adapter->audit->prepared_command_count++;
  *prepared = adapter->cached;
  return TRUE;
}

gboolean
goodix_enrollment_lifecycle_adapter_commit (
  GoodixEnrollmentLifecycleAdapter *adapter,
  GoodixEnrollmentEvent             command_event,
  GError                          **error)
{
  if (adapter == NULL)
    return adapter_fail (NULL, GOODIX_ENROLLMENT_ADAPTER_ERROR_ARGUMENT,
                         "lifecycle adapter is absent", error);
  if (adapter->failed || !adapter->has_cached)
    return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_STATE,
                         "no prepared command is available for commit", error);
  if (command_event != adapter->cached.intent.event)
    return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_PROTOCOL,
                         "commit event differs from prepared command", error);
  if (!goodix_enrollment_command_plan_commit (adapter->plan, command_event,
                                              error))
    return adapter_fail (adapter, GOODIX_ENROLLMENT_ADAPTER_ERROR_PROTOCOL,
                         "command plan rejected prepared-command commit", error);
  adapter->audit->committed_prepared_command_count++;
  goodix_enrollment_prepared_command_clear (&adapter->cached);
  adapter->has_cached = FALSE;
  return TRUE;
}

gboolean
goodix_enrollment_lifecycle_adapter_is_complete (
  const GoodixEnrollmentLifecycleAdapter *adapter)
{
  return adapter != NULL && !adapter->failed && !adapter->has_cached &&
         goodix_enrollment_command_plan_is_complete (adapter->plan);
}

gboolean
goodix_enrollment_lifecycle_adapter_is_failed (
  const GoodixEnrollmentLifecycleAdapter *adapter)
{
  return adapter == NULL || adapter->failed ||
         goodix_enrollment_command_plan_is_failed (adapter->plan);
}

GoodixEnrollmentEvent
goodix_enrollment_lifecycle_adapter_get_expected_event (
  const GoodixEnrollmentLifecycleAdapter *adapter)
{
  return adapter != NULL && !adapter->failed ?
    goodix_enrollment_command_plan_get_expected_event (adapter->plan) :
    GOODIX_ENROLLMENT_EVENT_NONE;
}

void
goodix_enrollment_prepared_command_clear (
  GoodixEnrollmentPreparedCommand *prepared)
{
  if (prepared == NULL)
    return;
  memset (&prepared->intent, 0, sizeof prepared->intent);
  goodix_enrollment_command_body_clear (&prepared->body);
}
