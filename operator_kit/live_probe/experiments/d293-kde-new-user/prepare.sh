#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

printf '%s\n' \
  'D293_04_PREPARE=BLOCKED' \
  'D293_04_BLOCKER=R7_GUI_SESSION_BUDGET_NOT_ENFORCED_BEFORE_EXTRA_ENROLLSTART' \
  'Il gate è disabilitato: nessuna predisposizione o azione sul sensore è stata avviata.' >&2
exit 3
