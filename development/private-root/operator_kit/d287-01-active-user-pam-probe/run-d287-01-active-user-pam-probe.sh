#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

d287p_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
d287p_root=$(CDPATH= cd -- "$d287p_dir/../.." && pwd)
d287p_d286="$d287p_dir/../d286-01-reboot-survival/run-d286-01.sh"
d287p_source="$d287p_dir/pam-confdir-runner.c"
d287p_pam="$d287p_dir/goodix-d287-01-active-user.pam"
d287p_capture_root="$d287p_root/captures/D287_01"
d287p_source_sha=d5d8e9c59f806cc4898340891515f9a823c126bcff982a0dfc1dbaf11b0e4b98
d287p_runner_sha=fc7e2d5926cea34a9b03c5a6c59792ea88f528cfa6f2181b680aa3602dcf8395
d287p_pam_sha=fea6acc8c6ca7e0342541892c69a8452565033168bb15bf671dfae730b6591f9
d287p_pam_module_sha=96e47e1514a7c6c4fc722fa086bc25bb1c4d44774421c3d2970c7fc2b4385ebd
d287p_pkcheck_sha=73d5942052e6458bba548f7f01b19fb204f13d87cf948bd0a7d4f7d2ecdf9a67
d287p_policy_sha=06b50c015ba54c7b847ff873222c8bd5e9a68ec3ba0d6d48949fe846fbd0a033
d287p_libpam=/usr/lib64/libpam.so.0.85.1
d287p_libpam_sha=e8a3e3aa67cc17d4c659892fe63b9695ae202b6f107170f1ef5bb345570a8760
d287p_action_timeout=60
d287p_critical=(analysis/D285 analysis/D286 analysis/D287
  operator_kit/d285-01-persistent-sudo
  operator_kit/d286-01-reboot-survival
  operator_kit/d287-01-kscreenlocker-testing
  operator_kit/d287-01-active-user-pam-probe
  "Goodix 27c6 5125 manuale tecnico.md")
d287p_tmp=
d287p_interrupted=false

d287p_refuse () {
  echo D287_01_PROBE_GATE_REFUSED=true >&2
  echo "D287_01_PROBE_REFUSAL_REASON=$1" >&2
  echo D287_01_PROBE_MAX_VERIFY_ACTIONS=1 >&2
  echo D287_01_PROBE_MAX_PHYSICAL_CONTACTS=1 >&2
  echo D287_01_PROBE_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false >&2
  exit 3
}

d287p_cleanup () {
  local rc=0
  [[ -z $d287p_tmp ]] && return 0
  [[ $d287p_tmp == /tmp/goodix-d287-01-active-user.* &&
     -d $d287p_tmp && ! -L $d287p_tmp ]] || return 1
  find "$d287p_tmp" -xdev -depth -delete || rc=1
  d287p_tmp=
  return "$rc"
}

d287p_is_sha256 () {
  [[ ${1:-} =~ ^[0-9a-f]{64}$ ]]
}

d287p_safe_user () {
  [[ ${1:-} =~ ^[a-z_][a-z0-9_-]*$ ]]
}

d287p_verify_hash () {
  local path=$1 expected=$2
  d287p_is_sha256 "$expected" || return 1
  [[ -f $path && ! -L $path &&
     $(sha256sum "$path" | awk '{print $1}') == "$expected" ]]
}

d287p_signal_safe_tee () (
  trap '' HUP INT TERM
  tee "$1"
)

d287p_verify_repo () {
  local baseline=$1 dirty
  [[ $baseline =~ ^[0-9a-f]{40}$ ]] || d287p_refuse INVALID_BASELINE
  [[ $(git -C "$d287p_root" branch --show-current) == development ]] ||
    d287p_refuse WRONG_BRANCH
  [[ $(git -C "$d287p_root" rev-parse HEAD) == "$baseline" ]] ||
    d287p_refuse HEAD_MISMATCH
  [[ $(git -C "$d287p_root" rev-parse origin/development) == "$baseline" ]] ||
    d287p_refuse ORIGIN_DEVELOPMENT_MISMATCH
  dirty=$(git -C "$d287p_root" status --porcelain --untracked-files=all -- \
    "${d287p_critical[@]}") || d287p_refuse REPOSITORY_STATUS_READ_FAILED
  [[ -z $dirty ]] || d287p_refuse LIVE_CRITICAL_DIRTY
}

