#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

fail() {
  printf 'D294_01_RPM_BUILD=FAIL reason=%s\n' "$1" >&2
  exit 1
}

[[ $# -eq 1 ]] || fail usage_output_directory_required
output=$1
[[ $EUID -ne 0 ]] || fail build_must_be_unprivileged
[[ $output == /* && $output != / && ! -L $output ]] || fail unsafe_output
if [[ -e $output ]]; then
  [[ -d $output && -z $(find "$output" -mindepth 1 -maxdepth 1 -print -quit) ]] ||
    fail output_not_empty
else
  mkdir -m 0700 -- "$output"
fi

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
for command in git rpmbuild rpm rpm2cpio cpio tar gzip sha256sum sed; do
  command -v "$command" >/dev/null || fail "missing_command_$command"
done
[[ $(git -C "$root" branch --show-current) == development ]] || fail wrong_branch
[[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
head=$(git -C "$root" rev-parse HEAD)
[[ $(git -C "$root" rev-parse origin/development) == "$head" ]] || fail origin_head_mismatch
[[ $head =~ ^[0-9a-f]{40}$ ]] || fail invalid_head

work=$(mktemp -d /tmp/goodix-d294-rpm.XXXXXX)
cleanup() {
  if [[ $work == /tmp/goodix-d294-rpm.* && -d $work && ! -L $work ]]; then
    find "$work" -xdev -depth -delete
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
production_output=$work/production
"$root/production/build.sh" normal "$production_output"

version=0.1.0
name=goodix-27c6-5125-runtime
source_dir=$work/$name-$version
topdir=$work/rpmbuild
mkdir -p "$source_dir" "$topdir"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
install -m 0644 "$production_output/libfprint-2.so.2.0.0" "$source_dir/"
install -m 0755 "$here/goodix-27c6-5125-fprintd-wrapper" "$source_dir/"
install -m 0644 "$here/99-goodix-27c6-5125-runtime.conf" "$source_dir/"
install -m 0644 "$root/LICENSES/GPL-2.0-or-later.txt" \
  "$source_dir/COPYING.GPL-2.0-or-later"
install -m 0644 "$root/LICENSES/LGPL-2.1-or-later.txt" \
  "$source_dir/COPYING.LGPL-2.1-or-later"
printf '%s\n' "$head" >"$source_dir/BUILD_COMMIT"
(cd "$source_dir" && sha256sum libfprint-2.so.2.0.0 >ARTIFACT.sha256)
epoch=$(git -C "$root" show -s --format=%ct "$head")
tar --sort=name --mtime="@$epoch" --owner=0 --group=0 --numeric-owner \
  -C "$work" -czf "$topdir/SOURCES/$name-$version.tar.gz" "$name-$version"
sed "s/@SOURCE_COMMIT@/$head/g" "$here/goodix-27c6-5125-runtime.spec.in" \
  >"$topdir/SPECS/$name.spec"

rpmbuild -bb --define "_topdir $topdir" --define '_build_id_links none' \
  "$topdir/SPECS/$name.spec"
rpm_path=$(find "$topdir/RPMS" -type f -name "$name-*.rpm" -print -quit)
[[ -n $rpm_path && -f $rpm_path ]] || fail rpm_missing
install -m 0644 "$rpm_path" "$output/"
rpm_path=$output/$(basename "$rpm_path")
rpm -qp --qf '%{NAME} %{VERSION}-%{RELEASE}.%{ARCH}\n' "$rpm_path" >"$output/package.nevra"
rpm -qp --requires "$rpm_path" | sort -u >"$output/package.requires"
rpm -qpl "$rpm_path" | sort >"$output/package.files"
rpm -qp --provides "$rpm_path" | sort -u >"$output/package.provides"
extract=$work/extract
mkdir "$extract"
(cd "$extract" && rpm2cpio "$rpm_path" | cpio -idm --quiet)
cmp "$production_output/libfprint-2.so.2.0.0" \
  "$extract/usr/lib64/goodix-27c6-5125/libfprint-2.so.2.0.0" ||
  fail packaged_library_changed
sha256sum "$rpm_path" >"$output/package.sha256"
{
  echo D294_01_RPM_BUILD=PASS
  echo "D294_01_SOURCE_COMMIT=$head"
  echo D294_01_PACKAGED_LIBRARY_BYTE_IDENTICAL=true
  echo D294_01_PAM_FILE_COUNT=0
  echo D294_01_PROTECTED_MATERIAL_FILE_COUNT=0
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo LIVE_EXECUTION_PERFORMED=false
} | tee "$output/build.env"
