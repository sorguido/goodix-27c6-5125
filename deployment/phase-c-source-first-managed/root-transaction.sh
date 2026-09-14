#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
repo=$(git -C "$here" rev-parse --show-toplevel)
test_root=${GOODIX_MANAGED_TEST_ROOT:-}
if [[ -n $test_root ]]; then
  [[ $test_root == /tmp/goodix-managed-test.* && -d $test_root && -O $test_root && ! -L $test_root ]] || {
    echo 'PHASE_C_TRANSACTION=FAIL reason=unsafe_test_root' >&2; exit 1;
  }
fi
p() { printf '%s%s\n' "$test_root" "$1"; }

state_dir=$(p /var/lib/goodix-27c6-5125-managed)
state=$state_dir/state
runtime_root=$(p /usr/lib64/goodix-27c6-5125)
current_link=$runtime_root/current
wrapper=$(p /usr/libexec/goodix-27c6-5125/fprintd-wrapper)
dropin=$(p /etc/systemd/system/fprintd.service.d/99-goodix-27c6-5125-managed.conf)
hook=$(p /etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete)
vendor_pam=$(p /usr/lib/pam.d/plasmalogin)
managed_pam=$(p /etc/pam.d/plasmalogin)
pam_saved=$state_dir/plasmalogin.managed
material=$(p /var/lib/goodix-5125-poc)
policy_name=goodix_fprint_account_delete
policy_priority=400
expected_pam_rule='auth        sufficient                                   pam_fprintd.so'
required_candidate=(
  MANIFEST SHA256SUMS LICENSE GPL-2.0-or-later.txt LGPL-2.1-or-later.txt
  libfprint-2.so.2.0.0 libgusb.so.2
  libopencv_core.so.413 libopencv_features2d.so.413 libopencv_flann.so.413
  libopencv_imgproc.so.413 fprintd-wrapper 50-goodix-fprint-account-delete
  goodix_fprint_account_delete.te goodix_fprint_account_delete.fc
  99-goodix-27c6-5125-managed.conf plasmalogin-pam.rule
)
required_material=(target-material-manifest.json transport-material.bin target-config-90.bin gfusb.dll fdt-cache.bin)

fail() { printf 'PHASE_C_TRANSACTION=FAIL reason=%s\n' "$1" >&2; exit 1; }
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
  [[ -n $test_root ]] && return 0
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
  [[ $(git -C "$repo" branch --show-current) == development ]] || fail wrong_branch
  [[ $(git -C "$repo" rev-parse HEAD) == "$expected" ]] || fail source_head_mismatch
  [[ $(git -C "$repo" rev-parse origin/development) == "$expected" ]] || fail origin_head_mismatch
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
  (cd "$candidate" && sha256sum -c SHA256SUMS >/dev/null) || fail candidate_digest_mismatch
  [[ $(manifest_value "$candidate" PHASE_C_DISTRIBUTION_MODEL) == SOURCE_FIRST_MANAGED_INSTALL ]] || fail distribution_model_invalid
  [[ $(manifest_value "$candidate" RPM_OFFICIAL_DISTRIBUTION) == false ]] || fail rpm_policy_invalid
  [[ $(manifest_value "$candidate" PROTECTED_MATERIAL_INCLUDED) == false ]] || fail candidate_contains_material
  [[ $(manifest_value "$candidate" PAM_FILES_INCLUDED) == true ]] || fail managed_pam_rule_missing
  [[ $(manifest_value "$candidate" PAM_INTEGRATION) == MANAGED_ETC_OVERRIDE_FROM_VENDOR ]] || fail pam_integration_model_invalid
  commit=$(manifest_value "$candidate" SOURCE_COMMIT) || fail candidate_commit_missing
  is_commit "$commit" || fail candidate_commit_invalid
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
  mkdir -p -- "$runtime_root"
  install -d -m 0755 -- "$destination"
  for library in libfprint-2.so.2.0.0 libgusb.so.2 libopencv_core.so.413 \
    libopencv_features2d.so.413 libopencv_flann.so.413 libopencv_imgproc.so.413; do
    install -m 0644 -- "$candidate/$library" "$destination/$library"
  done
  ln -s libfprint-2.so.2.0.0 "$destination/libfprint-2.so.2"
  ln -s libfprint-2.so.2 "$destination/libfprint-2.so"
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
write_state() {
  local current=$1 previous=$2 installer=$3 service_before=$4 current_digest=$5 previous_digest=$6
  local current_pam=$7 previous_pam=$8 pam_vendor_sha=$9 pam_override_sha=${10}
  local pending=$state.pending.$$
  {
    echo PHASE_C_STATUS=ACTIVE
    echo PHASE_C_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL
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
    echo "CURRENT_PAM_STATUS=$current_pam"
    echo "PREVIOUS_PAM_STATUS=$previous_pam"
    echo "PAM_VENDOR_SHA256=$pam_vendor_sha"
    echo "PAM_OVERRIDE_SHA256=$pam_override_sha"
  } >"$pending"
  chmod 0644 "$pending"
  mv -f -- "$pending" "$state"
}
verify_active() {
  local allow_legacy=${1:-false}
  local allow_vendor_drift=${2:-false}
  [[ -f $state && ! -L $state ]] || fail state_missing
  [[ $(state_value PHASE_C_STATUS) == ACTIVE ]] || fail state_inactive
  local current previous expected
  current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT)
  is_commit "$current" || fail current_commit_invalid
  [[ $previous == NONE ]] || is_commit "$previous" || fail previous_commit_invalid
  [[ -L $current_link && $(readlink "$current_link") == "$current" ]] || fail current_link_drift
  [[ $(tree_digest "$runtime_root/$current") == $(state_value CURRENT_TREE_SHA256) ]] || fail current_tree_drift
  if [[ $previous != NONE ]]; then
    [[ -d $runtime_root/$previous && ! -L $runtime_root/$previous ]] || fail previous_tree_missing
    [[ $(tree_digest "$runtime_root/$previous") == $(state_value PREVIOUS_TREE_SHA256) ]] || fail previous_tree_drift
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
    ACTIVE_PAM_STATE=LEGACY
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
}

