/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_A0_PROTOCOL_H
#define GOODIX_A0_PROTOCOL_H

#include <glib.h>

G_BEGIN_DECLS

typedef struct
{
  guint8  control;
  GBytes *body;
} GoodixA0Message;

GBytes  *goodix_a0_build_frame (guint8        wire_control,
                                guint8        checksum_control,
                                const guint8 *body,
                                gsize         body_length,
                                GError      **error);
gboolean goodix_a0_parse_frame (GBytes          *frame,
                                guint8           checksum_control,
                                GoodixA0Message *message,
                                GError         **error);
void     goodix_a0_message_clear (GoodixA0Message *message);

G_END_DECLS

#endif
