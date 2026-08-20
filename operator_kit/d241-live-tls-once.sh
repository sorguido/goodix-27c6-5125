#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly EXPECTED_REPOSITORY="/home/guido/Repository/goodix-27c6-5125"
readonly AUTHORIZATION_ARGUMENT="--i-authorize-one-d241-live-tls-attempt"
readonly DRY_RUN_ARGUMENT="--offline-dry-run"
readonly D241_REPORT_DIR="/var/lib/goodix-5125-poc/d241-results"
readonly AUTHORIZATION_MARKER="/var/lib/goodix-5125-poc/d241-operator-invocation.marker"
readonly PREFLIGHT_REPORT="analysis/D241/D241_preflight_report.json"
readonly CLOSURE_REPORT="analysis/D241/D241_executable_closure_report.json"
readonly OPERATOR_STDOUT="analysis/D241/D241_operator_live_stdout.json"
readonly CORE_SOURCE="src/goodix5125_d232_offline.py"
readonly BACKEND_SOURCE="src/goodix5125_d233_backend.py"
readonly ENTRYPOINT_SOURCE="src/goodix5125_d235_entrypoint.py"
readonly PREFLIGHT_SOURCE="analysis/D241/d241_preflight.py"
readonly DRY_RUN_SOURCE="analysis/D241/d241_operator_dry_run.py"
readonly UNSEAL_PATCH="analysis/D241/D241_live_unseal.patch"
readonly EXPECTED_CORE_SHA256="2875a0c4f3b166906d30c4648f0d965e8b18614299be46a7a24fb1d6a9079726"
readonly EXPECTED_BACKEND_SHA256="ffde5165bbb9fd44da9b6505c9e2e3e417c9e867e8e09deac555020353b2cb5f"
readonly EXPECTED_ENTRYPOINT_SHA256="0e062c591381084ca5f5b7e9b8296dd540f1a03a25dd3f565e56550dea8cc668"
readonly EXPECTED_PREFLIGHT_SHA256="6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7"
readonly EXPECTED_DRY_RUN_SHA256="0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f"
readonly EXPECTED_UNSEAL_SHA256="be6f73b86e9a4cdc8670cde716602cd9707358f84be952bd337887e5703aa378"

die() {
    local code="$1"
    shift
    printf 'D241_PHASE=LAUNCHER\nD241_RESULT=FAIL\nD241_FAILURE_CLASS=%s\n' "$*" >&2
    exit "$code"
}

[[ "$(pwd -P)" == "$EXPECTED_REPOSITORY" ]] || die 65 \
    "WRONG_REPOSITORY_CWD"

sha256_matches() {
    local path="$1"
    local expected="$2"
    [[ "$(sha256sum -- "$path" | awk '{print $1}')" == "$expected" ]]
}

verify_artifacts_and_seals() {
    sha256_matches "$CORE_SOURCE" "$EXPECTED_CORE_SHA256" || die 68 \
        "D241_CORE_PROTOCOL_HASH_MISMATCH"
    sha256_matches "$BACKEND_SOURCE" "$EXPECTED_BACKEND_SHA256" || die 68 \
        "D241_SEALED_BACKEND_HASH_MISMATCH"
    sha256_matches "$ENTRYPOINT_SOURCE" "$EXPECTED_ENTRYPOINT_SHA256" || die 68 \
        "D241_SEALED_ENTRYPOINT_HASH_MISMATCH"
    sha256_matches "$PREFLIGHT_SOURCE" "$EXPECTED_PREFLIGHT_SHA256" || die 68 \
        "D241_PREFLIGHT_HASH_MISMATCH"
    sha256_matches "$DRY_RUN_SOURCE" "$EXPECTED_DRY_RUN_SHA256" || die 68 \
        "D241_CLOSURE_RUNNER_HASH_MISMATCH"
    sha256_matches "$UNSEAL_PATCH" "$EXPECTED_UNSEAL_SHA256" || die 68 \
        "D241_UNSEAL_PATCH_HASH_MISMATCH"
    grep -Fq 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' "$BACKEND_SOURCE" || \
        die 68 "D241_BACKEND_NOT_SOURCE_SEALED"
    grep -Fq 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")' "$ENTRYPOINT_SOURCE" || \
        die 68 "D241_ENTRYPOINT_NOT_SOURCE_SEALED"
}

run_import_probe() {
    local probe_output="$1"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_SOURCE" --offline-import-probe > "$probe_output"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
        python3 -c \
        'import json,sys; r=json.load(open(sys.argv[1])); assert r["status"]=="pass"; assert r["repository"]==sys.argv[2]; assert r["libusb_init_count"]==0; assert r["usb_open_count"]==0; assert r["goodix_command_count"]==0; assert r["marker_namespace"].endswith("d241-operator-invocation.marker")' \
        "$probe_output" "$EXPECTED_REPOSITORY"
}

verify_closure_gate() {
    [[ -f "$CLOSURE_REPORT" ]] || die 72 "D241_EXECUTABLE_CLOSURE_REPORT_MISSING"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --verify-report "$CLOSURE_REPORT" >/dev/null || \
        die 72 "D241_EXECUTABLE_CLOSURE_REPORT_STALE_OR_FAILED"
}

