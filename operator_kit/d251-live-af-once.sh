#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY="$(git -C "$SCRIPT_DIRECTORY/.." rev-parse --show-toplevel)"
readonly AUTHORIZATION_ARGUMENT="--i-authorize-one-d251-af-live-attempt"
readonly DRY_RUN_ARGUMENT="--offline-dry-run"
readonly D251_REPORT_DIR="/var/lib/goodix-5125-poc/d251-results"
readonly AUTHORIZATION_MARKER="/var/lib/goodix-5125-poc/d251-operator-invocation.marker"
readonly PREFLIGHT_REPORT="analysis/D251/D251_preflight_report.json"
readonly OPERATOR_STDOUT="analysis/D251/D251_operator_live_stdout.json"
readonly BACKEND_SOURCE="src/goodix5125_d233_backend.py"
readonly ENTRYPOINT_SOURCE="src/goodix5125_d235_entrypoint.py"
readonly D245_UNSEAL_PATCH="analysis/D245/D245_live_unseal.patch"
readonly D246_CONTINUATION_PATCH="analysis/D246/D246_d4_continuation.patch"
readonly D250_CONTINUATION_PATCH="analysis/D250/D250_af_continuation.patch"
readonly D251_CONTINUATION_PATCH="analysis/D251/D251_af_semantics_continuation.patch"
readonly D251_DRY_RUN_SOURCE="analysis/D251/d251_operator_dry_run.py"
readonly PREFLIGHT_SOURCE="analysis/D251/d251_preflight.py"
readonly PREFLIGHT_OBSERVABILITY_SOURCE="analysis/D251/d251_preflight_observability.py"
readonly LIVE_CRITICAL_SOURCE="analysis/D251/d251_live_critical.py"

die_pre_usb() {
    local code="$1"
    shift
    printf '%s\n' \
        'D251_PHASE=PRE_USB_FENCE' \
        'D251_RESULT=FAIL' \
        "D251_FAILURE_CLASS=$*" \
        'D251_USB_OPEN_COUNT=0' \
        'D251_AF_ATTEMPT_COUNT=0' \
        'D251_AF_SEND_COUNT=0' \
        'D251_LIVE_USB_EXECUTION=NOT_STARTED' >&2
    exit "$code"
}

die_runtime() {
    local code="$1"
    shift
    printf 'D251_PHASE=LIVE_RUNTIME\nD251_RESULT=FAIL\nD251_FAILURE_CLASS=%s\n' "$*" >&2
    exit "$code"
}

source_is_sealed() {
    grep -Fq 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' \
        "$BACKEND_SOURCE" && \
        grep -Fq 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")' \
            "$ENTRYPOINT_SOURCE"
}

verify_source_seal() {
    source_is_sealed || die_pre_usb 68 "D251_SOURCE_NOT_SEALED"
}

baseline_state() {
    local baseline_sha="$1"
    local helper_copy
    local state
    if [[ ! "$baseline_sha" =~ ^[0-9a-f]{40}$ ]]; then
        printf 'UNAPPROVED\n'
        return
    fi
    if ! git cat-file -e "${baseline_sha}^{commit}" 2>/dev/null; then
        printf 'UNAPPROVED\n'
        return
    fi
    helper_copy="$(mktemp /tmp/d251-live-critical-bootstrap.XXXXXX)" || {
        printf 'STALE\n'
        return
    }
    if ! git show "${baseline_sha}:${LIVE_CRITICAL_SOURCE}" > "$helper_copy" 2>/dev/null || \
        ! cmp -s -- "$helper_copy" "$LIVE_CRITICAL_SOURCE"; then
        rm -f -- "$helper_copy"
        printf 'STALE\n'
        return
    fi
    rm -f -- "$helper_copy"
    state="$(PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
        PYTHONDONTWRITEBYTECODE=1 python3 "$LIVE_CRITICAL_SOURCE" \
        --repository "$REPOSITORY" --baseline-state "$baseline_sha" 2>/dev/null)" || {
        printf 'STALE\n'
        return
    }
    case "$state" in
        APPROVED|STALE|UNAPPROVED) printf '%s\n' "$state" ;;
        *) printf 'STALE\n' ;;
    esac
}

