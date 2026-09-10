/*
 * FPrint Print handling - Private APIs
 * Copyright (C) 2007 Daniel Drake <dsd@gentoo.org>
 * Copyright (C) 2019 Benjamin Berg <bberg@redhat.com>
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
 */

#define FP_COMPONENT "print"
#include "fpi-log.h"

#include "fp-print-private.h"
#include "fpi-device.h"
#include "fpi-compat.h"

#ifdef GOODIX_LIBFPRINT_SIGFM
#include "goodix_sigfm_metrics.h"
#endif

/**
 * SECTION: fpi-print
 * @title: Internal FpPrint
 * @short_description: Internal fingerprint handling routines
 *
 * Interaction with prints and their storage. See also the public
 * #FpPrint routines.
 */

/**
 * fpi_print_add_print:
 * @print: A #FpPrint
 * @add: Print to append to @print
 *
 * Appends the single NBIS or SIGFM sample from @add to the collection in
 * @print. Both print objects must have the same supported type.
 */
void
fpi_print_add_print (FpPrint *print, FpPrint *add)
{
  g_autoptr(GError) error = NULL;

  if (!fpi_print_add_print_checked (print, add, &error))
    fp_warn ("Could not append print sample: %s",
             error != NULL ? error->message : "invalid print sample");
}

/**
 * fpi_print_add_print_checked:
 * @print: A template #FpPrint
 * @add: A single-sample #FpPrint to append
 * @error: Return location for an error
 *
 * Checked and atomic variant of fpi_print_add_print(). The destination is
 * changed only after the sample has been copied successfully.
 *
 * Returns: %TRUE if one sample was appended
 */
gboolean
fpi_print_add_print_checked (FpPrint  *print,
                             FpPrint  *add,
                             GError  **error)
{
  gpointer copy = NULL;

  if (!FP_IS_PRINT (print) || !FP_IS_PRINT (add) ||
      !(print->type == FPI_PRINT_NBIS ||
#ifdef GOODIX_LIBFPRINT_SIGFM
        print->type == FPI_PRINT_SIGFM
#else
        FALSE
#endif
        ) || add->type != print->type || print->prints == NULL ||
      add->prints == NULL || add->prints->len != 1 ||
      add->prints->pdata[0] == NULL)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                           "Print append requires matching supported types and exactly one source sample");
      return FALSE;
    }
#ifdef GOODIX_LIBFPRINT_SIGFM
  if (print->type == FPI_PRINT_SIGFM &&
      print->prints->len >= GOODIX_SIGFM_MAX_PRINT_SAMPLES)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
                           "SIGFM template already has the maximum sample count");
      return FALSE;
    }
#endif
  if (print->type == FPI_PRINT_NBIS)
    copy = g_memdup2 (add->prints->pdata[0], sizeof (struct xyt_struct));
#ifdef GOODIX_LIBFPRINT_SIGFM
  else
    {
      GoodixSigfmSample *sigfm_copy = NULL;
      GoodixSigfmResult result;

      result = goodix_sigfm_sample_copy (add->prints->pdata[0], &sigfm_copy);
      if (result != GOODIX_SIGFM_OK)
        {
          g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                       "Could not copy SIGFM print sample: %d", result);
          return FALSE;
        }
      copy = sigfm_copy;
    }
#endif

  if (copy == NULL)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
                           "Could not allocate print sample copy");
      return FALSE;
    }
  g_ptr_array_add (print->prints, copy);
  return TRUE;
}

/**
 * fpi_print_set_type:
 * @print: A #FpPrint
 * @type: The newly type of the print data
 *
 * This function can only be called exactly once. Drivers should
 * call it after creating a new print, or to initialize the template
 * print passed during enrollment.
 */
