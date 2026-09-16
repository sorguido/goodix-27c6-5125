#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
ENTRYPOINT="$REPO/tools/d265_live_first_image_once.py"
[[ -f "$ENTRYPOINT" ]] || { echo "D265_FAIL_CLOSED: entrypoint mancante" >&2; exit 1; }

case "${1-}:$#" in
  --dry-run:1|--i-authorize-one-d265-first-image-live-attempt:1) ;;
  *) echo "HARD_DISABLED_DEFAULT: modalità D265 esatta richiesta" >&2; exit 2 ;;
esac
exec env PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" python3 "$ENTRYPOINT" "$1"
