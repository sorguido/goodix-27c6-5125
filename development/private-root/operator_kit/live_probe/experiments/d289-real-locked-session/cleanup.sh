#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ ${1:-} == --phase && ${2:-} == cleanup ]]
! mountpoint -q /etc/pam.d/kde-fingerprint
[[ ! -e /run/goodix-d289-real-lock-$(id -u) ]]
echo D289_ROOT_OVERLAY_RESIDUAL=false
echo D289_CLEANUP=PASS
