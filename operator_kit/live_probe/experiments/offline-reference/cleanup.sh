#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ ${1:-} == --phase && ${2:-} == cleanup ]]
echo LIVE_PROBE_OFFLINE_CLEANUP=PASS
