/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * minutiae_to_xyt() below derives from libfprint 1.94.100 fpi-print.c:
 * Copyright (C) 2007 Daniel Drake <dsd@gentoo.org>
 * Copyright (C) 2019 Benjamin Berg <bberg@redhat.com>
 */
/* Offline-only pinned NBIS quality and Bozorth pairwise aggregate adapter. */
#include <bozorth.h>
#include <glib.h>
#include <lfs.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define HEADER_SIZE 16u
#define TARGET_PIXELS (80u * 64u)
#define QUALITY_LEVELS 5u
#define MAX_SAMPLES 128u

typedef struct
{
  gint minutiae_total;
  gint minutiae_reliability_ge_025;
  gint minutiae_reliability_ge_050;
  gint quality_levels[QUALITY_LEVELS];
  gint map_width;
  gint map_height;
} NbisQualityMetrics;

typedef struct
{
  gboolean present;
  struct xyt_struct xyt;
} StoredSample;

static StoredSample samples[MAX_SAMPLES];

static guint32
read_u32le (const guint8 *value)
{
  return ((guint32) value[0]) |
         ((guint32) value[1] << 8) |
         ((guint32) value[2] << 16) |
         ((guint32) value[3] << 24);
}

static void
cleanse (guint8 *data, gsize length)
{
  volatile guint8 *cursor = data;
  while (length-- > 0)
    *cursor++ = 0;
}

/* Exact libfprint 1.94.100 fpi-print.c minutiae_to_xyt conversion. */
static void
minutiae_to_xyt (struct fp_minutiae *minutiae,
                 gint                width,
                 gint                height,
                 struct xyt_struct  *xyt)
{
  struct minutiae_struct converted[MAX_FILE_MINUTIAE];
  gint count = MIN (minutiae->num, MAX_BOZORTH_MINUTIAE);

  memset (converted, 0, sizeof converted);
  memset (xyt, 0, sizeof *xyt);
  for (gint index = 0; index < count; index++)
    {
      struct fp_minutia *item = minutiae->list[index];
      lfs2nist_minutia_XYT (&converted[index].col[0],
                            &converted[index].col[1],
                            &converted[index].col[2], item, width, height);
      converted[index].col[3] = sround (item->reliability * 100.0);
      if (converted[index].col[2] > 180)
        converted[index].col[2] -= 360;
    }
  qsort (converted, (gsize) count, sizeof (struct minutiae_struct), sort_x_y);
  for (gint index = 0; index < count; index++)
    {
      xyt->xcol[index] = converted[index].col[0];
      xyt->ycol[index] = converted[index].col[1];
      xyt->thetacol[index] = converted[index].col[2];
    }
  xyt->nrows = count;
  cleanse ((guint8 *) converted, sizeof converted);
}

static gint
extract_sample (guint8 *image, StoredSample *stored, NbisQualityMetrics *metrics)
{
  MINUTIAE *minutiae = NULL;
  gint *quality_map = NULL;
  gint *direction_map = NULL;
  gint *low_contrast_map = NULL;
  gint *low_flow_map = NULL;
  gint *high_curve_map = NULL;
  guint8 *binarized = NULL;
  gint map_width = 0, map_height = 0;
  gint binary_width = 0, binary_height = 0, binary_depth = 0;
  LFSPARMS parameters = g_lfsparms_V2;
  gint result;

  memset (metrics, 0, sizeof *metrics);
  memset (stored, 0, sizeof *stored);
  parameters.remove_perimeter_pts = FALSE;
  result = get_minutiae (&minutiae, &quality_map, &direction_map,
                         &low_contrast_map, &low_flow_map, &high_curve_map,
                         &map_width, &map_height, &binarized,
                         &binary_width, &binary_height, &binary_depth,
                         image, 80, 64, 8, 0.0, &parameters);
  if (result == 0)
    {
      if (quality_map == NULL || map_width <= 0 || map_height <= 0)
        result = -100;
      else
        {
          metrics->map_width = map_width;
          metrics->map_height = map_height;
          metrics->minutiae_total = minutiae != NULL ? minutiae->num : 0;
          for (gint index = 0; index < map_width * map_height; index++)
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
            for (gint index = 0; index < minutiae->num; index++)
              {
                double reliability = minutiae->list[index]->reliability;
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
          if (result == 0 && minutiae != NULL)
            minutiae_to_xyt (minutiae, 80, 64, &stored->xyt);
        }
    }
  stored->present = result == 0;
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

int
main (void)
{
  guint8 header[HEADER_SIZE];
  while (TRUE)
    {
      size_t got = fread (header, 1, sizeof header, stdin);
      guint32 first, second;
      if (got == 0 && feof (stdin))
        {
          cleanse ((guint8 *) samples, sizeof samples);
          return 0;
        }
      if (got != sizeof header)
        {
          fputs ("FAIL_CLOSED NBIS_PAIR_HEADER\n", stderr);
          return 2;
        }
      first = read_u32le (&header[4]);
      second = read_u32le (&header[8]);
      if (read_u32le (&header[12]) != 0 || first >= MAX_SAMPLES)
        {
          fputs ("FAIL_CLOSED NBIS_PAIR_CONTRACT\n", stderr);
          return 2;
        }
      if (memcmp (header, "NBX1", 4) == 0)
        {
          g_autofree guint8 *image = NULL;
          NbisQualityMetrics metrics;
          gint result;
          if (second != TARGET_PIXELS || samples[first].present)
            return 2;
          image = g_malloc (TARGET_PIXELS);
          if (fread (image, 1, TARGET_PIXELS, stdin) != TARGET_PIXELS)
            return 2;
          result = extract_sample (image, &samples[first], &metrics);
          cleanse (image, TARGET_PIXELS);
          if (result != 0)
            {
              fprintf (stderr, "FAIL_CLOSED NBIS_EXTRACT_%d\n", result);
              return 3;
            }
          g_print ("NBISX %u %d %d %d %d %d %d %d %d %d %d %d\n",
                   first, metrics.minutiae_total,
                   metrics.minutiae_reliability_ge_025,
                   metrics.minutiae_reliability_ge_050,
                   metrics.quality_levels[0], metrics.quality_levels[1],
                   metrics.quality_levels[2], metrics.quality_levels[3],
                   metrics.quality_levels[4], metrics.map_width,
                   metrics.map_height, samples[first].xyt.nrows >= 10);
          fflush (stdout);
        }
      else if (memcmp (header, "NBM1", 4) == 0)
        {
          gint eligible, score = 0;
          gint probe_len;
          if (second >= MAX_SAMPLES || !samples[first].present ||
              !samples[second].present)
            return 2;
          eligible = samples[first].xyt.nrows >= 10 && samples[second].xyt.nrows >= 10;
          if (eligible)
            {
              probe_len = bozorth_probe_init (&samples[first].xyt);
              score = bozorth_to_gallery (probe_len, &samples[first].xyt,
                                          &samples[second].xyt);
              if (score < 0)
                return 3;
            }
          g_print ("NBISM %u %u %d %d\n", first, second, eligible, score);
          fflush (stdout);
        }
      else
        {
          fputs ("FAIL_CLOSED NBIS_PAIR_MAGIC\n", stderr);
          return 2;
        }
    }
}
