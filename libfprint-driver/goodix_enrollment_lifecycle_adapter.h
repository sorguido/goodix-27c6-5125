/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_LIFECYCLE_ADAPTER_H
#define GOODIX_ENROLLMENT_LIFECYCLE_ADAPTER_H

#include "goodix_enrollment_fdt_state.h"

G_BEGIN_DECLS

typedef struct _GoodixEnrollmentLifecycleAdapter GoodixEnrollmentLifecycleAdapter;

typedef gboolean (*GoodixEnrollmentTimestampFunc) (
  guint                            stage_index,
  GoodixEnrollmentCommandPurpose   purpose,
  guint16                         *timestamp,
  gpointer                         user_data,
  GError                         **error);

typedef struct
{
  GoodixEnrollmentCommandIntent intent;
  GoodixEnrollmentCommandBody body;
} GoodixEnrollmentPreparedCommand;

typedef struct
{
  GoodixEnrollmentCommandPlanAudit plan;
  GoodixEnrollmentFdtStateAudit fdt;
  GoodixEnrollmentCommandBodyAudit body;
  guint prepared_command_count;
  guint committed_prepared_command_count;
  guint prepared_cache_hit_count;
  guint timestamp_request_count;
  guint rejected_operation_count;
  guint retry_count;
  guint a0_frame_build_count;
  guint submit_count;
  gboolean failed;
} GoodixEnrollmentLifecycleAdapterAudit;

GoodixEnrollmentLifecycleAdapter *goodix_enrollment_lifecycle_adapter_new (
  const GoodixEnrollmentModelConfig     *config,
  GoodixEnrollmentImageFunc              image_ready,
  GoodixEnrollmentTimestampFunc          timestamp_ready,
  gpointer                               user_data,
  GoodixEnrollmentLifecycleAdapterAudit *audit,
  GError                               **error);
void goodix_enrollment_lifecycle_adapter_free (
  GoodixEnrollmentLifecycleAdapter *adapter);

/* Observations are host-side inputs only.  IRQ2/IRQ0200 require exactly the
 * 12-byte FDT source; PRIMARY_B0 requires only canonical raster samples; all
 * other observations reject both payloads. */
gboolean goodix_enrollment_lifecycle_adapter_observe (
  GoodixEnrollmentLifecycleAdapter *adapter,
  GoodixEnrollmentEvent             event,
  const uint16_t                   *samples,
  size_t                            sample_count,
  const guint8                     *fdt_raw,
  gsize                             fdt_raw_length,
  GError                          **error);

/* Resolves and caches the exact next typed intent plus inner body. Repeated
 * peeks return the same cached bytes and do not request another timestamp. */
gboolean goodix_enrollment_lifecycle_adapter_prepare (
  GoodixEnrollmentLifecycleAdapter *adapter,
  GoodixEnrollmentPreparedCommand  *prepared,
  GError                          **error);

/* Commits only the event represented by the cached prepared command.  No
 * serialization or transport occurs in this adapter. */
gboolean goodix_enrollment_lifecycle_adapter_commit (
  GoodixEnrollmentLifecycleAdapter *adapter,
  GoodixEnrollmentEvent             command_event,
  GError                          **error);

gboolean goodix_enrollment_lifecycle_adapter_is_complete (
  const GoodixEnrollmentLifecycleAdapter *adapter);
gboolean goodix_enrollment_lifecycle_adapter_is_failed (
  const GoodixEnrollmentLifecycleAdapter *adapter);
void goodix_enrollment_prepared_command_clear (
  GoodixEnrollmentPreparedCommand *prepared);

G_END_DECLS

#endif
