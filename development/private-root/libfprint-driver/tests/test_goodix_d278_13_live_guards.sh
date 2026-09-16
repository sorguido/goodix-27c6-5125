#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

operation=D278_13_INTEGRATED_PATH_ONCE

expect_ticket_refusal () {
  expected_reason=$1
  shift
  set +e
  refusal_output=$("$@" 2>&1)
  refusal_rc=$?
  set -e
  test "$refusal_rc" -eq 3
  echo "$refusal_output" | grep -F \
    "\"authorization_failure_reason\":\"$expected_reason\"" >/dev/null
  echo "$refusal_output" | grep -F \
    '"live_authorization_consumed":false' >/dev/null
  echo "$refusal_output" | grep -F '"real_production_secret_read":false' \
    >/dev/null
  echo "$refusal_output" | grep -F '"real_usb_access":false' >/dev/null
  echo "$refusal_output" | grep -F '"real_usb_submit":0' >/dev/null
}

write_ticket () {
  ticket_path=$1
  ticket_baseline=$2
  ticket_operation=$3
  ticket_nonce=$4
  printf '%s\n%s\n%s\n' \
    "D278_13_BASELINE_SHA=$ticket_baseline" \
    "D278_13_OPERATION=$ticket_operation" \
    "D278_13_NONCE=$ticket_nonce" >"$ticket_path"
  chmod 0600 "$ticket_path"
}

ticket_tests () {
  binary=$1
  reference=$2
  other_reference=$3
  build=$4
  ticket_dir=$(mktemp -d "$build/d278-13-ticket-test.XXXXXX")
  chmod 0700 "$ticket_dir"
  cleanup_ticket_tests () {
    find "$ticket_dir" -depth -delete 2>/dev/null || true
  }
  trap cleanup_ticket_tests EXIT HUP INT TERM

  expect_ticket_refusal ticket_missing \
    "$binary" --authorization-ticket-gate-only \
    "$ticket_dir/missing.ticket" "$reference"

  malformed="$ticket_dir/malformed.ticket"
  printf '%s\n' 'not-a-ticket' >"$malformed"
  chmod 0600 "$malformed"
  expect_ticket_refusal ticket_malformed \
    "$binary" --authorization-ticket-gate-only "$malformed" "$reference"

  wrong_baseline="$ticket_dir/wrong-baseline.ticket"
  write_ticket "$wrong_baseline" "$other_reference" "$operation" \
    SYNTHETIC_WRONG_BASELINE_NONCE_0001
  expect_ticket_refusal ticket_baseline_mismatch \
    "$binary" --authorization-ticket-gate-only "$wrong_baseline" "$reference"

  wrong_operation="$ticket_dir/wrong-operation.ticket"
  write_ticket "$wrong_operation" "$reference" D278_13_WRONG_OPERATION \
    SYNTHETIC_WRONG_OPERATION_NONCE_0001
  expect_ticket_refusal ticket_operation_mismatch \
    "$binary" --authorization-ticket-gate-only "$wrong_operation" "$reference"

  symlink_target="$ticket_dir/symlink-target.ticket"
  symlink_ticket="$ticket_dir/symlink.ticket"
  write_ticket "$symlink_target" "$reference" "$operation" \
    SYNTHETIC_SYMLINK_NONCE_0000000001
  ln -s "$symlink_target" "$symlink_ticket"
  expect_ticket_refusal ticket_file_policy \
    "$binary" --authorization-ticket-gate-only "$symlink_ticket" "$reference"

  valid="$ticket_dir/valid.ticket"
  write_ticket "$valid" "$reference" "$operation" \
    SYNTHETIC_VALID_NONCE_000000000001
  accepted_output=$(
    "$binary" --authorization-ticket-gate-only "$valid" "$reference"
  )
  echo "$accepted_output" | grep -F '"accepted":true' >/dev/null
  echo "$accepted_output" | grep -F \
    '"live_authorization_consumed":true' >/dev/null
  echo "$accepted_output" | grep -F '"real_usb_access":false' >/dev/null
  expect_ticket_refusal ticket_already_consumed \
    "$binary" --authorization-ticket-gate-only "$valid" "$reference"

  concurrent="$ticket_dir/concurrent.ticket"
  concurrent_one="$ticket_dir/concurrent-one.out"
  concurrent_two="$ticket_dir/concurrent-two.out"
  concurrent_one_rc="$ticket_dir/concurrent-one.rc"
  concurrent_two_rc="$ticket_dir/concurrent-two.rc"
  write_ticket "$concurrent" "$reference" "$operation" \
    SYNTHETIC_CONCURRENT_NONCE_00000001
  (
    set +e
    "$binary" --authorization-ticket-gate-only "$concurrent" "$reference" \
      >"$concurrent_one" 2>&1
    printf '%s\n' "$?" >"$concurrent_one_rc"
  ) &
  first_pid=$!
  (
    set +e
    "$binary" --authorization-ticket-gate-only "$concurrent" "$reference" \
      >"$concurrent_two" 2>&1
    printf '%s\n' "$?" >"$concurrent_two_rc"
  ) &
  second_pid=$!
  wait "$first_pid"
  wait "$second_pid"
  winners=$(grep -l '"accepted":true' "$concurrent_one" "$concurrent_two" |
    wc -l)
  consumed_losers=$(grep -l '"authorization_failure_reason":"ticket_already_consumed"' \
    "$concurrent_one" "$concurrent_two" | wc -l)
  test "$winners" -eq 1
  test "$consumed_losers" -eq 1
  test "$(sort "$concurrent_one_rc" "$concurrent_two_rc" | tr '\n' ' ')" = \
    '0 3 '

  echo D278_13_TICKET_MISSING_REJECTED=true
  echo D278_13_TICKET_MALFORMED_REJECTED=true
  echo D278_13_TICKET_WRONG_BASELINE_REJECTED=true
  echo D278_13_TICKET_WRONG_OPERATION_REJECTED=true
  echo D278_13_TICKET_SYMLINK_REJECTED=true
  echo ONE_AUTHORIZATION_ONE_ATTEMPT_GUARD_HOST_ONLY_PROVEN=true
  echo SECOND_USE_OF_AUTHORIZATION_REJECTED=true
  echo CONCURRENT_DOUBLE_CLAIM_WINNER_COUNT=1
  echo REAL_PRODUCTION_SECRET_READ=false
  echo REAL_USB_ACCESS=false
  echo REAL_USB_SUBMIT=0
  trap - EXIT HUP INT TERM
  cleanup_ticket_tests
}

