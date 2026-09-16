/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Offline-only pinned libfprint bilinear-resize plus NBIS count adapter.
 *
 * Binary stdin protocol, repeated until EOF:
 *   "NBR1" | width:u16le | height:u16le | length:u32le |
 *   factor:u32le | pixels[length]
 * stdout response per frame:
 *   "NBISR <factor> <minutiae-count>\n"
 *
 * Input is always one native 80x64 (or transposed 64x80) 8-bit frame.  Factors
 * 2 and 3 use fpi_image_resize() from the pinned tree before exact NBIS.  The
 * factor-1 control bypasses interpolation and therefore reproduces D279/34.
 * No path, image writer, USB object or production driver entry point exists.
 */
#include <glib.h>
#include <lfs.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "fpi-image.h"

#define HEADER_SIZE 16u
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
  g_clear_pointer (&quality_map, g_free);
  g_clear_pointer (&direction_map, g_free);
  g_clear_pointer (&low_contrast_map, g_free);
  g_clear_pointer (&low_flow_map, g_free);
  g_clear_pointer (&high_curve_map, g_free);
  if (binarized != NULL)
    {
      if (binary_width > 0 && binary_height > 0)
        cleanse (binarized, (gsize) binary_width * binary_height);
      g_free (binarized);
    }
  return result;
}

static int
resize_and_count (const guint8 *pixels,
                  guint         width,
                  guint         height,
                  guint         factor,
                  gint         *count)
{
  g_autoptr(FpImage) input = fp_image_new (width, height);
  g_autoptr(FpImage) resized = NULL;
  FpImage *candidate = input;
  gint result;

  memcpy (input->data, pixels, (gsize) width * height);
  if (factor > 1)
    {
      resized = fpi_image_resize (input, factor, factor);
      if (resized->width != width * factor || resized->height != height * factor)
        {
          cleanse (input->data, (gsize) width * height);
          return -100;
        }
      candidate = resized;
    }

  result = count_minutiae (candidate->data,
                           candidate->width,
                           candidate->height,
                           count);
  cleanse (candidate->data, (gsize) candidate->width * candidate->height);
  if (candidate != input)
    cleanse (input->data, (gsize) width * height);
  return result;
}

int
main (void)
{
  guint8 header[HEADER_SIZE];

  while (TRUE)
    {
      g_autofree guint8 *image = NULL;
      guint16 width;
      guint16 height;
      guint32 length;
      guint32 factor;
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
      if (memcmp (header, "NBR1", 4) != 0)
        {
          fputs ("FAIL_CLOSED BAD_MAGIC\n", stderr);
          return 2;
        }

      width = read_u16le (&header[4]);
      height = read_u16le (&header[6]);
      length = read_u32le (&header[8]);
      factor = read_u32le (&header[12]);
      if (!((width == 80 && height == 64) ||
            (width == 64 && height == 80)) ||
          length != TARGET_PIXELS || length != (guint32) width * height ||
          factor < 1 || factor > 3)
        {
          fputs ("FAIL_CLOSED INPUT_CONTRACT\n", stderr);
          return 2;
        }

      image = g_malloc (length);
      if (fread (image, 1, length, stdin) != length)
        {
          cleanse (image, length);
          fputs ("FAIL_CLOSED TRUNCATED_IMAGE\n", stderr);
          return 2;
        }
      result = resize_and_count (image, width, height, factor, &count);
      cleanse (image, length);
      if (result != 0)
        {
          fprintf (stderr, "FAIL_CLOSED NBIS_OR_RESIZE_%d\n", result);
          return 3;
        }
      g_print ("NBISR %u %d\n", factor, count);
      fflush (stdout);
    }
}
