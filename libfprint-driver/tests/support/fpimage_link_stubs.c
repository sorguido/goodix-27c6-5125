/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Link-only seams for algorithms intentionally not executed by the host-only
 * libfprint shell tests.  NBIS paths abort because this slice deliberately
 * selects SIGFM and never reaches bozorth3.  SIGFM paths return a trivial
 * host-only double so that the real FpImageDevice enrollment state machine
 * can be exercised without a real biometric extractor.
 */
#include "test_sigfm_control.h"

#include <nbis.h>
#include <sigfm/sigfm.h>

#include <glib.h>

/* NBIS global required by fp-image.c when compiled into the test harness. */
LFSPARMS g_lfsparms_V2;

/* Opaque SIGFM object used only by these stubs. */
struct SigfmImgInfo
{
  gint dummy;
};

static GMutex sigfm_mutex;
static GCond  sigfm_cond;
static gint   sigfm_extract_block = 0;
static gint   sigfm_extract_blocked_count = 0;
static gint   sigfm_extract_fail = 0;

void
goodix_test_sigfm_extract_set_block (gboolean block)
{
  g_mutex_lock (&sigfm_mutex);
  sigfm_extract_block = block ? 1 : 0;
  g_mutex_unlock (&sigfm_mutex);
}

void
goodix_test_sigfm_extract_set_failure (gboolean fail)
{
  g_mutex_lock (&sigfm_mutex);
  sigfm_extract_fail = fail ? 1 : 0;
  g_mutex_unlock (&sigfm_mutex);
}

void
goodix_test_sigfm_extract_unblock (void)
{
  g_mutex_lock (&sigfm_mutex);
  sigfm_extract_block = 0;
  g_cond_broadcast (&sigfm_cond);
  g_mutex_unlock (&sigfm_mutex);
}

gboolean
goodix_test_sigfm_extract_is_blocked (void)
{
  gboolean blocked;

  g_mutex_lock (&sigfm_mutex);
  blocked = sigfm_extract_blocked_count > 0;
  g_mutex_unlock (&sigfm_mutex);

  return blocked;
}

gboolean
goodix_test_sigfm_extract_wait_blocked (gint64 timeout_us)
{
  gint64 deadline = g_get_monotonic_time () + timeout_us;
  gboolean blocked;

  g_mutex_lock (&sigfm_mutex);
  while (sigfm_extract_blocked_count == 0 &&
         g_cond_wait_until (&sigfm_cond, &sigfm_mutex, deadline))
    ;
  blocked = sigfm_extract_blocked_count > 0;
  g_mutex_unlock (&sigfm_mutex);

  return blocked;
}

/* --- NBIS stubs: never reached in SIGFM-mode tests --- */

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
  (void) ominutiae;
  (void) oquality_map;
  (void) odirection_map;
  (void) olow_contrast_map;
  (void) olow_flow_map;
  (void) ohigh_curve_map;
  (void) omap_w;
  (void) omap_h;
  (void) obdata;
  (void) obw;
  (void) obh;
  (void) obd;
  (void) idata;
  (void) iw;
  (void) ih;
  (void) id;
  (void) ppmm;
  (void) lfsparms;

  g_error ("D276 host-only test reached NBIS get_minutiae");
  return -1;
}

void
free_minutiae (MINUTIAE *minutiae)
{
  (void) minutiae;
  g_error ("D276 host-only test reached NBIS free_minutiae");
}

void
free_minutia (MINUTIA *minutia)
{
  (void) minutia;
  g_error ("D276 host-only test reached NBIS free_minutia");
}

int
bozorth_probe_init (struct xyt_struct *pstruct)
{
  (void) pstruct;
  g_error ("D276 host-only test reached bozorth_probe_init");
  return -1;
}

int
bozorth_to_gallery (int                 probe_len,
                    struct xyt_struct  *pstruct,
                    struct xyt_struct  *gstruct)
{
  (void) probe_len;
  (void) pstruct;
  (void) gstruct;
  g_error ("D276 host-only test reached bozorth_to_gallery");
  return -1;
}

void
lfs2nist_minutia_XYT (int *col, int *row, int *theta,
                      const MINUTIA *minutia,
                      const int img_width, const int img_height)
{
  (void) col;
  (void) row;
  (void) theta;
  (void) minutia;
  (void) img_width;
  (void) img_height;
  g_error ("D276 host-only test reached lfs2nist_minutia_XYT");
}

int
sort_x_y (const void *a, const void *b)
{
  (void) a;
  (void) b;
  g_error ("D276 host-only test reached sort_x_y");
  return 0;
}

/* --- SIGFM stubs: trivial host-only double --- */

SigfmImgInfo *
sigfm_extract (const SigfmPix *pix, int width, int height)
{
  SigfmImgInfo *info;

  (void) pix;
  (void) width;
  (void) height;

  g_mutex_lock (&sigfm_mutex);
  if (sigfm_extract_block)
    {
      sigfm_extract_blocked_count++;
      g_cond_broadcast (&sigfm_cond);
      while (sigfm_extract_block)
        g_cond_wait (&sigfm_cond, &sigfm_mutex);
      sigfm_extract_blocked_count--;
    }
  g_mutex_unlock (&sigfm_mutex);

  info = g_new0 (SigfmImgInfo, 1);
  info->dummy = 1;
  return info;
}

void
sigfm_free_info (SigfmImgInfo *info)
{
  g_free (info);
}

SigfmImgInfo *
sigfm_copy_info (SigfmImgInfo *info)
{
  SigfmImgInfo *copy;

  if (info == NULL)
    return NULL;

  copy = g_new0 (SigfmImgInfo, 1);
  copy->dummy = info->dummy;
  return copy;
}

int
sigfm_keypoints_count (SigfmImgInfo *info)
{
  gboolean fail;

  (void) info;

  g_mutex_lock (&sigfm_mutex);
  fail = sigfm_extract_fail != 0;
  g_mutex_unlock (&sigfm_mutex);

  if (fail)
    return 0;
  return 30;
}

int
sigfm_match_score (SigfmImgInfo *frame, SigfmImgInfo *enrolled)
{
  (void) frame;
  (void) enrolled;
  return 0;
}

unsigned char *
sigfm_serialize_binary (SigfmImgInfo *info, int *outlen)
{
  (void) info;
  if (outlen)
    *outlen = 0;
  return NULL;
}

SigfmImgInfo *
sigfm_deserialize_binary (const unsigned char *bytes, int len)
{
  (void) bytes;
  (void) len;
  return NULL;
}
