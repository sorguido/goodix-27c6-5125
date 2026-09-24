#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Human/root entrypoint only. Never authenticates or installs the candidate.
set -euo pipefail
[[ $EUID == 0 && $# == 1 && $1 == /* ]] || { echo 'MIGRATION=REFUSED operator_root_and_absolute_policy_required' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec /usr/bin/python3 -I -B "$here/migration.py" --apply "$1"
