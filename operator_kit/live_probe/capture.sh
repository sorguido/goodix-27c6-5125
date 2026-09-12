#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

lp_signal_safe_tee () (
  trap '' HUP INT TERM
  exec tee "$1"
)

lp_signal_safe_filter () (
  trap '' HUP INT TERM
  exec "$@"
)

lp_journal_enabled () {
  [[ ${COLLECT_JOURNAL:-false} == true ]] || return 1
  [[ ${LIVE_PROBE_MODE:-} == operator-run || ${COLLECT_JOURNAL_OFFLINE:-false} == true ]]
}

lp_make_capture () {
  local stamp short
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  short=$(git -C "$LP_GIT_ROOT" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)
  LP_CAPTURE_DIR="$LP_CAPTURE_ROOT/${EXPERIMENT_ID}_${stamp}_${short}/sanitized"
  mkdir -p "$LP_CAPTURE_DIR"
  chmod 0700 "$(dirname "$LP_CAPTURE_DIR")" "$LP_CAPTURE_DIR"
}

lp_capture_cursor () {
  local output cursor
  lp_journal_enabled || return 0
  output=$(LC_ALL=C journalctl -b -n 0 --show-cursor --no-pager 2>&1) || return 1
  cursor=$(printf '%s\n' "$output" | sed -n 's/^-- cursor: //p')
  [[ $(printf '%s\n' "$cursor" | sed '/^$/d' | wc -l) -eq 1 ]] || return 1
  LP_JOURNAL_CURSOR=$cursor
  printf 'LIVE_PROBE_JOURNAL_CURSOR=%s\n' "$cursor" >"$LP_CAPTURE_DIR/journal-context.env"
}

lp_collect_journal () {
  local -a command units
  lp_journal_enabled || return 0
  command=(journalctl -b --after-cursor "$LP_JOURNAL_CURSOR" --no-pager -o short-iso-precise)
  read -r -a units <<<"${JOURNAL_UNITS:-}"
  local unit
  for unit in "${units[@]}"; do command+=(-u "$unit"); done
  [[ -z ${JOURNAL_GREP_REGEX:-} ]] || command+=(--grep "$JOURNAL_GREP_REGEX")
  if [[ -n ${SANITIZER:-} ]]; then
    "${command[@]}" 2>&1 | lp_signal_safe_filter "$LP_EXPERIMENT_DIR/$SANITIZER" |
      lp_signal_safe_tee "$LP_CAPTURE_DIR/diagnostic-journal.log"
    local status=("${PIPESTATUS[@]}")
    [[ ${status[0]} -eq 0 && ${status[1]} -eq 0 && ${status[2]} -eq 0 ]]
  else
    "${command[@]}" 2>&1 | lp_signal_safe_tee "$LP_CAPTURE_DIR/diagnostic-journal.log"
    local status=("${PIPESTATUS[@]}")
    [[ ${status[0]} -eq 0 && ${status[1]} -eq 0 ]]
  fi
}

lp_run_hook () {
  local hook=$1 phase=$2 output=$3
  [[ -n $hook ]] || return 0
  if [[ -n ${SANITIZER:-} ]]; then
    "$LP_EXPERIMENT_DIR/$hook" --phase "$phase" 2>&1 |
      lp_signal_safe_filter "$LP_EXPERIMENT_DIR/$SANITIZER" | lp_signal_safe_tee "$output"
    local status=("${PIPESTATUS[@]}")
    [[ ${status[0]} -eq 0 && ${status[1]} -eq 0 && ${status[2]} -eq 0 ]]
  else
    "$LP_EXPERIMENT_DIR/$hook" --phase "$phase" 2>&1 |
      lp_signal_safe_tee "$output"
    local status=("${PIPESTATUS[@]}")
    [[ ${status[0]} -eq 0 && ${status[1]} -eq 0 ]]
  fi
}

lp_finalize_hashes () {
  (
    cd "$LP_CAPTURE_DIR"
    find . -maxdepth 1 -type f ! -name capture.sha256 -print0 |
      sort -z | xargs -0 sha256sum >capture.sha256
    chmod 0600 ./*
  )
}
