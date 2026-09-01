#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
build_script="$root/libfprint-driver/tests/build_goodix_d278_13_adapter.sh"
operation=D278_13_INTEGRATED_PATH_ONCE
test_only=${D278_14_WORKFLOW_GUARD_TEST_ONLY:-0}

usage () {
  echo "usage: $0 --host-only-prelive | --prepare-approved-live <FULL_APPROVED_SHA> | --run-approved-live <PREPARED_BUILD_DIR> --grant <GRANT_FILE>" >&2
  exit 2
}

is_full_sha () { [[ ${1:-} =~ ^[0-9a-fA-F]{40}$ ]]; }

guard_refusal () {
  echo "APPROVED_WORKFLOW_REFUSED=true"
  echo "APPROVED_WORKFLOW_REFUSAL_REASON=$1"
  echo "REAL_USB_ACCESS=false"
  echo "REAL_USB_SUBMIT=0"
  echo "REAL_PRODUCTION_SECRET_READ=false"
  echo "LIVE_EXECUTION_PERFORMED=false"
  exit 3
}

state_value () {
  local state=$1 key=$2 value
  value=$(sed -n "s/^${key}=//p" "$state")
  [[ -n $value && $(grep -c "^${key}=" "$state") -eq 1 ]] || return 1
  printf '%s\n' "$value"
}

verify_canonical_baseline () {
  local approved=$1
  is_full_sha "$approved" || guard_refusal INVALID_APPROVED_SHA
  [[ $(git -C "$root" branch --show-current) == main ]] ||
    guard_refusal BRANCH_NOT_MAIN
  [[ $(git -C "$root" rev-parse HEAD) == "$approved" ]] ||
    guard_refusal HEAD_MISMATCH
  D278_13_BASELINE_GUARD_TEST_ONLY=1 \
    D278_13_BASELINE_GUARD_TEST_ROOT="$root" \
    D278_13_BUILD_APPROVED_BASELINE_SHA="$approved" \
    "$build_script" >/dev/null || guard_refusal LIVE_CRITICAL_SOURCE_DIRTY
}

