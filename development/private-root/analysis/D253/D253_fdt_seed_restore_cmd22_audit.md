# D253 — initial FDT seed, post-FDT restore, and target 0x22 audit

## Outcome

```text
OUTCOME=0x22_TARGET_MODEL_CORRECTED_OFFLINE; FDT_BOOTSTRAP_AND_RESTORE_REMAIN_OPEN
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_OFFLINE_AUDIT_AND_UNIT_REGRESSION; LIVE_PATH_NOT_CREATED
D253_OUTCOME=BLOCKED
D253_LIVE_BOUNDARY=BLOCKED
D253_LIVE_EXECUTION=NOT_PERFORMED
NEXT_MINIMUM_LIVE_BOUNDARY=NONE
REQUIRES_EXTERNAL_EVIDENCE=true
```

D253 performed no hardware, USB, TLS, D4, AF, FDT, image command, finger
interaction, network access or privileged operation. No live operator kit was
created. Initial state was branch `main`, clean working tree, HEAD
`1b97774d792a674d9edbedd29f54c4509ec06ac8`, matching the prompt baseline.

The reproducible tool `d253_offline_audit.py` reads the pinned target capture,
`gfusb.dll`, its disassembly and APP12509. It fails on source hash, packet
census, byte sequence, static dataflow or current-core mismatch. Raw target
artifacts are referenced but excluded from the D253 bundle.

## Initial `0x36` seed lifecycle

The primary DLL has two distinct writers of FDT-down global `0x180580818`:

- routine `0x180028480`, registered at `0x180026c6a` in callback slot
  `context+0x13d68`, copies a caller-supplied table into FDT-down (selector 0
  copies the same input to down/up; selector 1 copies down only);
- routine `0x180029210` validates an IRQ baseline through `0x1800290f4`,
  transforms each word as `((raw >> 1) << 8) | 0x80`, then replaces FDT-down.

`ChicagoHUSetMode` reads that global when it builds `0x36`. Thus the first
captured seed is host-supplied before the first manual sample; later tables
come from the target IRQ100 transform. The available `gfusb.dll` registers the
setter but does not contain its higher-level caller or input construction.
There is no pre-copy validator in the setter, no default sensor-type-12 seed
literal, and no evidence that six independent scalars are derived there. The
first seed is also absent as an exact literal from gfusb, APP12509,
AlgoChicago/AlgoChicagoT/AlgoMilan and EngineAdapter.

The three observed samples are chained, but the fixed-count/convergence logic
is not inside `gfusb.dll`; orchestration is external. Consequently the capture
does not establish whether three iterations are fixed, validator-driven, or
environment-dependent. It also does not show whether a zero, stale or merely
numerically different initial seed would be accepted or physically alter the
measurement. The seed is demonstrably transmitted and replaced by returned
data, but its target-side semantic necessity is unresolved.

```text
INITIAL_FDT36_SEED_SOURCE=HOST_SUPPLIED_VIA_GFUSB_CALLBACK_CONTEXT+0x13d68_TO_GLOBAL_0x180580818; ULTIMATE_SOURCE_UNRESOLVED
INITIAL_FDT36_SEED_DERIVATION=OPAQUE_12_BYTE_CALLER_INPUT_MEMCPY; NO_SIX_SCALAR_OR_SENSOR_TYPE_12_DEFAULT_DERIVATION_PROVEN
INITIAL_FDT36_SEED_VALIDITY_CHECK=NONE_FOUND_BEFORE_COPY; IRQ100_RESPONSE_HAS_SEPARATE_VALIDATOR_0x1800290f4
INITIAL_FDT36_SEED_TARGET_DEPENDENCE=NOT_PROVEN; DEVICE_SESSION_ENVIRONMENT_BINDING_UNRESOLVED
INITIAL_FDT36_SEED_REQUIRED_SEMANTICALLY=TRANSMITTED_AND_CHAINED_BUT_NONZERO_OR_FRESH_SEED_NECESSITY_NOT_PROVEN
FRESH_BASELINE_BOOTSTRAP_CLOSED=false
```