root_install_or_update() {
  local mode=$1 caller=$2 source_candidate=$3 candidate commit current previous service_before installer
  local current_pam pam_vendor_sha pam_override_sha
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  candidate=$(freeze_candidate "$source_candidate" "$caller")
  cleanup_kind=none
  cleanup_runtime=
  cleanup_policy=false
  cleanup_old_current=
  cleanup_link_switched=false
  cleanup_service_before=inactive
  cleanup_pam_installed=false
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
      host_action systemctl daemon-reload
      [[ $cleanup_service_before != active ]] || host_action systemctl start fprintd.service
    elif [[ $rc -ne 0 && $cleanup_kind == fresh ]]; then
      rm -f -- "$current_link" "$wrapper" "$dropin" "$hook" "$managed_pam" "$pam_saved" "$state"
      [[ -z $cleanup_runtime || ! -d $cleanup_runtime ]] || find "$cleanup_runtime" -xdev -depth -delete
      rmdir -- "$runtime_root" 2>/dev/null
      [[ $cleanup_policy != true ]] || remove_policy
      rmdir -- "$state_dir" 2>/dev/null
      host_action systemctl daemon-reload
      [[ $cleanup_service_before != active ]] || host_action systemctl start fprintd.service
    fi
    remove_frozen_candidate "$candidate"
    exit "$rc"
  }
  trap cleanup_transaction EXIT
  commit=$(verify_candidate "$candidate" "$caller" true)
  verify_pam_rule "$candidate"
  if [[ -f $state ]]; then
    verify_active true
    current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT)
    if [[ $commit == "$current" ]]; then
      [[ $ACTIVE_PAM_STATE != LEGACY ]] || fail same_commit_requires_pam_corrective_update
      printf '%s\n' 'PHASE_C_INSTALL=PASS_ALREADY_CURRENT' "CURRENT_COMMIT=$current"
      remove_frozen_candidate "$candidate"; trap - EXIT; return
    fi
    [[ $mode == update ]] || fail active_install_requires_update
    [[ $previous == NONE ]] || fail rollback_slot_occupied
    [[ $(digest "$candidate/fprintd-wrapper") == $(state_value WRAPPER_SHA256) && \
       $(digest "$candidate/99-goodix-27c6-5125-managed.conf") == $(state_value DROPIN_SHA256) && \
       $(digest "$candidate/50-goodix-fprint-account-delete") == $(state_value HOOK_SHA256) ]] ||
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
    install_runtime_tree "$candidate" "$commit"
    ln -s "$commit" "$runtime_root/current.next"
    mv -Tf -- "$runtime_root/current.next" "$current_link"
    cleanup_link_switched=true
    host_action systemctl restart fprintd.service
    write_state "$commit" "$current" "$installer" "$cleanup_service_before" \
      "$(tree_digest "$runtime_root/$commit")" "$(tree_digest "$runtime_root/$current")" \
      ACTIVE "$current_pam" "$pam_vendor_sha" "$pam_override_sha"
    cleanup_kind=none
    printf '%s\n' 'PHASE_C_UPDATE=PASS' "CURRENT_COMMIT=$commit" "ROLLBACK_COMMIT=$current"
    remove_frozen_candidate "$candidate"; trap - EXIT; return
  fi
  [[ $mode == install ]] || fail no_active_install_for_update
  [[ ! -e $runtime_root && ! -L $runtime_root && ! -e $wrapper && ! -L $wrapper && \
     ! -e $dropin && ! -L $dropin && ! -e $hook && ! -L $hook && ! -e $state_dir && ! -L $state_dir && \
     ! -e $managed_pam && ! -L $managed_pam ]] ||
    fail managed_path_collision
  verify_vendor_pam
  service_before=$(service_state)
  [[ $service_before == active || $service_before == inactive ]] || fail unsupported_service_state
  cleanup_kind=fresh
  cleanup_runtime=$runtime_root/$commit
  cleanup_service_before=$service_before
  host_action systemctl stop fprintd.service
  install -d -m 0755 "$state_dir" "$(dirname "$wrapper")" "$(dirname "$dropin")" "$(dirname "$hook")"
  install_policy "$candidate"
  cleanup_policy=true
  if [[ ${GOODIX_MANAGED_TEST_FAIL_AFTER_POLICY:-false} == true ]]; then fail injected_failure_after_policy; fi
  install -m 0755 "$candidate/fprintd-wrapper" "$wrapper"
  install -m 0755 "$candidate/50-goodix-fprint-account-delete" "$hook"
  install -m 0644 "$candidate/99-goodix-27c6-5125-managed.conf" "$dropin"
  host_action restorecon -F "$hook"
  install_managed_pam "$candidate"
  cleanup_pam_installed=true
  install_runtime_tree "$candidate" "$commit"
  ln -s "$commit" "$current_link"
  write_state "$commit" NONE "$caller" "$service_before" "$(tree_digest "$runtime_root/$commit")" NONE \
    ACTIVE NONE "$installed_pam_vendor_sha" "$installed_pam_override_sha"
  host_action systemctl daemon-reload
  if material_ready && [[ $service_before == active ]]; then host_action systemctl start fprintd.service; fi
  cleanup_kind=none
  printf '%s\n' 'PHASE_C_INSTALL=PASS' "CURRENT_COMMIT=$commit" \
    "PROTECTED_MATERIAL_READY=$(material_ready && echo true || echo false)" \
    'MANAGED_PAM_INTEGRATION=true' 'PLASMALOGIN_VENDOR_MODIFIED=false'
  remove_frozen_candidate "$candidate"
  trap - EXIT
}

