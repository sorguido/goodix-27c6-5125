#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY="$(git -C "$SCRIPT_DIRECTORY/.." rev-parse --show-toplevel)"
readonly AUTHORIZATION_ARGUMENT="--i-authorize-one-d245-a8-e4-tls-attempt"
readonly DRY_RUN_ARGUMENT="--offline-dry-run"
readonly D245_REPORT_DIR="/var/lib/goodix-5125-poc/d245-results"
readonly AUTHORIZATION_MARKER="/var/lib/goodix-5125-poc/d245-operator-invocation.marker"
readonly PREFLIGHT_REPORT="analysis/D245/D245_preflight_report.json"
readonly CLOSURE_REPORT="analysis/D245/D245_executable_closure_report.json"
readonly OPERATOR_STDOUT="analysis/D245/D245_operator_live_stdout.json"
readonly BACKEND_SOURCE="src/goodix5125_d233_backend.py"
readonly ENTRYPOINT_SOURCE="src/goodix5125_d235_entrypoint.py"
readonly UNSEAL_PATCH="analysis/D245/D245_live_unseal.patch"
readonly DRY_RUN_SOURCE="analysis/D245/d245_operator_dry_run.py"
readonly PREFLIGHT_SOURCE="analysis/D245/d245_preflight.py"
readonly PREFLIGHT_OBSERVABILITY_SOURCE="analysis/D245/d245_preflight_observability.py"

readonly EXPECTED_CORE_SHA256="2875a0c4f3b166906d30c4648f0d965e8b18614299be46a7a24fb1d6a9079726"
readonly EXPECTED_BACKEND_SHA256="e537f33d47d49d47b0fc451c80b08fbafdc185e884d519cb603e22baf458c982"
readonly EXPECTED_ENTRYPOINT_SHA256="d87b11d0f2de608f05c232fa83d4e03ce4d248fe37839808f42f6ea577143b69"
readonly EXPECTED_AUDIT_SHA256="e70bd8bb4b020c38228aab139de751614c280aa78f4faa8f4e01360ac8913690"
readonly EXPECTED_CONTRACT_SHA256="99d77ca3fbb7d0bf80cd1a081111e7eddee491c13405054ae14f6bf6ecd1be86"
readonly EXPECTED_UNSEAL_SHA256="66b6a7416479190ef56b67623222346a1452f2fdfba03f47764a59b09a78f5b0"
readonly EXPECTED_RUNTIME_MATRIX_SHA256="32a24adae47e711b015016163805f6c6a36f78191021d222f37652924fd774c8"
readonly EXPECTED_DRY_RUN_SHA256="1589fbfe422518ec7a99339cf1e2c8daea24720cb9ef4c05fb8a5b4c10f756c5"
readonly EXPECTED_PREFLIGHT_SHA256="0f2d31e79f35bea6042bd4ce32d5fe9cfc0456b32508a288fac1e03d3cbdb057"
readonly EXPECTED_PREFLIGHT_OBSERVABILITY_SHA256="b09af724ce3e4df12b2cd38a44bf9d00443f8c30f809c90ce8308e66d5c860e1"
readonly EXPECTED_D244_LIVE_REPORT_SHA256="fd9099be8772afcd72592d2f113e837794e686a24e76b40aa8b13b0b92f079ae"
readonly EXPECTED_D241_PREFLIGHT_SHA256="6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7"
readonly EXPECTED_TEST_BACKEND_SHA256="61449bc53ad433148f645d14b8dd87ffd84fd6d66babbd6ea5a20c3c4b1d11a1"
readonly EXPECTED_TEST_CLOSURE_SHA256="2bebab6026c81987a517908096b8d14e21aab7fdb7a5444e33d6bcf8eb5ca85d"
readonly EXPECTED_TEST_TRANSITION_SHA256="b40a763a4f028b6e70c13623919e25d3a1c3fc41d6b997515543cc1b71dae019"

die() {
    local code="$1"
    shift
    printf 'D245_PHASE=LAUNCHER\nD245_RESULT=FAIL\nD245_FAILURE_CLASS=%s\n' "$*" >&2
    exit "$code"
}

sha256_matches() {
    local path="$1"
    local expected="$2"
    [[ "$(sha256sum -- "$path" | awk '{print $1}')" == "$expected" ]]
}

