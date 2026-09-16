# D262: fresh-FDT arm execution-readiness review (offline)

## Summary

D262 performs a final, offline execution-readiness review of the bounded
fresh-FDT arm path on the already-approved D261 candidate. **No live-critical
file was modified** (`D262_LIVE_CRITICAL_MODIFICATION_COUNT=0`) and no hardware
was accessed. The D261 operator kit is reused unchanged in `--dry-run` mode
from a realistic working directory (repo root).

## Evidence

| Criterion | Evidence file | Result |
|---|---|---|
| Dry-run from operator kit | `D262_operator_dry_run_evidence.json` | PASS |
| Live-critical baseline match (17/17) | `D262_baseline_integrity_evidence.json` | PASS |
| Full offline test suite | `D262_test_results.json` | 238 PASS, 0 fail |
| Import safety (fresh subprocess) | `D262_import_safety_evidence.json` | PASS (16 modules, 0 side-effects) |
| Execution boundary (happy path) | `D262_final_risk_boundary.json` | STOP_AFTER_FDT_ARM_ACK |
| Negative scenario containment | `D262_final_risk_boundary.json` | 6/6 fail-closed, 0 retry |

## Dry-run counters (real side-effects)

| Counter | Value |
|---|---|
| REAL_USB_OPEN_COUNT | 0 |
| REAL_SECRET_READ_COUNT | 0 |
| REAL_COMMAND_SEND_COUNT | 0 |
| REAL_MARKER_CREATE_COUNT | 0 |
| FPRINTD_MUTATION_COUNT | 0 |

`LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG=false`. Default invocation returns
exit code 2 (`HARD_DISABLED_DEFAULT`). The live path is gated behind the exact
explicit flag `--i-authorize-one-d261-fdt-arm-live-attempt` plus an approved
full-commit SHA in `D261_APPROVED_LIVE_BASELINE_SHA`; neither was set.

## Baseline integrity

`D261_APPROVED_LIVE_BASELINE_SHA=e9073a171697bd68dd2debabb851f23d007bf718` resolves
to itself as a git commit. All 17 paths in `CANONICAL_LIVE_CRITICAL_PATHS`
(defined in `tools/d261_live_fdt_arm_once.py:77`) are byte-identical between
the working tree and the approved commit blobs. The `verify_approved_git_baseline`
verifier ran without exception.

## Execution boundary

The offline rehearsal (fake libusb/OS/secret boundary) reaches exactly
`STOP_AFTER_FDT_ARM_ACK` on the happy path. The exact FDT device-command trace
is:

```text
0x36 stage0 → ACK → IRQ 0x0100 → 0x50 → ACK + response
→ 0x36 stage1 → ACK → IRQ 0x0100 → 0x82 → ACK + response
→ 0x20 → ACK → B0 baseline on SAME retained TLS session
→ authenticate/decrypt/consume B0
→ 0x36 stage2 → ACK → IRQ 0x0100 → 0x32 → ACK
→ STOP_AFTER_FDT_ARM_ACK
```

Final trace: `0x36,0x50,0x36,0x82,0x20,0x36,0x32` (7 commands, `FdtLifecycle`
`device_command_trace` at `core/fdt_lifecycle.py:270`).

## Risk boundary (offline)

| Counter | Happy path | All negatives |
|---|---|---|
| retry_count | 0 | 0 (all 6) |
| af_retry_count | 0 | 0 (all 6) |
| persistent_write_family_count | 0 | 0 (all 6) |
| A2/0x70 recovery | 0 | 0 (all 6) |
| tls_close_count | 1 | happy: 0, e4_mismatch: 0, otp_cache_mismatch: 0, extra_frame: 1 |
| queued frames at end | 0 | 0 except `unexpected_extra_frame_after_final_0x32`=1 (expected; extra frame injected in that failure case) |
| secret_boundary_zeroized | true | true (all 6) |
| usb_close_count | 1 | 1 (all 6) |

Negative scenarios (6): `wrong_vid_pid`, `identity_changes_after_open`,
`interface_claim_failure`, `live_otp_cache_mismatch`, `e4_mismatch`,
`unexpected_extra_frame_after_final_0x32`. All fail-closed before or at the
`0x32` ACK; none reach beyond. No automatic retry or recovery command is
invoked (`core/fdt_lifecycle.py:116-121` enforces allowlist;
`core/fdt_lifecycle.py:202-214` forbids implicit arm retry).

## Physical and post-FDT reachability

| Item | Reachable |
|---|---|
| `0x22` (post-IRQ2 image command) | No — lifecycle only emits `0x32` at `FDT_ARMED_WAIT`; `0x22` requires explicit `post_irq2_image_command()` which is never called (`core/fdt_lifecycle.py:222`) |
| Post-finger image (enrollment/matching) | No — FDT arm terminates at `STOP_AFTER_FDT_ARM_ACK` before `first_image_received` (`core/fdt_lifecycle.py:230`); no finger interaction required or allowed |
| A2 / 0x70 recovery after FDT failure | Forbidden — not in `SAFE_DEVICE_COMMANDS` (`core/fdt_lifecycle.py:57`); `fail_closed` prevents any retry path |

Physical USB OUT length is fixed at 64 bytes with zero-fill tail policy
(`operational_fdt_a0_policy` in `core/runtime_transport.py`; `core/persistent_runtime.py:168`
validates D4 chunk = 64 bytes with zero tail; `_FdtTransportAdapter` enforces
per-command timeout policy).

## Residual risk

The FDT A0 zero-tail device acceptance remains `UNPROVEN_LIVE_HYPOTHESIS` for
`0x36/0x50/0x82/0x20`. The `0x32` ACK is proven (primary target `PRIMARY_ZERO_TAIL_PROVEN`).
This is the same residual risk recorded in D261 (see `PRIMARY_FUTURE_LIVE_RISK`).

## Decision

```text
ADVANCEMENT = LIVE_EXECUTION_READINESS_REVIEW
EXECUTABLE_CLOSURE = PASS
OUTCOME = READY
RESIDUAL_BLOCKER_OR_RISK = FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND
READY_FOR_D262_OPERATOR_EXECUTION_REVIEW = true
READY_FOR_D262_OPERATOR_EXECUTION = false
READY_FOR_FDT_LIVE = false
LIVE_EXECUTION = NOT_PERFORMED
```

D262 confirms the D261 candidate is execution-ready: the live-critical set is
byte-identical to the approved baseline, the operator kit dry-runs cleanly with
zero real side-effects from a realistic cwd, all 238 offline tests pass, and the
bounded runtime terminates at `STOP_AFTER_FDT_ARM_ACK` with the exact command
trace `0x36,0x50,0x36,0x82,0x20,0x36,0x32`, zero retry, zero persistent writes,
and zero recovery/A2/0x70 injection. No new live path or launcher was created.

The next action is exclusively the AI-PM bundle review and the operator's
explicit single-shot hardware authorization — **not** performed in this step.

## References

- `tools/d261_live_fdt_arm_once.py` — entrypoint, `dry_run()`, `verify_approved_git_baseline()`
- `core/fdt_lifecycle.py` — `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE`, `FdtLifecycle`, `STOP_AFTER_FDT_ARM_ACK`
- `core/persistent_runtime.py` — `PersistentRuntimeCoordinator.run()` / `.audit()`
- `operator_kit/d261-live-fdt-arm-once.sh` — operator launcher, `--dry-run` only by default
