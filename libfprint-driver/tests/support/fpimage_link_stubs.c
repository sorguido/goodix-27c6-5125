/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Link-only seams for downstream algorithms intentionally not executed by
 * D270.  Any accidental call aborts the synthetic construction test.
 */
#include <nbis.h>
#include <sigfm/sigfm.h>

#include <glib.h>

LFSPARMS g_lfsparms_V2;

int
get_minutiae (MINUTIAE      **ominutiae,
              int           **oquality_map,
              int           **odirection_map,
              int           **olow_contrast_map,
              int           **olow_flow_map,
              int           **ohigh_curve_map,
              int            *omap_w,
              int            *omap_h,
              unsigned char **obdata,
              int            *obw,
              int            *obh,
              int            *obd,
              unsigned char  *idata,
              const int       iw,
              const int       ih,
              const int       id,
              const double    ppmm,
              const LFSPARMS *lfsparms)
{
  g_error ("D270 link stub called: get_minutiae");
  return -1;
}

void
free_minutiae (MINUTIAE *minutiae)
{
  g_error ("D270 link stub called: free_minutiae");
}

void
free_minutia (MINUTIA *minutia)
{
  g_error ("D270 link stub called: free_minutia");
}

SigfmImgInfo *
sigfm_extract (const SigfmPix *pix, int width, int height)
{
  g_error ("D270 link stub called: sigfm_extract");
  return NULL;
}

void
sigfm_free_info (SigfmImgInfo *info)
{
  g_error ("D270 link stub called: sigfm_free_info");
}

int
sigfm_keypoints_count (SigfmImgInfo *info)
{
  g_error ("D270 link stub called: sigfm_keypoints_count");
  return -1;
}