verify_artifacts_and_seals() {
    sha256_matches src/goodix5125_d232_offline.py "$EXPECTED_CORE_SHA256" || die 68 "D245_CORE_PROTOCOL_HASH_MISMATCH"
    sha256_matches "$BACKEND_SOURCE" "$EXPECTED_BACKEND_SHA256" || die 68 "D245_SEALED_BACKEND_HASH_MISMATCH"
    sha256_matches "$ENTRYPOINT_SOURCE" "$EXPECTED_ENTRYPOINT_SHA256" || die 68 "D245_SEALED_ENTRYPOINT_HASH_MISMATCH"
    sha256_matches analysis/D245/D245_A8_E4_primary_evidence_audit.md "$EXPECTED_AUDIT_SHA256" || die 68 "D245_A8_AUDIT_HASH_MISMATCH"
    sha256_matches analysis/D245/D245_A8_E4_contract.json "$EXPECTED_CONTRACT_SHA256" || die 68 "D245_A8_CONTRACT_HASH_MISMATCH"
    sha256_matches "$UNSEAL_PATCH" "$EXPECTED_UNSEAL_SHA256" || die 68 "D245_UNSEAL_PATCH_HASH_MISMATCH"
    sha256_matches analysis/D245/d245_runtime_matrix.py "$EXPECTED_RUNTIME_MATRIX_SHA256" || die 68 "D245_RUNTIME_MATRIX_HASH_MISMATCH"
    sha256_matches "$DRY_RUN_SOURCE" "$EXPECTED_DRY_RUN_SHA256" || die 68 "D245_CLOSURE_RUNNER_HASH_MISMATCH"
    sha256_matches "$PREFLIGHT_SOURCE" "$EXPECTED_PREFLIGHT_SHA256" || die 68 "D245_PREFLIGHT_HASH_MISMATCH"
    sha256_matches "$PREFLIGHT_OBSERVABILITY_SOURCE" "$EXPECTED_PREFLIGHT_OBSERVABILITY_SHA256" || die 68 "D245_PREFLIGHT_OBSERVABILITY_HASH_MISMATCH"
    sha256_matches analysis/D244/D244_operator_live_stdout.json "$EXPECTED_D244_LIVE_REPORT_SHA256" || die 68 "D245_D244_LIVE_REPORT_HASH_MISMATCH"
    sha256_matches analysis/D241/d241_preflight.py "$EXPECTED_D241_PREFLIGHT_SHA256" || die 68 "D245_D241_PREFLIGHT_DEPENDENCY_HASH_MISMATCH"
    sha256_matches tests/test_d233_backend.py "$EXPECTED_TEST_BACKEND_SHA256" || die 68 "D245_TEST_BACKEND_HASH_MISMATCH"
    sha256_matches tests/test_d233_closure.py "$EXPECTED_TEST_CLOSURE_SHA256" || die 68 "D245_TEST_CLOSURE_HASH_MISMATCH"
    sha256_matches tests/test_d241_transition.py "$EXPECTED_TEST_TRANSITION_SHA256" || die 68 "D245_TEST_TRANSITION_HASH_MISMATCH"
    grep -Fq 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' "$BACKEND_SOURCE" || die 68 "D245_BACKEND_NOT_SOURCE_SEALED"
    grep -Fq 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")' "$ENTRYPOINT_SOURCE" || die 68 "D245_ENTRYPOINT_NOT_SOURCE_SEALED"
}

verify_closure_gate() {
    [[ -f "$CLOSURE_REPORT" ]] || die 72 "D245_EXECUTABLE_CLOSURE_REPORT_MISSING"
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --verify-report "$CLOSURE_REPORT" >/dev/null \
        || die 72 "D245_EXECUTABLE_CLOSURE_REPORT_STALE_OR_FAILED"
}

render_preflight_failure() {
    if ! PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_OBSERVABILITY_SOURCE" --report "$PREFLIGHT_REPORT" >&2; then
        printf '%s\n' \
            'D245_PHASE=PREFLIGHT' \
            'D245_RESULT=FAIL' \
            'D245_FAILURE_CLASS=PREFLIGHT_REPORT_RENDERER_FAILED' \
            'D245_USB_OPEN_COUNT=0' \
            'D245_GOODIX_COMMAND_COUNT=0' \
            'D245_LIVE_USB_EXECUTION=NOT_STARTED' >&2
    fi
}

[[ "$SCRIPT_DIRECTORY" == "$REPOSITORY/operator_kit" ]] || die 65 "LAUNCHER_OUTSIDE_RESOLVED_REPOSITORY"
cd -- "$REPOSITORY"