baseline_tests () {
  root=$1
  build_script=$2
  fixture_parent=$(mktemp -d /tmp/goodix-d278-13-baseline-test.XXXXXX)
  fixture="$fixture_parent/repository"
  cleanup_baseline_tests () {
    find "$fixture_parent" -depth -delete 2>/dev/null || true
  }
  trap cleanup_baseline_tests EXIT HUP INT TERM
  git clone --quiet --no-hardlinks "$root" "$fixture"
  reference=$(git -C "$fixture" rev-parse HEAD)
  other_reference=$(git -C "$fixture" rev-parse "$reference^")

  set +e
  mismatch_output=$(D278_13_BASELINE_GUARD_TEST_ONLY=1 \
    D278_13_BASELINE_GUARD_TEST_ROOT="$fixture" \
    D278_13_BUILD_APPROVED_BASELINE_SHA="$other_reference" \
    "$build_script" 2>&1)
  mismatch_rc=$?
  set -e
  test "$mismatch_rc" -ne 0
  echo "$mismatch_output" | grep -F 'LIVE_BASELINE_MATCH=false' >/dev/null
  echo "$mismatch_output" | grep -F 'APPROVED_LIVE_BUILD_REFUSED=true' \
    >/dev/null
  test ! -e "$fixture/d278_integrated_path_once"

  printf '\nD278/13 synthetic unrelated dirty fixture.\n' \
    >>"$fixture/Goodix 27c6 5125 manuale tecnico.md"
  printf '\n/* D278/13 synthetic test-only dirty fixture. */\n' \
    >>"$fixture/libfprint-driver/tests/test_goodix_post_tls_lifecycle.c"
  D278_13_BASELINE_GUARD_TEST_ONLY=1 \
    D278_13_BASELINE_GUARD_TEST_ROOT="$fixture" \
    D278_13_BUILD_APPROVED_BASELINE_SHA="$reference" \
    "$build_script" >/dev/null

  printf '\n/* D278/13 synthetic live-critical dirty fixture. */\n' \
    >>"$fixture/tools/d278_integrated_path_once.c"
  set +e
  dirty_output=$(D278_13_BASELINE_GUARD_TEST_ONLY=1 \
    D278_13_BASELINE_GUARD_TEST_ROOT="$fixture" \
    D278_13_BUILD_APPROVED_BASELINE_SHA="$reference" \
    "$build_script" 2>&1)
  dirty_rc=$?
  set -e
  test "$dirty_rc" -ne 0
  echo "$dirty_output" | grep -F 'LIVE_BASELINE_MATCH=true' >/dev/null
  echo "$dirty_output" | grep -F 'LIVE_CRITICAL_SET_CLEAN=false' >/dev/null
  echo "$dirty_output" | grep -F 'APPROVED_LIVE_BUILD_REFUSED=true' \
    >/dev/null

  echo D278_13_APPROVED_MISMATCH_REJECTED=true
  echo LIVE_CRITICAL_DIRTY_SOURCE_REJECTED=true
  echo NON_LIVE_DOCUMENTATION_AND_TEST_DIRTY_IGNORED=true
  echo APPROVED_BINARY_PRODUCED_BY_NEGATIVE_TESTS=false
  echo TEST_APPROVED_SHA_INVENTED=false
  trap - EXIT HUP INT TERM
  cleanup_baseline_tests
}

case "${1:-}" in
  --ticket-only)
    test "$#" -eq 5
    ticket_tests "$2" "$3" "$4" "$5"
    ;;
  --baseline-only)
    test "$#" -eq 3
    baseline_tests "$2" "$3"
    ;;
  *)
    echo "usage: $0 --ticket-only <binary> <existing-ref> <other-existing-ref> <build-dir> | --baseline-only <git-root> <build-script>" >&2
    exit 2
    ;;
esac
