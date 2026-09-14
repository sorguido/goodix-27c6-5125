#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

fail() { printf 'PHASE_C_PREPARE=FAIL reason=%s\n' "$1" >&2; exit 1; }
[[ $# -eq 1 ]] || fail usage_prepare_absolute_empty_output
[[ $EUID -ne 0 ]] || fail build_must_be_unprivileged

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
output=$1
[[ $output == /* && $output != / && ! -L $output ]] || fail unsafe_output
if [[ -e $output ]]; then
  [[ -d $output && -O $output && -z $(find "$output" -mindepth 1 -maxdepth 1 -print -quit) ]] ||
    fail output_not_empty_or_not_owned
else
  mkdir -m 0700 -- "$output"
fi

[[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
head=$(git -C "$root" rev-parse HEAD)
[[ $head =~ ^[0-9a-f]{40}$ ]] || fail invalid_source_commit
for command in git sha256sum flatpak rpm2cpio cpio patch nm readelf; do
  command -v "$command" >/dev/null || fail "missing_command_$command"
done

build=$output/build
candidate=$output/candidate
mkdir -m 0700 -- "$build" "$candidate"
"$root/production/build.sh" normal "$build"

install -m 0644 "$build/libfprint-2.so.2.0.0" "$candidate/libfprint-2.so.2.0.0"
install -m 0644 "$build/libgusb.so.2" "$candidate/libgusb.so.2"
for component in core features2d flann imgproc; do
  install -m 0644 "$build/libopencv_${component}.so.413" \
    "$candidate/libopencv_${component}.so.413"
done
install -m 0755 "$here/fprintd-wrapper" "$candidate/fprintd-wrapper"
install -m 0755 "$here/50-goodix-fprint-account-delete" \
  "$candidate/50-goodix-fprint-account-delete"
install -m 0644 "$here/goodix_fprint_account_delete.te" \
  "$candidate/goodix_fprint_account_delete.te"
install -m 0644 "$here/goodix_fprint_account_delete.fc" \
  "$candidate/goodix_fprint_account_delete.fc"
install -m 0644 "$here/99-goodix-27c6-5125-managed.conf" \
  "$candidate/99-goodix-27c6-5125-managed.conf"
install -m 0644 "$root/LICENSE" "$candidate/LICENSE"
install -m 0644 "$root/LICENSES/GPL-2.0-or-later.txt" \
  "$candidate/GPL-2.0-or-later.txt"
install -m 0644 "$root/LICENSES/LGPL-2.1-or-later.txt" \
  "$candidate/LGPL-2.1-or-later.txt"

printf '%s\n' \
  'PHASE_C_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL' \
  'RPM_OFFICIAL_DISTRIBUTION=false' \
  "SOURCE_COMMIT=$head" \
  'TARGET_OS=Fedora-44-KDE-x86_64' \
  'PROTECTED_MATERIAL_INCLUDED=false' \
  'PAM_FILES_INCLUDED=false' \
  >"$candidate/MANIFEST"
(cd "$candidate" && find . -maxdepth 1 -type f ! -name SHA256SUMS -printf '%P\n' | \
  LC_ALL=C sort | xargs -r sha256sum >SHA256SUMS)
(cd "$candidate" && sha256sum -c SHA256SUMS >/dev/null) || fail candidate_digest_failure

printf '%s\n' \
  'PHASE_C_PREPARE=PASS' \
  "SOURCE_COMMIT=$head" \
  "CANDIDATE_DIRECTORY=$candidate" \
  'PROTECTED_MATERIAL_INCLUDED=false' \
  'REAL_USB_ENUMERATION_ATTEMPTED=false' \
  'LIVE_EXECUTION_PERFORMED=false'
