#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly EXPECTED_REPOSITORY="/home/guido/Repository/goodix-27c6-5125"
readonly AUTHORIZATION_ARGUMENT="--i-authorize-one-d239-live-attempt"
readonly DRY_RUN_ARGUMENT="--offline-dry-run-pre-usb"
readonly AUTHORIZATION_MARKER="/var/lib/goodix-5125-poc/d238-operator-invocation.marker"
readonly PREFLIGHT_REPORT="analysis/D236/D236_preflight_report.json"
readonly DRY_RUN_REPORT="analysis/D239/D239_operator_dry_run_report.json"
readonly OPERATOR_STDOUT="analysis/D239/D239_operator_live_stdout.json"
readonly BACKEND_SOURCE="src/goodix5125_d233_backend.py"
readonly ENTRYPOINT_SOURCE="src/goodix5125_d235_entrypoint.py"
readonly PREFLIGHT_SOURCE="analysis/D236/d236_preflight.py"
readonly DRY_RUN_SOURCE="analysis/D239/d239_operator_dry_run.py"
readonly UNSEAL_PATCH="analysis/D239/D239_live_unseal.patch"
readonly EXPECTED_BACKEND_SHA256="7727128ee27337b70ba48eac31b8640c888b76560387363e4eff0c167d993f5b"
readonly EXPECTED_ENTRYPOINT_SHA256="38e857a14bd416808b9ae2df7c4101809879e4732b6e001ce29d11bd731dd555"
readonly EXPECTED_PREFLIGHT_SHA256="de7aacd4213cd6e5ddf9b39917f7f28aa657af34bb62de6d6fbd3b7c529d9603"
readonly EXPECTED_DRY_RUN_SHA256="970b7c540e1276f5e129fba0987702e60862a6e064fbf3a7cdb6324d4cef188e"
readonly EXPECTED_UNSEAL_SHA256="4b243cacf7f0af00d358f1c72c05f0a83f36e22ee3c06d6af8136a8fec742003"

die() {
    local code="$1"
    shift
    printf 'D239 operator kit: %s\n' "$*" >&2
    exit "$code"
}

[[ "$(pwd -P)" == "$EXPECTED_REPOSITORY" ]] || die 65 \
    "launch from $EXPECTED_REPOSITORY"

sha256_matches() {
    local path="$1"
    local expected="$2"
    [[ "$(sha256sum -- "$path" | awk '{print $1}')" == "$expected" ]]
}

verify_artifacts_and_seals() {
    sha256_matches "$BACKEND_SOURCE" "$EXPECTED_BACKEND_SHA256" || die 68 \
        "sealed backend source differs from the reviewed D239 input"
    sha256_matches "$ENTRYPOINT_SOURCE" "$EXPECTED_ENTRYPOINT_SHA256" || die 68 \
        "sealed entrypoint source differs from the reviewed D239 input"
    sha256_matches "$PREFLIGHT_SOURCE" "$EXPECTED_PREFLIGHT_SHA256" || die 68 \
        "preflight source differs from the reviewed D239 input"
    sha256_matches "$DRY_RUN_SOURCE" "$EXPECTED_DRY_RUN_SHA256" || die 68 \
        "dry-run source differs from the reviewed D239 input"
    sha256_matches "$UNSEAL_PATCH" "$EXPECTED_UNSEAL_SHA256" || die 68 \
        "temporary unseal patch differs from the reviewed D239 patch"
    grep -Fq 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' "$BACKEND_SOURCE" || \
        die 68 "backend is not source-sealed"
    grep -Fq 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")' "$ENTRYPOINT_SOURCE" || \
        die 68 "entrypoint is not source-sealed"
}

run_import_probe() {
    local probe_output="$1"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
        python3 "$PREFLIGHT_SOURCE" --d239-offline-import-probe > "$probe_output"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
        python3 -c \
        'import json,sys; r=json.load(open(sys.argv[1])); assert r["status"]=="pass"; assert r["repository"]==sys.argv[2]; assert r["libusb_init_count"]==0; assert r["usb_open_count"]==0; assert r["goodix_command_count"]==0; assert r["live_marker_create_count"]==0' \
        "$probe_output" "$EXPECTED_REPOSITORY"
}

