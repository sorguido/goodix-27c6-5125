#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY="$(git -C "$SCRIPT_DIRECTORY/.." rev-parse --show-toplevel)"
readonly AUTHORIZATION_ARGUMENT="--i-authorize-one-d246-d4-live-attempt"
readonly DRY_RUN_ARGUMENT="--offline-dry-run"
readonly D246_REPORT_DIR="/var/lib/goodix-5125-poc/d246-results"
readonly AUTHORIZATION_MARKER="/var/lib/goodix-5125-poc/d246-operator-invocation.marker"
readonly PREFLIGHT_REPORT="analysis/D245/D245_preflight_report.json"
readonly OPERATOR_STDOUT="analysis/D246/D246_operator_live_stdout.json"
readonly BACKEND_SOURCE="src/goodix5125_d233_backend.py"
readonly ENTRYPOINT_SOURCE="src/goodix5125_d235_entrypoint.py"
readonly D245_UNSEAL_PATCH="analysis/D245/D245_live_unseal.patch"
readonly D246_CONTINUATION_PATCH="analysis/D246/D246_d4_continuation.patch"
readonly D246_DRY_RUN_SOURCE="analysis/D246/d246_operator_dry_run.py"
readonly D246_LIVE_TEST_SOURCE="analysis/D246/d246_live_enablement_offline.py"
readonly PREFLIGHT_SOURCE="analysis/D245/d245_preflight.py"
readonly PREFLIGHT_OBSERVABILITY_SOURCE="analysis/D245/d245_preflight_observability.py"

readonly -a LIVE_CRITICAL_FILES=(
    "operator_kit/d246-live-d4-once.sh"
    "analysis/D245/D245_live_unseal.patch"
    "analysis/D246/D246_d4_continuation.patch"
    "src/goodix5125_d232_offline.py"
    "src/goodix5125_d233_backend.py"
    "src/goodix5125_d235_entrypoint.py"
    "analysis/D241/d241_preflight.py"
    "analysis/D245/d245_preflight.py"
    "analysis/D245/d245_preflight_observability.py"
)

die() {
    local code="$1"
    shift
    printf 'D246_PHASE=LAUNCHER\nD246_RESULT=FAIL\nD246_FAILURE_CLASS=%s\n' "$*" >&2
    exit "$code"
}

verify_source_seal() {
    grep -Fq 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' \
        "$BACKEND_SOURCE" || die 68 "D246_BACKEND_NOT_SOURCE_SEALED"
    grep -Fq 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")' \
        "$ENTRYPOINT_SOURCE" || die 68 "D246_ENTRYPOINT_NOT_SOURCE_SEALED"
}

baseline_state() {
    local baseline_sha="$1"
    local path
    if [[ ! "$baseline_sha" =~ ^[0-9a-f]{40}$ ]]; then
        printf 'UNAPPROVED\n'
        return
    fi
    if ! git cat-file -e "${baseline_sha}^{commit}" 2>/dev/null; then
        printf 'UNAPPROVED\n'
        return
    fi
    for path in "${LIVE_CRITICAL_FILES[@]}"; do
        if ! git cat-file -e "${baseline_sha}:${path}" 2>/dev/null; then
            printf 'STALE\n'
            return
        fi
    done
    if ! git diff --quiet "$baseline_sha" -- "${LIVE_CRITICAL_FILES[@]}"; then
        printf 'STALE\n'
        return
    fi
    printf 'APPROVED\n'
}

