<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/57 — stage-8 live attempt and contact-boundary corrective

## Live attempt 01: operator-declared result

The operator executed exactly one authorized live action on full SHA
`1afe72e4d875daa60319cbbfb55d19a1e151de86`. That grant is consumed and the
attempt is not retryable. The run reached two completed libfprint stages and
then stopped fail-closed:

```text
OPEN_SUCCEEDED=true
STAGE_COMPLETATO=1/8
STAGE_COMPLETATO=2/8
ENROLLMENT_SUCCEEDED=false
ERRORE_ENROLLMENT=A0 frame does not match the expected enrollment event
RUN_RETURN_CODE=1
GRANT_CONSUMED=true
RETRY_AUTHORIZED=false
```

The operator also declared `primary B0=2`, `auxiliary B0=1`, `ACK=9`, one
inter-stage re-arm and two `0x32` commands. Close, context drain, interface
release and runtime-material cleanup all reported success; secure/post-TLS
retry, reopen and known persistent-family counts were zero.

These values are currently secondary evidence transcribed from the operator's
report. The named source directory,
`/var/tmp/goodix-d279-57-results/20260908T194249Z-1afe72e4d875`, is root-only
and was not read through elevated privileges by the AI. Consequently the
original `operator.log` and `summary.env` have not yet been imported or hashed
in Git. The corrected kit provides a separate `--export-results` operation
that copies only those two files, verifies source/copy SHA-256 equality and
performs zero USB enumeration or live action.

## AI-PM finding

The first-cycle OEM shape permits release after its primary B0 branch. The
repeated-cycle shape does not: after `PRIMARY_B0` it still requires
`0x34/ACK`, `0x36/ACK`, `IRQ0100`, `0x20/ACK`, auxiliary B0 and the final
`0x34/ACK` before `IRQ0200`. Therefore `PRIMARY_SAMPLE_DELIVERED` is biometric
sample provenance, not `PHYSICAL_CONTACT_CYCLE_COMPLETE`.

The 2-primary/1-auxiliary/9-ACK counts are strongly consistent with the
operator following the former progress-driven “remove finger” prompt during
stage 2 and the device then producing an early `IRQ0200` while the host
expected `IRQ0100`. This remains an inference: attempt 01 did not expose the
unexpected A0 control/IRQ class in sanitized telemetry, and no raw protected
payload is available or claimed.

## Corrective production semantics

For intermediate stages, the primary image is retained after `PRIMARY_B0` and
delivered to `FpImageDevice` only after the final `0x34/ACK` has armed
`IRQ0200`. That delivery moves the standard libfprint image state to
`AWAIT_FINGER_OFF` and changes public `finger-status` from
`NEEDED|PRESENT` to `PRESENT`; the operator client derives “remove finger”
from that physical-status signal. Enrollment progress remains biometric
progress and prints no physical instruction.

The terminal sample is also delivered at the final `0x34/ACK`, so stage 8
produces the same standard release-ready status as stages 1–7. A bounded
internal `FpImageDevice` hold suppresses only successful final enrollment
completion until the terminal `IRQ0200` has been fully consumed. If SIGFM
finishes first, the action remains active; if the IRQ arrives first,
completion waits for SIGFM. Fatal extraction/copy failures and cancellation
are not held and retain their immediate fail-closed deactivation path. In
particular, a retry-class extraction failure after the terminal hold was armed
is promoted to a fatal `DATA_INVALID`: the sensor-side final acquisition has
already been consumed, so libfprint must not request an unavailable ninth
sample or remain held without a template sample.

Mismatch telemetry now records only sanitized structure: expected enrollment
event, observed A0 control and, for structurally classifiable 16-byte
`0x32/0x34/0x36` events, IRQ and flags. No body, raster, template, secret or
protected plaintext is exported.

## Decision and evidence separation

The authentic D279/56 protected replay selected eight distinct ATTEMPT02 R2
samples and terminated at `MAX_STAGE_REACHED`. D279/57 uses that aggregate-only
result to stage a fixed-eight production candidate. It does not import the
Rockytkg USB transcript, does not infer enrollment policy from D279/54 identify,
and does not yet implement duplicate-driven dynamic convergence.

The original 21-stage ATTEMPT02 behavior remains the target-local wire and
regression profile. Fixed eight is limited to the production SIGFM candidate
needed to test one unresolved APP12509 fact: whether a complete stage-8 release
may terminate without sending the next `0x32`.

## Implementation boundary

`GOODIX_SIGFM_ENROLL_MAX_STAGES` is eight and drives both the production graph
and `FpDeviceClass.nr_enroll_stages`. `GOODIX_TARGET_LOCAL_ENROLL_STAGES` remains
21 and is not redefined or repurposed.

The expected terminal audit is exact:

```text
configured/observed/completed stages = 8
intermediate delivery deferred until release-ready = true
terminal delivery deferred until release-ready = true
terminal completion hold/release/abort = 1/1/0
terminal completion held at close = false
terminal transitions = 1
primary B0 = 8
inter-stage re-arms = 7
0x32 commands = 8
post-stage-8 re-arm = 0
known persistent-family sends = 0
retry/reopen/second action = 0
rejected inbound / last mismatch = 0 / NONE on success
backend drained, interface released, runtime material absent at close
```

The one-shot client calls `fp_device_enroll_sync()` exactly once, keeps the
template in memory, closes once and exports only sanitized telemetry. A
successful D279/57 run cannot establish reusability: a later action in a fresh
open epoch must remain separate and receive a new review and authorization.

## Multi-sample error propagation review

