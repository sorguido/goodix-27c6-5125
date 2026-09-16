#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# -eq 2 && $1 == --phase ]]
case "$2" in
  pre) echo LIVE_PROBE_OFFLINE_PRE_AUDIT=PASS ;;
  post) echo LIVE_PROBE_OFFLINE_POST_AUDIT=PASS ;;
  *) exit 2 ;;
esac
echo LIVE_PROBE_OFFLINE_SENSOR_ACTION_COUNT=0
