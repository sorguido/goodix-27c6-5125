#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly EXPECTED_REPOSITORY="$(git -C "$(dirname -- "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)"
readonly AUTHORIZATION_ARGUMENT="--i-authorize-one-d243-live-tls-attempt"
readonly DRY_RUN_ARGUMENT="--offline-dry-run"
readonly PREFLIGHT_FAILURE_FIXTURE_ARGUMENT="--offline-render-preflight-failure"
readonly D243_REPORT_DIR="/var/lib/goodix-5125-poc/d243-results"
readonly AUTHORIZATION_MARKER="/var/lib/goodix-5125-poc/d243-operator-invocation.marker"
readonly PREFLIGHT_REPORT="analysis/D243/D243_preflight_report.json"
readonly CLOSURE_REPORT="analysis/D243/D243_executable_closure_report.json"
readonly OPERATOR_STDOUT="analysis/D243/D243_operator_live_stdout.json"
readonly CORE_SOURCE="src/goodix5125_d232_offline.py"
readonly BACKEND_SOURCE="src/goodix5125_d233_backend.py"
readonly ENTRYPOINT_SOURCE="src/goodix5125_d235_entrypoint.py"
readonly DEPENDENCY_GATE_SOURCE="analysis/D243/d243_dependency_gate.py"
readonly PREFLIGHT_OBSERVABILITY_SOURCE="analysis/D243/d243_preflight_observability.py"
readonly PREFLIGHT_SOURCE="analysis/D243/d243_preflight.py"
readonly DRY_RUN_SOURCE="analysis/D243/d243_operator_dry_run.py"
readonly D241_PREFLIGHT_SOURCE="analysis/D241/d241_preflight.py"
readonly D241_DRY_RUN_SOURCE="analysis/D241/d241_operator_dry_run.py"
readonly D242_LIVE_REPORT="analysis/D242/D242_operator_live_stdout.json"
readonly UNSEAL_PATCH="analysis/D243/D243_live_unseal.patch"
readonly EXPECTED_CORE_SHA256="2875a0c4f3b166906d30c4648f0d965e8b18614299be46a7a24fb1d6a9079726"
readonly EXPECTED_BACKEND_SHA256="e537f33d47d49d47b0fc451c80b08fbafdc185e884d519cb603e22baf458c982"
readonly EXPECTED_ENTRYPOINT_SHA256="d87b11d0f2de608f05c232fa83d4e03ce4d248fe37839808f42f6ea577143b69"
readonly EXPECTED_DEPENDENCY_GATE_SHA256="3bd1a7b1b54696a7d0b26345cb80352991dbf2958084a6b565fe6f37eb89b1cb"
readonly EXPECTED_PREFLIGHT_OBSERVABILITY_SHA256="3a811bf07d22bb7a525c7b6fe49e1165147369cab149d6abe4ee528f2e8da426"
readonly EXPECTED_PREFLIGHT_SHA256="cecd99fefcb13bfaa753426e93479e70e605f8e7f6e40f5be78a8275b02902f4"
readonly EXPECTED_DRY_RUN_SHA256="fdedc6ed756e5ada8884d01598fa4c9c2e6ac94a3c36d33dda51e5b19a589f4b"
readonly EXPECTED_D241_PREFLIGHT_SHA256="6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7"
readonly EXPECTED_D241_DRY_RUN_SHA256="0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f"
readonly EXPECTED_D242_LIVE_REPORT_SHA256="1d9c2c736a2b8939855a184e350ea2ecaa914921536ae2a2d616130a166eb7e7"
readonly EXPECTED_UNSEAL_SHA256="23113e96010263a4d0050dfa33d60c64f2d1d1f40297e22b524a6803a973fe17"

die() {
    local code="$1"
    shift
    printf 'D243_PHASE=LAUNCHER\nD243_RESULT=FAIL\nD243_FAILURE_CLASS=%s\n' "$*" >&2
    exit "$code"
}

sha256_matches() {
    local path="$1"
    local expected="$2"
    [[ "$(sha256sum -- "$path" | awk '{print $1}')" == "$expected" ]]
}

verify_artifacts_and_seals() {
    sha256_matches "$CORE_SOURCE" "$EXPECTED_CORE_SHA256" || die 68 "D243_CORE_PROTOCOL_HASH_MISMATCH"
    sha256_matches "$BACKEND_SOURCE" "$EXPECTED_BACKEND_SHA256" || die 68 "D243_SEALED_BACKEND_HASH_MISMATCH"
    sha256_matches "$ENTRYPOINT_SOURCE" "$EXPECTED_ENTRYPOINT_SHA256" || die 68 "D243_SEALED_ENTRYPOINT_HASH_MISMATCH"
    sha256_matches "$DEPENDENCY_GATE_SOURCE" "$EXPECTED_DEPENDENCY_GATE_SHA256" || die 68 "D243_DEPENDENCY_GATE_HASH_MISMATCH"
    sha256_matches "$PREFLIGHT_OBSERVABILITY_SOURCE" "$EXPECTED_PREFLIGHT_OBSERVABILITY_SHA256" || die 68 "D243_PREFLIGHT_OBSERVABILITY_HASH_MISMATCH"
    sha256_matches "$PREFLIGHT_SOURCE" "$EXPECTED_PREFLIGHT_SHA256" || die 68 "D243_PREFLIGHT_HASH_MISMATCH"
    sha256_matches "$DRY_RUN_SOURCE" "$EXPECTED_DRY_RUN_SHA256" || die 68 "D243_CLOSURE_RUNNER_HASH_MISMATCH"
    sha256_matches "$D241_PREFLIGHT_SOURCE" "$EXPECTED_D241_PREFLIGHT_SHA256" || die 68 "D243_D241_PREFLIGHT_DEPENDENCY_HASH_MISMATCH"
    sha256_matches "$D241_DRY_RUN_SOURCE" "$EXPECTED_D241_DRY_RUN_SHA256" || die 68 "D243_D241_DRY_RUN_DEPENDENCY_HASH_MISMATCH"
    sha256_matches "$D242_LIVE_REPORT" "$EXPECTED_D242_LIVE_REPORT_SHA256" || die 68 "D243_D242_LIVE_REPORT_HASH_MISMATCH"
    sha256_matches "$UNSEAL_PATCH" "$EXPECTED_UNSEAL_SHA256" || die 68 "D243_UNSEAL_PATCH_HASH_MISMATCH"
    grep -Fq 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' "$BACKEND_SOURCE" || die 68 "D243_BACKEND_NOT_SOURCE_SEALED"
    grep -Fq 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")' "$ENTRYPOINT_SOURCE" || die 68 "D243_ENTRYPOINT_NOT_SOURCE_SEALED"
}

