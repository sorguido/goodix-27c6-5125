#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
[[ $EUID -ne 0 ]] || {
  echo 'D293_NATIVE_ROLLBACK=FAIL reason=entrypoint_must_be_unprivileged' >&2
  exit 1
}
caller=$(id -un)
[[ $caller =~ ^[a-z_][a-z0-9_-]*$ ]] || {
  echo 'D293_NATIVE_ROLLBACK=FAIL reason=caller_invalid' >&2
  exit 1
}
sudo -- "$here/install.sh" --root-uninstall "$caller"
