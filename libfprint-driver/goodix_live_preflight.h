/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_LIVE_PREFLIGHT_H
#define GOODIX_LIVE_PREFLIGHT_H

#include <glib.h>

#include "goodix_bb010002.h"
#include "goodix_config90.h"

G_BEGIN_DECLS

typedef enum
{
  GOODIX_LIVE_PREFLIGHT_REENTRY_A2 = 0,
  GOODIX_LIVE_PREFLIGHT_APP_A8,
  GOODIX_LIVE_PREFLIGHT_BB010002_E4,
  GOODIX_LIVE_PREFLIGHT_VALIDATOR_E4,
  GOODIX_LIVE_PREFLIGHT_COLD_A2,
  GOODIX_LIVE_PREFLIGHT_CHIP_82,
  GOODIX_LIVE_PREFLIGHT_OTP_A6,
  GOODIX_LIVE_PREFLIGHT_STOP,
  GOODIX_LIVE_PREFLIGHT_TERMINAL,
} GoodixLivePreflightPhase;

typedef struct
{
  guint16 chip_id;
  guint8 a2_response[3];
  guint8 chip_response[4];
  guint8 otp[GOODIX_CONFIG90_OTP_LENGTH];
  guint8 bb010002[GOODIX_BB010002_LENGTH];
  guint8 validator[32];
  guint8 config90[GOODIX_CONFIG90_LENGTH];
  GoodixConfig90Calibration calibration;
} GoodixLivePreflightEvidence;

typedef struct
{
  guint command_count;
  guint ack_count;
  guint typed_response_count;
  guint retry_count;
  guint persistent_write_count;
  gboolean exact_app;
  gboolean supported_chip_profile;
  gboolean otp_valid;
  gboolean bb010002_valid;
  gboolean config90_derived;
  gboolean complete;
} GoodixLivePreflightAudit;

typedef struct _GoodixLivePreflight GoodixLivePreflight;

GoodixLivePreflight *goodix_live_preflight_new (GoodixLivePreflightAudit *audit);
void goodix_live_preflight_free (GoodixLivePreflight *preflight);

/* Returns a newly-owned request only when the current phase is ready to be
 * submitted. NULL without an error means the phase is waiting for OUT or IN. */
GBytes *goodix_live_preflight_next_request (GoodixLivePreflight *preflight,
                                            GError             **error);
void goodix_live_preflight_out_complete (GoodixLivePreflight *preflight,
                                         const GError        *error);
gboolean goodix_live_preflight_handle_a0 (GoodixLivePreflight *preflight,
                                          GBytes              *frame,
                                          GError             **error);

GoodixLivePreflightPhase goodix_live_preflight_get_phase (
  const GoodixLivePreflight *preflight);
const GError *goodix_live_preflight_get_error (
  const GoodixLivePreflight *preflight);
gboolean goodix_live_preflight_copy_evidence (
  const GoodixLivePreflight *preflight,
  GoodixLivePreflightEvidence *evidence);
gboolean goodix_live_preflight_needs_receive (
  const GoodixLivePreflight *preflight);

G_DEFINE_AUTOPTR_CLEANUP_FUNC (GoodixLivePreflight,
                               goodix_live_preflight_free)

G_END_DECLS

#endif
