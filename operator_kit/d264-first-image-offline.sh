#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

SCRIPT_DIRECTORY="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
REPOSITORY="$(git -C "$SCRIPT_DIRECTORY" rev-parse --show-toplevel)"
ENTRYPOINT="$REPOSITORY/tools/d264_first_image_offline.py"

[[ -f "$ENTRYPOINT" ]] || { echo "D264_02_FAIL_CLOSED: entrypoint missing" >&2; exit 1; }

case "${1-}" in
    "") boundary="STOP_AFTER_FDT_ARM_ACK" ;;
    --stop-after-fdt-arm-ack) boundary="STOP_AFTER_FDT_ARM_ACK" ;;
    --stop-after-first-image) boundary="STOP_AFTER_FIRST_IMAGE" ;;
    *) echo "D264_02_FAIL_CLOSED: unsupported or ambiguous boundary" >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo "D264_02_FAIL_CLOSED: exactly one boundary flag is allowed" >&2; exit 2; }

exec env PYTHONPATH="$REPOSITORY${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$ENTRYPOINT" --terminal-boundary "$boundary"
