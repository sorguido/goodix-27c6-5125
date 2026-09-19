/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_TEST_SIGFM_CONTROL_H
#define GOODIX_TEST_SIGFM_CONTROL_H

#include <glib.h>

G_BEGIN_DECLS

void     goodix_test_sigfm_extract_set_block   (gboolean block);
void     goodix_test_sigfm_extract_set_failure (gboolean fail);
void     goodix_test_sigfm_match_use_content   (gboolean enabled);
void     goodix_test_sigfm_match_set_score     (gint score);
void     goodix_test_sigfm_match_reset_audit   (void);
guint    goodix_test_sigfm_match_get_call_count (void);
guint64  goodix_test_sigfm_match_get_enrolled_signature (guint index);
guint64  goodix_test_sigfm_match_get_probe_signature (guint index);
void     goodix_test_sigfm_extract_unblock     (void);
gboolean goodix_test_sigfm_extract_is_blocked  (void);
gboolean goodix_test_sigfm_extract_wait_blocked (gint64 timeout_us);

G_END_DECLS

#endif
