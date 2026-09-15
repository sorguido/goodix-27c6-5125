#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
repo=$(git -C "$here" rev-parse --show-toplevel)
target=/etc/pam.d/kde-fingerprint
state=/var/lib/goodix-d297-01-kscreenlocker
expected_vendor=8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437
expected_managed=858713e5b3b7ecf58a91f6fe5b736f344aa6c5b9c207318e6ac552a1a3ffb3d1
expected_fingerprint_auth=9e0ea3820ffe5b6ff6f4cea4896b40e244077830538ea824911759095f8b4a8a
expected_plasmalogin=559910be8631f69398332b2979bd5c18f1155a7af0960215d175694082cae2ac
expected_d293_dropin=91432adc0299628455f98772a42341b7b1fccc432fd85fcb1928eafa75523247
expected_d293_wrapper=ea0f5c0ebc2bb9524943fef0921f2d0ff845380d35d43d7112c3d0df357f78d2
rule='auth        required      pam_fprintd.so max-tries=3 timeout=45'
mode=${1:-}

fail() { printf 'D297_01_KSCREENLOCKER_INSTALL=FAIL reason=%s\n' "$1" >&2; exit 1; }
digest() { sha256sum "$1" | awk '{print $1}'; }
[[ $mode == --check || -z $mode ]] || fail usage_install_or_check
[[ $(git -C "$repo" branch --show-current) == development ]] || fail wrong_branch
head=$(git -C "$repo" rev-parse HEAD)
[[ $head == "$(git -C "$repo" rev-parse origin/development)" ]] || fail origin_head_mismatch
[[ -z $(git -C "$repo" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
[[ $(. /etc/os-release; printf '%s' "${VERSION_ID:-}") == 44 ]] || fail unsupported_target_os
[[ $(rpm -q plasma-workspace) == plasma-workspace-6.7.5-1.fc44.x86_64 ]] || fail plasma_workspace_nevra_drift
[[ $(rpm -q kscreenlocker) == kscreenlocker-6.7.5-1.fc44.x86_64 ]] || fail kscreenlocker_nevra_drift
[[ $(rpm -q fprintd-pam) == fprintd-pam-1.94.5-5.fc44.x86_64 ]] || fail fprintd_pam_nevra_drift
[[ ! -e /var/lib/goodix-27c6-5125-managed/state && \
   ! -e /usr/lib64/goodix-27c6-5125/current && \
   ! -e /etc/systemd/system/fprintd.service.d/99-goodix-27c6-5125-managed.conf ]] ||
  fail managed_candidate_deployment_detected
[[ -f /etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf && \
   $(digest /etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf) == "$expected_d293_dropin" ]] ||
  fail historical_d293_dropin_drift
[[ -f /usr/local/sbin/goodix-d293-native-fprintd && \
   $(digest /usr/local/sbin/goodix-d293-native-fprintd) == "$expected_d293_wrapper" ]] ||
  fail historical_d293_wrapper_drift
[[ -f /usr/lib/pam.d/plasmalogin && $(digest /usr/lib/pam.d/plasmalogin) == "$expected_plasmalogin" ]] ||
  fail historical_plasmalogin_pam_drift
[[ -f /etc/pam.d/fingerprint-auth && $(digest /etc/pam.d/fingerprint-auth) == "$expected_fingerprint_auth" ]] ||
  fail fingerprint_auth_global_stack_drift
[[ -f $target && ! -L $target && $(digest "$target") == "$expected_vendor" ]] ||
  fail kde_fingerprint_vendor_drift
rpm_digest=$(rpm -q --dump plasma-workspace | awk '$1 == "/etc/pam.d/kde-fingerprint" { print $4 }')
[[ $rpm_digest == "$expected_vendor" ]] || fail kde_fingerprint_rpm_digest_drift
flags=$(rpm -q --qf '[%{FILENAMES}\t%{FILEFLAGS}\n]' plasma-workspace |
  awk -F '\t' '$1 == "/etc/pam.d/kde-fingerprint" { print $2 }')
[[ $flags == 17 ]] || fail kde_fingerprint_not_config_noreplace
[[ ! -e $target.rpmnew && ! -e $target.rpmsave ]] || fail package_upgrade_artifact_present
[[ ! -e $state && ! -L $state ]] || fail corrective_state_collision

work=$(mktemp -d /tmp/goodix-d297-01-kscreenlocker.XXXXXX)
cleanup_work() { find "$work" -xdev -depth -delete; }
trap cleanup_work EXIT
awk -v rule="$rule" '
  /^[[:space:]]*auth[[:space:]]+substack[[:space:]]+fingerprint-auth[[:space:]]*$/ && !replaced {
    print rule; replaced=1; next
  }
  { print }
  END { if (!replaced) exit 1 }
' "$target" >"$work/kde-fingerprint" || fail pam_generation_failed
[[ $(digest "$work/kde-fingerprint") == "$expected_managed" ]] || fail generated_pam_digest_mismatch
[[ $(grep -Fxc "$rule" "$work/kde-fingerprint") -eq 1 ]] || fail generated_pam_rule_invalid

if [[ $mode == --check ]]; then
  printf '%s\n' 'D297_01_KSCREENLOCKER_CHECK=PASS' \
    'ACTIVE_HOST_DEPLOYMENT_MODE=HISTORICAL_D293_RUNTIME' \
    'HISTORICAL_RUNTIME_REPLACED_AS_SIDE_EFFECT=false' \
    'AUTHSELECT_GLOBAL_FINGERPRINT_UNCHANGED=true' \
    'FINGERPRINT_AUTH_GLOBAL_STACK_UNCHANGED=true' \
    "SOURCE_COMMIT=$head"
  exit 0
fi

[[ $EUID -eq 0 ]] || fail root_required_use_sudo
[[ $(stat -c '%u:%g:%a' "$target") == 0:0:644 ]] || fail kde_fingerprint_metadata_drift
rollback_on_error() {
  local rc=$?
  set +e
  if [[ $rc -ne 0 && -d $state && ! -L $state ]]; then
    if [[ -f $state/kde-fingerprint.vendor ]]; then
      install -m 0644 "$state/kde-fingerprint.vendor" "$target"
      restorecon -F "$target"
    fi
    find "$state" -xdev -depth -delete
  fi
  cleanup_work
  exit "$rc"
}
trap rollback_on_error EXIT
install -d -m 0700 "$state"
install -m 0644 "$target" "$state/kde-fingerprint.vendor"
install -m 0644 "$work/kde-fingerprint" "$state/kde-fingerprint.managed"
printf '%s\n' \
  "SOURCE_COMMIT=$head" \
  "VENDOR_SHA256=$expected_vendor" \
  "MANAGED_SHA256=$expected_managed" \
  'ACTIVE_HOST_DEPLOYMENT_MODE=HISTORICAL_D293_RUNTIME' \
  >"$state/state"
chmod 0600 "$state/state"
install -m 0644 "$state/kde-fingerprint.managed" "$target"
restorecon -F "$target"
[[ $(digest "$target") == "$expected_managed" ]] || fail installed_pam_digest_mismatch
printf '%s\n' 'D297_01_KSCREENLOCKER_INSTALL=PASS' \
  'ACTIVE_HOST_DEPLOYMENT_MODE=HISTORICAL_D293_RUNTIME' \
  'HISTORICAL_RUNTIME_REPLACED_AS_SIDE_EFFECT=false' \
  'AUTHSELECT_GLOBAL_FINGERPRINT_UNCHANGED=true' \
  'FINGERPRINT_AUTH_GLOBAL_STACK_UNCHANGED=true' \
  'MAX_PHYSICAL_ATTEMPTS=3' 'STOP_ON_FIRST_MATCH=true'
trap - EXIT
cleanup_work