verify_dry_run_gate() {
    [[ -f "$DRY_RUN_REPORT" ]] || die 72 \
        "OPERATOR_KIT_DRY_RUN_PRE_USB report is missing"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --verify-report "$DRY_RUN_REPORT" >/dev/null || die 72 \
        "OPERATOR_KIT_DRY_RUN_PRE_USB report is stale or failed"
}

if [[ "${1-}" == "$DRY_RUN_ARGUMENT" && "$#" -eq 1 ]]; then
    verify_artifacts_and_seals
    probe_output="$(mktemp /tmp/d239-import-probe.XXXXXX.json)"
    trap 'rm -f -- "$probe_output"' EXIT INT TERM HUP
    run_import_probe "$probe_output"
    PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
        python3 "$DRY_RUN_SOURCE" --report "$DRY_RUN_REPORT" >/dev/null
    verify_dry_run_gate
    printf 'D239 operator kit: OPERATOR_KIT_DRY_RUN_PRE_USB=PASS; no live USB execution\n'
    exit 0
fi

[[ "${1-}" == "$AUTHORIZATION_ARGUMENT" && "$#" -eq 1 ]] || die 64 \
    "explicit authorization argument required: $AUTHORIZATION_ARGUMENT"
verify_artifacts_and_seals
verify_dry_run_gate
[[ "$EUID" -eq 0 ]] || die 66 \
    "launch manually with sudo; this script never acquires or reuses a Codex sudo ticket"
[[ "${SUDO_UID-}" =~ ^[0-9]+$ && "${SUDO_UID}" -ne 0 ]] || die 67 \
    "a non-root human operator identity in SUDO_UID is required"

# Root preflight is read-only with respect to the sensor and performs no libusb call.
# D239 supplies the repository import root explicitly; direct script invocation alone
# was the D238 incident root cause.
PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
PYTHONDONTWRITEBYTECODE=1 \
    python3 "$PREFLIGHT_SOURCE" || die 69 \
    "root preflight failed; no live USB execution was started"
PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
PYTHONDONTWRITEBYTECODE=1 \
    python3 -c \
    'import json,sys; r=json.load(open(sys.argv[1])); assert r["status"]=="pass"; assert r["no_libusb_init"] is True; assert r["usb_open_count"]==0; assert r["psk_store_metadata"]["size"]==88' \
    "$PREFLIGHT_REPORT" || die 69 "preflight report gates did not validate"

[[ ! -e "$AUTHORIZATION_MARKER" ]] || die 70 \
    "this operator authorization was already consumed; a second invocation requires renewed review and authorization"

temporary_directory="$(mktemp -d /tmp/d239-live-pre-d1.XXXXXX)"
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
        printf 'D239 operator kit: CRITICAL source reseal failure; stop all further use\n' >&2
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
grep -Fq 'return None' "$BACKEND_SOURCE" || die 71 "backend unseal verification failed"
grep -Fq 'D235_RESULT_SCHEMA = "d238-live-single-shot-result-v1"' "$ENTRYPOINT_SOURCE" || \
    die 71 "entrypoint unseal verification failed"

# The existing D238 single-use marker is preserved: D239 fixes executability but
# does not widen the authorization or single-use contract.
( set -o noclobber; printf 'D239 human-authorized single invocation\n' > "$AUTHORIZATION_MARKER" ) || \
    die 70 "operator authorization marker could not be claimed"
chmod 0600 "$AUTHORIZATION_MARKER"

# Exactly one live entrypoint invocation. D4, application data, FDT, capture,
# enrollment, retry, reset, and invasive recovery remain unreachable.
set +e
PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
PYTHONDONTWRITEBYTECODE=1 \
    python3 -m src.goodix5125_d235_entrypoint > "$live_stdout"
live_status="$?"
set -e

reseal_source || die 90 "source reseal failed after the live invocation"

if [[ "$live_status" -eq 0 ]]; then
    printf 'D239 operator kit: one-shot pre-D1 TLS handshake completed; source resealed\n'
else
    printf 'D239 operator kit: one-shot attempt stopped with exit %s; source resealed; no retry authorized\n' \
        "$live_status" >&2
fi
exit "$live_status"
