#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
[[ $EUID != 0 && $# == 0 ]] || { echo 'Run ./rollback.sh as your normal user, without arguments.' >&2; exit 2; }
sudo -- python3 "$here/transaction.py" rollback
