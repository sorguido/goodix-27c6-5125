/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Offline-only exact Fedora 44/libfprint 1.94.100 NBIS count adapter.
 *
 * Binary stdin protocol, repeated until EOF:
 *   "NBS1" | width:u16le | height:u16le | length:u32le | pixels[length]
 * stdout response per frame:
 *   "NBIS1 <minutiae-count>\n"
 *
 * No path, image writer, USB object or production driver entry point exists.
 */
#include <glib.h>
#include <lfs.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define HEADER_SIZE 12u
#define TARGET_PIXELS (80u * 64u)

static guint16
read_u16le (const guint8 *value)
{
  return (guint16) value[0] | ((guint16) value[1] << 8);
}

static guint32
read_u32le (const guint8 *value)
{
  return ((guint32) value[0]) |
         ((guint32) value[1] << 8) |
         ((guint32) value[2] << 16) |
         ((guint32) value[3] << 24);
}

static void
cleanse (guint8 *data,
         gsize   length)
{
  volatile guint8 *cursor = data;

  while (length-- > 0)
    *cursor++ = 0;
}

static int
count_minutiae (guint8 *image,
                gint    width,
                gint    height,
                gint   *count)
{
  MINUTIAE *minutiae = NULL;
  gint *quality_map = NULL;
  gint *direction_map = NULL;
  gint *low_contrast_map = NULL;
  gint *low_flow_map = NULL;
  gint *high_curve_map = NULL;
  guint8 *binarized = NULL;
  gint map_width = 0;
  gint map_height = 0;
  gint binary_width = 0;
  gint binary_height = 0;
  gint binary_depth = 0;
  LFSPARMS parameters = g_lfsparms_V2;
  gint result;

  parameters.remove_perimeter_pts = FALSE;
  result = get_minutiae (&minutiae,
                         &quality_map,
                         &direction_map,
                         &low_contrast_map,
                         &low_flow_map,
                         &high_curve_map,
                         &map_width,
                         &map_height,
                         &binarized,
                         &binary_width,
                         &binary_height,
                         &binary_depth,
                         image,
                         width,
                         height,
                         8,
                         0.0,
                         &parameters);
  if (result == 0)
    *count = minutiae != NULL ? minutiae->num : 0;

  if (minutiae != NULL)
    free_minutiae (minutiae);
  g_free (quality_map);
  g_free (direction_map);
  g_free (low_contrast_map);
  g_free (low_flow_map);
  g_free (high_curve_map);
  g_free (binarized);
  return result;
}

int
main (void)
{
  guint8 header[HEADER_SIZE];

  while (TRUE)
    {
      guint8 *image;
      guint16 width;
      guint16 height;
      guint32 length;
      gint count = 0;
      gint result;
      size_t header_read = fread (header, 1, sizeof header, stdin);

      if (header_read == 0 && feof (stdin))
        return 0;
      if (header_read != sizeof header)
        {
          fputs ("FAIL_CLOSED TRUNCATED_HEADER\n", stderr);
          return 2;
        }
      if (memcmp (header, "NBS1", 4) != 0)
        {
          fputs ("FAIL_CLOSED BAD_MAGIC\n", stderr);
          return 2;
        }

      width = read_u16le (&header[4]);
      height = read_u16le (&header[6]);
      length = read_u32le (&header[8]);
      if (!((width == 80 && height == 64) ||
            (width == 64 && height == 80)) ||
          length != TARGET_PIXELS || length != (guint32) width * height)
        {
          fputs ("FAIL_CLOSED IMAGE_SHAPE\n", stderr);
          return 2;
        }

      image = g_malloc (length);
      if (fread (image, 1, length, stdin) != length)
        {
          cleanse (image, length);
          g_free (image);
          fputs ("FAIL_CLOSED TRUNCATED_IMAGE\n", stderr);
          return 2;
        }
      result = count_minutiae (image, width, height, &count);
      cleanse (image, length);
      g_free (image);
      if (result != 0)
        {
          fprintf (stderr, "FAIL_CLOSED NBIS_%d\n", result);
          return 3;
        }
      g_print ("NBIS1 %d\n", count);
      fflush (stdout);
    }
}

