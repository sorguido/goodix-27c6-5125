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
operation=D279_57_STAGE8_EARLY_TERMINAL_ENROLLMENT
authorization=D279_57_ONE_STAGE8_ENROLLMENT_NO_RETRY
d279_57_offline_cleanup_root=
d279_57_prepare_cleanup_root=
d279_57_runtime_cleanup_root=

git_root () { git -C "$root" -c safe.directory="$root" "$@"; }
is_full_sha () { [[ ${1:-} =~ ^[0-9a-fA-F]{40}$ ]]; }

usage ()
{
  echo "Uso:" >&2
  echo "  $0 --offline-preflight" >&2
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

cleanup_offline_tree ()
{
  if [[ ${d279_57_offline_cleanup_root:-} == /tmp/goodix-d279-57-offline.* ]]; then
    find "$d279_57_offline_cleanup_root" -depth -delete 2>/dev/null || true
  fi
}

cleanup_runtime_tree ()
{
  if [[ ${d279_57_runtime_cleanup_root:-} == /tmp/goodix-d279-57-runtime.* ]]; then
    find "$d279_57_runtime_cleanup_root" -depth -delete 2>/dev/null || true
  fi
}

cleanup_prepare_tree ()
{
  if [[ ${d279_57_prepare_cleanup_root:-} == /tmp/goodix-d279-57-approved.* ]]; then
    find "$d279_57_prepare_cleanup_root" -depth -delete 2>/dev/null || true
  fi
}

live_critical_paths=(
  libfprint-driver
  reference/libfprint-fedora44-1.94.100/source
  Rockytkg
  tools/d279_stage8_enroll.c
  operator_kit/d279-57-stage8-early-terminal
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
  local inner="$source_root/operator_kit/d279-57-stage8-early-terminal/build-inner.sh"
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
    refuse ACTION_CALL_COUNT_NOT_ONE
  if grep -E 'fp_device_(verify|identify|capture|delete_print|clear_storage|list_prints)_sync' \
       "$tool" >/dev/null; then
    refuse NON_ENROLL_ACTION_PRESENT
  fi
  grep -F 'OPERATOR_RETRY_COUNT=0' "$tool" >/dev/null ||
    refuse ZERO_RETRY_MARKER_MISSING
  grep -F 'SECOND_ACTION_COUNT=0' "$tool" >/dev/null ||
    refuse SECOND_ACTION_GUARD_MISSING
  grep -F 'BIOMETRIC_TEMPLATE_SAVED=false' "$tool" >/dev/null ||
    refuse TEMPLATE_NONSAVE_MARKER_MISSING
  grep -F 'PRODUCTION_AUDIT_AVAILABLE=true' "$tool" >/dev/null ||
    refuse PRODUCTION_AUDIT_MARKER_MISSING
  grep -F '#define D279_57_ENROLL_STAGES 8' "$tool" >/dev/null ||
    refuse STAGE8_GUARD_MISSING
  grep -F 'D279_57_STAGE8_TERMINAL_AUDIT_PASS=' "$tool" >/dev/null ||
    refuse TERMINAL_AUDIT_GUARD_MISSING
  grep -F 'PHYSICAL_INSTRUCTION_SOURCE=LIBFPRINT_FINGER_STATUS' \
    "$tool" >/dev/null || refuse PHYSICAL_INSTRUCTION_SOURCE_MISSING
  grep -F 'AUDIT_ENROLL_LAST_MISMATCH_EXPECTED_EVENT=' "$tool" >/dev/null ||
    refuse SANITIZED_MISMATCH_TELEMETRY_MISSING
  grep -F 'AUDIT_ENROLL_TERMINAL_COMPLETION_HOLD_COUNT=' "$tool" >/dev/null ||
    refuse TERMINAL_COMPLETION_HOLD_TELEMETRY_MISSING
  grep -F 'release_ready_prompt_count != D279_57_ENROLL_STAGES' "$tool" >/dev/null ||
    refuse ALL_STAGE_RELEASE_READY_GUARD_MISSING
  grep -F '#define GOODIX_FDT_TOUCH_MASK 0x003fu' \
    "$root/libfprint-driver/goodix_fdt_irq_policy.h" >/dev/null ||
    refuse FDT_TOUCH_MASK_POLICY_MISSING
  grep -F 'GOODIX_FDT_FLAGS_FINGER_DOWN, &touch_flags, &raw' \
    "$root/libfprint-driver/goodix_enrollment_post_tls_events.c" >/dev/null ||
    refuse ENROLLMENT_IRQ_POLICY_BINDING_MISSING
  grep -F 'goodix_fdt_derive_up_table (raw, touch_flags, 0x1du' \
    "$root/libfprint-driver/goodix_enrollment_fdt_state.c" >/dev/null ||
    refuse PARTIAL_TOUCH_FDT_DERIVATION_MISSING
  if grep -E 'parse_irq \(&message, 0x(32|34|36), 0x(0002|0100|0200), 0x' \
       "$root/libfprint-driver/goodix_enrollment_post_tls_events.c" >/dev/null; then
    refuse STALE_MAGIC_IRQ_FLAGS_PRESENT
  fi
}

offline_preflight ()
{
  local work binary

  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_REQUIRES_NORMAL_USER
  source_guard_audit "$root/tools/d279_stage8_enroll.c"
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
    analysis/D279/test_d279_59_full_irq_flags_audit.py
  "$root/libfprint-driver/tests/run_goodix_d279_59_irq_policy_test.sh"
  work=$(mktemp -d /tmp/goodix-d279-57-offline.XXXXXX)
  d279_57_offline_cleanup_root=$work
  trap cleanup_offline_tree EXIT HUP INT TERM
  build_snapshot "$root" "$work" UNAPPROVED_FOR_LIVE
  binary="$work/d279_stage8_enroll.pending"
  [[ -f $binary && ! -L $binary ]] || refuse OFFLINE_BINARY_MISSING
  mv "$binary" "$work/d279_stage8_enroll"
  chmod 0700 "$work/d279_stage8_enroll"
  "$work/d279_stage8_enroll" --gate-self-test
  LD_LIBRARY_PATH="$work" ldd "$work/d279_stage8_enroll" |
    grep -F "$work/libopencv_features2d.so.413" >/dev/null ||
    refuse OPENCV_RUNTIME_NOT_PINNED
  echo D279_57_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
  echo D279_57_COMPILED_BASELINE=UNAPPROVED_FOR_LIVE
  echo ACTION_ATTEMPT_MAX=1
  echo OPERATOR_RETRY_COUNT=0
  echo SECOND_ACTION_COUNT=0
  echo REOPEN_COUNT=0
  echo BIOMETRIC_TEMPLATE_SAVED=false
  echo HOST_DEADLINE_IS_DEVICE_QUIESCENCE_PROOF=false
  echo KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0
  echo SANITIZED_PRODUCTION_AUDIT_ACCESSOR_EXPORTED=true
  echo PHYSICAL_INSTRUCTION_SOURCE=LIBFPRINT_FINGER_STATUS
  echo INTERMEDIATE_STAGE_DELIVERY_BOUNDARY=FINAL_ACK34_RELEASE_READY
  echo INTERMEDIATE_SAMPLE_DELIVERY_BOUNDARY=FINAL_ACK34_BEFORE_IRQ0200
  echo TERMINAL_SAMPLE_DELIVERY_BOUNDARY=FINAL_ACK34_BEFORE_IRQ0200
  echo TERMINAL_COMPLETION_BOUNDARY=IRQ0200_AND_SIGFM_COMPLETE
  echo SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo LIVE_EXECUTION_PERFORMED=false
  cleanup_offline_tree
  d279_57_offline_cleanup_root=
  trap - EXIT HUP INT TERM
}

prepare_approved_live ()
{
  local approved=$1 prepared snapshot binary library gusb state grant_id
  local binary_sha library_sha gusb_sha manifest_sha

  [[ $EUID -ne 0 ]] || refuse PREPARE_REQUIRES_NORMAL_USER
  verify_approved_baseline "$approved"
  source_guard_audit "$root/tools/d279_stage8_enroll.c"
  prepared=$(mktemp -d /tmp/goodix-d279-57-approved.XXXXXX)
  d279_57_prepare_cleanup_root=$prepared
  trap cleanup_prepare_tree EXIT HUP INT TERM
  chmod 0700 "$prepared"
  snapshot="$prepared/snapshot"
  mkdir -m 0700 "$snapshot"
  git_root archive "$approved" -- "${live_critical_paths[@]}" |
    tar -x -C "$snapshot"
  build_snapshot "$snapshot" "$prepared" "$approved"
  verify_approved_baseline "$approved"

  binary="$prepared/d279_stage8_enroll.pending"
  library="$prepared/libfprint-2.so.2.0.0"
  gusb="$prepared/libgusb.so.2"
  [[ -f $binary && ! -L $binary && -f $library && ! -L $library &&
     -f $gusb && ! -L $gusb ]] ||
    refuse PREPARED_ARTIFACT_MISSING
  for component in core features2d flann imgproc; do
    [[ -f $prepared/libopencv_${component}.so.413 &&
       ! -L $prepared/libopencv_${component}.so.413 ]] ||
      refuse PREPARED_OPENCV_ARTIFACT_INVALID
  done
  mv "$binary" "$prepared/d279_stage8_enroll"
  binary="$prepared/d279_stage8_enroll"
  chmod 0700 "$binary"
  binary_sha=$(sha256sum "$binary" | awk '{print $1}')
  library_sha=$(sha256sum "$library" | awk '{print $1}')
  gusb_sha=$(sha256sum "$gusb" | awk '{print $1}')
  (cd "$prepared" && sha256sum d279_stage8_enroll libfprint-2.so.2.0.0 \
    libgusb.so.2 libopencv_core.so.413 libopencv_features2d.so.413 \
    libopencv_flann.so.413 libopencv_imgproc.so.413 \
    >d279-57-artifacts.sha256)
  manifest_sha=$(sha256sum "$prepared/d279-57-artifacts.sha256" | awk '{print $1}')
  grant_id="d27957-$approved"
  state="$prepared/d279-57-prepared.state"
  umask 077
  {
    echo "D279_57_BASELINE_SHA=$approved"
    echo "D279_57_OPERATION=$operation"
    echo "D279_57_PREPARED_DIR=$prepared"
    echo "D279_57_BINARY_SHA256=$binary_sha"
    echo "D279_57_LIBRARY_SHA256=$library_sha"
    echo "D279_57_GUSB_SHA256=$gusb_sha"
    echo "D279_57_ARTIFACT_MANIFEST_SHA256=$manifest_sha"
    echo "D279_57_GRANT_ID=$grant_id"
  } >"$state"
  chmod 0600 "$state"

  echo APPROVED_BUILD_PREPARED=true
  echo "APPROVED_BASELINE_SHA=$approved"
  echo "PREPARED_BUILD_DIR=$prepared"
  echo "BINARY_SHA256=$binary_sha"
  echo "LIBRARY_SHA256=$library_sha"
  echo "GUSB_SHA256=$gusb_sha"
  echo "ARTIFACT_MANIFEST_SHA256=$manifest_sha"
  echo "EXPECTED_GRANT_ID=$grant_id"
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo LIVE_EXECUTION_PERFORMED=false
  d279_57_prepare_cleanup_root=
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
  grant_id="d27957-$approved"
  umask 077
  ( set -C
    {
      echo "D279_57_BASELINE_SHA=$approved"
      echo "D279_57_OPERATION=$operation"
      echo "D279_57_GRANT_ID=$grant_id"
    } >"$grant"
  ) || refuse GRANT_CREATE_FAILED
  chmod 0600 "$grant"
  echo GRANT_WRITTEN=true
  echo "GRANT_FILE=$grant"
  echo "GRANT_ID=$grant_id"
  echo "NOTA=Il grant e one-shot; non ricrearlo e non riusarlo dopo la run."
}

run_approved_live ()
{
  local prepared=$1 grant=$2 state baseline state_operation state_dir
  local expected_binary_sha expected_library_sha expected_gusb_sha expected_manifest_sha expected_grant_id
  local actual_binary_sha actual_library_sha actual_gusb_sha actual_manifest_sha
  local grant_baseline grant_operation
  local grant_id mode owner accepted claim_root claim runtime results_parent
  local result_root
  local stamp log rc

  [[ $EUID -eq 0 ]] || refuse LIVE_REQUIRES_ROOT
  umask 077
  command -v pgrep >/dev/null 2>&1 || refuse FPRINTD_PROCESS_GUARD_UNAVAILABLE
  if pgrep -x fprintd >/dev/null 2>&1; then
    refuse FPRINTD_PROCESS_ACTIVE
  fi
  [[ $prepared == /tmp/goodix-d279-57-approved.* && -d $prepared &&
     ! -L $prepared ]] || refuse PREPARED_DIR_INVALID
  state="$prepared/d279-57-prepared.state"
  [[ -f $state && ! -L $state ]] || refuse PREPARED_STATE_INVALID
  baseline=$(state_value "$state" D279_57_BASELINE_SHA) || refuse STATE_MALFORMED
  state_operation=$(state_value "$state" D279_57_OPERATION) || refuse STATE_MALFORMED
  state_dir=$(state_value "$state" D279_57_PREPARED_DIR) || refuse STATE_MALFORMED
  expected_binary_sha=$(state_value "$state" D279_57_BINARY_SHA256) || refuse STATE_MALFORMED
  expected_library_sha=$(state_value "$state" D279_57_LIBRARY_SHA256) || refuse STATE_MALFORMED
  expected_gusb_sha=$(state_value "$state" D279_57_GUSB_SHA256) || refuse STATE_MALFORMED
  expected_manifest_sha=$(state_value "$state" D279_57_ARTIFACT_MANIFEST_SHA256) ||
    refuse STATE_MALFORMED
  expected_grant_id=$(state_value "$state" D279_57_GRANT_ID) || refuse STATE_MALFORMED
  [[ $state_operation == "$operation" && $state_dir == "$prepared" ]] ||
    refuse STATE_BINDING_MISMATCH
  verify_approved_baseline "$baseline"

  [[ -f $prepared/d279_stage8_enroll &&
     ! -L $prepared/d279_stage8_enroll ]] || refuse BINARY_INVALID
  [[ -f $prepared/libfprint-2.so.2.0.0 &&
     ! -L $prepared/libfprint-2.so.2.0.0 ]] || refuse LIBRARY_INVALID
  [[ -f $prepared/libgusb.so.2 && ! -L $prepared/libgusb.so.2 ]] ||
    refuse GUSB_INVALID
  actual_binary_sha=$(sha256sum "$prepared/d279_stage8_enroll" | awk '{print $1}')
  actual_library_sha=$(sha256sum "$prepared/libfprint-2.so.2.0.0" | awk '{print $1}')
  actual_gusb_sha=$(sha256sum "$prepared/libgusb.so.2" | awk '{print $1}')
  [[ $actual_binary_sha == "$expected_binary_sha" ]] || refuse BINARY_HASH_MISMATCH
  [[ $actual_library_sha == "$expected_library_sha" ]] || refuse LIBRARY_HASH_MISMATCH
  [[ $actual_gusb_sha == "$expected_gusb_sha" ]] || refuse GUSB_HASH_MISMATCH
  [[ -f $prepared/d279-57-artifacts.sha256 ]] ||
    refuse ARTIFACT_MANIFEST_MISSING
  actual_manifest_sha=$(sha256sum "$prepared/d279-57-artifacts.sha256" | awk '{print $1}')
  [[ $actual_manifest_sha == "$expected_manifest_sha" ]] ||
    refuse ARTIFACT_MANIFEST_HASH_MISMATCH
  (cd "$prepared" && sha256sum -c d279-57-artifacts.sha256) ||
    refuse ARTIFACT_BUNDLE_HASH_MISMATCH

  [[ $grant == /* && -f $grant && ! -L $grant &&
     $(wc -l <"$grant") -eq 3 ]] ||
    refuse GRANT_FILE_POLICY
  mode=$(stat -c %a "$grant")
  owner=$(stat -c %u "$grant")
  [[ $((8#$mode & 0177)) -eq 0 ]] || refuse GRANT_FILE_POLICY
  accepted=0
  [[ $owner -eq $EUID ]] && accepted=1
  if [[ ${SUDO_UID:-} =~ ^[0-9]+$ && $owner -eq $SUDO_UID ]]; then
    accepted=1
  fi
  [[ $accepted -eq 1 ]] || refuse GRANT_FILE_POLICY
  grant_baseline=$(state_value "$grant" D279_57_BASELINE_SHA) || refuse GRANT_MALFORMED
  grant_operation=$(state_value "$grant" D279_57_OPERATION) || refuse GRANT_MALFORMED
  grant_id=$(state_value "$grant" D279_57_GRANT_ID) || refuse GRANT_MALFORMED
  [[ $grant_baseline == "$baseline" && $grant_operation == "$operation" &&
     $grant_id == "$expected_grant_id" ]] || refuse GRANT_BINDING_MISMATCH

  claim_root=/var/tmp/goodix-d279-57-consumed-grants
  if [[ ! -e $claim_root ]]; then
    mkdir -m 0700 "$claim_root" || refuse CLAIM_ROOT_CREATE_FAILED
  fi
  [[ -d $claim_root && ! -L $claim_root &&
     $(stat -c %u "$claim_root") -eq 0 &&
     $(stat -c %a "$claim_root") == 700 ]] || refuse CLAIM_ROOT_POLICY
  claim="$claim_root/$grant_id"
  mkdir -m 0700 "$claim" 2>/dev/null || refuse GRANT_ALREADY_CONSUMED
  {
    echo "D279_57_BASELINE_SHA=$baseline"
    echo "D279_57_OPERATION=$operation"
    echo "D279_57_GRANT_ID=$grant_id"
  } >"$claim/consumed.state"
  chmod 0600 "$claim/consumed.state"

  runtime=$(mktemp -d /tmp/goodix-d279-57-runtime.XXXXXX)
  d279_57_runtime_cleanup_root=$runtime
  chmod 0700 "$runtime"
  trap cleanup_runtime_tree EXIT HUP INT TERM
  cp "$prepared/d279_stage8_enroll" "$runtime/d279_stage8_enroll"
  cp "$prepared/libfprint-2.so.2.0.0" "$runtime/libfprint-2.so.2.0.0"
  cp "$prepared/libgusb.so.2" "$runtime/libgusb.so.2"
  cp "$prepared"/libopencv_*.so.413 "$runtime/"
  cp "$prepared/d279-57-artifacts.sha256" "$runtime/"
  ln -s libfprint-2.so.2.0.0 "$runtime/libfprint-2.so.2"
  chmod 0700 "$runtime/d279_stage8_enroll"
  chmod 0600 "$runtime/libfprint-2.so.2.0.0"
  chmod 0600 "$runtime/libgusb.so.2" "$runtime"/libopencv_*.so.413 \
    "$runtime/d279-57-artifacts.sha256"
  [[ $(sha256sum "$runtime/d279_stage8_enroll" | awk '{print $1}') == "$expected_binary_sha" ]] ||
    refuse RUNTIME_BINARY_HASH_MISMATCH
  [[ $(sha256sum "$runtime/libfprint-2.so.2.0.0" | awk '{print $1}') == "$expected_library_sha" ]] ||
    refuse RUNTIME_LIBRARY_HASH_MISMATCH
  [[ $(sha256sum "$runtime/libgusb.so.2" | awk '{print $1}') == "$expected_gusb_sha" ]] ||
    refuse RUNTIME_GUSB_HASH_MISMATCH
  actual_manifest_sha=$(sha256sum "$runtime/d279-57-artifacts.sha256" | awk '{print $1}')
  [[ $actual_manifest_sha == "$expected_manifest_sha" ]] ||
    refuse RUNTIME_MANIFEST_HASH_MISMATCH
  (cd "$runtime" && sha256sum -c d279-57-artifacts.sha256) ||
    refuse RUNTIME_ARTIFACT_BUNDLE_HASH_MISMATCH
  verify_host_sigfm_runtime

  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  results_parent=/var/tmp/goodix-d279-57-results
  if [[ ! -e $results_parent ]]; then
    mkdir -m 0700 "$results_parent" || refuse RESULT_ROOT_CREATE_FAILED
  fi
  [[ -d $results_parent && ! -L $results_parent &&
     $(stat -c %u "$results_parent") -eq 0 &&
     $(stat -c %a "$results_parent") == 700 ]] || refuse RESULT_ROOT_POLICY
  result_root="$results_parent/${stamp}-${baseline:0:12}"
  mkdir -m 0700 "$result_root" || refuse RESULT_DIR_CREATE_FAILED
  log="$result_root/operator.log"
  echo "INIZIO RUN ONE-SHOT. Non rilanciare questo comando in caso di errore."
  echo "ISTRUZIONE_CONTATTI=Segui soltanto AZIONE_OPERATORE: il progresso STAGE_COMPLETATO non indica quando sollevare il dito."
  echo "ISTRUZIONE_STAGE8=Mantieni anche il contatto 8 finche compare RILASCIO_FISICO_PRONTO=8; quindi togli il dito."
  set +e
  env \
    LD_LIBRARY_PATH="$runtime" \
    D279_57_APPROVED_LIVE_SHA="$baseline" \
    D279_57_OPERATION="$operation" \
    D279_57_OPERATOR_AUTHORIZATION="$authorization" \
    D279_57_GRANT_ID="$grant_id" \
    timeout --signal=INT --kill-after=30s 660s \
      "$runtime/d279_stage8_enroll" --run-once 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  set -e
  chmod 0600 "$log"
  {
    echo "D279_57_BASELINE_SHA=$baseline"
    echo "D279_57_OPERATION=$operation"
    echo "D279_57_GRANT_ID=$grant_id"
    echo "RUN_RETURN_CODE=$rc"
    echo "ACTION_ATTEMPT_MAX=1"
    echo "OPERATOR_RETRY_COUNT=0"
    echo "SECOND_ACTION_COUNT=0"
    echo "REOPEN_COUNT=0"
    echo "KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0"
    echo "EXPECTED_ENROLLMENT_STAGE_COUNT=8"
    echo "REUSABILITY_PROVEN=false"
    echo "SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false"
    echo "DEVICE_SIDE_TIMEOUT_OR_QUIESCENCE_INFERRED=false"
  } >"$result_root/summary.env"
  chmod 0600 "$result_root/summary.env"
  echo "RISULTATI=$result_root"
  echo "RUN_RETURN_CODE=$rc"
  echo "GRANT_CONSUMED=true"
  echo "RETRY_AUTHORIZED=false"
  echo "DEVICE_SIDE_TIMEOUT_OR_QUIESCENCE_INFERRED=false"
  if [[ $rc -ne 0 ]]; then
    echo "STOP: non ripetere la run; conserva i risultati e considera ignoto lo stato del sensore." >&2
  fi
  cleanup_runtime_tree
  d279_57_runtime_cleanup_root=
  trap - EXIT HUP INT TERM
  return "$rc"
}

export_results ()
{
  local result_root=$1 basename export_dir source_sha copied_sha

  [[ $EUID -eq 0 ]] || refuse EXPORT_REQUIRES_ROOT
  [[ ${SUDO_UID:-} =~ ^[0-9]+$ && ${SUDO_GID:-} =~ ^[0-9]+$ ]] ||
    refuse EXPORT_REQUIRES_SUDO_CALLER
  [[ $result_root == /var/tmp/goodix-d279-57-results/* &&
     -d $result_root && ! -L $result_root ]] || refuse EXPORT_SOURCE_INVALID
  basename=${result_root##*/}
  [[ $basename =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] ||
    refuse EXPORT_SOURCE_INVALID
  [[ $(readlink -f -- "$result_root") == "$result_root" ]] ||
    refuse EXPORT_SOURCE_INVALID
  for name in operator.log summary.env; do
    [[ -f $result_root/$name && ! -L $result_root/$name &&
       $(stat -c %u "$result_root/$name") -eq 0 ]] ||
      refuse EXPORT_SOURCE_FILE_INVALID
  done

  export_dir=$(mktemp -d /tmp/goodix-d279-57-export.XXXXXX)
  chmod 0700 "$export_dir"
  for name in operator.log summary.env; do
    source_sha=$(sha256sum "$result_root/$name" | awk '{print $1}')
    install -m 0600 -o "$SUDO_UID" -g "$SUDO_GID" \
      "$result_root/$name" "$export_dir/$name"
    copied_sha=$(sha256sum "$export_dir/$name" | awk '{print $1}')
    [[ $source_sha == "$copied_sha" ]] || refuse EXPORT_HASH_MISMATCH
    echo "${name}_SHA256=$source_sha"
  done
  chown "$SUDO_UID:$SUDO_GID" "$export_dir"
  echo D279_57_RESULTS_EXPORT=PASS_BYTE_IDENTICAL
  echo "EXPORT_DIRECTORY=$export_dir"
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo LIVE_EXECUTION_PERFORMED=false
}

case ${1:-} in
  --offline-preflight)
    [[ $# -eq 1 ]] || usage
    offline_preflight
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
  *)
    usage
    ;;
esac
