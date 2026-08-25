/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef SIGFM_METRIC_TEST_DOUBLE_H
#define SIGFM_METRIC_TEST_DOUBLE_H

enum SigfmTestMode
{
  SIGFM_TEST_OK = 0,
  SIGFM_TEST_EXTRACT_NULL,
  SIGFM_TEST_EXTRACT_THROW,
  SIGFM_TEST_MATCH_THROW,
};

void sigfm_test_set_mode (enum SigfmTestMode mode);
void sigfm_test_set_keypoints (int keypoints);
void sigfm_test_set_score (int score);
int sigfm_test_last_width (void);
int sigfm_test_last_height (void);
unsigned int sigfm_test_last_pixel (unsigned int index);
int sigfm_test_live_info_count (void);

#endif
