# D264/03 — OFFLINE pre-live first-image wiring

## Decision

`OUTCOME=PASS_OFFLINE_PRELIVE_WIRING`. This is architectural/executable advancement, not new device evidence. The protected future candidate is wired through an injected production-shaped control flow and the shell surface remains hard-disabled for live use.

## Baseline and scope

The clean `work` branch began exactly at `eca1598801ce57241934d679b3b94784cad5693f`; the required ancestor check passed. No branch operation, real USB access, protected secret read, real marker creation, fprintd mutation, live TLS handshake, or sensor command occurred.

## Implementation

The new D264/03 launcher permits only `--dry-run`. Its entrypoint checks cwd independence, launcher syntax, manifest schema/path uniqueness/worktree hashes, the unapproved full-SHA baseline model and future-marker metadata without reading content. Every other CLI shape fails `HARD_DISABLED_D264_03`.

The future orchestration defines a fresh D265-future intent and marker schema/path, validates full commit SHA and byte identity, consumes authorization once, and explicitly invokes `TerminalBoundary.STOP_AFTER_FIRST_IMAGE`. Dangerous boundaries have no production construction in D264/03 and are exercised solely with injected doubles. Cleanup and external restore are independently attempted. D261 source and capability/marker semantics are unchanged.

## Evidence and limitations

Focused D264/03 tests pass. D264/02, D263 first-image/public runtime and D260 regressions pass. D261 operational tests cannot collect because the pre-existing optional `cryptography` module is unavailable; no package was installed. Hardware-required checks are `NOT_EXECUTED_OFFLINE_BY_POLICY`.

The candidate remains unapproved and unreachable live. Target acceptance of fixed64 zero-tail `0x22`, first B0 behavior, and device-internal post-image state remain unproven/unknown. AI-PM remote review and a distinct baseline approval are the next gate.

## Decision fields

- `ADVANCEMENT=NEW_PRODUCTION_SHAPED_FIRST_IMAGE_PRELIVE_CANDIDATE`
- `EXECUTABLE_CLOSURE=PASS_OFFLINE`
- `FIRST_IMAGE_PRELIVE_OPERATOR_WIRING=IMPLEMENTED_OFFLINE`
- `CURRENT_D261_REAL_BOUNDARY=STOP_AFTER_FDT_ARM_ACK`
- `FUTURE_FIRST_IMAGE_REAL_BOUNDARY=STOP_AFTER_FIRST_IMAGE`
- `D261_MARKER_REUSED=false`
- `NO_REAL_DEVICE_PROOF=PASS` (all six real counters zero)
- `D264_03_READY_FOR_AI_PM_REVIEW=true`
- `D264_03_READY_FOR_BASELINE_APPROVAL=false`
- `READY_FOR_LIVE=false`; `LIVE_AUTHORIZED=false`; `BASELINE_APPROVED=false`
