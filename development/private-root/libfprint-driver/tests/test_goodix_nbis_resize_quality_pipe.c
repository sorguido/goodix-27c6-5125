/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Offline-only pinned resize plus NBIS quality-map aggregate adapter. */
#include <glib.h>
#include <lfs.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "fpi-image.h"

#define HEADER_SIZE 16u
#define TARGET_PIXELS (80u * 64u)
#define QUALITY_LEVELS 5u

typedef struct
{
  gint minutiae_total;
  gint minutiae_reliability_ge_025;
  gint minutiae_reliability_ge_050;
  gint quality_levels[QUALITY_LEVELS];
  gint map_width;
  gint map_height;
} NbisQualityMetrics;

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
measure_quality (guint8            *image,
                 gint               width,
                 gint               height,
                 NbisQualityMetrics *metrics)
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
  gint index;

  memset (metrics, 0, sizeof *metrics);
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
    {
      if (map_width <= 0 || map_height <= 0 || quality_map == NULL)
        result = -100;
      else
        {
          metrics->map_width = map_width;
          metrics->map_height = map_height;
          metrics->minutiae_total = minutiae != NULL ? minutiae->num : 0;
          for (index = 0; index < map_width * map_height; index++)
            {
              gint level = quality_map[index];

              if (level < 0 || level >= (gint) QUALITY_LEVELS)
                {
                  result = -101;
                  break;
                }
              metrics->quality_levels[level]++;
            }
          if (result == 0 && minutiae != NULL)
            {
              for (index = 0; index < minutiae->num; index++)
                {
                  double reliability;

                  if (minutiae->list[index] == NULL)
                    {
                      result = -104;
                      break;
                    }
                  reliability = minutiae->list[index]->reliability;

                  if (reliability < 0.0 || reliability > 1.0)
                    {
                      result = -102;
                      break;
                    }
                  if (reliability >= 0.25)
                    metrics->minutiae_reliability_ge_025++;
                  if (reliability >= 0.50)
                    metrics->minutiae_reliability_ge_050++;
                }
            }
        }
    }

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
resize_and_measure (const guint8      *pixels,
                    guint              width,
                    guint              height,
                    guint              factor,
                    NbisQualityMetrics *metrics)
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
          return -103;
        }
      candidate = resized;
    }

  result = measure_quality (candidate->data,
                            candidate->width,
                            candidate->height,
                            metrics);
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
      NbisQualityMetrics metrics;
      gint result;
      size_t header_read = fread (header, 1, sizeof header, stdin);

      if (header_read == 0 && feof (stdin))
        return 0;
      if (header_read != sizeof header)
        {
          fputs ("FAIL_CLOSED TRUNCATED_HEADER\n", stderr);
          return 2;
        }
      if (memcmp (header, "NBQ1", 4) != 0)
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
      result = resize_and_measure (image, width, height, factor, &metrics);
      cleanse (image, length);
      if (result != 0)
        {
          fprintf (stderr, "FAIL_CLOSED NBIS_OR_RESIZE_%d\n", result);
          return 3;
        }
      g_print ("NBISQ %u %d %d %d %d %d %d %d %d %d %d\n",
               factor,
               metrics.minutiae_total,
               metrics.minutiae_reliability_ge_025,
               metrics.minutiae_reliability_ge_050,
               metrics.quality_levels[0],
               metrics.quality_levels[1],
               metrics.quality_levels[2],
               metrics.quality_levels[3],
               metrics.quality_levels[4],
               metrics.map_width,
               metrics.map_height);
      fflush (stdout);
    }
}
