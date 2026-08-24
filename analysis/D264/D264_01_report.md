# D264/01 — First-image terminal-state evidence audit

**Scope:** OFFLINE evidence/reasoning audit. No USB, sensor, finger, real secret,
service mutation, persistent write, or live execution. Expected branch
`codex-cloud`; observed branch `work`, left unchanged as required. Starting HEAD
matches the expected content baseline `4db9058a3235b82c8777f306a89bab10eb863337`.
That SHA is **not** approved here as a future live baseline.

## Evidence result

The primary APP12509 trace observes a continuing Windows workflow after the
first valid image: `0x34 → IRQ 0x0200 → 0x20 → second image → later re-arm`.
This is **HOST WORKFLOW CONTINUATION**. It does not demonstrate a **DEVICE-SIDE
REQUIREMENT FOR SAFE STOP**. In particular, local target capture and gfusb.dll
analysis identify `0x34` as finger-up arming. No primary evidence identifies it
as cancel, disarm, restore, or a prerequisite to disconnect. `gfOnCancel`
cancels the host request without directly sending A0; A2 and `0x70` do not occur
as post-image restore. Rockytkg independently uses `0x34` as a continuation
primitive, but remains corroboration only.

The device's internal post-image FDT state remains **UNKNOWN**. That unknown is
not promoted to `SAFE`. It is nevertheless bounded by evidence: D256 observes
host cancellation and terminal bus quiescence without a device restore, plus
same-device re-entry and acceptance of a new `0x32` without reset,
re-enumeration, or explicit USB restore. D262 later live-proves the exact
fresh-FDT path, whose cold-start includes the OEM A2 volatile sensor reset. No
post-image NVM write, persistent-write family, or plausible persistent mutation
path is present. Thus persistent/unrecoverable harm is unsupported; volatile
recoverability is an **INFERENCE**, not a direct observation.

## Arm window

The hash-gated primary trace yields: final `0x32` OUT @220, ACK @223, IRQ2 @225,
`0x22` @227, ACK @229, first B0 @231. At one-million pcap ticks per second,
ACK32→IRQ2 is **7108.212 ms**; IRQ2→0x22 is 2.404 ms; IRQ2→ACK22 is 2.952 ms;
IRQ2→first B0 is 50.217 ms. There is one positive observation, so no device TTL
or lifetime distribution can be claimed.

A future model should use one absolute monotonic deadline after validated ACK32,
wait exactly once for IRQ2, never renew on unmatched frames, and fail closed to
host-only cleanup. A **15,000 ms host deadline** covers the only primary positive
trace with bounded margin; it is not a device-lifetime claim. The D263 constant
was 5,000 ms and would reject the observed APP12509 trace before IRQ2. D264
therefore includes the minimal corrective `5000 → 15000` plus a regression
assertion. No other production/runtime behavior changed.

## Historical blockers

* First-`0x36` ultimate seed provenance is superseded as an operational blocker
  for the already live-accepted D262 bounded path; its ultimate source remains
  knowledge only.
* Cancel/disarm/restore, arm lifetime, and post-image internal state are residual
  knowledge gaps, not evidence of intrinsic unsafe stop.
* IRQ2→`0x22` remains a boundary-specific unproven hypothesis.
* `0x22` fixed64 zero-tail acceptance and first image remain live blockers for
  that future boundary. D262 did not reach either.

## Runtime audit

The D263 code preserves arm-only as the default and first-image as explicit
opt-in. The opt-in path performs one IRQ2 wait, one `0x22`, one ACK validation,
then consumes the first B0 on retained TLS. It performs no second secret
handoff, USB reopen, retry, `0x34`, post-image `0x20`, re-arm, A2, `0x70`,
persistent write, or biometric persistence; cleanup is exactly once through the
existing `finally`. Targeted offline tests validate these properties.

External Issue #1 could not be read: web access returned HTTP 401. No issue
content was reconstructed from memory or used as evidence.

## Conclusion and residual risk

There is no evidence that omitting a post-image device command makes host-side
stop intrinsically unsafe. The stronger supported conclusion is bounded and
recoverable-with-cold-start, while retaining `POST_FIRST_IMAGE_DEVICE_INTERNAL_STATE
= UNKNOWN`. Residual risk consists of the unobserved internal state/lifetime,
non-live-proven `0x22` zero-tail, and non-live-proven first image.

```text
OUTCOME=PASS_OFFLINE_EVIDENCE_AUDIT_WITH_MINIMAL_TIMEOUT_CORRECTIVE
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=0x22_ZERO_TAIL_AND_FIRST_IMAGE_NOT_LIVE_PROVEN; POST_IMAGE_INTERNAL_STATE_UNKNOWN
CANONICAL_DOCUMENTATION=UPDATED
FIRST_IMAGE_TERMINAL_RISK=ACCEPTABLY_BOUNDED
D264_01_READY_FOR_OFFLINE_OPERATIONALIZATION_REVIEW=true
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED=false
```
