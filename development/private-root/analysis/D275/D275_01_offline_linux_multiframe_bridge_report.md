# D275/01 — Offline Linux multiframe bridge

## Outcome

`OUTCOME=READY` and `EXECUTABLE_CLOSURE=PASS`. This step performed no real USB access and produced no new live evidence.

## Production owner graph

- `PRODUCTION_ENTRYPOINT`: `tools/d264_first_image_offline.py` (offline rehearsal; the live D268 wrapper remains unchanged).
- `PRODUCTION_COORDINATOR`, USB session owner, TLS session owner, PSK boundary owner and cleanup owner: `core.persistent_runtime.PersistentRuntimeCoordinator.run`.
- `APPLICATION_RECORD_CONSUMER`: the one retained `MemoryBioApplicationSessionAdapter` owned by `Tls12PskServerSession`.
- `FDT_LIFECYCLE_OWNER`: `PersistentRuntimeCoordinator.lifecycle`, with D273 `BoundedMultiFrameRunner` promoted through `_ProductionMultiFrameChannel` rather than copied.
- `FIRST_IMAGE_DECODE_OWNER`: `_consume_image_b0` using canonical `parse_image_payload`; the transition is recorded by `FdtLifecycle.first_image_received`.
- `POST_IMAGE_COMMAND_OWNER` and `NAV_OWNER`: `_ProductionMultiFrameChannel` bound to the coordinator's one transport/event source.
- `FDT_UP_TABLE_OWNER` / `FDT_DOWN_TABLE_OWNER`: `DerivedFdtTable`, tied to source IRQ and cycle generation.

D268 previously stopped after `_run_first_image_terminal`: it canceled receive, stopped the lifecycle and then the public `run()` finally closed TLS, secret boundary and transport. The retained TLS adapter already supported multiple application records; D275 keeps that object and consumes first, post-up and second image records through it.

## Integrated sequence and safety

The public production coordinator now supports the explicit offline boundary `STOP_AFTER_SECOND_IMAGE`. It executes first IRQ2 / exact `0x22 01 00` / ACK01 / first image decode, transitions to `FIRST_IMAGE_RECEIVED`, then runs exact `0x34`, IRQ0200-derived down generation, `0x20` and post-up B0, exact `0x50` and NAV 2417/2410, down-table `0x32`, second IRQ2-derived up generation, exact second `0x22`, ACK01, second B0 and terminal STOP.

B0 consumption is state-driven: image B0 is accepted only at the three image slots. IRQ and NAV slots parse their own exact frame class and fail closed. The bounded two-role contract makes continuation to a third cycle unreachable. Persistent-write and recovery command families remain outside the allowlist.

## Evidence and limitations

The production-shaped test proves one transport open, one TLS object, one PSK handoff/materialization, one handshake, zero retry, one terminal transport cleanup, zero persistent writes, and no remaining scripted input. Existing D272 tests prove missing/stale/cross-cycle FDT tables, exact ACK01, wrong echo/status, duplicate/out-of-order inputs and NAV shape failures. D274/03 supplies the target-specific oracle for the second edge; synthetic records contain no biometric material.

The target device timeout remains `UNKNOWN`; all test timeouts are host-only deadlines. `REAL_USB_ACCESS=false`, `NEW_LIVE_EVIDENCE=false`, `LIVE_AUTHORIZED=false`, and `AUTOMATIC_RETRY_AUTHORIZED=false`.

## Verification summary

- D275 + D272 + D263 + D259: 31 PASS, 0 FAIL, 0 SKIP.
- D268 operator-kit suite: NOT_AVAILABLE because the environment lacks the optional `cryptography` dependency during import.
- Executable closure: PASS through the repository-root invocation of the offline entrypoint and public production coordinator.
