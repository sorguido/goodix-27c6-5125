#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ ${1:-} == --phase && ${2:-} == cleanup ]]
if [[ ${LIVE_PROBE_MODE:-} == offline-test ]]; then
  echo D293_04_CLEANUP=PASS_OFFLINE
  exit 0
fi
public=/run/goodix-d293-04-public
work=${LIVE_PROBE_WORK_DIR:?}
if [[ -f $work/kcm.pid ]]; then
  pid=$(<"$work/kcm.pid")
  if [[ $pid =~ ^[1-9][0-9]*$ && -r /proc/$pid/status &&
        $(awk '/^Uid:/ {print $2}' "/proc/$pid/status") == "$(id -u)" ]]; then
    kill "$pid" 2>/dev/null || true
  fi
fi
if [[ -d $public/control && -O $public/control ]]; then
  : >"$public/control/release"
fi
for _ in $(seq 1 300); do
  [[ -f $public/rollback.env ]] && break
  sleep 0.1
done
[[ -f $public/rollback.env ]]
grep -Fx D293_04_RUNTIME_ROLLBACK=PASS "$public/rollback.env" >/dev/null
grep -Fx D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=true "$public/rollback.env" >/dev/null
grep -Fx D293_04_TEST_STORAGE=PASS "$public/rollback.env" >/dev/null
echo D293_04_RUNTIME_ROLLBACK=PASS
echo D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=true
echo D293_04_TEST_STORAGE_CLEAN=true
echo D293_04_CLEANUP=PASS
