/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef GOODIX_TEST_SIGFM_CONTROL_H
#define GOODIX_TEST_SIGFM_CONTROL_H

#include <glib.h>

G_BEGIN_DECLS

void     goodix_test_sigfm_extract_set_block   (gboolean block);
void     goodix_test_sigfm_extract_unblock     (void);
gboolean goodix_test_sigfm_extract_is_blocked  (void);

G_END_DECLS

#endif
