#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
work=$(mktemp -d /tmp/goodix-production-check.XXXXXX)
cleanup () {
  if [[ $work == /tmp/goodix-production-check.* && -d $work && ! -L $work ]]; then
    find "$work" -xdev -depth -delete
  fi
}
trap cleanup EXIT INT TERM

manifest_paths="$work/manifest.paths"
digest_paths="$work/digest.paths"
awk -F '\t' '
  NF != 3 || $1 == "" || $2 == "" || $3 == "" { exit 1 }
  { print $1 }
' "$script_dir/source-files.tsv" >"$manifest_paths" || {
  echo "invalid source-files.tsv" >&2; exit 1;
}
awk '
  NF != 2 || $1 !~ /^[0-9a-f]{64}$/ || $2 == "" { exit 1 }
  { print $2 }
' "$script_dir/source-files.sha256" >"$digest_paths" || {
  echo "invalid source-files.sha256" >&2; exit 1;
}
[[ $(wc -l <"$manifest_paths") -eq $(sort -u "$manifest_paths" | wc -l) ]] || {
  echo "duplicate source manifest path" >&2; exit 1;
}
cmp <(sort "$manifest_paths") <(sort "$digest_paths") || {
  echo "source manifest and digest path sets differ" >&2; exit 1;
}
while IFS= read -r path; do
  case "$path" in
    ""|/*|.|..|../*|*/../*|*/..|red_tag/*|development/*|analysis/*|captures/*|operator_kit/*)
      echo "unsafe or private source path: $path" >&2; exit 1 ;;
  esac
  [[ -f "$root/$path" && ! -L "$root/$path" ]] || {
    echo "source is not a regular file: $path" >&2; exit 1;
  }
done <"$manifest_paths"

tu_count=$(awk '/\.(c|cpp)$/ { count++ } END { print count + 0 }' "$manifest_paths")
header_count=$(awk '/\.(h|hpp)$/ { count++ } END { print count + 0 }' "$manifest_paths")
[[ $tu_count -eq 30 && $header_count -eq 32 &&
   $(wc -l <"$manifest_paths") -eq 62 ]] || {
  echo "unexpected production source counts" >&2; exit 1;
}
(cd "$root" && sha256sum -c production/source-files.sha256)
(cd "$script_dir/build-support" && sha256sum -c SHA256SUMS)

for required in \
  reference/libfprint-fedora44-1.94.100/source/meson.build \
  reference/libfprint-fedora44-1.94.100/source/meson_options.txt \
  reference/libfprint-fedora44-1.94.100/source/libfprint/meson.build \
  reference/libfprint-fedora44-1.94.100/source/libfprint/libfprint.ver; do
  [[ -f "$root/$required" && ! -L "$root/$required" ]] || {
    echo "missing public libfprint source: $required" >&2; exit 1;
  }
done

meson_file="$root/reference/libfprint-fedora44-1.94.100/source/libfprint/meson.build"
grep -F "../../../../libfprint-driver/goodix_fpimage_device.c" "$meson_file" >/dev/null
grep -F "../../../../Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp" "$meson_file" >/dev/null
if grep -E '(^|[/.])(red_tag|development)(/|$)' \
    "$meson_file" "$script_dir/build.sh" "$script_dir/build-inner.sh"; then
  echo "production path depends on a private or superseded tree" >&2; exit 1
fi

legacy_policy=GOODIX_D
legacy_policy="${legacy_policy}282_DIRECT_ENROLL_PROFILE"
if grep -F "$legacy_policy" \
     "$root/libfprint-driver/goodix_fpimage_device.c" \
     "$root/libfprint-driver/goodix_fpimage_device.h" \
     "$script_dir/build.sh" "$script_dir/build-inner.sh"; then
  echo "historical build-policy identifier remains canonical" >&2; exit 1
fi
if grep -F 'GOODIX_PRODUCTION_DIRECT_ENROLL_PROFILE' \
     "$root/libfprint-driver/goodix_fpimage_device.c" \
     "$root/libfprint-driver/goodix_fpimage_device.h" \
     "$script_dir/build.sh" "$script_dir/build-inner.sh"; then
  echo "superseded direct-enroll policy remains canonical" >&2; exit 1
fi
grep -F 'GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE' \
  "$root/libfprint-driver/goodix_fpimage_device.c" \
  "$script_dir/build-inner.sh" >/dev/null

echo PRODUCTION_SOURCE_DIGEST_CHECK=PASS
echo PRODUCTION_BUILD_SUPPORT_DIGEST_CHECK=PASS
echo PRODUCTION_SOURCE_MANIFEST_PATH_SET_CHECK=PASS
echo PRODUCTION_SOURCE_TU_COUNT=30
echo PRODUCTION_SOURCE_HEADER_COUNT=32
echo PRODUCTION_PRIVATE_TREE_DEPENDENCY_COUNT=0
