#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
awk '
  /GOODIX_/ { sub(/^.*GOODIX_/, "GOODIX_"); print; fflush(); next }
  /D293_04_RUNTIME_AUDIT / {
    sub(/^.*D293_04_RUNTIME_AUDIT /, "D293_04_RUNTIME_AUDIT ")
    print
    fflush()
    next
  }
  {
    gsub(/d293-phase-b-test/, "<TEST_USER>")
    gsub(/\/home\/[A-Za-z_][A-Za-z0-9_-]*/, "<HOME>")
    gsub(/\/tmp\/goodix-[A-Za-z0-9._-]+/, "<PRIVATE_TMP>")
    print
    fflush()
  }
'
