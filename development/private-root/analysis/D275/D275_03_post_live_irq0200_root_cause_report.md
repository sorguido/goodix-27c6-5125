# D275/03 - Post-live root-cause `0x34/ACK -> IRQ 0x0200`

```text
OUTCOME=READY_OFFLINE_CORRECTIVE
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_AND_PROTOCOL_TELEMETRY_CORRECTED_OFFLINE
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=FDT_MISMATCH_CAUSALITY_STRONG_INFERENCE_NOT_POST_CORRECTIVE_LIVE_OBSERVED;LIBUSB_TIMEOUT_PARTIAL_TRANSFER_COUNT_UNKNOWN;TARGET_DEVICE_TIMEOUT_UNKNOWN
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_3443154184e138ba0b104669076132c27ace8255_PLUS_CURRENT_MAIN_WORKTREE
```

## Scope and evidence classes

No USB, sensor command, secret materialization, marker mutation, retry, timeout
change, persistent write, commit or network operation was performed. The audit
used the versioned APP12509 OEM captures, D273 static dataflow artifacts and the
production D275 call-flow.

- `OBSERVED`: both supplied D275 live results reached exact trace suffix
  `0x22, 0x34`, ACKed `0x34`, then failed with
  `TimeoutError:libusb_bulk_timeout:0x81`; retry and persistent writes were zero.
- `VERIFIED_FROM_CALL_FLOW`: emission of `0x34` requires first IRQ2, exact
  `0x22`, ACK01, first B0, accepted plaintext, raster decode and lifecycle
  `FIRST_IMAGE_RECEIVED`.
- `OBSERVED`: D263 and D274/03 contain three target IRQ2/table pairs and two
  target ACK-to-IRQ0200 timing observations.
- `VERIFIED`: the D275 live baseline passed `event.raw_base` directly to
  `DerivedFdtTable` and then `build_fdt_up()`.
- `STRONG_CAUSAL_INFERENCE`: the wrong Linux table explains ACK without the
  state transition producing IRQ0200. No post-corrective live observation
  exists, so device causality is not promoted to observed.

## First-image state and telemetry

Production order before `0x34` is:

```text
wait IRQ0002 with raw table
-> lifecycle.post_irq2_image_command()
-> submit 0x22 [01 00]
-> exact ACK 0x22/0x01
-> receive B0
-> TLS application record accepted
-> parse_image_payload() returns 5120 samples
-> lifecycle.first_image_received()
-> build/submit 0x34
```

The live report values `first_image_received=false`, zero first-image counters
and `raster_decode_count=0` were semantically wrong. The multiframe acquisition
did not increment the monotonic counters, while a later `fail_closed()` changed
the lifecycle state used as the boolean proxy. The corrective records first
IRQ2, ACK, B0 and decode in the shared coordinator and derives
`first_image_received` from the monotonic decode milestone. A later IRQ0200
timeout now preserves all first-image milestones without claiming a second
image.

## OEM table derivation versus D275 baseline

All values below are non-biometric A0 FDT metadata. Words in the raw column are
little-endian u16 values. The OEM up encoding observed for
`IRQ0002/touch_flags=0x003f` is:

```text
encoded pair = 0x80 || ((raw_word >> 1) + 0x1d)
```

| Source | Raw IRQ0002 base | OEM `0x34` table | Linux baseline table |
| --- | --- | --- | --- |
| D263 packet 225 -> 233 | `d500ee00c800ba00c500d200` | `808780948081807a807f8086` | raw base |
| D274/03 frame 213 -> 220 | `ef00f000df00c800f400d100` | `80948095808c808180978085` | raw base |
| D274/03 frame 243 -> 250 | `bc00f200cb00d500c100e800` | `807b809680828087807d8091` | raw base |

Example by word for the first D274/03 cycle:

| Index | Raw u16 | `(raw >> 1) + 0x1d` | OEM pair |
| ---: | ---: | ---: | --- |
| 0 | `0x00ef` | `0x94` | `80 94` |
| 1 | `0x00f0` | `0x95` | `80 95` |
| 2 | `0x00df` | `0x8c` | `80 8c` |
| 3 | `0x00c8` | `0x81` | `80 81` |
| 4 | `0x00f4` | `0x97` | `80 97` |
| 5 | `0x00d1` | `0x85` | `80 85` |

The normal `IRQ0200/touch_flags=0` down-table uses
`0x80 || (raw_word >> 1)`. Both D263 and D274/03 prove the same mapping:

| Source | Raw IRQ0200 base | OEM re-arm down-table |
| --- | --- | --- |
| D263 packet 237 -> 251 | `58017b01470162014c016401` | `80ac80bd80a380b180a680b2` |
| D274/03 frame 225 -> 238 | `5a017c01470162014d016501` | `80ad80be80a380b180a680b2` |

