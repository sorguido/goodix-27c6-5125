#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -uo pipefail

usage () {
  echo "Uso: $0 <experiment-id> --offline-test|--operator-run [--capture-root DIRECTORY]" >&2
  exit 2
}

[[ $# -ge 2 ]] || usage
experiment_id=$1
mode=$2
shift 2
capture_override=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --capture-root) [[ $# -ge 2 ]] || usage; capture_override=$2; shift 2 ;;
    *) usage ;;
  esac
done
[[ $mode == --offline-test || $mode == --operator-run ]] || usage

LP_HARNESS_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || exit 2
LP_GIT_ROOT=$(git -C "$LP_HARNESS_DIR" rev-parse --show-toplevel 2>/dev/null) || {
  echo LIVE_PROBE_ERROR=NOT_IN_GIT_REPOSITORY >&2; exit 2;
}
if [[ -n ${LIVE_PROBE_TEST_EXPERIMENT_DIR:-} ]]; then
  [[ $mode == --offline-test ]] || { echo LIVE_PROBE_ERROR=TEST_OVERRIDE_FORBIDDEN_LIVE >&2; exit 2; }
  LP_EXPERIMENT_DIR=$LIVE_PROBE_TEST_EXPERIMENT_DIR
else
  LP_EXPERIMENT_DIR=$LP_HARNESS_DIR/experiments/$experiment_id
fi
[[ -f $LP_EXPERIMENT_DIR/experiment.conf ]] || { echo LIVE_PROBE_ERROR=EXPERIMENT_NOT_FOUND >&2; exit 2; }

# shellcheck source=safety.sh
source "$LP_HARNESS_DIR/safety.sh"
# shellcheck source=capture.sh
source "$LP_HARNESS_DIR/capture.sh"
# experiment.conf is trusted, reviewed repository data; it must only assign variables.
# shellcheck disable=SC1090
source "$LP_EXPERIMENT_DIR/experiment.conf"
[[ $EXPERIMENT_ID == "$experiment_id" ]] || { echo LIVE_PROBE_ERROR=EXPERIMENT_ID_MISMATCH >&2; exit 2; }
lp_validate_config || exit 2

if [[ $mode == --operator-run ]]; then
  [[ $LIVE_CAPABLE == true ]] || { echo LIVE_PROBE_ERROR=EXPERIMENT_NOT_LIVE_CAPABLE >&2; exit 2; }
  lp_git_gate || exit 2
  lp_runtime_gate || exit 2
  LP_CAPTURE_ROOT=${capture_override:-$LP_GIT_ROOT/captures/live_probe}
else
  [[ $OFFLINE_TEST_CAPABLE == true ]] || { echo LIVE_PROBE_ERROR=EXPERIMENT_NOT_OFFLINE_TEST_CAPABLE >&2; exit 2; }
  LP_CAPTURE_ROOT=${capture_override:-${TMPDIR:-/tmp}/goodix-live-probe-offline}
fi
mkdir -p "$LP_CAPTURE_ROOT" || exit 2
lp_make_capture || exit 2
LP_WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/goodix-live-probe.XXXXXX") || exit 2
LP_TELEMETRY_FILE=$LP_WORK_DIR/telemetry.env
LP_INTERRUPTED=false
LP_CLEANUP_DONE=false
LP_JOURNAL_CURSOR=
LP_JOURNAL_CURSOR_VALID=false
LP_JOURNAL_COLLECTION=NOT_REQUESTED
LP_PAYLOAD_STARTED=false
export LIVE_PROBE_WORK_DIR=$LP_WORK_DIR LIVE_PROBE_CAPTURE_DIR=$LP_CAPTURE_DIR
export LIVE_PROBE_TELEMETRY_FILE=$LP_TELEMETRY_FILE LIVE_PROBE_MODE=${mode#--}

finish_cleanup () {
  local rc=0
  [[ $LP_CLEANUP_DONE == false ]] || return 0
  LP_CLEANUP_DONE=true
  if [[ -n ${CLEANUP:-} ]]; then
    LIVE_PROBE_WORK_DIR=$LP_WORK_DIR LIVE_PROBE_CAPTURE_DIR=$LP_CAPTURE_DIR \
      "$LP_EXPERIMENT_DIR/$CLEANUP" --phase cleanup >"$LP_CAPTURE_DIR/cleanup.log" 2>&1 || rc=$?
  else
    echo LIVE_PROBE_CLEANUP=NOT_REQUIRED >"$LP_CAPTURE_DIR/cleanup.log"
  fi
  rm -rf -- "$LP_WORK_DIR"
  return "$rc"
}
trap 'LP_INTERRUPTED=true; echo LIVE_PROBE_SIGNAL_RECEIVED=true >&2' HUP INT TERM
trap 'finish_cleanup || true' EXIT

baseline=$(git -C "$LP_GIT_ROOT" rev-parse HEAD)
{
  echo "LIVE_PROBE_EXPERIMENT_ID=$EXPERIMENT_ID"
  echo "LIVE_PROBE_MODE=${mode#--}"
  echo "LIVE_PROBE_BASELINE=$baseline"
  echo "LIVE_PROBE_ACTION=$ACTION"
  echo "LIVE_PROBE_MAX_ACTIONS=$MAX_ACTIONS"
  echo "LIVE_PROBE_MAX_CONTACTS=$MAX_CONTACTS"
  echo "LIVE_PROBE_MAX_RETRIES=$MAX_RETRIES"
  echo "LIVE_PROBE_TIMEOUT_SECONDS=$TIMEOUT_SECONDS"
} >"$LP_CAPTURE_DIR/context.env"

pre_rc=0 cursor_rc=0 payload_rc=125 sanitizer_rc=0 tee_rc=0 journal_rc=0
cleanup_rc=0 post_rc=0 common_rc=1 custom_rc=0
lp_run_hook "${PRE_AUDIT:-}" pre "$LP_CAPTURE_DIR/pre-audit.log" || pre_rc=$?
[[ $pre_rc -ne 0 ]] || lp_capture_cursor || cursor_rc=$?
if [[ $pre_rc -eq 0 && $cursor_rc -eq 0 && $mode == --operator-run ]]; then
  lp_confirm_operator || pre_rc=$?
fi

if [[ $pre_rc -eq 0 && $cursor_rc -eq 0 ]]; then
  LP_PAYLOAD_STARTED=true
  payload_command=("$LP_EXPERIMENT_DIR/$PAYLOAD" --max-actions "$MAX_ACTIONS" \
    --max-contacts "$MAX_CONTACTS" --max-retries "$MAX_RETRIES" \
    --timeout-seconds "$TIMEOUT_SECONDS")
  set +e
  if [[ -n ${SANITIZER:-} ]]; then
    timeout --signal=TERM --kill-after=5s "${TIMEOUT_SECONDS}s" \
      "${payload_command[@]}" 2>&1 | lp_signal_safe_filter "$LP_EXPERIMENT_DIR/$SANITIZER" |
      lp_signal_safe_tee "$LP_CAPTURE_DIR/payload.log"
    pipeline_status=("${PIPESTATUS[@]}")
    payload_rc=${pipeline_status[0]}; sanitizer_rc=${pipeline_status[1]}; tee_rc=${pipeline_status[2]}
  else
    timeout --signal=TERM --kill-after=5s "${TIMEOUT_SECONDS}s" \
      "${payload_command[@]}" 2>&1 | lp_signal_safe_tee "$LP_CAPTURE_DIR/payload.log"
    pipeline_status=("${PIPESTATUS[@]}")
    payload_rc=${pipeline_status[0]}; tee_rc=${pipeline_status[1]}
  fi
  set +e
fi

if [[ -f $LP_TELEMETRY_FILE ]]; then
  cp "$LP_TELEMETRY_FILE" "$LP_CAPTURE_DIR/telemetry.env" || true
fi
finish_cleanup || cleanup_rc=$?
lp_collect_journal || journal_rc=$?
lp_run_hook "${POST_AUDIT:-}" post "$LP_CAPTURE_DIR/post-audit.log" || post_rc=$?

telemetry=$LP_CAPTURE_DIR/telemetry.env
if [[ -f $telemetry ]]; then
  common_rc=0
  "$LP_HARNESS_DIR/classify_common.sh" "$telemetry" "$MAX_ACTIONS" "$MAX_CONTACTS" \
    "$MAX_RETRIES" "$EXPECTED_TELEMETRY" >"$LP_CAPTURE_DIR/common-classification.env" || common_rc=$?
fi
if [[ -n ${CLASSIFIER:-} ]]; then
  "$LP_EXPERIMENT_DIR/$CLASSIFIER" "$LP_CAPTURE_DIR" >"$LP_CAPTURE_DIR/payload-classification.env" || custom_rc=$?
fi

accepted=false
for accepted_rc in ${PAYLOAD_ACCEPTED_RETURN_CODES:-0}; do
  [[ $payload_rc -ne $accepted_rc ]] || accepted=true
done
result=PASS
primary_failure=NONE
if [[ $LP_INTERRUPTED == true ]]; then result=INTERRUPTED; primary_failure=SIGNAL
elif [[ $pre_rc -ne 0 ]]; then result=FAIL_PRE_AUDIT; primary_failure=PRE_AUDIT
elif [[ $cursor_rc -ne 0 ]]; then result=FAIL_JOURNAL_CURSOR; primary_failure=JOURNAL_CURSOR_ACQUISITION
elif [[ $payload_rc -eq 124 || $payload_rc -eq 137 ]]; then result=FAIL_TIMEOUT; primary_failure=PAYLOAD_TIMEOUT
elif [[ $accepted != true ]]; then result=FAIL_PAYLOAD; primary_failure=PAYLOAD
elif [[ $sanitizer_rc -ne 0 || $tee_rc -ne 0 ]]; then result=FAIL_CAPTURE_PIPELINE; primary_failure=CAPTURE_PIPELINE
elif [[ $cleanup_rc -ne 0 ]]; then result=FAIL_CLEANUP; primary_failure=CLEANUP
elif [[ $journal_rc -ne 0 ]]; then result=FAIL_JOURNAL; primary_failure=JOURNAL_COLLECTION
elif [[ $post_rc -ne 0 ]]; then result=FAIL_POST_AUDIT; primary_failure=POST_AUDIT
elif [[ $common_rc -ne 0 ]]; then result=FAIL_COMMON_CLASSIFICATION; primary_failure=COMMON_CLASSIFICATION
elif [[ $custom_rc -ne 0 ]]; then result=FAIL_PAYLOAD_CLASSIFICATION; primary_failure=PAYLOAD_CLASSIFICATION
fi

{
  echo "LIVE_PROBE_RESULT=$result"
  echo "LIVE_PROBE_EXPERIMENT_ID=$EXPERIMENT_ID"
  echo "LIVE_PROBE_BASELINE=$baseline"
  echo "LIVE_PROBE_PRIMARY_FAILURE=$primary_failure"
  echo "LIVE_PROBE_PRE_AUDIT_RETURN_CODE=$pre_rc"
  echo "LIVE_PROBE_JOURNAL_CURSOR_RETURN_CODE=$cursor_rc"
  echo "LIVE_PROBE_PAYLOAD_STARTED=$LP_PAYLOAD_STARTED"
  echo "LIVE_PROBE_PAYLOAD_RETURN_CODE=$payload_rc"
  echo "LIVE_PROBE_SANITIZER_RETURN_CODE=$sanitizer_rc"
  echo "LIVE_PROBE_CAPTURE_TEE_RETURN_CODE=$tee_rc"
  echo "LIVE_PROBE_CLEANUP_RETURN_CODE=$cleanup_rc"
  echo "LIVE_PROBE_JOURNAL_RETURN_CODE=$journal_rc"
  echo "LIVE_PROBE_JOURNAL_COLLECTION=$LP_JOURNAL_COLLECTION"
  echo "LIVE_PROBE_POST_AUDIT_RETURN_CODE=$post_rc"
  echo "LIVE_PROBE_COMMON_CLASSIFIER_RETURN_CODE=$common_rc"
  echo "LIVE_PROBE_PAYLOAD_CLASSIFIER_RETURN_CODE=$custom_rc"
  echo "LIVE_PROBE_OPERATOR_INTERRUPTED=$LP_INTERRUPTED"
  echo "LIVE_PROBE_AUTOMATIC_RETRY_COUNT=0"
  echo "LIVE_PROBE_INVOCATION_COUNT=1"
} >"$LP_CAPTURE_DIR/summary.env"
lp_finalize_hashes
echo "LIVE_PROBE_CAPTURE=$LP_CAPTURE_DIR"
echo "LIVE_PROBE_RESULT=$result"
trap - EXIT HUP INT TERM
[[ $result == PASS ]]
