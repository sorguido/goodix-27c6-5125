#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

# This file is sourced by the D290 audit and payload.  Keep the two predicates
# explicit: the desktop that exists before logout and the desktop created after
# a successful login have different causal roles.
D290_LOGINCTL=${D290_LOGINCTL:-loginctl}

d290_session_value () {
  "$D290_LOGINCTL" show-session "$1" -p "$2" --value 2>/dev/null
}

d290_logged_session_state () {
  [[ $1 == active || $1 == online ]]
}

d290_initial_graphical_session_records () {
  local uid=$1 operator_session=$2 sessions
  local session_id session_uid rest service type class state tty
  sessions=$("$D290_LOGINCTL" list-sessions --no-legend 2>/dev/null) || return 1
  while read -r session_id session_uid rest; do
    [[ -n $session_id ]] || continue
    [[ $session_uid == "$uid" && $session_id != "$operator_session" ]] || continue
    service=$(d290_session_value "$session_id" Service) || return 1
    type=$(d290_session_value "$session_id" Type) || return 1
    class=$(d290_session_value "$session_id" Class) || return 1
    state=$(d290_session_value "$session_id" State) || return 1
    tty=$(d290_session_value "$session_id" TTY) || return 1
    if [[ $service == plasmalogin && $type == wayland && $class == user &&
          $tty == tty2 ]] && d290_logged_session_state "$state"; then
      printf '%s|%s|%s|%s|%s|%s\n' "$session_id" "$tty" "$service" "$type" "$class" "$state"
    fi
  done <<<"$sessions"
}

d290_new_graphical_session_records () {
  local uid=$1 operator_session=$2 initial_session=$3 sessions
  local session_id session_uid rest service type class state tty
  sessions=$("$D290_LOGINCTL" list-sessions --no-legend 2>/dev/null) || return 1
  while read -r session_id session_uid rest; do
    [[ -n $session_id ]] || continue
    [[ $session_uid == "$uid" && $session_id != "$operator_session" &&
       $session_id != "$initial_session" ]] || continue
    service=$(d290_session_value "$session_id" Service) || return 1
    type=$(d290_session_value "$session_id" Type) || return 1
    class=$(d290_session_value "$session_id" Class) || return 1
    state=$(d290_session_value "$session_id" State) || return 1
    tty=$(d290_session_value "$session_id" TTY) || return 1
    if [[ $service == plasmalogin && $type == wayland && $class == user &&
          $tty =~ ^tty[0-9]+$ && $tty != tty3 ]] && d290_logged_session_state "$state"; then
      printf '%s|%s|%s|%s|%s|%s\n' "$session_id" "$tty" "$service" "$type" "$class" "$state"
    fi
  done <<<"$sessions"
}

d290_current_graphical_session_records () {
  d290_new_graphical_session_records "$1" "$2" __NO_INITIAL_SESSION__
}
