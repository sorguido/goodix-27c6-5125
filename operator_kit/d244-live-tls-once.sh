#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly EXPECTED_REPOSITORY="$(git -C "$(dirname -- "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)"
readonly AUTHORIZATION_ARGUMENT="--i-confirm-complete-shutdown-power-on-and-authorize-one-d244-live-tls-attempt"
readonly DRY_RUN_ARGUMENT="--offline-dry-run"
readonly PREFLIGHT_FAILURE_FIXTURE_ARGUMENT="--offline-render-preflight-failure"
readonly D244_REPORT_DIR="/var/lib/goodix-5125-poc/d244-results"
readonly AUTHORIZATION_MARKER="/var/lib/goodix-5125-poc/d244-operator-invocation.marker"
readonly PREFLIGHT_REPORT="analysis/D244/D244_preflight_report.json"
readonly CLOSURE_REPORT="analysis/D244/D244_executable_closure_report.json"
readonly OPERATOR_STDOUT="analysis/D244/D244_operator_live_stdout.json"
readonly CORE_SOURCE="src/goodix5125_d232_offline.py"
readonly BACKEND_SOURCE="src/goodix5125_d233_backend.py"
readonly ENTRYPOINT_SOURCE="src/goodix5125_d235_entrypoint.py"
readonly DEPENDENCY_GATE_SOURCE="analysis/D244/d244_dependency_gate.py"
readonly FRESH_STATE_SOURCE="analysis/D244/d244_fresh_state.py"
readonly BOOT_BASELINE="analysis/D244/D244_d243_boot_baseline.json"
readonly PREFLIGHT_OBSERVABILITY_SOURCE="analysis/D244/d244_preflight_observability.py"
readonly PREFLIGHT_SOURCE="analysis/D244/d244_preflight.py"
readonly DRY_RUN_SOURCE="analysis/D244/d244_operator_dry_run.py"
readonly DIFFERENTIAL="analysis/D244/D244_d241_d242_d243_pre_e4_differential.csv"
readonly D242_LIVE_REPORT="analysis/D242/D242_operator_live_stdout.json"
readonly D243_LIVE_REPORT="analysis/D243/D243_operator_live_stdout.json"
readonly D241_PREFLIGHT_SOURCE="analysis/D241/d241_preflight.py"
readonly D241_DRY_RUN_SOURCE="analysis/D241/d241_operator_dry_run.py"
readonly UNSEAL_PATCH="analysis/D244/D244_live_unseal.patch"
readonly EXPECTED_CORE_SHA256="2875a0c4f3b166906d30c4648f0d965e8b18614299be46a7a24fb1d6a9079726"
readonly EXPECTED_BACKEND_SHA256="e537f33d47d49d47b0fc451c80b08fbafdc185e884d519cb603e22baf458c982"
readonly EXPECTED_ENTRYPOINT_SHA256="d87b11d0f2de608f05c232fa83d4e03ce4d248fe37839808f42f6ea577143b69"
readonly EXPECTED_DEPENDENCY_GATE_SHA256="29ba857dccda9b6cb90b8759383b15e49d24986c9e35f121b5a5ffdb1f32ae09"
readonly EXPECTED_FRESH_STATE_SHA256="87b9c449a6c328852c146215e997c1c974ff0aa401c3b32761881917ed34ce52"
readonly EXPECTED_BOOT_BASELINE_SHA256="fc1efcf379d41dcb9282d29bbd1659dea29bb1c71a85d1471ff3a74a2e86c850"
readonly EXPECTED_PREFLIGHT_OBSERVABILITY_SHA256="730d4b6054afc7a8e8bea8d296d4269db60040c0512b6daddc722067c11ba1c0"
readonly EXPECTED_PREFLIGHT_SHA256="009a2f0f9a72d8db5787d194cdce30c0710b63d21fd534f07d7e1c961e138717"
readonly EXPECTED_DRY_RUN_SHA256="881986b63364776b9edbc17cd78c8ad189ab0715382b4e78b838b1a6aacb9d8a"
readonly EXPECTED_DIFFERENTIAL_SHA256="5bc7df8a8e9237b6cfaac58a3f0ef1ea3cbaa1948c681f2ee970832f75cd4390"
readonly EXPECTED_D242_LIVE_REPORT_SHA256="1d9c2c736a2b8939855a184e350ea2ecaa914921536ae2a2d616130a166eb7e7"
readonly EXPECTED_D243_LIVE_REPORT_SHA256="a82c43f4aba5c6f9dcfe072eee7b8b6ab0edc7f621961ea6a322dfe6ac45aa23"
readonly EXPECTED_D241_PREFLIGHT_SHA256="6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7"
readonly EXPECTED_D241_DRY_RUN_SHA256="0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f"
readonly EXPECTED_UNSEAL_SHA256="b1b82174abf90da9b4fe45f2239a39e987f306aea8fc538079ac39bc4a2fecb7"