void
fpi_print_set_type (FpPrint     *print,
                    FpiPrintType type)
{
  g_return_if_fail (FP_IS_PRINT (print));
  /* We only allow setting this once! */
  g_return_if_fail (print->type == FPI_PRINT_UNDEFINED);

  if (type == FPI_PRINT_SIGFM)
    {
#ifndef GOODIX_LIBFPRINT_SIGFM
      g_return_if_reached ();
#endif
    }

  print->type = type;
  if (print->type == FPI_PRINT_NBIS
#ifdef GOODIX_LIBFPRINT_SIGFM
      || print->type == FPI_PRINT_SIGFM
#endif
      )
    {
      g_assert_null (print->prints);
      print->prints = g_ptr_array_new_with_free_func (
#ifdef GOODIX_LIBFPRINT_SIGFM
        print->type == FPI_PRINT_SIGFM ?
        (GDestroyNotify) goodix_sigfm_sample_free :
#endif
        g_free);
    }
  g_object_notify (G_OBJECT (print), "fpi-type");
}

/**
 * fpi_print_get_type:
 * @print: A #FpPrint
 *
 * Retrieves the type of the print data.
 *
 * Returns: The #FpiPrintType of the print.
 */
FpiPrintType
fpi_print_get_type (FpPrint *print)
{
  g_return_val_if_fail (FP_IS_PRINT (print), FPI_PRINT_UNDEFINED);

  return print->type;
}

/**
 * fpi_print_set_device_stored:
 * @print: A #FpPrint
 * @device_stored: Whether the print is stored on the device or not
 *
 * Drivers must set this to %TRUE for any print that is really a handle
 * for data that is stored on the device itself.
 */
void
fpi_print_set_device_stored (FpPrint *print,
                             gboolean device_stored)
{
  g_return_if_fail (FP_IS_PRINT (print));

  print->device_stored = device_stored;
  g_object_notify (G_OBJECT (print), "device-stored");
}

/* XXX: This is the old version, but wouldn't it be smarter to instead
 * use the highest quality mintutiae? Possibly just using bz_prune from
 * upstream? */
static void
minutiae_to_xyt (struct fp_minutiae *minutiae,
                 int                 bwidth,
                 int                 bheight,
                 struct xyt_struct  *xyt)
{
  int i;
  struct fp_minutia *minutia;
  struct minutiae_struct c[MAX_FILE_MINUTIAE];

  /* struct xyt_struct uses arrays of MAX_BOZORTH_MINUTIAE (200) */
  int nmin = min (minutiae->num, MAX_BOZORTH_MINUTIAE);

  for (i = 0; i < nmin; i++)
    {
      minutia = minutiae->list[i];

      lfs2nist_minutia_XYT (&c[i].col[0], &c[i].col[1], &c[i].col[2],
                            minutia, bwidth, bheight);
      c[i].col[3] = sround (minutia->reliability * 100.0);

      if (c[i].col[2] > 180)
        c[i].col[2] -= 360;
    }

  qsort ((void *) &c, (size_t) nmin, sizeof (struct minutiae_struct),
         sort_x_y);

  for (i = 0; i < nmin; i++)
    {
      xyt->xcol[i]     = c[i].col[0];
      xyt->ycol[i]     = c[i].col[1];
      xyt->thetacol[i] = c[i].col[2];
    }
  xyt->nrows = nmin;
}

/**
 * fpi_print_add_from_image:
 * @print: A #FpPrint
 * @image: A #FpImage
 * @error: Return location for error
 *
 * Extracts the minutiae from the given image and adds it to @print of
 * type #FPI_PRINT_NBIS.
 *
 * The @image will be kept so that API users can get retrieve it e.g.
 * for debugging purposes.
 *
 * Returns: %TRUE on success
 */
