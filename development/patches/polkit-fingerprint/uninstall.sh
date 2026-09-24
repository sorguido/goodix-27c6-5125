#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# == 0 && $EUID != 0 ]] || { echo 'Run ./uninstall.sh as your normal user.' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
sudo -- python3 "$root/production/polkit/deploy.py" uninstall local
