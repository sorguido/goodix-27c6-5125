#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd -P)
[[ $(id -u) -ne 0 ]] || { echo 'Eseguire come utente originale, non come root.' >&2; exit 2; }
printf '%s\n' \
  'Recovery D293/04: il runtime transiente sarà rimosso e il solo account d293-phase-b-test sarà cancellato.' \
  'Il comando rifiuta la cancellazione se la sessione è attiva o se restano impronte: in quel caso rientrare nel test user e cancellarle dal KCM Users.'
pkexec "$here/root-helper.sh" --recover
