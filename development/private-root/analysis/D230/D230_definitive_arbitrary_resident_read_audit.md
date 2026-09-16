# D230 definitive static arbitrary resident-memory read audit

## 1. Executive answer

**Decision: `D230_NO_SAFE_MEMORY_READ_PATH_EXISTS_IN_CORPUS`.**

No safe arbitrary resident-memory read path exists in the inventoried local
target-specific corpus.  In particular, no available host builder accepts a
32-bit MCU address and length, no recovered request uses such a layout, and no
APP-present dispatcher handler returns bytes from a host-selected flash source.
Read-like commands are bounded to registers, fixed metadata, OTP/factory
selectors or production service selectors.  IAP/update flows erase/program or
reset and expose status, not raw readback.

This does **not** say the device can never expose an undocumented command.  The
resident bodies are absent and the operator-designated first capture is
definitively lost.  The negative is deliberately bounded to the supplied local
corpus and the static host paths it contains.

## 2. Exact question and terminal decision

Question: can the Windows/APP/capture corpus identify a normal-mode,
host-reachable, arbitrary-addressed, read-only and factory-preserving command
that can return `0x080272e0..0x0802b8f4`, without IAP, a boot-mode change or a
persistent write?

Answer: **no**.  None of the 15 positive causal gates is closed because the
first indispensable gates—host builder, wire address/length layout and device
read handler—are absent.  Route status is
`SAFE_RESIDENT_READBACK_ROUTE_STATUS=EXHAUSTED_IN_LOCAL_CORPUS`.

## 3. Primary corpus availability and provenance

The operator supplied `/home/guido/Scaricati/GoodixExport.zip` and designated it
as a recovered, already provenance-validated private corpus.  D230 did not
search the home directory.  Container SHA-256 is
`2b76e294059fcfa2f32a6e75d92d04731b41a01bd3221852b5584ce409a3e45e`.
The archive contains 29 safely named entries, including canonical `gfusb.dll`
SHA-256 `904eab1d...c7e2` and one target capture SHA-256
`50071c0f...184b`.

The first capture identified by the operator is definitively lost.  Only the
supplied recovered capture is counted.  D230 does not use legacy A/B labels or
pretend a historical summary is a raw packet census.

The DLL embeds 20 byte-identical named `GF_ST411SEC_APP_12509` code records.  A
bounded offline extraction gives 128384 code bytes, SHA-256
`8305b1c4...7079`.  The standalone 128406-byte APP hash in public evidence
(`70d3befb...cb47`) is not reproduced by a standalone file in this ZIP; that
distinction is retained in the manifest.  Proprietary source bytes stay under
`analysis/D230/work/` and are excluded from the bundle.

Preflight: `HEAD == origin/main == ebaeda016bd3c66d78aa16b351fd0bd13d1daf8b`
and the worktree was clean before D230 outputs.

## 4. Capture census

The recovered USBPcap has 255 packets, 52 host framed requests (48 A0, four
B0/TLS), and 55 device frames.  Twenty A0 wire controls occur:

```text
01 20 22 32 34 36 50 70 80 82 90 97 A2 A6 A8 AF D1 D4 D5 E4
```

The complete normal pre-D1 sequence is present.  A byte-window scan found three
apparent `0x080xxxxx` values, all inside one fixed 224-byte `0x90` configuration
download.  They lack field alignment, address increments, a paired requested
length and a proportional IN response.  They are rejected false positives.

Wire controls are not mechanically normalized by clearing bit 0.  Pre-OR
coordinates are reported only where the builder proves them (for example wire
97 from logical 96, and wire AF from logical AE).  D1 remains D1 under its
special checksum coordinate.

Evidence: `D230_windows_capture_opcode_census.csv` lists every request and its
next response; `D230_capture_memory_read_candidates.md` records the structural
test and lost-capture limit.

## 5. `gfusb.dll` command-builder census

The PE is ASLR-enabled x86-64 at preferred base `0x180000000`.  The checksum
builder/verifier are `0x180059a70`/`0x180059390`; core builders are A0 generic
`0x18005c148`, A0 no-ack `0x18005cc04`, and B0/TLS `0x18005c344`.

All 65 direct call-sites to those builders were classified by PE `.pdata`
function range: 61/3/1 respectively, spanning 34 enclosing functions.  The
census recovers 27 constant logical controls plus dynamic sensor-mode,
production enum, send abstraction and TLS calls.  It includes commands absent
from the recovered cold-start.