root_rollback() {
  local caller=$1 current previous current_digest previous_digest service_before
  local current_pam previous_pam vendor_sha override_sha
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  verify_active
  [[ $(state_value INSTALLER) == "$caller" ]] || fail installer_mismatch
  current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT)
  [[ $previous != NONE ]] || fail no_update_to_rollback
  current_digest=$(state_value CURRENT_TREE_SHA256); previous_digest=$(state_value PREVIOUS_TREE_SHA256)
  service_before=$(state_value SERVICE_BEFORE)
  current_pam=$(state_value CURRENT_PAM_STATUS); previous_pam=$(state_value PREVIOUS_PAM_STATUS)
  vendor_sha=$(state_value PAM_VENDOR_SHA256); override_sha=$(state_value PAM_OVERRIDE_SHA256)
  rollback_pam_changed=false
  rollback_link_switched=false
  rollback_cleanup() {
    local rc=$?
    set +e
    if [[ $rc -ne 0 ]]; then
      if [[ $rollback_link_switched == true ]]; then
        ln -s "$current" "$runtime_root/current.recovery"
        mv -Tf -- "$runtime_root/current.recovery" "$current_link"
      fi
      if [[ $rollback_pam_changed == true ]]; then
        if [[ $current_pam == ACTIVE ]]; then
          install -D -m 0644 "$pam_saved" "$managed_pam"
          host_action restorecon -F "$managed_pam"
        else
          rm -f -- "$managed_pam"
        fi
      fi
      host_action systemctl daemon-reload
      [[ $service_before != active ]] || host_action systemctl start fprintd.service
    fi
    trap - EXIT
    exit "$rc"
  }
  trap rollback_cleanup EXIT
  host_action systemctl stop fprintd.service
  if [[ $current_pam != "$previous_pam" ]]; then
    if [[ $previous_pam == ACTIVE ]]; then
      restore_managed_pam "$vendor_sha" "$override_sha"
    else
      remove_managed_pam "$vendor_sha" "$override_sha"
    fi
    rollback_pam_changed=true
  fi
  ln -s "$previous" "$runtime_root/current.next"
  mv -Tf -- "$runtime_root/current.next" "$current_link"
  rollback_link_switched=true
  write_state "$previous" "$current" "$caller" "$service_before" "$previous_digest" "$current_digest" \
    "$previous_pam" "$current_pam" "$vendor_sha" "$override_sha"
  host_action systemctl daemon-reload
  if material_ready && [[ $service_before == active ]]; then host_action systemctl start fprintd.service; fi
  printf '%s\n' 'PHASE_C_ROLLBACK=PASS' "CURRENT_COMMIT=$previous" "ROLLBACK_COMMIT=$current" \
    "MANAGED_PAM_STATUS=$previous_pam" 'PLASMALOGIN_VENDOR_MODIFIED=false'
  trap - EXIT
}

