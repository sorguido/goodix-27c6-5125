# D278/14 — four consumed live attempts and corrective #6

## Outcome

```text
OUTCOME=PASS_HOST_ONLY_CORRECTIVE
ADVANCEMENT=STRUCTURAL_PRE_SESSION_RX_SYNCHRONIZATION_AND_GENERIC_OPERATOR_WORKFLOW_PROVEN_HOST_ONLY
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
CANONICAL_DOCUMENTATION=UPDATED
START_BRANCH=main
START_HEAD=7ce15fa72d0806f34202d2603ef397a740453c63
```

This corrective performs no live execution. It records the fourth consumed
authorization, retires corrective #5 before any live validation, implements a
passive pre-protocol RX quiet boundary in the existing backend/context, and
consolidates the tracked baseline-bound operator workflow.

## Live attempts

The four attempts remain distinct:

- `LIVE_ATTEMPT_1`: baseline
  `2172e750ae7c100a3a891ba25d0797286230a4ab`; host binding abort before
  protocol (`SIGABRT`, exit 134).
- `LIVE_ATTEMPT_2`: baseline
  `fceae05d9ff3ed14348f9031706e70d5a808ff91`; current A2 ACK received, but
  no second physical IN was armed and the run reached its one-shot deadline.
- `LIVE_ATTEMPT_3`: baseline
  `87c1bf89d0ba28497313f4bb75a8de4bbdb37b75`; first IN returned an A2
  typed-shaped frame before ACK and strict parsing terminated.
- `LIVE_ATTEMPT_4`: baseline
  `7ce15fa72d0806f34202d2603ef397a740453c63`; first IN returned an accepted
  A2 ACK and the rearmed second IN returned another valid-shaped A2 ACK;
  duplicate ACK parsing terminated.

Canonical attempt #4 evidence:

```text
D278_14_TOTAL_LIVE_ATTEMPTS=4
D278_14_TOTAL_CONSUMED_AUTHORIZATIONS=4

D278_14_ATTEMPT_4_BASELINE=7ce15fa72d0806f34202d2603ef397a740453c63
D278_14_ATTEMPT_4_BINARY_SHA256=01f6e3ff9cc023ade55d69f94108d8546d0ee321b90475aa43b1128f6255089e
D278_14_ATTEMPT_4_OUTCOME=FAIL_DUPLICATE_A2_ACK_AFTER_REARM
D278_14_ATTEMPT_4_FAILURE_CLASS=INTEGRATED_PATH_TERMINAL
D278_14_ATTEMPT_4_PHASE_TRACE=REENTRY_RECOVERY_A2>TERMINAL
D278_14_ATTEMPT_4_SECURE_COMMAND_COUNT=1
D278_14_ATTEMPT_4_ACK_COUNT=1
D278_14_ATTEMPT_4_TYPED_COUNT=0
D278_14_ATTEMPT_4_PHYSICAL_SUBMIT_COUNT=3
D278_14_ATTEMPT_4_PHYSICAL_IN_SUBMIT_COUNT=2
D278_14_ATTEMPT_4_PHYSICAL_OUT_SUBMIT_COUNT=1
D278_14_ATTEMPT_4_PHYSICAL_IN_COMPLETION_COUNT=2
D278_14_ATTEMPT_4_PHYSICAL_OUT_COMPLETION_COUNT=1
D278_14_ATTEMPT_4_PROTOCOL_FAILURE_KIND=ACK_SHAPE_MISMATCH
D278_14_ATTEMPT_4_OBSERVED_OUTER_TYPE=0xA0
D278_14_ATTEMPT_4_OBSERVED_A0_CONTROL=0xB0
D278_14_ATTEMPT_4_OBSERVED_ACK_ECHO=0xA2
D278_14_ATTEMPT_4_OBSERVED_ACK_STATUS=0x01
D278_14_ATTEMPT_4_OBSERVED_BODY_LENGTH=2
D278_14_ATTEMPT_4_REENTRY_PRE_ACK_TYPED_OBSERVED=false
D278_14_ATTEMPT_4_REENTRY_PRE_ACK_TYPED_DISCARD_COUNT=0
D278_14_ATTEMPT_4_A8_REACHED=false
D278_14_ATTEMPT_4_TLS_REACHED=false
D278_14_ATTEMPT_4_POST_TLS_REACHED=false
D278_14_ATTEMPT_4_STOP_TIME_MS=158
D278_14_ATTEMPT_4_BACKEND_DRAINED=true
D278_14_ATTEMPT_4_CLEANUP_COMPLETE=true
D278_14_ATTEMPT_4_PROJECT_SECRET_ZEROIZED=true
D278_14_ATTEMPT_4_RETRY_COUNT=0
D278_14_ATTEMPT_4_REOPEN_COUNT=0
D278_14_ATTEMPT_4_DEVICE_RESET_COUNT=0
D278_14_ATTEMPT_4_CLEAR_HALT_COUNT=0
D278_14_ATTEMPT_4_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_14_ATTEMPT_4_CORE_DUMP_LIMIT=0
```

