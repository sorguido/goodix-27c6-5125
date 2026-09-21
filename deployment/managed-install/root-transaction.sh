#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
test_root=${GOODIX_MANAGED_TEST_ROOT:-}
if [[ -n $test_root ]]; then
  [[ $test_root == /tmp/goodix-managed-test.* && -d $test_root && -O $test_root && ! -L $test_root ]] || {
    echo 'GOODIX_MANAGED_TRANSACTION=FAIL reason=unsafe_test_root' >&2; exit 1;
  }
  repo=
else
  repo=$(git -C "$here" rev-parse --show-toplevel)
fi
p() { printf '%s%s\n' "$test_root" "$1"; }

state_dir=$(p /var/lib/goodix-27c6-5125-managed)
state=$state_dir/state
runtime_root=$(p /usr/lib64/goodix-27c6-5125)
current_link=$runtime_root/current
wrapper=$(p /usr/libexec/goodix-27c6-5125/fprintd-wrapper)
dropin=$(p /etc/systemd/system/fprintd.service.d/99-goodix-27c6-5125-managed.conf)
greeter_dropin=$(p /etc/systemd/user/plasma-login.service.d/99-goodix-login-greeter.conf)
greeter_directory_created=false
plasma_dropin=$(p /etc/systemd/system/plasmalogin.service.d/99-goodix-plasma-vt.conf)
plasma_directory_created=false
plasma_service_before=inactive
hook=$(p /etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete)
vendor_pam=$(p /usr/lib/pam.d/plasmalogin)
managed_pam=$(p /etc/pam.d/plasmalogin)
pam_saved=$state_dir/plasmalogin.managed
kde_fingerprint_pam=$(p /etc/pam.d/kde-fingerprint)
kde_fingerprint_vendor_saved=$state_dir/kde-fingerprint.vendor
kde_fingerprint_managed_saved=$state_dir/kde-fingerprint.managed
material=$(p /var/lib/goodix-5125-poc)
policy_name=goodix_fprint_account_delete
policy_priority=400
expected_pam_rule='auth        sufficient    /usr/lib64/goodix-27c6-5125/current/pam_fprintd.so max-tries=3 timeout=8'
legacy_pam_rule='auth        sufficient                                   pam_fprintd.so'
expected_kde_fingerprint_pam_rule='auth        required      pam_fprintd.so max-tries=3 timeout=45'
required_candidate=(
  MANIFEST SHA256SUMS SBOM.spdx.json THIRD_PARTY_NOTICES.md LICENSE
  GPL-2.0-or-later.txt LGPL-2.1-or-later.txt GPL-3.0-or-later.txt
  Apache-2.0.txt OpenCV-LICENSES.txt
  fprintd greeter pam_fprintd.so pam_goodix_polkit.so pam_goodix_sudo.so sudo-source.sha256 polkit-source.sha256 99-goodix-login-greeter.conf login-source.sha256
  plasmalogin plasma-vt-preflight plasma-vt-source.sha256 99-goodix-plasma-vt.conf
  fprintd-COPYING fprintd-AUTHORS production-source.sha256 fprintd-source.sha256
  libfprint-2.so.2.0.0 libgusb.so.2
  libopencv_core.so.413 libopencv_features2d.so.413 libopencv_flann.so.413
  libopencv_imgproc.so.413 fprintd-wrapper 50-goodix-fprint-account-delete
  goodix_fprint_account_delete.te goodix_fprint_account_delete.fc
  99-goodix-27c6-5125-managed.conf plasmalogin-pam.rule kde-fingerprint-pam.rule
)
required_material=(target-material-manifest.json transport-material.bin target-config-90.bin gfusb.dll fdt-cache.bin)

polkit_deploy() { python3 "$here/../../production/polkit/deploy.py" "$@"; }