root_uninstall() {
  local caller=$1 current previous service_before
  [[ -n $test_root || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  verify_active true true
  [[ $(state_value INSTALLER) == "$caller" ]] || fail installer_mismatch
  current=$(state_value CURRENT_COMMIT); previous=$(state_value PREVIOUS_COMMIT); service_before=$(state_value SERVICE_BEFORE)
  host_action systemctl stop fprintd.service
  if [[ $ACTIVE_PAM_STATE == MANAGED && $(state_value CURRENT_PAM_STATUS) == ACTIVE ]]; then
    [[ -f $managed_pam && ! -L $managed_pam && \
       $(digest "$managed_pam") == $(state_value PAM_OVERRIDE_SHA256) ]] || fail managed_pam_override_drift
    rm -f -- "$managed_pam"
  fi
  remove_policy
  rm -f -- "$current_link" "$wrapper" "$dropin" "$hook"
  find "$runtime_root/$current" -xdev -depth -delete
  if [[ $previous != NONE ]]; then find "$runtime_root/$previous" -xdev -depth -delete; fi
  rmdir -- "$runtime_root" 2>/dev/null || true
  rm -f -- "$pam_saved" "$state"
  rmdir -- "$state_dir" 2>/dev/null || true
  host_action systemctl daemon-reload
  [[ $service_before != active ]] || host_action systemctl start fprintd.service
  printf '%s\n' 'PHASE_C_UNINSTALL=PASS' 'PROTECTED_MATERIAL_PRESERVED=true' \
    'FEDORA_FPRINTD_BASELINE=RESTORED' 'MANAGED_PAM_REMOVED=true' 'PLASMALOGIN_VENDOR_MODIFIED=false'
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
  printf '%s\n' 'PHASE_C_MATERIAL_IMPORT=PASS' 'MATERIAL_CONTENT_LOGGED=false' 'SOURCE_FILES_PRESERVED=true'
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
      pam_status=ABSENT
      pam_managed=false
    else
      pam_status=$(state_value CURRENT_PAM_STATUS)
      pam_managed=true
    fi
    printf '%s\n' 'PHASE_C_STATUS=ACTIVE' "CURRENT_COMMIT=$(state_value CURRENT_COMMIT)" \
      "PREVIOUS_COMMIT=$(state_value PREVIOUS_COMMIT)" \
      "PROTECTED_MATERIAL_READY=$(material_ready && echo true || echo false)" \
      'RPM_OFFICIAL_DISTRIBUTION=false' "MANAGED_PAM_INTEGRATION=$pam_managed" \
      "MANAGED_PAM_STATUS=$pam_status" 'PLASMALOGIN_VENDOR_MODIFIED=false'
    ;;
  *) fail internal_usage ;;
esac
