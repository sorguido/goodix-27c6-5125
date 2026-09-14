#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

package=goodix-27c6-5125-runtime
state=/var/lib/goodix-27c6-5125-phase-c-runtime.state

fail() {
  printf 'D294_01_ROLLBACK=FAIL reason=%s\n' "$1" >&2
  exit 1
}

if [[ ${1:-} == --root-uninstall ]]; then
  [[ $# -eq 2 ]] || fail root_usage
  caller=$2
  [[ $EUID -eq 0 ]] || fail root_required
  [[ ${SUDO_USER:-} == "$caller" && $caller =~ ^[a-z_][a-z0-9_-]*$ ]] ||
    fail caller_invalid
  [[ -f $state && ! -L $state && $(stat -c %a "$state") == 600 ]] || fail state_invalid
  rpm -q "$package" >/dev/null || fail package_missing
  source_commit=$(awk -F= '$1=="D294_01_SOURCE_COMMIT" {print $2}' "$state")
  [[ $source_commit =~ ^[0-9a-f]{40}$ ]] || fail state_provenance_invalid
  rpm -q --provides "$package" |
    grep -Fx "goodix-27c6-5125-runtime-commit($source_commit)" >/dev/null ||
    fail installed_package_drift
  service_before=$(awk -F= '$1=="D294_01_SERVICE_BEFORE" {print $2}' "$state")
  features_before=$(awk -F= '$1=="D294_01_OPENCV_FEATURES2D_BEFORE" {print $2}' "$state")
  flann_before=$(awk -F= '$1=="D294_01_OPENCV_FLANN_BEFORE" {print $2}' "$state")
  [[ $service_before == active || $service_before == inactive ]] || fail state_service_invalid
  [[ $features_before == true || $features_before == false ]] || fail state_dependency_invalid
  [[ $flann_before == true || $flann_before == false ]] || fail state_dependency_invalid
  restore_service() {
    rc=$?
    systemctl daemon-reload >/dev/null 2>&1 || true
    if [[ $service_before == active ]]; then
      systemctl start fprintd.service >/dev/null 2>&1 || true
    fi
    exit "$rc"
  }
  trap restore_service EXIT INT TERM
  systemctl stop fprintd.service || true
  dnf5 remove -y "$package" || fail dnf_remove_failed
  if [[ $features_before == false ]]; then
    dnf5 remove -y opencv-features2d || fail features2d_cleanup_failed
  fi
  if [[ $flann_before == false ]]; then
    dnf5 remove -y opencv-flann || fail flann_cleanup_failed
  fi
  systemctl daemon-reload
  [[ -x /usr/local/sbin/goodix-d293-native-fprintd &&
     -f /etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf ]] ||
    fail d293_fallback_missing
  [[ -x /etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete ]] ||
    fail d293_b5_fallback_missing
  if [[ $service_before == active ]]; then
    systemctl start fprintd.service
  fi
  systemctl show -p ExecStart --value fprintd.service |
    grep -F /usr/local/sbin/goodix-d293-native-fprintd >/dev/null ||
    fail d293_execstart_not_restored
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
