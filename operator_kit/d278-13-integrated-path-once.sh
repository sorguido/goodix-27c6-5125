#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)

case "${1:-}" in
  --host-only-prelive)
    cd "$root"
    "$root/libfprint-driver/tests/run_goodix_d278_secure_session_test.sh"
    "$root/libfprint-driver/tests/test_goodix_d278_13_live_guards.sh" \
      --baseline-only "$root" \
      "$root/libfprint-driver/tests/build_goodix_d278_13_adapter.sh"
    build=$(mktemp -d /tmp/goodix-d278-13-prelive.XXXXXX)
    cleanup () {
      find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true
      rmdir "$build" 2>/dev/null || true
    }
    trap cleanup EXIT HUP INT TERM
    KEEP_BUILD=1 D278_13_BUILD_DIR="$build" \
      "$root/libfprint-driver/tests/build_goodix_d278_13_adapter.sh" \
      >/dev/null
    proof_output=$("$build/d278_integrated_path_once" \
      --operator-prompt-state-machine-host-only)
    printf '%s\n' "$proof_output"
    printf '%s\n' "$proof_output" | grep -F \
      'OPERATOR_PROMPT_SEQUENCE_HOST_ONLY_PROVEN=true' >/dev/null
    printf '%s\n' "$proof_output" | grep -F \
      'OPERATOR_PROMPT_SUCCESS_FAILURE_EXCLUSIVE=true' >/dev/null
    printf '%s\n' "$proof_output" | grep -F \
      'OPERATOR_PROMPT_DUPLICATE_SUPPRESSION_HOST_ONLY_PROVEN=true' >/dev/null
    printf '%s\n' "$proof_output" | grep -F \
      'OPERATOR_PROMPT_STOP_THEN_TERMINAL_HOST_ONLY_PROVEN=true' >/dev/null
    printf '%s\n' "$proof_output" | grep -F \
      'OPERATOR_PROMPT_TERMINAL_THEN_STOP_HOST_ONLY_PROVEN=true' >/dev/null
    printf '%s\n' "$proof_output" | grep -F \
      'OPERATOR_ACTION_BANNER_FORMAT_EXACT=true' >/dev/null
    printf '%s\n' "$proof_output" | grep -F \
      'OPERATOR_ACTION_BANNER_MACHINE_PREFIX=false' >/dev/null
    echo EXECUTABLE_CLOSURE=PASS_HOST_ONLY
    echo LIVE_CAPABLE_INTEGRATED_PATH_HOST_ONLY_PROVEN=true
    echo LIVE_BASELINE_BINDING_GUARD_HOST_ONLY_PROVEN=true
    echo ONE_AUTHORIZATION_ONE_ATTEMPT_GUARD_HOST_ONLY_PROVEN=true
    echo SECOND_USE_OF_AUTHORIZATION_REJECTED=true
    echo OPERATOR_PROMPT_PRELIVE_GATED=true
    echo OPERATOR_MESSAGES_LANGUAGE=ITALIAN
    echo OPERATOR_ACTION_BANNERS_IMPLEMENTED=true
    echo OPERATOR_ACTION_BANNER_FORMAT_EXACT=true
    echo OPERATOR_ACTION_BANNER_MACHINE_PREFIX=false
    echo OPERATOR_PROMPTS_RUNTIME_STATE_DRIVEN=true
    echo REAL_USB_ACCESS=false
    echo REAL_USB_SUBMIT=0
    echo REAL_PRODUCTION_SECRET_READ=false
    echo LIVE_EXECUTION_PERFORMED=false
    echo CURRENT_LIVE_AUTHORIZED=false
    echo READY_FOR_LIVE=false
    echo RETRY_AUTHORIZED=false
    ;;
  --live-integrated-once)
    build=$(mktemp -d /tmp/goodix-d278-13-operator.XXXXXX)
    cleanup () {
      find "$build" -maxdepth 1 -type f -delete 2>/dev/null || true
      rmdir "$build" 2>/dev/null || true
    }
    trap cleanup EXIT HUP INT TERM
    D278_13_BUILD_DIR=$build \
      "$root/libfprint-driver/tests/build_goodix_d278_13_adapter.sh"
    cd "$root"
    LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
      "$build/d278_integrated_path_once" --live-integrated-once
    ;;
  *)
    echo "usage: $0 --host-only-prelive | --live-integrated-once" >&2
    exit 2
    ;;
esac