d287p_validate_static_contract () {
  local defaults
  [[ $(rpm -q pam) == pam-1.7.2-2.fc44.x86_64 ]] || d287p_refuse PAM_NEVRA_DRIFT
  [[ $(rpm -q fprintd-pam) == fprintd-pam-1.94.5-5.fc44.x86_64 ]] ||
    d287p_refuse FPRINTD_PAM_NEVRA_DRIFT
  [[ $(rpm -q polkit) == polkit-127-2.fc44.2.x86_64 ]] ||
    d287p_refuse POLKIT_NEVRA_DRIFT
  [[ $(rpm -q gcc) == gcc-16.2.1-2.fc44.x86_64 ]] ||
    d287p_refuse GCC_NEVRA_DRIFT
  [[ $(rpm -q glibc-devel) == glibc-devel-2.43-8.fc44.x86_64 ]] ||
    d287p_refuse GLIBC_DEVEL_NEVRA_DRIFT
  d287p_verify_hash "$d287p_source" "$d287p_source_sha" ||
    d287p_refuse RUNNER_SOURCE_DRIFT
  d287p_verify_hash "$d287p_pam" "$d287p_pam_sha" || d287p_refuse PROBE_PAM_DRIFT
  d287p_verify_hash /usr/lib64/security/pam_fprintd.so "$d287p_pam_module_sha" ||
    d287p_refuse PAM_FPRINTD_MODULE_DRIFT
  d287p_verify_hash /usr/bin/pkcheck "$d287p_pkcheck_sha" ||
    d287p_refuse PKCHECK_BINARY_DRIFT
  d287p_verify_hash /usr/share/polkit-1/actions/net.reactivated.fprint.device.policy \
    "$d287p_policy_sha" || d287p_refuse FPRINTD_POLKIT_POLICY_DRIFT
  [[ $(readlink /usr/lib64/libpam.so.0) == ${d287p_libpam##*/} ]] ||
    d287p_refuse LIBPAM_SONAME_LINK_DRIFT
  d287p_verify_hash "$d287p_libpam" "$d287p_libpam_sha" ||
    d287p_refuse LIBPAM_DRIFT
  nm -D "$d287p_libpam" | grep -F 'pam_start_confdir@@LIBPAM_1.4' >/dev/null ||
    d287p_refuse PAM_START_CONFDIR_SYMBOL_MISSING
  defaults=$(sed -n \
    '/<action id="net.reactivated.fprint.device.verify">/,/<\/action>/p' \
    /usr/share/polkit-1/actions/net.reactivated.fprint.device.policy) ||
    d287p_refuse FPRINTD_POLKIT_POLICY_PARSE_FAILED
  [[ -n $defaults ]] || d287p_refuse FPRINTD_POLKIT_POLICY_PARSE_FAILED
  grep -Fx '      <allow_any>no</allow_any>' <<<"$defaults" >/dev/null ||
    d287p_refuse FPRINTD_POLKIT_ALLOW_ANY_DRIFT
  grep -Fx '      <allow_inactive>no</allow_inactive>' <<<"$defaults" >/dev/null ||
    d287p_refuse FPRINTD_POLKIT_ALLOW_INACTIVE_DRIFT
  grep -Fx '      <allow_active>yes</allow_active>' <<<"$defaults" >/dev/null ||
    d287p_refuse FPRINTD_POLKIT_ALLOW_ACTIVE_DRIFT
  grep -Eq '^auth[[:space:]]+required[[:space:]]+/usr/lib64/security/pam_fprintd\.so[[:space:]]+max-tries=1[[:space:]]+timeout=45[[:space:]]+debug[[:space:]]*$' \
    "$d287p_pam" || d287p_refuse PROBE_PAM_CONTRACT_INVALID
  [[ $(grep -c pam_fprintd.so "$d287p_pam") -eq 1 ]] ||
    d287p_refuse PROBE_PAM_MODULE_COUNT_INVALID
  grep -Eq '^auth[[:space:]]+include[[:space:]]+system-auth[[:space:]]*$' \
    /usr/lib/pam.d/polkit-1 ||
    d287p_refuse POLKIT_PAM_PASSWORD_PATH_DRIFT
  [[ -f /etc/authselect/system-auth && ! -L /etc/authselect/system-auth ]] ||
    d287p_refuse AUTHSELECT_SYSTEM_AUTH_INVALID
  ! grep -Eq '^[[:space:]]*auth[[:space:]].*pam_fprintd\.so' \
    /etc/authselect/system-auth || d287p_refuse POLKIT_PAM_FINGERPRINT_RECURSION
  grep -F 'POST_LIVE_POLKIT_CONTEXT_DEFECT_CLOSED_DO_NOT_RERUN' \
    "$d287p_dir/../d287-01-kscreenlocker-testing/run-d287-01.sh" >/dev/null ||
    d287p_refuse HISTORICAL_GREETER_PATH_NOT_CLOSED
  for command in cc git journalctl ldd nm pgrep pkcheck pkexec rpm sha256sum tee timeout; do
    command -v "$command" >/dev/null || d287p_refuse "HOST_TOOL_MISSING_${command}"
  done
}

d287p_prepare_runner () {
  local permit
  [[ -z $d287p_tmp ]] || d287p_refuse TEMP_DIRECTORY_ALREADY_ACTIVE
  d287p_tmp=$(mktemp -d /tmp/goodix-d287-01-active-user.XXXXXX)
  [[ -d $d287p_tmp && ! -L $d287p_tmp ]] || d287p_refuse TEMP_DIRECTORY_INVALID
  chmod 0700 "$d287p_tmp"
  cc -std=c11 -O2 -Wall -Wextra -Werror -Wl,--build-id=none \
    "$d287p_source" -Wl,-l:libpam.so.0 -o "$d287p_tmp/pam-confdir-runner"
  chmod 0700 "$d287p_tmp/pam-confdir-runner"
  d287p_verify_hash "$d287p_tmp/pam-confdir-runner" "$d287p_runner_sha" ||
    d287p_refuse PAM_RUNNER_BINARY_DRIFT
  ldd "$d287p_tmp/pam-confdir-runner" | grep -F 'libpam.so.0' >/dev/null ||
    d287p_refuse PAM_RUNNER_LINKAGE_INVALID
  install -d -m 0700 "$d287p_tmp/pam.d" "$d287p_tmp/permit"
  install -m 0600 "$d287p_pam" "$d287p_tmp/pam.d/goodix-d287-01-active-user"
  permit=/usr/lib64/security/pam_permit.so
  [[ -f $permit && ! -L $permit ]] || d287p_refuse PAM_PERMIT_MISSING
  printf 'auth required %s\n' "$permit" >"$d287p_tmp/permit/goodix-d287-01-offline-permit"
  "$d287p_tmp/pam-confdir-runner" --offline-permit "$d287p_tmp/permit" nobody \
    >"$d287p_tmp/offline-permit.log" 2>&1 || d287p_refuse PAM_RUNNER_OFFLINE_PERMIT_FAILED
  grep -Fx D287_01_PROBE_PAM_START_CONFDIR_RETURN_CODE=0 \
    "$d287p_tmp/offline-permit.log" >/dev/null || d287p_refuse PAM_RUNNER_START_NOT_PROVEN
  grep -Fx D287_01_PROBE_PAM_AUTHENTICATE_RETURN_CODE=0 \
    "$d287p_tmp/offline-permit.log" >/dev/null || d287p_refuse PAM_RUNNER_AUTH_NOT_PROVEN
  grep -Fx D287_01_PROBE_PAM_END_RETURN_CODE=0 \
    "$d287p_tmp/offline-permit.log" >/dev/null || d287p_refuse PAM_RUNNER_END_NOT_PROVEN
}

d287p_validate_user_session () {
  local uid=$1 runtime=${XDG_RUNTIME_DIR:-} wayland=${WAYLAND_DISPLAY:-}
  local dbus=${DBUS_SESSION_BUS_ADDRESS:-} cgroup
  [[ $EUID -ne 0 && $(id -u) == "$uid" ]] || d287p_refuse OPERATOR_MUST_BE_UNPRIVILEGED
  [[ ${XDG_SESSION_TYPE:-} == wayland ]] || d287p_refuse WAYLAND_SESSION_REQUIRED
  [[ $runtime == "/run/user/$uid" && -d $runtime && ! -L $runtime &&
     $(stat -c %u "$runtime") == "$uid" ]] || d287p_refuse XDG_RUNTIME_DIR_INVALID
  [[ $wayland =~ ^wayland-[0-9]+$ && -S $runtime/$wayland ]] ||
    d287p_refuse WAYLAND_SOCKET_INVALID
  [[ $dbus == "unix:path=$runtime/bus" && -S $runtime/bus ]] ||
    d287p_refuse DBUS_SESSION_BUS_INVALID
  cgroup=$(sed -n 's/^0:://p' /proc/self/cgroup)
  [[ -n $cgroup && $cgroup != *'/user-0.slice/'* &&
     ! $cgroup =~ /session-c[0-9]+\.scope(/|$) ]] ||
    d287p_refuse ROOT_BACKGROUND_SESSION_CONTEXT_DETECTED
  printf '%s\n' "$cgroup"
}

d287p_count_goodix_targets () {
  local sysfs=${1:-/sys/bus/usb/devices} device count=0
  [[ -d $sysfs && ! -L $sysfs ]] || return 1
  for device in "$sysfs"/*; do
    [[ -d $device && -f $device/idVendor && -f $device/idProduct ]] || continue
    if [[ $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      count=$((count + 1))
    fi
  done
  printf '%s\n' "$count"
}

d287p_current_cursor () {
  local output cursor count
  output=$(LC_ALL=C journalctl -b -n 0 --show-cursor --no-pager) ||
    d287p_refuse JOURNAL_CURSOR_READ_FAILED
  cursor=$(printf '%s\n' "$output" | sed -n 's/^-- cursor: //p')
  count=$(printf '%s\n' "$cursor" | grep -c . || true)
  [[ $count -eq 1 && $cursor =~ ^[A-Za-z0-9_=.\;:-]{20,512}$ ]] ||
    d287p_refuse JOURNAL_CURSOR_INVALID
  printf '%s\n' "$cursor"
}

d287p_root_audit () (
  local phase=$1 user=$2 output=$3 rc tee_rc
  local -a pipeline_status
  set +e
  pkexec "$d287p_d286" --root-audit "$phase" --user "$user" 2>&1 |
    d287p_signal_safe_tee "$output"
  pipeline_status=("${PIPESTATUS[@]}")
  rc=${pipeline_status[0]}; tee_rc=${pipeline_status[1]}
  set -e
  [[ $rc -eq 0 && $tee_rc -eq 0 ]] || return 1
  grep -Fx D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES "$output" >/dev/null ||
    return 1
)

d287p_collect_journals () (
  local cursor=$1 capture=$2 user=$3
  local unit_rc unit_filter_rc diagnostic_rc diagnostic_filter_rc
  local -a pipeline_status
  local unit_error="$d287p_tmp/fprintd-journal.error"
  local diagnostic_error="$d287p_tmp/diagnostic-journal.error"
  local pattern='GOODIX_|pam_fprintd|pam-confdir-runner|fprintd(\.service)?|net\.reactivated\.fprint|Authorization (denied|granted)|polkit|systemd-logind|New session|Removed session|session-[0-9]+\.scope'
  set +e
  LC_ALL=C journalctl -b -u fprintd.service --after-cursor "$cursor" \
    --output=short-iso-precise --no-pager \
    2>"$unit_error" |
    sed "s/$user/<USER>/g" >"$capture/fprintd-journal.log"
  pipeline_status=("${PIPESTATUS[@]}")
  unit_rc=${pipeline_status[0]}; unit_filter_rc=${pipeline_status[1]}
  LC_ALL=C journalctl -b --after-cursor "$cursor" --grep "$pattern" \
    --case-sensitive=yes --output=short-iso-precise --no-pager \
    2>"$diagnostic_error" |
    sed "s/$user/<USER>/g" \
    >"$capture/diagnostic-journal.log"
  pipeline_status=("${PIPESTATUS[@]}")
  diagnostic_rc=${pipeline_status[0]}; diagnostic_filter_rc=${pipeline_status[1]}
  set -e
  if [[ $unit_rc -ne 0 || $unit_filter_rc -ne 0 ||
        $diagnostic_rc -gt 1 || $diagnostic_filter_rc -ne 0 ||
        ( $diagnostic_rc -eq 1 && -s $diagnostic_error ) ]]; then
    sed "s/$user/<USER>/g" "$unit_error" "$diagnostic_error" >&2
    return 1
  fi
)

d287p_collect_terminal_observability () {
  local cursor=$1 capture=$2 user=$3 runner_log=$4
  local deadline=$((SECONDS + 10))
  d287p_collect_journals "$cursor" "$capture" "$user" || return 1
  if grep -Fx D287_01_PROBE_ACTIVE_USER_POLKIT_PREFLIGHT=PASS "$runner_log" >/dev/null &&
     grep -q '^D287_01_PROBE_PAM_START_CONFDIR_RETURN_CODE=' "$runner_log"; then
    while ! grep -q GOODIX_D282_EPOCH_AUDIT "$capture/diagnostic-journal.log" &&
          ! grep -q 'Authorization denied .*ListEnrolledFingers' \
            "$capture/diagnostic-journal.log"; do
      pgrep -x fprintd >/dev/null || break
      (( SECONDS < deadline )) || break
      sleep 0.2
      d287p_collect_journals "$cursor" "$capture" "$user" || return 1
    done
  fi
}

d287p_field_sum () {
  local field=$1 journal=$2
  (grep GOODIX_D282_EPOCH_AUDIT "$journal" || true) |
    awk -v key="$field" '{for(i=1;i<=NF;i++){split($i,a,"=");if(a[1]==key)s+=a[2]}}END{print s+0}'
}

d287p_marker_field () {
  local marker=$1 field=$2 journal=$3
  awk -v marker="$marker" -v key="$field" '
    index($0, marker) {
      for (i = 1; i <= NF; i++) {
        split($i, a, "=")
        if (a[1] == key && a[2] ~ /^[0-9]+$/) { print a[2]; exit }
      }
    }' "$journal"
}

d287p_classify () {
  local runner_log=$1 journal=$2 runner_rc=$3 timeout_rc=$4
  local all_epoch epoch start comparison extract outcome_markers match no_match
  local attempts rejected consumed tls first_image real_submit outstanding drained closed
  local retry reopen reset clear_halt persistent polkit polkit_fail pam_not_started
  local denial pam_started auth_markers end_markers declared_comparisons
  local template_samples matched_sample extract_keypoints outcome
  all_epoch=$(grep -c 'GOODIX_D282_EPOCH_AUDIT ' "$journal" || true)
  epoch=$(grep -c 'GOODIX_D282_EPOCH_AUDIT .*action=FPI_DEVICE_ACTION_VERIFY' "$journal" || true)
  start=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=start' "$journal" || true)
  comparison=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=comparison' "$journal" || true)
  extract=$(grep -c 'GOODIX_SIGFM_EXTRACT_AUDIT ' "$journal" || true)
  outcome_markers=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome' "$journal" || true)
  match=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=match' "$journal" || true)
  no_match=$(grep -c 'GOODIX_SIGFM_MATCH_AUDIT .*event=outcome result=no_match' "$journal" || true)
  attempts=$(d287p_field_sum attempts "$journal")
  rejected=$(d287p_field_sum rejected "$journal")
  consumed=$(d287p_field_sum consumed "$journal")
  tls=$(d287p_field_sum tls "$journal")
  first_image=$(d287p_field_sum first_image "$journal")
  real_submit=$(d287p_field_sum real_submit "$journal")
  outstanding=$(d287p_field_sum outstanding "$journal")
  drained=$(d287p_field_sum drained "$journal")
  closed=$(d287p_field_sum context_closed "$journal")
  retry=$(( $(d287p_field_sum secure_retry "$journal") + $(d287p_field_sum post_retry "$journal") ))
  reopen=$(d287p_field_sum reopen "$journal")
  reset=$(d287p_field_sum reset "$journal")
  clear_halt=$(d287p_field_sum clear_halt "$journal")
  persistent=$(d287p_field_sum persistent "$journal")
  polkit=$(grep -c '^D287_01_PROBE_ACTIVE_USER_POLKIT_PREFLIGHT=PASS$' "$runner_log" || true)
  polkit_fail=$(grep -c '^D287_01_PROBE_ACTIVE_USER_POLKIT_PREFLIGHT=FAIL$' "$runner_log" || true)
  pam_not_started=$(grep -c '^D287_01_PROBE_PAM_NOT_STARTED=true$' "$runner_log" || true)
  pam_started=$(grep -c '^D287_01_PROBE_PAM_START_CONFDIR_RETURN_CODE=' "$runner_log" || true)
  auth_markers=$(grep -c '^D287_01_PROBE_PAM_AUTHENTICATE_RETURN_CODE=' "$runner_log" || true)
  end_markers=$(grep -c '^D287_01_PROBE_PAM_END_RETURN_CODE=' "$runner_log" || true)
  denial=$(grep -c 'Authorization denied .*ListEnrolledFingers' "$journal" || true)
  declared_comparisons=$(d287p_marker_field \
    'GOODIX_SIGFM_MATCH_AUDIT event=outcome' comparisons "$journal")
  template_samples=$(d287p_marker_field \
    'GOODIX_SIGFM_MATCH_AUDIT event=start' template_samples "$journal")
  matched_sample=$(d287p_marker_field \
    'GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match' matched_sample "$journal")
  extract_keypoints=$(d287p_marker_field \
    'GOODIX_SIGFM_EXTRACT_AUDIT' keypoints "$journal")
  declared_comparisons=${declared_comparisons:-0}
  template_samples=${template_samples:-0}
  matched_sample=${matched_sample:-0}
  extract_keypoints=${extract_keypoints:-0}
  outcome=PAM_ERROR
  if [[ $all_epoch -ne $epoch || $all_epoch -gt 1 || $epoch -gt 1 ||
        $start -gt 1 || $extract -gt 1 || $outcome_markers -gt 1 ||
        $match -gt 1 || $no_match -gt 1 ||
        $polkit -gt 1 || $polkit_fail -gt 1 || $pam_not_started -gt 1 ||
        $pam_started -gt 1 || $auth_markers -gt 1 || $end_markers -gt 1 ||
        $((polkit + polkit_fail)) -gt 1 ||
        $((pam_not_started + pam_started)) -gt 1 ||
        $((match + no_match)) -gt 1 || $retry -ne 0 || $reopen -ne 0 ||
        $reset -ne 0 || $clear_halt -ne 0 || $persistent -ne 0 ]]; then
    outcome=SAFETY_VIOLATION
  elif [[ $polkit -eq 1 && $all_epoch -eq 1 && $epoch -eq 1 &&
          $start -eq 1 && $comparison -ge 1 && $extract -eq 1 &&
          $comparison -eq $declared_comparisons && $matched_sample -eq $comparison &&
          $extract_keypoints -ge 1 && $pam_started -eq 1 &&
          $auth_markers -eq 1 && $end_markers -eq 1 &&
          $attempts -eq 1 && $rejected -eq 0 && $consumed -eq 1 &&
          $tls -eq 1 && $first_image -eq 1 && $real_submit -ge 1 &&
          $outstanding -eq 0 &&
          $drained -eq 1 && $closed -eq 1 &&
          $match -eq 1 && $no_match -eq 0 &&
          $runner_rc -eq 0 && $timeout_rc -eq 0 ]] &&
       grep -Fx D287_01_PROBE_PAM_AUTHENTICATE_RETURN_CODE=0 "$runner_log" >/dev/null &&
       grep -Fx D287_01_PROBE_PAM_START_CONFDIR_RETURN_CODE=0 "$runner_log" >/dev/null &&
       grep -Fx D287_01_PROBE_PAM_END_RETURN_CODE=0 "$runner_log" >/dev/null; then
    outcome=MATCH_REACHED_VERIFY
  elif [[ $polkit -eq 1 && $all_epoch -eq 1 && $epoch -eq 1 &&
          $start -eq 1 && $comparison -ge 1 && $extract -eq 1 &&
          $comparison -eq $declared_comparisons &&
          $declared_comparisons -eq $template_samples &&
          $extract_keypoints -ge 1 && $pam_started -eq 1 &&
          $auth_markers -eq 1 && $end_markers -eq 1 &&
          $attempts -eq 1 && $rejected -eq 0 && $consumed -eq 1 &&
          $tls -eq 1 && $first_image -eq 1 && $real_submit -ge 1 &&
          $outstanding -eq 0 &&
          $drained -eq 1 && $closed -eq 1 &&
          $match -eq 0 && $no_match -eq 1 &&
          $runner_rc -eq 1 && $timeout_rc -eq 0 ]] &&
       grep -Fx D287_01_PROBE_PAM_START_CONFDIR_RETURN_CODE=0 "$runner_log" >/dev/null &&
       grep -Eq '^D287_01_PROBE_PAM_AUTHENTICATE_RETURN_CODE=[1-9][0-9]*$' "$runner_log" &&
       grep -Fx D287_01_PROBE_PAM_END_RETURN_CODE=0 "$runner_log" >/dev/null; then
    outcome=NO_MATCH_REACHED_VERIFY
  elif [[ $polkit -eq 0 && $polkit_fail -eq 1 && $pam_not_started -eq 1 &&
          $pam_started -eq 0 && $all_epoch -eq 0 &&
          $runner_rc -eq 3 && $timeout_rc -eq 0 ]]; then
    outcome=POLKIT_PREFLIGHT_FAILED_BEFORE_PAM
  elif [[ $polkit -eq 1 && $pam_started -eq 1 && $denial -ge 1 &&
          $all_epoch -eq 0 && $runner_rc -eq 1 && $timeout_rc -eq 0 ]] &&
       grep -Fx D287_01_PROBE_PAM_START_CONFDIR_RETURN_CODE=0 "$runner_log" >/dev/null &&
       grep -Eq '^D287_01_PROBE_PAM_AUTHENTICATE_RETURN_CODE=[1-9][0-9]*$' "$runner_log" &&
       grep -Fx D287_01_PROBE_PAM_END_RETURN_CODE=0 "$runner_log" >/dev/null; then
    outcome=FPRINTD_POLKIT_DENIED_BEFORE_VERIFY
  fi
  echo "D287_01_PROBE_OUTCOME=$outcome"
  echo "D287_01_PROBE_RUNNER_RETURN_CODE=$runner_rc"
  echo "D287_01_PROBE_TIMEOUT_RETURN_CODE=$timeout_rc"
  echo "D287_01_PROBE_ALL_EPOCH_COUNT=$all_epoch"
  echo "D287_01_PROBE_VERIFY_EPOCH_COUNT=$epoch"
  echo "D287_01_PROBE_MATCH_START_COUNT=$start"
  echo "D287_01_PROBE_COMPARISON_COUNT=$comparison"
  echo "D287_01_PROBE_EXTRACT_COUNT=$extract"
  echo "D287_01_PROBE_OUTCOME_MARKER_COUNT=$outcome_markers"
  echo "D287_01_PROBE_EXTRACT_KEYPOINTS=$extract_keypoints"
  echo "D287_01_PROBE_TEMPLATE_SAMPLE_COUNT=$template_samples"
  echo "D287_01_PROBE_DECLARED_COMPARISON_COUNT=$declared_comparisons"
  echo "D287_01_PROBE_MATCHED_SAMPLE=$matched_sample"
  echo "D287_01_PROBE_MATCH_COUNT=$match"
  echo "D287_01_PROBE_NO_MATCH_COUNT=$no_match"
  echo "D287_01_PROBE_RETRY_COUNT=$retry"
  echo "D287_01_PROBE_REOPEN_COUNT=$reopen"
  echo "D287_01_PROBE_RESET_COUNT=$reset"
  echo "D287_01_PROBE_CLEAR_HALT_COUNT=$clear_halt"
  echo "D287_01_PROBE_PERSISTENT_WRITE_FAMILY_COUNT=$persistent"
  echo "D287_01_PROBE_LIST_ENROLLED_FINGERS_DENIAL_COUNT=$denial"
  echo "D287_01_PROBE_POLKIT_PREFLIGHT_PASS_COUNT=$polkit"
  echo "D287_01_PROBE_POLKIT_PREFLIGHT_FAIL_COUNT=$polkit_fail"
  echo "D287_01_PROBE_PAM_NOT_STARTED_COUNT=$pam_not_started"
  echo "D287_01_PROBE_ACTION_ATTEMPT_COUNT=$attempts"
  echo "D287_01_PROBE_ACTION_REJECTED_COUNT=$rejected"
  echo "D287_01_PROBE_ACTION_CONSUMED_COUNT=$consumed"
  echo "D287_01_PROBE_TLS_COUNT=$tls"
  echo "D287_01_PROBE_FIRST_IMAGE_COUNT=$first_image"
  echo "D287_01_PROBE_REAL_USB_SUBMIT_COUNT=$real_submit"
  echo "D287_01_PROBE_OUTSTANDING_COUNT=$outstanding"
  echo "D287_01_PROBE_DRAINED_COUNT=$drained"
  echo "D287_01_PROBE_CONTEXT_CLOSED_COUNT=$closed"
  [[ $outcome == MATCH_REACHED_VERIFY || $outcome == NO_MATCH_REACHED_VERIFY ]]
}

d287p_series () {
  local baseline=$1 user=$2 uid=$3 capture=$4 cgroup cursor confirmation
  local runner_rc runner_tee_rc timeout_rc journal_rc post_audit_rc
  local classify_rc=1 classification_tee_rc=1 cleanup_rc=0
  local -a pipeline_status
  local final=FAIL_LIVE_PENDING_INDEPENDENT_REVIEW
  trap d287p_cleanup EXIT
  d287p_verify_repo "$baseline"
  d287p_validate_static_contract
  cgroup=$(d287p_validate_user_session "$uid")
  [[ $(d287p_count_goodix_targets) -eq 1 ]] || d287p_refuse REAL_TARGET_CARDINALITY_NOT_ONE
  ! pgrep -x fprintd >/dev/null || d287p_refuse FPRINTD_ALREADY_ACTIVE
  d287p_prepare_runner
  d287p_root_audit D287_ACTIVE_USER_PAM_PRE "$user" "$capture/pre-root-audit.log" ||
    d287p_refuse ROOT_AUDIT_D287_ACTIVE_USER_PAM_PRE_FAILED
  cgroup=$(d287p_validate_user_session "$uid")
  ! pgrep -x fprintd >/dev/null || d287p_refuse FPRINTD_BECAME_ACTIVE_BEFORE_PROBE
  cursor=$(d287p_current_cursor)
  {
    echo "D287_01_PROBE_BOOT_ID=$(</proc/sys/kernel/random/boot_id)"
    echo "D287_01_PROBE_JOURNAL_CURSOR=$cursor"
    echo "D287_01_PROBE_OPERATOR_UID=$uid"
    echo "D287_01_PROBE_OPERATOR_CGROUP=$cgroup"
    echo D287_01_PROBE_PKCHECK_SUBJECT=RUNNER_PID_START_TIME_UID
    echo D287_01_PROBE_PKCHECK_ALLOW_USER_INTERACTION=false
    echo "D287_01_PROBE_RUNNER_SOURCE_SHA256=$d287p_source_sha"
    echo "D287_01_PROBE_RUNNER_BINARY_SHA256=$d287p_runner_sha"
    echo "D287_01_PROBE_PAM_SHA256=$d287p_pam_sha"
    echo "D287_01_PROBE_PAM_FPRINTD_MODULE_SHA256=$d287p_pam_module_sha"
    echo D287_01_PROBE_PAM_SERVICE=goodix-d287-01-active-user
    echo D287_01_PROBE_PAM_MAX_TRIES=1
    echo D287_01_PROBE_PAM_TIMEOUT_SECONDS=45
  } >"$capture/context.env"
  echo 'Probe PAM singolo dalla sessione grafica attiva; nessuna finestra fullscreen.'
  echo 'Il runner esegue pkcheck sul proprio PID/start-time/UID prima di pam_start.'
  echo 'Massimo una VERIFY e un solo contatto. Ctrl-C interrompe; non appoggiare di nuovo il dito.'
  printf 'Per autorizzare il solo contatto con INDICE DESTRO digitare INDICE DESTRO: '
  read -r confirmation || d287p_refuse OPERATOR_CONFIRMATION_READ_FAILED
  [[ $confirmation == 'INDICE DESTRO' ]] || d287p_refuse PHYSICAL_FINGER_NOT_CONFIRMED
  d287p_interrupted=false
  trap 'd287p_interrupted=true; echo D287_01_PROBE_OPERATOR_INTERRUPT_RECEIVED=true' HUP INT TERM
  set +e
  timeout --foreground --signal=TERM --kill-after=5s "${d287p_action_timeout}s" \
    "$d287p_tmp/pam-confdir-runner" --active-user-probe "$d287p_tmp/pam.d" "$user" \
    2>&1 | d287p_signal_safe_tee "$capture/pam-runner.log"
  pipeline_status=("${PIPESTATUS[@]}")
  runner_rc=${pipeline_status[0]}; runner_tee_rc=${pipeline_status[1]}
  set -e
  trap - HUP INT TERM
  timeout_rc=0
  [[ $runner_rc -ne 124 && $runner_rc -ne 137 ]] || timeout_rc=$runner_rc
  set +e
  d287p_collect_terminal_observability "$cursor" "$capture" "$user" \
    "$capture/pam-runner.log"
  journal_rc=$?
  set -e
  if [[ $journal_rc -ne 0 ]]; then
    echo D287_01_PROBE_JOURNAL_COLLECTION_FAILED=true >"$capture/fprintd-journal.log"
    echo D287_01_PROBE_JOURNAL_COLLECTION_FAILED=true >"$capture/diagnostic-journal.log"
  fi
  set +e
  d287p_classify "$capture/pam-runner.log" "$capture/diagnostic-journal.log" \
    "$runner_rc" "$timeout_rc" | d287p_signal_safe_tee "$capture/classification.env"
  pipeline_status=("${PIPESTATUS[@]}")
  classify_rc=${pipeline_status[0]}; classification_tee_rc=${pipeline_status[1]}
  set -e
  set +e
  d287p_root_audit D287_ACTIVE_USER_PAM_POST "$user" "$capture/post-root-audit.log"
  post_audit_rc=$?
  set -e
  if [[ $d287p_interrupted == true ]]; then
    final=OPERATOR_INTERRUPTED_AFTER_ACTION_START
  elif [[ $runner_tee_rc -ne 0 ]]; then
    final=FAIL_RUNNER_CAPTURE
  elif [[ $journal_rc -ne 0 ]]; then
    final=FAIL_JOURNAL_COLLECTION
  elif [[ $classification_tee_rc -ne 0 ]]; then
    final=FAIL_CLASSIFICATION_CAPTURE
  elif [[ $post_audit_rc -ne 0 ]]; then
    final=FAIL_POST_ROOT_AUDIT
  elif [[ $classify_rc -eq 0 ]]; then
    final=PROBE_REACHED_VERIFY_PENDING_INDEPENDENT_REVIEW
  fi
  set +e
  d287p_cleanup
  cleanup_rc=$?
  set -e
  [[ $cleanup_rc -eq 0 ]] || final=FAIL_TEMP_CLEANUP
  echo "D287_01_PROBE_SERIES_RESULT=$final"
  echo D287_01_PROBE_HOST_PAM_FILE_WRITE_COUNT=0
  echo D287_01_PROBE_REAL_SESSION_LOCKED=false
  echo D287_01_PROBE_GREETER_STARTED=false
  echo D287_01_PROBE_MAX_VERIFY_ACTIONS=1
  echo D287_01_PROBE_MAX_PHYSICAL_CONTACTS=1
  echo D287_01_PROBE_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
  echo "D287_01_PROBE_JOURNAL_COLLECTION_RETURN_CODE=$journal_rc"
  echo "D287_01_PROBE_RUNNER_CAPTURE_TEE_RETURN_CODE=$runner_tee_rc"
  echo "D287_01_PROBE_CLASSIFICATION_CAPTURE_TEE_RETURN_CODE=$classification_tee_rc"
  echo "D287_01_PROBE_POST_ROOT_AUDIT_RETURN_CODE=$post_audit_rc"
  echo "D287_01_PROBE_TEMP_CLEANUP_RETURN_CODE=$cleanup_rc"
  echo "D287_01_PROBE_OPERATOR_INTERRUPTED=$d287p_interrupted"
  echo TEMPLATE_INCLUDED_IN_EXPORT=false
  [[ $final == PROBE_REACHED_VERIFY_PENDING_INDEPENDENT_REVIEW ]]
}

d287p_operator_run () {
  local baseline user uid stamp capture rc tee_rc result count
  local -a pipeline_status
  [[ $EUID -ne 0 ]] || d287p_refuse OPERATOR_MUST_BE_UNPRIVILEGED
  baseline=$(git -C "$d287p_root" rev-parse HEAD)
  d287p_verify_repo "$baseline"
  user=$(id -un); uid=$(id -u)
  d287p_safe_user "$user" || d287p_refuse OPERATOR_USER_INVALID
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  capture="$d287p_capture_root/D28701_ACTIVE_USER_PAM_${stamp}_${baseline:0:12}/sanitized"
  [[ ! -e $capture && ! -L $capture ]] || d287p_refuse CAPTURE_COLLISION
  install -d -m 0700 "$capture"
  trap 'echo D287_01_PROBE_OUTER_INTERRUPT_DEFERRED_FOR_CAPTURE=true >&2' HUP INT TERM
  set +e
  d287p_series "$baseline" "$user" "$uid" "$capture" 2>&1 |
    d287p_signal_safe_tee "$capture/operator.log"
  pipeline_status=("${PIPESTATUS[@]}")
  rc=${pipeline_status[0]}; tee_rc=${pipeline_status[1]}
  set -e
  trap - HUP INT TERM
  result=$(sed -n 's/^D287_01_PROBE_SERIES_RESULT=//p' "$capture/operator.log" | tail -n 1)
  count=$(grep -c '^D287_01_PROBE_SERIES_RESULT=' "$capture/operator.log" || true)
  if [[ $tee_rc -ne 0 ]]; then
    result=CAPTURE_TEE_FAILED
  elif [[ $count -ne 1 ]]; then
    result=SERIES_RESULT_MISSING_OR_MULTIPLE
  fi
  {
    echo "D287_01_PROBE_RESULT=$result"
    echo "D287_01_PROBE_SERIES_RETURN_CODE=$rc"
    echo "D287_01_PROBE_CAPTURE_TEE_RETURN_CODE=$tee_rc"
    echo "D287_01_PROBE_REPO_BASELINE=$baseline"
    echo D287_01_PROBE_CONSUMER=ACTIVE_USER_SESSION_PAM_CONFDIR
    echo D287_01_PROBE_HOST_PAM_FILE_WRITE_COUNT=0
    echo D287_01_PROBE_REAL_SESSION_LOCKED=false
    echo D287_01_PROBE_GREETER_STARTED=false
    echo D287_01_PROBE_MAX_VERIFY_ACTIONS=1
    echo D287_01_PROBE_MAX_PHYSICAL_CONTACTS=1
    echo D287_01_PROBE_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
    echo TEMPLATE_INCLUDED_IN_EXPORT=false
  } >"$capture/summary.env"
  chmod 0600 "$capture"/*
  sha256sum "$capture"/* >"$capture/capture.sha256"
  chmod 0600 "$capture/capture.sha256"
  cat "$capture/capture.sha256"
  echo "D287_01_PROBE_CAPTURE_DIRECTORY=$capture"
  d287p_cleanup || d287p_refuse TEMP_CLEANUP_FAILED
  [[ $rc -eq 0 && $tee_rc -eq 0 &&
     $result == PROBE_REACHED_VERIFY_PENDING_INDEPENDENT_REVIEW ]]
}

d287p_offline_preflight () {
  [[ $EUID -ne 0 ]] || d287p_refuse OFFLINE_PREFLIGHT_MUST_BE_UNPRIVILEGED
  trap d287p_cleanup EXIT
  d287p_validate_static_contract
  d287p_prepare_runner
  echo D287_01_PROBE_OFFLINE_PREFLIGHT=PASS
  echo D287_01_PROBE_RUNNER_REAL_PAM_PERMIT=PASS
  echo D287_01_PROBE_PKCHECK_EXACT_SUBJECT_CONSTRUCTION=PASS_STATIC
  echo D287_01_PROBE_LIVE_EXECUTION=HUMAN_REQUIRED
  echo REAL_USB_ENUMERATION_ATTEMPTED=false
  echo REAL_SENSOR_ACCESSED=false
  echo LIVE_EXECUTION_PERFORMED=false
  d287p_cleanup
  trap - EXIT
}

if [[ ${D287_PROBE_LIBRARY_ONLY:-false} == true ]]; then
  return 0 2>/dev/null || exit 0
fi

trap d287p_cleanup EXIT
case ${1:-} in
  --offline-preflight)
    [[ $# -eq 1 ]] || d287p_refuse USAGE
    d287p_offline_preflight
    ;;
  --operator-run)
    [[ $# -eq 1 ]] || d287p_refuse USAGE
    d287p_operator_run
    ;;
  *)
    echo "Uso: $0 --offline-preflight | --operator-run" >&2
    exit 2
    ;;
esac
