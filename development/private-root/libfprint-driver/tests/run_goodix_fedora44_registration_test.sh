#!/bin/sh
# SPDX-License-Identifier: LGPL-2.1-or-later
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <directory-containing-pinned-opencv-rpms>" >&2
  exit 2
fi

# Compatibility entrypoint: D279/52 superseded the NBIS-only D279/03 build.
# The current production-shaped action closure also verifies the exact
# standard driver registry without enumerating or opening USB.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$script_dir/run_goodix_fedora44_nbis_action_test.sh" "$1"
