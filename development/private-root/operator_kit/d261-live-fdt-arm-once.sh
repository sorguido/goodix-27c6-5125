#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

SCRIPT_DIRECTORY="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
REPOSITORY="$(git -C "$SCRIPT_DIRECTORY" rev-parse --show-toplevel)"
ENTRYPOINT="$REPOSITORY/tools/d261_live_fdt_arm_once.py"

if [[ ! -f "$ENTRYPOINT" ]]; then
    echo "D261_FAIL_CLOSED: entrypoint missing: $ENTRYPOINT" >&2
    exit 1
fi

case "${1-}" in
    --dry-run)
        if [[ $# -ne 1 ]]; then
            echo "D261_FAIL_CLOSED: --dry-run accepts no additional arguments" >&2
            exit 2
        fi
        exec env PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
            python3 "$ENTRYPOINT" --dry-run
        ;;
    --i-authorize-one-d261-fdt-arm-live-attempt)
        if [[ $# -ne 1 ]]; then
            echo "D261_FAIL_CLOSED: live authorization must be the sole argument" >&2
            exit 2
        fi
        if [[ -z "${D261_APPROVED_LIVE_BASELINE_SHA-}" ]]; then
            echo "D261_FAIL_CLOSED: D261_APPROVED_LIVE_BASELINE_SHA is required" >&2
            exit 1
        fi
        exec env PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
            python3 "$ENTRYPOINT" --i-authorize-one-d261-fdt-arm-live-attempt
        ;;
    "")
        echo "D261_HARD_DISABLED_DEFAULT: use --dry-run for offline review" >&2
        exit 2
        ;;
    *)
        echo "D261_FAIL_CLOSED: unsupported argument" >&2
        exit 2
        ;;
esac