print_preflight_failure() {
    if [[ -f "$PREFLIGHT_REPORT" ]]; then
        PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
        PYTHONDONTWRITEBYTECODE=1 \
            python3 -c \
            'import json,sys; r=json.load(open(sys.argv[1])); print("D241_PHASE="+str(r.get("phase","PREFLIGHT"))); print("D241_RESULT=FAIL"); print("D241_FAILURE_CLASS="+str(r.get("failure_class","PREFLIGHT_UNRESOLVED")))' \
            "$PREFLIGHT_REPORT" >&2 || true
    else
        printf 'D241_PHASE=PREFLIGHT\nD241_RESULT=FAIL\nD241_FAILURE_CLASS=PREFLIGHT_REPORT_MISSING\n' >&2
    fi
}

if [[ "${1-}" == "$DRY_RUN_ARGUMENT" && "$#" -eq 1 ]]; then
    verify_artifacts_and_seals
    probe_output="$(mktemp /tmp/d241-import-probe.XXXXXX.json)"
    trap 'rm -f -- "$probe_output"' EXIT INT TERM HUP
    run_import_probe "$probe_output"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --report "$CLOSURE_REPORT" >/dev/null
    verify_closure_gate
    printf 'D241_PHASE=EXECUTABLE_CLOSURE\nD241_RESULT=PASS\nD241_FAILURE_CLASS=none\n'
    exit 0
fi

[[ "${1-}" == "$AUTHORIZATION_ARGUMENT" && "$#" -eq 1 ]] || die 64 \
    "EXPLICIT_D241_AUTHORIZATION_ARGUMENT_REQUIRED"
verify_artifacts_and_seals
verify_closure_gate
[[ "$EUID" -eq 0 ]] || die 66 "ROOT_CONTEXT_REQUIRED"
[[ "${SUDO_UID-}" =~ ^[0-9]+$ && "${SUDO_UID}" -ne 0 ]] || die 67 \
    "NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED"
[[ ! -e "$AUTHORIZATION_MARKER" ]] || die 70 "D241_SINGLE_USE_MARKER_ALREADY_CONSUMED"

# The authorized root launcher owns this idempotent host prerequisite. The
# subsequent preflight still validates directory type, owner, mode and path.
install -d -m 0700 -o root -g root "$D241_REPORT_DIR" || die 69 \
    "D241_REPORT_DIRECTORY_PREPARATION_FAILED"

if ! PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 python3 "$PREFLIGHT_SOURCE"; then
    print_preflight_failure
    exit 69
fi

temporary_directory="$(mktemp -d /tmp/d241-live-tls.XXXXXX)"
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
    if ! reseal_source; then
        printf 'D241_PHASE=RESEAL\nD241_RESULT=FAIL\nD241_FAILURE_CLASS=CRITICAL_SOURCE_RESEAL_FAILURE\n' >&2
        original_status=90
    fi
    if [[ -s "$live_stdout" ]]; then
        cp -- "$live_stdout" "$OPERATOR_STDOUT"
        chmod 0600 "$OPERATOR_STDOUT"
        chown "$SUDO_UID" "$OPERATOR_STDOUT"
    fi
    rm -f -- "$live_stdout"
    rm -f -- \
        "$backup_directory/$(basename "$BACKEND_SOURCE")" \
        "$backup_directory/$(basename "$ENTRYPOINT_SOURCE")"
    rmdir -- "$backup_directory" "$temporary_directory" 2>/dev/null || true
    exit "$original_status"
}
trap finish EXIT INT TERM HUP

source_unsealed=1
patch --batch --forward --strip=1 --input="$UNSEAL_PATCH"
grep -Fq 'return None' "$BACKEND_SOURCE" || die 71 "D241_BACKEND_UNSEAL_VERIFICATION_FAILED"
grep -Fq 'D235_RESULT_SCHEMA = "d241-live-tls-single-shot-result-v1"' "$ENTRYPOINT_SOURCE" || \
    die 71 "D241_ENTRYPOINT_UNSEAL_VERIFICATION_FAILED"

# ProductionOsPreflight atomically claims the sole D241 marker immediately
# before protected inputs and USB. Historical marker namespaces are untouched.
set +e
PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
PYTHONDONTWRITEBYTECODE=1 \
    python3 -m src.goodix5125_d235_entrypoint > "$live_stdout"
live_status="$?"
set -e

reseal_source || die 90 "CRITICAL_SOURCE_RESEAL_FAILURE"

if [[ -s "$live_stdout" ]]; then
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
        python3 -c \
        'import json,sys; r=json.load(open(sys.argv[1])); print("D241_PHASE="+str(r.get("attempted_phase","UNKNOWN"))); print("D241_RESULT="+str(r.get("d241_result","UNKNOWN"))); print("D241_FAILURE_CLASS="+str(r.get("d241_failure_class","UNKNOWN")))' \
        "$live_stdout" || true
fi

if [[ "$live_status" -ne 0 ]]; then
    printf 'D241 live TLS attempt stopped; source resealed; no retry authorized\n' >&2
fi
exit "$live_status"
