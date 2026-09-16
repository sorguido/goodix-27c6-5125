#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
ENTRYPOINT="$REPO/tools/d268_live_first_image_once.py"
[[ -f "$ENTRYPOINT" ]] || { echo "D268 BLOCCATO: programma del Kit mancante" >&2; exit 1; }

case "${1-}:$#" in
  --dry-run:1|--i-authorize-one-d268-first-image-live-attempt:1) ;;
  *) echo "D268 BLOCCATO: usa esclusivamente --dry-run oppure il flag live D268 autorizzato" >&2; exit 2 ;;
esac
exec env PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" python3 "$ENTRYPOINT" "$1"