Evidence classification and bounded model:

```text
INTER_SESSION_RX_RESIDUE_OBSERVED_DIRECTLY=false
INTER_SESSION_RX_RESIDUE_MODEL=STRONG_HYPOTHESIS
NEW_OPEN_CLAIM_IMPLIES_EMPTY_RX=DISPROVEN_AS_SAFE_ASSUMPTION
BACKEND_DRAINED_IMPLIES_DEVICE_RX_EMPTY=false

attempt #2:
  current A2 ACK read
  typed A2 not read because no second IN

attempt #3:
  first IN receives A2 typed-shaped frame before ACK
  run fails
  current attempt #3 ACK may remain unread

attempt #4:
  first IN produces accepted A2 ACK
  second IN produces another valid-shaped A2 ACK
  run fails as duplicate ACK
```

This sequence strongly supports inter-session RX residue. It does not prove
the exact origin, age, or causal provenance of any quarantined or observed
frame.

## Correctives #1–#5 retained as history

```text
CORRECTIVE_1=FPDEVICE_USB_BINDING_CONSTRUCTION
CORRECTIVE_2=IN_COMPLETION_REARM_UNIFICATION
CORRECTIVE_3=OPERATOR_UX_HISTORY_AND_STOP_TELEMETRY
CORRECTIVE_4=EXACT_BANNERS_AND_TERMINAL_STOP_EXCLUSIVITY
CORRECTIVE_5=BOUNDED_PRE_ACK_PINNED_A2_TOLERANCE
D278_14_CORRECTIVE_5_STATUS=SUPERSEDED_BEFORE_NEXT_LIVE
D278_14_CORRECTIVE_5_LIVE_VALIDATION_PERFORMED=false
```

Corrective #5 existed only in host tests and production-shaped code at
baseline `7ce15fa72d0806f34202d2603ef397a740453c63`. Corrective #6 removes its
one-frame discard behavior and result class. The protocol contract is strict
again: ACK must precede typed A2; typed-before-ACK, duplicate ACK, wrong ACK
status, wrong typed control/pin/shape, or malformed input is terminal.

```text
CORRECTIVE_5_RUNTIME_TOLERANCE_RETIRED=true
STRICT_A2_ACK_THEN_TYPED_RESTORED=true
```

## Corrective #6 — structural pre-session RX synchronization

The live-shaped physical order is now:

```text
authorization gate
protected material preparation
target enumeration and Goodix FpDevice construction
USB open and claim
one GoodixDeviceContext operator epoch / generation
PRE_SESSION_RX_SYNC
only after PASS: post-TLS configuration, secure-session start, first A2 OUT
```

`GoodixFpiUsbBackend` records each outstanding IN purpose as either
`PROTOCOL_RX` or `PRE_SESSION_SYNC_RX`. The sync purpose is the same physical
backend and never reaches `GoodixUsbRouter` or `GoodixSecureSession`. Its
completion callback receives only length/error metadata for bounded counting;
raw bytes are neither parsed nor logged. `context_usb_in_completed()` remains
the normal protocol rearm callback and is not invoked for sync completions.