live_guard_failure() {
    local argument_count="$1"
    local argument="$2"
    local effective_uid="$3"
    local sudo_uid="$4"
    local marker_state="$5"
    local approved_state="$6"
    if [[ "$argument_count" -ne 1 || "$argument" != "$AUTHORIZATION_ARGUMENT" ]]; then
        printf 'EXPLICIT_D246_SINGLE_RUN_AUTHORIZATION_REQUIRED\n'
    elif [[ "$effective_uid" -ne 0 ]]; then
        printf 'ROOT_CONTEXT_REQUIRED\n'
    elif [[ ! "$sudo_uid" =~ ^[0-9]+$ || "$sudo_uid" -eq 0 ]]; then
        printf 'NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED\n'
    elif [[ "$marker_state" != "ABSENT" ]]; then
        printf 'D246_SINGLE_USE_MARKER_ALREADY_CONSUMED\n'
    elif [[ "$approved_state" == "UNAPPROVED" ]]; then
        printf 'D246_LIVE_BASELINE_NOT_APPROVED\n'
    elif [[ "$approved_state" != "APPROVED" ]]; then
        printf 'D246_LIVE_CRITICAL_BASELINE_STALE\n'
    else
        printf 'PASS\n'
    fi
}

verify_guardrail_model_offline() {
    [[ "$(live_guard_failure 0 "" 0 1000 ABSENT APPROVED)" == \
        "EXPLICIT_D246_SINGLE_RUN_AUTHORIZATION_REQUIRED" ]]
    [[ "$(live_guard_failure 1 "--wrong" 0 1000 ABSENT APPROVED)" == \
        "EXPLICIT_D246_SINGLE_RUN_AUTHORIZATION_REQUIRED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 1000 1000 ABSENT APPROVED)" == \
        "ROOT_CONTEXT_REQUIRED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 "" ABSENT APPROVED)" == \
        "NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 0 ABSENT APPROVED)" == \
        "NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 1000 PRESENT APPROVED)" == \
        "D246_SINGLE_USE_MARKER_ALREADY_CONSUMED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 1000 ABSENT UNAPPROVED)" == \
        "D246_LIVE_BASELINE_NOT_APPROVED" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 1000 ABSENT STALE)" == \
        "D246_LIVE_CRITICAL_BASELINE_STALE" ]]
    [[ "$(live_guard_failure 1 "$AUTHORIZATION_ARGUMENT" 0 1000 ABSENT APPROVED)" == \
        "PASS" ]]
}

verify_offline_closure() {
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$D246_DRY_RUN_SOURCE" >/dev/null
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$D246_LIVE_TEST_SOURCE" >/dev/null
}

render_preflight_failure() {
    if ! PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_OBSERVABILITY_SOURCE" --report "$PREFLIGHT_REPORT" >&2; then
        printf '%s\n' \
            'D246_PHASE=PREFLIGHT' \
            'D246_RESULT=FAIL' \
            'D246_FAILURE_CLASS=PREFLIGHT_REPORT_RENDERER_FAILED' \
            'D246_USB_OPEN_COUNT=0' \
            'D246_GOODIX_COMMAND_COUNT=0' \
            'D246_LIVE_USB_EXECUTION=NOT_STARTED' >&2
    fi
}

[[ "$SCRIPT_DIRECTORY" == "$REPOSITORY/operator_kit" ]] || \
    die 65 "LAUNCHER_OUTSIDE_RESOLVED_REPOSITORY"
cd -- "$REPOSITORY"

if [[ "${1-}" == "$DRY_RUN_ARGUMENT" && "$#" -eq 1 ]]; then
    verify_source_seal
    verify_guardrail_model_offline
    verify_offline_closure
    printf '%s\n' \
        'D246_PHASE=EXECUTABLE_CLOSURE' \
        'D246_RESULT=PASS' \
        'D246_FAILURE_CLASS=none' \
        'D246_GUARDRAIL_MATRIX=PASS' \
        'D246_RUNTIME_DISCONNECT_REENUMERATION=PASS_TERMINAL_NO_RETRY' \
        'D246_SECOND_D4=UNREACHABLE' \
        'D246_AF=UNREACHABLE' \
        'D246_LIVE_USB_EXECUTION=NOT_PERFORMED' \
        'D246_SOURCE_SEAL=ACTIVE' \
        'D246_LIVE_BASELINE_APPROVAL=PENDING_AI_PM_REVIEW'
    exit 0
fi

marker_state="ABSENT"
[[ ! -e "$AUTHORIZATION_MARKER" && ! -L "$AUTHORIZATION_MARKER" ]] || marker_state="PRESENT"
approved_baseline_sha="${D246_APPROVED_LIVE_BASELINE_SHA-}"
approved_state="$(baseline_state "$approved_baseline_sha")"
guard_failure="$(live_guard_failure "$#" "${1-}" "$EUID" "${SUDO_UID-}" "$marker_state" "$approved_state")"
[[ "$guard_failure" == "PASS" ]] || die 64 "$guard_failure"

verify_source_seal
[[ ! -e "$AUTHORIZATION_MARKER" && ! -L "$AUTHORIZATION_MARKER" ]] || \
    die 70 "D246_SINGLE_USE_MARKER_ALREADY_CONSUMED"

install -d -m 0700 -o root -g root "$D246_REPORT_DIR" || \
    die 69 "D246_REPORT_DIRECTORY_PREPARATION_FAILED"
if ! PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
    python3 "$PREFLIGHT_SOURCE"; then
    render_preflight_failure
    exit 69
fi
[[ ! -e "$AUTHORIZATION_MARKER" && ! -L "$AUTHORIZATION_MARKER" ]] || \
    die 70 "D246_SINGLE_USE_MARKER_ALREADY_CONSUMED"

temporary_directory="$(mktemp -d /tmp/d246-live-d4.XXXXXX)"
backup_directory="$temporary_directory/sealed-source"
mkdir -m 700 -- "$backup_directory"
cp --archive -- "$BACKEND_SOURCE" "$ENTRYPOINT_SOURCE" "$backup_directory/"
live_stdout="$temporary_directory/live-stdout.json"
source_unsealed=0
source_resealed=0

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
        "$temporary_directory/d245.rej" "$temporary_directory/d246.rej" \
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
grep -Fq 'D235_RESULT_SCHEMA = "d246-live-d4-single-shot-result-v1"' \
    "$ENTRYPOINT_SOURCE" || die 71 "D246_CONTINUATION_VERIFICATION_FAILED"
grep -Fq 'single_use_marker=store / "d246-operator-invocation.marker"' \
    "$ENTRYPOINT_SOURCE" || die 71 "D246_NAMESPACE_UNSEAL_VERIFICATION_FAILED"
grep -Fq 'D4_CANONICAL_REQUEST = bytes.fromhex("a00600a6d403000000d3")' \
    "$BACKEND_SOURCE" || die 71 "D246_D4_UNSEAL_VERIFICATION_FAILED"

set +e
PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
    python3 -m src.goodix5125_d235_entrypoint > "$live_stdout"
live_status="$?"
set -e
reseal_source || die 90 "CRITICAL_SOURCE_RESEAL_FAILURE"
verify_source_seal

if [[ -s "$live_stdout" ]]; then
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); fields=(("TLS_HANDSHAKE_COMPLETED",r.get("tls_handshake_completed",False)),("D4_SEND_COUNT",r.get("d4_send_count",0)),("D4_ACK_STATUS",r.get("d4_ack_status","none")),("D4_COMPLETED",r.get("d4_completed",False)),("D4_FAILURE_CLASS",r.get("d4_failure_class","not_reached")),("STOP_AFTER_D4",r.get("D246_STOP_BOUNDARY","STOP_AFTER_D4") == "STOP_AFTER_D4"),("cleanup_count",r.get("cleanup_count",0)),("retry_count",r.get("retry_count",0)),("persistent_write_family_count",r.get("persistent_write_family_count",0))); [print("D246_"+k+"="+str(v).lower() if isinstance(v,bool) else "D246_"+k+"="+str(v)) for k,v in fields]' "$live_stdout" || true
fi
[[ "$live_status" -eq 0 ]] || \
    printf 'D246 live attempt stopped; durable report published; source resealed; no retry authorized\n' >&2
exit "$live_status"
