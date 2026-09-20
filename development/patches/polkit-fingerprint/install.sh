#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# == 0 && $EUID != 0 ]] || { echo 'Run ./install.sh as your normal user.' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
work=$(mktemp -d /tmp/goodix-polkit-install.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
"$here/prepare.sh" "$work"
(cd "$work" && sha256sum -c SHA256SUMS)
sudo -- python3 "$root/production/polkit/deploy.py" install local "$work/pam_goodix_polkit.so"