gboolean
fpi_print_add_from_image (FpPrint *print,
                          FpImage *image,
                          GError **error)
{
  GPtrArray *minutiae;
  struct fp_minutiae _minutiae;
  struct xyt_struct *xyt;

  if (!image)
    {
      g_set_error (error,
                   G_IO_ERROR,
                   G_IO_ERROR_INVALID_DATA,
                   "Cannot add print data from image!");
      return FALSE;
    }

#ifdef GOODIX_LIBFPRINT_SIGFM
  if (print->type == FPI_PRINT_SIGFM)
    {
      GoodixSigfmSample *sample = fpi_image_get_sigfm_sample (image);

      if (sample == NULL)
        {
          g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                               "No SIGFM sample found in image or not yet extracted");
          return FALSE;
        }
      if (!fpi_print_add_sigfm_sample (print, sample, error))
        return FALSE;
      g_clear_object (&print->image);
      print->image = g_object_ref (image);
      g_object_notify (G_OBJECT (print), "image");
      return TRUE;
    }
#endif
  if (print->type != FPI_PRINT_NBIS)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_DATA,
                           "Cannot add print data from image");
      return FALSE;
    }

  minutiae = fp_image_get_minutiae (image);
  if (!minutiae || minutiae->len == 0)
    {
      g_set_error (error,
                   G_IO_ERROR,
                   G_IO_ERROR_INVALID_DATA,
                   "No minutiae found in image or not yet detected!");
      return FALSE;
    }

  _minutiae.num = minutiae->len;
  _minutiae.list = (struct fp_minutia **) minutiae->pdata;
  _minutiae.alloc = minutiae->len;

  xyt = g_new0 (struct xyt_struct, 1);
  minutiae_to_xyt (&_minutiae, image->width, image->height, xyt);
  g_ptr_array_add (print->prints, xyt);

  g_clear_object (&print->image);
  print->image = g_object_ref (image);
  g_object_notify (G_OBJECT (print), "image");

  return TRUE;
}

/**
 * fpi_print_bz3_match:
 * @print_template: A #FpPrint containing one or more prints
 * @print: A newly scanned #FpPrint to test
 * @bz3_threshold: The BZ3 match threshold
 * @error: Return location for error
 *
 * Match the newly scanned @print (containing exactly one print) against the
 * prints contained in @template which will have been stored during enrollment.
 *
 * Both @template and @print need to be of type #FPI_PRINT_NBIS for this to
 * work.
 *
 * Returns: Whether the prints match, @error will be set if #FPI_MATCH_ERROR is returned
 */
FpiMatchResult
fpi_print_bz3_match (FpPrint *print_template,
                     FpPrint *print,
                     gint     bz3_threshold,
                     GError **error)
{
  struct xyt_struct *pstruct;
  gint probe_len;
  gint i;

  /* XXX: Use a different error type? */
  if (print_template->type != FPI_PRINT_NBIS || print->type != FPI_PRINT_NBIS)
    {
      *error = fpi_device_error_new_msg (FP_DEVICE_ERROR_NOT_SUPPORTED,
                                         "It is only possible to match NBIS type print data");
      return FPI_MATCH_ERROR;
    }

  if (print->prints->len != 1)
    {
      *error = fpi_device_error_new_msg (FP_DEVICE_ERROR_GENERAL,
                                         "New print contains more than one print!");
      return FPI_MATCH_ERROR;
    }

  pstruct = g_ptr_array_index (print->prints, 0);
  probe_len = bozorth_probe_init (pstruct);

  for (i = 0; i < print_template->prints->len; i++)
    {
      struct xyt_struct *gstruct;
      gint score;
      gstruct = g_ptr_array_index (print_template->prints, i);
      score = bozorth_to_gallery (probe_len, pstruct, gstruct);
      fp_dbg ("score %d/%d", score, bz3_threshold);

      if (score >= bz3_threshold)
        return FPI_MATCH_SUCCESS;
    }

  return FPI_MATCH_FAIL;
}

#ifdef GOODIX_LIBFPRINT_SIGFM
/**
 * fpi_print_add_sigfm_sample:
 * @print: A #FPI_PRINT_SIGFM print
 * @sample: A validated SIGFM sample
 * @error: Return location for error
 *
 * Copies @sample into @print. The caller retains ownership of @sample.
 *
 * Returns: %TRUE on success
 */
