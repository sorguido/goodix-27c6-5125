<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D249 — Rocky-assisted AF → FDT → first-image offline implementation

## Baselines and scope

| Item | Value |
| --- | --- |
| Local initial HEAD | `bc377c820fa661c889d61b17a4c81e42507fc78a` |
| Branch / initial status | `work` / clean |
| Rocky repository | `https://github.com/Rockytkg/goodix-linux-27c6-5125` |
| Immutable Rocky commit | `227eba219fa9e3fbac5bd59aca79f624f67cd11b` |
| Execution | offline only; no USB enumeration/open, secret, sudo, finger or device command |

The repository was reachable and the pinned commit was checked out read-only in
`/tmp`. Its root license and the SPDX headers of `src/goodix_cmd.c`,
`src/goodix_frame.c`, and `src/goodix_capture.c` were verified as
GPL-2.0-or-later; the repository notice names liushicong (Rockytkg). No firmware,
`goodix_fw.h`, libusb lifecycle, PSK, updater, persistent baseline file, or
LGPL driver code was imported.

## Differential evidence

| Contract field | Classification | Result/source |
| --- | --- | --- |
| Position after D4 | **osservato** | local capture: TLS Finished → D4/ACK → AF (packet 139/frame 140 coordinates in the D230 census) |
| AF logical/wire control | **verificato** | DLL builder uses logical AE with `more=1`; capture request is AF and response clears to AE |
| AF request body | **osservato** | five bytes `55,ts16le,00,00`; captured examples and DLL call length 5 |
| AF logical request/response size | **osservato** | request data 5; response data 16; response outer payload 24 bytes |
| AF timestamp | **verificato** host-side | DLL/Rocky: local-second milliseconds, `(second*1000 + millisecond) & 0xffff`; D249 takes controlled `ts16` so offline KAT is deterministic |
| AF ACK | **osservato** absent at the post-D4 occurrence | direct AE response; D249 rejects ACK, duplicates and unrelated frames rather than importing Rocky's permissive skip loop |
| AF timeout/pacing/physical tail | **non noto** as a complete target-safe live contract | DLL call budget is 500 ms; exact post-D4 physical tail and safe live pacing are not promoted by this offline step |
| State flags | **verificato** DLL + Rocky, locally consistent | byte 1: bit0 POV valid, bit1 TLS connected, bit3 locked; all other bits preserved as unknown |
| AF persistence | **inferito** session/read-only | fixed state query, no address; no flash/NVM/OTP dataflow found in the available APP corpus, but resident handler body is unavailable |
| Mixed A0/B0 after D4 | **osservato** at channel level | local capture has plaintext AF/FDT controls in a TLS-era session and B0/TLS traffic; DLL receive dispatcher separates wrappers |
| TLS application fragmentation/coalescing | **verificato** parser requirement, **non noto** for every target ordering | DLL stream path and existing local BIO work require byte-stream accumulation; synthetic fixtures cover fragmentation/coalescing/interleaving. Rocky is corroboration, not target proof. |

The APP12509 corpus does not expose the resident AF/FDT handler bodies. No
target-specific absolute claim about NVM side effects is therefore made beyond
the absence of a host-controlled address and the negative call/dataflow evidence
available locally.

## AF → FDT → first-image map

| Semantic name | Request | Expected response/event | Channel | Preconditions / side effect / persistence | Local / DLL / APP evidence | Rocky source | Core status / adaptation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GetMcuState | AF, `55 ts16le 00 00` | direct AE, exactly 16 state bytes | A0 plaintext | after D4; query; session/read-only inferred | capture yes; DLL callsite/serializer/parser yes; APP resident body absent | `goodix_cmd.c` | `ADAPTED_FROM_ROCKY`; strict direct response, typed unknown bits |
| FDT manual/baseline | 36, `09 01 table12` | cmd0=3 IRQ 0x100, base data | A0 command; event may be plaintext/decrypted stream | samples volatile baseline; persistence not justified | three local requests; DLL strings/control flow; APP body absent | `goodix_capture.c` | builder/event parser adapted; no retry or host persistence |
| FDT down | 32, `08 01 table12 ts16le` | ACK then cmd0=3 IRQ 2 on touch | mixed | arms finger detection; volatile inferred; cleanup unresolved | local requests; DLL builder/event logic; APP body absent | `goodix_capture.c` | builder/parser present; executable machine stops before live arming |
| SetMode Image | 20, `01 00` | cmd0=2 image payload | command A0; image may be TLS stream | exposure/capture; biometric volatile handling required | DLL/capture and local codec; APP receiver body unavailable | `goodix_capture.c` | builder present; no automatic sensor-reaching dispatch |
| FDT up | 34, `0a 01 table12` | cmd0=3 IRQ 0x200 | mixed | arms release detection, not proven to disarm/restore | local request; DLL logic; APP body absent | `goodix_capture.c` | builder/parser present; not claimed as deterministic cleanup |
| cached POV image | D2, `00 00` | POV/cached image event | mixed | only if AF bit0; no persistence observed | DLL builder/callsite; APP body absent; capture ordering incomplete | `goodix_capture.c` | builder present; conditional dispatch intentionally not automated |