host_only_prelive () {
  local build proof_output secure_output marker
  cd "$root"
  secure_output=$("$root/libfprint-driver/tests/run_goodix_d278_secure_session_test.sh")
  printf '%s\n' "$secure_output"
  for marker in \
    PRE_SESSION_RX_SYNC_IMPLEMENTED=true \
    PRE_SESSION_RX_CLEAN_QUIET_BOUNDARY_HOST_ONLY_PROVEN=true \
    PRE_SESSION_RX_RESIDUE_CHAIN_QUARANTINED_HOST_ONLY_PROVEN=true \
    PRE_SESSION_RX_MULTI_FRAME_COMPLETION_QUARANTINED_HOST_ONLY_PROVEN=true \
    PRE_SESSION_RX_NON_TIMEOUT_ERROR_FAIL_CLOSED=true \
    PRE_SESSION_RX_BOUNDS_FAIL_CLOSED=true \
    PRE_SESSION_RX_OUT_BEFORE_SYNC_REJECTED=true \
    PRE_SESSION_RX_SECURE_START_BEFORE_SYNC_REJECTED=true \
    STRICT_A2_ACK_THEN_TYPED_RESTORED=true \
    CORRECTIVE_5_RUNTIME_TOLERANCE_RETIRED=true; do
    grep -F "$marker" <<<"$secure_output" >/dev/null
  done
  "$root/libfprint-driver/tests/test_goodix_d278_13_live_guards.sh" \
    --baseline-only "$root" "$build_script"
  "$root/libfprint-driver/tests/test_goodix_d278_14_workflow.sh" "$root"
  build=$(mktemp -d /tmp/goodix-d278-13-prelive.XXXXXX)
  cleanup () {
    find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true
    rmdir "$build" 2>/dev/null || true
  }
  trap cleanup EXIT HUP INT TERM
  KEEP_BUILD=1 D278_13_BUILD_DIR="$build" "$build_script" >/dev/null
  proof_output=$("$build/d278_integrated_path_once" \
    --operator-prompt-state-machine-host-only)
  printf '%s\n' "$proof_output"
  for marker in \
    OPERATOR_PROMPT_SEQUENCE_HOST_ONLY_PROVEN=true \
    OPERATOR_PROMPT_SUCCESS_FAILURE_EXCLUSIVE=true \
    OPERATOR_PROMPT_DUPLICATE_SUPPRESSION_HOST_ONLY_PROVEN=true \
    OPERATOR_PROMPT_STOP_THEN_TERMINAL_HOST_ONLY_PROVEN=true \
    OPERATOR_PROMPT_TERMINAL_THEN_STOP_HOST_ONLY_PROVEN=true \
    OPERATOR_ACTION_BANNER_FORMAT_EXACT=true \
    OPERATOR_ACTION_BANNER_MACHINE_PREFIX=false \
    PRE_SESSION_RX_SYNC_IMPLEMENTED=true \
    PRE_SESSION_RX_CLEAN_QUIET_BOUNDARY_HOST_ONLY_PROVEN=true \
    STRICT_A2_ACK_THEN_TYPED_RESTORED=true \
    CORRECTIVE_5_RUNTIME_TOLERANCE_RETIRED=true; do
    grep -F "$marker" <<<"$proof_output" >/dev/null
  done
  echo EXECUTABLE_CLOSURE=PASS_HOST_ONLY
  echo LIVE_CAPABLE_INTEGRATED_PATH_HOST_ONLY_PROVEN=true
  echo LIVE_BASELINE_BINDING_GUARD_HOST_ONLY_PROVEN=true
  echo ONE_AUTHORIZATION_ONE_ATTEMPT_GUARD_HOST_ONLY_PROVEN=true
  echo SECOND_USE_OF_AUTHORIZATION_REJECTED=true
  echo GENERIC_BASELINE_BOUND_OPERATOR_WORKFLOW_HOST_ONLY_PROVEN=true
  echo DIRECT_UNPREPARED_LIVE_PATH_REJECTED=true
  echo OPERATOR_PROMPT_PRELIVE_GATED=true
  echo OPERATOR_MESSAGES_LANGUAGE=ITALIAN
  echo OPERATOR_ACTION_BANNERS_IMPLEMENTED=true
  echo REAL_USB_ACCESS=false
  echo REAL_USB_SUBMIT=0
  echo REAL_PRODUCTION_SECRET_READ=false
  echo LIVE_EXECUTION_PERFORMED=false
  echo CURRENT_LIVE_AUTHORIZED=false
  echo READY_FOR_LIVE=false
  echo RETRY_AUTHORIZED=false
  cleanup
  trap - EXIT HUP INT TERM
}

prepare_approved_live () {
  local approved=$1 build binary binary_sha state
  if [[ $test_only != 1 && $EUID -eq 0 ]]; then
    guard_refusal PREPARE_REQUIRES_NORMAL_USER
  fi
  verify_canonical_baseline "$approved"
  if [[ $test_only == 1 ]]; then
    build=${D278_14_TEST_BUILD_DIR:?missing D278_14_TEST_BUILD_DIR}
    binary=${D278_14_TEST_BINARY:?missing D278_14_TEST_BINARY}
    mkdir -p "$build"
    cp "$binary" "$build/d278_integrated_path_once"
  else
    host_only_prelive
    build=$(mktemp -d /tmp/goodix-d278-14-approved.XXXXXX)
    KEEP_BUILD=1 D278_13_BUILD_DIR="$build" \
      D278_13_BUILD_APPROVED_BASELINE_SHA="$approved" \
      "$build_script" >/dev/null
  fi
  binary="$build/d278_integrated_path_once"
  [[ -x $binary ]] || guard_refusal PREPARED_BINARY_MISSING
  binary_sha=$(sha256sum "$binary" | awk '{print $1}')
  state="$build/d278-14-prepared.state"
  umask 077
  {
    echo "D278_14_BASELINE_SHA=$approved"
    echo "D278_14_OPERATION=$operation"
    echo "D278_14_BUILD_DIR=$build"
    echo "D278_14_BINARY_SHA256=$binary_sha"
    echo "D278_14_TEST_ONLY=$test_only"
  } >"$state"
  chmod 0600 "$state"
  echo "APPROVED_BASELINE=$approved"
  echo "PREPARED_BUILD_DIR=$build"
  echo "BINARY_SHA256=$binary_sha"
  echo "PREPARED_STATE=$state"
  echo "REAL_USB_ACCESS=false"
  echo "REAL_USB_SUBMIT=0"
  echo "REAL_PRODUCTION_SECRET_READ=false"
  echo "LIVE_EXECUTION_PERFORMED=false"
}

