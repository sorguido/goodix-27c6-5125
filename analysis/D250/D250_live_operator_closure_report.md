<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D250 same-step correction — live operator closure without hardware

## Outcome

D250 is now live-capable but hard-gated. The operator launcher supports exactly:

```text
--offline-dry-run
--i-authorize-one-d250-af-live-attempt
```

The live argument was exercised only through its non-root pre-USB denial gate.
No privileged invocation, USB open, TLS handshake, D4 send, AF attempt, or AF
send occurred. No commit SHA was approved or invented. The operator path is:

```text
D250_LIVE_OPERATOR_PATH=READY_FOR_AI_PM_BASELINE_REVIEW
D250_LIVE_CAPABILITY=HARD_GATED
D250_LIVE_EXECUTION=NOT_PERFORMED
D250_LIVE_BASELINE_APPROVAL=PENDING_AI_PM_REVIEW
```

## Baseline and scope

- Initial branch: `main`.
- Initial HEAD: `d10814150a06b7e5a1fa72c61b5ce23994598e58` (`d250`).
- Initial working tree: clean.
- No commit, push, PR, merge, rebase, amend, reset, stash, or history rewrite was
  performed.
- The canonical D250 offline bundle was not overwritten.

This is a same-step operator-path correction. It does not reopen the D249/D250
protocol decision and does not advance the device boundary.

## Review corrections

The capture audit now derives AF ACK presence, tail length, nonzero-byte count,
nonzero offsets, and cross-occurrence tail identity from the canonical capture.
Its output remains redacted; no raw tail is printed. The audit asserts the
canonical five-occurrence profile and fails if those facts change.

`McuState` now exposes version and flags explicitly. Version `1` is the only
accepted observed AF state version. A different version is classified by the
candidate as `semantic_state_version_mismatch`, fails closed, and remains
terminal at the AF boundary. Candidate telemetry includes:

```text
af_state_version
af_state_flags
af_unknown_flag_bits
```

`ExactlyOneAfMachine` catches `Exception`, not `BaseException`; process-control
exceptions such as `KeyboardInterrupt` and `SystemExit` are not swallowed.

## Live-critical baseline and preflight

`d250_live_critical.py` compares working-tree bytes directly with blobs from a
full 40-hex Git commit, independently of the staging index. The 17-file set
covers the launcher, D245/D246/D250 patch chain, D250 preflight/helper, AF core,
sealed runtime sources, the canonical PE, and behavior-relevant transitive
modules. It deliberately excludes the manual, reports, bundles, status files,
analysis index, and purely offline tests.

The temporary Git fixture proves:

- clean live-critical set: `APPROVED`;
- missing, malformed, and nonexistent SHA: `UNAPPROVED`;
- mutation of each of all 17 live-critical paths: `STALE`;
- comparisons remain independent of the index.

The future live path requires the externally supplied environment variable
`D250_APPROVED_LIVE_BASELINE_SHA`. The launcher first bootstraps the verifier
from the approved commit, checks the full set, runs the D250 preflight, and
checks the baseline again immediately before unseal. No value is embedded in
the repository. At handoff the delta is intentionally uncommitted, so the
initial HEAD returns `STALE`; it is not eligible for approval. This is expected
until the complete live-critical delta is committed and reviewed by the AI PM.

The D250 preflight has D250-only report/marker paths, treats D245/D246 markers
as benign historical state, verifies source seal and baseline before protected
input inspection or target enumeration, and displays actionable pre-USB
failure fields including zero USB/AF counters. It does not handle passwords.

## Patch lifecycle and maximum runtime boundary

The future authorized branch backs up both sealed runtime sources byte-exact,
installs traps, applies D245→D246→D250 in order, verifies the D250 schema,
namespace, AF version gate, and telemetry, invokes the production entrypoint
once, then restores and compares both sources byte-exact. There is no retry.

The maximum path remains:

```text
A8 -> E4 -> pre-D1 -> D1 -> TLS -> D4 once -> ACK d4/01
-> AF once -> one direct AE -> STOP_AFTER_AF
```

