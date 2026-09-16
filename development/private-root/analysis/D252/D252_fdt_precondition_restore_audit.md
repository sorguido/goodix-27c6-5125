# D252 — D251 live closure and fresh-FDT precondition/restore audit

## Outcome

```text
OUTCOME=D251_CANONICALIZED; FRESH_FDT_PRECONDITION_AND_RESTORE_NOT_CLOSED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_OFFLINE_AUDIT; LIVE_PATH_NOT_CREATED
D252_LIVE_BOUNDARY=BLOCKED
D252_LIVE_EXECUTION=NOT_PERFORMED
```

No hardware, USB, TLS, D4, AF, FDT, finger interaction, network access or
privileged operation occurred in D252.  No operator kit was created because
the mandatory restore condition is not proved.

## Scope and evidence hierarchy

Initial Git state was branch `main`, HEAD
`f07352ce085651568a9aedbf04b097df91d7c0bb`.  The pre-existing untracked
operator artifacts `analysis/D251/D251_operator_live_stdout.json` and
`analysis/D251/D251_preflight_report.json` were treated as user-owned evidence
and were not modified.  The former matches the redacted D251 telemetry in the
step prompt, including the single AF response and all safety counters.  The
latter records the approved full baseline SHA above.  The D251 root reports
under `/var/lib/goodix-5125-poc/d251-results/` were not readable without
privilege; D252 did not use `sudo` and relies on the supplied and repository
redacted evidence.

Primary target sources, in order, were:

1. `analysis/D230/work/GoodixExport/rilevamento.pcapng`, SHA-256
   `50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`;
2. `gfusb.dll`, SHA-256
   `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`,
   and its local disassembly/string extracts;
3. mapped APP12509, SHA-256
   `8305b1c43ab092d3e55d353c5cd0a01675c1f4d47980557b084decfd53877079`;
4. canonical reports/manual D230–D251 and the D251 live artifact.