die() {
    local code="$1"
    shift
    printf 'D244_PHASE=LAUNCHER\nD244_RESULT=FAIL\nD244_FAILURE_CLASS=%s\n' "$*" >&2
    exit "$code"
}

sha256_matches() {
    local path="$1"
    local expected="$2"
    [[ "$(sha256sum -- "$path" | awk '{print $1}')" == "$expected" ]]
}

verify_artifacts_and_seals() {
    sha256_matches "$CORE_SOURCE" "$EXPECTED_CORE_SHA256" || die 68 "D244_CORE_PROTOCOL_HASH_MISMATCH"
    sha256_matches "$BACKEND_SOURCE" "$EXPECTED_BACKEND_SHA256" || die 68 "D244_SEALED_BACKEND_HASH_MISMATCH"
    sha256_matches "$ENTRYPOINT_SOURCE" "$EXPECTED_ENTRYPOINT_SHA256" || die 68 "D244_SEALED_ENTRYPOINT_HASH_MISMATCH"
    sha256_matches "$DEPENDENCY_GATE_SOURCE" "$EXPECTED_DEPENDENCY_GATE_SHA256" || die 68 "D244_DEPENDENCY_GATE_HASH_MISMATCH"
    sha256_matches "$FRESH_STATE_SOURCE" "$EXPECTED_FRESH_STATE_SHA256" || die 68 "D244_FRESH_STATE_SOURCE_HASH_MISMATCH"
    sha256_matches "$BOOT_BASELINE" "$EXPECTED_BOOT_BASELINE_SHA256" || die 68 "D244_BOOT_BASELINE_HASH_MISMATCH"
    sha256_matches "$PREFLIGHT_OBSERVABILITY_SOURCE" "$EXPECTED_PREFLIGHT_OBSERVABILITY_SHA256" || die 68 "D244_PREFLIGHT_OBSERVABILITY_HASH_MISMATCH"
    sha256_matches "$PREFLIGHT_SOURCE" "$EXPECTED_PREFLIGHT_SHA256" || die 68 "D244_PREFLIGHT_HASH_MISMATCH"
    sha256_matches "$DRY_RUN_SOURCE" "$EXPECTED_DRY_RUN_SHA256" || die 68 "D244_CLOSURE_RUNNER_HASH_MISMATCH"
    sha256_matches "$DIFFERENTIAL" "$EXPECTED_DIFFERENTIAL_SHA256" || die 68 "D244_DIFFERENTIAL_HASH_MISMATCH"
    sha256_matches "$D242_LIVE_REPORT" "$EXPECTED_D242_LIVE_REPORT_SHA256" || die 68 "D244_D242_LIVE_REPORT_HASH_MISMATCH"
    sha256_matches "$D243_LIVE_REPORT" "$EXPECTED_D243_LIVE_REPORT_SHA256" || die 68 "D244_D243_LIVE_REPORT_HASH_MISMATCH"
    sha256_matches "$D241_PREFLIGHT_SOURCE" "$EXPECTED_D241_PREFLIGHT_SHA256" || die 68 "D244_D241_PREFLIGHT_DEPENDENCY_HASH_MISMATCH"
    sha256_matches "$D241_DRY_RUN_SOURCE" "$EXPECTED_D241_DRY_RUN_SHA256" || die 68 "D244_D241_DRY_RUN_DEPENDENCY_HASH_MISMATCH"
    sha256_matches "$UNSEAL_PATCH" "$EXPECTED_UNSEAL_SHA256" || die 68 "D244_UNSEAL_PATCH_HASH_MISMATCH"
    grep -Fq 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' "$BACKEND_SOURCE" || die 68 "D244_BACKEND_NOT_SOURCE_SEALED"
    grep -Fq 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")' "$ENTRYPOINT_SOURCE" || die 68 "D244_ENTRYPOINT_NOT_SOURCE_SEALED"
}

