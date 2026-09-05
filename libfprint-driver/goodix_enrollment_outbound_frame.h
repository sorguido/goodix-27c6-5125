/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_ENROLLMENT_OUTBOUND_FRAME_H
#define GOODIX_ENROLLMENT_OUTBOUND_FRAME_H

#include "goodix_a0_protocol.h"
#include "goodix_enrollment_lifecycle_adapter.h"

G_BEGIN_DECLS

#define GOODIX_ENROLLMENT_FIXED64_LENGTH 64u

typedef struct
{
  guint frame_build_count;
  guint command_20_count;
  guint command_22_count;
  guint command_32_count;
  guint command_34_count;
  guint command_36_count;
  guint command_50_count;
  guint rejected_prepared_count;
  guint persistent_family_count;
  guint retry_count;
  guint submit_count;
} GoodixEnrollmentOutboundFrameAudit;

/* Produces one zero-padded fixed64 frame from an exact prepared command.
 * This module has no backend and cannot submit the returned bytes. */
GBytes *goodix_enrollment_outbound_frame_build (
  const GoodixEnrollmentPreparedCommand *prepared,
  GoodixEnrollmentOutboundFrameAudit    *audit,
  GError                               **error);

G_END_DECLS

#endif