## Complete `0x36` census and physical contract

The tool enumerates all target OUTs before applying expected indices. There
are exactly three `0x36` occurrences, at zero-based packets 142, 154 and 172.
Each has logical A0 length 22, physical USB OUT length 64, data
`09 01 || table12`, ACK echo `36`/status `01`, then IRQ `0x0100`.

| OUT | input table | ACK / ms | IRQ100 / ms | learned table | relationship |
| ---: | --- | --- | --- | --- | --- |
| 142 | `adadbdbda3a3b1b1a6a6b2b2` | 145 / 0.532 | 147 / 10.878 | `80ad80be80a380b180a680b2` | initial host seed |
| 154 | `80ad80be80a380b180a680b2` | 157 / 1.550 | 159 / 21.408 | `80ad80bd80a380b180a680b2` | prior IRQ result |
| 172 | `80ad80bd80a380b180a680b2` | 175 / 2.064 | 177 / 12.219 | `80ac80bd80a380b180a680b2` | prior IRQ result; feeds all `0x32` |

All three physical tails are identical. The 42 bytes outside declared A0 have
nonzero bytes only at physical offsets 40–45: `cb f2 e2 be fb 7f`. The same
six bytes occur at those physical offsets in all `0x20`/`0x22` submissions,
while other command paths such as `0x32` have zero tails. They are therefore
not `0x36` payload and are best classified as transport/staging residue.

The DLL explicitly zeroes its local 64-byte `ChicagoHUSetMode` buffer before
construction. Since the captured submit still contains the six bytes outside
the declared A0 frame, the physical submit buffer is not simply that clean
local buffer, or is restaged later. Rocky explicitly zero-pads each physical
64-byte chunk, but it is corroboration only.
No target `0x36` with a zero tail exists. A0 length parsing and cross-command
residue support receiver indifference beyond the declared frame, but do not
prove target-specific zero-tail equivalence for `0x36`; D251 AF cannot be
substituted for that proof.

```text
FDT36_TARGET_OCCURRENCE_COUNT=3
FDT36_TAIL_PROFILE_COUNT=1
FDT36_TAIL_IDENTICAL_ACROSS_OCCURRENCES=true
FDT36_ZERO_TAIL_OBSERVED_ON_TARGET=false
FDT36_PHYSICAL_OUT_OBSERVED=LOGICAL_A0_22_BYTES; PHYSICAL_USB_OUT_64_BYTES; OUT_OF_FRAME_TAIL_42_BYTES
FDT36_OEM_OPAQUE_TAIL=NONZERO_ONLY_AT_PHYSICAL_OFFSETS_40_45:CBF2E2BEFB7F; TRANSPORT_STAGING_RESIDUE_INFERRED
FDT36_ZERO_TAIL_CORROBORATION=ROCKY_EXPLICIT_64_BYTE_ZERO_PADDING; NON_TARGET
FDT36_ZERO_TAIL_TARGET_EQUIVALENCE=NOT_PROVEN
FDT36_PHYSICAL_CONTRACT_LIVE_READY=false
```

## `goodix.dat` and host persistence

No file named `goodix.dat` is present in the reasonable repository/corpus
scope. The DLL string and control-flow evidence at `0x180026ce0` constructs
that filename, reads the sensor-reported OTP byte count, compares the loaded
prefix to live sensor OTP, and selects file OTP only when equal. The observed
OEM function then parses OTP-dependent calibration; no direct dataflow from
that function to `0x180580818` was found.

The Rocky snapshot describes a file containing OTP, a 12-byte FDT table,
navigation/image baselines and CRC, with OTP binding. Under repository
provenance rules this is an implementation/corroboration source, not primary
APP12509 proof. Without a sanitized OEM file or the missing higher-level
caller, OEM FDT fields, full-file CRC/version, sensor-type binding, write
timing, absent/corrupt fallback, and timestamp/temperature freshness cannot be
promoted. Reusing or introducing this host persistence on Linux is therefore
not safe or authorized by D253.