run_import_probe() {
    local probe_output="$1"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_SOURCE" --offline-import-probe > "$probe_output"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["status"]=="pass"; assert r["repository"]==sys.argv[2]; assert r["marker_namespace"].endswith("d244-operator-invocation.marker"); assert r["report_directory"].endswith("d244-results"); assert r["libusb_init_count"]==r["usb_open_count"]==r["goodix_command_count"]==0' "$probe_output" "$EXPECTED_REPOSITORY"
}

verify_closure_gate() {
    [[ -f "$CLOSURE_REPORT" ]] || die 72 "D244_EXECUTABLE_CLOSURE_REPORT_MISSING"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --verify-report "$CLOSURE_REPORT" >/dev/null || die 72 "D244_EXECUTABLE_CLOSURE_REPORT_STALE_OR_FAILED"
}

render_preflight_failure() {
    local report_path="$1"
    if ! PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_OBSERVABILITY_SOURCE" --report "$report_path" >&2; then
        printf '%s\n' \
            'D244_PHASE=PREFLIGHT' \
            'D244_RESULT=FAIL' \
            'D244_FAILURE_CLASS=PREFLIGHT_REPORT_RENDERER_FAILED' \
            'D244_USB_OPEN_COUNT=0' \
            'D244_GOODIX_COMMAND_COUNT=0' \
            'D244_LIVE_USB_EXECUTION=NOT_STARTED' >&2
    fi
}

[[ "$(pwd -P)" == "$EXPECTED_REPOSITORY" ]] || die 65 "WRONG_REPOSITORY_CWD"

if [[ "${1-}" == "$PREFLIGHT_FAILURE_FIXTURE_ARGUMENT" && "$#" -eq 2 ]]; then
    verify_artifacts_and_seals
    render_preflight_failure "$2"
    exit 69
fi

if [[ "${1-}" == "$DRY_RUN_ARGUMENT" && "$#" -eq 1 ]]; then
    verify_artifacts_and_seals
    probe_output="$(mktemp /tmp/d244-import-probe.XXXXXX.json)"
    trap 'rm -f -- "$probe_output"' EXIT INT TERM HUP
    run_import_probe "$probe_output"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --report "$CLOSURE_REPORT" >/dev/null
    verify_closure_gate
    printf 'D244_PHASE=EXECUTABLE_CLOSURE\nD244_RESULT=PASS\nD244_FAILURE_CLASS=none\n'
    exit 0
fi

[[ "${1-}" == "$AUTHORIZATION_ARGUMENT" && "$#" -eq 1 ]] || die 64 "EXPLICIT_D244_FRESH_STATE_AUTHORIZATION_REQUIRED"
verify_artifacts_and_seals
verify_closure_gate
[[ "$EUID" -eq 0 ]] || die 66 "ROOT_CONTEXT_REQUIRED"
[[ "${SUDO_UID-}" =~ ^[0-9]+$ && "${SUDO_UID}" -ne 0 ]] || die 67 "NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED"
[[ ! -e "$AUTHORIZATION_MARKER" ]] || die 70 "D244_SINGLE_USE_MARKER_ALREADY_CONSUMED"

fresh_environment="$(mktemp /tmp/d244-fresh-state.XXXXXX.env)"
trap 'rm -f -- "$fresh_environment"' EXIT INT TERM HUP
PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
    python3 "$FRESH_STATE_SOURCE" --baseline "$BOOT_BASELINE" --operator-confirmed --format env > "$fresh_environment"