if [[ "${1-}" == "$DRY_RUN_ARGUMENT" && "$#" -eq 1 ]]; then
    verify_artifacts_and_seals
    probe_output="$(mktemp /tmp/d245-import-probe.XXXXXX.json)"
    sandbox_root="$(mktemp -d /tmp/d245-preflight-sandbox.XXXXXX)"
    trap 'rm -f -- "$probe_output"; find "$sandbox_root" -type f -delete 2>/dev/null || true; find "$sandbox_root" -depth -type d -empty -delete 2>/dev/null || true' EXIT INT TERM HUP
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_SOURCE" --offline-import-probe > "$probe_output"
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["status"]=="pass"; assert r["repository"]==sys.argv[2]; assert r["marker_namespace"].endswith("d245-operator-invocation.marker"); assert r["report_directory"].endswith("d245-results"); assert r["libusb_init_count"]==r["usb_open_count"]==r["goodix_command_count"]==0' "$probe_output" "$REPOSITORY"
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_SOURCE" --offline-sandbox-preflight "$sandbox_root" >/dev/null
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --report "$CLOSURE_REPORT" >/dev/null
    verify_closure_gate
    printf 'D245_PHASE=EXECUTABLE_CLOSURE\nD245_RESULT=PASS\nD245_FAILURE_CLASS=none\nD245_LIVE_USB_EXECUTION=NOT_PERFORMED\n'
    exit 0
fi

[[ "${1-}" == "$AUTHORIZATION_ARGUMENT" && "$#" -eq 1 ]] || die 64 "EXPLICIT_D245_SINGLE_RUN_AUTHORIZATION_REQUIRED"
verify_artifacts_and_seals
verify_closure_gate
[[ "$EUID" -eq 0 ]] || die 66 "ROOT_CONTEXT_REQUIRED"
[[ "${SUDO_UID-}" =~ ^[0-9]+$ && "${SUDO_UID}" -ne 0 ]] || die 67 "NON_ROOT_HUMAN_OPERATOR_IDENTITY_REQUIRED"
[[ ! -e "$AUTHORIZATION_MARKER" ]] || die 70 "D245_SINGLE_USE_MARKER_ALREADY_CONSUMED"

install -d -m 0700 -o root -g root "$D245_REPORT_DIR" || die 69 "D245_REPORT_DIRECTORY_PREPARATION_FAILED"
if ! PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 python3 "$PREFLIGHT_SOURCE"; then
    render_preflight_failure
    exit 69
fi

temporary_directory="$(mktemp -d /tmp/d245-live-tls.XXXXXX)"
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
grep -Fq 'D235_RESULT_SCHEMA = "d245-live-tls-single-shot-result-v1"' "$ENTRYPOINT_SOURCE" || die 71 "D245_UNSEAL_VERIFICATION_FAILED"
grep -Fq 'single_use_marker=store / "d245-operator-invocation.marker"' "$ENTRYPOINT_SOURCE" || die 71 "D245_NAMESPACE_UNSEAL_VERIFICATION_FAILED"
grep -Fq 'A8_CANONICAL_REQUEST = bytes.fromhex("a00600a6a803000000ff")' "$BACKEND_SOURCE" || die 71 "D245_A8_UNSEAL_VERIFICATION_FAILED"

set +e
PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 python3 -m src.goodix5125_d235_entrypoint > "$live_stdout"
live_status="$?"
set -e
reseal_source || die 90 "CRITICAL_SOURCE_RESEAL_FAILURE"

if [[ -s "$live_stdout" ]]; then
    PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("D245_PHASE="+str(r.get("attempted_phase","UNKNOWN"))); print("D245_RESULT="+str(r.get("d245_result","UNKNOWN"))); print("D245_FAILURE_CLASS="+str(r.get("a8_failure_class",r.get("d244_failure_class",r.get("abort_class","UNKNOWN"))))); print("D245_A8_ACK_STATUS="+str(r.get("a8_ack_status","none"))); print("D245_A8_FIRMWARE_VERSION_MATCH="+str(r.get("a8_firmware_version_match",False)).lower()); print("D245_RUNTIME_PSK_E4_BINDING_STATUS="+str(r.get("runtime_psk_e4_binding_status","not_reached")))' "$live_stdout" || true
fi
[[ "$live_status" -eq 0 ]] || printf 'D245 live attempt stopped; durable report published; source resealed; no retry authorized\n' >&2
exit "$live_status"
