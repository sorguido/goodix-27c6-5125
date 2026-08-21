#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY="$(git -C "$SCRIPT_DIRECTORY/.." rev-parse --show-toplevel)"
readonly DRY_RUN_ARGUMENT="--offline-dry-run"
readonly CLOSURE_SOURCE="$REPOSITORY/analysis/D250/d250_operator_dry_run.py"

if [[ "$SCRIPT_DIRECTORY" != "$REPOSITORY/operator_kit" ]]; then
    printf 'D250_PHASE=LAUNCHER\nD250_RESULT=FAIL\nD250_FAILURE_CLASS=LAUNCHER_OUTSIDE_RESOLVED_REPOSITORY\n' >&2
    exit 65
fi

if [[ "$#" -ne 1 || "${1-}" != "$DRY_RUN_ARGUMENT" ]]; then
    printf 'D250_PHASE=PRE_USB_FENCE\nD250_RESULT=BLOCKED\nD250_FAILURE_CLASS=EXPLICIT_SEPARATE_D250_LIVE_AUTHORIZATION_REQUIRED\nD250_USB_OPEN_COUNT=0\n' >&2
    exit 64
fi

cd -- "$REPOSITORY"
result="$(PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
    python3 "$CLOSURE_SOURCE" "$DRY_RUN_ARGUMENT")"
python3 -c 'import json,sys; r=json.loads(sys.argv[1]); assert r["status"] == "PASS"; assert r["real_usb_open_count"] == 0; assert r["real_af_send_count"] == 0' "$result"
printf '%s\n' \
    'D250_PHASE=EXECUTABLE_CLOSURE' \
    'D250_RESULT=PASS' \
    'D250_FAILURE_CLASS=none' \
    'D250_TERMINAL_BOUNDARY=STOP_AFTER_AF' \
    'D250_SECOND_AF=UNREACHABLE' \
    'D250_FDT_32_20_D2=UNREACHABLE' \
    'D250_LIVE_CAPABILITY=HARD_DISABLED_PENDING_SEPARATE_USER_AUTHORIZATION' \
    'D250_USB_OPEN_COUNT=0' \
    'D250_AF_ATTEMPT_COUNT=0' \
    'D250_AF_SEND_COUNT=0' \
    'D250_RETRY_COUNT=0' \
    'D250_PERSISTENT_WRITE_FAMILY_COUNT=0' \
    'D250_SOURCE_SEAL=ACTIVE'