Only after those sources, the preserved Rocky snapshot at commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b` was used as corroboration.  No
Rocky code was imported or adapted by D252.

Packet indices below are zero-based.  USB OUT is endpoint `0x01`; IN is
endpoint `0x81`.  `d252_fdt_capture_audit.py` reproduces the capture claims and
fails on a source hash or byte-sequence mismatch.

## D251 canonical live result

D251 performed its approved path once: TLS completed, D4 was sent once and
ACKed with status `0x01`, AF was attempted/sent once, and exactly one
structurally valid A0/AE with a 16-byte body was received.  The state was
`byte0=0`, `flags=0x02`: byte 0 remains opaque; the only set known bit means
TLS connected, while POV-valid and locked are false and unknown flag bits are
zero.  Therefore the live state selects fresh FDT and does not select D2.
D251 stopped after AF.  Retry, persistent-write-family and application-data
counts were zero; cleanup, secret zeroization, fprintd/signal restore and
source reseal passed.  The one-shot marker is consumed.

## Complete target `0x36` reconstruction

All three target `0x36` OUT frames have logical A0 length 22, inner data length
14 (`09 01 || table12`), physical submission length 64 and endpoint `0x01`.
Each physical tail has the same six opaque nonzero bytes at physical offsets
40–45 (`cb f2 e2 be fb 7f`); these bytes are outside the declared frame and
are evidence of the OEM submission buffer, not protocol payload or material
authorized for replay.

| OUT | table input | ACK IN / delay | IRQ IN / delay | learned table |
| ---: | --- | --- | --- | --- |
| 142 | `adad bdbd a3a3 b1b1 a6a6 b2b2` | 145, echo `36`, status `01`, 0.532 ms | 147, IRQ `0100`, touch=0, 10.878 ms | `80ad 80be 80a3 80b1 80a6 80b2` |
| 154 | prior learned table | 157, echo `36`, status `01`, 1.550 ms | 159, IRQ `0100`, touch=0, 21.408 ms | `80ad 80bd 80a3 80b1 80a6 80b2` |
| 172 | prior learned table | 175, echo `36`, status `01`, 2.064 ms | 177, IRQ `0100`, touch=0, 12.219 ms | `80ac 80bd 80a3 80b1 80a6 80b2` |

For every IRQ `0x0100`, the DLL routine at `0x180029210` first invokes the
validator at `0x1800290f4`, then transforms each little-endian raw word `v` as
`((v >> 1) << 8) | 0x80` and writes six words to the FDT-down global at
`0x180580818`.  The audit independently applies that transform and obtains
exactly the next request table for the first two samples and the final table
used by every later `0x32` for the third.  This is primary target proof that
the operational FDT-down table is learned dynamically from sensor IRQ data.

The first nonzero `0x36` seed is not an exact literal in `gfusb.dll`, APP12509
or config90 frame 103, and the current D251 cold-start does not construct or
load a FDT baseline.  The DLL contains `goodix.dat` and OTP-match/base-load
paths, so an OEM host-side reused baseline is plausible, but the exact source
of this capture's first seed and its freshness are not closed by the available
corpus.  Rocky corroborates manual sampling and host-file reuse, but its first
run zero seed, retries and persistence are not target proof and are not
adopted.

No physical finger state is recorded as metadata.  The three IRQ `0x0100`
frames report touch flag zero, which supports, but does not independently
prove, the expected no-finger sampling condition.  The target capture does not
establish a bounded timeout/failure cleanup contract for a fresh `0x36` probe.

## Complete target `0x32` reconstruction

All three `0x32` requests use data
`08 01 || 80ac80bd80a380b180a680b2 || ts16le`.  They have logical A0 length
24, physical submission length 64, all-zero physical tail, endpoint `0x01`,
and an ACK with exact echo `32` and status `01`.

| OUT | timestamp bytes | ACK IN / delay | subsequent target evidence |
| ---: | --- | --- | --- |
| 178 | `6d68` | 181 / 0.458 ms | no FDT event before the next host OUT; about 80.21 s to OUT 187 |
| 220 | `b73d` | 223 / 0.433 ms | IN 225 after 7.108645 s: control `32`, IRQ `0002`, touch mask `003f`; next OUT 227 is exact wire `22`, data `0100` |
| 251 | `765e` | 253 / 0.376 ms | capture ends without a later event or explicit restore |

The DLL `ChicagoHUSetMode` at `0x180024c90` constructs subtype 1 at
`0x180024f6d`: `08 01`, 12 bytes from global `0x180580818`, then two timestamp
bytes.  At `0x180024d10..0x180024d2e` it computes
`wSecond * 1000 + wMilliseconds` and truncates to 16 bits.  Thus this is
millisecond position within the local wall-clock minute, not a baseline
identifier or monotonic lifetime token.

The final learned table is reused by all three `0x32` requests over about
117.45 seconds of one captured USB session.  This proves same-session reuse,
not validity across cold starts, temperature changes or sessions.  ACK
presence/shape is observed three times; causal necessity remains unproved.
Finger contact is inferred only for the second occurrence from IRQ 2, touch
mask and the following image path, not from external capture metadata.

The next target OUT after the only captured IRQ 2 is `0x22 [01 00]`, not
`0x20 [01 00]`.  Separate `0x20` occurrences exist for no-finger/base-image
flows.  Therefore the D249/Rocky-based `IRQ 2 -> 0x20 -> image` model is not an
exact reconstruction of this target occurrence.  The semantics of the wire
`0x22` variant must be closed before any first-image continuation is promoted.

## Semantic, persistence and lifetime classification

Primary DLL construction/call context and the target capture classify `0x32`
as finger-down detection arming and `0x36` as manual no-finger FDT baseline
sampling which produces IRQ `0x0100`.  No local request chain for either
contains E0/A4/F0/F4/IAP/provisioning operations, and no device persistent
write is observed.

That is not an absolute device-side nonmutation proof: APP12509 dispatches the
family through a callback into the missing resident region, so the receiver
body is absent.  The strongest justified persistence statement is therefore
`NO_PERSISTENT_WRITE_PATH_OBSERVED`, with strong evidence for volatile sensor
mode/dynamic baseline semantics but without a universal NVM guarantee.  Host
baseline persistence is a separate matter: OEM strings/control paths and
Rocky show a `goodix.dat`-style cache bound to OTP, but D252 neither reads nor
writes such a file and does not validate a cached table for the current Linux
cold-start.

```text
FDT_DOWN_TABLE_SOURCE=DYNAMIC_IRQ_0x100_TRANSFORM_AFTER_0x36; FIRST_0x36_SEED_PROVENANCE_UNRESOLVED
FDT_DOWN_TABLE_LIFETIME=OBSERVED_REUSED_WITHIN_ONE_CAPTURE_SESSION; CROSS_SESSION_AND_ENVIRONMENTAL_VALIDITY_NOT_PROVEN
FDT_DOWN_TABLE_TARGET_VALIDITY=TARGET_CAPTURE_SESSION_ONLY; NOT_VALIDATED_FOR_CURRENT_D251_COLD_START
FDT_DOWN_TABLE_LIVE_READY=false
FDT32_SEMANTIC_CLASS=FINGER_DOWN_DETECTION_ARMING_SENSOR_MODE [PRIMARY_TARGET]
FDT32_PERSISTENCE_CLASS=NO_PERSISTENT_WRITE_PATH_OBSERVED; DEVICE_NVM_NONMUTATION_NOT_ABSOLUTELY_PROVEN
FDT36_REQUIRED_BEFORE_FDT32=YES_FOR_CURRENT_PATH_TO_OBTAIN_FRESH_TARGET_BASELINE; SAFE_LIVE_0x36_PRECONDITIONS_NOT_CLOSED
FDT36_SEMANTIC_CLASS=MANUAL_NO_FINGER_FDT_BASELINE_SAMPLING_WITH_IRQ_0x100 [PRIMARY_TARGET]
FDT36_PERSISTENCE_CLASS=DYNAMIC_SENSOR_BASELINE_AND_HOST_LEARNED_TABLE; NO_DEVICE_PERSISTENT_WRITE_PATH_OBSERVED; DEVICE_NVM_NONMUTATION_NOT_ABSOLUTELY_PROVEN
```

## Cancel, disarm and restore audit

`0x34` is not a generic disarm: the target sends `0a 01 || up_table12`, ACKs
it, and later reports IRQ `0x0200`, consistent with arming finger-up detection.
The OEM `gfOnCancel` routine at `0x18001fa90..0x18001fd31` completes/cancels a
pending WDF host request and clears host fields; it has no direct A0 command
builder call.  It therefore does not prove device-mode restoration.

No `A2 {1,20}` or `0x70 {20,0}` follows any captured FDT arm/manual operation.
Their previously established reset-sensor/idle host semantics do not prove
that either is the OEM post-FDT cancel sequence, nor that it restores the
exact pre-FDT state.  The first `0x32` is followed by other session activity
without an explicit restore, and the third is followed by capture termination
without one.  Behavior on process termination, USB release or TLS close is
not exposed by the capture.  A2, idle, reboot or power-cycle recovery would be
deductions, not evidence-backed D252 cleanup.

```text
FDT_CANCEL_COMMAND=NOT_FOUND_OR_PROVEN
FDT_CANCEL_PRIMARY_EVIDENCE=NONE; OEM_gfOnCancel_IS_HOST_REQUEST_CANCELLATION; 0x34_ARMS_FINGER_UP
FDT_RESTORE_STATE=NOT_PROVEN
FDT_RESTORE_LIVE_PROVEN_PREDECESSOR=NONE
FDT_ARM_AND_STOP_SAFE=false
```

## Decision and next useful audit

The current Linux path has no target-valid FDT table.  Replaying the captured
table would use a stale, session-bounded value; sending `0x36` would still
depend on an unresolved initial seed/no-finger contract and would lack a
proved restore.  Sending `0x32` would arm the sensor without a deterministic
evidence-backed way to return to the pre-FDT state.  Hence neither scenario B
nor C satisfies the prompt's safety gates.

```text
NEXT_MINIMUM_LIVE_BOUNDARY=NONE
D252_LIVE_BOUNDARY=BLOCKED
```

The next useful work is offline and primary-evidence driven: map the exact OEM
source/validity checks for the first `0x36` seed; identify a target call path
that performs post-FDT device restore (not merely host request cancellation);
and resolve the `0x22` versus `0x20` mode distinction.  A new target capture
that includes explicit cancel/timeout/service-stop while armed, or the missing
resident handler, would materially advance those questions.  Repeating the
same live boundary would not.

## Safety counters

```text
USB_OPEN_COUNT=0
TLS_HANDSHAKE_COUNT=0
D4_SEND_COUNT=0
AF_SEND_COUNT=0
FDT_SEND_COUNT=0
FINGER_INTERACTION_COUNT=0
RETRY_COUNT=0
PERSISTENT_WRITE_FAMILY_COUNT=0
```
