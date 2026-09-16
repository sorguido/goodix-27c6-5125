#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ ${1:-} == --phase && ${2:-} == cleanup ]]
pid_file=${LIVE_PROBE_WORK_DIR:?}/greeter.pid
if [[ -f $pid_file ]]; then
  pid=$(<"$pid_file")
  if [[ $pid =~ ^[0-9]+$ ]]; then
    kill -TERM -- "-$pid" 2>/dev/null || true
    for _ in {1..25}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
    kill -KILL -- "-$pid" 2>/dev/null || true
    for _ in {1..10}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
    wait "$pid" 2>/dev/null || true
    ! kill -0 "$pid" 2>/dev/null
  fi
  rm -f -- "$pid_file"
fi
echo D288_GREETER_CLEANUP=PASS
