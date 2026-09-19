#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077
[[ $# == 1 && $EUID != 0 ]] || { echo 'usage (unprivileged): prepare.sh /absolute/empty/output' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
output=$1
[[ $output == /* && $output != / && ! -L $output ]] || exit 2
mkdir -p -- "$output"
[[ -d $output && -O $output && -z $(find "$output" -mindepth 1 -maxdepth 1 -print -quit) ]] || exit 2
source_base=c0e13ff5f78ac32403a753446dcbc44aa7f30556
installed_base=e61fce313794922a2dab156a1b38a8ddc5837f19
source_dir=$output/source
mkdir "$source_dir"
git -C "$root" archive "$source_base" libfprint-driver production \
  reference/libfprint-fedora44-1.94.100/source \
  Rockytkg/libfprint/libfprint/sigfm | tar -x -C "$source_dir"

# Preserve the installed D293 material format. No material/secret is opened,
# converted or copied: these are the four already-versioned loader sources.
for name in goodix_target_material.c goodix_target_material.h \
            goodix_runtime_material.c goodix_runtime_inputs.c; do
  git -C "$root" show "$installed_base:libfprint-driver/$name" \
    >"$source_dir/libfprint-driver/$name"
done
patch --batch --fuzz=0 -d "$source_dir" -p1 <"$here/same-action.patch"
python3 - "$source_dir" <<'PY'
from pathlib import Path
import hashlib, sys
root = Path(sys.argv[1])
manifest = root / 'production/source-files.sha256'
paths = [line.split()[1] for line in manifest.read_text().splitlines()]
manifest.write_text(''.join(f'{hashlib.sha256((root / p).read_bytes()).hexdigest()}  {p}\n' for p in paths))
PY
ln -s "$root/GoodixArtifacts" "$source_dir/GoodixArtifacts"
"$source_dir/production/build.sh" normal "$output/build"
mkdir "$output/candidate"
for name in libfprint-2.so.2.0.0 libgusb.so.2 libopencv_core.so.413 \
            libopencv_features2d.so.413 libopencv_flann.so.413 libopencv_imgproc.so.413; do
  cp "$output/build/$name" "$output/candidate/$name"
done
{
  printf 'RECIPE_COMMIT=%s\nSOURCE_BASE=%s\nMATERIAL_LOADER_BASE=%s\n' \
    "$(git -C "$root" rev-parse HEAD)" "$source_base" "$installed_base"
  printf 'PATCH_SHA256=%s\n' "$(sha256sum "$here/same-action.patch" | cut -d' ' -f1)"
  printf 'PURPOSE=TEMPORARY_SAME_ACTION_LIFT_RECONTACT\n'
  printf 'BUILD_PROTECTED_MATERIAL_READ=false\nBUILD_REAL_USB_ACCESS=false\n'
} >"$output/candidate/PROVENANCE"
cp "$source_dir/production/source-files.sha256" "$output/candidate/source-files.sha256"
(cd "$output/candidate" && sha256sum lib*.so* PROVENANCE source-files.sha256 >SHA256SUMS)
echo "SAME_ACTION_PREPARE=PASS candidate=$output/candidate"
