#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

package=goodix-27c6-5125-runtime
state=/var/lib/goodix-27c6-5125-phase-c-runtime.state
d293_wrapper=/usr/local/sbin/goodix-d293-native-fprintd
d293_dropin=/etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf
b5_hook=/etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete

fail() {
  printf 'D294_01_ROLLBACK=FAIL reason=%s\n' "$1" >&2
  exit 1
}

state_value() {
  local key=$1 count value
  count=$(awk -F= -v key="$key" '$1 == key { count++ } END { print count + 0 }' "$state")
  [[ $count -eq 1 ]] || return 1
  value=$(awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print }' "$state")
  [[ $value != *$'\n'* ]] || return 1
  printf '%s\n' "$value"
}

digest() { sha256sum "$1" | awk '{print $1}'; }

if [[ ${1:-} == --root-uninstall ]]; then
  [[ $# -eq 2 ]] || fail root_usage
  caller=$2
  [[ $EUID -eq 0 ]] || fail root_required
  [[ ${SUDO_USER:-} == "$caller" && $caller =~ ^[a-z_][a-z0-9_-]*$ ]] ||
    fail caller_invalid
  [[ -f $state && ! -L $state && $(stat -c %a "$state") == 600 ]] || fail state_invalid
  rpm -q "$package" >/dev/null || fail package_missing
  [[ $(state_value D294_01_STATUS) == ACTIVE ]] || fail state_inactive
  [[ $(state_value D294_01_INSTALLER) == "$caller" ]] || fail installer_mismatch
  source_commit=$(state_value D294_01_SOURCE_COMMIT) || fail state_provenance_invalid
  [[ $source_commit =~ ^[0-9a-f]{40}$ ]] || fail state_provenance_invalid
  rpm -q --provides "$package" |
    grep -Fx "goodix-27c6-5125-runtime-commit($source_commit)" >/dev/null ||
    fail installed_package_drift
  rpm -V "$package" >/dev/null || fail installed_package_file_drift
  service_before=$(state_value D294_01_SERVICE_BEFORE) || fail state_service_invalid
  features_before=$(state_value D294_01_OPENCV_FEATURES2D_BEFORE) || fail state_dependency_invalid
  flann_before=$(state_value D294_01_OPENCV_FLANN_BEFORE) || fail state_dependency_invalid
  unit_before=$(state_value D294_01_UNIT_BEFORE_SHA256) || fail state_unit_invalid
  d293_wrapper_sha=$(state_value D294_01_D293_WRAPPER_SHA256) || fail state_d293_invalid
  d293_dropin_sha=$(state_value D294_01_D293_DROPIN_SHA256) || fail state_d293_invalid
  b5_hook_sha=$(state_value D294_01_B5_HOOK_SHA256) || fail state_b5_invalid
  [[ $service_before == active || $service_before == inactive ]] || fail state_service_invalid
  [[ $features_before == true || $features_before == false ]] || fail state_dependency_invalid
  [[ $flann_before == true || $flann_before == false ]] || fail state_dependency_invalid
  for value in "$unit_before" "$d293_wrapper_sha" "$d293_dropin_sha" "$b5_hook_sha"; do
    [[ $value =~ ^[0-9a-f]{64}$ ]] || fail state_hash_invalid
  done
  [[ -f $d293_wrapper && ! -L $d293_wrapper && $(digest "$d293_wrapper") == "$d293_wrapper_sha" ]] ||
    fail d293_wrapper_drift
  [[ -f $d293_dropin && ! -L $d293_dropin && $(digest "$d293_dropin") == "$d293_dropin_sha" ]] ||
    fail d293_dropin_drift
  [[ -f $b5_hook && ! -L $b5_hook && $(digest "$b5_hook") == "$b5_hook_sha" ]] ||
    fail b5_hook_drift
  restore_service() {
    rc=$?
    systemctl daemon-reload >/dev/null 2>&1 || true
    if [[ $service_before == active ]]; then
      systemctl start fprintd.service >/dev/null 2>&1 || true
    fi
    exit "$rc"
  }
  trap restore_service EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  systemctl stop fprintd.service
  [[ $(systemctl is-active fprintd.service || true) == inactive ]] || fail service_stop_failed
  remove_packages=("$package")
  if [[ $features_before == false ]]; then
    remove_packages+=(opencv-features2d)
  fi
  if [[ $flann_before == false ]]; then
    remove_packages+=(opencv-flann)
  fi
  rpm -e "${remove_packages[@]}" || fail rpm_remove_failed
  systemctl daemon-reload
  [[ $(systemctl cat fprintd.service | sha256sum | awk '{print $1}') == "$unit_before" ]] ||
    fail d293_unit_not_restored_exact
  [[ $(digest "$d293_wrapper") == "$d293_wrapper_sha" &&
     $(digest "$d293_dropin") == "$d293_dropin_sha" ]] || fail d293_fallback_changed
  [[ $(digest "$b5_hook") == "$b5_hook_sha" ]] || fail d293_b5_changed
  if [[ $service_before == active ]]; then
    systemctl start fprintd.service
  fi
  systemctl show -p ExecStart --value fprintd.service |
    grep -F /usr/local/sbin/goodix-d293-native-fprintd >/dev/null ||
    fail d293_execstart_not_restored
  [[ $(systemctl is-active fprintd.service || true) == "$service_before" ]] ||
    fail service_state_changed
  rm -f -- "$state"
  trap - EXIT INT TERM
  echo D294_01_ROLLBACK=PASS
  echo D294_01_D293_BASELINE=RESTORED
  echo D294_01_D293_B5=PRESERVED
  exit 0
fi

[[ $# -eq 0 ]] || fail usage
[[ $EUID -ne 0 ]] || fail entrypoint_must_be_unprivileged
caller=$(id -un)
[[ $caller =~ ^[a-z_][a-z0-9_-]*$ ]] || fail caller_invalid
sudo -- "$0" --root-uninstall "$caller"