# The file is emitted by the pinned D244 helper and contains only quoted D244_* exports.
source "$fresh_environment"
if [[ "$D244_FRESH_STATE_CONTROL_VALID" != "true" ]]; then
    printf 'D244 fresh-state evidence is insufficient or matches the D243 boot; run remains single-shot but is not a valid causal control\n' >&2
fi

install -d -m 0700 -o root -g root "$D244_REPORT_DIR" || die 69 "D244_REPORT_DIRECTORY_PREPARATION_FAILED"
if ! PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 python3 "$PREFLIGHT_SOURCE"; then
    render_preflight_failure "$PREFLIGHT_REPORT"
    exit 69
fi

temporary_directory="$(mktemp -d /tmp/d244-live-tls.XXXXXX)"
backup_directory="$temporary_directory/sealed-source"
mkdir -m 700 -- "$backup_directory"
cp --archive -- "$BACKEND_SOURCE" "$ENTRYPOINT_SOURCE" "$backup_directory/"
live_stdout="$temporary_directory/live-stdout.json"
source_unsealed=0
source_resealed=0

reseal_source() {
    local restore_status=0
    if [[ "$source_unsealed" -eq 1 && "$source_resealed" -eq 0 ]]; then
        cp --archive -- "$backup_directory/$(basename "$BACKEND_SOURCE")" "$BACKEND_SOURCE" || restore_status=1
        cp --archive -- "$backup_directory/$(basename "$ENTRYPOINT_SOURCE")" "$ENTRYPOINT_SOURCE" || restore_status=1
        sha256_matches "$BACKEND_SOURCE" "$EXPECTED_BACKEND_SHA256" || restore_status=1
        sha256_matches "$ENTRYPOINT_SOURCE" "$EXPECTED_ENTRYPOINT_SHA256" || restore_status=1
        source_resealed=1
    fi
    return "$restore_status"
}

finish() {
    local original_status="$?"
    trap - EXIT INT TERM HUP
    reseal_source || original_status=90
    if [[ -s "$live_stdout" ]]; then
        cp -- "$live_stdout" "$OPERATOR_STDOUT"
        chmod 0600 "$OPERATOR_STDOUT"
        chown "$SUDO_UID" "$OPERATOR_STDOUT"
    fi
    rm -f -- "$fresh_environment" "$live_stdout" "$backup_directory/$(basename "$BACKEND_SOURCE")" "$backup_directory/$(basename "$ENTRYPOINT_SOURCE")"
    rmdir -- "$backup_directory" "$temporary_directory" 2>/dev/null || true
    exit "$original_status"
}
trap finish EXIT INT TERM HUP

source_unsealed=1
patch --batch --forward --strip=1 --input="$UNSEAL_PATCH"
grep -Fq 'D235_RESULT_SCHEMA = "d244-live-tls-single-shot-result-v1"' "$ENTRYPOINT_SOURCE" || die 71 "D244_UNSEAL_VERIFICATION_FAILED"
grep -Fq 'single_use_marker=store / "d244-operator-invocation.marker"' "$ENTRYPOINT_SOURCE" || die 71 "D244_NAMESPACE_UNSEAL_VERIFICATION_FAILED"

set +e
PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 python3 -m src.goodix5125_d235_entrypoint > "$live_stdout"
live_status="$?"
set -e
reseal_source || die 90 "CRITICAL_SOURCE_RESEAL_FAILURE"

if [[ -s "$live_stdout" ]]; then
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("D244_PHASE="+str(r.get("attempted_phase","UNKNOWN"))); print("D244_RESULT="+str(r.get("d244_result","UNKNOWN"))); print("D244_FAILURE_CLASS="+str(r.get("d244_failure_class","UNKNOWN"))); print("D244_FRESH_STATE_CONTROL_VALID="+str(r.get("D244_FRESH_STATE_CONTROL_VALID",False)).lower())' "$live_stdout" || true
fi
[[ "$live_status" -eq 0 ]] || printf 'D244 live TLS attempt stopped; durable report published; source resealed; no retry authorized\n' >&2
exit "$live_status"