The corrective encodes these target-observed modes only. Other touch flags,
missing raw data, wrong IRQ, invalid length or out-of-range derived components
fail closed. `DerivedFdtTable` still enforces source IRQ and generation, so the
same-cycle freshness contract is unchanged.

```text
D275_LIVE_BASELINE_0x34_TABLE_EQUALS_OEM_REQUIRED_TABLE=FALSE
CORRECTED_0x34_TABLE_EQUALS_OEM_CAPTURED_TABLE=TRUE
RAW_IRQ_BASE_CAN_BE_USED_DIRECTLY_FOR_0x34=DISPROVEN
```

## OEM timing and surrounding sequence

| Capture | `T(0x34 request)` | `T(ACK)` | `T(IRQ0200)` | ACK -> IRQ0200 |
| --- | ---: | ---: | ---: | ---: |
| D263 | 117615.824 ms | 117616.576 ms | 117663.777 ms | 47.201 ms |
| D274/03 | 110585.493 ms | 110605.094 ms | 110950.953 ms | 345.859 ms |

Both are far below the unchanged Linux host deadline of 15 s. The evidence
therefore rejects timeout widening as a corrective. The D274/03 raw packet
window is first fingerprint B0, exact `0x34`, ACK01, IRQ0200; it contains no
intervening Goodix command, control transfer, endpoint operation or mode write.

```text
HOST_15S_TIMEOUT_PLAUSIBLY_TOO_SHORT=NO
TARGET_DEVICE_TIMEOUT=UNKNOWN
```

## Routing and libusb timeout meaning

`LibusbRuntimeTransport` owns one `SharedFrameRouter` and one physical EP81
reader. While the command view waits for the `0x34` ACK, `_split()` queues every
complete frame; `_pop(event=False)` removes only the ACK and leaves a queued
IRQ0200 for the subsequent event view. Existing interleaving tests cover event
before ACK, ACK before event, coalesced frames, fragmented frames, absolute
deadline and exactly-once delivery. No lost-event window was found.

TLS/B0 consumption also cannot take the IRQ0200: after first B0 the next command
read is ACK-only and the subsequent event read selects the structural pair
`(control=0x34, irq=0x0200)`. Endpoint, maximum completion size and splitter are
unchanged across this boundary.

The failure string proves libusb returned status `-7` for endpoint `0x81`.
It does not prove zero transferred bytes because `_bulk()` does not include the
libusb `transferred` value when status is nonzero. Partial transfer in the two
historical failures is therefore `UNKNOWN`; no speculative chunking corrective
was introduced.

```text
EVENT_LOSS_RACE_FOUND=FALSE
LIBUSB_TIMEOUT_PROVES_ZERO_BYTES=NOT_PROVEN
```

## Corrective and verification

Changed runtime behavior is limited to:

- derive FDT-up and FDT-down bytes for the two proven APP12509 contexts;
- preserve first-image telemetry monotonically after later failure;
- update the synthetic second-image rehearsal to target-shaped FDT events.

Unchanged invariants: exact ACK01, one USB session, one TLS object/handshake,
one secret handoff, zero retry/reopen/persistent writes, no third cycle and
terminal stop after the second image.

The focused combined suite ran 118 tests and passed. It covered D275/01,
D275/02, D272, D273 evidence metadata, D266 router, D260/D263 runtime, D274
postprocessor and the D268 semantic/runtime subset. The D275-specific tests
also prove exact D263/D274 table bytes, rejection of raw/unproven contexts and
milestone preservation after an IRQ0200 timeout.

The real operator launcher was also executed in its hardware-inert mode from
the repository root:

```text
./operator_kit/d275-second-b0-once.sh --fake-live --terminal-boundary STOP_AFTER_SECOND_IMAGE
RESULT=PASS
REAL_USB_ACCESS=false
REAL_SENSOR_COMMAND_COUNT=0
THIRD_CYCLE_STARTED=false
```

```text
FIRST_IMAGE_REACHED_IN_D275_LIVE=VERIFIED_FROM_CALL_FLOW
LINUX_0x34_ACK_REACHED=TRUE
LINUX_IRQ0200_OBSERVED=FALSE_IN_TWO_RUNS
OPERATOR_TIMING_CONFOUND=ELIMINATED_BY_ATTEMPT_2
LINUX_0x34_TABLE_EQUALS_OEM_REQUIRED_TABLE=TRUE_AFTER_CORRECTIVE_FOR_PROVEN_CONTEXT
RAW_IRQ_BASE_CAN_BE_USED_DIRECTLY_FOR_0x34=DISPROVEN
HOST_15S_TIMEOUT_PLAUSIBLY_TOO_SHORT=NO
EVENT_LOSS_RACE_FOUND=FALSE
PROTOCOL_CORRECTIVE_IMPLEMENTED=TRUE
NEW_LIVE_AUTHORIZED=false
THIRD_EQUIVALENT_LIVE_ATTEMPT_NOT_AUTHORIZED=true
```