The production receive uses the existing `FpiUsbTransfer` timeout argument.
Repository-local libfprint passes through the error from
`g_usb_device_bulk_transfer_finish()`, so the accepted quiet-boundary error is
the actual GUsb classification:

```text
timeout_domain=G_USB_DEVICE_ERROR
timeout_code=G_USB_DEVICE_ERROR_TIMED_OUT
PRE_SESSION_RX_QUIET_TIMEOUT_MS=250
PRE_SESSION_RX_MAX_COMPLETIONS=16
PRE_SESSION_RX_MAX_BYTES=65536
PRE_SESSION_RX_MAX_TOTAL_MS=2000
```

A quiet timeout passes only while sync is active, with zero returned data and
no outstanding IN/OUT. Each non-empty success is counted, discarded and
immediately followed by one new timed IN. A non-timeout error, empty success,
completion/byte/time bound failure, OUT attempt, or secure-session start before
PASS fails closed before A2.

The integrated tests use `GoodixDeviceContext` and
`goodix_fpi_usb_backend_complete_receive()` directly. They quarantine stale
typed-A2/ACK-A2/typed-A2 as separate completions and the same sequence
concatenated into one completion, prove zero router delivery/command/OUT before
quiet PASS, then submit exactly one current A2 and advance with current
ACK→typed→A8. Maximum physical IN outstanding remains one.

```text
PRE_SESSION_RX_SYNC_IMPLEMENTED=true
PRE_SESSION_RX_CLEAN_QUIET_BOUNDARY_HOST_ONLY_PROVEN=true
PRE_SESSION_RX_RESIDUE_CHAIN_QUARANTINED_HOST_ONLY_PROVEN=true
PRE_SESSION_RX_MULTI_FRAME_COMPLETION_QUARANTINED_HOST_ONLY_PROVEN=true
PRE_SESSION_RX_NON_TIMEOUT_ERROR_FAIL_CLOSED=true
PRE_SESSION_RX_BOUNDS_FAIL_CLOSED=true
PRE_SESSION_RX_OUT_BEFORE_SYNC_REJECTED=true
PRE_SESSION_RX_SECURE_START_BEFORE_SYNC_REJECTED=true
SAME_GOODIX_DEVICE_CONTEXT=true
SINGLE_GOODIX_DEVICE_CONTEXT=true
SINGLE_USB_BACKEND_OWNER=true
SINGLE_USB_ROUTER=true
SINGLE_PHYSICAL_IN_OWNER=true
NO_PARALLEL_RX_DRAIN_STACK=true
MAX_PHYSICAL_IN_OUTSTANDING=1
```

Only bounded non-sensitive live-shaped telemetry was added:

```text
pre_session_rx_sync_started
pre_session_rx_sync_completed
pre_session_rx_quiet_boundary
pre_session_rx_discarded_completion_count
pre_session_rx_discarded_byte_count
pre_session_rx_timeout_count
pre_session_rx_non_timeout_error_count
pre_session_rx_max_outstanding
pre_session_rx_elapsed_ms
pre_session_rx_result
first_protocol_out_after_rx_sync
SENSITIVE_RX_SYNC_TELEMETRY_EXPOSURE=false
```

## Generic baseline-bound operator workflow

The tracked launcher now exposes:

```text
--host-only-prelive
--prepare-approved-live <FULL_APPROVED_SHA>
--run-approved-live <PREPARED_BUILD_DIR> --grant <GRANT_FILE>
```

Preparation is normal-user-only, requires canonical `main`, exact HEAD and a
clean live-critical set, runs canonical host-only prelive, builds from the
approved Git archive with the existing build guard, and writes
`d278-14-prepared.state` containing the full baseline, operation, build path
and binary SHA-256. It does not touch USB, production material, grants, or live.

