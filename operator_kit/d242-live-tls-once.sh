#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly EXPECTED_REPOSITORY="/home/guido/Repository/goodix-27c6-5125"
readonly AUTHORIZATION_ARGUMENT="--i-authorize-one-d242-live-tls-attempt"
readonly DRY_RUN_ARGUMENT="--offline-dry-run"
readonly PREFLIGHT_FAILURE_FIXTURE_ARGUMENT="--offline-render-preflight-failure"
readonly D242_REPORT_DIR="/var/lib/goodix-5125-poc/d242-results"
readonly AUTHORIZATION_MARKER="/var/lib/goodix-5125-poc/d242-operator-invocation.marker"
readonly PREFLIGHT_REPORT="analysis/D242/D242_preflight_report.json"
readonly CLOSURE_REPORT="analysis/D242/D242_executable_closure_report.json"
readonly OPERATOR_STDOUT="analysis/D242/D242_operator_live_stdout.json"
readonly CORE_SOURCE="src/goodix5125_d232_offline.py"
readonly BACKEND_SOURCE="src/goodix5125_d233_backend.py"
readonly ENTRYPOINT_SOURCE="src/goodix5125_d235_entrypoint.py"
readonly DEPENDENCY_GATE_SOURCE="analysis/D242/d242_dependency_gate.py"
readonly PREFLIGHT_OBSERVABILITY_SOURCE="analysis/D242/d242_preflight_observability.py"
readonly PREFLIGHT_SOURCE="analysis/D242/d242_preflight.py"
readonly DRY_RUN_SOURCE="analysis/D242/d242_operator_dry_run.py"
readonly D241_PREFLIGHT_SOURCE="analysis/D241/d241_preflight.py"
readonly D241_DRY_RUN_SOURCE="analysis/D241/d241_operator_dry_run.py"
readonly UNSEAL_PATCH="analysis/D242/D242_live_unseal.patch"
readonly EXPECTED_CORE_SHA256="2875a0c4f3b166906d30c4648f0d965e8b18614299be46a7a24fb1d6a9079726"
readonly EXPECTED_BACKEND_SHA256="c072db52c29a9e22dc597e53743820217077e5373bafb48cadc69cbb0e90fcef"
readonly EXPECTED_ENTRYPOINT_SHA256="6cd9fd3796ded831b0c70877282807c6a423d39f4ee42b8fd2593fe1b4908993"
readonly EXPECTED_DEPENDENCY_GATE_SHA256="591d9962a7ca5209341000fe28ed690a5774f25e4f5bc325129adf2727379006"
readonly EXPECTED_PREFLIGHT_OBSERVABILITY_SHA256="74ac5ac2a4a6ab084f1302e411b5a70a13b0195e249aa9594d16f4273fb85d5b"
readonly EXPECTED_PREFLIGHT_SHA256="7d7f0569ce1cbf351c82ba1634ab911b489934bb4db7055926a88c3f809f0e9d"
readonly EXPECTED_DRY_RUN_SHA256="89d79bd1fa27e4a33905cc231c089d2fb0c21d950ddc278a7b6dd2ad45e393ea"
readonly EXPECTED_D241_PREFLIGHT_SHA256="6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7"
readonly EXPECTED_D241_DRY_RUN_SHA256="0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f"
readonly EXPECTED_UNSEAL_SHA256="14b68374080675e81e63148647da80124ac675d43313d956b3951c75c4ff17fd"

die() {
    local code="$1"
    shift
    printf 'D242_PHASE=LAUNCHER\nD242_RESULT=FAIL\nD242_FAILURE_CLASS=%s\n' "$*" >&2
    exit "$code"
}

sha256_matches() {
    local path="$1"
    local expected="$2"
    [[ "$(sha256sum -- "$path" | awk '{print $1}')" == "$expected" ]]
}

verify_artifacts_and_seals() {
    sha256_matches "$CORE_SOURCE" "$EXPECTED_CORE_SHA256" || die 68 "D242_CORE_PROTOCOL_HASH_MISMATCH"
    sha256_matches "$BACKEND_SOURCE" "$EXPECTED_BACKEND_SHA256" || die 68 "D242_SEALED_BACKEND_HASH_MISMATCH"
    sha256_matches "$ENTRYPOINT_SOURCE" "$EXPECTED_ENTRYPOINT_SHA256" || die 68 "D242_SEALED_ENTRYPOINT_HASH_MISMATCH"
    sha256_matches "$DEPENDENCY_GATE_SOURCE" "$EXPECTED_DEPENDENCY_GATE_SHA256" || die 68 "D242_DEPENDENCY_GATE_HASH_MISMATCH"
    sha256_matches "$PREFLIGHT_OBSERVABILITY_SOURCE" "$EXPECTED_PREFLIGHT_OBSERVABILITY_SHA256" || die 68 "D242_PREFLIGHT_OBSERVABILITY_HASH_MISMATCH"
    sha256_matches "$PREFLIGHT_SOURCE" "$EXPECTED_PREFLIGHT_SHA256" || die 68 "D242_PREFLIGHT_HASH_MISMATCH"
    sha256_matches "$DRY_RUN_SOURCE" "$EXPECTED_DRY_RUN_SHA256" || die 68 "D242_CLOSURE_RUNNER_HASH_MISMATCH"
    sha256_matches "$D241_PREFLIGHT_SOURCE" "$EXPECTED_D241_PREFLIGHT_SHA256" || die 68 "D242_D241_PREFLIGHT_DEPENDENCY_HASH_MISMATCH"
    sha256_matches "$D241_DRY_RUN_SOURCE" "$EXPECTED_D241_DRY_RUN_SHA256" || die 68 "D242_D241_DRY_RUN_DEPENDENCY_HASH_MISMATCH"
    sha256_matches "$UNSEAL_PATCH" "$EXPECTED_UNSEAL_SHA256" || die 68 "D242_UNSEAL_PATCH_HASH_MISMATCH"
    grep -Fq 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' "$BACKEND_SOURCE" || die 68 "D242_BACKEND_NOT_SOURCE_SEALED"
    grep -Fq 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")' "$ENTRYPOINT_SOURCE" || die 68 "D242_ENTRYPOINT_NOT_SOURCE_SEALED"
}

