#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

[[ $# -ge 1 ]]
mode=$1
if [[ $mode == --hold ]]; then
  [[ $# -eq 7 && $2 == --control-fifo && $4 == --owner-pid && $6 == --owner-start-time ]]
  control_fifo=$3
  owner_pid=$5
  owner_start_time=$7
elif [[ $mode == --recover ]]; then
  [[ $# -eq 1 ]]
  control_fifo=
  owner_pid=
  owner_start_time=
else
  exit 2
fi
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
target=/usr/lib/pam.d/plasmalogin
candidate=$here/goodix-d290-plasmalogin.pam
expected_host=c6fc4a0bc2d89f88fa15ca7e9a6c5aaeccfbe66897755b5416ce9c5e35b4e40b
expected_candidate=89d389e6c2ee59dcee374029a5428a81dc9138c4f5e86068159b3d5a2c77ab2d
operator_uid=${PKEXEC_UID:-}
runtime=
expected_runtime=
mounted=false
control_watchdog_pid=
# shellcheck source=root-overlay-lib.sh
source "$here/root-overlay-lib.sh"

on_exit () {
  local rc=$?
  trap - EXIT
  d290_cleanup_overlay || rc=1
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' HUP INT TERM

[[ $EUID -eq 0 && $operator_uid =~ ^[1-9][0-9]*$ ]]
runtime=/run/goodix-d290-plasmalogin-$operator_uid
expected_runtime=$runtime
if [[ $mode == --recover ]]; then
  d290_recover_overlay
  exit 0
fi

d290_hold_overlay
