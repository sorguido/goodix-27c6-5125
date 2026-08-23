# D257 — exact fresh-bootstrap corrective

## Closure

```text
OUTCOME=BLOCKED_EXACT_TARGET_BOOTSTRAP_DYNAMIC_HOST_GATES
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_AND_OFFLINE_FAILURE_CONTAINMENT_IMPLEMENTED
EXECUTABLE_CLOSURE=PASS_OFFLINE; LIVE_PATH_NOT_CREATED
RESIDUAL_BLOCKER_OR_RISK=EXACT_0x50_NAV_0x82_DELTA_AND_0x20_DECRYPTED_BASELINE_HOST_DECISION_PREDICATES_NOT_DERIVABLE_FROM_D255_RAW; GENERAL_CACHE_TTL_FUNCTIONAL_SUCCESS_UNCERTAINTY
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md UPDATED ORGANICALLY
BUNDLE=analysis/D257/D257_exact_fresh_bootstrap_corrective_bundle.zip
```

D257 remains entirely offline. It did not enumerate or open USB, start a
capture, attach a VM, contact the sensor, request a finger, invoke `sudo`,
create an operator kit, approve a live baseline or authorize a run.

## Corrected decision

The prior D257 report selected only the manual-FDT subsequence from D255. A
full logical-frame census of raw capture SHA-256
`802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`
instead derives this target-observed sequence after the fresh AF/AE pair:

```text
0x36/ACK/IRQ100
0x50/ACK/dynamic NAV
0x36/ACK/IRQ100
0x82/ACK/two-byte response
0x20/ACK/encrypted baseline image
0x36/ACK/IRQ100
0x32/ACK
```

Consequently:

```text
PROJECTED_FDT_SUBSEQUENCE_REPLAY=PASS_HISTORICAL
EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY=BLOCKED_DYNAMIC_HOST_GATES_NOT_DERIVABLE_FROM_D255_RAW
FDT_OFFLINE_CANDIDATE_CLOSED=false
SEED_FRESHNESS_IS_SOLE_LIVE_BLOCKER=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
```

The earlier projected replay is retained as a useful regression for the three
manual stages and D256 cancel/re-entry contract. It is not an exact bootstrap
replay and cannot declare the candidate closed.

## Exact inter-stage audit

The timeline is derived programmatically from the fresh AF request through the
ACK of the first subsequent `0x32`; no FDT-only frame filter defines the
segment. Every logical response is correlated with its request. Dynamic NAV,
image, table, seed, OTP and biometric bytes remain redacted.

| Stage | Request | Response/dataflow | Corrective classification |
| --- | --- | --- | --- |
| `0x50` | `01 00` | A0/`0x50`, 2,417 bytes, dynamic NAV; bounded OEM marker `0x88` | required in exact candidate; target host predicate unresolved |
| `0x82` | `00 82 00 02 00` | register `0x0082`, two-byte response `80 1d` | required in exact candidate; exact decision predicate unresolved |
| `0x20` | `01 00` | 7,726-byte B0 encrypted baseline/image response | required in exact candidate; decrypt-and-validate predicate unavailable from raw |

D254 cross-family material supports the broader NAV/read-register/baseline
lifecycle, but does not prove APP12509 target predicates. Causal necessity is
therefore not excluded. The implementation never substitutes captured dynamic
blobs as runtime truth: missing semantic gates fail closed.

## Temporal provenance and freshness

Programmatic comparison of D255 metadata, operator marker and raw frame time:

```text
CACHE_MTIME_UTC=2026-08-22T20:29:28.5244390Z
VM_ATTACH_BEGIN_UTC=2026-08-22T20:56:34.7220147Z
FIRST_0x36_UTC=2026-08-22T20:56:44.146639Z
CACHE_MTIME_TO_ATTACH_BEGIN_SECONDS=1626.1975757
CACHE_MTIME_TO_FIRST_0x36_SECONDS=1635.6222000
SAME_ATTACH_SEED_GENERATION_REQUIRED=false
PERSISTED_PRE_ATTACH_CACHE_REUSE_PROVEN=true
GENERAL_CACHE_TTL_PROVEN=false
```

These deltas are not called “seed age”: cache mtime is not proven to equal seed
generation time. D255 nevertheless proves successful reuse of the OTP-bound,
CRC-valid persisted cache that pre-existed attach by more than 27 minutes and
whose FDT12 equals the first wire seed.

Current-attempt post-hoc correlation would be circular as a pre-run gate and
is not needed for factory preservation: no persistent-write family is
reachable, and a rejected seed stops on the first mismatched ACK/event/gate.
General TTL remains unproven and is retained as a bounded functional-success
risk, not promoted to a factory-preservation blocker.