run_import_probe() {
    local probe_output="$1"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_SOURCE" --offline-import-probe > "$probe_output"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["status"]=="pass"; assert r["repository"]==sys.argv[2]; assert r["marker_namespace"].endswith("d243-operator-invocation.marker"); assert r["report_directory"].endswith("d243-results"); assert r["libusb_init_count"]==r["usb_open_count"]==r["goodix_command_count"]==0' "$probe_output" "$EXPECTED_REPOSITORY"
}

verify_closure_gate() {
    [[ -f "$CLOSURE_REPORT" ]] || die 72 "D243_EXECUTABLE_CLOSURE_REPORT_MISSING"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --verify-report "$CLOSURE_REPORT" >/dev/null || die 72 "D243_EXECUTABLE_CLOSURE_REPORT_STALE_OR_FAILED"
}

render_preflight_failure() {
    local report_path="$1"
    if ! PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_OBSERVABILITY_SOURCE" --report "$report_path" >&2; then
        printf '%s\n' \
            'D243_PHASE=PREFLIGHT' \
            'D243_RESULT=FAIL' \
            'D243_FAILURE_CLASS=PREFLIGHT_REPORT_RENDERER_FAILED' \
            'D243_PREFLIGHT_FAILURES=preflight_report_renderer_failed' \
            'D243_MARKER_PATH=UNAVAILABLE' \
            'D243_USB_OPEN_COUNT=0' \
            'D243_GOODIX_COMMAND_COUNT=0' \
            'D243_REAL_SECRET_READ_COUNT=0' \
            'D243_FPRINTD_MUTATION_COUNT=0' \
            'D243_LIVE_MARKER_CREATE_COUNT=0' \
            'D243_LIVE_USB_EXECUTION=NOT_STARTED' >&2
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
    probe_output="$(mktemp /tmp/d243-import-probe.XXXXXX.json)"
    trap 'rm -f -- "$probe_output"' EXIT INT TERM HUP
    run_import_probe "$probe_output"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --report "$CLOSURE_REPORT" >/dev/null
    verify_closure_gate
    printf 'D243_PHASE=EXECUTABLE_CLOSURE\nD243_RESULT=PASS\nD243_FAILURE_CLASS=none\n'
    exit 0
fi

[[ "${1-}" == "$AUTHORIZATION_ARGUMENT" && "$#" -eq 1 ]] || die 64 "EXPLICIT_D243_AUTHORIZATION_ARGUMENT_REQUIRED"
verify_artifacts_and_seals
verify_closure_gate
[[ "$EUID" -eq 0 ]] || die 66 "ROOT_CONTEXT_REQUIRED"
[[ "${SUDO_UID-}" =~ ^[0-9]+$ && "${SUDO_UID}" -ne 0 ]] || die 67 "NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED"
[[ ! -e "$AUTHORIZATION_MARKER" ]] || die 70 "D243_SINGLE_USE_MARKER_ALREADY_CONSUMED"

install -d -m 0700 -o root -g root "$D243_REPORT_DIR" || die 69 "D243_REPORT_DIRECTORY_PREPARATION_FAILED"
if ! PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 python3 "$PREFLIGHT_SOURCE"; then
    render_preflight_failure "$PREFLIGHT_REPORT"
    exit 69
fi

temporary_directory="$(mktemp -d /tmp/d243-live-tls.XXXXXX)"
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
    rm -f -- "$live_stdout" "$backup_directory/$(basename "$BACKEND_SOURCE")" "$backup_directory/$(basename "$ENTRYPOINT_SOURCE")"
    rmdir -- "$backup_directory" "$temporary_directory" 2>/dev/null || true
    exit "$original_status"
}
trap finish EXIT INT TERM HUP

source_unsealed=1
patch --batch --forward --strip=1 --input="$UNSEAL_PATCH"
grep -Fq 'D235_RESULT_SCHEMA = "d243-live-tls-single-shot-result-v1"' "$ENTRYPOINT_SOURCE" || die 71 "D243_UNSEAL_VERIFICATION_FAILED"

set +e
PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 python3 -m src.goodix5125_d235_entrypoint > "$live_stdout"
live_status="$?"
set -e
reseal_source || die 90 "CRITICAL_SOURCE_RESEAL_FAILURE"

if [[ -s "$live_stdout" ]]; then
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("D243_PHASE="+str(r.get("attempted_phase","UNKNOWN"))); print("D243_RESULT="+str(r.get("d243_result","UNKNOWN"))); print("D243_FAILURE_CLASS="+str(r.get("d243_failure_class","UNKNOWN")))' "$live_stdout" || true
fi
[[ "$live_status" -eq 0 ]] || printf 'D243 live TLS attempt stopped; durable report published; source resealed; no retry authorized\n' >&2
exit "$live_status"
