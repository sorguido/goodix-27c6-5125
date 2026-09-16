#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
exec env PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" python3 "$REPO/tools/d275_live_second_b0_once.py" "$@"
