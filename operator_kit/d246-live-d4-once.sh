#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIRECTORY="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPOSITORY="$(git -C "$SCRIPT_DIRECTORY/.." rev-parse --show-toplevel)"

if [[ "$#" -ne 1 || "$1" != "--offline-dry-run" ]]; then
    echo "D246_RESULT=BLOCKED_LIVE_BASELINE_APPROVAL_PENDING_USER_REVIEW" >&2
    echo "D246_SOURCE_SEAL=ACTIVE" >&2
    echo "Only --offline-dry-run is implemented; no live USB path is available." >&2
    exit 64
fi

cd "$REPOSITORY"
grep -Fq 'raise D233LiveUnavailable("D233 USB source is hard-disabled")' \
    src/goodix5125_d233_backend.py
grep -Fq 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")' \
    src/goodix5125_d235_entrypoint.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$REPOSITORY" \
    python3 analysis/D246/d246_operator_dry_run.py >/dev/null

echo "D246_PHASE=EXECUTABLE_CLOSURE"
echo "D246_RESULT=PASS"
echo "D246_LIVE_USB_EXECUTION=NOT_PERFORMED"
echo "D246_SOURCE_SEAL=ACTIVE"
echo "D246_LIVE_BASELINE_APPROVAL=PENDING_USER_REVIEW"
