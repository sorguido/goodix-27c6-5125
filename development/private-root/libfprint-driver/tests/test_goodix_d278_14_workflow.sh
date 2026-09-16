#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

root=${1:?usage: test_goodix_d278_14_workflow.sh <git-root>}
fixture_parent=$(mktemp -d /tmp/goodix-d278-14-workflow-test.XXXXXX)
fixture="$fixture_parent/repository"
build=/tmp/goodix-d278-14-test-build.$$
build2=/tmp/goodix-d278-14-test-build2.$$
cleanup () {
  find "$fixture_parent" -depth -delete 2>/dev/null || true
  find "$build" -depth -delete 2>/dev/null || true
  find "$build2" -depth -delete 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

git clone --quiet --no-hardlinks "$root" "$fixture"
cp "$root/operator_kit/d278-13-integrated-path-once.sh" \
  "$fixture/operator_kit/d278-13-integrated-path-once.sh"
git -C "$fixture" add operator_kit/d278-13-integrated-path-once.sh
if ! git -C "$fixture" diff --cached --quiet; then
  git -C "$fixture" -c user.name='D278 host-only test' \
    -c user.email='d278-host-only@example.invalid' \
    commit --quiet -m 'Synthetic current launcher fixture'
fi
launcher="$fixture/operator_kit/d278-13-integrated-path-once.sh"
reference=$(git -C "$fixture" rev-parse HEAD)
other_reference=$(git -C "$fixture" rev-parse "$reference^")
test_binary="$fixture_parent/test-binary"
export D278_14_TEST_CLAIM_ROOT="$fixture_parent/claims"
printf '%s\n' '#!/bin/sh' 'exit 99' >"$test_binary"
chmod 0700 "$test_binary"

expect_refusal () {
  local expected=$1 output rc
  shift
  set +e
  output=$("$@" 2>&1)
  rc=$?
  set -e
  [[ $rc -eq 3 ]]
  grep -F "APPROVED_WORKFLOW_REFUSAL_REASON=$expected" <<<"$output" >/dev/null
  grep -F 'REAL_USB_ACCESS=false' <<<"$output" >/dev/null
  grep -F 'REAL_USB_SUBMIT=0' <<<"$output" >/dev/null
  grep -F 'REAL_PRODUCTION_SECRET_READ=false' <<<"$output" >/dev/null
  grep -F 'LIVE_EXECUTION_PERFORMED=false' <<<"$output" >/dev/null
}

write_grant () {
  local path=$1 baseline=$2 operation=$3 grant_id=$4
  printf '%s\n%s\n%s\n' \
    "D278_14_BASELINE_SHA=$baseline" \
    "D278_14_OPERATION=$operation" \
    "D278_14_GRANT_ID=$grant_id" >"$path"
  chmod 0600 "$path"
}

# --- Defect 1: bounded safe.directory on every root-path Git call ---
git_audit_dir="$fixture_parent/git-audit"
mkdir -p "$git_audit_dir"
real_git=$(command -v git)
cat > "$git_audit_dir/git" <<EOF
#!/usr/bin/env bash
printf '%s\t%s\n' "\$PWD" "\$*" >> "$fixture_parent/git-audit.log"
exec "$real_git" "\$@"
EOF
chmod +x "$git_audit_dir/git"

audit_build="$fixture_parent/audit-build"
mkdir -p "$audit_build"
(
  PATH="$git_audit_dir:$PATH"
  env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
    D278_14_TEST_BUILD_DIR="$audit_build" \
    D278_14_TEST_BINARY="$test_binary" \
    "$launcher" --prepare-approved-live "$reference" >/dev/null
)

audit_fail=0
while IFS=$'\t' read -r _cwd _args; do
  [[ -n ${_args:-} ]] || continue
  [[ $_args == *"$fixture"* ]] || continue
  sub=
  for t in $_args; do
    [[ $t == -* ]] && continue
    sub=$t
    break
  done
  case $sub in
    rev-parse|branch|show-current|status|cat-file|ls-tree|archive)
      [[ $_args == *"safe.directory=$fixture"* ]] || audit_fail=1 ;;
  esac
done < "$fixture_parent/git-audit.log"
[[ $audit_fail -eq 0 ]]
echo REAL_SUDO_GIT_SAFE_DIRECTORY_HOST_ONLY_PROVEN=true

expect_refusal HEAD_MISMATCH env \
  D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  D278_14_TEST_BUILD_DIR="$build" D278_14_TEST_BINARY="$test_binary" \
  "$launcher" --prepare-approved-live "$other_reference"

