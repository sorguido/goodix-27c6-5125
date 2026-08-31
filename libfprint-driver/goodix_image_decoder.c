/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Independent decoder for the canonical APP12509 image contract.  The
 * implementation uses only the neutral, repository-canonical framing,
 * packed-12, CRC and raster facts; no GPL implementation was translated.
 */
#include "goodix_image_decoder.h"

#include <string.h>

typedef enum
{
  GOODIX_IMAGE_ERROR_SHAPE,
  GOODIX_IMAGE_ERROR_CLASS,
  GOODIX_IMAGE_ERROR_CHECKSUM,
  GOODIX_IMAGE_ERROR_CRC,
} GoodixImageError;

#define GOODIX_IMAGE_ERROR (goodix_image_error_quark ())

static GQuark
goodix_image_error_quark (void)
{
  return g_quark_from_static_string ("goodix-image-decoder-error");
}

static guint32
crc32_mpeg2 (const guint8 *data,
             gsize         length)
{
  guint32 crc = UINT32_C (0xffffffff);

  for (gsize i = 0; i < length; i++)
    {
      crc ^= (guint32) data[i] << 24;
      for (guint bit = 0; bit < 8; bit++)
        crc = (crc & UINT32_C (0x80000000)) != 0 ?
          (crc << 1) ^ UINT32_C (0x04c11db7) : crc << 1;
    }
  return crc;
}

static guint32
decode_crc_trailer (const guint8 trailer[4])
{
  return ((guint32) trailer[2] << 24) |
         ((guint32) trailer[3] << 16) |
         ((guint32) trailer[0] << 8) |
         (guint32) trailer[1];
}

static guint8
payload_checksum (guint8        control,
                  const guint8 *data,
                  gsize         data_length)
{
  guint sum = (guint) control + (guint) data_length + 1u;

  for (gsize i = 0; i < data_length; i++)
    sum += data[i];
  return (guint8) (0xaau - sum);
}

gboolean
goodix_image_decode_plaintext (
  GBytes                 *plaintext,
  uint16_t                samples[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT],
  GoodixImageDecodeAudit *audit,
  GError                 **error)
{
  const guint8 *bytes;
  const guint8 *data;
  const guint8 *packed;
  gsize length;
  guint16 declared_length;
  guint32 expected_crc;
  guint32 observed_crc;
  uint16_t decoded[GOODIX_CANONICAL_IMAGE_SAMPLE_COUNT];

  if (plaintext == NULL || samples == NULL)
    {
      g_set_error_literal (error, GOODIX_IMAGE_ERROR, GOODIX_IMAGE_ERROR_SHAPE,
                           "image decoder argument is absent");
      return FALSE;
    }
  if (audit != NULL)
    memset (audit, 0, sizeof *audit);
  bytes = g_bytes_get_data (plaintext, &length);
  if (length != GOODIX_IMAGE_PLAINTEXT_LENGTH)
    goto invalid_shape;
  declared_length = (guint16) bytes[1] | ((guint16) bytes[2] << 8);
  if (declared_length != 7690u || (gsize) declared_length + 3u != length)
    goto invalid_shape;
  if ((bytes[0] >> 4) != 2u)
    {
      g_set_error_literal (error, GOODIX_IMAGE_ERROR, GOODIX_IMAGE_ERROR_CLASS,
                           "plaintext is not an image-class payload");
      return FALSE;
    }
  data = bytes + 3;
  if (data[0] == 0xaa)
    {
      g_set_error_literal (error, GOODIX_IMAGE_ERROR, GOODIX_IMAGE_ERROR_CLASS,
                           "POV notification is not an image record");
      return FALSE;
    }
  if (bytes[length - 1u] == 0x88)
    {
      if (audit != NULL)
        audit->checksum_policy = GOODIX_IMAGE_CHECKSUM_NO_CHECK_0X88;
    }
  else if (bytes[length - 1u] ==
           payload_checksum (bytes[0], data, 7689u))
    {
      if (audit != NULL)
        audit->checksum_policy = GOODIX_IMAGE_CHECKSUM_ADDITIVE_VERIFIED;
    }
  else
    {
      g_set_error_literal (error, GOODIX_IMAGE_ERROR,
                           GOODIX_IMAGE_ERROR_CHECKSUM,
                           "image payload checksum mismatch");
      return FALSE;
    }

  packed = data + 5;
  expected_crc = crc32_mpeg2 (packed, GOODIX_IMAGE_PACKED_LENGTH);
  observed_crc = decode_crc_trailer (packed + GOODIX_IMAGE_PACKED_LENGTH);
  if (observed_crc != expected_crc)
    {
      g_set_error_literal (error, GOODIX_IMAGE_ERROR, GOODIX_IMAGE_ERROR_CRC,
                           "image record CRC-32/MPEG-2 mismatch");
      return FALSE;
    }

  for (gsize group = 0; group < GOODIX_IMAGE_PACKED_LENGTH; group += 6u)
    {
      const guint8 *p = packed + group;
      const uint16_t values[4] = {
        (uint16_t) ((((guint16) p[0] & 0x0fu) << 8) | p[1]),
        (uint16_t) (((guint16) p[3] << 4) | (p[0] >> 4)),
        (uint16_t) ((((guint16) p[5] & 0x0fu) << 8) | p[2]),
        (uint16_t) (((guint16) p[4] << 4) | (p[5] >> 4)),
      };
      gsize wire_base = (group / 6u) * 4u;

      for (gsize item = 0; item < 4u; item++)
        {
          gsize wire_index = wire_base + item;
          gsize raster_index =
            (wire_index % GOODIX_CANONICAL_IMAGE_HEIGHT) *
              GOODIX_CANONICAL_IMAGE_WIDTH +
            wire_index / GOODIX_CANONICAL_IMAGE_HEIGHT;
          decoded[raster_index] = values[item];
        }
    }
  memcpy (samples, decoded, sizeof decoded);
  if (audit != NULL)
    {
      audit->record_crc_match = TRUE;
      audit->width = GOODIX_CANONICAL_IMAGE_WIDTH;
      audit->height = GOODIX_CANONICAL_IMAGE_HEIGHT;
    }
  return TRUE;

invalid_shape:
  g_set_error_literal (error, GOODIX_IMAGE_ERROR, GOODIX_IMAGE_ERROR_SHAPE,
                       "image plaintext shape is invalid");
  return FALSE;
}