## First `0x36` failure containment

The exact candidate implements the maximum offline-verifiable containment:

- attempt latch before submission;
- exactly one first `0x36`, with no automatic retry;
- 100 ms command-response timeout contract;
- exact ACK echo/status, IRQ `0x0100` with touch zero and learned-table
  validator required before advancing;
- on any failure: stop new traffic, cancel a pending receive if any and perform
  terminal host cleanup;
- no A2, `0x70`, provisioning, firmware or persistent-write path.

Negative tests prove that a bad first ACK leaves one request and one attempt,
enters `FAILED_CLOSED`, and rejects a second call without transport traffic.
The exact happy-path synthetic test proves the enforced control order
`36,50,36,82,20,36,32`, but it is an implementation test—not evidence that
the unavailable target semantic predicates have been recovered.

## Preserved boundaries

D256 remains authoritative for cancel/re-entry and terminal host/bus
quiescence. Internal prior-arm lifetime/disarm remains a non-blocking epistemic
unknown. The seed provider remains explicit, read-only, exact-layout,
CRC-checked and OTP-bound with no fallback. IRQ2→`0x22`→first image remains a
separate synthetic-codec closure. These facts do not close the missing exact
bootstrap gates.

The previous `D257_fresh_fdt_candidate_live_readiness_bundle.zip` and sidecar
remain preserved for provenance but are
`SUPERSEDED_BY_D257_EXACT_BOOTSTRAP_CORRECTIVE`. The corrective bundle
contains only step-local review artifacts and references private raw evidence
by hash.

## Final closure fields

```text
PROJECTED_FDT_SUBSEQUENCE_REPLAY=PASS_HISTORICAL
EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY=BLOCKED_DYNAMIC_HOST_GATES_NOT_DERIVABLE_FROM_D255_RAW
FDT_OFFLINE_CANDIDATE_CLOSED=false

INTERSTAGE_0x50_OBSERVED=true
INTERSTAGE_0x50_CAUSAL_CLASS=REQUIRED_IN_EXACT_CANDIDATE; CAUSAL_NECESSITY_NOT_EXCLUDED
INTERSTAGE_0x82_OBSERVED=true
INTERSTAGE_0x82_CAUSAL_CLASS=REQUIRED_IN_EXACT_CANDIDATE; CAUSAL_NECESSITY_NOT_EXCLUDED
INTERSTAGE_0x20_OBSERVED=true
INTERSTAGE_0x20_CAUSAL_CLASS=REQUIRED_IN_EXACT_CANDIDATE; CAUSAL_NECESSITY_NOT_EXCLUDED
INTERSTAGE_DYNAMIC_PAYLOAD_BLOCKER=NAV_AND_DECRYPTED_BASELINE_HOST_DECISION_GATES_NOT_DERIVABLE_FROM_D255_RAW

CACHE_MTIME_UTC=2026-08-22T20:29:28.5244390Z
VM_ATTACH_BEGIN_UTC=2026-08-22T20:56:34.7220147Z
FIRST_0x36_UTC=2026-08-22T20:56:44.146639Z
CACHE_MTIME_TO_ATTACH_BEGIN_SECONDS=1626.1975757
CACHE_MTIME_TO_FIRST_0x36_SECONDS=1635.6222000
SAME_ATTACH_SEED_GENERATION_REQUIRED=false
PERSISTED_PRE_ATTACH_CACHE_REUSE_PROVEN=true
GENERAL_CACHE_TTL_PROVEN=false
SEED_FRESHNESS_FACTORY_PRESERVATION_CLASS=NOT_A_FACTORY_PRESERVATION_BLOCKER_ON_CURRENT_EVIDENCE
SEED_FRESHNESS_FUNCTIONAL_CLASS=GENERAL_TTL_UNPROVEN_BOUNDED_FUNCTIONAL_SUCCESS_RISK

FIRST_0x36_EXACTLY_ONCE_GATE=PASS_OFFLINE
FIRST_0x36_FAIL_CLOSED_CONTAINMENT=PASS_OFFLINE
NO_SPECIAL_FDT_RECOVERY_COMMAND_POLICY=DEFAULT
A2_REENTRY_INJECTION=0
0x70_REENTRY_INJECTION=0

SEED_FRESHNESS_IS_SOLE_LIVE_BLOCKER=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false

REAL_USB_OPEN_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
REAL_COMMAND_SEND_COUNT=0
PERSISTENT_WRITE_FAMILY_COUNT=0
```
