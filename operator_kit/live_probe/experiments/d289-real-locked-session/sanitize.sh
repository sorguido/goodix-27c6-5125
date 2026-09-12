#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
user=${USER:-}
if [[ -n $user ]]; then
  sed -E "s/${user//\//\\/}/<USER>/g; s#/tmp/goodix-live-probe\.[A-Za-z0-9]+#<PRIVATE_WORK>#g"
else
  sed -E 's#/tmp/goodix-live-probe\.[A-Za-z0-9]+#<PRIVATE_WORK>#g'
fi
