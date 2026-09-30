/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef GOODIX_CONFIG90_H
#define GOODIX_CONFIG90_H

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_CONFIG90_LENGTH 224u
#define GOODIX_CONFIG90_OTP_LENGTH 64u

typedef enum
{
  GOODIX_CONFIG90_ERROR_ARGUMENT,
  GOODIX_CONFIG90_ERROR_PROFILE,
  GOODIX_CONFIG90_ERROR_OTP,
  GOODIX_CONFIG90_ERROR_TEMPLATE,
} GoodixConfig90Error;

typedef struct
{
  guint16 dac_registers[4];
  guint16 tcode;
  guint8  delta;
  guint8  fdt_offset;
} GoodixConfig90Calibration;

#define GOODIX_CONFIG90_ERROR (goodix_config90_error_quark ())

GQuark goodix_config90_error_quark (void);

/* Pure ChicagoHS type-12 derivation.  The output and calibration record are
 * cleared before validation and on every failure. */
gboolean goodix_config90_derive (
  guint16                    chip_id,
  const guint8              *otp,
  gsize                      otp_length,
  guint8                     output[GOODIX_CONFIG90_LENGTH],
  GoodixConfig90Calibration *calibration,
  GError                   **error);

G_END_DECLS

#endif
