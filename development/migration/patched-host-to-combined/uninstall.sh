#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Recover with the saved version, independently of later repository changes.
set -euo pipefail
[[ $EUID == 0 && $# == 0 ]] || { echo 'MIGRATION=REFUSED operator_root_required' >&2; exit 2; }
exec /usr/bin/python3 -I -B /var/lib/goodix-27c6-5125-migration/recovery.py
