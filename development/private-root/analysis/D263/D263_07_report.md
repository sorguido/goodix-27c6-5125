# D263 / 07 — Executable closure, regression audit & micro-corrective

**Reasoning:** HIGH · **Offline:** yes · **Live execution:** no · **Gate:** Phase 1 READY + step05/06 completed → Phase 2 active.

## Executable closure (AGENTS.md §12)
- **cwd / import / path resolution:** coordinator imported as `from core.persistent_runtime import PersistentRuntimeCoordinator` from repo-root cwd; relative package imports resolve; no PYTHONPATH needed.
- **invocation mode / offline path:** `run()` drives D1→TLS handshake→D4→AF→exact bootstrap→arm→first-image terminal via injected offline doubles (ScriptedTransport/ScriptedEventSource/FakeTlsSession). No USB, no live.
- **failure reporting:** fail-closed — `run()` catches `Exception` → `FAILED_CLOSED` + `lifecycle.fail_closed()` + re-raise; `RuntimeFailure` carries cause; `audit()` exposes `failure_reason`.
- **single-use / cleanup:** `runtime_single_use` guard; `finally` closes TLS (zeroize), secret boundary, transport; on `COMPLETED` transitions to `CLOSED`.

## Regression audit (checklist)
| Audit item | Result |
|---|---|
| sequence state machine esatta | PASS — `run()` order + trace prefix `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE` then exactly `(0x22)` |
| one-shot semantics | PASS — `post_irq2_image_command()` increments `image_command_attempt_count` and fails closed on second attempt; coordinator single-use |
| no forbidden command reachability | PASS — `run()` rejects any post-arm command in `{0x34,0xA2,0x70,0x20}` and requires `extra==(0x22,)`; lifecycle `_record` rejects non-allowlisted/persistent/recovery |
| physical `0x22` policy coerente con evidence | PASS — `fdt_a0_policy(0x22, …)` is `ABSTRACT_LOGICAL_ONLY`; arm `0x32` (proven trace) may use operational FIXED64, but post-arm `0x22` is NOT in the D255/D261-proven trace, so abstract is the evidence-faithful choice (no padding invented) |
| retained TLS single-session | PASS — one `Tls12PskServerSession`; `handshake_count==1` enforced; `audit()` reports `second_server_session_created=False`, same secret-boundary object |
| no second handshake/provision/reopen | PASS — `transport_reopen_after_tls = session_count != 1`; handshake bounded; `psk_context_provisioning_count==1` |
| first-image data non persistita | PASS — plaintext zeroed after decode; on decode failure plaintext wiped before raise; `first_image_bytes_persisted=False`; only shape `(…,64)` reported, never pixels; `host_cache_write_count=0` |
| cleanup in success/failure | PASS — `cancel_pending_receive` + `terminal_stop` on success; `finally` cleanup on every path |
| lifecycle terminal state | PASS — `FIRST_IMAGE_RECEIVED`→`HOST_WAIT_CANCELED`→`TERMINAL_STOPPED` |
| exceptions fail closed | PASS — any exception → `FAILED_CLOSED` |
| no accidental logs of sensitive payload | PASS — no pixel/secret logging |
| no operator/live path preparato | PASS — no launcher/USB/operator kit |

## Micro-corrective (only permitted step)
- **Defect (local):** `_run_first_image_terminal` hardcoded `first_image_raster_shape=(80,64)` instead of deriving from the canonical decode.
- **Correction:** `raster = parse_image_payload(bytes(plaintext)); outcome["first_image_raster_shape"] = (len(raster)//64, 64)`. Decode stays canonical; no pixel persisted; scope/invariants unchanged.
- **File:** `core/persistent_runtime.py` `c266ef8a…` → `1a731cda…`
- **Retest:** `test_d263_phase2_first_image_terminal` (8) + `test_d263_phase2_support_primitives` (12) → 20 pass.

## Test execution
- **D263-targeted:** 20 executed, 20 pass, 0 fail/skip/unavailable.
- **Full discovery:** 248 executed; 5 fail + 33 error + 3 skip. All 38 non-passing are **environmental** (no OpenSSL PSK / `patch` / libusb / synthetic-TLS client in Cloud) and pre-existed D263; the Cloud environmental failures occur before reaching the
D263-modified path — the D260 rehearsal transitively imports `core/persistent_runtime.py`,
but the Cloud failure occurs before the D263 path, and none of these failures exercise
the D263-modified code paths. **No D263 regression.**

## Integrity (live-critical diff)
Exactly the three Phase-2-patched files changed vs `D263_04` baseline; all reused + backend/guardrail/launcher live-critical files byte-identical. See `D263_07_live_critical_diff_manifest.json`.

## Artefatti
- `analysis/D263/D263_07_executable_closure.json`
- `analysis/D263/D263_07_regression_results.json`
- `analysis/D263/D263_07_live_critical_diff_manifest.json`
- `analysis/D263/D263_07_report.md`
- `analysis/D263/D263_workflow_state.json` (substep 07 + `phase2_step07_summary`)
- `Goodix 27c6 5125 manuale tecnico.md` (sottosezione D263/07)

**No ZIP. Stop.**
