# D263 — Final report (canonical, single coherent document)

**Outcome:** `OFFLINE_IMPLEMENTATION_READY_FOR_AI_PM_REVIEW` (non live-ready).
**Reasoning:** HIGH · **Offline:** yes · **Live execution:** not performed.
**Milestone:** D263 (unico) · **Branch:**
`session/agent_16ceb075-09cc-4bef-9575-02c7f6528892`.

This document is the single canonical final report for D263. It supersedes the
earlier substep-by-substep closure; the corrective history is summarized
below for provenance but the technical state stated here is final and
non-contradictory. No D264 is created.

## What D263 proved offline

- **D263/01** — post-arm order, target-specific, from primary APP12509 evidence
  (`rilevamento.pcapng`, hash-gated SHA-256
  `50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`):
  `0x32(arm,ACK) → IRQ0x0002 → 0x22[01 00](ACK) → first image (TLS B0 17 03 03,
  7726)`. Taxonomy `0x22 = PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY`.
- **D263/02** — retained-TLS + first-image pipeline audit: one retained TLS
  session, one canonical codec (`decode_image_record` 7684B → 80×64, CRC
  fail-closed). Gap: the coordinator stopped at `arm()`; post-arm not wired.
- **D263/03** — terminal-stop candidate after the first image (host/TLS/USB
  cleanup → STOP, without `0x34`/`0x20`/re-arm/A2/`0x70`); Phase-1 gate
  `READY_FOR_PHASE2_OFFLINE_RUNTIME_INTEGRATION=true`.
- **D263/04** — Phase-2 contract + patch plan (design-only), live-critical
  prechange hashes recorded.
- **D263/05** — support primitives: `0x22` allowlist in `runtime_transport.py`;
  `post_irq2_image_command()` one-shot + `cancel_pending_receive` accepting
  `FIRST_IMAGE_RECEIVED` in `fdt_lifecycle.py`. 12 tests PASS.
- **D263/06** — runtime integration: `_run_first_image_terminal()` in the
  production coordinator, reusing the canonical codec + retained TLS. 8 tests PASS.
- **D263/07** — executable closure + regression audit; micro-corrective (raster
  shape derived from the decode, not hardcoded). 20/20 D263 tests PASS; full
  discovery 248 (38 environmental, 0 D263 regressions).
- **D263/08** — final consolidation, canonical closure, single bundle.
- **D263/09 (corrective)** — closed two real defects and normalized the
  taxonomy/ACK; see "Corrective history" below. This polish pass (final
  canonical closure) reconciles remaining stale wording without changing the
  approved technical implementation or the production boundary.

## Final coherent `0x22` model

```text
0x22                       = PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY
0x22_LOGICAL_OFFLINE_POLICY= ABSTRACT_LOGICAL_ONLY
0x22_OPERATIONAL_LINUX_CANDIDATE = FIXED64_ZERO_TAIL
0x22_OPERATIONAL_ZERO_TAIL_CANDIDATE = EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE
0x22_LIVE_ACCEPTANCE       = NOT_LIVE_PROVEN
0x22_ACK_POLICY            = EXACTLY_ONE_REQUIRED_AND_VALIDATED
```

The primary capture **proves the OEM fixed-64 submission** (logical A0 = 10,
physical OUT = 64, out-of-frame residue/staging observed at offsets 40–45 =
`cb f2 e2 be fb 7f`) and **supports** the Linux deterministic candidate
`FIXED64_ZERO_TAIL`. It does **not** prove live device acceptance of the Linux
zero-tail on `0x22`. `D263_01` `phase2_model_confirmed` is therefore `false`.

## Terminal boundary (final)

- `TerminalBoundary` enum: `STOP_AFTER_FDT_ARM_ACK` (default, preserves D260/D262)
  and `STOP_AFTER_FIRST_IMAGE` (opt-in D263 candidate).
- Default `run()` stops after the final FDT arm; no consumer is promoted to the
  D263 boundary implicitly.
- `FIRST_IMAGE_TERMINAL_STOP = EVIDENCE_SUPPORTED_BUT_DEVICE_INTERNAL_STATE_UNKNOWN`:
  host cleanup (cancel pending receive, TLS close, USB release, restore fprintd,
  zero extra Goodix command) is supported and implemented offline; device
  internal state post-first-image is UNKNOWN; device stop is NOT live-proven.

## Invariants preserved

One USB/TLS session+handshake; zero second secret/USB reopen/retry/re-arm;
exactly one `0x22`; no `0x34`/`0x20`-post/`A2`/`0x70`/persistent-write;
first-image bytes not persisted (plaintext zeroed after decode); fail-closed;
cleanup on every path.

## Corrective history (D263/09, for provenance only)

- **Defect A (CLOSED):** `run()` unconditionally ran the first-image terminal
  after arm, promoting every consumer to the D263 boundary. Fixed by the explicit
  `TerminalBoundary` enum with arm-only default; boundary-dependent trace check.
- **Defect B (CLOSED):** `0x22` always used `fdt_a0_policy`. Fixed: `0x22` selects
  `operational_fdt_a0_policy` (`FIXED64_ZERO_TAIL`) when
  `operational_physical_policy=true`, else `fdt_a0_policy` (`ABSTRACT_LOGICAL_ONLY`).
- **Normalization:** `0x22 = PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY`;
  `ABSTRACT_LOGICAL_ONLY` (logical) vs `FIXED64_ZERO_TAIL`
  (`EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE`, not live-accepted); ACK `0x22`
  `= EXACTLY_ONE_REQUIRED_AND_VALIDATED`.
- **Tests:** 7 environment-independent public-`run()` tests added (arm-only x3,
  first-image success x1, first-image failure x1, `0x22` policy x2). Total D263
  tests = 27 PASS.

## File live-critical changed (vs `D263_04`)

- `core/persistent_runtime.py` (`8e448caa…` → `c266ef8a…` → `1a731cda…` → `36963ce7…`)
- `core/runtime_transport.py` (`cbbb0b68…` → `2930aa57…`)
- `core/fdt_lifecycle.py` (`2edbec9e…` → `2aac7422…`)

All other backend/guardrail/launcher live-critical files: byte-identical. The
final canonical-polish pass changed **no production boundary code**; it
reconciled artifacts, this report, the manual, and hardened the synthetic
secret-handoff test double.

## Residual blocker / risk

Causality IRQ2→0x22 not proven; `0x22` not live-proven; device-side
restore/cancel/arm-lifetime open (D252/D253/D255); `0x22` operational zero-tail
candidate `EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE`, not live-accepted.

## Artifacts (`analysis/D263/`)

`D263_01_*` … `D263_07_*`, `D263_corrective_closure.json`,
`D263_final_decision.json`, `D263_final_report.md`, `D263_workflow_state.json`,
`d263_01_0x22_evidence_audit.py`, `tests/test_d263_phase2_public_run.py`, and the
bundle `D263_post_arm_first_image_offline_bundle.zip` (+ `.sha256`).

## Bundle

Single, step-local, non-cumulative. Includes D263 artifacts (Phase1+Phase2+
Corrective+Polish), the updated canonical manual, and D263-modified
source/test files. Excludes raw capture / secret / biometric / temp / unrelated.
Manifest with path+SHA-256. Verified: CRC OK, no path traversal/symlink, no
forbidden-material.

## Next review required before any live

Explicit AI-PM-approved live baseline SHA; separate live authorization;
verification of the live-critical set against this bundle; targeted OEM evidence
to close D252/D253/D255. `0x22` remains `OBSERVED_ONLY` until a dedicated live
run accepts it.
