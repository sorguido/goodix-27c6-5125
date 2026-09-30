/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GOODIX_PAIRING_PROVISION_H
#define GOODIX_PAIRING_PROVISION_H

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_PAIRING_PROVISION_BB010002_LENGTH 332u
#define GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH 102u
#define GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH 32u
#define GOODIX_PAIRING_PROVISION_E0_BODY_LENGTH 452u
#define GOODIX_PAIRING_PROVISION_E0_FRAME_LENGTH 460u

typedef enum
{
  GOODIX_PAIRING_PROVISION_WAITING = 0,
  GOODIX_PAIRING_PROVISION_ACCEPTED,
  GOODIX_PAIRING_PROVISION_REJECTED,
} GoodixPairingProvisionTerminal;

typedef enum
{
  GOODIX_PAIRING_PROVISION_ERROR_ARGUMENT,
  GOODIX_PAIRING_PROVISION_ERROR_STATE,
  GOODIX_PAIRING_PROVISION_ERROR_PROTOCOL,
  GOODIX_PAIRING_PROVISION_ERROR_PROOF,
} GoodixPairingProvisionError;

typedef struct
{
  guint logical_e0_count;
  guint ack_count;
  guint completion_count;
  guint retry_count;
  guint persistent_write_count;
  guint8 ack_status;
  guint8 result_control;
  guint8 result_code;
  gboolean bb010002_unchanged;
  gboolean validator_match;
  gboolean tls_proven;
} GoodixPairingProvisionAudit;

typedef struct _GoodixPairingProvision GoodixPairingProvision;

#define GOODIX_PAIRING_PROVISION_ERROR (goodix_pairing_provision_error_quark ())

GQuark goodix_pairing_provision_error_quark (void);

GoodixPairingProvision *goodix_pairing_provision_new (
  const guint8                    bb010002[GOODIX_PAIRING_PROVISION_BB010002_LENGTH],
  gsize                           bb010002_length,
  const guint8                    envelope[GOODIX_PAIRING_PROVISION_ENVELOPE_LENGTH],
  gsize                           envelope_length,
  const guint8                    validator[GOODIX_PAIRING_PROVISION_VALIDATOR_LENGTH],
  gsize                           validator_length,
  GoodixPairingProvisionAudit    *audit,
  GError                        **error);
void goodix_pairing_provision_free (GoodixPairingProvision *provision);

/* Returns the only E0 frame this transaction may submit.  A second call fails
 * closed and never returns another frame. */
GBytes *goodix_pairing_provision_begin_e0 (GoodixPairingProvision *provision,
                                           GError                **error);

/* Feed one complete A0 frame from the exclusive E0 response epoch. */
gboolean goodix_pairing_provision_handle_a0 (
  GoodixPairingProvision *provision,
  GBytes                 *frame,
  GError                **error);

/* Independent post-write proofs.  Raw protected material is retained only by
 * the transaction object and is cleansed on free. */
gboolean goodix_pairing_provision_check_readback (
  GoodixPairingProvision *provision,
  const guint8           *bb010002,
  gsize                   bb010002_length,
  const guint8           *validator,
  gsize                   validator_length,
  GError                **error);
gboolean goodix_pairing_provision_mark_tls_proven (
  GoodixPairingProvision *provision,
  GError                **error);

gboolean goodix_pairing_provision_is_complete (
  const GoodixPairingProvision *provision);
GoodixPairingProvisionTerminal goodix_pairing_provision_get_terminal (
  const GoodixPairingProvision *provision);

G_DEFINE_AUTOPTR_CLEANUP_FUNC (GoodixPairingProvision,
                               goodix_pairing_provision_free)

G_END_DECLS

#endif
