# D274/03 — Offline Finalizer Corrective Report

- Executor: Tencent Hy3 Free via Kilo
- Reasoning: HIGH
- Mode: OFFLINE ONLY (no USB, no new live run)
- Date (local): 2026-08-26
- Git root: `/home/guido/Repository/goodix-27c6-5125_private`
- Branch: `main`
- HEAD: `fb8614c979d03d66ba648d4c43fcabff683eff4e`
- Canonical raw: `captures/D274_03/D27403_20260826T201852Z/raw/wire.pcapng`
- Canonical raw SHA-256 (before = after): `5f11d06763d34531c72283a189a47d9bcd7c666a5fa3c043ec1371eddf107998`

## 1. Summary

The Windows Hello live capture for D274/03 was already executed in a separately
authorized live run. The canonical raw is byte-identical and was never mutated.
The previously reported failure was a **postprocessor/finalizer semantic bug**,
not missing live evidence.

The original finalizer promoted *any* single event after the second boundary —
`IRQ 0x0002`, `COMMAND 0x22`, or `FINGERPRINT_B0` — to `THIRD_CYCLE_OBSERVED`.
The real post-boundary traffic (0x34 / 0x36 / IRQ 0x0100 / 0x20 / isolated
`FINGERPRINT_B0` at frame 265) is ordinary OEM teardown, not a third
acquisition lifecycle. Because the false positive flipped `boundary_status`
away from `OBSERVED_COMPLETE`, `verify_finalized_capture()` then wrongly raised
`CAPTURE_FINALIZATION_LOST_TERMINAL_EVIDENCE`.

## 2. Corrective changes

File: `analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/d274_03_postprocess_second_cycle.py`

- Added `_third_cycle_lifecycle(events)` — a bounded, auditable ordered matcher
  requiring the exact lifecycle `IRQ 0x0002 → COMMAND 0x22 (body 01 00) →
  ACK 0x22 (status 0x01) → FINGERPRINT_B0`. Non-lifecycle events are skipped;
  a contradictory lifecycle-bearing event (wrong 0x22 body, wrong 0x22 ACK
  status, or out-of-order `FINGERPRINT_B0`) resets partial progress so
  ambiguity can never become PASS. No capture-specific frame number is
  hard-coded.
- `analyze_frames()` derives `third_cycle_observed` only from
  `_third_cycle_lifecycle()` (the exact ordered lifecycle above; non-lifecycle
  events skipped, a contradictory lifecycle-bearing event resetting partial
  progress so ambiguity can never become PASS).

  INTERMEDIATE v1 (REJECTED): v1 set `complete = index == len(SEQUENCE)`,
  decoupling `complete` from `failure_class`, so a genuine third cycle did **not**
  flip `boundary_status` away from `OBSERVED_COMPLETE` and was wrongly reported as
  a successful observer terminal signal. This is the rejected intermediate
  behavior and is **not** the current semantics.

  FINAL v2 (AUTHORITATIVE): `complete = index == len(SEQUENCE) and not third_cycle`.
  A genuine third lifecycle therefore yields
  `third_cycle_observed = true` → `failure_class = THIRD_CYCLE_OBSERVED` →
  `boundary_status = NOT_OBSERVED_COMPLETE`, and the growing observer returns
  `status = FAIL_CLOSED`.

- `verify_finalized_capture()` explicitly preserves `THIRD_CYCLE_OBSERVED` when the
  observer signal is taken from the pre-third state and the finalized raw
  additionally contains the later genuine third lifecycle (with a recoverable
  terminal frame), and does **not** remap it to
  `CAPTURE_FINALIZATION_LOST_TERMINAL_EVIDENCE`, which stays reserved for real
  finalization loss (truncated/unreadable raw).

The rearm `0x32 → ACK 0x32/0x01` is treated as corroborating context only, not
mandatory (the code does not require it, and no comment claims it is required).

## 2b. Corrective v2 — growing observer fail-closed regression

An AI-PM review of the v1 uncommitted working tree isolated two further
defects, corrected offline without any new live activity.

### 2b.1 Growing observer fail-closed

After v1 decoupled `boundary_status` from `failure_class`, a genuine third
lifecycle could still be reported as a successful observer terminal signal.
`analyze_frames()` set `complete = index == len(SEQUENCE)` regardless of the
`THIRD_CYCLE_OBSERVED` failure, so `boundary_status` was `OBSERVED_COMPLETE`
and `inspect_growing_capture()` returned `SECOND_FINGERPRINT_B0_OBSERVED`
with `failure_class = null`, weakening fail-closed semantics.

Fix: `complete = index == len(SEQUENCE) and not third_cycle`. A genuine third
lifecycle is now a protocol/post-boundary failure, so the snapshot's
`boundary_status` is no longer `OBSERVED_COMPLETE` and `inspect_growing_capture()`
returns `status = FAIL_CLOSED`, `failure_class = THIRD_CYCLE_OBSERVED`. The
authority in `verify_finalized_capture()` is preserved: when the finalized raw
contains a genuine third lifecycle it keeps the meaningful `THIRD_CYCLE_OBSERVED`
root cause and does **not** remap it to
`CAPTURE_FINALIZATION_LOST_TERMINAL_EVIDENCE` (reserved for real
truncation/unreadable raw).

