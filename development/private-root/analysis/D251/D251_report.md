<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D251 — AF state semantics post-mortem and corrected one-shot candidate

## Outcome

D250 returned one structurally valid direct A0/AE after the single AF zero-tail
submission. The recorded `af_response_count=0` was caused by incrementing the
counter after the rejected `byte0 == 1` check; it is not evidence of no
response. The byte0 value itself was not persisted and is
`LOST_BY_OBSERVABILITY_GAP`.

The static audit does not support treating byte0 as a version. D251 therefore
reclassifies it as opaque, fixes telemetry, and prepares a wire-identical,
hard-gated one-shot candidate. No USB, TLS, D4 or AF live action was performed.

## Initial state and preserved evidence

- Branch: `main`.
- Initial HEAD / approved D250 live baseline:
  `44b22f21178c0083d4628ca9bbdb4ee895df40bd`.
- Initial worktree contained only the user-owned untracked
  `analysis/D250/D250_operator_live_stdout.json` and
  `analysis/D250/D250_preflight_report.json`; neither was modified.
- Both `/var/lib/goodix-5125-poc/d250-results/d250-live-result.json` and
  `d250-live-pre-restore.json` were inaccessible without privilege. No `sudo`
  was used.
- No clearly run-related temporary file containing byte0 remained under
  `/tmp`.

The copied operator JSON records TLS complete, D4 send `1`, ACK `d4/01`, AF
attempt/send `1/1`, validator failure `semantic_state_version_mismatch`, cleanup
`1`, successful secret zeroization and fprintd/signal restore, and zero retry,
persistent-write family and application data.

## Structural diagnosis

In D250, `parse_af_response()` checked outer A0 framing, payload length and
checksum, control `0xAE`, and body length 16 before raising
`UnexpectedStateVersion`. The observed failure therefore proves that the live
target returned a structurally valid direct A0/AE. Since the physical AF OUT
was the reviewed 64-byte zero-tail submission and completed, the bounded
classification is:

```text
D250_AF_ZERO_TAIL_DEVICE_ACCEPTANCE=LIVE_PROVEN
D250_AF_ZERO_TAIL_STRUCTURAL_AE_RESPONSE=LIVE_PROVEN
D250_AF_ZERO_TAIL_OEM_BYTEWISE_EQUIVALENCE=NOT_PROVEN
```

## Byte0 audit

Primary local `gfusb.dll` disassembly identifies `GetMcuState` at
`0x180059f98` and three direct call sites at `0x1800146ca`, `0x18001e3af` and
`0x18001f23e`. Across those sites, byte0 is neither compared with `1` nor used
for a branch. Observed decisions use byte1 bit0 (POV), bit1 (TLS connected) and
bit3 (locked); one call site uses only query success. The five OEM capture
occurrences establish only the observation `byte0=1`.