The closest host candidates fail as follows:

- `ChipRegRead` `0x180059488`: real typed read, but only LE16 register plus
  LE16 count; neither target address is encodable.
- `production_read_mcu` `0x18003c7f4`: typed production selector blob and
  bounded result; no 32-bit address serializer in the wrapper or callers.
- `ProductionOperateKey` `0x18005b4bc`: fixed operation enum for typed key/state
  results, not a pointer.
- A6/A8/AE: fixed OTP, version and state reads.
- A4/F0/F4: erase/update/check/reset maintenance, no raw read return.

No function closes `host address → serialization → response bytes`.

## 6. Alternate USB surface audit

The only command-bearing wire surface is bulk OUT `0x01` / IN `0x81`, carrying
A0 and B0 frames in 64-byte chunks.  Interrupt IN `0x82` is not host-to-device
and carries no command payload in the capture.  EP0 traffic is standard
enumeration/configuration.  No vendor/class control command, CDC, alternate
interface, raw non-A0 bulk request or separate UMDF IOCTL-to-control-transfer
builder was found.  IO indirection `0x18005ddcc` routes the already classified
pipes rather than defining another protocol.

## 7. APP 12509 dispatcher census

The APP state switch at `0x08035e3c` covers all 16 high-nibble families.
APP-present direct handlers are:

```text
8x 0x0803356c   9x 0x080367d4   Ax 0x08033188
Dx 0x080396b0   Ex 0x08033b3c   Fx 0x08033c4c
```

Families 2–7 use callbacks based at SRAM `0x20006d4c`; the observed family-7
slot points to missing resident `0x0802b8f5`.  A2 subtype 2 points to missing
resident `0x080272e1`.  Present handlers implement registers, configuration,
state, fixed queries, production selectors and firmware maintenance.  None
interprets a host-supplied 32-bit source plus length and returns that source.

The two resident bodies remain semantically unknown.  They do not defeat the
host-path negative: their exact captured requests contain no arbitrary address,
and the exhaustive gfusb builder census exposes no alternate arbitrary carrier
to either target.

## 8. Internal memory/flash read primitives

The APP necessarily performs ordinary internal loads and copies.  The audit
distinguishes those CPU primitives from host exposure.  The classified map has
nine rows: internal copy/load, register read, production selector read,
OTP/factory read, version, MCU state, firmware maintenance, flash programming
control and the two unknown resident receivers.  No primitive is both sourced
from a host-controlled MCU address and connected to an A0 response.

Therefore the useful class is a mix of
`PRIMITIVE_EXISTS_BUT_NOT_EXPOSED`, bounded typed reads and mutating write
primitives—not an exposed arbitrary resident read.

## 9. Known reads and boundaries

`D230_known_read_operations_boundary.csv` gives exact boundaries.  E4 is a
production selector service; 0x82 is a 16-bit register service; A6 is fixed
OTP/factory; A8 and AE/AF are fixed metadata/state.  `0x90` is explicitly a
download/write operation, not a read.  None reaches either resident target.

## 10. IAP, boot and debug readback

A4 (`device_action_erase_app`, `0x180061550`), the ClearApp branch
(`0x1800656f4`) and F0/F4 (`0x18006bb3c`) are maintenance flows with erase,
program and/or reset effects.  APP flash control `0x0802d874` is a positive
programming control.  “Check firmware” returns status rather than raw flash.
No boot/debug/vendor-control readback surface was found.

No arbitrary read exists in the inventoried IAP domain; accordingly the result
is not classified as `READ_EXISTS_BUT_REQUIRES_IAP`.

## 11. Unused and maintenance builders

Commands not observed in the recovered capture were not omitted.  The builder
census includes mode variants, DAC, communication test, power management,
erase/update, dynamic production enums, NOP/no-ack and TLS.  “Dump” string hits
are host diagnostic/image dumps.  No unused memory-dump serializer or
length-proportional response consumer exists in the classified graph.

## 12. Best candidates

Best candidate by shape is 0x82, but its LE16 namespace conclusively excludes
the 32-bit target range.  Best candidate by name is E4
`production_read_mcu`, but its actual dataflow is selector/result, not
address/length/raw bytes.  Neither is close enough to qualify as a safety-open
candidate.

## 13. Falsification attempts

