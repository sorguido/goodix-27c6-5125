# D264/03 corrective — protected pre-live first-image wiring

## AI-PM pre-corrective finding

The AI-PM reviewed the first D264/03 candidate at remote HEAD `830c95c407ecbe0f9b185a8adbc968ae5c9cef0d` and classified it as `PARTIAL_PRODUCTION_SHAPED_SKELETON`: one opaque preflight callback hid guard order; baseline verification was not in the candidate; marker claim did not formally mint live-I/O authority; secret ownership permitted double-close; and the failure matrix overclaimed tests. Executor-local pre-corrective SHA `7e80561882247da4d8dfcd6d34f0b40ef6f11d18` is provenance only, never remote baseline authority.

## Corrective patch

The candidate now directly verifies the approved full SHA, exact authoritative path set, commit resolution and every baseline/worktree blob before any side effect. Its control flow explicitly orders operator context, directory/report safety, protected metadata, gfusb hash, exact target, fprintd/signal transactions, holder check, non-secret material/cache, secret, marker, capability, backend/coordinator and restore/report. `FutureProductionDependencies` is a concrete future adapter to the reviewed guard, protected-runtime, real USB, cold-start/FDT and persistent-coordinator graph, while the D264/03 CLI cannot construct or reach it.

The enforced capability chain is `FutureIntentCapability → FutureMarkerClaimCapability → FutureLiveIoCapability`; nonce/type checks and one-shot consumption prevent construction, wrong-type use and reuse. Secret ownership remains outer until coordinator construction succeeds, then transfers exactly once. Before transfer the outer closes once; after transfer `PersistentRuntimeCoordinator.run()` alone owns TLS/secret/transport cleanup.

## Proof obtained

Thirty-three focused tests cover real temporary-Git baseline gates, explicit guard order and early stop, target cardinalities, holder/backend classes, marker metadata and namespace, capability reuse, ownership success/failures, CLI hard-disable/import safety and D261 arm-only semantics. An integrated test enters the real public `PersistentRuntimeCoordinator.run()` through the candidate using reviewed D263 transport/event/TLS/secret doubles and proves the historical FDT prefix, exactly one fixed64-zero-tail `0x22`, retained TLS, first B0, 80×64 decode, zero persistence/retry/forbidden continuation and host cleanup. Specific runtime tests prove TLS consume and buffered-frame failure; inherited D263/D264/02 tests are identified rather than relabeled as direct proof. The unchanged `core/persistent_runtime.py` hash records the inherited absolute 15000 ms deadline proof.

The D264/03 shell remains `--dry-run` only and reports all six real side-effect counters zero. No USB, secret, marker, fprintd, TLS sensor session or sensor command was executed.

## Remaining unknowns and gate

Fixed64 `0x22` target acceptance, Linux first B0 behavior and post-image device-internal state remain not live-proven/unknown. No baseline is approved and no live run is authorized. The next gate is AI-PM review of the corrected remote branch and byte-level live-critical set.

```text
OUTCOME=PASS_OFFLINE_PRELIVE_WIRING
ADVANCEMENT=CORRECTED_PRODUCTION_SHAPED_FIRST_IMAGE_PRELIVE_CANDIDATE
EXECUTABLE_CLOSURE=PASS_OFFLINE
D264_03_READY_FOR_AI_PM_REVIEW=true
D264_03_READY_FOR_BASELINE_APPROVAL=false
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED=false
```
