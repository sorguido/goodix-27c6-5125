#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
capture=${1:?}
grep -Fx LIVE_PROBE_COMMON_CLASSIFICATION=PASS "$capture/common-classification.env" >/dev/null
grep -Fx LIVE_PROBE_OFFLINE_REFERENCE_PAYLOAD=PASS "$capture/payload.log" >/dev/null
grep -Fx LIVE_PROBE_OFFLINE_PRE_AUDIT=PASS "$capture/pre-audit.log" >/dev/null
grep -Fx LIVE_PROBE_OFFLINE_POST_AUDIT=PASS "$capture/post-audit.log" >/dev/null
grep -Fx LIVE_PROBE_OFFLINE_CLEANUP=PASS "$capture/cleanup.log" >/dev/null
echo LIVE_PROBE_OFFLINE_REFERENCE_CLASSIFICATION=PASS
