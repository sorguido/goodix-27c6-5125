#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# == 0 && $EUID != 0 ]] || { echo 'Run ./install.sh as your normal user.' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
work=$(mktemp -d /tmp/goodix-login-three.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
"$here/prepare.sh" "$work"
sudo -- python3 "$here/transaction.py" install "$work/candidate"
