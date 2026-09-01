#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

root=${1:?usage: test_goodix_d278_14_workflow.sh <git-root>}
fixture_parent=$(mktemp -d /tmp/goodix-d278-14-workflow-test.XXXXXX)
fixture="$fixture_parent/repository"
build=/tmp/goodix-d278-14-test-build.$$
cleanup () {
  find "$fixture_parent" -depth -delete 2>/dev/null || true
  find "$build" -depth -delete 2>/dev/null || true
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

concurrent="$fixture_parent/concurrent.grant"
out_one="$fixture_parent/concurrent-one.out"
out_two="$fixture_parent/concurrent-two.out"
write_grant "$concurrent" "$reference" D278_13_INTEGRATED_PATH_ONCE \
  SYNTHETIC_CONCURRENT_GRANT_01
(env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$concurrent" \
  >"$out_one" 2>&1 || true) &
pid_one=$!
(env D278_14_WORKFLOW_GUARD_TEST_ONLY=1 \
  "$launcher" --run-approved-live "$build" --grant "$concurrent" \
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
echo SECOND_USE_OF_AUTHORIZATION_REJECTED=true
echo CONCURRENT_DOUBLE_CLAIM_WINNER_COUNT=1
echo DIRECT_UNPREPARED_LIVE_PATH_REJECTED=true
echo GENERIC_BASELINE_BOUND_OPERATOR_WORKFLOW_HOST_ONLY_PROVEN=true
echo REAL_USB_ACCESS=false
echo REAL_USB_SUBMIT=0
echo REAL_PRODUCTION_SECRET_READ=false
echo LIVE_EXECUTION_PERFORMED=false