The one-shot mode is root-only, sets `ulimit -c 0`, rechecks canonical HEAD and
live-critical cleanliness, validates state and the prepared binary hash,
validates a nonsymlink grant with private permissions and exact
baseline/operation/unique ID, atomically claims that ID once, creates a private
runtime ticket, copies and re-hashes the exact prepared binary, saves a live
log and never rebuilds. The baseline is data; no new baseline-specific wrapper
is required. The legacy direct mode is a fail-closed refusal.

Host-only workflow tests cover wrong HEAD, dirty live-critical input, exact
state binding, binary hash mismatch, malformed/baseline-mismatched/symlink
grants, second use, concurrent double claim and direct unprepared invocation.
The test-only branch can only skip live; it cannot enable it.

```text
GENERIC_BASELINE_BOUND_OPERATOR_WORKFLOW_HOST_ONLY_PROVEN=true
DIRECT_UNPREPARED_LIVE_PATH_REJECTED=true
ONE_AUTHORIZATION_ONE_ATTEMPT_GUARD_HOST_ONLY_PROVEN=true
SECOND_USE_OF_AUTHORIZATION_REJECTED=true
```

## Methodological review before any future live

1. What changes from attempt #4: synchronization occurs passively before the
   first protocol OUT, rather than tolerating one response inside the active A2
   transaction.
2. New hypothesis: a bounded sequence of immediately available RX completions
   followed by a genuine timed quiet interval isolates inter-session residue
   without interpreting or attributing it.
3. If another authorized run fails at the same first A2 boundary, do not add
   another shape-specific tolerance or repeat the run; reassess endpoint/device
   queue semantics from the new sync telemetry and captured failure boundary.

This is a substantive method and hypothesis change, not a pacing, logging,
packaging or preflight-only change. It does not authorize a future live.

## Regression and no-live boundary

All commands ran from the Git root except the explicitly required canonical
prelive invocation, which ran from `/tmp`. Flatpak suites used Freedesktop SDK
25.08 with networking disabled.

| Check | Result |
| --- | --- |
| `run_goodix_fpimage_device_test.sh` | 18/18 normal; 18/18 ASAN/UBSAN PASS |
| `run_goodix_d278_secure_session_test.sh` | 24/24 normal; 24/24 ASAN/UBSAN PASS |
| `run_goodix_d278_12_post_tls_test.sh` | 6/6 normal; 6/6 ASAN/UBSAN PASS |
| `run_goodix_d278_02_test.sh` | 62/62 normal; 62/62 ASAN/UBSAN PASS |
| D278/13 adapter build/link + physical constructor | PASS |
| baseline and original ticket guards | PASS |
| D278/14 prepared-state/grant workflow guards | PASS |
| persistent-recovery source/symbol audits | PASS |
| duplicate-stack and legacy-harness audits | PASS |
| canonical `--host-only-prelive` from `/tmp` | PASS |
| changed shell `bash -n` and `sh -n` | PASS |
| `git diff --check` | PASS |

```text
NO_FLASH=true
NO_IAP=true
NO_CLEARAPP=true
NO_PSK_PROVISIONING=true
NO_PSK_REPLACEMENT=true
NO_OTP_WRITE=true
NO_FACTORY_WRITE=true
NO_PERSISTENT_DEVICE_WRITE=true
NO_PERSISTENT_VID_PID_MODE_CHANGE=true
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
REAL_USB_ACCESS=false
REAL_USB_SUBMIT=0
REAL_PRODUCTION_SECRET_READ=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

## Git-native review set

```text
PARENT_HEAD=7ce15fa72d0806f34202d2603ef397a740453c63
REVIEW_SET=PARENT_HEAD_PLUS_FINAL_COMMIT_ON_main_PLUS_CURRENT_D278_14_CHANGED_FILES
```

No ZIP/Base64, branch change, merge, reset, core-dump operation, real USB
access, production-secret read, grant creation, or live execution was performed
by corrective #6.