```text
GOODIX_DAT_AVAILABLE_FOR_AUDIT=false
GOODIX_DAT_FDT_SEED_ROLE=UNRESOLVED; OEM_GFUSB_PATH_PROVES_ONLY_OTP_PREFIX_LOAD_COMPARE; ROCKY_FDT_LAYOUT_IS_CORROBORATION_ONLY
GOODIX_DAT_OTP_BINDING=OEM_FILE_OTP_PREFIX_COMPARED_WITH_LIVE_SENSOR_OTP; BINDING_OF_ANY_FDT_FIELD_NOT_PROVEN
GOODIX_DAT_FRESHNESS_MODEL=NO_OEM_TIMESTAMP_TEMPERATURE_VERSION_OR_FDT_FRESHNESS_CHECK_PROVEN
GOODIX_DAT_REUSE_SAFETY=NOT_PROVEN_FOR_LINUX_OR_CURRENT_TARGET_COLD_START
```

## Post-FDT restore/cancel

The extended capture ordering provides positive evidence for event/cycle
progression, but not deterministic cancellation:

```text
0x32 -> IRQ2 -> 0x22 -> B0/TLS image
     -> 0x34 -> IRQ0x0200 -> 0x20 -> B0/TLS image -> later 0x32
```

The first `0x32` at packet 178 has no captured FDT event or explicit restore
before later host activity and another accepted `0x32` at 220. The third
`0x32` at 251 is ACKed and the capture ends without restore. This proves that
a later arm can be accepted without an observed cleanup; it does not reveal
whether the earlier volatile state persisted, decayed or was overwritten.

`0x34` is finger-up arming, not disable. `gfOnCancel` cancels/completes a WDF
host request and has no direct A0 builder reachability. No A2 or `0x70` occurs
after the first FDT arm. The available primary evidence does not expose
timeout, image/USB/TLS errors, close, deinit, suspend, service stop or internal
device timeout behavior. Therefore no device-side cancel, USB/TLS-close
lifetime or no-finger safe stop can be claimed.

```text
POST_FDT_RESTORE_MODEL=NO_EXPLICIT_RESTORE_OBSERVED; SUCCESS_PATH_USES_EVENT_CONSUMPTION_FINGER_UP_CYCLE_AND_LATER_REARM; FAILURE_AND_STOP_MODEL_UNKNOWN
DEVICE_SIDE_CANCEL_COMMAND=NOT_FOUND_OR_PROVEN
DEVICE_SIDE_CANCEL_EVIDENCE=NONE; GFONCANCEL_IS_HOST_REQUEST_CANCELLATION; 0x34_IS_FINGER_UP_ARM; NO_POST_FDT_A2_OR_0x70
FDT_ARM_LIFETIME=OBSERVED_UNTIL_EVENT_OR_LATER_REARM_OR_CAPTURE_END; INTERNAL_DECAY_UNKNOWN
FDT_ARM_SURVIVES_USB_CLOSE=UNKNOWN
FDT_ARM_SURVIVES_TLS_CLOSE=UNKNOWN
FDT_ARM_REENTRY_BEHAVIOR=LATER_0x32_ACCEPTED_WITHOUT_OBSERVED_RESTORE; OVERWRITE_VERSUS_EXPIRED_PRIOR_STATE_UNRESOLVED
SAFE_STOP_AFTER_FDT_ARM=false
```

## Target `0x20` versus `0x22`

All target occurrences were enumerated. Body, logical/physical lengths,
opaque tail profile and next RX shape are identical; the wire selector and
context differ.

