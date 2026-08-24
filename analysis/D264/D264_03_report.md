# D264/03 corrective 2 — fixed authority and canonical closure

## Second AI-PM finding

At remote review HEAD `495cc2c6cd2467241cf67ec4e0e8e748726e9f8c`, AI-PM confirmed guard order, ownership transfer, real-coordinator synthetic integration, D261 arm-only preservation and CLI hard-disable, but rejected closure because public validator callbacks allowed `lambda _: True`, the live-critical manifest omitted the directly imported D261 operator module, both sides of the path-set comparison were caller-controlled, offline gate files were mislabeled future-live, and production report/signal/service transactions were not fully bound.

## Corrective 2

`core/live_capability.py` is now the sole fixed authority for known D261 and future intent/marker/live-I/O types and private nonces. Public secret/material/backend APIs no longer accept validator functions: they accept only capabilities recognized by that authority. D261 wrappers retain their exact flag → intent → durable marker → live-I/O semantics; the future namespace is distinct and a future marker capability is emitted through a private seam only after the durable claim function succeeds.

`FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS` is the internal baseline authority. `verify_authoritative_baseline()` compares the approval record directly against it; there is no caller-supplied `expected_paths`. The derived manifest contains 18 future-live files, including `core/live_capability.py` and the directly imported `tools/d261_live_fdt_arm_once.py`. The D264/03 shell/tool are a separate two-file offline-gate set and are false for future-live reachability.

`FutureProductionDependencies.build(repo, intent)` now instantiates the reviewed `FprintdTransaction` and `SignalTransaction`, binds durable publication to `/var/lib/goodix-5125-poc/d261-results/d265-first-image-final.json`, validates that destination before effects, and performs a non-mutating future-marker absence check before secret materialization. Tests still inject doubles; the D264/03 CLI never constructs the production adapter.

## Proof and residual risk

Thirty-nine focused corrective tests cover callback-bypass impossibility, D261/future authority separation, canonical tuple/manifest equality, subset rejection, D261 dependency inclusion, offline-gate separation, fixed report destination collision, marker presence, existing guard/ownership/failure cases, and the real public persistent coordinator with synthetic transport/TLS/secret. All six real counters remain zero.

Target acceptance of fixed64 `0x22`, Linux first B0 behavior and post-image internal state remain unproven/unknown. No baseline or live run is approved.