After reading `Rockytkg/PROVENANCE.md`, the preserved snapshot at commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b` was checked. Rocky logs byte0 but
uses byte1 for POV/TLS/locked decisions and does not enforce byte0 `== 1`.
This is corroboration, not target-specific proof.

Conclusion: the D250 control was a promotion of an observation to an
unproven invariant.

```text
SAFETY_BEHAVIOR=CORRECT_FAIL_CLOSED
SEMANTIC_MODEL=OVERCONSTRAINED
OBSERVABILITY=INSUFFICIENT_BECAUSE_BYTE0_NOT_PERSISTED
AF_STATE_BYTE0_SEMANTIC_CLASS=OPAQUE_NO_POSITIVE_VERSION_SEMANTICS_PROVEN
```

The audit facts are also captured in
`analysis/D251/D251_af_state_semantics_audit.json`.

## D251 implementation

The canonical parser now returns `McuState.byte0` for any structurally valid
16-byte AE body. The D251 continuation patch:

- removes the D250 semantic-version exception path;
- increments `af_response_count` immediately after structural validation;
- retains `af_state_byte0`, flags, unknown bits, POV, TLS and locked fields;
- distinguishes `no_response`, `malformed_response`, `unexpected_ack`,
  `valid_ae_with_unusual_state_fields`, and `valid_ae_accepted`;
- keeps every successful or failed AF outcome terminal at `STOP_AFTER_AF`.

The wire path remains D245→D246→D250 followed by the D251 validator-only patch.
AF serializer, 64-byte zero-tail submission, 20 ms pacing, 500 ms timeout,
endpoints, D4 policy and one-IN budget are unchanged. Second AF, FDT `32`,
SetMode `20`, D2, finger/image and automatic recovery remain unreachable.

The D251 launcher has an independent marker and report namespace:

```text
/var/lib/goodix-5125-poc/d251-operator-invocation.marker
/var/lib/goodix-5125-poc/d251-results
```

It treats the D250 marker as historical benign state, never deletes or reuses
it, requires an externally supplied approved full commit SHA, and preserves
authorization, root/non-root operator identity, exact-target, source
seal/reseal, single-shot and zero-retry gates.

## Required pre-live method review

1. The real method change is limited to removing the unproven byte0 invariant
   and persisting/counting the already structurally valid AE.
2. The new hypothesis is that the D250 AE was protocol-valid and byte0 is an
   opaque state byte rather than a required version discriminator.
3. If a separately authorized D251 attempt fails at the same boundary, no
   equivalent probe or retry follows; the retained telemetry must drive a new
   receiver/protocol audit before another live proposal.

## Offline verification

- D251 targeted/operator suite: PASS.
- D249, D250 and D246 regressions: PASS.
- Full unittest discovery: PASS, 170 tests.
- Byte0 `1`, `0` and `2`: PASS; all retained, response count `1`, terminal
  `STOP_AFTER_AF`.
- Malformed length/control/checksum, unexpected AF ACK, timeout, ambiguous OUT,
  duplicate/coalesced AE, second AF and post-AF command fence: PASS.
- Patch chain D245→D246→D250→D251 apply/reverse: PASS byte-exact.
- Live-critical stale detection: PASS for all 18 paths.
- Launcher `bash -n`: PASS.
- Dry-run from repository root and external cwd: PASS.
- Real USB/TLS/D4/AF counters: all zero.

## Closure

```text
OUTCOME=READY
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_AND_SEMANTIC_MODEL_CORRECTED_OFFLINE
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=D250_BYTE0_VALUE_LOST;APP12509_RECEIVER_ABSENT;D251_BASELINE_PENDING_AI_PM_REVIEW;EXPLICIT_USER_AUTHORIZATION_REQUIRED
CANONICAL_DOCUMENTATION=UPDATED_MANUAL_STATE_D250_D251_CURRENT_BOUNDARY_HARD_WALL_IMPLEMENTATION
BUNDLE=analysis/D251/D251_af_state_semantics_and_operator_closure_bundle.zip;SHA256_IN_EXTERNAL_SIDECAR

INITIAL_HEAD=44b22f21178c0083d4628ca9bbdb4ee895df40bd
D250_LIVE_RESULT=D250_ABORTED_AF
D250_AF_SEND_COUNT=1
D250_AF_STRUCTURAL_AE_PROVEN=true
D250_AF_ZERO_TAIL_DEVICE_ACCEPTANCE=LIVE_PROVEN
D250_AF_LIVE_STATE_BYTE0_VALUE=LOST_BY_OBSERVABILITY_GAP
D250_AF_RESPONSE_COUNTER_DIAGNOSIS=INCREMENTED_TOO_LATE_AFTER_SEMANTIC_CHECK
AF_STATE_BYTE0_SEMANTIC_CLASS=OPAQUE_NO_POSITIVE_VERSION_SEMANTICS_PROVEN
D251_AF_LIVE_BOUNDARY=READY_FOR_SEPARATE_AI_PM_REVIEW
D251_LIVE_EXECUTION=NOT_PERFORMED
USB_OPEN_COUNT=0
TLS_HANDSHAKE_COUNT=0
D4_SEND_COUNT=0
AF_SEND_COUNT=0
RETRY_COUNT=0
PERSISTENT_WRITE_FAMILY_COUNT=0
```