Second D4/AF, FDT `32`, SetMode `20`, D2, finger/image, application data,
E0/A4/F0/F4, IAP, ClearApp, provisioning, reset/reopen, and retry recovery stay
unreachable in the tested candidate.

## Method review before any future live authorization

1. The method changes from the successful D246 boundary by testing the next
   command, exactly-one AF, rather than repeating D4.
2. The new hypothesis is that the declared 13-byte AF request submitted in a
   deterministic zero-filled 64-byte buffer is accepted as equivalent and
   yields one semantic version-1 AE state response.
3. If a future authorized attempt fails at this point, it stops without retry;
   the new evidence must be analyzed before a materially different method is
   proposed.

## Offline verification

- `bash -n operator_kit/d250-live-af-once.sh` — PASS.
- D250 targeted suite — 11/11 PASS.
- D249 regression — 13/13 PASS.
- D246 regression — 4/4 PASS.
- D245 regression — 7/7 PASS.
- full suite — 159/159 PASS.
- capture audit reproduction/redaction — PASS.
- patch apply D245→D246→D250 and reverse — PASS byte-exact.
- dry-run from repository root and external cwd — PASS.
- synthetic happy D4→AF→AE, timeout, ambiguous completion, unexpected ACK,
  malformed AE, semantic version mismatch, duplicate/coalesced AE, second AF,
  and post-AF command fence — PASS.
- cleanup/restore/secret zeroization — exactly once in the synthetic runtime;
  sealed source restore — exactly once and byte-exact in operator closure.

## Residual risk

`D250_AF_ZERO_TAIL_DEVICE_EQUIVALENCE=NOT_LIVE_PROVEN` remains unchanged. The
APP12509 AF receiver implementation remains unavailable. A reviewed full commit
SHA and separate explicit user authorization are still required before any
hardware execution.

## Closure fields

```text
OUTCOME=READY
ADVANCEMENT=NONE_SAME_STEP_OPERATOR_CLOSURE_NO_NEW_DEVICE_BOUNDARY
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=AF_ZERO_TAIL_DEVICE_EQUIVALENCE_NOT_LIVE_PROVEN;APP12509_AF_RECEIVER_UNKNOWN;LIVE_BASELINE_PENDING_AI_PM_REVIEW;EXPLICIT_USER_AUTHORIZATION_REQUIRED
CANONICAL_DOCUMENTATION=UPDATED_MANUAL_D250_STATE_CURRENT_BOUNDARY_HARD_WALL_IMPLEMENTATION
BUNDLE=analysis/D250/D250_live_operator_closure_bundle.zip;SHA256_IN_EXTERNAL_SIDECAR

INITIAL_HEAD=d10814150a06b7e5a1fa72c61b5ce23994598e58
FINAL_WORKTREE_STATUS=MODIFIED_AND_UNTRACKED_D250_SAME_STEP_DELTA;NO_UNRELATED_CHANGES_OBSERVED
D250_LIVE_OPERATOR_PATH=READY_FOR_AI_PM_BASELINE_REVIEW
D250_LIVE_CAPABILITY=HARD_GATED
D250_LIVE_EXECUTION=NOT_PERFORMED
D250_LIVE_BASELINE_APPROVAL=PENDING_AI_PM_REVIEW
D250_LIVE_CRITICAL_SET_STATUS=FIXTURE_PASS_ALL_17_PATHS;CURRENT_HEAD_STALE_UNCOMMITTED_DELTA_NOT_ELIGIBLE
D250_AF_ZERO_TAIL_DEVICE_EQUIVALENCE=NOT_LIVE_PROVEN
USB_OPEN_COUNT=0
TLS_HANDSHAKE_COUNT=0
D4_SEND_COUNT=0
AF_ATTEMPT_COUNT=0
AF_SEND_COUNT=0
RETRY_COUNT=0
PERSISTENT_WRITE_FAMILY_COUNT=0
```
