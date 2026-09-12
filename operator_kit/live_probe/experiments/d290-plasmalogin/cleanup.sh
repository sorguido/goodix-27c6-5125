#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ ${1:-} == --phase && ${2:-} == cleanup ]]
! mountpoint -q /usr/lib/pam.d/plasmalogin
[[ ! -e /run/goodix-d290-plasmalogin-$(id -u) ]]
echo D290_ROOT_OVERLAY_RESIDUAL=false
echo D290_CLEANUP=PASS