gboolean
fpi_print_add_sigfm_sample (FpPrint                 *print,
                            const GoodixSigfmSample *sample,
                            GError                 **error)
{
  GoodixSigfmSample *copy = NULL;
  GoodixSigfmResult result;

  if (!FP_IS_PRINT (print) || print->type != FPI_PRINT_SIGFM || !sample ||
      print->prints == NULL)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT,
                           "Cannot add a SIGFM sample to this print");
      return FALSE;
    }
  if (print->prints->len >= GOODIX_SIGFM_MAX_PRINT_SAMPLES)
    {
      g_set_error_literal (error, G_IO_ERROR, G_IO_ERROR_NO_SPACE,
                           "SIGFM template already has the maximum sample count");
      return FALSE;
    }

  result = goodix_sigfm_sample_copy (sample, &copy);
  if (result != GOODIX_SIGFM_OK)
    {
      g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                   "Could not copy SIGFM sample (result %d)", result);
      return FALSE;
    }

  g_ptr_array_add (print->prints, copy);
  return TRUE;
}

/**
 * fpi_print_sigfm_match:
 * @print_template: A SIGFM print containing one or more enrollment samples
 * @print: A SIGFM print containing exactly one probe sample
 * @score_threshold: The SIGFM score threshold
 * @error: Return location for error
 *
 * Returns: Whether any enrollment sample matches, or #FPI_MATCH_ERROR
 */
FpiMatchResult
fpi_print_sigfm_match (FpPrint *print_template,
                       FpPrint *print,
                       gint     score_threshold,
                       GError **error)
{
  GoodixSigfmSample *probe;

  if (!FP_IS_PRINT (print_template) || !FP_IS_PRINT (print) ||
      print_template->type != FPI_PRINT_SIGFM ||
      print->type != FPI_PRINT_SIGFM)
    {
      g_set_error_literal (error, FP_DEVICE_ERROR,
                           FP_DEVICE_ERROR_NOT_SUPPORTED,
                           "SIGFM matching requires two SIGFM prints");
      return FPI_MATCH_ERROR;
    }
  if (!print_template->prints || print_template->prints->len == 0 ||
      print_template->prints->len > GOODIX_SIGFM_MAX_PRINT_SAMPLES ||
      !print->prints || print->prints->len != 1 || score_threshold <= 0)
    {
      g_set_error_literal (error, FP_DEVICE_ERROR,
                           FP_DEVICE_ERROR_DATA_INVALID,
                           "Invalid SIGFM template, probe, or threshold");
      return FPI_MATCH_ERROR;
    }

  probe = g_ptr_array_index (print->prints, 0);
  g_message ("GOODIX_SIGFM_MATCH_AUDIT event=start template_samples=%u threshold=%d",
             print_template->prints->len, score_threshold);
  for (guint i = 0; i < print_template->prints->len; i++)
    {
      GoodixSigfmSample *enrolled =
        g_ptr_array_index (print_template->prints, i);
      GoodixSigfmResult result;
      gint score = 0;

      result = goodix_sigfm_match_ephemeral (probe, enrolled, &score);
      if (result != GOODIX_SIGFM_OK)
        {
          g_message ("GOODIX_SIGFM_MATCH_AUDIT event=error sample=%u result=%d",
                     i + 1, result);
          g_set_error (error, FP_DEVICE_ERROR, FP_DEVICE_ERROR_DATA_INVALID,
                       "SIGFM matcher failed (result %d)", result);
          return FPI_MATCH_ERROR;
        }
      g_message ("GOODIX_SIGFM_MATCH_AUDIT event=comparison sample=%u score=%d threshold=%d",
                 i + 1, score, score_threshold);
      if (score >= score_threshold)
        {
          g_message ("GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match matched_sample=%u comparisons=%u threshold=%d",
                     i + 1, i + 1, score_threshold);
          return FPI_MATCH_SUCCESS;
        }
    }

  g_message ("GOODIX_SIGFM_MATCH_AUDIT event=outcome result=no_match matched_sample=0 comparisons=%u threshold=%d",
             print_template->prints->len, score_threshold);
  return FPI_MATCH_FAIL;
}
#endif