### 2b.2 Surgical manual repair

The v1 manual edit had wrongly promoted historical D274/01 / pre-live / D274/02
sections from their HEAD historical values (`NOT_EXECUTED`, capture count 0) to
the current observed values, and had mixed the live-authorization template
counters (`LIVE_PATH_EXECUTED=false`, `LIVE_EXECUTION=NOT_PERFORMED`, zero
`REAL_*` counters) with the observed `D274_SECOND_CYCLE_TARGET_OBSERVATION=OBSERVED_COMPLETE`
and a real capture.

Corrective v2 reverted the manual to HEAD and re-applied **only** the
high/current canonical state to the now-observed D274/03 result:

- top canonical state block and the two current D274/03 blocks updated to
  `OBSERVED_COMPLETE` / `REAL_CAPTURE_COUNT=1` / `D274_03_REAL_CAPTURE_CAPABILITY=1`;
- historical D274/01 / pre-live / D274/02 sections restored exactly to HEAD
  (`NOT_EXECUTED`, capture count 0);
- baseline live-authorization template state is now explicitly distinguished
  from the observed canonical capture (comment + separate fact lines);
- obsolete `NEXT_PRIMARY_BOUNDARY` pointing to pre-live freeze/authorization was
  replaced with the current post-observation next boundary;
- verified current facts recorded (terminal frame 249, `WIRE_DRIVEN`,
  `automatic_retry_count = 0`, canonical raw SHA-256, third cycle absent,
  offline corrective, no new live run, `timeout = UNKNOWN` preserved);
- the dedicated D274/03 corrective subsection remains and agrees with both the
  current and the historical sections.

## 3. Real capture reprocessing result

Reprocessed offline via `verify_finalized_capture()` with the canonical expected
SHA-256 and observer signal. Wrote
`captures/D274_03/D27403_20260826T201852Z/sanitized/D274_03_second_cycle_evidence.json`.

- `boundary_status = OBSERVED_COMPLETE`
- `stop_reason = SECOND_FINGERPRINT_B0`
- `failure_class = null`
- `third_cycle_observed = false`
- `second_b0_frame.frame = 249`
- `capture_sha256 = 5f11d06763d34531c72283a189a47d9bcd7c666a5fa3c043ec1371eddf107998`

The sanitized evidence contains no raw payload, biometric plaintext/hash, PIN,
PSK, secret, key material, raster, image, or pixel content (validated by
`D274_03_evidence_schema.json` forbidden-field and additionalProperties checks).

## 4. Regression tests

Updated/extended `analysis/D274/test_d274_03_second_cycle_operator_kit.py`:

- `test_10` rewritten to a genuine ordered third cycle (still `THIRD_CYCLE_OBSERVED`, `third_cycle_observed = true`).
- `test_10b` real-capture regression (canonical raw → required real result).
- `test_10c` isolated post-boundary B0 → not a third cycle.
- `test_10d` realistic OEM post-boundary traffic → not a third cycle.
- `test_10e` partial fragments (lone IRQ / lone 0x22 / lone B0) → not a third cycle.
- `test_10f` genuine third cycle with interposed irrelevant event → still detected.
- `test_10g` authoritative finalizer preserves `THIRD_CYCLE_OBSERVED` (not remapped): builds a valid capture ending at the authorized second B0, takes the observer signal from that pre-third state, then finalizes a version that additionally contains a genuine third lifecycle and requires `THIRD_CYCLE_OBSERVED`.
- `test_10h` growing observer containing a complete genuine third lifecycle returns `status = FAIL_CLOSED`, `failure_class = THIRD_CYCLE_OBSERVED`.
- `test_31` (H) true finalization loss still `CAPTURE_FINALIZATION_LOST_TERMINAL_EVIDENCE`.

Full existing D274/03 suite also executed (see below).

## 5. Closure fields

```text
OUTCOME=READY
ADVANCEMENT=NONE_HARDWARE (offline documentation/packaging corrective v3 on preserved raw; Python/logic unchanged; real live boundary already observed in prior authorized run)
EXECUTABLE_CLOSURE=PASS_LINUX_OFFLINE_ONLY
RESIDUAL_BLOCKER_OR_RISK=none
CANONICAL_DOCUMENTATION=v3 surgical: removed stale pre-live statements from top/current state (D263 framed historical; D274/03 second cycle stated observed); scoped operator-kit direct-USB counters away from observed capture; historical D274/01+pre-live+D274/02 preserved; report v1 semantics relabeled rejected/intermediate, final v2 authoritative
MANUAL_STALE_PRELIVE_STATEMENTS_REMOVED=PASS
MANUAL_CURRENT_STATE_COHERENT=PASS
MANUAL_HISTORICAL_STATE_NOT_CORRUPTED=PASS
REPORT_FINAL_V2_SEMANTICS_COHERENT=PASS
CODE_BYTE_IDENTITY=PASS
TEST_BYTE_IDENTITY=PASS
SANITIZED_EVIDENCE_BYTE_IDENTITY=PASS
RAW_BYTE_IDENTITY=PASS
FULL_D274_TEST_SUITE=PASS (56 tests)
STEP_LOCAL_ZIP_AND_SIDECAR=PASS
BUNDLE=analysis/D274/D274_03_offline_finalizer_corrective_bundle.zip
```