live_guard_failure() {
    local argument_count="$1"
    local argument="$2"
    local effective_uid="$3"
    local sudo_uid="$4"
    local marker_state="$5"
    local approved_state="$6"
    if [[ "$argument_count" -ne 1 || "$argument" != "$AUTHORIZATION_ARGUMENT" ]]; then
        printf 'EXPLICIT_D251_SINGLE_RUN_AUTHORIZATION_REQUIRED\n'
    elif [[ "$effective_uid" -ne 0 ]]; then
        printf 'ROOT_CONTEXT_REQUIRED\n'
    elif [[ ! "$sudo_uid" =~ ^[0-9]+$ || "$sudo_uid" -eq 0 ]]; then
        printf 'NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED\n'
    elif [[ "$marker_state" != "ABSENT" ]]; then
        printf 'D251_SINGLE_USE_MARKER_ALREADY_CONSUMED\n'
    elif [[ "$approved_state" == "UNAPPROVED" ]]; then
        printf 'D251_LIVE_BASELINE_NOT_APPROVED\n'
    elif [[ "$approved_state" != "APPROVED" ]]; then
        printf 'D251_LIVE_CRITICAL_BASELINE_STALE\n'
    else
        printf 'PASS\n'
    fi
}

verify_guardrail_model_offline() {
    [[ "$(live_guard_failure 0 "" 0 1000 ABSENT APPROVED)" == \
        "EXPLICIT_D251_SINGLE_RUN_AUTHORIZATION_REQUIRED" ]]
    [[ "$(live_guard_failure 1 "--wrong" 0 1000 ABSENT APPROVED)" == \
        "EXPLICIT_D251_SINGLE_RUN_AUTHORIZATION_REQUIRED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 1000 1000 ABSENT APPROVED)" == \
        "ROOT_CONTEXT_REQUIRED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 "" ABSENT APPROVED)" == \
        "NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 0 ABSENT APPROVED)" == \
        "NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 1000 PRESENT APPROVED)" == \
        "D251_SINGLE_USE_MARKER_ALREADY_CONSUMED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 1000 ABSENT UNAPPROVED)" == \
        "D251_LIVE_BASELINE_NOT_APPROVED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 1000 ABSENT STALE)" == \
        "D251_LIVE_CRITICAL_BASELINE_STALE" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 1000 ABSENT APPROVED)" == \
        "PASS" ]]
}

verify_offline_closure() {
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$D251_DRY_RUN_SOURCE" "$DRY_RUN_ARGUMENT" >/dev/null
}

render_preflight_failure() {
    if ! PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_OBSERVABILITY_SOURCE" --report "$PREFLIGHT_REPORT" >&2; then
        printf '%s\n' \
            'D251_PHASE=PREFLIGHT' \
            'D251_RESULT=FAIL' \
            'D251_FAILURE_CLASS=PREFLIGHT_REPORT_RENDERER_FAILED' \
            'D251_USB_OPEN_COUNT=0' \
            'D251_AF_ATTEMPT_COUNT=0' \
            'D251_AF_SEND_COUNT=0' \
            'D251_LIVE_USB_EXECUTION=NOT_STARTED' >&2
    fi
}

[[ "$SCRIPT_DIRECTORY" == "$REPOSITORY/operator_kit" ]] || \
    die_pre_usb 65 "LAUNCHER_OUTSIDE_RESOLVED_REPOSITORY"
cd -- "$REPOSITORY"

if [[ "${1-}" == "$DRY_RUN_ARGUMENT" && "$#" -eq 1 ]]; then
    verify_source_seal
    verify_guardrail_model_offline
    verify_offline_closure
    printf '%s\n' \
        'D251_PHASE=EXECUTABLE_CLOSURE' \
        'D251_RESULT=PASS' \
        'D251_FAILURE_CLASS=none' \
        'D251_GUARDRAIL_MATRIX=PASS' \
        'D251_PREFLIGHT_NAMESPACE=D251_ONLY' \
        'D251_LIVE_CRITICAL_STALE_DETECTION=PASS_ALL_FILES' \
        'D251_TERMINAL_BOUNDARY=STOP_AFTER_AF' \
        'D251_SECOND_AF=UNREACHABLE' \
        'D251_FDT_32_20_D2=UNREACHABLE' \
        'D251_CLEANUP_RESEAL=PASS_BYTE_EXACT' \
        'D251_LIVE_CAPABILITY=HARD_GATED' \
        'D251_LIVE_EXECUTION=NOT_PERFORMED' \
        'D251_LIVE_BASELINE_APPROVAL=PENDING_AI_PM_REVIEW' \
        'D251_USB_OPEN_COUNT=0' \
        'D251_TLS_HANDSHAKE_COUNT=0' \
        'D251_D4_SEND_COUNT=0' \
        'D251_AF_ATTEMPT_COUNT=0' \
        'D251_AF_SEND_COUNT=0' \
        'D251_RETRY_COUNT=0' \
        'D251_PERSISTENT_WRITE_FAMILY_COUNT=0' \
        'D251_SOURCE_SEAL=ACTIVE'
    exit 0
fi

[[ "$#" -eq 1 && "${1-}" == "$AUTHORIZATION_ARGUMENT" ]] || \
    die_pre_usb 64 "EXPLICIT_D251_SINGLE_RUN_AUTHORIZATION_REQUIRED"
[[ "$EUID" -eq 0 ]] || die_pre_usb 64 "ROOT_CONTEXT_REQUIRED"
[[ "${SUDO_UID-}" =~ ^[0-9]+$ && "${SUDO_UID-}" -ne 0 ]] || \
    die_pre_usb 64 "NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED"
[[ ! -e "$AUTHORIZATION_MARKER" && ! -L "$AUTHORIZATION_MARKER" ]] || \
    die_pre_usb 70 "D251_SINGLE_USE_MARKER_ALREADY_CONSUMED"

approved_baseline_sha="${D251_APPROVED_LIVE_BASELINE_SHA-}"
approved_state="$(baseline_state "$approved_baseline_sha")"
if [[ "$approved_state" == "UNAPPROVED" ]]; then
    die_pre_usb 66 "D251_LIVE_BASELINE_NOT_APPROVED"
fi
[[ "$approved_state" == "APPROVED" ]] || \
    die_pre_usb 67 "D251_LIVE_CRITICAL_BASELINE_STALE"

verify_source_seal
install -d -m 0700 -o root -g root "$D251_REPORT_DIR" || \
    die_pre_usb 69 "D251_REPORT_DIRECTORY_PREPARATION_FAILED"
if ! PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
    python3 "$PREFLIGHT_SOURCE"; then
    render_preflight_failure
    exit 69
fi
[[ ! -e "$AUTHORIZATION_MARKER" && ! -L "$AUTHORIZATION_MARKER" ]] || \
    die_pre_usb 70 "D251_SINGLE_USE_MARKER_ALREADY_CONSUMED"
[[ "$(baseline_state "$approved_baseline_sha")" == "APPROVED" ]] || \
    die_pre_usb 67 "D251_LIVE_CRITICAL_BASELINE_CHANGED_DURING_PREFLIGHT"

temporary_directory="$(mktemp -d /tmp/d251-live-af.XXXXXX)"
backup_directory="$temporary_directory/sealed-source"
mkdir -m 700 -- "$backup_directory"
cp --archive -- "$BACKEND_SOURCE" "$ENTRYPOINT_SOURCE" "$backup_directory/"
live_stdout="$temporary_directory/live-stdout.json"
source_unsealed=0
source_resealed=0
source_restore_count=0

reseal_source() {
    local restore_status=0
    if [[ "$source_unsealed" -eq 1 && "$source_resealed" -eq 0 ]]; then
        cp --archive -- "$backup_directory/$(basename "$BACKEND_SOURCE")" \
            "$BACKEND_SOURCE" || restore_status=1
        cp --archive -- "$backup_directory/$(basename "$ENTRYPOINT_SOURCE")" \
            "$ENTRYPOINT_SOURCE" || restore_status=1
        cmp -s -- "$backup_directory/$(basename "$BACKEND_SOURCE")" \
            "$BACKEND_SOURCE" || restore_status=1
        cmp -s -- "$backup_directory/$(basename "$ENTRYPOINT_SOURCE")" \
            "$ENTRYPOINT_SOURCE" || restore_status=1
        if [[ "$restore_status" -eq 0 ]]; then
            source_resealed=1
            source_restore_count=1
        fi
    fi
    return "$restore_status"
}

finish() {
    local original_status="$?"
    trap - EXIT INT TERM HUP
    reseal_source || original_status=90
    if [[ -s "$live_stdout" ]]; then
        if ! cp -- "$live_stdout" "$OPERATOR_STDOUT" || \
            ! chmod 0600 "$OPERATOR_STDOUT" || \
            ! chown "$SUDO_UID" "$OPERATOR_STDOUT"; then
            original_status=91
        fi
    fi
    rm -f -- "$live_stdout" \
        "$temporary_directory/d245.rej" \
        "$temporary_directory/d246.rej" \
        "$temporary_directory/d250.rej" \
        "$temporary_directory/d251.rej" \
        "$backup_directory/$(basename "$BACKEND_SOURCE")" \
        "$backup_directory/$(basename "$ENTRYPOINT_SOURCE")"
    rmdir -- "$backup_directory" "$temporary_directory" 2>/dev/null || true
    exit "$original_status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

source_unsealed=1
patch --batch --forward --strip=1 --no-backup-if-mismatch \
    --reject-file="$temporary_directory/d245.rej" --input="$D245_UNSEAL_PATCH"
patch --batch --forward --strip=1 --no-backup-if-mismatch \
    --reject-file="$temporary_directory/d246.rej" --input="$D246_CONTINUATION_PATCH"
patch --batch --forward --strip=1 --no-backup-if-mismatch \
    --reject-file="$temporary_directory/d250.rej" --input="$D250_CONTINUATION_PATCH"
patch --batch --forward --strip=1 --no-backup-if-mismatch \
    --reject-file="$temporary_directory/d251.rej" --input="$D251_CONTINUATION_PATCH"
grep -Fq 'D235_RESULT_SCHEMA = "d251-live-af-single-shot-result-v1"' \
    "$ENTRYPOINT_SOURCE" || die_runtime 71 "D251_CONTINUATION_VERIFICATION_FAILED"
grep -Fq 'single_use_marker=store / "d251-operator-invocation.marker"' \
    "$ENTRYPOINT_SOURCE" || die_runtime 71 "D251_NAMESPACE_UNSEAL_VERIFICATION_FAILED"
grep -Fq 'AF_TIMEOUT_MS = 500' "$BACKEND_SOURCE" || \
    die_runtime 71 "D251_AF_UNSEAL_VERIFICATION_FAILED"
if grep -Fq 'semantic_state_version_mismatch' "$BACKEND_SOURCE"; then
    die_runtime 71 "D251_AF_OVERCONSTRAINED_GATE_STILL_PRESENT"
fi
grep -Fq '"af_state_byte0"' "$BACKEND_SOURCE" || \
    die_runtime 71 "D251_AF_TELEMETRY_VERIFICATION_FAILED"
grep -Fq 'self.af_response_count = 1' "$BACKEND_SOURCE" || \
    die_runtime 71 "D251_AF_RESPONSE_COUNTER_VERIFICATION_FAILED"

set +e
PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
    python3 -m src.goodix5125_d235_entrypoint > "$live_stdout"
live_status="$?"
set -e
reseal_source || die_runtime 90 "CRITICAL_SOURCE_RESEAL_FAILURE"
[[ "$source_restore_count" -eq 1 ]] || die_runtime 90 "D251_SOURCE_RESTORE_COUNT_INVALID"
source_is_sealed || die_runtime 90 "D251_SOURCE_RESEAL_VERIFICATION_FAILED"

if [[ -s "$live_stdout" ]]; then
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); fields=(("TLS_HANDSHAKE_COMPLETED",r.get("tls_handshake_completed",False)),("D4_SEND_COUNT",r.get("d4_send_count",0)),("AF_ATTEMPT_COUNT",r.get("af_attempt_count",0)),("AF_SEND_COUNT",r.get("af_send_count",0)),("AF_RESPONSE_COUNT",r.get("af_response_count",0)),("AF_RESPONSE_CLASS",r.get("af_response_class","no_response")),("AF_STATE_BYTE0",r.get("af_state_byte0")),("AF_STATE_FLAGS",r.get("af_state_flags")),("AF_UNKNOWN_FLAG_BITS",r.get("af_unknown_flag_bits")),("AF_POV_VALID",r.get("af_pov_valid")),("AF_TLS_CONNECTED",r.get("af_tls_connected")),("AF_LOCKED",r.get("af_locked")),("AF_FAILURE_CLASS",r.get("af_failure_class","not_reached")),("STOP_AFTER_AF",r.get("D251_STOP_BOUNDARY","STOP_AFTER_AF") == "STOP_AFTER_AF"),("cleanup_count",r.get("cleanup_count",0)),("retry_count",r.get("retry_count",0)),("persistent_write_family_count",r.get("persistent_write_family_count",0))); [print("D251_"+k+"="+str(v).lower() if isinstance(v,bool) else "D251_"+k+"="+str(v)) for k,v in fields]' "$live_stdout" || true
fi
[[ "$live_status" -eq 0 ]] || \
    printf 'D251 live attempt stopped; durable report published; source resealed; no retry authorized\n' >&2
exit "$live_status"
