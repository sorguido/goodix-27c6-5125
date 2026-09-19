#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
[[ $# == 1 && $EUID != 0 && $1 == /* && $1 != / && ! -L $1 ]] || exit 2
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
[[ $(git -C "$root" branch --show-current) == development ]] || exit 2
[[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || { echo 'Commit source changes before preparing.' >&2; exit 2; }
out=$1
mkdir -p "$out"
[[ -O $out && -z $(find "$out" -mindepth 1 -maxdepth 1 -print -quit) ]] || exit 2
mkdir "$out/source" "$out/candidate"
# Same canonical behavior; retain only the installed development material ABI.
git -C "$root" archive HEAD production libfprint-driver reference/libfprint-fedora44-1.94.100 reference/fprintd-fedora44-1.94.5 Rockytkg/libfprint/libfprint/sigfm | tar -x -C "$out/source"
loader=e61fce313794922a2dab156a1b38a8ddc5837f19
for file in goodix_target_material.c goodix_target_material.h goodix_runtime_material.c goodix_runtime_inputs.c; do
  git -C "$root" show "$loader:libfprint-driver/$file" > "$out/source/libfprint-driver/$file"
done
python3 - "$out/source" <<'PY'
from pathlib import Path
import hashlib, sys
r = Path(sys.argv[1]); p = r / 'production/source-files.sha256'
p.write_text(''.join(f'{hashlib.sha256((r / line.split()[1]).read_bytes()).hexdigest()}  {line.split()[1]}\n' for line in p.read_text().splitlines()))
PY
ln -s "$root/GoodixArtifacts" "$out/source/GoodixArtifacts"
"$out/source/production/build.sh" normal "$out/build"
for file in libfprint-2.so.2.0.0 fprintd pam_fprintd.so; do cp "$out/build/$file" "$out/candidate/$file"; done
cp "$out/source/production/source-files.sha256" "$out/candidate/source-files.sha256"
{
  printf 'SOURCE_COMMIT=%s\nMATERIAL_LOADER_BASE=%s\nMODE=normal\nPURPOSE=PREPARED_LOGIN_THREE_ATTEMPTS\n' "$(git -C "$root" rev-parse HEAD)" "$loader"
  sha256sum "$root/production/login/"{fprintd.patch,fprintd-cleanup.patch,fprintd-attempts.patch,source.sha256}
} > "$out/candidate/PROVENANCE"
(cd "$out/candidate" && sha256sum libfprint-2.so.2.0.0 fprintd pam_fprintd.so PROVENANCE source-files.sha256 > SHA256SUMS)
echo "LOGIN_THREE_PREPARE=PASS candidate=$out/candidate"