run_approved_live () {
  local build=$1 grant=$2 state baseline state_operation state_build
  local expected_sha actual_sha state_test grant_baseline grant_operation grant_id
  local mode owner claim_root claim runtime_dir runtime_binary runtime_ticket live_log rc
  if [[ $test_only != 1 && $EUID -ne 0 ]]; then
    guard_refusal LIVE_REQUIRES_ROOT
  fi
  [[ $build == /tmp/goodix-d278-* && -d $build ]] ||
    guard_refusal PREPARED_BUILD_PATH_INVALID
  state="$build/d278-14-prepared.state"
  [[ -f $state && ! -L $state ]] || guard_refusal PREPARED_STATE_INVALID
  baseline=$(state_value "$state" D278_14_BASELINE_SHA) ||
    guard_refusal PREPARED_STATE_MALFORMED
  state_operation=$(state_value "$state" D278_14_OPERATION) ||
    guard_refusal PREPARED_STATE_MALFORMED
  state_build=$(state_value "$state" D278_14_BUILD_DIR) ||
    guard_refusal PREPARED_STATE_MALFORMED
  expected_sha=$(state_value "$state" D278_14_BINARY_SHA256) ||
    guard_refusal PREPARED_STATE_MALFORMED
  state_test=$(state_value "$state" D278_14_TEST_ONLY) ||
    guard_refusal PREPARED_STATE_MALFORMED
  [[ $state_operation == "$operation" && $state_build == "$build" ]] ||
    guard_refusal PREPARED_STATE_MISMATCH
  [[ $state_test == "$test_only" ]] || guard_refusal TEST_STATE_MISMATCH
  verify_canonical_baseline "$baseline"
  [[ -f $build/d278_integrated_path_once &&
     ! -L $build/d278_integrated_path_once ]] ||
    guard_refusal PREPARED_BINARY_INVALID
  actual_sha=$(sha256sum "$build/d278_integrated_path_once" | awk '{print $1}')
  [[ $actual_sha == "$expected_sha" ]] || guard_refusal BINARY_SHA256_MISMATCH

  [[ -f $grant && ! -L $grant ]] || guard_refusal GRANT_FILE_POLICY
  mode=$(stat -c %a "$grant")
  owner=$(stat -c %u "$grant")
  [[ $((8#$mode & 077)) -eq 0 ]] || guard_refusal GRANT_FILE_POLICY
  [[ $test_only == 1 || $owner -eq $EUID ]] || guard_refusal GRANT_FILE_POLICY
  [[ $(wc -l <"$grant") -eq 3 ]] || guard_refusal GRANT_MALFORMED
  grant_baseline=$(state_value "$grant" D278_14_BASELINE_SHA) ||
    guard_refusal GRANT_MALFORMED
  grant_operation=$(state_value "$grant" D278_14_OPERATION) ||
    guard_refusal GRANT_MALFORMED
  grant_id=$(state_value "$grant" D278_14_GRANT_ID) ||
    guard_refusal GRANT_MALFORMED
  [[ $grant_baseline == "$baseline" ]] || guard_refusal GRANT_BASELINE_MISMATCH
  [[ $grant_operation == "$operation" ]] || guard_refusal GRANT_OPERATION_MISMATCH
  [[ $grant_id =~ ^[A-Za-z0-9_-]{16,128}$ ]] || guard_refusal GRANT_MALFORMED
  if [[ $test_only == 1 ]]; then
    claim_root=${D278_14_TEST_CLAIM_ROOT:?missing D278_14_TEST_CLAIM_ROOT}
  else
    claim_root=/tmp/goodix-d278-14-consumed-grants
  fi
  if [[ ! -e $claim_root ]]; then
    mkdir -m 0700 "$claim_root" 2>/dev/null ||
      guard_refusal GRANT_CLAIM_ROOT_POLICY
  fi
  [[ -d $claim_root && ! -L $claim_root &&
     $(stat -c %u "$claim_root") -eq $EUID &&
     $(stat -c %a "$claim_root") == 700 ]] ||
    guard_refusal GRANT_CLAIM_ROOT_POLICY
  claim="$claim_root/$grant_id"
  mkdir -m 0700 "$claim" 2>/dev/null || guard_refusal GRANT_ALREADY_CONSUMED

  runtime_dir=$(mktemp -d /tmp/goodix-d278-14-runtime.XXXXXX)
  cleanup_runtime () { find "$runtime_dir" -depth -delete 2>/dev/null || true; }
  trap cleanup_runtime EXIT HUP INT TERM
  runtime_binary="$runtime_dir/d278_integrated_path_once"
  cp "$build/d278_integrated_path_once" "$runtime_binary"
  chmod 0700 "$runtime_binary"
  [[ $(sha256sum "$runtime_binary" | awk '{print $1}') == "$expected_sha" ]] ||
    guard_refusal RUNTIME_BINARY_COPY_MISMATCH
  runtime_ticket="$runtime_dir/runtime.ticket"
  umask 077
  {
    echo "D278_13_BASELINE_SHA=$baseline"
    echo "D278_13_OPERATION=$operation"
    echo "D278_13_NONCE=$grant_id"
  } >"$runtime_ticket"
  chmod 0600 "$runtime_ticket"
  if [[ $test_only == 1 ]]; then
    echo "RUNTIME_TICKET_CREATED=true"
    echo "ONE_AUTHORIZATION_ONE_ATTEMPT_GUARD_HOST_ONLY_PROVEN=true"
    echo "REAL_USB_ACCESS=false"
    echo "REAL_USB_SUBMIT=0"
    echo "REAL_PRODUCTION_SECRET_READ=false"
    echo "LIVE_EXECUTION_PERFORMED=false"
    cleanup_runtime
    trap - EXIT HUP INT TERM
    return 0
  fi

  ulimit -c 0
  live_log="$build/d278-14-live-${grant_id}.log"
  echo "======================"
  echo "AVVIO DEL TENTATIVO LIVE APPROVATO. NON RIPETERE IL COMANDO."
  echo "======================"
  set +e
  D278_13_APPROVED_LIVE_BASELINE_SHA="$baseline" \
    D278_13_OPERATOR_AUTHORIZATION=D278_13_ONE_INTEGRATED_TWO_ACQUISITION_RUN_NO_RETRY \
    D278_13_OPERATION="$operation" \
    D278_13_AUTHORIZATION_TICKET="$runtime_ticket" \
    LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$runtime_binary" --live-integrated-once 2>&1 | tee "$live_log"
  rc=${PIPESTATUS[0]}
  set -e
  echo "LIVE_LOG=$live_log"
  cleanup_runtime
  trap - EXIT HUP INT TERM
  return "$rc"
}

case "${1:-}" in
  --host-only-prelive)
    [[ $# -eq 1 ]] || usage
    host_only_prelive
    ;;
  --prepare-approved-live)
    [[ $# -eq 2 ]] || usage
    prepare_approved_live "$2"
    ;;
  --run-approved-live)
    [[ $# -eq 4 && $3 == --grant ]] || usage
    run_approved_live "$2" "$4"
    ;;
  --live-integrated-once)
    guard_refusal DIRECT_UNPREPARED_LIVE_PATH_REJECTED
    ;;
  *) usage ;;
esac
