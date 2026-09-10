#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

canonical_repo_root ()
{
  local dir=$1
  while [[ $dir != / ]]; do
    if [[ -e $dir/.git ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir=$(dirname -- "$dir")
  done
  return 1
}

root=$(canonical_repo_root "$script_dir") || {
  echo "ERRORE=Git root canonica non trovata sopra $script_dir" >&2
  exit 2
}
operation=D280_01_ENROLL_FP3_CLOSE_OPEN_IDENTIFY_EPHEMERAL
authorization=D280_01_ONE_ENROLL_ONE_IDENTIFY_NO_RETRY_EPHEMERAL_FP3
d280_offline_cleanup_root=
d280_prepare_cleanup_root=
d280_runtime_cleanup_root=
d280_template_cleanup_path=
d280_template_cleanup_dir=
runtime_counters_complete=false
action_attempt_count=UNKNOWN
enroll_action_attempt_count=UNKNOWN
identify_action_attempt_count=UNKNOWN
open_attempt_count=UNKNOWN
open_success_count=UNKNOWN
reopen_count=UNKNOWN
close_attempt_count=UNKNOWN
close_success_count=UNKNOWN

git_root () { git -C "$root" -c safe.directory="$root" "$@"; }
is_full_sha () { [[ ${1:-} =~ ^[0-9a-fA-F]{40}$ ]]; }

usage ()
{
  echo "Uso:" >&2
  echo "  $0 --offline-preflight" >&2
  echo "  $0 --summarize-runtime-log <OPERATOR.LOG>" >&2
  echo "  $0 --prepare-approved-live <SHA_COMPLETO_APPROVATO>" >&2
  echo "  $0 --write-grant <SHA_COMPLETO_APPROVATO> <FILE_GRANT>" >&2
  echo "  sudo $0 --run-approved-live <BUILD_PREPARATO> --grant <FILE_GRANT>" >&2
  echo "  sudo $0 --export-results <DIRECTORY_RISULTATI>" >&2
  exit 2
}

refuse ()
{
  echo "LIVE_GATE_REFUSED=true" >&2
  echo "LIVE_GATE_REFUSAL_REASON=$1" >&2
  echo "REAL_USB_ENUMERATION_ATTEMPTED=false" >&2
  echo "LIVE_EXECUTION_PERFORMED=false" >&2
  exit 3
}

state_value ()
{
  local file=$1 key=$2 value
  value=$(sed -n "s/^${key}=//p" "$file")
  [[ -n $value && $(grep -c "^${key}=" "$file") -eq 1 ]] || return 1
  printf '%s\n' "$value"
}

verify_tmpfs_directory ()
{
  local directory=$1 required_mode=${2:-} owner filesystem mode
  [[ -d $directory && ! -L $directory ]] || return 1
  owner=$(stat -c %u "$directory") || return 1
  filesystem=$(stat -f -c %T "$directory") || return 1
  [[ $owner -eq 0 && $filesystem == tmpfs ]] || return 1
  if [[ -n $required_mode ]]; then
    mode=$(stat -c %a "$directory") || return 1
    [[ $mode == "$required_mode" ]] || return 1
  fi
}

collect_runtime_counters ()
{
  local log=$1 key variable value
  local parsed_action=0 parsed_enroll=0 parsed_identify=0
  local parsed_open=0 parsed_open_success=0 parsed_reopen=0
  local parsed_close=0 parsed_close_success=0
  runtime_counters_complete=false
  action_attempt_count=UNKNOWN
  enroll_action_attempt_count=UNKNOWN
  identify_action_attempt_count=UNKNOWN
  open_attempt_count=UNKNOWN
  open_success_count=UNKNOWN
  reopen_count=UNKNOWN
  close_attempt_count=UNKNOWN
  close_success_count=UNKNOWN
  [[ -f $log && ! -L $log ]] || return 1
  [[ $(grep -c '^D280_01_RUNTIME_COUNTERS_BEGIN=true$' "$log") -eq 1 &&
     $(grep -c '^D280_01_RUNTIME_COUNTERS_END=true$' "$log") -eq 1 ]] ||
    return 1
  while read -r key variable; do
    value=$(state_value "$log" "D280_01_OBSERVED_${key}") || return 1
    [[ $value =~ ^(0|[1-9][0-9]{0,2})$ ]] || return 1
    printf -v "$variable" '%s' "$value"
  done <<'EOF'
ACTION_ATTEMPT_COUNT parsed_action
ENROLL_ACTION_ATTEMPT_COUNT parsed_enroll
IDENTIFY_ACTION_ATTEMPT_COUNT parsed_identify
OPEN_ATTEMPT_COUNT parsed_open
OPEN_SUCCESS_COUNT parsed_open_success
REOPEN_COUNT parsed_reopen
CLOSE_ATTEMPT_COUNT parsed_close
CLOSE_SUCCESS_COUNT parsed_close_success
EOF
  (( parsed_action <= 2 && parsed_enroll <= 1 && parsed_identify <= 1 &&
     parsed_action == parsed_enroll + parsed_identify &&
     parsed_open <= 2 && parsed_open_success <= parsed_open &&
     parsed_reopen <= 1 &&
     parsed_reopen == (parsed_open == 2 ? 1 : 0) &&
     parsed_identify <= parsed_reopen &&
     parsed_close <= 2 && parsed_close_success <= parsed_close )) ||
    return 1
  action_attempt_count=$parsed_action
  enroll_action_attempt_count=$parsed_enroll
  identify_action_attempt_count=$parsed_identify
  open_attempt_count=$parsed_open
  open_success_count=$parsed_open_success
  reopen_count=$parsed_reopen
  close_attempt_count=$parsed_close
  close_success_count=$parsed_close_success
  runtime_counters_complete=true
}

write_runtime_counter_summary ()
{
  echo "RUNTIME_COUNTERS_COMPLETE=$runtime_counters_complete"
  echo "ACTION_ATTEMPT_COUNT=$action_attempt_count"
  echo "ENROLL_ACTION_ATTEMPT_COUNT=$enroll_action_attempt_count"
  echo "IDENTIFY_ACTION_ATTEMPT_COUNT=$identify_action_attempt_count"
  echo "OPEN_ATTEMPT_COUNT=$open_attempt_count"
  echo "OPEN_SUCCESS_COUNT=$open_success_count"
  echo "REOPEN_COUNT=$reopen_count"
  echo "CLOSE_ATTEMPT_COUNT=$close_attempt_count"
  echo "CLOSE_SUCCESS_COUNT=$close_success_count"
}

summarize_runtime_log ()
{
  local log=$1
  if collect_runtime_counters "$log"; then
    write_runtime_counter_summary
    return 0
  fi
  write_runtime_counter_summary
  return 1
}

cleanup_offline_tree ()
{
  if [[ ${d280_offline_cleanup_root:-} == /tmp/goodix-d280-01-offline.* ]]; then
    find "$d280_offline_cleanup_root" -depth -delete 2>/dev/null || true
  fi
}

cleanup_prepare_tree ()
{
  if [[ ${d280_prepare_cleanup_root:-} == /tmp/goodix-d280-01-approved.* ]]; then
    find "$d280_prepare_cleanup_root" -depth -delete 2>/dev/null || true
  fi
}

cleanup_runtime_tree ()
{
  if [[ ${d280_template_cleanup_path:-} == \
        /run/goodix-d280-01/*/template.fp3 ]]; then
    find "$d280_template_cleanup_path" -maxdepth 0 \
      \( -type f -o -type l \) -delete \
      2>/dev/null || true
  fi
  if [[ ${d280_template_cleanup_dir:-} == /run/goodix-d280-01/* ]]; then
    rmdir "$d280_template_cleanup_dir" 2>/dev/null || true
  fi
  if [[ ${d280_runtime_cleanup_root:-} == /tmp/goodix-d280-01-runtime.* ]]; then
    find "$d280_runtime_cleanup_root" -depth -delete 2>/dev/null || true
  fi
}

live_critical_paths=(
  libfprint-driver
  reference/libfprint-fedora44-1.94.100/source
  Rockytkg
  tools/d280_ephemeral_template_reuse.c
  operator_kit/d280-01-ephemeral-template-reuse
  operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256
)

verify_approved_baseline ()
{
  local approved=$1 head origin_head dirty
  is_full_sha "$approved" || refuse INVALID_APPROVED_SHA
  [[ $(git_root branch --show-current) == development ]] ||
    refuse BRANCH_NOT_DEVELOPMENT
  git_root cat-file -e "$approved^{commit}" 2>/dev/null ||
    refuse APPROVED_COMMIT_NOT_LOCAL
  head=$(git_root rev-parse HEAD)
  [[ $head == "$approved" ]] || refuse HEAD_MISMATCH
  origin_head=$(git_root rev-parse origin/development 2>/dev/null) ||
    refuse ORIGIN_DEVELOPMENT_UNAVAILABLE
  [[ $origin_head == "$approved" ]] || refuse ORIGIN_DEVELOPMENT_MISMATCH
  dirty=$(git_root status --porcelain --untracked-files=all -- \
    "${live_critical_paths[@]}")
  [[ -z $dirty ]] || refuse LIVE_CRITICAL_SOURCE_DIRTY
}

find_host_gusb ()
{
  local candidate
  for candidate in \
    /usr/lib64/libgusb.so.2.0.10 \
    /usr/lib64/libgusb.so.2 \
    /usr/lib/x86_64-linux-gnu/libgusb.so.2; do
    if [[ -f $candidate ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

verify_host_sigfm_runtime ()
{
  [[ $(rpm -q tbb) == tbb-2022.3.0-3.fc44.x86_64 ]] ||
    refuse HOST_TBB_PACKAGE_DRIFT
  [[ $(rpm -q flexiblas) == flexiblas-3.5.0-2.fc44.x86_64 ]] ||
    refuse HOST_FLEXIBLAS_PACKAGE_DRIFT
  [[ $(rpm -q flexiblas-netlib) == flexiblas-netlib-3.5.0-2.fc44.x86_64 ]] ||
    refuse HOST_FLEXIBLAS_BACKEND_DRIFT
  [[ $(rpm -q libstdc++.x86_64) == libstdc++-16.2.1-2.fc44.x86_64 ]] ||
    refuse HOST_LIBSTDCXX_PACKAGE_DRIFT
}

download_and_extract_opencv ()
{
  local source_root=$1 output_root=$2 rpms prefix package
  rpms="$output_root/opencv-rpms"
  prefix="$output_root/opencv-prefix"
  mkdir -p "$rpms" "$prefix" "$output_root/dnf-log"
  command -v dnf >/dev/null 2>&1 || refuse DNF_NOT_FOUND
  command -v rpm2cpio >/dev/null 2>&1 || refuse RPM2CPIO_NOT_FOUND
  command -v cpio >/dev/null 2>&1 || refuse CPIO_NOT_FOUND
  dnf --setopt="logdir=$output_root/dnf-log" download --destdir="$rpms" \
    opencv-core-4.13.0-1.fc44.x86_64 \
    opencv-devel-4.13.0-1.fc44.x86_64 \
    opencv-features2d-4.13.0-1.fc44.x86_64 \
    opencv-flann-4.13.0-1.fc44.x86_64 \
    opencv-imgproc-4.13.0-1.fc44.x86_64
  (cd "$rpms" && sha256sum -c \
    "$source_root/operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256")
  for package in "$rpms"/*.rpm; do
    (cd "$prefix" && rpm2cpio "$package" | cpio -idm --quiet)
  done
}

build_snapshot ()
{
  local source_root=$1 output_root=$2 baseline=$3
  local build_dir="$output_root/build"
  local pkgconfig_dir="$output_root/pkgconfig"
  local inner="$source_root/operator_kit/d280-01-ephemeral-template-reuse/build-inner.sh"
  local pc_template="$source_root/libfprint-driver/tests/support/d279/gusb.pc.in"
  local opencv_pc_template="$source_root/libfprint-driver/tests/support/d279/opencv4.pc.in"
  local include_dir="$source_root/libfprint-driver/tests/support/d279"
  local host_gusb component

  host_gusb=$(find_host_gusb) || {
    echo "BLOCKED_ENVIRONMENT=libgusb runtime host non trovata" >&2
    return 2
  }
  verify_host_sigfm_runtime
  download_and_extract_opencv "$source_root" "$output_root"
  mkdir -p "$build_dir" "$pkgconfig_dir"
  cp "$host_gusb" "$pkgconfig_dir/libgusb.so.2"
  sed -e "s|@PREFIX@|$pkgconfig_dir|g" \
      -e "s|@INCLUDEDIR@|$include_dir|g" \
      "$pc_template" >"$pkgconfig_dir/gusb.pc"
  sed -e "s|@PREFIX@|$output_root/opencv-prefix/usr|g" \
      "$opencv_pc_template" >"$pkgconfig_dir/opencv4.pc"

  if ! command -v flatpak >/dev/null 2>&1 ||
     ! flatpak info --user org.freedesktop.Sdk//25.08 >/dev/null 2>&1; then
    echo "BLOCKED_ENVIRONMENT=Freedesktop SDK 25.08 non disponibile" >&2
    return 2
  fi
  echo EXECUTION_ENVIRONMENT=FREEDESKTOP_SDK_25_08
  flatpak run --user --unshare=network \
    --filesystem="$source_root":ro \
    --filesystem="$output_root" \
    --command=sh org.freedesktop.Sdk//25.08 \
    "$inner" "$source_root" "$build_dir" "$pkgconfig_dir" \
    "$output_root" "$baseline"
  for component in core features2d flann imgproc; do
    cp -L "$output_root/opencv-prefix/usr/lib64/libopencv_${component}.so.4.13.0" \
      "$output_root/libopencv_${component}.so.413"
    chmod 0600 "$output_root/libopencv_${component}.so.413"
  done
}

source_guard_audit ()
{
  local tool=$1
  [[ $(grep -c 'fp_device_enroll_sync (' "$tool") -eq 1 ]] ||
    refuse ENROLL_ACTION_CALL_COUNT_NOT_ONE
  [[ $(grep -c 'fp_device_identify_sync (' "$tool") -eq 1 ]] ||
    refuse IDENTIFY_ACTION_CALL_COUNT_NOT_ONE
  [[ $(grep -c 'fp_print_serialize (' "$tool") -eq 1 ]] ||
    refuse SERIALIZE_CALL_COUNT_NOT_ONE
  [[ $(grep -c 'fp_print_deserialize (' "$tool") -eq 1 ]] ||
    refuse DESERIALIZE_CALL_COUNT_NOT_ONE
  if grep -E 'fp_device_(verify|capture|delete_print|clear_storage|list_prints)_sync' \
       "$tool" >/dev/null; then
    refuse FORBIDDEN_ACTION_PRESENT
  fi
  grep -F 'O_EXCL | O_NOFOLLOW | O_CLOEXEC' "$tool" >/dev/null ||
    refuse TEMPLATE_EXCLUSIVE_CREATE_GUARD_MISSING
  grep -F 'fstatfs (fd, &filesystem)' "$tool" >/dev/null ||
    refuse TEMPLATE_TMPFS_GUARD_MISSING
  grep -F 'FP3_REMOVED_BEFORE_IDENTIFY=true' "$tool" >/dev/null ||
    refuse TEMPLATE_PRE_IDENTIFY_REMOVAL_GUARD_MISSING
  grep -F 'OPERATOR_RETRY_COUNT=0' "$tool" >/dev/null ||
    refuse ZERO_RETRY_MARKER_MISSING
  grep -F 'ACTION_ATTEMPT_MAX=2' "$tool" >/dev/null ||
    refuse TWO_ACTION_BOUND_MISSING
  grep -F 'SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false' "$tool" >/dev/null ||
    refuse PERSISTENCE_CLAIM_GUARD_MISSING
  grep -F 'D280_01_EPHEMERAL_TEMPLATE_REUSE_PASS=' "$tool" >/dev/null ||
    refuse TERMINAL_AUDIT_GUARD_MISSING
  grep -F 'GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION' \
    "$root/libfprint-driver/goodix_fpimage_device.c" >/dev/null ||
    refuse SINGLE_ACQUISITION_AUDIT_MISSING
  grep -F '#define GOODIX_FDT_TOUCH_MASK 0x003fu' \
    "$root/libfprint-driver/goodix_fdt_irq_policy.h" >/dev/null ||
    refuse FDT_TOUCH_MASK_POLICY_MISSING
}

offline_preflight ()
{
  local work binary
  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_REQUIRES_NORMAL_USER
  verify_tmpfs_directory /run || refuse RUN_IS_NOT_ROOT_OWNED_TMPFS
  source_guard_audit "$root/tools/d280_ephemeral_template_reuse.c"
  "$root/libfprint-driver/tests/run_goodix_d278_secure_session_test.sh"
  work=$(mktemp -d /tmp/goodix-d280-01-offline.XXXXXX)
  d280_offline_cleanup_root=$work
  trap cleanup_offline_tree EXIT HUP INT TERM
  build_snapshot "$root" "$work" UNAPPROVED_FOR_LIVE
  "$root/libfprint-driver/tests/run_goodix_fedora44_nbis_action_test.sh" \
    "$work/opencv-rpms"
  binary="$work/d280_ephemeral_template_reuse.pending"
  [[ -f $binary && ! -L $binary ]] || refuse OFFLINE_BINARY_MISSING
  mv "$binary" "$work/d280_ephemeral_template_reuse"
  chmod 0700 "$work/d280_ephemeral_template_reuse"
  "$work/d280_ephemeral_template_reuse" --gate-self-test
  LD_LIBRARY_PATH="$work" ldd "$work/d280_ephemeral_template_reuse" |
    grep -F "$work/libopencv_features2d.so.413" >/dev/null ||
    refuse OPENCV_RUNTIME_NOT_PINNED
  echo D280_01_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
  echo D280_01_COMPILED_BASELINE=UNAPPROVED_FOR_LIVE
  echo ACTION_ATTEMPT_MAX=2
  echo ENROLL_ACTION_ATTEMPT_MAX=1
  echo IDENTIFY_ACTION_ATTEMPT_MAX=1
  echo OPEN_ATTEMPT_MAX=2
  echo REOPEN_ATTEMPT_MAX=1
  echo OPERATOR_RETRY_COUNT=0
  echo TEMPLATE_STORAGE=ROOT_0700_DIRECTORY_AND_0600_FILE_ON_VERIFIED_TMPFS
  echo TEMPLATE_STORAGE_FILESYSTEM=tmpfs
  echo TEMPLATE_REMOVAL_BOUNDARY=BEFORE_IDENTIFY
  echo TEMPLATE_INCLUDED_IN_EXPORT=false
  echo KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0
  echo SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo LIVE_EXECUTION_PERFORMED=false
  cleanup_offline_tree
  d280_offline_cleanup_root=
  trap - EXIT HUP INT TERM
}

prepare_approved_live ()
{
  local approved=$1 prepared snapshot binary state grant_id manifest_sha
  local binary_sha library_sha gusb_sha
  [[ $EUID -ne 0 ]] || refuse PREPARE_REQUIRES_NORMAL_USER
  verify_approved_baseline "$approved"
  source_guard_audit "$root/tools/d280_ephemeral_template_reuse.c"
  prepared=$(mktemp -d /tmp/goodix-d280-01-approved.XXXXXX)
  d280_prepare_cleanup_root=$prepared
  trap cleanup_prepare_tree EXIT HUP INT TERM
  chmod 0700 "$prepared"
  snapshot="$prepared/snapshot"
  mkdir -m 0700 "$snapshot"
  git_root archive "$approved" -- "${live_critical_paths[@]}" |
    tar -x -C "$snapshot"
  build_snapshot "$snapshot" "$prepared" "$approved"
  verify_approved_baseline "$approved"

  binary="$prepared/d280_ephemeral_template_reuse.pending"
  [[ -f $binary && ! -L $binary &&
     -f $prepared/libfprint-2.so.2.0.0 &&
     -f $prepared/libgusb.so.2 ]] || refuse PREPARED_ARTIFACT_MISSING
  mv "$binary" "$prepared/d280_ephemeral_template_reuse"
  binary="$prepared/d280_ephemeral_template_reuse"
  chmod 0700 "$binary"
  binary_sha=$(sha256sum "$binary" | awk '{print $1}')
  library_sha=$(sha256sum "$prepared/libfprint-2.so.2.0.0" | awk '{print $1}')
  gusb_sha=$(sha256sum "$prepared/libgusb.so.2" | awk '{print $1}')
  (cd "$prepared" && sha256sum d280_ephemeral_template_reuse \
    libfprint-2.so.2.0.0 libgusb.so.2 libopencv_core.so.413 \
    libopencv_features2d.so.413 libopencv_flann.so.413 \
    libopencv_imgproc.so.413 >d280-01-artifacts.sha256)
  manifest_sha=$(sha256sum "$prepared/d280-01-artifacts.sha256" | awk '{print $1}')
  grant_id="d28001-$approved"
  state="$prepared/d280-01-prepared.state"
  umask 077
  {
    echo "D280_01_BASELINE_SHA=$approved"
    echo "D280_01_OPERATION=$operation"
    echo "D280_01_PREPARED_DIR=$prepared"
    echo "D280_01_BINARY_SHA256=$binary_sha"
    echo "D280_01_LIBRARY_SHA256=$library_sha"
    echo "D280_01_GUSB_SHA256=$gusb_sha"
    echo "D280_01_ARTIFACT_MANIFEST_SHA256=$manifest_sha"
    echo "D280_01_GRANT_ID=$grant_id"
  } >"$state"
  chmod 0600 "$state"
  echo APPROVED_BUILD_PREPARED=true
  echo "APPROVED_BASELINE_SHA=$approved"
  echo "PREPARED_BUILD_DIR=$prepared"
  echo "EXPECTED_GRANT_ID=$grant_id"
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo LIVE_EXECUTION_PERFORMED=false
  d280_prepare_cleanup_root=
  trap - EXIT HUP INT TERM
}

write_grant ()
{
  local approved=$1 grant=$2 grant_id parent
  [[ $EUID -ne 0 ]] || refuse GRANT_CREATION_REQUIRES_NORMAL_USER
  verify_approved_baseline "$approved"
  [[ ! -e $grant && ! -L $grant ]] || refuse GRANT_PATH_ALREADY_EXISTS
  parent=$(dirname -- "$grant")
  [[ -d $parent && ! -L $parent ]] || refuse GRANT_PARENT_INVALID
  grant_id="d28001-$approved"
  umask 077
  ( set -C
    {
      echo "D280_01_BASELINE_SHA=$approved"
      echo "D280_01_OPERATION=$operation"
      echo "D280_01_GRANT_ID=$grant_id"
    } >"$grant"
  ) || refuse GRANT_CREATE_FAILED
  chmod 0600 "$grant"
  echo GRANT_WRITTEN=true
  echo "GRANT_FILE=$grant"
  echo "GRANT_ID=$grant_id"
  echo "NOTA=Grant one-shot per due action bounded; non ricrearlo o riusarlo."
}

run_approved_live ()
{
  local prepared=$1 grant=$2 state baseline state_operation state_dir
  local expected_binary_sha expected_library_sha expected_gusb_sha
  local expected_manifest_sha expected_grant_id actual_sha grant_id
  local grant_baseline grant_operation mode owner accepted claim_root claim
  local runtime results_parent result_root stamp log rc template_path
  local template_parent template_dir
  local template_present_after_run template_directory_present_after_run

  [[ $EUID -eq 0 ]] || refuse LIVE_REQUIRES_ROOT
  umask 077
  command -v pgrep >/dev/null 2>&1 || refuse FPRINTD_PROCESS_GUARD_UNAVAILABLE
  pgrep -x fprintd >/dev/null 2>&1 && refuse FPRINTD_PROCESS_ACTIVE
  [[ $prepared == /tmp/goodix-d280-01-approved.* && -d $prepared &&
     ! -L $prepared ]] || refuse PREPARED_DIR_INVALID
  state="$prepared/d280-01-prepared.state"
  [[ -f $state && ! -L $state ]] || refuse PREPARED_STATE_INVALID
  baseline=$(state_value "$state" D280_01_BASELINE_SHA) || refuse STATE_MALFORMED
  state_operation=$(state_value "$state" D280_01_OPERATION) || refuse STATE_MALFORMED
  state_dir=$(state_value "$state" D280_01_PREPARED_DIR) || refuse STATE_MALFORMED
  expected_binary_sha=$(state_value "$state" D280_01_BINARY_SHA256) || refuse STATE_MALFORMED
  expected_library_sha=$(state_value "$state" D280_01_LIBRARY_SHA256) || refuse STATE_MALFORMED
  expected_gusb_sha=$(state_value "$state" D280_01_GUSB_SHA256) || refuse STATE_MALFORMED
  expected_manifest_sha=$(state_value "$state" D280_01_ARTIFACT_MANIFEST_SHA256) || refuse STATE_MALFORMED
  expected_grant_id=$(state_value "$state" D280_01_GRANT_ID) || refuse STATE_MALFORMED
  [[ $state_operation == "$operation" && $state_dir == "$prepared" ]] ||
    refuse STATE_BINDING_MISMATCH
  verify_approved_baseline "$baseline"

  for name in d280_ephemeral_template_reuse libfprint-2.so.2.0.0 \
    libgusb.so.2 d280-01-artifacts.sha256; do
    [[ -f $prepared/$name && ! -L $prepared/$name ]] ||
      refuse PREPARED_ARTIFACT_INVALID
  done
  actual_sha=$(sha256sum "$prepared/d280_ephemeral_template_reuse" | awk '{print $1}')
  [[ $actual_sha == "$expected_binary_sha" ]] || refuse BINARY_HASH_MISMATCH
  actual_sha=$(sha256sum "$prepared/libfprint-2.so.2.0.0" | awk '{print $1}')
  [[ $actual_sha == "$expected_library_sha" ]] || refuse LIBRARY_HASH_MISMATCH
  actual_sha=$(sha256sum "$prepared/libgusb.so.2" | awk '{print $1}')
  [[ $actual_sha == "$expected_gusb_sha" ]] || refuse GUSB_HASH_MISMATCH
  actual_sha=$(sha256sum "$prepared/d280-01-artifacts.sha256" | awk '{print $1}')
  [[ $actual_sha == "$expected_manifest_sha" ]] || refuse MANIFEST_HASH_MISMATCH
  (cd "$prepared" && sha256sum -c d280-01-artifacts.sha256) ||
    refuse ARTIFACT_BUNDLE_HASH_MISMATCH

  [[ $grant == /* && -f $grant && ! -L $grant &&
     $(wc -l <"$grant") -eq 3 ]] || refuse GRANT_FILE_POLICY
  mode=$(stat -c %a "$grant")
  owner=$(stat -c %u "$grant")
  [[ $((8#$mode & 0177)) -eq 0 ]] || refuse GRANT_FILE_POLICY
  accepted=0
  [[ $owner -eq $EUID ]] && accepted=1
  if [[ ${SUDO_UID:-} =~ ^[0-9]+$ && $owner -eq $SUDO_UID ]]; then
    accepted=1
  fi
  [[ $accepted -eq 1 ]] || refuse GRANT_FILE_POLICY
  grant_baseline=$(state_value "$grant" D280_01_BASELINE_SHA) || refuse GRANT_MALFORMED
  grant_operation=$(state_value "$grant" D280_01_OPERATION) || refuse GRANT_MALFORMED
  grant_id=$(state_value "$grant" D280_01_GRANT_ID) || refuse GRANT_MALFORMED
  [[ $grant_baseline == "$baseline" && $grant_operation == "$operation" &&
     $grant_id == "$expected_grant_id" ]] || refuse GRANT_BINDING_MISMATCH

  template_parent=/run/goodix-d280-01
  [[ -e $template_parent ]] || mkdir -m 0700 "$template_parent"
  verify_tmpfs_directory "$template_parent" 700 ||
    refuse TEMPLATE_RAM_ROOT_POLICY
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  template_dir="$template_parent/${stamp}-${baseline:0:12}"
  mkdir -m 0700 "$template_dir" || refuse TEMPLATE_RAM_RUN_DIR_CREATE_FAILED
  d280_template_cleanup_dir=$template_dir
  template_path="$template_dir/template.fp3"
  d280_template_cleanup_path=$template_path
  trap cleanup_runtime_tree EXIT HUP INT TERM
  verify_tmpfs_directory "$template_dir" 700 || refuse TEMPLATE_RAM_RUN_DIR_POLICY

  claim_root=/var/tmp/goodix-d280-01-consumed-grants
  [[ -e $claim_root ]] || mkdir -m 0700 "$claim_root"
  [[ -d $claim_root && ! -L $claim_root &&
     $(stat -c %u "$claim_root") -eq 0 &&
     $(stat -c %a "$claim_root") == 700 ]] || refuse CLAIM_ROOT_POLICY
  claim="$claim_root/$grant_id"
  mkdir -m 0700 "$claim" 2>/dev/null || refuse GRANT_ALREADY_CONSUMED
  {
    echo "D280_01_BASELINE_SHA=$baseline"
    echo "D280_01_OPERATION=$operation"
    echo "D280_01_GRANT_ID=$grant_id"
  } >"$claim/consumed.state"
  chmod 0600 "$claim/consumed.state"

  runtime=$(mktemp -d /tmp/goodix-d280-01-runtime.XXXXXX)
  d280_runtime_cleanup_root=$runtime
  chmod 0700 "$runtime"
  cp "$prepared/d280_ephemeral_template_reuse" "$runtime/"
  cp "$prepared/libfprint-2.so.2.0.0" "$runtime/"
  cp "$prepared/libgusb.so.2" "$runtime/"
  cp "$prepared"/libopencv_*.so.413 "$runtime/"
  cp "$prepared/d280-01-artifacts.sha256" "$runtime/"
  ln -s libfprint-2.so.2.0.0 "$runtime/libfprint-2.so.2"
  chmod 0700 "$runtime/d280_ephemeral_template_reuse"
  chmod 0600 "$runtime"/*.so.* "$runtime/d280-01-artifacts.sha256"
  (cd "$runtime" && sha256sum -c d280-01-artifacts.sha256) ||
    refuse RUNTIME_ARTIFACT_BUNDLE_HASH_MISMATCH
  verify_host_sigfm_runtime

  results_parent=/var/tmp/goodix-d280-01-results
  [[ -e $results_parent ]] || mkdir -m 0700 "$results_parent"
  [[ -d $results_parent && ! -L $results_parent &&
     $(stat -c %u "$results_parent") -eq 0 &&
     $(stat -c %a "$results_parent") == 700 ]] || refuse RESULT_ROOT_POLICY
  result_root="$results_parent/${stamp}-${baseline:0:12}"
  mkdir -m 0700 "$result_root"
  log="$result_root/operator.log"
  echo "INIZIO RUN ONE-SHOT A DUE ACTION. Non rilanciare in caso di errore."
  echo "DATI_BIOMETRICI=Un FP3 root 0600 su tmpfs esistera solo tra close e reopen; verra azzerato in memoria e rimosso prima della identify."
  set +e
  env LD_LIBRARY_PATH="$runtime" \
    D280_01_APPROVED_LIVE_SHA="$baseline" \
    D280_01_OPERATION="$operation" \
    D280_01_OPERATOR_AUTHORIZATION="$authorization" \
    D280_01_GRANT_ID="$grant_id" \
    D280_01_TEMPLATE_PATH="$template_path" \
    timeout --signal=INT --kill-after=30s 1060s \
      "$runtime/d280_ephemeral_template_reuse" --run-once 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  set -e
  if [[ -e $template_path || -L $template_path ]]; then
    find "$template_path" -maxdepth 0 \( -type f -o -type l \) -delete || rc=1
  fi
  template_present_after_run=false
  if [[ -e $template_path || -L $template_path ]]; then
    template_present_after_run=true
    rc=1
  fi
  if [[ $template_present_after_run == false ]]; then
    d280_template_cleanup_path=
  fi
  if rmdir "$template_dir"; then
    d280_template_cleanup_dir=
    template_directory_present_after_run=false
  else
    rc=1
    template_directory_present_after_run=true
  fi
  chmod 0600 "$log"
  if ! collect_runtime_counters "$log"; then
    rc=1
  fi
  {
    echo "D280_01_BASELINE_SHA=$baseline"
    echo "D280_01_OPERATION=$operation"
    echo "D280_01_GRANT_ID=$grant_id"
    echo "RUN_RETURN_CODE=$rc"
    echo "ACTION_ATTEMPT_MAX=2"
    echo "ENROLL_ACTION_ATTEMPT_MAX=1"
    echo "IDENTIFY_ACTION_ATTEMPT_MAX=1"
    echo "OPEN_ATTEMPT_MAX=2"
    echo "REOPEN_ATTEMPT_MAX=1"
    echo "OPERATOR_RETRY_COUNT=0"
    write_runtime_counter_summary
    echo "TEMPLATE_FILE_PRESENT_AFTER_RUN=$template_present_after_run"
    echo "TEMPLATE_RAM_DIRECTORY_PRESENT_AFTER_RUN=$template_directory_present_after_run"
    echo "TEMPLATE_STORAGE_FILESYSTEM=tmpfs"
    echo "TEMPLATE_INCLUDED_IN_EXPORT=false"
    echo "KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0"
    echo "SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false"
  } >"$result_root/summary.env"
  chmod 0600 "$result_root/summary.env"
  echo "RISULTATI=$result_root"
  echo "RUN_RETURN_CODE=$rc"
  echo "GRANT_CONSUMED=true"
  echo "RETRY_AUTHORIZED=false"
  cleanup_runtime_tree
  d280_runtime_cleanup_root=
  trap - EXIT HUP INT TERM
  return "$rc"
}

export_results ()
{
  local result_root=$1 basename export_dir source_sha copied_sha name ram_run
  [[ $EUID -eq 0 ]] || refuse EXPORT_REQUIRES_ROOT
  [[ ${SUDO_UID:-} =~ ^[0-9]+$ && ${SUDO_GID:-} =~ ^[0-9]+$ ]] ||
    refuse EXPORT_REQUIRES_SUDO_CALLER
  [[ $result_root == /var/tmp/goodix-d280-01-results/* &&
     -d $result_root && ! -L $result_root ]] || refuse EXPORT_SOURCE_INVALID
  basename=${result_root##*/}
  [[ $basename =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] ||
    refuse EXPORT_SOURCE_INVALID
  ram_run="/run/goodix-d280-01/$basename"
  [[ ! -e $ram_run && ! -L $ram_run ]] ||
    refuse BIOMETRIC_RAM_STATE_STILL_PRESENT
  [[ ! -e $result_root/template.fp3 && ! -L $result_root/template.fp3 ]] ||
    refuse BIOMETRIC_TEMPLATE_STILL_PRESENT
  export_dir=$(mktemp -d /tmp/goodix-d280-01-export.XXXXXX)
  chmod 0700 "$export_dir"
  for name in operator.log summary.env; do
    [[ -f $result_root/$name && ! -L $result_root/$name &&
       $(stat -c %u "$result_root/$name") -eq 0 &&
       $(stat -c %a "$result_root/$name") == 600 ]] ||
      refuse EXPORT_SOURCE_FILE_INVALID
    source_sha=$(sha256sum "$result_root/$name" | awk '{print $1}')
    install -m 0600 -o "$SUDO_UID" -g "$SUDO_GID" \
      "$result_root/$name" "$export_dir/$name"
    copied_sha=$(sha256sum "$export_dir/$name" | awk '{print $1}')
    [[ $source_sha == "$copied_sha" ]] || refuse EXPORT_HASH_MISMATCH
    echo "${name}_SHA256=$source_sha"
  done
  chown "$SUDO_UID:$SUDO_GID" "$export_dir"
  echo D280_01_RESULTS_EXPORT=PASS_BYTE_IDENTICAL
  echo "EXPORT_DIRECTORY=$export_dir"
  echo TEMPLATE_INCLUDED_IN_EXPORT=false
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo LIVE_EXECUTION_PERFORMED=false
}

case ${1:-} in
  --offline-preflight)
    [[ $# -eq 1 ]] || usage
    offline_preflight
    ;;
  --summarize-runtime-log)
    [[ $# -eq 2 ]] || usage
    summarize_runtime_log "$2"
    ;;
  --prepare-approved-live)
    [[ $# -eq 2 ]] || usage
    prepare_approved_live "$2"
    ;;
  --write-grant)
    [[ $# -eq 3 ]] || usage
    write_grant "$2" "$3"
    ;;
  --run-approved-live)
    [[ $# -eq 4 && $3 == --grant ]] || usage
    run_approved_live "$2" "$4"
    ;;
  --export-results)
    [[ $# -eq 2 ]] || usage
    export_results "$2"
    ;;
  *) usage ;;
esac
