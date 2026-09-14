#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
fail() { printf 'PHASE_C_MANAGE=FAIL reason=%s\n' "$1" >&2; exit 1; }
[[ $EUID -ne 0 ]] || fail entrypoint_must_be_unprivileged
caller=$(id -un)
[[ $caller =~ ^[a-z_][a-z0-9_-]*$ ]] || fail caller_invalid

case ${1:-} in
  prepare)
    [[ $# -eq 2 ]] || fail usage_prepare
    exec "$here/prepare.sh" "$2"
    ;;
  install|update)
    [[ $# -eq 2 && $2 == /* ]] || fail usage_install_or_update
    exec sudo -- "$here/root-transaction.sh" "--root-$1" "$caller" "$2"
    ;;
  status)
    [[ $# -eq 1 ]] || fail usage_status
    exec "$here/root-transaction.sh" --status
    ;;
  rollback|uninstall)
    [[ $# -eq 1 ]] || fail usage_rollback_or_uninstall
    exec sudo -- "$here/root-transaction.sh" "--root-$1" "$caller"
    ;;
  import-materials)
    [[ $# -eq 2 && $2 == /* ]] || fail usage_import_materials
    exec sudo -- "$here/root-transaction.sh" --root-import-materials "$caller" "$2"
    ;;
  *) fail 'usage: manage.sh prepare OUTPUT | install CANDIDATE | update CANDIDATE | status | rollback | uninstall | import-materials SOURCE_DIRECTORY' ;;
esac