printf '%s\n' '/* synthetic live-critical dirt */' \
  >>"$fixture/tools/d278_integrated_path_once.c"
expect_refusal LIVE_CRITICAL_SOURCE_DIRTY env \
  D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  D278_14_TEST_BUILD_DIR="$build" D278_14_TEST_BINARY="$test_binary" \
  "$launcher" --prepare-approved-live "$reference"
git -C "$fixture" restore -- tools/d278_integrated_path_once.c

prepare_output=$(env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  D278_14_TEST_BUILD_DIR="$build" D278_14_TEST_BINARY="$test_binary" \
  "$launcher" --prepare-approved-live "$reference")
grep -F "APPROVED_BASELINE=$reference" <<<"$prepare_output" >/dev/null
grep -F "PREPARED_BUILD_DIR=$build" <<<"$prepare_output" >/dev/null
grep -F "D278_14_BASELINE_SHA=$reference" \
  "$build/d278-14-prepared.state" >/dev/null

grant="$fixture_parent/hash-mismatch.grant"
write_grant "$grant" "$reference" D278_13_INTEGRATED_PATH_ONCE \
  SYNTHETIC_HASH_MISMATCH_0001
printf '%s\n' '# modified' >>"$build/d278_integrated_path_once"
expect_refusal BINARY_SHA256_MISMATCH env \
  D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$grant"
cp "$test_binary" "$build/d278_integrated_path_once"

malformed="$fixture_parent/malformed.grant"
printf '%s\n' malformed >"$malformed"
chmod 0600 "$malformed"
expect_refusal GRANT_MALFORMED env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$malformed"

wrong="$fixture_parent/wrong-baseline.grant"
write_grant "$wrong" "$other_reference" D278_13_INTEGRATED_PATH_ONCE \
  SYNTHETIC_WRONG_BASELINE_0001
expect_refusal GRANT_BASELINE_MISMATCH env \
  D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$wrong"

# --- Defect 2: grant owner/mode policy under simulated sudo ---
# A bounded stat shim lets the production script believe the test claim-root is
# root-owned, without requiring real root privileges in the host-only suite.
stat_shim_dir="$fixture_parent/stat-shim"
mkdir -p "$stat_shim_dir"
real_stat=$(command -v stat)
cat > "$stat_shim_dir/stat" <<EOF
#!/usr/bin/env bash
fake_root=\${D278_14_STAT_FAKE_ROOT:-}
path=\${!#}
if [[ -n \$fake_root && \$path == "\$fake_root" ]]; then
  case "\$*" in
    *%u*) echo 0; exit 0 ;;
    *%a*) echo 700; exit 0 ;;
  esac
fi
exec "$real_stat" "\$@"
EOF
chmod +x "$stat_shim_dir/stat"

sudo_env () {
  PATH="$stat_shim_dir:$PATH" D278_14_STAT_FAKE_ROOT="$D278_14_TEST_CLAIM_ROOT" \
    env "$@"
}

my_uid=$(id -u)
sudo_owned="$fixture_parent/sudo-owned.grant"
write_grant "$sudo_owned" "$reference" D278_13_INTEGRATED_PATH_ONCE \
  SYNTHETIC_SUDO_OWNED_GRANT_0001
