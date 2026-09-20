#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Developer-only offline evidence. Never reads the installed protected bundle.
set -euo pipefail
umask 077
[[ $# == 0 && $EUID != 0 ]] || exit 2
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
fixture=$root/development/private-root/analysis/D232/D232_target_material_manifest.json
# Already versioned analysis metadata, qualified by D232_target_material_provenance.md.
# This is the exact manifest pin in the e61fce3 D293 loader, not a host-file hash.
[[ $(sha256sum "$fixture" | cut -d' ' -f1) == 1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15 ]]
work=$(mktemp -d /tmp/goodix-manifest-build.XXXXXX)
trap 'rm -f -- "$work/normal" "$work/sanitizer"; rmdir -- "$work"' EXIT
flatpak run --user --unshare=network --filesystem="$root:ro" --filesystem="$work" \
  --command=bash org.freedesktop.Sdk//25.08 -c '
  set -euo pipefail
  root=$1; here=$2; fixture=$3; work=$4
  read -ra cflags <<< "$(pkg-config --cflags glib-2.0 openssl)"
  read -ra libs <<< "$(pkg-config --libs glib-2.0 openssl)"
  flags=(-std=gnu11 -g -Wall -Wextra -Werror -Wformat=2 -Wshadow -Wconversion)
  for mode in normal sanitizer; do
    extra=(-O2)
    if [[ $mode == sanitizer ]]; then
      extra=(-O1 -fno-omit-frame-pointer -fsanitize=address,undefined)
    fi
    gcc "${flags[@]}" "${extra[@]}" "${cflags[@]}" -I"$root/libfprint-driver" \
      "$root/libfprint-driver/goodix_d190_binder.c" \
      "$root/libfprint-driver/goodix_target_material.c" \
      "$here/test_material_boundary.c" "${libs[@]}" -o "$work/$mode"
    # LeakSanitizer cannot inspect threads in this SDK/ptrace environment.
    # Match the existing material suite: ASan/UBSan, no leak-check claim.
    ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
      timeout 30 "$work/$mode" "$fixture"
    printf "MATERIAL_BOUNDARY_%s=PASS\n" "$mode"
  done
  ' bash "$root" "$here" "$fixture" "$work"
