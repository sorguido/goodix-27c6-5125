#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
runtime_names=(libfprint-2.so.2.0.0 libgusb.so.2 libopencv_core.so.413
  libopencv_features2d.so.413 libopencv_flann.so.413 libopencv_imgproc.so.413)

fail() {
  printf 'D293_NATIVE_PATCH=FAIL reason=%s\n' "$1" >&2
  exit 1
}

is_sha256() { [[ ${1:-} =~ ^[0-9a-f]{64}$ ]]; }
is_git_sha() { [[ ${1:-} =~ ^[0-9a-f]{40}$ ]]; }

state_value() {
  local file=$1 key=$2 count value
  count=$(awk -F= -v key="$key" '$1 == key { count++ } END { print count + 0 }' "$file")
  [[ $count -eq 1 ]] || return 1
  value=$(awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print }' "$file")
  [[ $value != *$'\n'* ]] || return 1
  printf '%s\n' "$value"
}

test_mode=${D293_NATIVE_TEST_MODE:-false}
fsroot=
systemctl_cmd=/usr/bin/systemctl
restorecon_cmd=/usr/sbin/restorecon
if [[ $test_mode == true ]]; then
  fsroot=${D293_NATIVE_TEST_ROOT:?}
  command_dir=${D293_NATIVE_TEST_COMMAND_DIR:?}
  [[ $fsroot == /tmp/d293-native-test.* && -d $fsroot && -O $fsroot && ! -L $fsroot ]] ||
    fail unsafe_test_root
  [[ -d $command_dir && -O $command_dir && ! -L $command_dir ]] || fail unsafe_test_commands
  for command in systemctl restorecon; do
    [[ -f $command_dir/$command && -x $command_dir/$command && -O $command_dir/$command &&
       ! -L $command_dir/$command ]] || fail "unsafe_test_command_$command"
  done
  systemctl_cmd=$command_dir/systemctl
  restorecon_cmd=$command_dir/restorecon
elif [[ $test_mode != false ]]; then
  fail invalid_test_mode
fi

p() { printf '%s%s\n' "$fsroot" "$1"; }

state=$(p /etc/goodix-27c6-5125/d293-native.state)
d285_state=$(p /etc/goodix-27c6-5125/d285-01.state)
d285_wrapper=$(p /usr/local/sbin/goodix-d285-01-fprintd)
d285_dropin=$(p /etc/systemd/system/fprintd.service.d/90-goodix-d285-01.conf)
d285_pam=$(p /etc/pam.d/goodix-d285-01-sudo)
d285_sudoers=$(p /etc/sudoers.d/90-goodix-d285-01)
wrapper=$(p /usr/local/sbin/goodix-d293-native-fprintd)
dropin=$(p /etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf)
runtime_parent=$(p /usr/local/lib64/goodix-27c6-5125)
daemon=$(p /usr/libexec/fprintd)

require_regular() {
  [[ -f $1 && ! -L $1 ]] || fail "$2"
}

require_directory() {
  [[ -d $1 && ! -L $1 ]] || fail "$2"
}

validate_wrapper_parent() {
  local parent=$1 target
  if [[ -L $parent ]]; then
    [[ $(readlink "$parent") == bin ]] || fail wrapper_parent_invalid
    target="$(dirname "$parent")/bin"
    require_directory "$target" wrapper_parent_target_invalid
  else
    require_directory "$parent" wrapper_parent_invalid
  fi
}

digest() { sha256sum "$1" | awk '{print $1}'; }

verify_hash() {
  local path=$1 expected=$2 reason=$3
  require_regular "$path" "$reason"
  is_sha256 "$expected" || fail state_hash_invalid
  [[ $(digest "$path") == "$expected" ]] || fail "$reason"
}

