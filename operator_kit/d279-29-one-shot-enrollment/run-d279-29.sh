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
operation=D279_29_ONE_SHOT_ENROLLMENT
authorization=D279_29_ONE_ENROLLMENT_ACTION_NO_RETRY
d279_29_offline_cleanup_root=
d279_29_runtime_cleanup_root=

git_root () { git -C "$root" -c safe.directory="$root" "$@"; }
is_full_sha () { [[ ${1:-} =~ ^[0-9a-fA-F]{40}$ ]]; }

usage ()
{
  echo "Uso:" >&2
  echo "  $0 --offline-preflight" >&2
  echo "  $0 --prepare-approved-live <SHA_COMPLETO_APPROVATO>" >&2
  echo "  $0 --write-grant <SHA_COMPLETO_APPROVATO> <FILE_GRANT>" >&2
  echo "  sudo $0 --run-approved-live <BUILD_PREPARATO> --grant <FILE_GRANT>" >&2
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
  if [[ ${d279_29_offline_cleanup_root:-} == /tmp/goodix-d279-29-offline.* ]]; then
    find "$d279_29_offline_cleanup_root" -depth -delete 2>/dev/null || true
  fi
}

cleanup_runtime_tree ()
{
  if [[ ${d279_29_runtime_cleanup_root:-} == /tmp/goodix-d279-29-runtime.* ]]; then
    find "$d279_29_runtime_cleanup_root" -depth -delete 2>/dev/null || true
  fi
}

