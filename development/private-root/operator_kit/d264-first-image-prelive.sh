#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
ENTRYPOINT="$REPO/tools/d264_first_image_prelive.py"
[[ -f "$ENTRYPOINT" ]] || { echo "D264_03_FAIL_CLOSED: entrypoint missing" >&2; exit 1; }

if [[ "${1-}" != "--dry-run" || $# -ne 1 ]]; then
    echo "HARD_DISABLED_D264_03: only --dry-run is available" >&2
    exit 2
fi
exec env PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" python3 "$ENTRYPOINT" --dry-run
