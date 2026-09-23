#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
exec python3 "$(dirname -- "$(realpath -- "$0")")/deploy.py" uninstall "$@"
