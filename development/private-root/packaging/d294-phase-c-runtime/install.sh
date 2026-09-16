#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
package=goodix-27c6-5125-runtime
state=/var/lib/goodix-27c6-5125-phase-c-runtime.state
d293_wrapper=/usr/local/sbin/goodix-d293-native-fprintd
d293_dropin=/etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf
b5_hook=/etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete
packaged_dropin=/etc/systemd/system/fprintd.service.d/99-goodix-27c6-5125-runtime.conf
packaged_runtime=/usr/lib64/goodix-27c6-5125
packaged_wrapper=/usr/libexec/goodix-27c6-5125

fail() {
  printf 'D294_01_INSTALL=FAIL reason=%s\n' "$1" >&2
  exit 1
}

digest() { sha256sum "$1" | awk '{print $1}'; }

if [[ ${1:-} == --root-install ]]; then
  [[ $# -eq 5 ]] || fail root_usage
  rpm_path=$2
  expected_sha=$3
  expected_head=$4
  caller=$5
  [[ $EUID -eq 0 ]] || fail root_required
  [[ ${SUDO_USER:-} == "$caller" && $caller =~ ^[a-z_][a-z0-9_-]*$ ]] ||
    fail caller_invalid
  [[ $expected_sha =~ ^[0-9a-f]{64}$ && $expected_head =~ ^[0-9a-f]{40}$ ]] ||
    fail provenance_invalid
  [[ $(git -C "$root" branch --show-current) == development ]] || fail wrong_branch
  [[ $(git -C "$root" rev-parse HEAD) == "$expected_head" ]] || fail head_mismatch
  [[ $(git -C "$root" rev-parse origin/development) == "$expected_head" ]] ||
    fail origin_head_mismatch
  [[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
  case "$rpm_path" in
    "$here"/dist/"$package"-*.rpm|/tmp/goodix-d294-install.*/output/"$package"-*.rpm) ;;
    *) fail rpm_path_invalid ;;
  esac
  [[ -f $rpm_path && ! -L $rpm_path && $(stat -c %u "$rpm_path") == $(id -u "$caller") ]] ||
    fail rpm_source_invalid
  root_work=$(mktemp -d /var/tmp/goodix-d294-root.XXXXXX)
  cleanup_root_work() {
    if [[ $root_work == /var/tmp/goodix-d294-root.* && -d $root_work && ! -L $root_work ]]; then
      find "$root_work" -xdev -depth -delete
    fi
  }
  trap cleanup_root_work EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  install -m 0600 "$rpm_path" "$root_work/candidate.rpm"
  rpm_path=$root_work/candidate.rpm
  [[ $(digest "$rpm_path") == "$expected_sha" ]] ||
    fail rpm_drift
  [[ $(rpm -qp --qf '%{NAME}' "$rpm_path") == "$package" ]] || fail rpm_name_invalid
  rpm -qp --provides "$rpm_path" |
    grep -Fx "goodix-27c6-5125-runtime-commit($expected_head)" >/dev/null ||
    fail rpm_commit_invalid
  [[ ! -e $state && ! -L $state ]] || fail state_collision
  ! rpm -q "$package" >/dev/null 2>&1 || fail package_already_installed
  [[ ! -e $packaged_dropin && ! -L $packaged_dropin &&
     ! -e $packaged_runtime && ! -L $packaged_runtime &&
     ! -e $packaged_wrapper && ! -L $packaged_wrapper ]] || fail package_path_collision
  [[ -x $d293_wrapper && -f $d293_wrapper && ! -L $d293_wrapper &&
     -f $d293_dropin && ! -L $d293_dropin ]] || fail d293_fallback_missing
  [[ -x $b5_hook && -f $b5_hook && ! -L $b5_hook ]] || fail d293_b5_fallback_missing
  d293_wrapper_sha=$(digest "$d293_wrapper")
  d293_dropin_sha=$(digest "$d293_dropin")
  b5_hook_sha=$(digest "$b5_hook")
  service_before=$(systemctl is-active fprintd.service || true)
  [[ $service_before == active || $service_before == inactive ]] || fail service_state_unsupported
  unit_before=$(systemctl cat fprintd.service | sha256sum | awk '{print $1}')
  features_before=false
  flann_before=false
  if rpm -q opencv-features2d >/dev/null 2>&1; then
    [[ $(rpm -q opencv-features2d) == opencv-features2d-4.13.0-1.fc44.x86_64 ]] ||
      fail opencv_features2d_version
    features_before=true
  fi
  if rpm -q opencv-flann >/dev/null 2>&1; then
    [[ $(rpm -q opencv-flann) == opencv-flann-4.13.0-1.fc44.x86_64 ]] ||
      fail opencv_flann_version
    flann_before=true
  fi
  mutated=false
  cleanup_failed_install() {
    rc=$?
    if [[ $mutated == true && $rc -ne 0 ]]; then
      rm -f -- "$state"
      if rpm -q "$package" >/dev/null 2>&1; then
        rpm -e "$package" >/dev/null 2>&1 || true
      fi
      if [[ $features_before == false ]] && rpm -q opencv-features2d >/dev/null 2>&1; then
        rpm -e opencv-features2d >/dev/null 2>&1 || true
      fi
      if [[ $flann_before == false ]] && rpm -q opencv-flann >/dev/null 2>&1; then
        rpm -e opencv-flann >/dev/null 2>&1 || true
      fi
      systemctl daemon-reload >/dev/null 2>&1 || true
      if [[ $service_before == active ]]; then
        systemctl start fprintd.service >/dev/null 2>&1 || true
      fi
    fi
    cleanup_root_work
    exit "$rc"
  }
  trap cleanup_failed_install EXIT
  if [[ $service_before == active ]]; then
    mutated=true
    systemctl stop fprintd.service
  fi
  mutated=true
  dnf5 install -y --disablerepo='*' \
    "$root/GoodixArtifacts/opencv-4.13-rpms/opencv-features2d-4.13.0-1.fc44.x86_64.rpm" \
    "$root/GoodixArtifacts/opencv-4.13-rpms/opencv-flann-4.13.0-1.fc44.x86_64.rpm" \
    "$rpm_path" || fail dnf_install_failed
  install -m 0600 /dev/null "$state"
  {
    echo D294_01_STATUS=ACTIVE
    echo "D294_01_SOURCE_COMMIT=$expected_head"
    echo "D294_01_RPM_SHA256=$expected_sha"
    echo "D294_01_INSTALLER=$caller"
    echo "D294_01_SERVICE_BEFORE=$service_before"
    echo "D294_01_UNIT_BEFORE_SHA256=$unit_before"
    echo "D294_01_D293_WRAPPER_SHA256=$d293_wrapper_sha"
    echo "D294_01_D293_DROPIN_SHA256=$d293_dropin_sha"
    echo "D294_01_B5_HOOK_SHA256=$b5_hook_sha"
    echo "D294_01_OPENCV_FEATURES2D_BEFORE=$features_before"
    echo "D294_01_OPENCV_FLANN_BEFORE=$flann_before"
  } >"$state"
  restorecon -F "$state"
  systemctl daemon-reload
  if [[ $service_before == active ]]; then
    systemctl start fprintd.service
  fi
  [[ $(systemctl is-active fprintd.service || true) == "$service_before" ]] ||
    fail service_state_changed
  rpm -V "$package" >/dev/null || fail rpm_verify_failed
  systemctl show -p ExecStart --value fprintd.service |
    grep -F /usr/libexec/goodix-27c6-5125/fprintd-wrapper >/dev/null ||
    fail packaged_execstart_inactive
  cleanup_root_work
  trap - EXIT INT TERM
  echo D294_01_INSTALL=PASS
  echo D294_01_D293_FALLBACK=PRESERVED
  echo D294_01_D293_B5_FALLBACK=PRESERVED
  exit 0
fi

[[ $# -eq 0 ]] || fail usage
[[ $EUID -ne 0 ]] || fail entrypoint_must_be_unprivileged
for command in git rpm sudo sha256sum; do
  command -v "$command" >/dev/null || fail "missing_command_$command"
done
[[ $(git -C "$root" branch --show-current) == development ]] || fail wrong_branch
[[ -z $(git -C "$root" status --porcelain --untracked-files=all) ]] || fail worktree_dirty
head=$(git -C "$root" rev-parse HEAD)
[[ $(git -C "$root" rev-parse origin/development) == "$head" ]] || fail origin_head_mismatch
[[ $(rpm -q shadow-utils) == shadow-utils-4.19.0-7.fc44.x86_64 ]] || fail shadow_utils_version
[[ $(rpm -q fprintd) == fprintd-1.94.5-5.fc44.x86_64 ]] || fail fprintd_version
[[ $(rpm -q libfprint) == libfprint-1.94.100-1.fc44.x86_64 ]] || fail libfprint_version
[[ $(rpm -q opencv-core) == opencv-core-4.13.0-1.fc44.x86_64 ]] || fail opencv_core_version
[[ $(rpm -q opencv-imgproc) == opencv-imgproc-4.13.0-1.fc44.x86_64 ]] || fail opencv_imgproc_version
[[ $(rpm -q libgusb) == libgusb-0.4.9-5.fc44.x86_64 ]] || fail libgusb_version
(cd "$root/GoodixArtifacts/opencv-4.13-rpms" &&
  sha256sum -c "$root/production/build-support/opencv-rpms.sha256") ||
  fail opencv_rpm_provenance
work=$(mktemp -d /tmp/goodix-d294-install.XXXXXX)
cleanup() {
  if [[ $work == /tmp/goodix-d294-install.* && -d $work && ! -L $work ]]; then
    find "$work" -xdev -depth -delete
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mapfile -t prepared < <(find "$here/dist" -maxdepth 1 -type f -name "$package-*.rpm" -print 2>/dev/null | sort)
if [[ ${#prepared[@]} -eq 1 ]] &&
   rpm -qp --provides "${prepared[0]}" | grep -Fx "goodix-27c6-5125-runtime-commit($head)" >/dev/null; then
  rpm_path=${prepared[0]}
else
  command -v rpmbuild >/dev/null || fail prepared_rpm_missing_and_rpmbuild_unavailable
  "$here/build-rpm.sh" "$work/output"
  rpm_path=$(find "$work/output" -maxdepth 1 -type f -name "$package-*.rpm" -print -quit)
  [[ -n $rpm_path ]] || fail built_rpm_missing
fi
rpm_sha=$(sha256sum "$rpm_path" | awk '{print $1}')
sudo -- "$here/install.sh" --root-install "$rpm_path" "$rpm_sha" "$head" "$(id -un)"