live_critical_paths=(
  libfprint-driver
  reference/libfprint-fedora44-1.94.100/source
  tools/d279_one_shot_enroll.c
  operator_kit/d279-29-one-shot-enrollment
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

build_snapshot ()
{
  local source_root=$1 output_root=$2 baseline=$3
  local build_dir="$output_root/build"
  local pkgconfig_dir="$output_root/pkgconfig"
  local inner="$source_root/operator_kit/d279-29-one-shot-enrollment/build-inner.sh"
  local pc_template="$source_root/libfprint-driver/tests/support/d279/gusb.pc.in"
  local include_dir="$source_root/libfprint-driver/tests/support/d279"
  local host_gusb

  host_gusb=$(find_host_gusb) || {
    echo "BLOCKED_ENVIRONMENT=libgusb runtime host non trovata" >&2
    return 2
  }
  mkdir -p "$build_dir" "$pkgconfig_dir"
  cp "$host_gusb" "$pkgconfig_dir/libgusb.so.2"
  sed -e "s|@PREFIX@|$pkgconfig_dir|g" \
      -e "s|@INCLUDEDIR@|$include_dir|g" \
      "$pc_template" >"$pkgconfig_dir/gusb.pc"

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
}

offline_preflight ()
{
  local work binary

  [[ $EUID -ne 0 ]] || refuse OFFLINE_PREFLIGHT_REQUIRES_NORMAL_USER
  source_guard_audit "$root/tools/d279_one_shot_enroll.c"
  work=$(mktemp -d /tmp/goodix-d279-29-offline.XXXXXX)
  d279_29_offline_cleanup_root=$work
  trap cleanup_offline_tree EXIT HUP INT TERM
  build_snapshot "$root" "$work" UNAPPROVED_FOR_LIVE
  binary="$work/d279_one_shot_enroll.pending"
  [[ -f $binary && ! -L $binary ]] || refuse OFFLINE_BINARY_MISSING
  mv "$binary" "$work/d279_one_shot_enroll"
  chmod 0700 "$work/d279_one_shot_enroll"
  "$work/d279_one_shot_enroll" --gate-self-test
  LD_LIBRARY_PATH="$work" ldd "$work/d279_one_shot_enroll"
  echo D279_29_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
  echo D279_29_COMPILED_BASELINE=UNAPPROVED_FOR_LIVE
  echo ACTION_ATTEMPT_MAX=1
  echo OPERATOR_RETRY_COUNT=0
  echo SECOND_ACTION_COUNT=0
  echo REOPEN_COUNT=0
  echo BIOMETRIC_TEMPLATE_SAVED=false
  echo HOST_DEADLINE_IS_DEVICE_QUIESCENCE_PROOF=false
  echo KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0
  echo SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo LIVE_EXECUTION_PERFORMED=false
  cleanup_offline_tree
  d279_29_offline_cleanup_root=
  trap - EXIT HUP INT TERM
}

prepare_approved_live ()
{
  local approved=$1 prepared snapshot binary library gusb state grant_id
  local binary_sha library_sha gusb_sha

  [[ $EUID -ne 0 ]] || refuse PREPARE_REQUIRES_NORMAL_USER
  verify_approved_baseline "$approved"
  source_guard_audit "$root/tools/d279_one_shot_enroll.c"
  prepared=$(mktemp -d /tmp/goodix-d279-29-approved.XXXXXX)
  chmod 0700 "$prepared"
  snapshot="$prepared/snapshot"
  mkdir -m 0700 "$snapshot"
  git_root archive "$approved" -- "${live_critical_paths[@]}" |
    tar -x -C "$snapshot"
  build_snapshot "$snapshot" "$prepared" "$approved"
  verify_approved_baseline "$approved"

  binary="$prepared/d279_one_shot_enroll.pending"
  library="$prepared/libfprint-2.so.2.0.0"
  gusb="$prepared/libgusb.so.2"
  [[ -f $binary && ! -L $binary && -f $library && ! -L $library &&
     -f $gusb && ! -L $gusb ]] ||
    refuse PREPARED_ARTIFACT_MISSING
  mv "$binary" "$prepared/d279_one_shot_enroll"
  binary="$prepared/d279_one_shot_enroll"
  chmod 0700 "$binary"
  binary_sha=$(sha256sum "$binary" | awk '{print $1}')
  library_sha=$(sha256sum "$library" | awk '{print $1}')
  gusb_sha=$(sha256sum "$gusb" | awk '{print $1}')
  grant_id="d27929-$approved"
  state="$prepared/d279-29-prepared.state"
  umask 077
  {
    echo "D279_29_BASELINE_SHA=$approved"
    echo "D279_29_OPERATION=$operation"
    echo "D279_29_PREPARED_DIR=$prepared"
    echo "D279_29_BINARY_SHA256=$binary_sha"
    echo "D279_29_LIBRARY_SHA256=$library_sha"
    echo "D279_29_GUSB_SHA256=$gusb_sha"
    echo "D279_29_GRANT_ID=$grant_id"
  } >"$state"
  chmod 0600 "$state"

  echo APPROVED_BUILD_PREPARED=true
  echo "APPROVED_BASELINE_SHA=$approved"
  echo "PREPARED_BUILD_DIR=$prepared"
  echo "BINARY_SHA256=$binary_sha"
  echo "LIBRARY_SHA256=$library_sha"
  echo "GUSB_SHA256=$gusb_sha"
  echo "EXPECTED_GRANT_ID=$grant_id"
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo LIVE_EXECUTION_PERFORMED=false
}

write_grant ()
{
  local approved=$1 grant=$2 grant_id parent

  [[ $EUID -ne 0 ]] || refuse GRANT_CREATION_REQUIRES_NORMAL_USER
  verify_approved_baseline "$approved"
  [[ ! -e $grant && ! -L $grant ]] || refuse GRANT_PATH_ALREADY_EXISTS
  parent=$(dirname -- "$grant")
  [[ -d $parent && ! -L $parent ]] || refuse GRANT_PARENT_INVALID
  grant_id="d27929-$approved"
  umask 077
  ( set -C
    {
      echo "D279_29_BASELINE_SHA=$approved"
      echo "D279_29_OPERATION=$operation"
      echo "D279_29_GRANT_ID=$grant_id"
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
  local expected_binary_sha expected_library_sha expected_gusb_sha expected_grant_id
  local actual_binary_sha actual_library_sha actual_gusb_sha grant_baseline grant_operation
  local grant_id mode owner accepted claim_root claim runtime results_parent
  local result_root
  local stamp log rc

  [[ $EUID -eq 0 ]] || refuse LIVE_REQUIRES_ROOT
  umask 077
  command -v pgrep >/dev/null 2>&1 || refuse FPRINTD_PROCESS_GUARD_UNAVAILABLE
  if pgrep -x fprintd >/dev/null 2>&1; then
    refuse FPRINTD_PROCESS_ACTIVE
  fi
  [[ $prepared == /tmp/goodix-d279-29-approved.* && -d $prepared &&
     ! -L $prepared ]] || refuse PREPARED_DIR_INVALID
  state="$prepared/d279-29-prepared.state"
  [[ -f $state && ! -L $state ]] || refuse PREPARED_STATE_INVALID
  baseline=$(state_value "$state" D279_29_BASELINE_SHA) || refuse STATE_MALFORMED
  state_operation=$(state_value "$state" D279_29_OPERATION) || refuse STATE_MALFORMED
  state_dir=$(state_value "$state" D279_29_PREPARED_DIR) || refuse STATE_MALFORMED
  expected_binary_sha=$(state_value "$state" D279_29_BINARY_SHA256) || refuse STATE_MALFORMED
  expected_library_sha=$(state_value "$state" D279_29_LIBRARY_SHA256) || refuse STATE_MALFORMED
  expected_gusb_sha=$(state_value "$state" D279_29_GUSB_SHA256) || refuse STATE_MALFORMED
  expected_grant_id=$(state_value "$state" D279_29_GRANT_ID) || refuse STATE_MALFORMED
  [[ $state_operation == "$operation" && $state_dir == "$prepared" ]] ||
    refuse STATE_BINDING_MISMATCH
  verify_approved_baseline "$baseline"

  [[ -f $prepared/d279_one_shot_enroll &&
     ! -L $prepared/d279_one_shot_enroll ]] || refuse BINARY_INVALID
  [[ -f $prepared/libfprint-2.so.2.0.0 &&
     ! -L $prepared/libfprint-2.so.2.0.0 ]] || refuse LIBRARY_INVALID
  [[ -f $prepared/libgusb.so.2 && ! -L $prepared/libgusb.so.2 ]] ||
    refuse GUSB_INVALID
  actual_binary_sha=$(sha256sum "$prepared/d279_one_shot_enroll" | awk '{print $1}')
  actual_library_sha=$(sha256sum "$prepared/libfprint-2.so.2.0.0" | awk '{print $1}')
  actual_gusb_sha=$(sha256sum "$prepared/libgusb.so.2" | awk '{print $1}')
  [[ $actual_binary_sha == "$expected_binary_sha" ]] || refuse BINARY_HASH_MISMATCH
  [[ $actual_library_sha == "$expected_library_sha" ]] || refuse LIBRARY_HASH_MISMATCH
  [[ $actual_gusb_sha == "$expected_gusb_sha" ]] || refuse GUSB_HASH_MISMATCH

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
  grant_baseline=$(state_value "$grant" D279_29_BASELINE_SHA) || refuse GRANT_MALFORMED
  grant_operation=$(state_value "$grant" D279_29_OPERATION) || refuse GRANT_MALFORMED
  grant_id=$(state_value "$grant" D279_29_GRANT_ID) || refuse GRANT_MALFORMED
  [[ $grant_baseline == "$baseline" && $grant_operation == "$operation" &&
     $grant_id == "$expected_grant_id" ]] || refuse GRANT_BINDING_MISMATCH

  claim_root=/var/tmp/goodix-d279-29-consumed-grants
  if [[ ! -e $claim_root ]]; then
    mkdir -m 0700 "$claim_root" || refuse CLAIM_ROOT_CREATE_FAILED
  fi
  [[ -d $claim_root && ! -L $claim_root &&
     $(stat -c %u "$claim_root") -eq 0 &&
     $(stat -c %a "$claim_root") == 700 ]] || refuse CLAIM_ROOT_POLICY
  claim="$claim_root/$grant_id"
  mkdir -m 0700 "$claim" 2>/dev/null || refuse GRANT_ALREADY_CONSUMED
  {
    echo "D279_29_BASELINE_SHA=$baseline"
    echo "D279_29_OPERATION=$operation"
    echo "D279_29_GRANT_ID=$grant_id"
  } >"$claim/consumed.state"
  chmod 0600 "$claim/consumed.state"

  runtime=$(mktemp -d /tmp/goodix-d279-29-runtime.XXXXXX)
  d279_29_runtime_cleanup_root=$runtime
  chmod 0700 "$runtime"
  trap cleanup_runtime_tree EXIT HUP INT TERM
  cp "$prepared/d279_one_shot_enroll" "$runtime/d279_one_shot_enroll"
  cp "$prepared/libfprint-2.so.2.0.0" "$runtime/libfprint-2.so.2.0.0"
  cp "$prepared/libgusb.so.2" "$runtime/libgusb.so.2"
  ln -s libfprint-2.so.2.0.0 "$runtime/libfprint-2.so.2"
  chmod 0700 "$runtime/d279_one_shot_enroll"
  chmod 0600 "$runtime/libfprint-2.so.2.0.0"
  chmod 0600 "$runtime/libgusb.so.2"
  [[ $(sha256sum "$runtime/d279_one_shot_enroll" | awk '{print $1}') == "$expected_binary_sha" ]] ||
    refuse RUNTIME_BINARY_HASH_MISMATCH
  [[ $(sha256sum "$runtime/libfprint-2.so.2.0.0" | awk '{print $1}') == "$expected_library_sha" ]] ||
    refuse RUNTIME_LIBRARY_HASH_MISMATCH
  [[ $(sha256sum "$runtime/libgusb.so.2" | awk '{print $1}') == "$expected_gusb_sha" ]] ||
    refuse RUNTIME_GUSB_HASH_MISMATCH

  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  results_parent=/var/tmp/goodix-d279-29-results
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
  set +e
  env \
    LD_LIBRARY_PATH="$runtime" \
    D279_29_APPROVED_LIVE_SHA="$baseline" \
    D279_29_OPERATION="$operation" \
    D279_29_OPERATOR_AUTHORIZATION="$authorization" \
    D279_29_GRANT_ID="$grant_id" \
    timeout --signal=INT --kill-after=30s 660s \
      "$runtime/d279_one_shot_enroll" --run-once 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  set -e
  chmod 0600 "$log"
  {
    echo "D279_29_BASELINE_SHA=$baseline"
    echo "D279_29_OPERATION=$operation"
    echo "D279_29_GRANT_ID=$grant_id"
    echo "RUN_RETURN_CODE=$rc"
    echo "ACTION_ATTEMPT_MAX=1"
    echo "OPERATOR_RETRY_COUNT=0"
    echo "SECOND_ACTION_COUNT=0"
    echo "REOPEN_COUNT=0"
    echo "KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0"
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
  d279_29_runtime_cleanup_root=
  trap - EXIT HUP INT TERM
  return "$rc"
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
  *)
    usage
    ;;
esac
