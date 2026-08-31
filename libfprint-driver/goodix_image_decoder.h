/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_IMAGE_DECODER_H
#define GOODIX_IMAGE_DECODER_H

#include <gio/gio.h>
#include <stdint.h>

#include "goodix_u16_to_fpimage.h"

G_BEGIN_DECLS

#define GOODIX_IMAGE_PLAINTEXT_LENGTH 7693u
#define GOODIX_IMAGE_RECORD_LENGTH 7684u
#define GOODIX_IMAGE_PACKED_LENGTH 7680u

typedef enum
{
  GOODIX_IMAGE_CHECKSUM_ADDITIVE_VERIFIED = 0,
  GOODIX_IMAGE_CHECKSUM_NO_CHECK_0X88,
} GoodixImageChecksumPolicy;

typedef struct
{
  GoodixImageChecksumPolicy checksum_policy;
  gboolean record_crc_match;
  guint width;
  guint height;
} GoodixImageDecodeAudit;

gboolean goodix_image_decode_plaintext (
  GBytes                 *plaintext,
  uint16_t                samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT],
  GoodixImageDecodeAudit *audit,
  GError                 **error);

G_END_DECLS

#endif
