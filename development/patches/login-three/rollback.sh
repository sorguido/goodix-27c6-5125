#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# == 0 && $EUID != 0 ]] || exit 2
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
sudo -- python3 "$here/transaction.py" rollback
