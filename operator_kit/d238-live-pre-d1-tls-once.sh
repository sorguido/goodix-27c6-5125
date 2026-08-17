#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly EXPECTED_REPOSITORY="/home/guido/Repository/goodix-27c6-5125"
readonly AUTHORIZATION_ARGUMENT="--i-authorize-one-d238-live-attempt"
readonly AUTHORIZATION_MARKER="/var/lib/goodix-5125-poc/d238-operator-invocation.marker"
readonly PREFLIGHT_REPORT="analysis/D236/D236_preflight_report.json"
readonly OPERATOR_STDOUT="analysis/D238/D238_operator_live_stdout.json"
readonly BACKEND_SOURCE="src/goodix5125_d233_backend.py"
readonly ENTRYPOINT_SOURCE="src/goodix5125_d235_entrypoint.py"
readonly UNSEAL_PATCH="analysis/D238/D238_live_unseal.patch"
readonly EXPECTED_BACKEND_SHA256="7727128ee27337b70ba48eac31b8640c888b76560387363e4eff0c167d993f5b"
readonly EXPECTED_ENTRYPOINT_SHA256="38e857a14bd416808b9ae2df7c4101809879e4732b6e001ce29d11bd731dd555"
readonly EXPECTED_UNSEAL_SHA256="4b243cacf7f0af00d358f1c72c05f0a83f36e22ee3c06d6af8136a8fec742003"

die() {
    local code="$1"
    shift
    printf 'D238 operator kit: %s\n' "$*" >&2
    exit "$code"
}

[[ "${1-}" == "$AUTHORIZATION_ARGUMENT" && "$#" -eq 1 ]] || die 64 \
    "explicit authorization argument required: $AUTHORIZATION_ARGUMENT"
[[ "$(pwd -P)" == "$EXPECTED_REPOSITORY" ]] || die 65 \
    "launch from $EXPECTED_REPOSITORY"
[[ "$EUID" -eq 0 ]] || die 66 \
    "launch manually with sudo; this script never acquires or reuses a Codex sudo ticket"
[[ "${SUDO_UID-}" =~ ^[0-9]+$ && "${SUDO_UID}" -ne 0 ]] || die 67 \
    "a non-root human operator identity in SUDO_UID is required"

sha256_matches() {
    local path="$1"
    local expected="$2"
    [[ "$(sha256sum -- "$path" | awk '{print $1}')" == "$expected" ]]
}

sha256_matches "$BACKEND_SOURCE" "$EXPECTED_BACKEND_SHA256" || die 68 \
    "sealed backend source differs from the reviewed D238 input"
sha256_matches "$ENTRYPOINT_SOURCE" "$EXPECTED_ENTRYPOINT_SHA256" || die 68 \
    "sealed entrypoint source differs from the reviewed D238 input"
sha256_matches "$UNSEAL_PATCH" "$EXPECTED_UNSEAL_SHA256" || die 68 \
    "temporary unseal patch differs from the reviewed D238 patch"

grep -Fq 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' "$BACKEND_SOURCE" || \
    die 68 "backend is not source-sealed"
grep -Fq 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")' "$ENTRYPOINT_SOURCE" || \
    die 68 "entrypoint is not source-sealed"

# Root preflight is read-only with respect to the sensor and performs no libusb call.
PYTHONDONTWRITEBYTECODE=1 python3 analysis/D236/d236_preflight.py || die 69 \
    "root preflight failed; no live USB execution was started"
PYTHONDONTWRITEBYTECODE=1 python3 -c \
    'import json,sys; r=json.load(open(sys.argv[1])); assert r["status"]=="pass"; assert r["no_libusb_init"] is True; assert r["usb_open_count"]==0; assert r["psk_store_metadata"]["size"]==88' \
    "$PREFLIGHT_REPORT" || die 69 "preflight report gates did not validate"

[[ ! -e "$AUTHORIZATION_MARKER" ]] || die 70 \
    "this operator authorization was already consumed; a second invocation requires renewed review and authorization"

temporary_directory="$(mktemp -d /tmp/d238-live-pre-d1.XXXXXX)"
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
        if ! sha256_matches "$BACKEND_SOURCE" "$EXPECTED_BACKEND_SHA256"; then
            restore_status=1
        fi
        if ! sha256_matches "$ENTRYPOINT_SOURCE" "$EXPECTED_ENTRYPOINT_SHA256"; then
            restore_status=1
        fi
        source_resealed=1
    fi
    return "$restore_status"
}

finish() {
    local original_status="$?"
    trap - EXIT INT TERM HUP
    if ! reseal_source; then
        printf 'D238 operator kit: CRITICAL source reseal failure; stop all further use\n' >&2
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

# This marker is never automatically removed. It consumes this human authorization
# even if the Python process terminates before its own single-use marker is claimed.
( set -o noclobber; printf 'D238 human-authorized single invocation\n' > "$AUTHORIZATION_MARKER" ) || \
    die 70 "operator authorization marker could not be claimed"
chmod 0600 "$AUTHORIZATION_MARKER"

# Exactly one live entrypoint invocation. The implementation contains no retry,
# D4, application-data, FDT, capture, enroll, reset or invasive recovery path.
set +e
PYTHONDONTWRITEBYTECODE=1 python3 -m src.goodix5125_d235_entrypoint > "$live_stdout"
live_status="$?"
set -e

reseal_source || die 90 "source reseal failed after the live invocation"

if [[ "$live_status" -eq 0 ]]; then
    printf 'D238 operator kit: one-shot pre-D1 TLS handshake completed; source resealed\n'
else
    printf 'D238 operator kit: one-shot attempt stopped with exit %s; source resealed; no retry authorized\n' \
        "$live_status" >&2
fi
exit "$live_status"