sudo_output=$(sudo_env EUID=0 SUDO_UID="$my_uid" \
  D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$sudo_owned")
grep -F 'RUNTIME_TICKET_CREATED=true' <<<"$sudo_output" >/dev/null
grep -F 'LIVE_EXECUTION_PERFORMED=false' <<<"$sudo_output" >/dev/null
echo SUDO_OPERATOR_OWNED_GRANT_ACCEPTED_HOST_ONLY=true

unrelated="$fixture_parent/unrelated-owner.grant"
write_grant "$unrelated" "$reference" D278_13_INTEGRATED_PATH_ONCE \
  SYNTHETIC_UNRELATED_OWNER_000001
expect_refusal GRANT_FILE_POLICY sudo_env EUID=0 SUDO_UID=99999 \
  D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$unrelated"
echo UNRELATED_GRANT_OWNER_REJECTED_HOST_ONLY=true

unsafe_mode="$fixture_parent/unsafe-mode.grant"
write_grant "$unsafe_mode" "$reference" D278_13_INTEGRATED_PATH_ONCE \
  SYNTHETIC_UNSAFE_MODE_0000001
chmod 0666 "$unsafe_mode"
expect_refusal GRANT_FILE_POLICY sudo_env EUID=0 SUDO_UID="$my_uid" \
  D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$unsafe_mode"
echo GRANT_UNSAFE_MODE_REJECTED=true

# --- Defect 2: symlink rejected ---
symlink_target="$fixture_parent/symlink-target.grant"
symlink_grant="$fixture_parent/symlink.grant"
write_grant "$symlink_target" "$reference" D278_13_INTEGRATED_PATH_ONCE \
  SYNTHETIC_SYMLINK_000000001
ln -s "$symlink_target" "$symlink_grant"
expect_refusal GRANT_FILE_POLICY env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$symlink_grant"

valid="$fixture_parent/valid.grant"
write_grant "$valid" "$reference" D278_13_INTEGRATED_PATH_ONCE \
  SYNTHETIC_VALID_GRANT_000001
valid_output=$(env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$valid")
grep -F 'RUNTIME_TICKET_CREATED=true' <<<"$valid_output" >/dev/null
grep -F 'LIVE_EXECUTION_PERFORMED=false' <<<"$valid_output" >/dev/null
expect_refusal GRANT_ALREADY_CONSUMED env \
  D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$valid"

# --- Defect 3: one-shot claim persists across runtime/build cleanup ---
persistent="$fixture_parent/persistent.grant"
write_grant "$persistent" "$reference" D278_13_INTEGRATED_PATH_ONCE \
  SYNTHETIC_PERSISTENT_CLAIM_0001
env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$persistent" >/dev/null
find "$build" -depth -delete 2>/dev/null || true
mkdir -p "$build2"
env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  D278_14_TEST_BUILD_DIR="$build2" D278_14_TEST_BINARY="$test_binary" \
  "$launcher" --prepare-approved-live "$reference" >/dev/null
expect_refusal GRANT_ALREADY_CONSUMED env \
  D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build2" --grant "$persistent"
echo PERSISTENT_ONE_SHOT_GRANT_CLAIM_HOST_ONLY_PROVEN=true

concurrent="$fixture_parent/concurrent.grant"
out_one="$fixture_parent/concurrent-one.out"
out_two="$fixture_parent/concurrent-two.out"
write_grant "$concurrent" "$reference" D278_13_INTEGRATED_PATH_ONCE \
  SYNTHETIC_CONCURRENT_GRANT_01
(env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build2" --grant "$concurrent" \
  >"$out_one" 2>&1 || true) &
pid_one=$!
(env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build2" --grant "$concurrent" \
  >"$out_two" 2>&1 || true) &
pid_two=$!
wait "$pid_one"
wait "$pid_two"
[[ $(grep -l 'RUNTIME_TICKET_CREATED=true' "$out_one" "$out_two" | wc -l) -eq 1 ]]
[[ $(grep -l 'APPROVED_WORKFLOW_REFUSAL_REASON=GRANT_ALREADY_CONSUMED' \
       "$out_one" "$out_two" | wc -l) -eq 1 ]]

expect_refusal DIRECT_UNPREPARED_LIVE_PATH_REJECTED \
  "$launcher" --live-integrated-once

echo PREPARE_WRONG_HEAD_REJECTED=true
echo PREPARE_DIRTY_LIVE_CRITICAL_SOURCE_REJECTED=true
echo PREPARED_STATE_BASELINE_BOUND=true
echo PREPARED_BINARY_SHA_MISMATCH_REJECTED=true
echo GRANT_BASELINE_MISMATCH_REJECTED=true
echo GRANT_MALFORMED_REJECTED=true
echo GRANT_SYMLINK_REJECTED=true
echo GRANT_UNSAFE_MODE_REJECTED=true
echo SECOND_USE_OF_AUTHORIZATION_REJECTED=true
echo CONCURRENT_DOUBLE_CLAIM_WINNER_COUNT=1
echo DIRECT_UNPREPARED_LIVE_PATH_REJECTED=true
echo ONE_AUTHORIZATION_ONE_ATTEMPT_GUARD_HOST_ONLY_PROVEN=true
echo GENERIC_BASELINE_BOUND_OPERATOR_WORKFLOW_HOST_ONLY_PROVEN=true
echo REAL_USB_ACCESS=false
echo REAL_USB_SUBMIT=0
echo REAL_PRODUCTION_SECRET_READ=false
echo LIVE_EXECUTION_PERFORMED=false
