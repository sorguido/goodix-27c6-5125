#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
baseline=f609c865f760768edb6a9e404b863ccd0569e1c8
patch_file="$script_dir/patches/0001-goodix-fedora44-production.patch"
work=$(mktemp -d /tmp/goodix-production-check.XXXXXX)
cleanup () {
  if [[ $work == /tmp/goodix-production-check.* && -d $work && ! -L $work ]]; then
    find "$work" -xdev -depth -delete
  fi
}
trap cleanup EXIT INT TERM
generated="$work/generated.patch"
manifest_paths="$work/manifest.paths"
digest_paths="$work/digest.paths"
documented_paths="$work/downstream.paths"
actual_delta="$work/actual-delta.paths"
actual_production_delta="$work/actual-production-delta.paths"

git -C "$root" cat-file -e "$baseline^{commit}"

awk -F '\t' '
  NF != 3 || $1 == "" || $2 == "" || $3 == "" { exit 1 }
  { print $1 }
' "$script_dir/source-files.tsv" >"$manifest_paths" || {
  echo "source-files.tsv non valido" >&2
  exit 1
}
awk '
  NF != 2 || $1 !~ /^[0-9a-f]{64}$/ || $2 == "" { exit 1 }
  { print $2 }
' "$script_dir/source-files.sha256" >"$digest_paths" || {
  echo "source-files.sha256 non valido" >&2
  exit 1
}
[[ $(wc -l <"$manifest_paths") -eq $(sort -u "$manifest_paths" | wc -l) ]] || {
  echo "path duplicato in source-files.tsv" >&2; exit 1;
}
[[ $(wc -l <"$digest_paths") -eq $(sort -u "$digest_paths" | wc -l) ]] || {
  echo "path duplicato in source-files.sha256" >&2; exit 1;
}
cmp <(sort "$manifest_paths") <(sort "$digest_paths") || {
  echo "path-set manifest/digest differente" >&2; exit 1;
}
while IFS= read -r path; do
  case "$path" in
    ""|/*|.|..|../*|*/../*|*/..)
      echo "path source non sicuro: $path" >&2; exit 1 ;;
  esac
  [[ -f "$root/$path" && ! -L "$root/$path" ]] || {
    echo "source non è un file regolare: $path" >&2; exit 1;
  }
  git -C "$root" ls-files --error-unmatch -- "$path" >/dev/null || {
    echo "source non versionato: $path" >&2; exit 1;
  }
done <"$manifest_paths"
tu_count=$(awk '/\.(c|cpp)$/ { count++ } END { print count + 0 }' "$manifest_paths")
header_count=$(awk '/\.(h|hpp)$/ { count++ } END { print count + 0 }' "$manifest_paths")
[[ $tu_count -eq 30 && $header_count -eq 32 &&
   $(wc -l <"$manifest_paths") -eq 62 ]] || {
  echo "conteggio sorgenti production inatteso" >&2; exit 1;
}
if grep -E '^(analysis/|operator_kit/|tests/)|/tests/' "$manifest_paths"; then
  echo "prefix vietato nella source manifest" >&2
  exit 1
fi

mapfile -t paths <"$script_dir/downstream-paths.txt"
printf '%s\n' "${paths[@]}" >"$documented_paths"
[[ ${#paths[@]} -eq 15 &&
   $(wc -l <"$documented_paths") -eq $(sort -u "$documented_paths" | wc -l) ]] || {
  echo "downstream-paths deve contenere 15 path unici" >&2; exit 1;
}
while IFS= read -r path; do
  case "$path" in
    ""|/*|.|..|../*|*/../*|*/..)
      echo "path downstream non sicuro: $path" >&2; exit 1 ;;
  esac
  [[ -f "$root/$path" && ! -L "$root/$path" ]] || {
    echo "downstream input non è un file regolare: $path" >&2; exit 1;
  }
  git -C "$root" ls-files --error-unmatch -- "$path" >/dev/null || {
    echo "downstream input non versionato: $path" >&2; exit 1;
  }
done <"$documented_paths"
git -C "$root" diff --name-only "$baseline" -- \
  reference/libfprint-fedora44-1.94.100/source >"$actual_delta"
grep -vFx 'reference/libfprint-fedora44-1.94.100/source/tests/meson.build' \
  "$actual_delta" >"$actual_production_delta"
[[ $(wc -l <"$actual_delta") -eq 16 ]] || {
  echo "delta Fedora completo inatteso" >&2; exit 1;
}
[[ $(grep -Fx 'reference/libfprint-fedora44-1.94.100/source/tests/meson.build' \
     "$actual_delta" | wc -l) -eq 1 ]] || {
  echo "delta test-only Fedora inatteso" >&2; exit 1;
}
cmp <(sort "$documented_paths") <(sort "$actual_production_delta") || {
  echo "downstream-paths non coincide col delta production" >&2; exit 1;
}
git -C "$root" diff --full-index --binary --no-ext-diff --no-renames \
  "$baseline" -- "${paths[@]}" >"$generated"
# Git preserves whitespace on context lines; normalize the generated artifact
# so the versioned patch itself remains diff-check clean without changing what
# `patch` applies.
sed -i 's/[[:space:]]$//' "$generated"
cmp "$generated" "$patch_file"
(cd "$root" && sha256sum -c production/source-files.sha256)
(cd "$script_dir/build-support" && sha256sum -c SHA256SUMS)

legacy_policy=GOODIX_D
legacy_policy="${legacy_policy}282_DIRECT_ENROLL_PROFILE"
if grep -n -F -- "$legacy_policy" \
     "$root/libfprint-driver/goodix_fpimage_device.c" \
     "$root/libfprint-driver/goodix_fpimage_device.h" \
     "$script_dir/build.sh" "$script_dir/build-inner.sh"; then
  echo "historical build-policy identifier remains canonical" >&2
  exit 1
fi
if grep -n -F -- 'GOODIX_PRODUCTION_DIRECT_ENROLL_PROFILE' \
     "$root/libfprint-driver/goodix_fpimage_device.c" \
     "$root/libfprint-driver/goodix_fpimage_device.h" \
     "$script_dir/build.sh" "$script_dir/build-inner.sh"; then
  echo "superseded direct-enroll policy remains canonical" >&2
  exit 1
fi
grep -n -F -- 'GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE' \
  "$root/libfprint-driver/goodix_fpimage_device.c" \
  "$script_dir/build-inner.sh" >/dev/null

echo PRODUCTION_PATCH_REGENERATION_CHECK=PASS
echo PRODUCTION_SOURCE_DIGEST_CHECK=PASS
echo PRODUCTION_BUILD_SUPPORT_DIGEST_CHECK=PASS
echo PRODUCTION_SOURCE_MANIFEST_PATH_SET_CHECK=PASS
echo PRODUCTION_SOURCE_TU_COUNT=30
echo PRODUCTION_SOURCE_HEADER_COUNT=32
echo PRODUCTION_SOURCE_FORBIDDEN_PREFIX_COUNT=0
echo PRODUCTION_DOWNSTREAM_PATH_SET_CHECK=PASS
echo PRODUCTION_DOWNSTREAM_PATH_COUNT=15