## Implementation and safety

`core/post_d4.py` provides strict A0/B0 framing, AF, FDT builders/event parser,
a mixed-channel accumulator accepting only already-decrypted TLS application
bytes, the existing local image codec, a mockable `Transport` protocol and a
small monotonic machine. It has no libusb import or concrete transport.

Component classification:

- command framing, AF, FDT shapes/events: `ADAPTED_FROM_ROCKY`;
- mixed-channel accumulator: `ADAPTED_FROM_ROCKY`, tightened to fail closed;
- CRC/packed-12/transpose: `LOCAL_EXISTING_REUSED`;
- Python transport protocol, typed errors and monotonic offline seam:
  `NEW_LOCAL_IMPLEMENTATION`.

Safety is structural: the sole command builder rejects everything outside
`AF,36,32,34,20,D2`; E0, A4, F0 and F4 are negative-tested. IAP, PSK,
provisioning, firmware blobs, USB lifecycle, resets, retry/backoff, TLS reconnect,
baseline disk writes and automatic recovery do not exist in the active core.

## Offline executable closure

`timeout 30s python3 -m unittest -v tests.test_d249_post_d4` passed 7 tests in
0.030 s. Fixtures cover controlled AF serialization, exact 16-byte parsing and
unknown bits; all safe builders; FDT event parsing; A0 interleaving with a B0
decrypted stream fragmented and coalesced; synthetic non-biometric 7684-byte
CRC/unpack; truncated headers, declared length mismatch, bad checksums, bad CRC,
unexpected wrapper/control/ACK, short/long AF, EOF mid-payload and duplicate AF
responses. Operations are bounded by both a shell timeout and finite loops.

`timeout 120s python3 -m unittest discover -s tests -v` ran 48 tests: 31
passed, 1 skipped, 3 failed and 13 module-import errors. All 16 non-passes are
legacy runtime paths blocked by the environment's missing optional
`cryptography` dependency; D249's seven tests passed within that same run.
This full-suite command is reported as environment-limited, not as a pass. The
explicit D249 command is the executable closure command.

## Next-live decision

1. **AF sufficiently understood/implemented?** Sufficient for offline framing,
   direct response validation and state interpretation. Physical-tail/pacing and
   resident-handler certainty remain insufficient for declaring a live contract
   closed without a separately reviewed launcher.
2. **FDT/first image sufficiently understood/implemented?** Request shapes,
   event/image parsing and synthetic state transition are implemented. Arming,
   cleanup and failure recovery are not target-closed.
3. **Known deterministic disarm?** No. FDT up is a release-detection mode, not
   proven cleanup/restore, and automatic retry/re-arm was deliberately excluded.
4. **Request a finger in the first run?** No. The live first-image gate fails on
   cleanup/disarm and complete mixed-channel target ordering.
5. **First genuinely unresolved action?** Sensor-reaching FDT manual/down arming
   followed by a proven factory-preserving deterministic disarm/restore.

`MIN_SAFE_LIVE_BOUNDARY=EXACTLY_ONE_AF_QUERY_AFTER_THE_ALREADY_PROVEN_D4_ACK_THEN_STOP`

`MAX_JUSTIFIED_LIVE_BOUNDARY=AF_RESPONSE_VALIDATED_AND_STATE_TELEMETRY_RECORDED_THEN_STOP_BEFORE_ANY_FDT_OR_FINGER_INTERACTION`

These are candidates only, not authorization. Before any such run, a separate
step must answer the mandatory three-part methodological review, obtain an
explicit approved full Git SHA for the live-critical set, and implement
single-shot/cleanup/reseal guardrails. No live execution occurred in D249.

## Six-field closure

`OUTCOME=READY_OFFLINE`

`ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_AND_GPL_CORE_IMPLEMENTED_NO_DEVICE_SIDE_ADVANCEMENT`

`EXECUTABLE_CLOSURE=PASS`

`RESIDUAL_BLOCKER_OR_RISK=FDT_ARMING_DISARM_RESTORE_AND_COMPLETE_TARGET_MIXED_CHANNEL_ORDERING_NOT_CLOSED;AF_PHYSICAL_LIVE_CONTRACT_REQUIRES_SEPARATE_REVIEW`

`CANONICAL_DOCUMENTATION=UPDATED`

`BUNDLE=analysis/D249/D249_rocky_assisted_af_fdt_first_image_bundle.zip.b64 (decoded ZIP SHA-256 recorded after generation)`
