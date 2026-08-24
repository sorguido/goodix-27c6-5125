# D264/03 micro-corrective 3 — final pre-baseline hardening

## Third AI-PM finding

At remote HEAD `415c7357e6cdc7457ccd2f70d55805b6471818dd`, AI-PM accepted corrective2’s fixed validator authority, canonical future set, dependency inclusion, offline-gate separation, internal path-set comparison, report binding and marker preflight. Three blockers remained: D261 capability mint helpers were publicly supported, pre-baseline failures could still publish/consume the protected report destination, and future operator context accepted `SUDO_UID=0`. The offline manifest roles also required correction.

## Corrective 3

D261 intent, marker and live-I/O mint helpers in `core/live_capability.py` are private. The supported D261 surface remains `core.protected_runtime`: exact main flag issues intent, the D261 durable marker writer performs `O_EXCL`/write-all/fsync, only then its private marker factory runs, and the historical reviewed live-I/O API consumes that marker capability. Future marker minting likewise remains a private post-durable-claim seam; D261/future marker and live-I/O types are not interchangeable.

The future orchestration now records report-preflight, fprintd-started and signals-started state. It publishes only after report destination preflight, restores only transactions that actually started, and leaves baseline/operator/report-preflight failures in memory without protected report writes. The shared pure operator-context helper enforces exactly `EUID=0`, numeric present `SUDO_UID`, and `SUDO_UID != 0` for D261 and future paths.

The future durable marker writer now loops over short writes, requires forward progress, fsyncs, and mints capability only afterward. Synthetic tests prove multi-write completion and zero-progress failure before capability issuance. Offline manifest roles now explicitly classify the launcher and inspector as `OFFLINE_GATE_ONLY_NOT_FUTURE_LIVE`.

## Proof and residual state

Focused corrective3 tests cover private mint surfaces, namespace separation, report/restore transaction gating, operator-context matrix, short/zero-progress marker writes, prior canonical closure and the real persistent coordinator synthetic integration. All six real side-effect counters remain zero. Fixed64 `0x22`, Linux first B0 and post-image internal device state remain live-unproven/unknown; baseline approval and live authorization remain false.
