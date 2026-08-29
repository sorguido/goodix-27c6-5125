/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Independent A0 codec derived from the neutral protocol facts recorded in
 * docs/EVIDENCE.md (USB-002), the D232 contract and the canonical A8/E4/D1
 * vectors.  No GPL implementation was copied, adapted or translated.
 */
#include "goodix_a0_protocol.h"

typedef enum
{
  GOODIX_A0_ERROR_ARGUMENT,
  GOODIX_A0_ERROR_LENGTH,
  GOODIX_A0_ERROR_TAG,
  GOODIX_A0_ERROR_CHECKSUM,
} GoodixA0Error;

#define GOODIX_A0_ERROR (goodix_a0_error_quark ())

static GQuark
goodix_a0_error_quark (void)
{
  return g_quark_from_static_string ("goodix-a0-error");
}

static guint8
outer_tag (guint8 type,
           guint16 payload_length)
{
  return (guint8) (type + (guint8) payload_length +
                   (guint8) (payload_length >> 8));
}

/* The inner additive coordinate sums to 0xaa when the encoded inner length
 * (body plus checksum) is included. */
static guint8
inner_checksum (guint8        control,
                const guint8 *body,
                gsize         body_length)
{
  guint sum = control + (guint) body_length + 1u;

  for (gsize i = 0; i < body_length; i++)
    sum += body[i];
  return (guint8) (0xaau - sum);
}

GBytes *
goodix_a0_build_frame (guint8        wire_control,
                       guint8        checksum_control,
                       const guint8 *body,
                       gsize         body_length,
                       GError      **error)
{
  g_autoptr(GByteArray) frame = NULL;
  guint16 inner_length;
  guint16 payload_length;
  guint8 header[4];
  guint8 inner[3];
  guint8 checksum;

  if ((body_length != 0 && body == NULL) || body_length > G_MAXUINT16 - 4u)
    {
      g_set_error_literal (error, GOODIX_A0_ERROR, GOODIX_A0_ERROR_ARGUMENT,
                           "A0 body is absent or too large");
      return NULL;
    }

  inner_length = (guint16) (body_length + 1u);
  payload_length = (guint16) (body_length + 4u);
  header[0] = 0xa0;
  header[1] = (guint8) payload_length;
  header[2] = (guint8) (payload_length >> 8);
  header[3] = outer_tag (header[0], payload_length);
  inner[0] = wire_control;
  inner[1] = (guint8) inner_length;
  inner[2] = (guint8) (inner_length >> 8);
  checksum = inner_checksum (checksum_control, body, body_length);

  frame = g_byte_array_sized_new ((guint) payload_length + 4u);
  g_byte_array_append (frame, header, sizeof header);
  g_byte_array_append (frame, inner, sizeof inner);
  if (body_length != 0)
    g_byte_array_append (frame, body, (guint) body_length);
  g_byte_array_append (frame, &checksum, 1);
  return g_byte_array_free_to_bytes (g_steal_pointer (&frame));
}

gboolean
goodix_a0_parse_frame (GBytes          *frame,
                       guint8           checksum_control,
                       GoodixA0Message *message,
                       GError         **error)
{
  gsize length;
  const guint8 *data;
  guint16 payload_length;
  guint16 inner_length;
  gsize body_length;

  if (frame == NULL || message == NULL)
    {
      g_set_error_literal (error, GOODIX_A0_ERROR, GOODIX_A0_ERROR_ARGUMENT,
                           "A0 parser argument is absent");
      return FALSE;
    }
  message->control = 0;
  message->body = NULL;
  data = g_bytes_get_data (frame, &length);
  if (length < 8 || data[0] != 0xa0)
    {
      g_set_error_literal (error, GOODIX_A0_ERROR, GOODIX_A0_ERROR_LENGTH,
                           "A0 outer type or minimum length is invalid");
      return FALSE;
    }
  payload_length = (guint16) data[1] | ((guint16) data[2] << 8);
  if ((gsize) payload_length + 4u != length || payload_length < 4u)
    {
      g_set_error_literal (error, GOODIX_A0_ERROR, GOODIX_A0_ERROR_LENGTH,
                           "A0 outer length is inconsistent");
      return FALSE;
    }
  if (data[3] != outer_tag (data[0], payload_length))
    {
      g_set_error_literal (error, GOODIX_A0_ERROR, GOODIX_A0_ERROR_TAG,
                           "A0 outer tag mismatch");
      return FALSE;
    }
  inner_length = (guint16) data[5] | ((guint16) data[6] << 8);
  if (inner_length == 0 || (gsize) inner_length + 3u != payload_length)
    {
      g_set_error_literal (error, GOODIX_A0_ERROR, GOODIX_A0_ERROR_LENGTH,
                           "A0 inner length is inconsistent");
      return FALSE;
    }
  body_length = (gsize) inner_length - 1u;
  if (data[length - 1u] !=
      inner_checksum (checksum_control, data + 7, body_length))
    {
      g_set_error_literal (error, GOODIX_A0_ERROR, GOODIX_A0_ERROR_CHECKSUM,
                           "A0 inner checksum mismatch");
      return FALSE;
    }

  message->control = data[4];
  message->body = g_bytes_new (data + 7, body_length);
  return TRUE;
}

void
goodix_a0_message_clear (GoodixA0Message *message)
{
  if (message == NULL)
    return;
  g_clear_pointer (&message->body, g_bytes_unref);
  message->control = 0;
}
