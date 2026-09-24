#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# == 1 && $EUID != 0 && $1 == /* && ! -L $1 ]] || exit 2
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
[[ $(git -C "$root" branch --show-current) == development ]] || exit 2
[[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || {
  echo 'Commit source changes before preparing.' >&2; exit 2;
}
mkdir -p "$1"
[[ -O $1 && -z $(find "$1" -mindepth 1 -maxdepth 1 -print -quit) ]] || exit 2
out=$(realpath "$1")
(cd "$root" && sha256sum -c production/polkit/source.sha256)
"$root/production/polkit/build.sh" "$out/build"
install -m 0644 "$out/build/pam_goodix_polkit.so" "$out/pam_goodix_polkit.so"
printf 'SOURCE_COMMIT=%s\nPURPOSE=POLKIT_INTERRUPTIBLE_SERVICE_LOCAL_V1\n' \
  "$(git -C "$root" rev-parse HEAD)" > "$out/PROVENANCE"
(cd "$out" && sha256sum pam_goodix_polkit.so PROVENANCE > SHA256SUMS)
cat "$out/PROVENANCE"
echo "POLKIT_PREPARE=PASS candidate=$out"