Eleven counterexample searches are recorded in
`D230_falsification_matrix.csv`: hidden opcode, sliding address scan, unused
builder, alternate transport, APP pointer-copy handler, flash verify readback,
E4 generic peek, 0x82 alias, unclassified builder, lost-capture uniqueness and
overbroad global-negative scope.  The last test intentionally rejects any
claim that the hardware can never expose such a command.

## 14. Coverage and completeness

Coverage is sufficient for the explicitly local negative: 1/1 available
capture, 52/52 host frames, 20 wire controls, 65/65 builder call-sites, 7 USB
surface classes, 16/16 dispatcher families, nine primitive classes and six
maintenance/debug candidates.

The lost first capture is a real limit.  It prevents independent packet-level
replication and means D230 cannot enumerate opcodes that might have existed only
there.  It is not material to the scoped local-corpus conclusion because that
capture is not in the supplied corpus and the independent gfusb census covers
unobserved builders.  Recovery of it with a new opcode is a reopening condition.

The absent resident bodies are also explicit.  They prevent a global device
negative, but no inventoried host request carries arbitrary address/length data
to them.

## 15. Negative proof

An arbitrary read needs all of builder, wire layout, normal reachability,
dispatcher, source dereference, response and safety gates.  D230 has exhaustive
negative evidence at three independent earlier cuts:

1. no host builder serializes a 32-bit MCU read address and length;
2. no available request has that structure or matching proportional response;
3. no APP-present handler consumes such fields and returns raw source bytes.

Maintenance candidates additionally fail factory-preserving safety.  Thus no
safe path exists in the inventoried corpus.

## 16. Safety classification

`safe_arbitrary_memory_read_path=no`.  No live command, firmware, driver,
emulation, IAP or boot flow was executed.  No persistent mutation was made.

## 17. Target range

`0x080272e0..0x0802b8f4` is **not readable through any proven path in this
corpus**.  The wording is not a readout-protection claim and not a statement
about undocumented resident code.

## 18. Strategic implication

`NO_NOT_WITH_CURRENT_LOCAL_CORPUS_AND_CONSTRAINTS`.

After D230 there is no technically concrete, factory-preserving route in the
current local evidence to autonomously extract the missing resident code.
Repeating static searches of the same interface is exhausted.

## 19. Conditions for reopening

Reopen only for one of:

1. provenance-valid target 12509 resident/combined firmware;
2. recovered/new target capture using an opcode absent from this census;
3. target-specific OEM artifact documenting a readback interface;
4. equivalent independent primary evidence.

Do not create or recommend D231/D232 for the same static interface without one
of those sources.

## 20. Load-bearing evidence ledger

| Claim | Source / address / frame | Evidence | Confidence | Limit | Falsifier |
| --- | --- | --- | --- | --- | --- |
| No capture read request | recovered capture; all 52 host frames | structural address/length and response census | high for available capture | first capture lost | new opcode/address request |
| No gfusb builder | `0x18005c148`, `0x18005cc04`, `0x18005c344`; 65 call-sites | serializer/consumer classification | high for direct builder graph | absent external module possible | new call path/module |
| 0x82 cannot reach target | `0x180059488`; APP `0x0803356c` | LE16 register + LE16 quantity | high | device register semantics not exhaustively named | proven flash alias/extension |
| E4 is selector, not pointer | `0x18003c7f4`; APP E family `0x08033b3c` | wrapper/caller/result dataflow | high | undocumented resident selector not globally excluded | target-specific selector with raw address proof |
| No alternate transport | capture transfer census; `0x18005ddcc` | EP0/interrupt/bulk and UMDF path classification | high for corpus | new OEM backend possible | vendor/debug request artifact |
| APP-present handlers lack arbitrary read | dispatcher `0x08035e3c`; family handlers listed above | 16-family control/data-flow census | medium-high | embedded vs standalone identity distinction | canonical handler with source-pointer return |
| Resident targets remain unknown | `0x080272e1`, `0x0802b8f5` | below mapped APP start | high | bodies unavailable | provenance-valid resident bytes |
| Update is unsafe and not readback | A4/F0/F4 builders; APP `0x08033c4c`; flash control `0x0802d874` | erase/program/check/reset flow | high | no live validation (not authorized) | static raw-read branch without mutation |

## 21. Authorization statement

`NO_LIVE_AUTHORIZATION_GRANTED`.  D230 was static/offline only.  It opened no
USB device, used no sudo, installed nothing, executed no OEM driver or firmware,
performed no emulation and accessed no secret store.
