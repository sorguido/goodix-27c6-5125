/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_BB010002_H
#define GOODIX_BB010002_H

#include <glib.h>

G_BEGIN_DECLS

#define GOODIX_BB010002_LENGTH 332u

typedef enum
{
  GOODIX_BB010002_ERROR_ARGUMENT,
  GOODIX_BB010002_ERROR_LENGTH,
  GOODIX_BB010002_ERROR_STRUCTURE,
} GoodixBb010002Error;

typedef struct
{
  guint32 blob_version;
  guint32 masterkey_version;
  guint32 flags;
  guint32 crypt_algorithm;
  guint32 crypt_bits;
  guint32 hash_algorithm;
  guint32 hash_bits;
  gsize   blob_length;
  gsize   trailer_length;
} GoodixBb010002Info;

#define GOODIX_BB010002_ERROR (goodix_bb010002_error_quark ())

GQuark goodix_bb010002_error_quark (void);

/* Validate the exact opaque Windows DPAPI envelope observed for legitimate
 * APP12509 BB010002 values.  The function does not decrypt, synthesize, copy,
 * or reinterpret protected payload bytes. */
gboolean goodix_bb010002_validate (const guint8        *data,
                                   gsize                length,
                                   GoodixBb010002Info *info,
                                   GError             **error);

G_END_DECLS

#endif
