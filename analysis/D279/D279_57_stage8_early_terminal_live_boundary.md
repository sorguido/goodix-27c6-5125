<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/57 — production stage-8 early-terminal live boundary

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
terminal transitions = 1
primary B0 = 8
inter-stage re-arms = 7
0x32 commands = 8
post-stage-8 re-arm = 0
known persistent-family sends = 0
retry/reopen/second action = 0
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

## Offline verification

- focused `FpImageDevice` stage-8 class/action test: PASS normal and
  ASan/UBSan;
- full-TLS production enrollment test: PASS normal and ASan/UBSan, including
  exact 8/7/8 terminal counts and same-epoch second-action rejection;
- Fedora 44 production-shaped real Rockytkg SIGFM/OpenCV action: PASS with
  eight samples, serialization/identify and standard fprintd ABI checks;
- D279/52 SIGFM print/core suite: PASS normal and ASan/UBSan;
- D279/11 model and D279/13 lifecycle adapter: PASS normal and ASan/UBSan,
  retaining configurable 2/3/21 profiles;
- operator kit offline preflight: PASS; the unapproved build refuses before
  `FpContext` and reports zero USB enumeration/live action;
- shell syntax and `git diff --check`: PASS.

Two production-shaped TLS fixtures were corrected to supply the existing
valid synthetic image record as the FDT bootstrap B0. Their former opaque
four-byte/zero-filled payload was stale once real R2 preprocessing became
mandatory. No production parser or failure rule was weakened.

## Pre-live methodology

1. The technical change from D279/29 is material: production uses R2/SIGFM
   instead of NBIS and terminates after eight complete samples instead of
   re-arming toward 21.
2. The tested hypothesis is that APP12509 accepts host termination after the
   complete stage-8 `IRQ 0x0200`, followed by deactivation/drain/release/close,
   without requiring a ninth `0x32`.
3. Failure authorizes no retry. The evidence must be reviewed and the next
   step must be a protocol-specific replan rather than an equivalent rerun.

## Human Gate

`operator_kit/d279-57-stage8-early-terminal/` is live-capable but not live
authorized. Preparation, grant creation and the single run require explicit
approval of the final full SHA and operation
`D279_57_STAGE8_EARLY_TERMINAL_ENROLLMENT`. The AI does not run `sudo`, access
protected material or execute USB.

```text
OUTCOME=HUMAN_REQUIRED
ADVANCEMENT=PRODUCTION_SIGFM_STAGE8_CANDIDATE_AND_ONE_SHOT_KIT_READY
EXECUTABLE_CLOSURE=PASS_OFFLINE
PRODUCTION_ENROLLMENT_STAGE_POLICY=FIXED_8_CANDIDATE_PENDING_LIVE_PROOF
ATTEMPT02_21_STAGE_REGRESSION_PROFILE_RETAINED=true
DYNAMIC_DUPLICATE_SELECTION_IMPLEMENTED=false
SIGFM_APPEND_FAILURE_ADVANCES_STAGE=false
CURRENT_LIVE_AUTHORIZED=false
REAL_USB_ENUMERATION_COUNT=0
LIVE_EXECUTION_PERFORMED=false
REUSABILITY_PROVEN=false
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
REVIEW_SET=GIT_NATIVE
RESIDUAL_BLOCKER_OR_RISK=APP12509_STAGE8_NO_REARM_TERMINAL_UNPROVEN;POST_CLOSE_REUSABILITY_SEPARATE
NEXT_PRIMARY_BOUNDARY=HUMAN_GATE_FULL_SHA_ONE_D279_57_STAGE8_EARLY_TERMINAL_ENROLLMENT
```