fail() { printf 'GOODIX_MANAGED_TRANSACTION=FAIL reason=%s\n' "$1" >&2; exit 1; }
digest() { sha256sum "$1" | awk '{print $1}'; }
is_sha() { [[ ${1:-} =~ ^[0-9a-f]{64}$ ]]; }
is_commit() { [[ ${1:-} =~ ^[0-9a-f]{40}$ ]]; }
state_value() {
  local key=$1 count
  count=$(awk -F= -v key="$key" '$1 == key { n++ } END { print n + 0 }' "$state")
  [[ $count -eq 1 ]] || return 1
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print }' "$state"
}
manifest_value() {
  local candidate=$1 key=$2 count
  count=$(awk -F= -v key="$key" '$1 == key { n++ } END { print n + 0 }' "$candidate/MANIFEST")
  [[ $count -eq 1 ]] || return 1
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print }' "$candidate/MANIFEST"
}
material_ready() {
  [[ -d $material && ! -L $material ]] || return 1
  [[ $(stat -c '%u:%g:%a' "$material") == 0:0:700 || -n $test_root ]] || return 1
  local name
  for name in "${required_material[@]}"; do
    [[ -f $material/$name && ! -L $material/$name ]] || return 1
    [[ -n $test_root || $(stat -c '%u:%g:%a' "$material/$name") == 0:0:600 ]] || return 1
  done
}
host_action() {
  if [[ -n $test_root ]]; then
    [[ ${GOODIX_MANAGED_TEST_FAIL_ACTION:-} != "$1:${2:-}" && \
       ${GOODIX_MANAGED_TEST_FAIL_ACTION:-} != "$1:${2:-}:${3:-}" ]] || return 1
    return 0
  fi
  "$@"
}
service_state() {
  if [[ -n $test_root ]]; then printf 'inactive\n'; else systemctl is-active fprintd.service || true; fi
}
verify_repo_provenance() {
  local expected=$1
  [[ -n $test_root || $EUID -eq 0 ]] || fail root_required
  if [[ -n $test_root ]]; then
    is_commit "$expected" || fail source_head_invalid
    return
  fi
  [[ $(git -C "$repo" rev-parse HEAD) == "$expected" ]] || fail source_head_mismatch
  [[ -z $(git -C "$repo" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
}
verify_candidate() {
  local candidate=$1 caller=$2 frozen=${3:-false} name commit count
  [[ $candidate == /* && -d $candidate && ! -L $candidate ]] || fail candidate_invalid
  if [[ $frozen == true ]]; then
    [[ -n $test_root || $(stat -c %U "$candidate") == root ]] || fail frozen_candidate_owner_invalid
  else
    [[ -n $test_root || $(stat -c %U "$candidate") == "$caller" ]] || fail candidate_owner_invalid
  fi
  for name in "${required_candidate[@]}"; do
    [[ -f $candidate/$name && ! -L $candidate/$name ]] || fail "candidate_${name}_invalid"
  done
  count=$(find "$candidate" -mindepth 1 -maxdepth 1 -type f -printf '%f\n' | wc -l)
  [[ $count -eq ${#required_candidate[@]} ]] || fail candidate_file_set_invalid
  [[ -z $(find "$candidate" -mindepth 1 -maxdepth 1 ! -type f -print -quit) ]] || fail candidate_nonregular_entry
  awk 'NF != 2 || $1 !~ /^[0-9a-f]{64}$/ || $2 ~ /[^A-Za-z0-9_.-]/ { exit 1 }' "$candidate/SHA256SUMS" || fail candidate_checksum_grammar
  cmp -s <(printf '%s\n' "${required_candidate[@]}" | grep -vx SHA256SUMS | LC_ALL=C sort) \
    <(awk '{print $2}' "$candidate/SHA256SUMS" | LC_ALL=C sort) || fail candidate_checksum_file_set
  (cd "$candidate" && sha256sum -c SHA256SUMS >/dev/null) || fail candidate_digest_mismatch
  [[ $(manifest_value "$candidate" GOODIX_MANAGED_DISTRIBUTION_MODEL) == SOURCE_FIRST_MANAGED_INSTALL ]] || fail distribution_model_invalid
  [[ $(manifest_value "$candidate" RPM_OFFICIAL_DISTRIBUTION) == false ]] || fail rpm_policy_invalid
  [[ $(manifest_value "$candidate" PROTECTED_MATERIAL_INCLUDED) == false ]] || fail candidate_contains_material
  [[ $(manifest_value "$candidate" PAM_FILES_INCLUDED) == true ]] || fail managed_pam_rule_missing
  [[ $(manifest_value "$candidate" PAM_INTEGRATION) == MANAGED_ETC_OVERRIDE_FROM_VENDOR ]] || fail pam_integration_model_invalid
  [[ $(manifest_value "$candidate" KSCREENLOCKER_PAM_INTEGRATION) == MANAGED_PACKAGE_CONFIG_TRANSFORM ]] ||
    fail kscreenlocker_pam_integration_model_invalid
  [[ $(manifest_value "$candidate" EARLY_LOGIN_INTEGRATION) == PAIRED_FPRINTD_PAM_GREETER_V1 ]] || fail early_login_integration_missing
  [[ $(manifest_value "$candidate" SBOM_FORMAT) == SPDX-2.3-JSON ]] || fail sbom_format_invalid
  [[ $(manifest_value "$candidate" COMBINED_BINARY_LICENSE) == GPL-3.0-or-later ]] || fail combined_binary_license_invalid
  [[ $(manifest_value "$candidate" FAR_FRR_CLAIM) == NOT_MADE ]] || fail far_frr_claim_invalid
  commit=$(manifest_value "$candidate" SOURCE_COMMIT) || fail candidate_commit_missing
  is_commit "$commit" || fail candidate_commit_invalid
  [[ $(manifest_value "$candidate" SUDO_INTEGRATION) == PASSWORD_FIRST_SERVICE_LOCAL_V1 ]] || fail sudo_integration_missing
  [[ $(manifest_value "$candidate" POLKIT_INTEGRATION) == INTERRUPTIBLE_SERVICE_LOCAL_V1 ]] || fail polkit_integration_missing
  [[ $(manifest_value "$candidate" PLASMA_VT_INTEGRATION) == QUALIFIED_SESSION_VT_V1 ]] || fail plasma_vt_contract
  verify_repo_provenance "$commit"
  printf '%s\n' "$commit"
}
freeze_candidate() {
  local source=$1 caller=$2 freeze name
  [[ $source == /* && -d $source && ! -L $source ]] || fail candidate_invalid
  [[ -n $test_root || $(stat -c %U "$source") == "$caller" ]] || fail candidate_owner_invalid
  for name in "${required_candidate[@]}"; do
    [[ -f $source/$name && ! -L $source/$name ]] || fail "candidate_${name}_invalid"
  done
  [[ $(find "$source" -mindepth 1 -maxdepth 1 -printf '%f\n' | wc -l) -eq ${#required_candidate[@]} ]] || fail candidate_file_set_invalid
  if [[ -n $test_root ]]; then
    freeze=$(mktemp -d "$test_root/goodix-managed-candidate.XXXXXX")
  else
    freeze=$(mktemp -d /var/tmp/goodix-managed-candidate.XXXXXX)
  fi
  chmod 0700 "$freeze"
  for name in "${required_candidate[@]}"; do install -m 0600 "$source/$name" "$freeze/$name"; done
  printf '%s\n' "$freeze"
}
remove_frozen_candidate() {
  local freeze=${1:-}
  [[ -n $freeze && -d $freeze && ! -L $freeze ]] || return 0
  if [[ -n $test_root ]]; then
    [[ $freeze == "$test_root"/goodix-managed-candidate.* ]] || return 1
  else
    [[ $freeze == /var/tmp/goodix-managed-candidate.* ]] || return 1
  fi
  find "$freeze" -xdev -depth -delete
}
install_runtime_tree() {
  local candidate=$1 commit=$2 destination=$runtime_root/$commit library
  [[ ! -e $destination && ! -L $destination ]] || fail runtime_commit_collision
  install -d -m 0755 -- "$runtime_root"
  install -d -m 0755 -- "$destination"
  for library in libfprint-2.so.2.0.0 libgusb.so.2 libopencv_core.so.413 \
    libopencv_features2d.so.413 libopencv_flann.so.413 libopencv_imgproc.so.413; do
    install -m 0644 -- "$candidate/$library" "$destination/$library"
  done
  install -m 0755 "$candidate/fprintd" "$candidate/greeter" "$candidate/plasmalogin" "$candidate/plasma-vt-preflight" "$destination/"
  install -m 0644 "$candidate/pam_fprintd.so" "$candidate/pam_goodix_polkit.so" "$candidate/pam_goodix_sudo.so" "$destination/"
  host_action restorecon -RF "$destination"
  host_action chcon --reference=/usr/bin/plasmalogin "$destination/plasmalogin"
  host_action chcon --reference=/usr/bin/bash "$destination/plasma-vt-preflight"
  host_action chcon --reference=/usr/libexec/fprintd "$destination/fprintd"
  host_action chcon --reference=/usr/libexec/plasma-login-greeter "$destination/greeter"
  host_action chcon --reference=/usr/lib64/security/pam_fprintd.so "$destination/pam_fprintd.so" "$destination/pam_goodix_polkit.so" "$destination/pam_goodix_sudo.so"
  if [[ -n $test_root && ${GOODIX_MANAGED_TEST_FAIL_AFTER_LOGIN_RUNTIME:-false} == true ]]; then
    fail injected_failure_after_login_runtime
  fi
  ln -s libfprint-2.so.2.0.0 "$destination/libfprint-2.so.2"
  ln -s libfprint-2.so.2 "$destination/libfprint-2.so"
}
verify_runtime_layout() {
  local directory=$1 file mode
  [[ -d $directory && ! -L $directory ]] || fail runtime_directory_invalid
  [[ $(readlink "$directory/libfprint-2.so.2") == libfprint-2.so.2.0.0 && \
     $(readlink "$directory/libfprint-2.so") == libfprint-2.so.2 ]] || fail runtime_symlink_drift
  [[ $(find "$directory" -mindepth 1 -maxdepth 1 -printf '%f\n' | wc -l) -eq 15 ]] || fail runtime_file_set_drift
  for file in libfprint-2.so.2.0.0 libgusb.so.2 libopencv_{core,features2d,flann,imgproc}.so.413 fprintd greeter plasmalogin plasma-vt-preflight pam_fprintd.so pam_goodix_polkit.so pam_goodix_sudo.so; do
    [[ -f $directory/$file && ! -L $directory/$file ]] || fail runtime_file_invalid
    mode=644
    [[ $file != fprintd && $file != greeter && $file != plasmalogin && $file != plasma-vt-preflight ]] || mode=755
    [[ $(stat -c %a "$directory/$file") == "$mode" ]] || fail runtime_mode_drift
    [[ -n $test_root || $(stat -c '%u:%g' "$directory/$file") == 0:0 ]] || fail runtime_owner_drift
  done
}
tree_digest() {
  local directory=$1
  (cd "$directory" && find . -maxdepth 1 -type f -printf '%P\n' | LC_ALL=C sort | xargs -r sha256sum) |
    sha256sum | awk '{print $1}'
}
install_policy() {
  [[ -n $test_root ]] && { install -D -m 0600 /dev/null "$state_dir/policy.test"; return; }
  local work mod package
  work=$(mktemp -d /tmp/goodix-managed-policy.XXXXXX)
  trap 'find "$work" -xdev -depth -delete' RETURN
  mod=$work/$policy_name.mod
  package=$work/$policy_name.pp
  checkmodule -M -m -E -o "$mod" "$1/goodix_fprint_account_delete.te"
  semodule_package -o "$package" -m "$mod" -f "$1/goodix_fprint_account_delete.fc"
  [[ -z $(semodule -lfull | awk -v name="$policy_name" '$2 == name { print }') ]] || fail policy_collision
  semodule -X "$policy_priority" -i "$package"
  find "$work" -xdev -depth -delete
  trap - RETURN
}
remove_policy() {
  if [[ -n $test_root ]]; then rm -f -- "$state_dir/policy.test"; else semodule -X "$policy_priority" -r "$policy_name"; fi
}
verify_pam_rule() {
  local candidate=$1
  [[ $(wc -l <"$candidate/plasmalogin-pam.rule") -eq 1 && \
     $(<"$candidate/plasmalogin-pam.rule") == "$expected_pam_rule" ]] || fail pam_rule_invalid
}
verify_kde_fingerprint_pam_rule() {
  local candidate=$1
  [[ $(wc -l <"$candidate/kde-fingerprint-pam.rule") -eq 1 && \
     $(<"$candidate/kde-fingerprint-pam.rule") == "$expected_kde_fingerprint_pam_rule" ]] ||
    fail kde_fingerprint_pam_rule_invalid
}
kde_fingerprint_rpm_digest() {
  if [[ -n $test_root ]]; then
    printf '%s\n' "${GOODIX_MANAGED_TEST_KDE_VENDOR_SHA256:-}"
    return
  fi
  local output count
  output=$(rpm -q --dump plasma-workspace | awk -v path=/etc/pam.d/kde-fingerprint '$1 == path { print $4 }') ||
    fail kde_fingerprint_vendor_rpm_query_failed
  count=$(wc -l <<<"$output")
  [[ $count -eq 1 ]] || fail kde_fingerprint_vendor_rpm_metadata_invalid
  printf '%s\n' "$output"
}
verify_kde_fingerprint_vendor_layout() {
  local source=$1
  [[ -f $source && ! -L $source ]] || fail kde_fingerprint_vendor_pam_invalid
  [[ -z $(grep -F 'pam_fprintd.so' "$source" || true) ]] ||
    fail kde_fingerprint_vendor_pam_already_modified
  [[ $(grep -Ec '^[[:space:]]*auth[[:space:]]+substack[[:space:]]+fingerprint-auth[[:space:]]*$' "$source") -eq 1 ]] ||
    fail kde_fingerprint_vendor_auth_boundary_invalid
  [[ $(tail -c 1 "$source" | od -An -tuC | tr -d ' ') == 10 ]] ||
    fail kde_fingerprint_vendor_pam_no_final_newline
}
verify_kde_fingerprint_target_metadata() {
  [[ $(stat -c '%a' "$kde_fingerprint_pam") == 644 ]] || fail kde_fingerprint_pam_mode_drift
  [[ -n $test_root || $(stat -c '%u:%g' "$kde_fingerprint_pam") == 0:0 ]] ||
    fail kde_fingerprint_pam_owner_drift
}
verify_kde_fingerprint_vendor() {
  local rpm_digest flags
  verify_kde_fingerprint_vendor_layout "$kde_fingerprint_pam"
  verify_kde_fingerprint_target_metadata
  rpm_digest=$(kde_fingerprint_rpm_digest)
  is_sha "$rpm_digest" || fail kde_fingerprint_vendor_rpm_digest_invalid
  [[ $(digest "$kde_fingerprint_pam") == "$rpm_digest" ]] || fail kde_fingerprint_vendor_package_drift
  if [[ -z $test_root ]]; then
    [[ $(stat -c '%u:%g:%a' "$kde_fingerprint_pam") == 0:0:644 ]] ||
      fail kde_fingerprint_vendor_pam_metadata_invalid
    [[ $(. /etc/os-release; printf '%s' "${VERSION_ID:-}") == 44 ]] || fail unsupported_target_os
    [[ $(rpm -q --whatprovides --qf '%{NAME}\n' "$kde_fingerprint_pam") == plasma-workspace ]] ||
      fail kde_fingerprint_vendor_owner_invalid
    flags=$(rpm -q --qf '[%{FILENAMES}\t%{FILEFLAGS}\n]' plasma-workspace |
      awk -F '\t' '$1 == "/etc/pam.d/kde-fingerprint" { print $2 }')
    [[ $flags == 17 ]] || fail kde_fingerprint_vendor_not_config_noreplace
    rpm -q fprintd-pam >/dev/null || fail fprintd_pam_package_missing
    [[ -f /usr/lib64/security/pam_fprintd.so && ! -L /usr/lib64/security/pam_fprintd.so ]] ||
      fail pam_fprintd_module_missing
  fi
  [[ ! -e $kde_fingerprint_pam.rpmnew && ! -L $kde_fingerprint_pam.rpmnew && \
     ! -e $kde_fingerprint_pam.rpmsave && ! -L $kde_fingerprint_pam.rpmsave ]] ||
    fail kde_fingerprint_package_upgrade_artifact_present
}
generate_kde_fingerprint_pam() {
  local candidate=$1 source=$2 output=$3
  verify_kde_fingerprint_pam_rule "$candidate"
  verify_kde_fingerprint_vendor_layout "$source"
  awk -v rule="$expected_kde_fingerprint_pam_rule" '
    /^[[:space:]]*auth[[:space:]]+substack[[:space:]]+fingerprint-auth[[:space:]]*$/ && !replaced {
      print rule; replaced=1; next
    }
    { print }
    END { if (!replaced) exit 1 }
  ' "$source" >"$output" || fail kde_fingerprint_pam_generation_failed
}
verify_vendor_pam() {
  local verification
  [[ -f $vendor_pam && ! -L $vendor_pam ]] || fail plasmalogin_vendor_pam_invalid
  [[ -z $(grep -F 'pam_fprintd.so' "$vendor_pam" || true) ]] || fail plasmalogin_vendor_pam_already_modified
  [[ $(grep -Ec '^[[:space:]]*auth[[:space:]]+substack[[:space:]]+password-auth[[:space:]]*$' "$vendor_pam") -eq 1 ]] ||
    fail plasmalogin_vendor_password_auth_boundary_invalid
  [[ $(tail -c 1 "$vendor_pam" | od -An -tuC | tr -d ' ') == 10 ]] || fail plasmalogin_vendor_pam_no_final_newline
  if [[ -z $test_root ]]; then
    [[ $(stat -c '%u:%g:%a' "$vendor_pam") == 0:0:644 ]] || fail plasmalogin_vendor_pam_metadata_invalid
    [[ $(. /etc/os-release; printf '%s' "${VERSION_ID:-}") == 44 ]] || fail unsupported_target_os
    [[ $(rpm -q --whatprovides --qf '%{NAME}\n' "$vendor_pam") == plasma-login-manager ]] ||
      fail plasmalogin_vendor_owner_invalid
    verification=$(rpm -V plasma-login-manager 2>/dev/null || true)
    [[ -z $(awk -v path="$vendor_pam" '$NF == path { print }' <<<"$verification") ]] ||
      fail plasmalogin_vendor_pam_package_drift
    rpm -q fprintd-pam >/dev/null || fail fprintd_pam_package_missing
    [[ -f /usr/lib64/security/pam_fprintd.so && ! -L /usr/lib64/security/pam_fprintd.so ]] ||
      fail pam_fprintd_module_missing
  fi
}
generate_pam_override() {
  local candidate=$1 output=$2
  verify_pam_rule "$candidate"
  verify_vendor_pam
  awk -v rule="$expected_pam_rule" '
    /^[[:space:]]*auth[[:space:]]+substack[[:space:]]+password-auth[[:space:]]*$/ && !inserted {
      print rule; inserted=1
    }
    { print }
    END { if (!inserted) exit 1 }
  ' "$vendor_pam" >"$output" || fail plasmalogin_pam_generation_failed
}
verify_saved_pam() {
  local expected_vendor=$1 expected_override=$2
  is_sha "$expected_vendor" && is_sha "$expected_override" || fail pam_state_hash_invalid
  [[ $(digest "$vendor_pam") == "$expected_vendor" ]] || fail plasmalogin_vendor_pam_drift
  [[ -f $pam_saved && ! -L $pam_saved && $(digest "$pam_saved") == "$expected_override" ]] ||
    fail managed_pam_saved_drift
  [[ -n $test_root || $(stat -c '%u:%g:%a' "$pam_saved") == 0:0:644 ]] || fail managed_pam_saved_metadata_invalid
  if grep -Fqx "${expected_pam_rule/max-tries=3/max-tries=1}" "$pam_saved" && [[ $ACTIVE_LOGIN_STATE == MANAGED ]]; then
    fail single_attempt_pam_requires_previous_uninstall_then_fresh_install
  fi
  [[ $(grep -Fxc "$expected_pam_rule" "$pam_saved") -eq 1 ]] || fail managed_pam_rule_drift
  cmp -s "$vendor_pam" <(awk -v rule="$expected_pam_rule" '$0 != rule { print }' "$pam_saved") ||
    fail managed_pam_not_vendor_derived
}
install_managed_pam() {
  local candidate=$1 generated=$state_dir/plasmalogin.pending.$$
  [[ ! -e $managed_pam && ! -L $managed_pam && ! -e $pam_saved && ! -L $pam_saved ]] ||
    fail managed_pam_path_collision
  generate_pam_override "$candidate" "$generated"
  install -m 0644 "$generated" "$pam_saved"
  install -D -m 0644 "$generated" "$managed_pam"
  rm -f -- "$generated"
  host_action restorecon -F "$managed_pam"
  installed_pam_vendor_sha=$(digest "$vendor_pam")
  installed_pam_override_sha=$(digest "$managed_pam")
  [[ -n $test_root || $(stat -c '%u:%g:%a' "$managed_pam") == 0:0:644 ]] ||
    fail managed_pam_override_metadata_invalid
  verify_saved_pam "$installed_pam_vendor_sha" "$installed_pam_override_sha"
}
remove_managed_pam() {
  local expected_vendor=$1 expected_override=$2
  verify_saved_pam "$expected_vendor" "$expected_override"
  [[ -f $managed_pam && ! -L $managed_pam && $(digest "$managed_pam") == "$expected_override" ]] ||
    fail managed_pam_override_drift
  rm -f -- "$managed_pam"
}
restore_managed_pam() {
  local expected_vendor=$1 expected_override=$2
  verify_saved_pam "$expected_vendor" "$expected_override"
  [[ ! -e $managed_pam && ! -L $managed_pam ]] || fail managed_pam_path_collision
  install -D -m 0644 "$pam_saved" "$managed_pam"
  host_action restorecon -F "$managed_pam"
}
verify_saved_kde_fingerprint_pam() {
  local expected_vendor=$1 expected_override=$2 rpm_digest rendered=$state_dir/kde-fingerprint.verify.$$
  is_sha "$expected_vendor" && is_sha "$expected_override" || fail kscreenlocker_pam_state_hash_invalid
  rpm_digest=$(kde_fingerprint_rpm_digest)
  [[ $rpm_digest == "$expected_vendor" ]] || fail kde_fingerprint_vendor_package_drift
  [[ -f $kde_fingerprint_vendor_saved && ! -L $kde_fingerprint_vendor_saved && \
     $(digest "$kde_fingerprint_vendor_saved") == "$expected_vendor" ]] ||
    fail kde_fingerprint_vendor_saved_drift
  [[ -f $kde_fingerprint_managed_saved && ! -L $kde_fingerprint_managed_saved && \
     $(digest "$kde_fingerprint_managed_saved") == "$expected_override" ]] ||
    fail kde_fingerprint_managed_saved_drift
  [[ -n $test_root || $(stat -c '%u:%g:%a' "$kde_fingerprint_vendor_saved") == 0:0:644 ]] ||
    fail kde_fingerprint_vendor_saved_metadata_invalid
  [[ -n $test_root || $(stat -c '%u:%g:%a' "$kde_fingerprint_managed_saved") == 0:0:644 ]] ||
    fail kde_fingerprint_managed_saved_metadata_invalid
  verify_kde_fingerprint_vendor_layout "$kde_fingerprint_vendor_saved"
  awk -v rule="$expected_kde_fingerprint_pam_rule" '
    /^[[:space:]]*auth[[:space:]]+substack[[:space:]]+fingerprint-auth[[:space:]]*$/ && !replaced {
      print rule; replaced=1; next
    }
    { print }
    END { if (!replaced) exit 1 }
  ' "$kde_fingerprint_vendor_saved" >"$rendered" || fail kde_fingerprint_saved_render_failed
  if ! cmp -s "$rendered" "$kde_fingerprint_managed_saved"; then
    rm -f -- "$rendered"
    fail kde_fingerprint_managed_not_vendor_derived
  fi
  rm -f -- "$rendered"
  [[ ! -e $kde_fingerprint_pam.rpmnew && ! -L $kde_fingerprint_pam.rpmnew && \
     ! -e $kde_fingerprint_pam.rpmsave && ! -L $kde_fingerprint_pam.rpmsave ]] ||
    fail kde_fingerprint_package_upgrade_artifact_present
}
install_managed_kde_fingerprint_pam() {
  local candidate=$1 generated=$state_dir/kde-fingerprint.pending.$$
  [[ ! -e $kde_fingerprint_vendor_saved && ! -L $kde_fingerprint_vendor_saved && \
     ! -e $kde_fingerprint_managed_saved && ! -L $kde_fingerprint_managed_saved ]] ||
    fail kde_fingerprint_managed_state_collision
  verify_kde_fingerprint_vendor
  generate_kde_fingerprint_pam "$candidate" "$kde_fingerprint_pam" "$generated"
  install -m 0644 "$kde_fingerprint_pam" "$kde_fingerprint_vendor_saved"
  install -m 0644 "$generated" "$kde_fingerprint_managed_saved"
  rm -f -- "$generated"
  installed_kde_fingerprint_vendor_sha=$(digest "$kde_fingerprint_vendor_saved")
  installed_kde_fingerprint_override_sha=$(digest "$kde_fingerprint_managed_saved")
  verify_saved_kde_fingerprint_pam "$installed_kde_fingerprint_vendor_sha" \
    "$installed_kde_fingerprint_override_sha"
  install -m 0644 "$kde_fingerprint_managed_saved" "$kde_fingerprint_pam"
  host_action restorecon -F "$kde_fingerprint_pam"
  [[ $(digest "$kde_fingerprint_pam") == "$installed_kde_fingerprint_override_sha" ]] ||
    fail kde_fingerprint_managed_activation_failed
}
activate_managed_kde_fingerprint_pam() {
  local expected_vendor=$1 expected_override=$2
  verify_saved_kde_fingerprint_pam "$expected_vendor" "$expected_override"
  [[ -f $kde_fingerprint_pam && ! -L $kde_fingerprint_pam && \
     $(digest "$kde_fingerprint_pam") == "$expected_vendor" ]] ||
    fail kde_fingerprint_vendor_restore_drift
  install -m 0644 "$kde_fingerprint_managed_saved" "$kde_fingerprint_pam"
  host_action restorecon -F "$kde_fingerprint_pam"
}
deactivate_managed_kde_fingerprint_pam() {
  local expected_vendor=$1 expected_override=$2
  verify_saved_kde_fingerprint_pam "$expected_vendor" "$expected_override"
  [[ -f $kde_fingerprint_pam && ! -L $kde_fingerprint_pam && \
     $(digest "$kde_fingerprint_pam") == "$expected_override" ]] ||
    fail kde_fingerprint_managed_override_drift
  install -m 0644 "$kde_fingerprint_vendor_saved" "$kde_fingerprint_pam"
  host_action restorecon -F "$kde_fingerprint_pam"
}
write_state() {
  local current=$1 previous=$2 installer=$3 service_before=$4 current_digest=$5 previous_digest=$6
  local current_pam=$7 previous_pam=$8 pam_vendor_sha=$9 pam_override_sha=${10}
  local current_kde_pam=${11} previous_kde_pam=${12} kde_vendor_sha=${13} kde_override_sha=${14}
  local pending=$state.pending.$$
  {
    echo SUDO_INTEGRATION=PASSWORD_FIRST_SERVICE_LOCAL_V1
    echo POLKIT_INTEGRATION=INTERRUPTIBLE_SERVICE_LOCAL_V1
    echo GOODIX_MANAGED_STATUS=ACTIVE
    echo GOODIX_MANAGED_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL
    echo RPM_OFFICIAL_DISTRIBUTION=false
    echo "CURRENT_COMMIT=$current"
    echo "PREVIOUS_COMMIT=$previous"
    echo "INSTALLER=$installer"
    echo "SERVICE_BEFORE=$service_before"
    echo "CURRENT_TREE_SHA256=$current_digest"
    echo "PREVIOUS_TREE_SHA256=$previous_digest"
    echo "WRAPPER_SHA256=$(digest "$wrapper")"
    echo "DROPIN_SHA256=$(digest "$dropin")"
    echo "HOOK_SHA256=$(digest "$hook")"
    echo EARLY_LOGIN_INTEGRATION=PAIRED_FPRINTD_PAM_GREETER_V1
    echo "GREETER_DROPIN_SHA256=$(digest "$greeter_dropin")"
    echo "GREETER_DIRECTORY_CREATED=$greeter_directory_created"
    echo PLASMA_VT_INTEGRATION=QUALIFIED_SESSION_VT_V1
    echo "PLASMA_DROPIN_SHA256=$(digest "$plasma_dropin")"
    echo "PLASMA_DIRECTORY_CREATED=$plasma_directory_created"
    echo "PLASMA_SERVICE_BEFORE=$plasma_service_before"
    echo "POLICY_SOURCE_SHA256=$policy_source_sha"
    echo "POLICY_CONTEXTS_SHA256=$policy_contexts_sha"
    echo "CURRENT_PAM_STATUS=$current_pam"
    echo "PREVIOUS_PAM_STATUS=$previous_pam"
    echo "PAM_VENDOR_SHA256=$pam_vendor_sha"
    echo "PAM_OVERRIDE_SHA256=$pam_override_sha"
    echo "CURRENT_KSCREENLOCKER_PAM_STATUS=$current_kde_pam"
    echo "PREVIOUS_KSCREENLOCKER_PAM_STATUS=$previous_kde_pam"
    echo "KSCREENLOCKER_VENDOR_SHA256=$kde_vendor_sha"
    echo "KSCREENLOCKER_OVERRIDE_SHA256=$kde_override_sha"
  } >"$pending"
  chmod 0644 "$pending"
  mv -f -- "$pending" "$state"
}
ensure_runtime_root_mode() {
  local mode allow_fix=${1:-true}
  [[ -e $runtime_root || -L $runtime_root ]] || return 0
  [[ -d $runtime_root && ! -L $runtime_root ]] || fail runtime_root_invalid
  if [[ -z $test_root ]]; then
    [[ $(stat -c '%u:%g' "$runtime_root") == 0:0 ]] || fail runtime_root_owner_invalid
  fi
  mode=$(stat -c '%a' "$runtime_root")
  case $mode in
    755) ;;
    700)
      [[ $allow_fix == true ]] || fail runtime_root_mode_drift_before_uninstall
      chmod 0755 "$runtime_root" || fail runtime_root_mode_fix_failed
      [[ $(stat -c '%a' "$runtime_root") == 755 ]] || fail runtime_root_mode_fix_failed
      ;;
    *) fail runtime_root_mode_unexpected ;;
  esac
}

verify_active() {
  ensure_runtime_root_mode "${3:-true}"
  local allow_legacy=${1:-false}
  local allow_vendor_drift=${2:-false}
  [[ -f $state && ! -L $state ]] || fail state_missing
  [[ $(state_value GOODIX_MANAGED_STATUS) == ACTIVE ]] || fail state_inactive
  [[ $(state_value SUDO_INTEGRATION || true) == PASSWORD_FIRST_SERVICE_LOCAL_V1 ]] ||
    fail pre_sudo_install_requires_original_uninstall_then_fresh_install
  [[ $(state_value POLKIT_INTEGRATION || true) == INTERRUPTIBLE_SERVICE_LOCAL_V1 ]] ||
    fail pre_polkit_install_requires_original_uninstall_then_fresh_install
  [[ $(state_value PLASMA_VT_INTEGRATION || true) == QUALIFIED_SESSION_VT_V1 ]] || fail pre_vt_install_requires_saved_original_uninstall
  [[ -f $plasma_dropin && ! -L $plasma_dropin && $(digest "$plasma_dropin") == $(state_value PLASMA_DROPIN_SHA256) ]] || fail plasma_dropin_drift
  plasma_directory_created=$(state_value PLASMA_DIRECTORY_CREATED)
  [[ $plasma_directory_created == true || $plasma_directory_created == false ]] || fail plasma_directory_state_invalid
  plasma_service_before=$(state_value PLASMA_SERVICE_BEFORE)
  [[ $plasma_service_before == active || $plasma_service_before == inactive ]] || fail plasma_service_state_invalid
  if [[ $allow_vendor_drift != true ]]; then
    polkit_deploy verify managed
  fi
  local current previous expected
  if [[ $(state_value EARLY_LOGIN_INTEGRATION || true) == PAIRED_FPRINTD_PAM_GREETER_V1 ]]; then
    [[ -f $greeter_dropin && ! -L $greeter_dropin && $(digest "$greeter_dropin") == $(state_value GREETER_DROPIN_SHA256) ]] || fail greeter_dropin_drift
    greeter_directory_created=$(state_value GREETER_DIRECTORY_CREATED)
    [[ $greeter_directory_created == true || $greeter_directory_created == false ]] || fail greeter_directory_state_invalid
    policy_source_sha=$(state_value POLICY_SOURCE_SHA256)
    policy_contexts_sha=$(state_value POLICY_CONTEXTS_SHA256)
    is_sha "$policy_source_sha" && is_sha "$policy_contexts_sha" || fail policy_source_state_invalid
    ACTIVE_LOGIN_STATE=MANAGED
  else
    [[ $allow_legacy == true ]] || fail legacy_login_requires_fresh_install
    expected_pam_rule=$legacy_pam_rule
    ACTIVE_LOGIN_STATE=LEGACY
  fi
  current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT)
  is_commit "$current" || fail current_commit_invalid
  [[ $previous == NONE ]] || is_commit "$previous" || fail previous_commit_invalid
  [[ -L $current_link && $(readlink "$current_link") == "$current" ]] || fail current_link_drift
  [[ $(tree_digest "$runtime_root/$current") == $(state_value CURRENT_TREE_SHA256) ]] || fail current_tree_drift
  if [[ $previous != NONE ]]; then
    [[ -d $runtime_root/$previous && ! -L $runtime_root/$previous ]] || fail previous_tree_missing
    [[ $(tree_digest "$runtime_root/$previous") == $(state_value PREVIOUS_TREE_SHA256) ]] || fail previous_tree_drift
  fi
  if [[ $ACTIVE_LOGIN_STATE == MANAGED ]]; then
    verify_runtime_layout "$runtime_root/$current"
    [[ $previous == NONE ]] || verify_runtime_layout "$runtime_root/$previous"
  fi
  if [[ $allow_vendor_drift != true && -z $test_root ]]; then
    verify_runtime_layout "$runtime_root/$current"
    "$current_link/plasma-vt-preflight"
  fi
  for pair in "$wrapper:WRAPPER_SHA256" "$dropin:DROPIN_SHA256" "$hook:HOOK_SHA256"; do
    expected=$(state_value "${pair#*:}")
    is_sha "$expected" || fail state_hash_invalid
    [[ -f ${pair%%:*} && ! -L ${pair%%:*} && $(digest "${pair%%:*}") == "$expected" ]] || fail managed_file_drift
  done
  if ! awk -F= '$1 == "CURRENT_PAM_STATUS" { found=1 } END { exit !found }' "$state"; then
    [[ $allow_legacy == true ]] || fail legacy_state_requires_pam_corrective_update
    [[ ! -e $managed_pam && ! -L $managed_pam && ! -e $pam_saved && ! -L $pam_saved ]] ||
      fail legacy_state_managed_pam_collision
    [[ ! -e $kde_fingerprint_vendor_saved && ! -L $kde_fingerprint_vendor_saved && \
       ! -e $kde_fingerprint_managed_saved && ! -L $kde_fingerprint_managed_saved ]] ||
      fail legacy_state_kscreenlocker_pam_collision
    verify_kde_fingerprint_vendor
    ACTIVE_PAM_STATE=LEGACY
    ACTIVE_KSCREENLOCKER_PAM_STATE=LEGACY
    return
  fi
  local current_pam previous_pam vendor_sha override_sha
  current_pam=$(state_value CURRENT_PAM_STATUS); previous_pam=$(state_value PREVIOUS_PAM_STATUS)
  vendor_sha=$(state_value PAM_VENDOR_SHA256); override_sha=$(state_value PAM_OVERRIDE_SHA256)
  [[ -f $vendor_pam && ! -L $vendor_pam ]] || fail plasmalogin_vendor_pam_invalid
  [[ $current_pam == ACTIVE || $current_pam == ABSENT ]] || fail current_pam_status_invalid
  if [[ $previous == NONE ]]; then
    [[ $previous_pam == NONE && $current_pam == ACTIVE ]] || fail previous_pam_status_invalid
  else
    [[ $previous_pam == ACTIVE || $previous_pam == ABSENT ]] || fail previous_pam_status_invalid
  fi
  if [[ $(digest "$vendor_pam") == "$vendor_sha" ]]; then
    [[ $allow_vendor_drift == true ]] || verify_vendor_pam
    verify_saved_pam "$vendor_sha" "$override_sha"
    ACTIVE_PAM_VENDOR_DRIFT=false
  else
    [[ $allow_vendor_drift == true ]] || fail plasmalogin_vendor_pam_drift
    [[ -f $pam_saved && ! -L $pam_saved && $(digest "$pam_saved") == "$override_sha" ]] ||
      fail managed_pam_saved_drift
    [[ -n $test_root || $(stat -c '%u:%g:%a' "$pam_saved") == 0:0:644 ]] ||
      fail managed_pam_saved_metadata_invalid
    [[ $(grep -Fxc "$expected_pam_rule" "$pam_saved") -eq 1 ]] || fail managed_pam_rule_drift
    ACTIVE_PAM_VENDOR_DRIFT=true
  fi
  if [[ $current_pam == ACTIVE ]]; then
    [[ -f $managed_pam && ! -L $managed_pam && $(digest "$managed_pam") == "$override_sha" ]] ||
      fail managed_pam_override_drift
    [[ -n $test_root || $(stat -c '%u:%g:%a' "$managed_pam") == 0:0:644 ]] ||
      fail managed_pam_override_metadata_invalid
  else
    [[ ! -e $managed_pam && ! -L $managed_pam ]] || fail managed_pam_expected_absent
  fi
  ACTIVE_PAM_STATE=MANAGED
  if ! awk -F= '$1 == "CURRENT_KSCREENLOCKER_PAM_STATUS" { found=1 } END { exit !found }' "$state"; then
    [[ $allow_legacy == true ]] || fail legacy_state_requires_kscreenlocker_pam_corrective_update
    [[ ! -e $kde_fingerprint_vendor_saved && ! -L $kde_fingerprint_vendor_saved && \
       ! -e $kde_fingerprint_managed_saved && ! -L $kde_fingerprint_managed_saved ]] ||
      fail legacy_state_kscreenlocker_pam_collision
    verify_kde_fingerprint_vendor
    ACTIVE_KSCREENLOCKER_PAM_STATE=LEGACY
    return
  fi
  local current_kde_pam previous_kde_pam kde_vendor_sha kde_override_sha
  current_kde_pam=$(state_value CURRENT_KSCREENLOCKER_PAM_STATUS)
  previous_kde_pam=$(state_value PREVIOUS_KSCREENLOCKER_PAM_STATUS)
  kde_vendor_sha=$(state_value KSCREENLOCKER_VENDOR_SHA256)
  kde_override_sha=$(state_value KSCREENLOCKER_OVERRIDE_SHA256)
  [[ $current_kde_pam == ACTIVE || $current_kde_pam == ABSENT ]] ||
    fail current_kscreenlocker_pam_status_invalid
  if [[ $previous == NONE ]]; then
    [[ $previous_kde_pam == NONE && $current_kde_pam == ACTIVE ]] ||
      fail previous_kscreenlocker_pam_status_invalid
  else
    [[ $previous_kde_pam == ACTIVE || $previous_kde_pam == ABSENT ]] ||
      fail previous_kscreenlocker_pam_status_invalid
  fi
  verify_saved_kde_fingerprint_pam "$kde_vendor_sha" "$kde_override_sha"
  if [[ $current_kde_pam == ACTIVE ]]; then
    [[ -f $kde_fingerprint_pam && ! -L $kde_fingerprint_pam && \
       $(digest "$kde_fingerprint_pam") == "$kde_override_sha" ]] ||
      fail kde_fingerprint_managed_override_drift
  else
    [[ -f $kde_fingerprint_pam && ! -L $kde_fingerprint_pam && \
       $(digest "$kde_fingerprint_pam") == "$kde_vendor_sha" ]] ||
      fail kde_fingerprint_vendor_restore_drift
  fi
  verify_kde_fingerprint_target_metadata
  ACTIVE_KSCREENLOCKER_PAM_STATE=MANAGED
}

verify_login_host() {
  local directory file unit
  unit=$(p /usr/lib/systemd/user/plasma-login.service)
  [[ -f $unit && ! -L $unit ]] || fail greeter_unit_missing
  if [[ -z $test_root ]]; then
    [[ $(rpm -q --qf '%{VERSION}-%{RELEASE}' plasma-login-manager) == 6.7.5-1.fc44 ]] || fail unsupported_plasma_login_version
    [[ $(rpm -q --qf '%{VERSION}-%{RELEASE}' fprintd) == 1.94.5-5.fc44 ]] || fail unsupported_fprintd_version
    [[ $(digest "$unit") == 97d00cf76a68583453ecee781c2bc8e9b2411d842464290698a2ad978f70f8f0 ]] || fail greeter_unit_drift
    getent passwd plasmalogin >/dev/null || fail greeter_user_missing
    [[ -x /usr/libexec/plasma-login-greeter ]] || fail greeter_missing
  fi
  # Do not layer this deployment over a development daemon or another UI wrapper.
  for directory in /etc/systemd/user /usr/local/lib/systemd/user /run/systemd/user \
      /var/lib/plasmalogin/.config/systemd/user; do
    [[ ! -e $(p "$directory/plasma-login.service") && ! -L $(p "$directory/plasma-login.service") ]] || fail greeter_unit_override
  done
  for directory in /etc/systemd/user /usr/local/lib/systemd/user /usr/lib/systemd/user \
      /run/systemd/user /var/lib/plasmalogin/.config/systemd/user; do
    for file in "$(p "$directory")"/plasma-login.service.d/*.conf; do
      [[ -e $file || -L $file ]] || continue
      [[ $file == "$greeter_dropin" && -f $state ]] || fail greeter_dropin_collision
    done
  done
  for directory in /etc/systemd/system /usr/local/lib/systemd/system /run/systemd/system; do
    [[ ! -e $(p "$directory/fprintd.service") && ! -L $(p "$directory/fprintd.service") ]] || fail fprintd_unit_override
    for file in "$(p "$directory")"/fprintd.service.d/*.conf; do
      [[ -e $file || -L $file ]] || continue
      [[ $file == "$dropin" && -f $state ]] || fail fprintd_dropin_collision
    done
  done
}

root_install_or_update() {
  local mode=$1 caller=$2 source_candidate=$3 candidate commit current previous service_before installer
  local current_pam pam_vendor_sha pam_override_sha
  local current_kde_pam kde_vendor_sha kde_override_sha
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  candidate=$(freeze_candidate "$source_candidate" "$caller")
  cleanup_candidate=$candidate
  cleanup_kind=none
  cleanup_runtime=
  cleanup_policy=false
  cleanup_old_current=
  cleanup_link_switched=false
  cleanup_service_before=inactive
  cleanup_pam_installed=false
  cleanup_greeter_installed=false
  cleanup_plasma_installed=false
  cleanup_kde_pam_installed=false
  cleanup_polkit=false
  cleanup_transaction() {
    local rc=$?
    set +e
    if [[ $rc -ne 0 && $cleanup_kind == update ]]; then
      if [[ $cleanup_link_switched == true && -n $cleanup_old_current ]]; then
        ln -s "$cleanup_old_current" "$runtime_root/current.recovery"
        mv -Tf -- "$runtime_root/current.recovery" "$current_link"
      fi
      [[ -z $cleanup_runtime || ! -d $cleanup_runtime ]] || find "$cleanup_runtime" -xdev -depth -delete
      if [[ $cleanup_pam_installed == true ]]; then rm -f -- "$managed_pam" "$pam_saved"; fi
      if [[ $cleanup_kde_pam_installed == true && -f $kde_fingerprint_vendor_saved ]]; then
        install -m 0644 "$kde_fingerprint_vendor_saved" "$kde_fingerprint_pam"
        host_action restorecon -F "$kde_fingerprint_pam"
        rm -f -- "$kde_fingerprint_vendor_saved" "$kde_fingerprint_managed_saved"
      fi
      host_action systemctl daemon-reload
      [[ $cleanup_service_before != active ]] || host_action systemctl start fprintd.service
    elif [[ $rc -ne 0 && $cleanup_kind == fresh ]]; then
      if [[ $cleanup_polkit == true ]] && ! polkit_deploy uninstall managed; then
        printf '%s\n' 'GOODIX_MANAGED_RECOVERY_REQUIRED=POLKIT_ROLLBACK_FAILED runtime_and_backups_preserved' >&2
        remove_frozen_candidate "$cleanup_candidate"
        exit "$rc"
      fi
      if [[ $cleanup_kde_pam_installed == true && -f $kde_fingerprint_vendor_saved ]]; then
        install -m 0644 "$kde_fingerprint_vendor_saved" "$kde_fingerprint_pam"
        host_action restorecon -F "$kde_fingerprint_pam"
      fi
      if [[ $cleanup_plasma_installed == true ]]; then rm -f -- "$plasma_dropin"; fi
      if [[ $plasma_directory_created == true ]]; then rmdir -- "$(dirname "$plasma_dropin")" 2>/dev/null; fi
      if [[ $cleanup_greeter_installed == true ]]; then rm -f -- "$greeter_dropin"; fi
      if [[ $greeter_directory_created == true ]]; then rmdir -- "$(dirname "$greeter_dropin")" 2>/dev/null; fi
      rm -f -- "$current_link" "$wrapper" "$dropin" "$hook" "$managed_pam" "$pam_saved" \
        "$kde_fingerprint_vendor_saved" "$kde_fingerprint_managed_saved" "$state"
      [[ -z $cleanup_runtime || ! -d $cleanup_runtime ]] || find "$cleanup_runtime" -xdev -depth -delete
      rmdir -- "$runtime_root" 2>/dev/null
      [[ $cleanup_policy != true ]] || remove_policy
      rmdir -- "$state_dir" 2>/dev/null
      host_action systemctl daemon-reload
      [[ $cleanup_service_before != active ]] || host_action systemctl start fprintd.service
    fi
    remove_frozen_candidate "$cleanup_candidate"
    exit "$rc"
  }
  trap cleanup_transaction EXIT
  commit=$(verify_candidate "$candidate" "$caller" true)
  verify_pam_rule "$candidate"
  verify_kde_fingerprint_pam_rule "$candidate"
  if [[ -f $state ]]; then
    verify_active true
    [[ $ACTIVE_LOGIN_STATE == MANAGED ]] || fail legacy_login_requires_uninstall_then_fresh_install
    verify_login_host
    current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT)
    if [[ $commit == "$current" ]]; then
      [[ $ACTIVE_PAM_STATE != LEGACY && $ACTIVE_KSCREENLOCKER_PAM_STATE != LEGACY ]] ||
        fail same_commit_requires_pam_corrective_update
      printf '%s\n' 'GOODIX_MANAGED_INSTALL=PASS_ALREADY_CURRENT' "CURRENT_COMMIT=$current"
      remove_frozen_candidate "$candidate"; trap - EXIT; return
    fi
    [[ $mode == update ]] || fail active_install_requires_update
    [[ $(digest "$candidate/plasmalogin") == $(digest "$runtime_root/$current/plasmalogin") && \
       $(digest "$candidate/plasma-vt-preflight") == $(digest "$runtime_root/$current/plasma-vt-preflight") ]] || \
      fail plasma_vt_update_requires_saved_uninstall_then_fresh_install
    [[ $previous == NONE ]] || fail rollback_slot_occupied
    [[ $(digest "$candidate/fprintd-wrapper") == $(state_value WRAPPER_SHA256) && \
       $(digest "$candidate/99-goodix-27c6-5125-managed.conf") == $(state_value DROPIN_SHA256) && \
       $(digest "$candidate/50-goodix-fprint-account-delete") == $(state_value HOOK_SHA256) && \
       $(digest "$candidate/99-goodix-login-greeter.conf") == $(state_value GREETER_DROPIN_SHA256) && \
       $(digest "$candidate/99-goodix-plasma-vt.conf") == $(state_value PLASMA_DROPIN_SHA256) && \
       $(digest "$candidate/goodix_fprint_account_delete.te") == "$policy_source_sha" && \
       $(digest "$candidate/goodix_fprint_account_delete.fc") == "$policy_contexts_sha" ]] ||
      fail managed_host_assets_changed_requires_fresh_install
    cleanup_kind=update
    cleanup_runtime=$runtime_root/$commit
    cleanup_old_current=$current
    cleanup_service_before=$(state_value SERVICE_BEFORE)
    installer=$(state_value INSTALLER)
    if [[ $ACTIVE_PAM_STATE == LEGACY ]]; then
      current_pam=ABSENT
      install_managed_pam "$candidate"
      cleanup_pam_installed=true
      pam_vendor_sha=$installed_pam_vendor_sha
      pam_override_sha=$installed_pam_override_sha
    else
      current_pam=$(state_value CURRENT_PAM_STATUS)
      pam_vendor_sha=$(state_value PAM_VENDOR_SHA256)
      pam_override_sha=$(state_value PAM_OVERRIDE_SHA256)
    fi
    if [[ $ACTIVE_KSCREENLOCKER_PAM_STATE == LEGACY ]]; then
      current_kde_pam=ABSENT
      cleanup_kde_pam_installed=true
      install_managed_kde_fingerprint_pam "$candidate"
      kde_vendor_sha=$installed_kde_fingerprint_vendor_sha
      kde_override_sha=$installed_kde_fingerprint_override_sha
    else
      current_kde_pam=$(state_value CURRENT_KSCREENLOCKER_PAM_STATUS)
      kde_vendor_sha=$(state_value KSCREENLOCKER_VENDOR_SHA256)
      kde_override_sha=$(state_value KSCREENLOCKER_OVERRIDE_SHA256)
    fi
    host_action systemctl stop fprintd.service
    install_runtime_tree "$candidate" "$commit"
    ln -s "$commit" "$runtime_root/current.next"
    mv -Tf -- "$runtime_root/current.next" "$current_link"
    cleanup_link_switched=true
    host_action systemctl restart fprintd.service
    write_state "$commit" "$current" "$installer" "$cleanup_service_before" \
      "$(tree_digest "$runtime_root/$commit")" "$(tree_digest "$runtime_root/$current")" \
      ACTIVE "$current_pam" "$pam_vendor_sha" "$pam_override_sha" \
      ACTIVE "$current_kde_pam" "$kde_vendor_sha" "$kde_override_sha"
    cleanup_kind=none
    printf '%s\n' 'GOODIX_MANAGED_UPDATE=PASS' "CURRENT_COMMIT=$commit" "ROLLBACK_COMMIT=$current"
    remove_frozen_candidate "$candidate"; trap - EXIT; return
  fi
  [[ $mode == install ]] || fail no_active_install_for_update
  [[ ! -e $runtime_root && ! -L $runtime_root && ! -e $wrapper && ! -L $wrapper && \
     ! -e $dropin && ! -L $dropin && ! -e $hook && ! -L $hook && ! -e $state_dir && ! -L $state_dir && \
     ! -e $managed_pam && ! -L $managed_pam ]] ||
    fail managed_path_collision
  polkit_deploy preflight managed
  [[ ! -e $(p /var/lib/goodix-polkit) && ! -L $(p /var/lib/goodix-polkit) ]] || fail polkit_deployment_collision
  verify_vendor_pam
  verify_kde_fingerprint_vendor
  verify_login_host
  [[ ! -e $greeter_dropin && ! -L $greeter_dropin ]] || fail greeter_dropin_collision
  [[ -d $(dirname "$greeter_dropin") ]] || greeter_directory_created=true
  [[ ! -L $(dirname "$plasma_dropin") ]] || fail plasma_dropin_directory_symlink
  [[ ! -e $plasma_dropin && ! -L $plasma_dropin ]] || fail plasma_dropin_collision
  [[ -d $(dirname "$plasma_dropin") ]] || plasma_directory_created=true
  if [[ -z $test_root ]]; then
    "$candidate/plasma-vt-preflight"
    [[ $(systemctl show plasmalogin.service -p FragmentPath --value) == /usr/lib/systemd/system/plasmalogin.service && \
       $(systemctl show plasmalogin.service -p DropInPaths --value) == /usr/lib/systemd/system/service.d/10-timeout-abort.conf ]] || fail plasma_unit_override
    plasma_service_before=$(systemctl is-active plasmalogin.service || true)
    [[ $plasma_service_before == active || $plasma_service_before == inactive ]] || fail plasma_service_state
  fi
  service_before=$(service_state)
  [[ $service_before == active || $service_before == inactive ]] || fail unsupported_service_state
  cleanup_kind=fresh
  cleanup_runtime=$runtime_root/$commit
  cleanup_service_before=$service_before
  host_action systemctl stop fprintd.service
  install -d -m 0755 "$state_dir" "$(dirname "$wrapper")" "$(dirname "$dropin")" "$(dirname "$hook")"
  install_policy "$candidate"
  cleanup_policy=true
  policy_source_sha=$(digest "$candidate/goodix_fprint_account_delete.te")
  policy_contexts_sha=$(digest "$candidate/goodix_fprint_account_delete.fc")
  if [[ ${GOODIX_MANAGED_TEST_FAIL_AFTER_POLICY:-false} == true ]]; then fail injected_failure_after_policy; fi
  install -m 0755 "$candidate/fprintd-wrapper" "$wrapper"
  install -m 0755 "$candidate/50-goodix-fprint-account-delete" "$hook"
  install -m 0644 "$candidate/99-goodix-27c6-5125-managed.conf" "$dropin"
  host_action restorecon -F "$hook"
  install_managed_pam "$candidate"
  cleanup_pam_installed=true
  cleanup_kde_pam_installed=true
  install_managed_kde_fingerprint_pam "$candidate"
  if [[ ${GOODIX_MANAGED_TEST_FAIL_AFTER_KSCREENLOCKER_PAM:-false} == true ]]; then
    fail injected_failure_after_kscreenlocker_pam
  fi
  install_runtime_tree "$candidate" "$commit"
  cleanup_plasma_installed=true
  install -D -m 0644 "$candidate/99-goodix-plasma-vt.conf" "$plasma_dropin"
  host_action restorecon -F "$plasma_dropin"
  cleanup_greeter_installed=true
  install -D -m 0644 "$candidate/99-goodix-login-greeter.conf" "$greeter_dropin"
  host_action restorecon -F "$greeter_dropin"
  ln -s "$commit" "$current_link"
  cleanup_polkit=true
  polkit_deploy install managed
  if [[ -n $test_root && ${GOODIX_MANAGED_TEST_FAIL_AFTER_POLKIT:-false} == true ]]; then
    fail injected_failure_after_polkit
  fi
  write_state "$commit" NONE "$caller" "$service_before" "$(tree_digest "$runtime_root/$commit")" NONE \
    ACTIVE NONE "$installed_pam_vendor_sha" "$installed_pam_override_sha" \
    ACTIVE NONE "$installed_kde_fingerprint_vendor_sha" "$installed_kde_fingerprint_override_sha"
  host_action systemctl daemon-reload
  if material_ready && [[ $service_before == active ]]; then host_action systemctl start fprintd.service; fi
  cleanup_kind=none
  printf '%s\n' 'GOODIX_MANAGED_INSTALL=PASS' "CURRENT_COMMIT=$commit" \
    "PROTECTED_MATERIAL_READY=$(material_ready && echo true || echo false)" \
    'MANAGED_PAM_INTEGRATION=true' 'PLASMALOGIN_VENDOR_MODIFIED=false' \
    'KSCREENLOCKER_MANAGED_PAM_INTEGRATION=true' 'FINGERPRINT_AUTH_GLOBAL_STACK_UNCHANGED=true'
  remove_frozen_candidate "$candidate"
  trap - EXIT
}

root_rollback() {
  local caller=$1 current previous current_digest previous_digest service_before
  local current_pam previous_pam vendor_sha override_sha
  local current_kde_pam previous_kde_pam kde_vendor_sha kde_override_sha
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  verify_active
  [[ $(state_value INSTALLER) == "$caller" ]] || fail installer_mismatch
  current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT)
  [[ $previous != NONE ]] || fail no_update_to_rollback
  current_digest=$(state_value CURRENT_TREE_SHA256); previous_digest=$(state_value PREVIOUS_TREE_SHA256)
  service_before=$(state_value SERVICE_BEFORE)
  current_pam=$(state_value CURRENT_PAM_STATUS); previous_pam=$(state_value PREVIOUS_PAM_STATUS)
  vendor_sha=$(state_value PAM_VENDOR_SHA256); override_sha=$(state_value PAM_OVERRIDE_SHA256)
  current_kde_pam=$(state_value CURRENT_KSCREENLOCKER_PAM_STATUS)
  previous_kde_pam=$(state_value PREVIOUS_KSCREENLOCKER_PAM_STATUS)
  kde_vendor_sha=$(state_value KSCREENLOCKER_VENDOR_SHA256)
  kde_override_sha=$(state_value KSCREENLOCKER_OVERRIDE_SHA256)
  rollback_saved_current=$current
  rollback_saved_pam=$current_pam
  rollback_saved_kde_pam=$current_kde_pam
  rollback_saved_service=$service_before
  rollback_pam_changed=false
  rollback_kde_pam_changed=false
  rollback_link_switched=false
  rollback_cleanup() {
    local rc=$?
    set +e
    if [[ $rc -ne 0 ]]; then
      if [[ $rollback_link_switched == true ]]; then
        ln -s "$rollback_saved_current" "$runtime_root/current.recovery"
        mv -Tf -- "$runtime_root/current.recovery" "$current_link"
      fi
      if [[ $rollback_pam_changed == true ]]; then
        if [[ $rollback_saved_pam == ACTIVE ]]; then
          install -D -m 0644 "$pam_saved" "$managed_pam"
          host_action restorecon -F "$managed_pam"
        else
          rm -f -- "$managed_pam"
        fi
      fi
      if [[ $rollback_kde_pam_changed == true ]]; then
        if [[ $rollback_saved_kde_pam == ACTIVE ]]; then
          install -m 0644 "$kde_fingerprint_managed_saved" "$kde_fingerprint_pam"
        else
          install -m 0644 "$kde_fingerprint_vendor_saved" "$kde_fingerprint_pam"
        fi
        host_action restorecon -F "$kde_fingerprint_pam"
      fi
      host_action systemctl daemon-reload
      [[ $rollback_saved_service != active ]] || host_action systemctl start fprintd.service
    fi
    trap - EXIT
    exit "$rc"
  }
  trap rollback_cleanup EXIT
  host_action systemctl stop fprintd.service
  if [[ $current_pam != "$previous_pam" ]]; then
    rollback_pam_changed=true
    if [[ $previous_pam == ACTIVE ]]; then
      restore_managed_pam "$vendor_sha" "$override_sha"
    else
      remove_managed_pam "$vendor_sha" "$override_sha"
    fi
  fi
  if [[ $current_kde_pam != "$previous_kde_pam" ]]; then
    rollback_kde_pam_changed=true
    if [[ $previous_kde_pam == ACTIVE ]]; then
      activate_managed_kde_fingerprint_pam "$kde_vendor_sha" "$kde_override_sha"
    else
      deactivate_managed_kde_fingerprint_pam "$kde_vendor_sha" "$kde_override_sha"
    fi
  fi
  ln -s "$previous" "$runtime_root/current.next"
  mv -Tf -- "$runtime_root/current.next" "$current_link"
  rollback_link_switched=true
  host_action systemctl daemon-reload
  if material_ready && [[ $service_before == active ]]; then host_action systemctl start fprintd.service; fi
  write_state "$previous" "$current" "$caller" "$service_before" "$previous_digest" "$current_digest" \
    "$previous_pam" "$current_pam" "$vendor_sha" "$override_sha" \
    "$previous_kde_pam" "$current_kde_pam" "$kde_vendor_sha" "$kde_override_sha"
  printf '%s\n' 'GOODIX_MANAGED_ROLLBACK=PASS' "CURRENT_COMMIT=$previous" "ROLLBACK_COMMIT=$current" \
    "MANAGED_PAM_STATUS=$previous_pam" "KSCREENLOCKER_MANAGED_PAM_STATUS=$previous_kde_pam" \
    'PLASMALOGIN_VENDOR_MODIFIED=false' 'FINGERPRINT_AUTH_GLOBAL_STACK_UNCHANGED=true'
  trap - EXIT
}

root_uninstall() {
  local caller=$1 current previous service_before
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  # Removal qualification must not repair permissions before Polkit's complete
  # counter validation. Status/install retain their existing legacy repair.
  verify_active true true false
  [[ $(state_value INSTALLER) == "$caller" ]] || fail installer_mismatch
  current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT); service_before=$(state_value SERVICE_BEFORE)
  # Keep a still-running vendor daemon during rollback of a staged install.
  # Stop the replacement (or a pending restart) before removing its runtime.
  local stop_plasma=true plasma_pid plasma_sha
  if [[ -n $test_root ]]; then
    stop_plasma=${GOODIX_MANAGED_TEST_PLASMA_RUNNING:-true}
    [[ $stop_plasma == true || $stop_plasma == false ]] || fail invalid_plasma_test_state
  else
    plasma_pid=$(systemctl show plasmalogin.service -p MainPID --value)
    [[ $plasma_pid =~ ^[0-9]+$ ]] || fail plasma_pid_invalid_before_uninstall
    if [[ $plasma_pid != 0 ]]; then
      plasma_sha=$(digest "/proc/$plasma_pid/exe")
      if [[ $plasma_sha != $(digest "$runtime_root/$current/plasmalogin") ]]; then
        [[ $plasma_sha == $(digest /usr/bin/plasmalogin) ]] || fail unknown_running_plasma_preserve_recovery
        stop_plasma=false
      fi
    fi
  fi
  polkit_deploy uninstall managed
  if [[ $stop_plasma == true ]]; then host_action systemctl stop plasmalogin.service; fi
  host_action systemctl stop fprintd.service
  if [[ $ACTIVE_PAM_STATE == MANAGED && $(state_value CURRENT_PAM_STATUS) == ACTIVE ]]; then
    [[ -f $managed_pam && ! -L $managed_pam && \
       $(digest "$managed_pam") == $(state_value PAM_OVERRIDE_SHA256) ]] || fail managed_pam_override_drift
    rm -f -- "$managed_pam"
  fi
  if [[ $ACTIVE_KSCREENLOCKER_PAM_STATE == MANAGED ]]; then
    if [[ $(state_value CURRENT_KSCREENLOCKER_PAM_STATUS) == ACTIVE ]]; then
      deactivate_managed_kde_fingerprint_pam \
        "$(state_value KSCREENLOCKER_VENDOR_SHA256)" "$(state_value KSCREENLOCKER_OVERRIDE_SHA256)"
    else
      verify_saved_kde_fingerprint_pam \
        "$(state_value KSCREENLOCKER_VENDOR_SHA256)" "$(state_value KSCREENLOCKER_OVERRIDE_SHA256)"
      [[ $(digest "$kde_fingerprint_pam") == $(state_value KSCREENLOCKER_VENDOR_SHA256) ]] ||
        fail kde_fingerprint_vendor_restore_drift
    fi
  fi
  remove_policy
  if [[ $ACTIVE_LOGIN_STATE == MANAGED ]]; then
    rm -f -- "$greeter_dropin"
    if [[ $greeter_directory_created == true ]]; then rmdir -- "$(dirname "$greeter_dropin")" 2>/dev/null || true; fi
  fi
  rm -f -- "$plasma_dropin"
  if [[ $plasma_directory_created == true ]]; then rmdir -- "$(dirname "$plasma_dropin")" 2>/dev/null || true; fi
  rm -f -- "$current_link" "$wrapper" "$dropin" "$hook"
  find "$runtime_root/$current" -xdev -depth -delete
  if [[ $previous != NONE ]]; then find "$runtime_root/$previous" -xdev -depth -delete; fi
  rmdir -- "$runtime_root" 2>/dev/null || true
  rm -f -- "$pam_saved" "$kde_fingerprint_vendor_saved" "$kde_fingerprint_managed_saved" "$state"
  rmdir -- "$state_dir" 2>/dev/null || true
  host_action systemctl daemon-reload
  [[ $service_before != active ]] || host_action systemctl start fprintd.service
  if [[ ${GOODIX_DEFER_PLASMA_RESTART:-false} != true && $plasma_service_before == active ]]; then
    host_action systemctl start plasmalogin.service
  fi
  printf '%s\n' 'GOODIX_MANAGED_UNINSTALL=PASS' 'PROTECTED_MATERIAL_PRESERVED=true' \
    'FEDORA_FPRINTD_BASELINE=RESTORED' 'MANAGED_PAM_REMOVED=true' \
    'KSCREENLOCKER_VENDOR_PAM_RESTORED=true' 'PLASMALOGIN_VENDOR_MODIFIED=false' \
    'FINGERPRINT_AUTH_GLOBAL_STACK_UNCHANGED=true'
}

root_import_materials() {
  local caller=$1 source=$2 name staging
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  [[ $source == /* && -d $source && ! -L $source ]] || fail material_source_invalid
  [[ -n $test_root || $(stat -c %U "$source") == "$caller" ]] || fail material_source_owner_invalid
  for name in "${required_material[@]}"; do
    [[ -f $source/$name && ! -L $source/$name ]] || fail "material_source_${name}_invalid"
  done
  [[ ! -e $material && ! -L $material ]] || fail material_destination_collision
  staging=$material.pending.$$
  install -d -m 0700 "$staging"
  for name in "${required_material[@]}"; do install -m 0600 "$source/$name" "$staging/$name"; done
  if [[ -z $test_root ]]; then chown -R root:root "$staging"; fi
  mv -- "$staging" "$material"
  printf '%s\n' 'GOODIX_MANAGED_MATERIAL_IMPORT=PASS' 'MATERIAL_CONTENT_LOGGED=false' 'SOURCE_FILES_PRESERVED=true'
}

case ${1:-} in
  --root-install|--root-update)
    [[ $# -eq 3 ]] || fail root_install_usage
    root_install_or_update "${1#--root-}" "$2" "$3"
    ;;
  --root-rollback|--root-uninstall)
    [[ $# -eq 2 ]] || fail root_remove_usage
    if [[ $1 == --root-rollback ]]; then root_rollback "$2"; else root_uninstall "$2"; fi
    ;;
  --root-import-materials)
    [[ $# -eq 3 ]] || fail root_import_usage
    root_import_materials "$2" "$3"
    ;;
  --status)
    [[ $# -eq 1 ]] || fail status_usage
    verify_active true
    if [[ $ACTIVE_PAM_STATE == LEGACY ]]; then
      verify_vendor_pam
      pam_status=ABSENT
      pam_managed=false
    else
      pam_status=$(state_value CURRENT_PAM_STATUS)
      pam_managed=true
    fi
    if [[ $ACTIVE_KSCREENLOCKER_PAM_STATE == LEGACY ]]; then
      kde_pam_status=ABSENT
      kde_pam_managed=false
    else
      kde_pam_status=$(state_value CURRENT_KSCREENLOCKER_PAM_STATUS)
      kde_pam_managed=true
    fi
    plasma_activation=RESTART_REQUIRED
    if [[ -z $test_root ]]; then
      plasma_pid=$(systemctl show plasmalogin.service -p MainPID --value)
      if [[ $plasma_pid =~ ^[1-9][0-9]*$ && -r /proc/$plasma_pid/exe && $(digest "/proc/$plasma_pid/exe") == $(digest "$current_link/plasmalogin") ]]; then
        plasma_activation=RUNNING_CORRECTIVE
      fi
    fi
    printf '%s\n' "PLASMA_VT_ACTIVATION=$plasma_activation"
    printf '%s\n' 'GOODIX_MANAGED_STATUS=ACTIVE' "EARLY_LOGIN_STATUS=$ACTIVE_LOGIN_STATE" "CURRENT_COMMIT=$(state_value CURRENT_COMMIT)" \
      "PREVIOUS_COMMIT=$(state_value PREVIOUS_COMMIT)" \
      "PROTECTED_MATERIAL_READY=$(material_ready && echo true || echo false)" \
      'RPM_OFFICIAL_DISTRIBUTION=false' 'SUDO_INTEGRATION=PASSWORD_FIRST_SERVICE_LOCAL_V1' 'POLKIT_INTEGRATION=INTERRUPTIBLE_SERVICE_LOCAL_V1' "MANAGED_PAM_INTEGRATION=$pam_managed" \
      "MANAGED_PAM_STATUS=$pam_status" \
      "KSCREENLOCKER_MANAGED_PAM_INTEGRATION=$kde_pam_managed" \
      "KSCREENLOCKER_MANAGED_PAM_STATUS=$kde_pam_status" \
      'PLASMALOGIN_VENDOR_MODIFIED=false' 'FINGERPRINT_AUTH_GLOBAL_STACK_UNCHANGED=true'
    ;;
  *) fail internal_usage ;;
esac
