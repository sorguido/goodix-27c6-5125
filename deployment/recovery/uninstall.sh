#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
test "$#" -eq 0
exec /usr/bin/python3 -I -B "$(dirname -- "$(realpath -- "$0")")/manage.py" uninstall