| Property | `0x20` | `0x22` |
| --- | --- | --- |
| target occurrences | packets 167, 238 | packet 227 |
| observed context | baseline/no-finger between manual samples; after finger-up IRQ | immediately after `0x32` finger-down IRQ2 |
| data / lengths | `01 00`; logical 10, physical 64 | `01 00`; logical 10, physical 64 |
| decomposition | cmd0=2, cmd1=0, more=0 | cmd0=2, cmd1=1, more=0 |
| ACK | echo `20`, status `01` | echo `22`, status `01` |
| ACK delay | 0.274 / 0.528 ms | 0.548 ms |
| next RX | B0/TLS image-sized frame 7726 bytes after 81.326 / 80.957 ms | B0/TLS image-sized frame 7726 bytes after 47.813 ms |
| bounded semantic | SetMode Image baseline/no-finger variant | SetMode Image post-finger-down variant |
| evidence | primary target capture + DLL builder | primary target capture + DLL builder |

`ChicagoHUSetMode` selects Image mode with cmd0 2 and uses its second input as
cmd1. The generic control construction shifts cmd0 by four and cmd1 by one;
both observed controls have low `more` bit zero. Thus `0x22` is not
`0x20` with `more=1`, and request-more/response-expected semantics are not
supported. The single target first-image occurrence is exact `0x22`, ACKed as
`0x22`, followed by the B0/TLS image-sized record.

`core/post_d4.py` now retains `build_set_image()` for the separately observed
`0x20` baseline variant, adds allowlisted `build_finger_image()` and ACK policy
for exact `0x22`, and changes `FirstImageMachine` to use it after IRQ2. A
pre-send attempt latch makes that second command single-shot and terminal on
exchange/ACK failure. Tests cover exact serializer KATs, positive/negative
allowlist and ACKs, wrong/duplicate/out-of-order inputs, the second-command
fence, parsers and historical regressions. This correction is offline only.

```text
CMD20_TARGET_SEMANTICS=SETMODE_IMAGE_CMD0_2_CMD1_0_MORE_0; OBSERVED_ONLY_IN_BASELINE_NO_FINGER_CONTEXTS_IN_THIS_CAPTURE
CMD22_TARGET_SEMANTICS=SETMODE_IMAGE_CMD0_2_CMD1_1_MORE_0; OBSERVED_POST_IRQ2_FINGER_DOWN_WITH_ACK22_AND_B0_TLS_IMAGE
CMD20_22_RELATION=SAME_BODY_AND_IMAGE_MODE; CMD1_SELECTOR_0_VERSUS_1; NOT_MORE_BIT
POST_IRQ2_IMAGE_COMMAND=0x22_DATA_0100
D249_FIRST_IMAGE_MODEL_STATUS=HISTORICAL_0x20_MODEL_CORRECTED_IN_CURRENT_CORE_TO_TARGET_EXACT_0x22; STILL_OFFLINE_AND_NOT_LIVE_SAFE
```

## Decision and required external evidence

The `0x22` blocker is closed strongly enough to correct the offline current
model. The ultimate cold-start seed/bootstrap and deterministic post-FDT
restore are not closed, and `0x36` zero-tail equivalence is not target-proven.
The prompt's mandatory stop rule therefore applies: no `0x36`, `0x32` or
first-image live boundary and no operator kit.

Minimum useful external evidence is specific and has two parts:

1. a sanitized target/OEM cold-start trace with cache absent and present that
   identifies the caller/input to callback `context+0x13d68`, records the first
   seed and the sample-loop stop criterion, plus a safely acquired/sanitized
   OEM `goodix.dat` if that caller consumes it;
2. a target/OEM trace or receiver/lifecycle implementation covering explicit
   no-finger cancel/timeout/service-stop/USB-close immediately after FDT arm,
   followed by a deterministic state/re-entry check that establishes the
   device restore state.

A provenance-valid resident APP12509 family-3 receiver/lifecycle body could
substitute where it proves both effects. Repeating the existing live path
would test neither missing hypothesis.

## Safety counters

```text
USB_OPEN_COUNT=0
TLS_HANDSHAKE_COUNT=0
D4_SEND_COUNT=0
AF_SEND_COUNT=0
FDT_SEND_COUNT=0
IMAGE_COMMAND_COUNT=0
FINGER_INTERACTION_COUNT=0
RETRY_COUNT=0
PERSISTENT_WRITE_FAMILY_COUNT=0
```
