#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ ${1:-} == --phase && ${2:-} == cleanup ]]
if mountpoint -q /usr/lib/pam.d/plasmalogin; then
  exit 1
fi
[[ ! -e /run/goodix-d290-plasmalogin-$(id -u) ]]
echo D290_ROOT_OVERLAY_RESIDUAL=false
echo D290_CLEANUP=PASS
