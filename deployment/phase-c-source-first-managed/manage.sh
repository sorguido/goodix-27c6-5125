#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
fail() { printf 'PHASE_C_MANAGE=FAIL reason=%s\n' "$1" >&2; exit 1; }
[[ $EUID -ne 0 ]] || fail entrypoint_must_be_unprivileged
caller=$(id -un)
[[ $caller =~ ^[a-z_][a-z0-9_-]*$ ]] || fail caller_invalid
runtime_root=/usr/lib64/goodix-27c6-5125

ensure_runtime_root_mode() {
  local mode
  [[ -e $runtime_root || -L $runtime_root ]] || return 0
  [[ -d $runtime_root && ! -L $runtime_root ]] || fail runtime_root_invalid
  [[ $(stat -c '%u:%g' "$runtime_root") == 0:0 ]] || fail runtime_root_owner_invalid
  mode=$(stat -c '%a' "$runtime_root")
  case $mode in
    755) return 0 ;;
    700)
      sudo -- chmod 0755 "$runtime_root" || fail runtime_root_mode_fix_failed
      [[ $(stat -c '%a' "$runtime_root") == 755 ]] || fail runtime_root_mode_fix_failed
      ;;
    *) fail runtime_root_mode_unexpected ;;
  esac
}

case ${1:-} in
  prepare)
    [[ $# -eq 2 ]] || fail usage_prepare
    exec "$here/prepare.sh" "$2"
    ;;
  install|update)
    [[ $# -eq 2 && $2 == /* ]] || fail usage_install_or_update
    sudo -- "$here/root-transaction.sh" "--root-$1" "$caller" "$2"
    ensure_runtime_root_mode
    ;;
  status)
    [[ $# -eq 1 ]] || fail usage_status
    ensure_runtime_root_mode
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
