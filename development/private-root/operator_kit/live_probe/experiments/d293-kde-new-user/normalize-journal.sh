#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

# Input is limited upstream to fprintd.service.  Accept a journal MESSAGE with
# or without its display prefix, but require exactly one machine marker per
# record and emit only the normalized marker.  Missing/ambiguous input fails.
awk '
  BEGIN { records=0 }
  {
    copies=$0
    count=gsub(/GOODIX_PRODUCTION_EPOCH_AUDIT /,
               "GOODIX_PRODUCTION_EPOCH_AUDIT ", copies)
    if (count != 1) exit 2
    sub(/^.*GOODIX_PRODUCTION_EPOCH_AUDIT /,
        "GOODIX_PRODUCTION_EPOCH_AUDIT ")
    if ($0 !~ /^GOODIX_PRODUCTION_EPOCH_AUDIT /) exit 2
    print
    records++
  }
  END { if (records == 0) exit 3 }
'
