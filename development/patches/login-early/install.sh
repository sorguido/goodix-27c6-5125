#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
[[ $EUID != 0 ]] || { echo 'Run install.sh as your normal user, without sudo.' >&2; exit 2; }
[[ $# == 0 ]] || { echo 'usage: ./install.sh' >&2; exit 2; }
[[ $(git -C "$root" branch --show-current) == development ]] || exit 2
[[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || {
  echo 'Worktree must be clean before installation.' >&2; exit 2;
}
work=$(mktemp -d /tmp/goodix-early-login-install.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
"$here/prepare.sh" "$work"
sudo -- python3 "$here/transaction.py" install "$work/candidate"