run_import_probe() {
    local probe_output="$1"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_SOURCE" --offline-import-probe > "$probe_output"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["status"]=="pass"; assert r["repository"]==sys.argv[2]; assert r["marker_namespace"].endswith("d242-operator-invocation.marker"); assert r["libusb_init_count"]==r["usb_open_count"]==r["goodix_command_count"]==0' "$probe_output" "$EXPECTED_REPOSITORY"
}

verify_closure_gate() {
    [[ -f "$CLOSURE_REPORT" ]] || die 72 "D242_EXECUTABLE_CLOSURE_REPORT_MISSING"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --verify-report "$CLOSURE_REPORT" >/dev/null || die 72 "D242_EXECUTABLE_CLOSURE_REPORT_STALE_OR_FAILED"
}

render_preflight_failure() {
    local report_path="$1"
    if ! PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_OBSERVABILITY_SOURCE" --report "$report_path" >&2; then
        printf '%s\n' \
            'D242_PHASE=PREFLIGHT' \
            'D242_RESULT=FAIL' \
            'D242_FAILURE_CLASS=PREFLIGHT_REPORT_RENDERER_FAILED' \
            'D242_PREFLIGHT_FAILURES=preflight_report_renderer_failed' \
            'D242_MARKER_PATH=UNAVAILABLE' \
            'D242_USB_OPEN_COUNT=0' \
            'D242_GOODIX_COMMAND_COUNT=0' \
            'D242_REAL_SECRET_READ_COUNT=0' \
            'D242_FPRINTD_MUTATION_COUNT=0' \
            'D242_LIVE_MARKER_CREATE_COUNT=0' \
            'D242_LIVE_USB_EXECUTION=NOT_STARTED' >&2
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
    probe_output="$(mktemp /tmp/d242-import-probe.XXXXXX.json)"
    trap 'rm -f -- "$probe_output"' EXIT INT TERM HUP
    run_import_probe "$probe_output"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --report "$CLOSURE_REPORT" >/dev/null
    verify_closure_gate
    printf 'D242_PHASE=EXECUTABLE_CLOSURE\nD242_RESULT=PASS\nD242_FAILURE_CLASS=none\n'
    exit 0
fi

[[ "${1-}" == "$AUTHORIZATION_ARGUMENT" && "$#" -eq 1 ]] || die 64 "EXPLICIT_D242_AUTHORIZATION_ARGUMENT_REQUIRED"
verify_artifacts_and_seals
verify_closure_gate
[[ "$EUID" -eq 0 ]] || die 66 "ROOT_CONTEXT_REQUIRED"
[[ "${SUDO_UID-}" =~ ^[0-9]+$ && "${SUDO_UID}" -ne 0 ]] || die 67 "NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED"
[[ ! -e "$AUTHORIZATION_MARKER" ]] || die 70 "D242_SINGLE_USE_MARKER_ALREADY_CONSUMED"

install -d -m 0700 -o root -g root "$D242_REPORT_DIR" || die 69 "D242_REPORT_DIRECTORY_PREPARATION_FAILED"
if ! PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 python3 "$PREFLIGHT_SOURCE"; then
    render_preflight_failure "$PREFLIGHT_REPORT"
    exit 69
fi

temporary_directory="$(mktemp -d /tmp/d242-live-tls.XXXXXX)"
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
grep -Fq 'D235_RESULT_SCHEMA = "d242-live-tls-single-shot-result-v1"' "$ENTRYPOINT_SOURCE" || die 71 "D242_UNSEAL_VERIFICATION_FAILED"

set +e
PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 python3 -m src.goodix5125_d235_entrypoint > "$live_stdout"
live_status="$?"
set -e
reseal_source || die 90 "CRITICAL_SOURCE_RESEAL_FAILURE"

if [[ -s "$live_stdout" ]]; then
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("D242_PHASE="+str(r.get("attempted_phase","UNKNOWN"))); print("D242_RESULT="+str(r.get("d242_result","UNKNOWN"))); print("D242_FAILURE_CLASS="+str(r.get("d242_failure_class","UNKNOWN")))' "$live_stdout" || true
fi
[[ "$live_status" -eq 0 ]] || printf 'D242 live TLS attempt stopped; source resealed; no retry authorized\n' >&2
exit "$live_status"