The D279/52 checked path remains authoritative. SIGFM enrollment calls
`fpi_image_device_add_enroll_sample_checked()`, which performs the atomic
`fpi_print_add_print_checked()` operation before incrementing the libfprint
stage. Extraction or `goodix_sigfm_sample_copy()` failure aborts the action and
deactivates it; no progress is reported and no stage advances for a sample that
was not added to the template.

Both `checked-append-atomic-failure` and
`enroll-stage-stable-on-copy-failure` pass in normal and ASan/UBSan builds.

## Offline verification of the corrective

- focused `FpImageDevice` stage-8 class/action test: PASS normal and
  ASan/UBSan;
- full-TLS production enrollment test: PASS normal and ASan/UBSan, including
  exact 8/7/8 terminal counts, SIGFM-completes-before-IRQ ordering, terminal
  hold/release 1/1 and same-epoch second-action rejection;
- focused `FpImageDevice` terminal hold test: PASS normal and ASan/UBSan for
  the inverse IRQ-before-SIGFM ordering;
- focused terminal SIGFM-failure test: PASS normal and ASan/UBSan; the action
  deactivates with `DATA_INVALID`, reports zero progress and cannot deadlock or
  retry even when `IRQ0200` releases the hold before SIGFM reports failure;
- Fedora 44 production-shaped real Rockytkg SIGFM/OpenCV action: PASS with
  eight samples, serialization/identify and standard fprintd ABI checks;
- D279/52 SIGFM print/core suite: PASS normal and ASan/UBSan;
- D279/11 model and D279/13 lifecycle adapter: PASS normal and ASan/UBSan,
  retaining configurable 2/3/21 profiles;
- explicit repeated-stage early-finger-up fixture: PASS normal and
  ASan/UBSan; no image/stage is delivered after the primary B0, the early
  `IRQ0200` fails closed while `IRQ0100` is expected, and sanitized telemetry
  reports expected event/control/IRQ/flags;
- full-TLS production `FpImageDevice` executable closure: PASS normal and
  ASan/UBSan; at primary B0 the state is still `CAPTURE` with
  `NEEDED|PRESENT`, while final `0x34/ACK` yields `AWAIT_FINGER_OFF` with
  `PRESENT` before `IRQ0200`;
- the historical D279/24 context fixture was reproduced red, reviewed and
  corrected: its handoff remains valid, while stale 21-stage/non-SIGFM action
  expectations and invalid bootstrap image were replaced by the current
  eight-stage SIGFM profile and valid synthetic image. The focused test is
  PASS normal and ASan/UBSan;
- operator kit offline preflight: PASS; the unapproved build refuses before
  `FpContext` and reports zero USB enumeration/live action;
- shell syntax and `git diff --check`: PASS.

Two production-shaped TLS fixtures were corrected to supply the existing
valid synthetic image record as the FDT bootstrap B0. Their former opaque
four-byte/zero-filled payload was stale once real R2 preprocessing became
mandatory. No production parser or failure rule was weakened.

## Methodology before any new live attempt

1. The actual method change from attempt 01 is the contact boundary: an
   image is no longer handed to `FpImageDevice` at primary B0,
   and the client no longer maps biometric progress to finger release. It
   waits at every stage, including stage 8, for the standard `finger-status`
   transition produced after final `0x34/ACK`; terminal completion is held
   independently until `IRQ0200`.
2. The new hypothesis is that holding contact through the repeated auxiliary
   branch, then releasing only at the release-ready status, permits the
   target-local cycle to reach `IRQ0200`, re-arm safely through stage 7 and
   test the already-scoped stage-8 early terminal.
3. A new failure authorizes no retry. Sanitized expected/control/IRQ metadata
   must drive a protocol-specific review; an equivalent third action is not
   prepared automatically.

## Human Gate

Attempt 01 and its authorization are consumed. The corrected
`operator_kit/d279-57-stage8-early-terminal/` is live-capable but not live
authorized. A new preparation, grant and single action require explicit
approval of the new final full SHA and operation
`D279_57_STAGE8_EARLY_TERMINAL_ENROLLMENT`. The AI does not run `sudo`, access
protected material or execute USB.

```text
OUTCOME=HUMAN_REQUIRED
ADVANCEMENT=LIVE_FAIL_CLOSED_NEW_CONTACT_BOUNDARY_AND_OFFLINE_CORRECTIVE
EXECUTABLE_CLOSURE=PASS_OFFLINE
PRODUCTION_ENROLLMENT_STAGE_POLICY=FIXED_8_CANDIDATE_PENDING_LIVE_PROOF
ATTEMPT02_21_STAGE_REGRESSION_PROFILE_RETAINED=true
DYNAMIC_DUPLICATE_SELECTION_IMPLEMENTED=false
SIGFM_APPEND_FAILURE_ADVANCES_STAGE=false
CURRENT_LIVE_AUTHORIZED=false
ATTEMPT01_GRANT_CONSUMED=true
ATTEMPT01_AUTHENTIC_FILES_IMPORTED=false
AI_REVIEW_REAL_USB_ENUMERATION_COUNT=0
ATTEMPT01_LIVE_EXECUTION_PERFORMED=true
AI_REVIEW_LIVE_EXECUTION_PERFORMED=false
REUSABILITY_PROVEN=false
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
REVIEW_SET=GIT_NATIVE
RESIDUAL_BLOCKER_OR_RISK=AUTHENTIC_ATTEMPT01_FILES_PENDING_SAFE_EXPORT;CORRECTED_CONTACT_BOUNDARY_UNPROVEN_LIVE;APP12509_STAGE8_NO_REARM_TERMINAL_UNPROVEN;POST_CLOSE_REUSABILITY_SEPARATE
NEXT_PRIMARY_BOUNDARY=HUMAN_GATE_NEW_FULL_SHA_ONE_CORRECTED_D279_57_ACTION_NO_RETRY
```
