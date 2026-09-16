#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ ${1:-} == --phase && ${2:-} == cleanup ]]
if [[ ${LIVE_PROBE_MODE:-} == offline-test ]]; then
  echo D293_04_CLEANUP=PASS_OFFLINE
  exit 0
fi

public=${D293_04_PUBLIC_ROOT:-/run/goodix-d293-04-public}
work=${LIVE_PROBE_WORK_DIR:?}
fail() { printf 'D293_04_CLEANUP=FAIL reason=%s\n' "$1" >&2; exit 1; }
one() {
  local key=$1 file=$2 values
  [[ -f $file && ! -L $file ]] || return 1
  values=$(sed -n "s/^${key}=//p" "$file")
  [[ $(printf '%s\n' "$values" | sed '/^$/d' | wc -l) -eq 1 && -n $values ]] || return 1
  printf '%s\n' "$values"
}

if [[ -f $work/kcm.pid ]]; then
  pid=$(<"$work/kcm.pid")
  if [[ $pid =~ ^[1-9][0-9]*$ && -r /proc/$pid/status &&
        $(awk '/^Uid:/ {print $2}' "/proc/$pid/status") == "$(id -u)" &&
        $(<"/proc/$pid/comm") == systemsettings ]]; then
    kill "$pid" 2>/dev/null || true
  fi
fi
[[ -d $public/control && -O $public/control ]] || fail control_channel_unavailable
[[ ! -e $public/control/release && ! -L $public/control/release ]] || fail release_collision
: >"$public/control/release"
for _ in $(seq 1 300); do
  [[ -f $public/rollback.env && ! -L $public/rollback.env ]] && break
  sleep 0.1
done
[[ -f $public/rollback.env && ! -L $public/rollback.env ]] || fail rollback_result_timeout
[[ $(one D293_04_RUNTIME_ROLLBACK "$public/rollback.env") == PASS ]] || fail runtime_rollback
[[ $(one D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED "$public/rollback.env") == true ]] ||
  fail existing_principal_drift
[[ $(one D293_04_TEST_STORAGE "$public/rollback.env") == PASS ]] || fail test_storage_remains
[[ $(one D293_04_D285_D286_POST_ROLLBACK "$public/rollback.env") == PASS ]] || fail d285_d286_post_rollback
echo D293_04_RUNTIME_ROLLBACK=PASS
echo D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=true
echo D293_04_TEST_STORAGE_CLEAN=true
echo D293_04_CLEANUP=PASS
