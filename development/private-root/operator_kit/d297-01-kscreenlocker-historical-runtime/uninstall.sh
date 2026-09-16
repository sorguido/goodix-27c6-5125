#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

target=/etc/pam.d/kde-fingerprint
state=/var/lib/goodix-d297-01-kscreenlocker
expected_vendor=8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437
expected_managed=858713e5b3b7ecf58a91f6fe5b736f344aa6c5b9c207318e6ac552a1a3ffb3d1
expected_fingerprint_auth=9e0ea3820ffe5b6ff6f4cea4896b40e244077830538ea824911759095f8b4a8a

fail() { printf 'D297_01_KSCREENLOCKER_UNINSTALL=FAIL reason=%s\n' "$1" >&2; exit 1; }
digest() { sha256sum "$1" | awk '{print $1}'; }
[[ $# -eq 0 ]] || fail usage_uninstall
[[ $EUID -eq 0 ]] || fail root_required_use_sudo
[[ -d $state && ! -L $state && $(stat -c '%u:%g:%a' "$state") == 0:0:700 ]] || fail state_invalid
[[ -f $state/state && ! -L $state/state && $(stat -c '%u:%g:%a' "$state/state") == 0:0:600 ]] || fail state_file_invalid
[[ -f $state/kde-fingerprint.vendor && ! -L $state/kde-fingerprint.vendor && \
   $(digest "$state/kde-fingerprint.vendor") == "$expected_vendor" ]] || fail vendor_backup_drift
[[ -f $state/kde-fingerprint.managed && ! -L $state/kde-fingerprint.managed && \
   $(digest "$state/kde-fingerprint.managed") == "$expected_managed" ]] || fail managed_backup_drift
[[ -f $target && ! -L $target && $(digest "$target") == "$expected_managed" ]] || fail installed_pam_drift
[[ -f /etc/pam.d/fingerprint-auth && $(digest /etc/pam.d/fingerprint-auth) == "$expected_fingerprint_auth" ]] ||
  fail fingerprint_auth_global_stack_drift
rpm_digest=$(rpm -q --dump plasma-workspace | awk '$1 == "/etc/pam.d/kde-fingerprint" { print $4 }')
[[ $rpm_digest == "$expected_vendor" ]] || fail kde_fingerprint_rpm_digest_drift
[[ ! -e $target.rpmnew && ! -e $target.rpmsave ]] || fail package_upgrade_artifact_present
install -m 0644 "$state/kde-fingerprint.vendor" "$target"
restorecon -F "$target"
[[ $(digest "$target") == "$expected_vendor" ]] || fail vendor_restore_failed
rm -f -- "$state/kde-fingerprint.managed" "$state/kde-fingerprint.vendor" "$state/state"
rmdir -- "$state"
printf '%s\n' 'D297_01_KSCREENLOCKER_UNINSTALL=PASS' \
  'KDE_FINGERPRINT_VENDOR_RESTORED=true' \
  'HISTORICAL_D293_RUNTIME_UNCHANGED=true' \
  'FINGERPRINT_AUTH_GLOBAL_STACK_UNCHANGED=true'