validate_candidate_manifest() {
  local candidate=$1 name count expected
  require_regular "$candidate/deploy.sha256" candidate_manifest_missing
  [[ $(wc -l <"$candidate/deploy.sha256") -eq ${#runtime_names[@]} ]] ||
    fail candidate_manifest_path_set_invalid
  awk 'NF != 2 || $1 !~ /^[0-9a-f]{64}$/ { exit 1 }' "$candidate/deploy.sha256" ||
    fail candidate_manifest_format_invalid
  for name in "${runtime_names[@]}"; do
    count=$(awk -v name="$name" '$2 == name { count++ } END { print count + 0 }' \
      "$candidate/deploy.sha256")
    [[ $count -eq 1 ]] || fail candidate_manifest_path_set_invalid
    expected=$(awk -v name="$name" '$2 == name { print $1 }' "$candidate/deploy.sha256")
    require_regular "$candidate/$name" candidate_artifact_invalid
    [[ $(digest "$candidate/$name") == "$expected" ]] || fail candidate_artifact_drift
  done
}

validate_d285_previous() {
  local d285_runtime baseline daemon_sha pam_sha sudoers_sha wrapper_sha dropin_sha manifest_sha
  require_regular "$d285_state" d285_state_missing
  [[ $(stat -c %a "$d285_state") == 600 ]] || fail d285_state_mode_drift
  [[ $(state_value "$d285_state" D285_01_INSTALL_STATUS) == ACTIVE ]] || fail d285_not_active
  baseline=$(state_value "$d285_state" D285_01_BASELINE_SHA) || fail d285_state_invalid
  is_git_sha "$baseline" || fail d285_baseline_invalid
  d285_runtime=$(state_value "$d285_state" D285_01_RUNTIME) || fail d285_state_invalid
  if [[ -n $fsroot ]]; then d285_runtime="$fsroot$d285_runtime"; fi
  [[ $d285_runtime == "$runtime_parent/d285-01-$baseline" && -d $d285_runtime && ! -L $d285_runtime ]] ||
    fail d285_runtime_drift
  daemon_sha=$(state_value "$d285_state" D285_01_DAEMON_SHA256) || fail d285_state_invalid
  pam_sha=$(state_value "$d285_state" D285_01_PAM_SHA256) || fail d285_state_invalid
  sudoers_sha=$(state_value "$d285_state" D285_01_SUDOERS_SHA256) || fail d285_state_invalid
  wrapper_sha=$(state_value "$d285_state" D285_01_WRAPPER_SHA256) || fail d285_state_invalid
  dropin_sha=$(state_value "$d285_state" D285_01_DROPIN_SHA256) || fail d285_state_invalid
  manifest_sha=$(state_value "$d285_state" D285_01_MANIFEST_SHA256) || fail d285_state_invalid
  verify_hash "$daemon" "$daemon_sha" d285_daemon_drift
  verify_hash "$d285_pam" "$pam_sha" d285_pam_drift
  verify_hash "$d285_sudoers" "$sudoers_sha" d285_sudoers_drift
  verify_hash "$d285_wrapper" "$wrapper_sha" d285_wrapper_drift
  verify_hash "$d285_dropin" "$dropin_sha" d285_dropin_drift
  verify_hash "$d285_runtime/artifacts.sha256" "$manifest_sha" d285_manifest_drift
  (cd "$d285_runtime" && sha256sum -c artifacts.sha256 >/dev/null) || fail d285_runtime_artifact_drift
  [[ -L $d285_runtime/libfprint-2.so.2 &&
     $(readlink "$d285_runtime/libfprint-2.so.2") == libfprint-2.so.2.0.0 ]] ||
    fail d285_runtime_symlink_drift
  [[ -L $d285_runtime/libfprint-2.so &&
     $(readlink "$d285_runtime/libfprint-2.so") == libfprint-2.so.2 ]] ||
    fail d285_runtime_symlink_drift
  printf '%s\n' "$d285_runtime"
}

unit_snapshot_sha() {
  "$systemctl_cmd" cat fprintd.service | sha256sum | awk '{print $1}'
}

write_wrapper() {
  local runtime=$1 daemon_sha=$2 output=$3
  cat >"$output" <<EOF
#!/usr/bin/env bash
set -euo pipefail
runtime='$runtime'
expected_daemon_sha='$daemon_sha'
actual_daemon_sha=\$(sha256sum '$daemon' | awk '{print \$1}')
[[ \$actual_daemon_sha == "\$expected_daemon_sha" ]] || exit 126
[[ -d \$runtime && ! -L \$runtime ]] || exit 126
[[ -L \$runtime/libfprint-2.so.2 && \$(readlink "\$runtime/libfprint-2.so.2") == libfprint-2.so.2.0.0 ]] || exit 126
[[ -L \$runtime/libfprint-2.so && \$(readlink "\$runtime/libfprint-2.so") == libfprint-2.so.2 ]] || exit 126
(cd "\$runtime" && sha256sum -c artifacts.sha256 >/dev/null) || exit 126
exec env LD_LIBRARY_PATH="\$runtime" FP_DRIVERS_ALLOWLIST=goodix_27c6_5125 '$daemon'
EOF
  chmod 0755 "$output"
}

remove_runtime() {
  local target=$1
  [[ $target == "$runtime_parent"/d293-native-[0-9a-f][0-9a-f]* && -d $target && ! -L $target ]] ||
    return 1
  find "$target" -xdev -depth -delete
}

root_install() {
  local candidate=$1 head=$2 installer=$3 runtime d285_runtime unit_before daemon_sha
  local manifest_sha wrapper_sha dropin_sha d285_wrapper_sha d285_dropin_sha d285_manifest_sha script_sha
  local temp_state mutated=false service_before
  [[ $test_mode == true || $EUID -eq 0 ]] || fail install_requires_root
  is_git_sha "$head" || fail candidate_head_invalid
  [[ $installer =~ ^[a-z_][a-z0-9_-]*$ ]] || fail installer_invalid
  if [[ $test_mode == true ]]; then
    [[ $candidate == "$fsroot"/candidate && -d $candidate && ! -L $candidate ]] || fail candidate_path_invalid
  else
    [[ $candidate == /tmp/goodix-d293-native-build.*/output && -d $candidate && ! -L $candidate ]] ||
      fail candidate_path_invalid
    [[ ${SUDO_USER:-} == "$installer" ]] || fail installer_identity_mismatch
    [[ $(git -C "$root" branch --show-current) == development ]] || fail wrong_branch
    [[ $(git -C "$root" rev-parse HEAD) == "$head" ]] || fail candidate_head_mismatch
    [[ $(git -C "$root" rev-parse origin/development) == "$head" ]] || fail origin_head_mismatch
    [[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
  fi
  validate_candidate_manifest "$candidate"
  [[ ! -e $state && ! -L $state && ! -e $wrapper && ! -L $wrapper && ! -e $dropin && ! -L $dropin ]] ||
    fail patch_already_present_or_collision
  d285_runtime=$(validate_d285_previous)
  require_directory "$runtime_parent" runtime_parent_invalid
  validate_wrapper_parent "$(dirname "$wrapper")"
  require_directory "$(dirname "$dropin")" dropin_parent_invalid
  require_directory "$(dirname "$state")" state_parent_invalid
  service_before=$("$systemctl_cmd" is-active fprintd.service) || true
  [[ $service_before == active || $service_before == inactive ]] || fail fprintd_state_unsupported
  unit_before=$(unit_snapshot_sha) || fail service_snapshot_failed
  is_sha256 "$unit_before" || fail service_snapshot_invalid
  runtime="$runtime_parent/d293-native-$head"
  [[ ! -e $runtime && ! -L $runtime ]] || fail runtime_collision
  daemon_sha=$(digest "$daemon")
  d285_wrapper_sha=$(digest "$d285_wrapper")
  d285_dropin_sha=$(digest "$d285_dropin")
  d285_manifest_sha=$(digest "$d285_runtime/artifacts.sha256")
  script_sha=$(digest "$here/install.sh")
  temp_state="$state.pending.$$"
  cleanup_failed_install() {
    local rc=$?
    if [[ $mutated == true ]]; then
      [[ ! -f $dropin || -L $dropin ]] || rm -f -- "$dropin"
      [[ ! -f $wrapper || -L $wrapper ]] || rm -f -- "$wrapper"
      [[ ! -d $runtime || -L $runtime ]] || remove_runtime "$runtime" || true
      rm -f -- "$temp_state" "$state"
      "$systemctl_cmd" daemon-reload >/dev/null 2>&1 || true
      if [[ $service_before == active ]]; then
        "$systemctl_cmd" start fprintd.service >/dev/null 2>&1 || true
      else
        "$systemctl_cmd" stop fprintd.service >/dev/null 2>&1 || true
      fi
    fi
    exit "$rc"
  }
  trap cleanup_failed_install EXIT INT TERM
  if [[ $service_before == active ]]; then
    mutated=true
    "$systemctl_cmd" stop fprintd.service
    [[ $("$systemctl_cmd" is-active fprintd.service) == inactive ]] || fail service_stop_failed
  fi
  mutated=true
  install -d -m 0755 "$runtime"
  for name in "${runtime_names[@]}"; do install -m 0644 "$candidate/$name" "$runtime/$name"; done
  ln -s libfprint-2.so.2.0.0 "$runtime/libfprint-2.so.2"
  ln -s libfprint-2.so.2 "$runtime/libfprint-2.so"
  (cd "$runtime" && sha256sum "${runtime_names[@]}" >artifacts.sha256)
  write_wrapper "$runtime" "$daemon_sha" "$wrapper"
  cat >"$dropin" <<EOF
[Service]
ExecStart=
ExecStart=$wrapper
EOF
  chmod 0644 "$dropin"
  "$restorecon_cmd" -RF "$runtime" "$wrapper" "$dropin"
  manifest_sha=$(digest "$runtime/artifacts.sha256")
  wrapper_sha=$(digest "$wrapper")
  dropin_sha=$(digest "$dropin")
  cat >"$temp_state" <<EOF
D293_NATIVE_STATUS=ACTIVE
D293_NATIVE_PRODUCTION_HEAD=$head
D293_NATIVE_INSTALLER=$installer
D293_NATIVE_RUNTIME=${runtime#"$fsroot"}
D293_NATIVE_MANIFEST_SHA256=$manifest_sha
D293_NATIVE_WRAPPER_SHA256=$wrapper_sha
D293_NATIVE_DROPIN_SHA256=$dropin_sha
D293_NATIVE_INSTALL_SCRIPT_SHA256=$script_sha
D293_NATIVE_PREVIOUS_SERVICE_STATE=$service_before
D293_NATIVE_PREVIOUS_UNIT_SNAPSHOT_SHA256=$unit_before
D293_NATIVE_PREVIOUS_D285_WRAPPER_SHA256=$d285_wrapper_sha
D293_NATIVE_PREVIOUS_D285_DROPIN_SHA256=$d285_dropin_sha
D293_NATIVE_PREVIOUS_D285_MANIFEST_SHA256=$d285_manifest_sha
D293_NATIVE_PREVIOUS_OWN_PATHS=ABSENT
EOF
  chmod 0600 "$temp_state"
  mv -- "$temp_state" "$state"
  "$restorecon_cmd" "$state"
  "$systemctl_cmd" daemon-reload
  "$systemctl_cmd" show -p ExecStart --value fprintd.service | grep -F "$wrapper" >/dev/null ||
    fail candidate_not_effective
  if [[ $service_before == active ]]; then
    "$systemctl_cmd" start fprintd.service
  fi
  [[ $("$systemctl_cmd" is-active fprintd.service) == "$service_before" ]] || fail service_state_changed
  trap - EXIT INT TERM
  printf '%s\n' \
    'D293_NATIVE_INSTALL=PASS' \
    "D293_NATIVE_PRODUCTION_HEAD=$head" \
    "D293_NATIVE_RUNTIME=${runtime#"$fsroot"}" \
    'D293_NATIVE_PREVIOUS_SOFTWARE=D285_PRESERVED' \
    "D293_NATIVE_SERVICE_STATE=$service_before"
}

root_uninstall() {
  local caller=$1 head runtime expected_manifest expected_wrapper expected_dropin expected_unit
  local expected_d285_wrapper expected_d285_dropin expected_d285_manifest d285_runtime service_before
  local expected_script
  local removing_dropin
  [[ $test_mode == true || $EUID -eq 0 ]] || fail uninstall_requires_root
  [[ $caller =~ ^[a-z_][a-z0-9_-]*$ ]] || fail caller_invalid
  [[ $test_mode == true || ${SUDO_USER:-} == "$caller" ]] || fail caller_identity_mismatch
  require_regular "$state" patch_state_missing
  [[ $(stat -c %a "$state") == 600 ]] || fail patch_state_mode_drift
  [[ $(state_value "$state" D293_NATIVE_STATUS) == ACTIVE ]] || fail patch_state_inactive
  [[ $(state_value "$state" D293_NATIVE_INSTALLER) == "$caller" ]] || fail patch_installer_mismatch
  service_before=$(state_value "$state" D293_NATIVE_PREVIOUS_SERVICE_STATE) || fail patch_state_invalid
  [[ $service_before == active || $service_before == inactive ]] || fail previous_service_state_invalid
  [[ $(state_value "$state" D293_NATIVE_PREVIOUS_OWN_PATHS) == ABSENT ]] || fail previous_path_state_invalid
  head=$(state_value "$state" D293_NATIVE_PRODUCTION_HEAD) || fail patch_state_invalid
  is_git_sha "$head" || fail patch_head_invalid
  runtime=$(state_value "$state" D293_NATIVE_RUNTIME) || fail patch_state_invalid
  runtime="$fsroot$runtime"
  [[ $runtime == "$runtime_parent/d293-native-$head" ]] || fail patch_runtime_invalid
  expected_manifest=$(state_value "$state" D293_NATIVE_MANIFEST_SHA256) || fail patch_state_invalid
  expected_wrapper=$(state_value "$state" D293_NATIVE_WRAPPER_SHA256) || fail patch_state_invalid
  expected_dropin=$(state_value "$state" D293_NATIVE_DROPIN_SHA256) || fail patch_state_invalid
  expected_script=$(state_value "$state" D293_NATIVE_INSTALL_SCRIPT_SHA256) || fail patch_state_invalid
  expected_unit=$(state_value "$state" D293_NATIVE_PREVIOUS_UNIT_SNAPSHOT_SHA256) || fail patch_state_invalid
  expected_d285_wrapper=$(state_value "$state" D293_NATIVE_PREVIOUS_D285_WRAPPER_SHA256) || fail patch_state_invalid
  expected_d285_dropin=$(state_value "$state" D293_NATIVE_PREVIOUS_D285_DROPIN_SHA256) || fail patch_state_invalid
  expected_d285_manifest=$(state_value "$state" D293_NATIVE_PREVIOUS_D285_MANIFEST_SHA256) || fail patch_state_invalid
  verify_hash "$wrapper" "$expected_wrapper" patch_wrapper_drift
  verify_hash "$dropin" "$expected_dropin" patch_dropin_drift
  verify_hash "$here/install.sh" "$expected_script" rollback_script_drift
  verify_hash "$runtime/artifacts.sha256" "$expected_manifest" patch_manifest_drift
  (cd "$runtime" && sha256sum -c artifacts.sha256 >/dev/null) || fail patch_runtime_drift
  d285_runtime=$(validate_d285_previous)
  [[ $(digest "$d285_wrapper") == "$expected_d285_wrapper" &&
     $(digest "$d285_dropin") == "$expected_d285_dropin" &&
     $(digest "$d285_runtime/artifacts.sha256") == "$expected_d285_manifest" ]] ||
    fail previous_d285_changed
  "$systemctl_cmd" stop fprintd.service
  [[ $("$systemctl_cmd" is-active fprintd.service) == inactive ]] || fail service_stop_failed
  removing_dropin="$dropin.removing"
  [[ ! -e $removing_dropin && ! -L $removing_dropin ]] || fail rollback_staging_collision
  mv -- "$dropin" "$removing_dropin"
  "$systemctl_cmd" daemon-reload
  if [[ $(unit_snapshot_sha) != "$expected_unit" ]]; then
    mv -- "$removing_dropin" "$dropin"
    "$systemctl_cmd" daemon-reload
    if [[ $service_before == active ]]; then "$systemctl_cmd" start fprintd.service || true; fi
    fail previous_service_definition_not_restored
  fi
  if [[ $service_before == active ]]; then
    if ! "$systemctl_cmd" start fprintd.service; then
      mv -- "$removing_dropin" "$dropin"
      "$systemctl_cmd" daemon-reload
      "$systemctl_cmd" start fprintd.service || true
      fail previous_service_start_failed
    fi
  fi
  [[ $("$systemctl_cmd" is-active fprintd.service) == "$service_before" ]] || {
    mv -- "$removing_dropin" "$dropin"
    "$systemctl_cmd" daemon-reload
    if [[ $service_before == active ]]; then "$systemctl_cmd" start fprintd.service || true; fi
    fail service_final_state_wrong
  }
  rm -f -- "$removing_dropin"
  rm -f -- "$wrapper"
  remove_runtime "$runtime" || fail runtime_remove_failed
  rm -f -- "$state"
  [[ ! -e $dropin && ! -L $dropin && ! -e $wrapper && ! -L $wrapper &&
     ! -e $runtime && ! -L $runtime ]] || fail patch_remove_incomplete
  validate_d285_previous >/dev/null
  printf '%s\n' \
    'D293_NATIVE_ROLLBACK=PASS' \
    'D293_NATIVE_PREVIOUS_SOFTWARE=D285_RESTORED_EXACT' \
    "D293_NATIVE_SERVICE_STATE=$service_before"
}

operator_install() {
  local head user work output
  [[ $EUID -ne 0 ]] || fail operator_entrypoint_must_be_unprivileged
  [[ $(git -C "$root" branch --show-current) == development ]] || fail wrong_branch
  head=$(git -C "$root" rev-parse HEAD) || fail head_unreadable
  [[ $head == "$(git -C "$root" rev-parse origin/development)" ]] || fail head_origin_mismatch
  [[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
  [[ $(rpm -q fprintd) == fprintd-1.94.5-5.fc44.x86_64 ]] || fail fprintd_nevra_drift
  [[ $(rpm -q libfprint) == libfprint-1.94.100-1.fc44.x86_64 ]] || fail libfprint_nevra_drift
  user=$(id -un)
  [[ $user =~ ^[a-z_][a-z0-9_-]*$ ]] || fail operator_user_invalid
  work=$(mktemp -d /tmp/goodix-d293-native-build.XXXXXX)
  cleanup_work() {
    local rc=$?
    if [[ $work == /tmp/goodix-d293-native-build.* && -d $work && ! -L $work ]]; then
      find "$work" -xdev -depth -delete
    fi
    exit "$rc"
  }
  trap cleanup_work EXIT INT TERM
  output=$work/output
  "$root/production/build.sh" normal "$output"
  (cd "$output" && sha256sum "${runtime_names[@]}" >deploy.sha256)
  sudo -- "$here/install.sh" --root-install "$output" "$head" "$user"
  trap - EXIT INT TERM
  find "$work" -xdev -depth -delete
}

case ${1:-} in
  '') operator_install ;;
  --root-install)
    [[ $# -eq 4 ]] || fail root_install_arguments
    root_install "$2" "$3" "$4"
    ;;
  --root-uninstall)
    [[ $# -eq 2 ]] || fail root_uninstall_arguments
    root_uninstall "$2"
    ;;
  *) fail invalid_arguments ;;
esac