/**
 * fpi_print_generate_user_id:
 * @print: #FpPrint to generate the ID for
 *
 * Generates a string identifier for the represented print. This identifier
 * encodes some metadata about the print. It also includes a random string
 * and may be assumed to be unique.
 *
 * This is useful if devices are able to store a string identifier, but more
 * storing more metadata may be desirable. In effect, this means the driver
 * can provide somewhat more meaningful data to fp_device_list_prints().
 *
 * The generated ID may be truncated after 23 characters. However, more space
 * is required to include the username, and it is recommended to store at
 * at least 31 bytes.
 *
 * The generated format may change in the future. It is versioned though and
 * decoding should remain functional.
 *
 * Returns: A unique string of 23 + strlen(username) characters
 */
gchar *
fpi_print_generate_user_id (FpPrint *print)
{
  const gchar *username = NULL;
  gchar *user_id = NULL;
  const GDate *date;
  gint y = 0, m = 0, d = 0;
  gint32 rand_id = 0;

  g_assert (print);
  date = fp_print_get_enroll_date (print);
  if (date && g_date_valid (date))
    {
      y = g_date_get_year (date);
      m = g_date_get_month (date);
      d = g_date_get_day (date);
    }

  username = fp_print_get_username (print);
  if (!username)
    username = "nobody";

  if (fpi_device_emulation_mode_enabled (NULL))
    rand_id = 0;
  else
    rand_id = g_random_int ();

  user_id = g_strdup_printf ("FP1-%04d%02d%02d-%X-%08X-%s",
                             y, m, d,
                             fp_print_get_finger (print),
                             rand_id,
                             username);

  return user_id;

}

/**
 * fpi_print_fill_from_user_id:
 * @print: #FpPrint to fill metadata into
 * @user_id: An ID that was likely encoded using fpi_print_generate_user_id()
 *
 * This is the reverse operation of fpi_print_generate_user_id(), allowing
 * the driver to encode some print metadata in a string.
 *
 * Returns: Whether a valid ID was found
 */
gboolean
fpi_print_fill_from_user_id (FpPrint *print, const char *user_id)
{
  g_return_val_if_fail (user_id, FALSE);

  /* The format has 24 bytes at the start and some dashes in the right places */
  if (g_str_has_prefix (user_id, "FP1-") && strlen (user_id) >= 24 &&
      user_id[12] == '-' && user_id[14] == '-' && user_id[23] == '-')
    {
      g_autofree gchar *copy = g_strdup (user_id);
      g_autoptr(GDate) date = NULL;
      gint32 date_ymd;
      gint32 finger;
      gchar *username;
      /* Try to parse information from the string. */

      copy[12] = '\0';
      date_ymd = g_ascii_strtod (copy + 4, NULL);
      if (date_ymd > 0)
        date = g_date_new_dmy (date_ymd % 100,
                               (date_ymd / 100) % 100,
                               date_ymd / 10000);
      else
        date = g_date_new ();

      fp_print_set_enroll_date (print, date);

      copy[14] = '\0';
      finger = g_ascii_strtoll (copy + 13, NULL, 16);
      fp_print_set_finger (print, finger);

      /* We ignore the next chunk, it is just random data.
       * Then comes the username; nobody is the default if the metadata
       * is unknown */
      username = copy + 24;
      if (strlen (username) > 0 && g_strcmp0 (username, "nobody") != 0)
        fp_print_set_username (print, username);

      return TRUE;
    }

  return FALSE;
}
