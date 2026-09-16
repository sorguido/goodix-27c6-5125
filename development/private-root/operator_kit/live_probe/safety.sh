#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

lp_fail () {
  echo "LIVE_PROBE_ERROR=$1" >&2
  return 1
}

lp_is_uint () {
  [[ ${1:-} =~ ^[0-9]+$ ]]
}

lp_is_bool () {
  [[ ${1:-} == true || ${1:-} == false ]]
}

lp_configure_timeout_options () {
  local mode=$1
  LP_TIMEOUT_OPTIONS=(--signal=TERM --kill-after=5s)
  if [[ ${PAYLOAD_REQUIRES_FOREGROUND_TTY:-false} == true && $mode == --operator-run ]]; then
    LP_TIMEOUT_OPTIONS+=(--foreground)
  fi
}

lp_validate_config () {
  local key
  for key in EXPERIMENT_ID GOAL ACTION PAYLOAD MAX_ACTIONS MAX_CONTACTS \
    MAX_RETRIES TIMEOUT_SECONDS REQUIRES_ROOT REQUIRES_ACTIVE_USER_SESSION \
    LIVE_CAPABLE OFFLINE_TEST_CAPABLE OUTPUT_IS_SANITIZED EXPECTED_TELEMETRY STOP_CONDITIONS; do
    [[ -n ${!key:-} ]] || lp_fail "CONFIG_MISSING_${key}" || return
  done
  [[ $EXPERIMENT_ID =~ ^[a-z0-9][a-z0-9._-]*$ ]] ||
    lp_fail CONFIG_EXPERIMENT_ID_INVALID || return
  for key in MAX_ACTIONS MAX_CONTACTS MAX_RETRIES TIMEOUT_SECONDS; do
    lp_is_uint "${!key}" || lp_fail "CONFIG_${key}_INVALID" || return
  done
  [[ $MAX_ACTIONS -ge 0 && $MAX_CONTACTS -ge 0 && $MAX_RETRIES -eq 0 &&
     $TIMEOUT_SECONDS -ge 1 ]] || lp_fail CONFIG_BUDGET_INVALID || return
  for key in REQUIRES_ROOT REQUIRES_ACTIVE_USER_SESSION LIVE_CAPABLE OFFLINE_TEST_CAPABLE OUTPUT_IS_SANITIZED; do
    lp_is_bool "${!key}" || lp_fail "CONFIG_${key}_INVALID" || return
  done
  if [[ -n ${PAYLOAD_REQUIRES_FOREGROUND_TTY:-} ]]; then
    lp_is_bool "$PAYLOAD_REQUIRES_FOREGROUND_TTY" ||
      lp_fail CONFIG_PAYLOAD_REQUIRES_FOREGROUND_TTY_INVALID || return
  fi
  [[ $PAYLOAD != /* && $PAYLOAD != *..* ]] || lp_fail CONFIG_PAYLOAD_PATH_INVALID || return
  [[ -x $LP_EXPERIMENT_DIR/$PAYLOAD ]] || lp_fail PAYLOAD_NOT_EXECUTABLE || return
  if [[ -n ${SANITIZER:-} ]]; then
    [[ $SANITIZER != /* && $SANITIZER != *..* && -x $LP_EXPERIMENT_DIR/$SANITIZER ]] ||
      lp_fail SANITIZER_INVALID || return
  else
    [[ $OUTPUT_IS_SANITIZED == true ]] || lp_fail SANITIZER_REQUIRED || return
  fi
  for key in PRE_AUDIT POST_AUDIT CLEANUP CLASSIFIER; do
    [[ -z ${!key:-} ]] && continue
    [[ ${!key} != /* && ${!key} != *..* && -x $LP_EXPERIMENT_DIR/${!key} ]] ||
      lp_fail "${key}_INVALID" || return
  done
}

lp_git_gate () {
  local branch head origin dirty
  local -a critical=(operator_kit/live_probe)
  branch=$(git -C "$LP_GIT_ROOT" branch --show-current) || return 1
  [[ $branch == development ]] || lp_fail GIT_BRANCH_NOT_DEVELOPMENT || return
  head=$(git -C "$LP_GIT_ROOT" rev-parse HEAD) || return 1
  origin=$(git -C "$LP_GIT_ROOT" rev-parse origin/development) || return 1
  [[ $head == "$origin" ]] || lp_fail GIT_HEAD_ORIGIN_MISMATCH || return
  if declare -p LIVE_CRITICAL_PATHS 2>/dev/null | grep -q 'declare -a'; then
    critical+=("${LIVE_CRITICAL_PATHS[@]}")
  fi
  dirty=$(git -C "$LP_GIT_ROOT" status --porcelain=v1 --untracked-files=all -- \
    "${critical[@]}" 2>/dev/null) ||
    lp_fail GIT_CRITICAL_STATUS_UNREADABLE || return
  [[ -z $dirty ]] || {
    printf '%s\n' "$dirty" >&2
    lp_fail GIT_LIVE_CRITICAL_SET_DIRTY
  }
}

lp_runtime_gate () {
  if [[ $REQUIRES_ROOT == false && ${EUID:-$(id -u)} -eq 0 ]]; then
    lp_fail ROOT_EXECUTION_FORBIDDEN
    return
  fi
  if [[ $REQUIRES_ACTIVE_USER_SESSION == true ]]; then
    [[ ${XDG_SESSION_TYPE:-} == wayland || ${XDG_SESSION_TYPE:-} == x11 ]] ||
      lp_fail ACTIVE_GRAPHICAL_SESSION_REQUIRED || return
    [[ -n ${DBUS_SESSION_BUS_ADDRESS:-} && -n ${XDG_RUNTIME_DIR:-} ]] ||
      lp_fail ACTIVE_USER_RUNTIME_REQUIRED || return
    case "$(awk -F: 'NR==1 {print $NF}' /proc/self/cgroup 2>/dev/null)" in
      /user.slice/user-0.slice/*|/system.slice/*) lp_fail ROOT_BACKGROUND_CGROUP_FORBIDDEN; return ;;
    esac
  fi
}

lp_confirm_operator () {
  local answer
  printf '%s\n' "$GOAL"
  printf 'Limiti: action=%s, contatti=%s, retry=%s, timeout=%ss.\n' \
    "$MAX_ACTIONS" "$MAX_CONTACTS" "$MAX_RETRIES" "$TIMEOUT_SECONDS"
  printf 'Stop conditions: %s\n' "$STOP_CONDITIONS"
  printf 'Per continuare digitare %s: ' "$CONFIRMATION_TEXT"
  IFS= read -r answer || return 1
  [[ $answer == "$CONFIRMATION_TEXT" ]] || lp_fail OPERATOR_CONFIRMATION_REJECTED
}
