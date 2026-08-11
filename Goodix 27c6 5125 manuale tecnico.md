# Goodix 27c6:5125 on Linux

**Goodix 27c6:5125 — Technical Manual, Revision 2**

This document is the engineering handoff for research toward factory-preserving
Linux support for the Goodix USB fingerprint reader `27c6:5125`. It describes
the current technical model, the evidence behind it, the implementation work
that is safe to reuse, and the exact boundary at which development is paused.
It is not a chronological research log.

## Table of contents

- [Project status](#project-status)
- [Scope and safety model](#scope-and-safety-model)
- [Hardware and target environment](#hardware-and-target-environment)
- [What is known / what is not known](#what-is-known--what-is-not-known)
- [Evidence and confidence model](#evidence-and-confidence-model)
- [System architecture](#system-architecture)
- [Windows stack](#windows-stack)
- [USB transport](#usb-transport)
- [Security architecture](#security-architecture)
- [Observed cold-start lifecycle](#observed-cold-start-lifecycle)
- [Device configuration before TLS](#device-configuration-before-tls)
- [TLS and application protocol](#tls-and-application-protocol)
- [Post-TLS application envelope](#post-tls-application-envelope)
- [Image transport and decoding](#image-transport-and-decoding)
- [Windows image handoff](#windows-image-handoff)
- [Linux implementation status](#linux-implementation-status)
- [Current critical blocker](#current-critical-blocker)
- [The Hard Wall — Why Development Is Paused](#the-hard-wall--why-development-is-paused)
- [Required next primary evidence](#required-next-primary-evidence)
- [Suggested engineering continuation](#suggested-engineering-continuation)
- [Reproducible synthetic tests](#reproducible-synthetic-tests)
- [Public repository contents](#public-repository-contents)
- [Non-redistributed source material](#non-redistributed-source-material)
- [References](#references)
- [Glossary](#glossary)

## Project status

Development is **paused at a documented evidence boundary**. The transport,
security profile, much of the cold-start sequence, and the image record format
are sufficiently understood to support clean-room offline code. A complete
factory-preserving Linux activation is not yet justified.

| Area | Status | Current result |
| --- | --- | --- |
| USB framing and chunking | **CONFIRMED** | Bulk endpoints, 64-byte chunking, A0 and B0 wrappers are known. |
| Windows transport secret on the original laptop | **CONFIRMED** | A legitimate machine-bound secret was transferred once to a root-only Linux store and produced a live E4 `MATCH`. |
| TLS 1.2 PSK profile | **CONFIRMED** statically and synthetically | Cipher suite, identity, roles, key schedule and B0 transport are known; the real device handshake is not verified. |
| Register writes `0x80` and `DEVICE_CONFIG` `0x90` | **CONFIRMED** for the studied paths | Host provenance is closed and device effects are volatile/factory-preserving for this limited scope. |
| A2 and `0x70` | **BLOCKED** | Dispatch targets are known, but their target-specific resident bodies are not in the inventoried local corpus. |
| Complete pre-D1 path | **BLOCKED** | `PRE_D1_PATH_CLEARED=false`; the observed order is not a proven minimum safe sequence. |
| Real TLS handshake | **UNKNOWN** | `LIVE_TLS_HANDSHAKE_VERIFIED=false`. A historical experiment used a non-target D1 checksum and omitted the cold-start sequence. |
| Image record codec | **CONFIRMED** | CRC, packed-12 decode, transpose and owned `80x64` u16 raster are known. |
| libfprint image contract | **BLOCKED** | Windows consumes u16 directly; a Linux u16-to-`FpImage` policy needs real acquisitions after activation is safe. |

The detailed claim ledger is in [docs/EVIDENCE.md](docs/EVIDENCE.md).

## Scope and safety model

The project has one non-negotiable invariant:

> Preserve the factory firmware, device identity, configuration and persistent
> secure state, and preserve compatibility with the original Windows stack.

The following shortcuts are out of scope:

- erase, firmware replacement, IAP or boot-mode changes;
- provisioning a known, zero or replacement PSK;
- writes to OTP, factory data or persistent configuration;
- replaying private captures or proprietary device configuration;
- publishing machine-bound secrets, DPAPI/cache material, biometric payloads,
  fingerprint images or templates;
- treating a related Goodix model as proof for this target.

Future device work must be explicitly authorized, host-side, bounded,
non-persistent and fail-closed. Nothing in this repository is an operator kit.

## Hardware and target environment

The observed platform is a Huawei MateBook D15 / BohrD-WDH9D with the built-in
USB fingerprint reader `VID:PID 27c6:5125`.

The Windows package identifies `gfusb.dll` as a UMDF NativeUSB driver. Its INF
version is `1.1.125.14`, dated 2021-09-13. The proprietary DLL has SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2` and
is not redistributed. The target reports firmware name
`GF_ST411SEC_APP_12509`. The exact embedded APP payload identified during
private analysis is 128406 bytes with SHA-256
`70d3befbf0111ddc4cca0ea00989e672380323e9b543c08ffa3f548d0bdccb47`;
it is proprietary and not redistributed.

See [HW-001](docs/EVIDENCE.md#hw-001) and
[references to non-redistributed material](docs/REFERENCES.md#non-redistributed-oem-sources).

## What is known / what is not known

Known at high confidence:

- USB endpoints and outer frame formats;
- A0 checksum rules, including the PID 5125 pre-OR checksum coordinate;
- the relationship `validator = KDF_OEM(out A)` and `PSK_TLS = out A`;
- the Windows DPAPI/cache model on the original machine;
- TLS 1.2 pure-PSK roles, suite and identity;
- the observed cold-start ordering and target-correct D1 frame;
- complete host provenance and positive volatile lifetime evidence for the
  studied `0x80` and `0x90` paths;
- the A2 and `0x70` dispatch targets;
- the application image record, CRC, packed-12 decode and transpose;
- the Windows u16 handoff through `gfusb.dll`, `EngineAdapter.dll` and
  `AlgoChicago.dll`.

Not known or not yet justified:

- the device semantics and persistence behavior of A2 and `0x70`;
- the causal minimum subset of the observed pre-D1 sequence;
- a clean real-device TLS handshake on Linux;
- a generally reproducible, factory-preserving way to obtain or establish the
  transport secret on an arbitrary `27c6:5125`;
- the final Linux intensity/orientation policy and u16-to-`FpImage` mapping;
- enroll, verify, matching and desktop integration behavior.

## Evidence and confidence model

Important statements use four public statuses:

| Status | Meaning |
| --- | --- |
| **CONFIRMED** | Direct primary evidence, or repeatable clean-room tests tied to primary evidence, establishes the claim. |
| **STRONGLY_SUPPORTED** | Multiple independent observations support the model, but one boundary remains inferential. |
| **UNKNOWN** | Evidence does not distinguish the plausible alternatives. |
| **BLOCKED** | A named missing source or safety condition prevents promotion. |

The public [evidence index](docs/EVIDENCE.md) records claim, status, evidence
type, primary source identifier, confidence, falsifiers and residual limits.
Proprietary and private primary sources are identified by hashes and addresses
but are not redistributed.

## System architecture

```text
Windows Biometric Framework
        |
        v
EngineAdapter.dll -- loads/selects AlgoChicago.dll
        |
        | DeviceIoControl, including 0x442120 image pull
        v
gfusb.dll (UMDF NativeUSB)
        |
        | A0 control frames / B0 TLS records, 64-byte USB chunks
        v
Goodix MCU running ST411/12509 APP + unavailable resident code
        |
        v
Fingerprint sensing hardware
```

The Linux target replaces the Windows framework and proprietary algorithm
layers with a clean-room transport, protocol state machine, TLS server,
validated image decoder and eventually a libfprint-facing device. The current
blocker occurs before the real TLS transition, not in the offline codec.

## Windows stack

`gfusb.dll` owns low-level USB transport, A0/B0 framing, queues, device command
builders and the embedded TLS stack. It is a user-mode UMDF NativeUSB driver;
its PE entry point and `FxDriverEntryUm` export are distinct.

`EngineAdapter.dll` exports `WbioQueryEngineInterface` and provides a Windows
Biometric Framework engine interface. It issues `DeviceIoControl` calls to the
driver, including `0x442120`, and dynamically loads an algorithm module.
Sensor index 12 selects `AlgoChicago.dll`; its preprocessing path consumes the
u16 raster directly. The static chain strongly supports match-on-host for the
Windows implementation, but the proprietary matcher is outside the Linux
clean-room scope. See [WIN-001](docs/EVIDENCE.md#win-001).

## USB transport

### USB endpoints and chunking

The observed configuration exposes:

| Interface | Endpoint | Type | Max packet | Role |
| --- | --- | --- | ---: | --- |
| 0 | `0x82` IN | interrupt | 8 | present; not used by the reconstructed core A0 path |
| 1 | `0x01` OUT | bulk | 64 | host-to-device A0/B0 chunks |
| 1 | `0x81` IN | bulk | 64 | device-to-host A0/B0 chunks |

Logical frames may span multiple 64-byte transfers. Parsers must be streaming,
length-bounded and independent of USB completion boundaries. See
[USB-001](docs/EVIDENCE.md#usb-001).

### A0 framing

The outer A0 frame is:

```text
offset  size  meaning
0       1     0xa0 magic
1       2     wrapper length, little-endian
3       1     outer tag = (magic + len_low + len_high) mod 256
4       ...   logical A0 payload
```

The logical payload begins with a command/control byte and an inner little-
endian length. For the ordinary form, the final byte is chosen so the inner
sum is `0xaa`:

```text
final = 0xaa - (seed_control + inner_len_low + inner_len_high
                + sum(body_without_final)) mod 256
```

On the PID 5125 path, some builders calculate with a pre-OR control byte and
then set bit 0 on the wire. A serializer must retain separate logical and wire
coordinates; recomputing over the final wire control is wrong for D1. A
special final byte `0x88` exists for tightly bounded observed shapes and must
not become a general bypass. See [USB-002](docs/EVIDENCE.md#usb-002).

### ACK and typed responses

A request may receive a generic A0 ACK followed by a typed response. The ACK
uses control `0xb0`, echoes the request control and includes a status byte.
Status `0x01` and `0x07` both precede valid typed responses for several
observed operations; they must not be renamed “success” and “failure” without
new device-side evidence. Correlation must validate the echo, structure,
checksum and operation-specific response shape.

### B0 framing

B0 directly wraps a TLS record:

```text
offset  size  meaning
0       1     high nibble 0xb0
1       2     TLS-record length, little-endian
3       1     tag = (magic + len_low + len_high) mod 256
4       ...   complete TLS record
```

The send path copies an already formed TLS record after this four-byte header,
then chunks it for USB. The receive path strips B0 and queues the TLS record.
B0 is transport, not a second encryption or compression layer. See
[USB-003](docs/EVIDENCE.md#usb-003).

## Security architecture

### Machine-bound transport secret

The Windows transport secret is device/machine material, not a public default.
It must never be committed, logged, printed on a command line or embedded in a
fixture. A zero/known PSK or a value from another Goodix family is not a valid
substitute.

### DPAPI/cache relationship

Windows stores the protected container in `Goodix_Cache.bin` under the global
ProgramData area and uses machine-scope DPAPI. The decrypted 32-byte value,
called `out A` in this manual, feeds both validation and TLS:

```text
out A --KDF_OEM--> validator compared through E4
out A -----------> TLS PSK
```

The relationship is:

```text
validator = KDF_OEM(out A)
PSK_TLS   = out A
```

The cache blob alone is not portable across Windows installations. See
[SEC-001](docs/EVIDENCE.md#sec-001).

### OEM validator derivation

The E4 read uses selector `0xbb020003` and returns a 32-byte validator. The
validator is not the TLS PSK and is safe only as a comparison result, not as a
credential. The corresponding write/provisioning paths are explicitly out of
scope.

### E4 validation

On the original laptop, the legitimate Windows material was exported locally,
imported into a root-only Linux store and checked once against the physical
sensor. E4 returned `MATCH`. This is redacted live evidence that the original
machine's transport-secret boundary was bridged; no secret is present here.
See [SEC-002](docs/EVIDENCE.md#sec-002).

### TLS 1.2 PSK profile

The target profile is:

| Property | Value |
| --- | --- |
| Protocol | TLS 1.2 pure PSK |
| Cipher suite | `TLS_PSK_WITH_AES_128_GCM_SHA256` (`0x00a8`) |
| PSK identity | `Client_identity` |
| Device role | TLS client |
| Host role | TLS server |
| PSK | `out A` from the legitimate machine-bound container |

The key schedule is standard TLS 1.2 pure PSK: the premaster contains an
all-zero half and the PSK half, the PRF is HMAC-SHA-256, and AES-128-GCM uses
the normal client/server key and fixed-IV split. Cross-engine synthetic tests
have verified the profile and B0 integration, but do not constitute a live
device handshake. See [SEC-003](docs/EVIDENCE.md#sec-003).

### D1 handshake trigger

For PID `27c6:5125`, the target frame is:

```text
a0 06 00 a6 d1 03 00 00 00 d7
```

The final `d7` is calculated from pre-OR control `d0`, followed by wire control
`d1`. A historical Linux experiment sent final byte `d6`, omitted the full
cold-start path and timed out. It therefore is not a clean falsification of
the target-correct D1/TLS path and must not be retried. See
[CFG-002](docs/EVIDENCE.md#cfg-002).

## Observed cold-start lifecycle

Two independent private Windows captures show the same ordering:

```text
E4 -> A2 -> 82 -> A6 -> A2 -> 70 -> 80 x4 -> 90 -> D1(d7) -> B0/TLS
```

This is **observed ordering**, not proof that every node is causally necessary
or that it is a minimal initialization sequence. E4 validates the transport
material; `0x82` and A6 return state/factory-related data; the `0x80` and
`0x90` paths apply runtime calibration/configuration. A2 and `0x70` remain the
unresolved safety boundary. See [CFG-001](docs/EVIDENCE.md#cfg-001).

## Device configuration before TLS

### `0x80` register writes

Four `0x80` operations write these sensor-register addresses:

```text
0x0220
0x0236
0x0238
0x023a
```

Their runtime values and the corresponding fields in `0x90` share a proven
calibration producer. The target handler writes the register interface and an
SRAM shadow; it does not reach the independently identified flash-programming
path.

### `0x90` DEVICE_CONFIG

The effective configuration body is 224 bytes. Runtime-derived fields include
the same four address/value tuples and calibrated offsets. Bytes 222–223 are
an additive u16 finalizer, not a CRC:

```text
sum = 0xa5a5 + sum(111 little-endian u16 words at offsets 0..221)
finalizer = (-sum) mod 65536
body[222] = finalizer low byte
body[223] = finalizer high byte
```

A current body can be reconstructed from the current calibration response and
the factory base; the private captured body must not be copied or replayed.

### Factory-preserving evidence

The target `0x80` receiver updates runtime registers/SRAM. The `0x90` receiver
copies into SRAM and applies the configuration. Startup restores and applies a
factory `.data` source before servicing RX. A separate updater receiver reaches
the actual flash controller, while the `0x80`/`0x90` call chains do not.

Therefore the studied four `0x80` writes and `0x90` configuration are
`VOLATILE_NONPERSISTENT_PROVEN`. This result is strictly limited to those
paths; it does not make the complete pre-D1 sequence factory-preserving. See
[CFG-003](docs/EVIDENCE.md#cfg-003).

### A2 unresolved resident handler

Both observed A2 instances are byte-identical:

```text
a0 06 00 a6 a2 03 00 01 14 f0
```

Subtype 2 selects odd Thumb target `0x080272e1`. The aligned receiver body at
`0x080272e0` is below the mapped APP start and is absent from the inventoried
local target-specific corpus. Labels such as reset or enable are not confirmed
device semantics. Lifetime remains `PERSISTENCE_UNKNOWN`. See
[CFG-004](docs/EVIDENCE.md#cfg-004).

### `0x70` unresolved resident handler

The observed request is:

```text
a0 06 00 a6 70 03 00 14 00 23
```

The current target mapping is:

```text
callback table base = 0x20006d4c
family-7 slot       = 0x20006d5c
callback target     = 0x0802b8f5
```

Four APP configuration branches initialize the same slot to that odd Thumb
target. Its aligned body at `0x0802b8f4` is `0x70c` bytes below the mapped APP
start, so the target-specific body is not available. “Idle” is not a confirmed
semantic and lifetime remains `PERSISTENCE_UNKNOWN`. See
[CFG-005](docs/EVIDENCE.md#cfg-005).

## TLS and application protocol

After D1, the device acts as TLS client and the host as TLS server. TLS records
are transported in B0 frames. Once TLS produces plaintext, the Windows driver
dispatches an internal application protocol with major, subtype and slot-like
fields. The private captures show post-handshake control, finger-detection and
image cycles, but real application-data and biometric payloads are deliberately
not redistributed.

No real Linux/device TLS handshake has completed:

```text
LIVE_TLS_HANDSHAKE_VERIFIED=false
```

## Post-TLS application envelope

The plaintext envelope contains a packed command selector (major/subtype/slot),
a little-endian body length, an opaque body and an additive final byte bringing
the applicable inner sum to `0xaa`. Streaming code must validate length and
checksum before dispatch and keep unknown major/subtype combinations blocked.

Static Windows handlers support waiter responses, callback events, opaque bulk
results, state updates and fixed record lists. These route classes are useful
for architecture, but opaque payloads must remain opaque until independently
typed. In particular, a major/subtype name is not permission to issue a command
or interpret biometric data.

## Image transport and decoding

### major `0x02`

The confirmed image path reaches the Windows major-`0x02` handler after TLS
plaintext dispatch. The handler validates and decodes one record into an owned
u16 raster, then signals the image-ready handoff used by `0x442120`.

### CRC-32/MPEG-2

The record is exactly 7684 bytes:

```text
7680 packed image bytes + 4 CRC trailer bytes
```

CRC parameters are:

```text
width      = 32
polynomial = 0x04c11db7
init       = 0xffffffff
refin      = false
refout     = false
xorout     = 0x00000000
```

If the trailer bytes are `t0 t1 t2 t3`, the compared word is:

```text
(t2 << 24) | (t3 << 16) | (t0 << 8) | t1
```

CRC must be validated before allocation, decode or publication.

### packed-12 decoding

Each six-byte group `b0..b5` yields four 12-bit samples:

```text
p0 = ((b0 & 0x0f) << 8) | b1
p1 = (b3 << 4) | (b0 >> 4)
p2 = ((b5 & 0x0f) << 8) | b2
p3 = (b4 << 4) | (b5 >> 4)
```

The 7680 packed bytes therefore produce 5120 values.

### `80x64` uint16 raster

Samples are stored in `uint16_t`, but only 12 bits are valid. `uint16_t` is a
storage domain, not evidence of a 16-bit intensity sensor contract.

### orientation / transpose

Sequential wire sample `k` is stored at:

```text
destination = (k % 64) * 80 + (k // 64)
```

This is a proven bijective transpose into 5120 positions. No later Windows
u16-to-u8, rotation, flip or public image-orientation contract has been found.
See [IMG-001](docs/EVIDENCE.md#img-001).

## Windows image handoff

### ChicagoHS buffers

The decoder publishes an owned 10240-byte buffer (`5120 * sizeof(uint16_t)`) in
the ChicagoHS state. Completion occurs only after length, CRC, decode and
transpose succeed. Ownership and cancellation must prevent partial or late
frames from becoming visible.

### IOCTL `0x442120`

The UMDF handler for `0x442120` copies exactly `2 * width * height` bytes from
the decoded ChicagoHS buffer into the request output and completes the request.
It does not add a WBF image header or perform a second conversion.

### EngineAdapter

`EngineAdapter!AcceptSampleData` allocates a local work buffer, requests the
frame through `DeviceIoControl(..., 0x442120, ...)`, and passes the resulting
u16 storage into the selected preprocessing module.

### AlgoChicago

Sensor index 12 selects `AlgoChicago.dll`. Its wrapper validates input size as
twice the pixel count, copies the u16 data and consumes it directly. This
falsifies the assumption that Windows contains a recoverable u16-to-u8 adapter
at this boundary. See [WIN-001](docs/EVIDENCE.md#win-001).

## Linux implementation status

### What can already be implemented clean-room

- streaming A0/B0 framing, validation, chunking and reassembly;
- operation-specific ACK/response correlation with fail-closed unknown states;
- an abstract TLS 1.2 PSK server/BIO boundary without embedded secrets;
- the post-TLS envelope parser with unknown routes blocked;
- exact image record validation, CRC-32/MPEG-2, packed-12 decode and transpose;
- owned/cancellable frame delivery into a Linux-facing u16 buffer;
- offline state machines, synthetic fixtures and deterministic tests;
- a libfprint-shaped lifecycle skeleton that never opens hardware by default.

The small public helper in `src/` demonstrates only the frame codec. It has no
USB, TLS, secret, firmware, replay or biometric operation entrypoint.

### What is still blocked

- safe reproduction of the complete pre-D1 cold start;
- real-device TLS establishment;
- capture, finger detection, enroll, verify and matching;
- a general factory-preserving transport-secret provisioning model;
- final libfprint integration and desktop authentication.

### libfprint integration boundary

The likely architecture is a libfprint driver with asynchronous open/activate/
deactivate/cancel states, a bounded USB transport, a TLS server and owned image
delivery. The Windows u16 domain does not define libfprint's `FpImage` byte
semantics. A Linux intensity/orientation policy must be an explicit Linux
engineering decision validated against future authorized live acquisitions,
not guessed from static code.

## Current critical blocker

The local static corpus does not contain the target-specific resident bodies
for:

```text
A2   -> 0x080272e1
0x70 -> 0x0802b8f5
```

Both lie below the mapped start `0x0802c000` of the available
`GF_ST411SEC_APP_12509` APP payload. Without those bodies, their state changes,
rollback behavior and persistence cannot be established. Therefore:

```text
PRE_D1_PATH_CLEARED=false
COLD_START_MINIMUM_SEQUENCE_PROVEN=false
LIVE_TLS_HANDSHAKE_VERIFIED=false
```

## The Hard Wall — Why Development Is Paused

The original user story is simple: **use the built-in Goodix fingerprint reader
for reliable authentication on Fedora**.

Despite substantial progress in reconstructing the Windows stack, USB protocol,
TLS transport, device configuration, and image format, the project currently
stops at a genuine engineering boundary rather than at an unfinished
implementation task.

Three constraints define that boundary:

1. **Factory-preserving is a hard requirement**

   This project deliberately refuses destructive shortcuts such as firmware
   replacement, erase/IAP procedures, provisioning a known or zero PSK,
   modifying OTP/factory state, or otherwise changing the device in ways that
   may break compatibility with the original Windows installation.

   The sensor belongs to a working personal laptop and must remain compatible
   with its factory Windows stack. Any future Linux path must therefore preserve
   firmware, device identity, factory configuration, and persistent secure
   state.

2. **The required resident receiver code is missing from the available corpus**

   The observed Windows cold-start sequence contains two still-unresolved
   commands before the TLS trigger:

   ```text
   A2   -> resident target 0x080272e1
   0x70 -> resident target 0x0802b8f5
   ```

   Both targets lie below the mapped start of the available
   `GF_ST411SEC_APP_12509` application image at `0x0802c000`.

   The inventoried local target-specific corpus contains no ST411/12509 boot,
   resident, IAP, or combined image covering those receiver bodies. Their exact
   semantics and persistence behaviour therefore remain unknown.

   This is the current technical blocker for proving that the complete pre-D1
   cold-start path is safe to reproduce on Linux.

   The missing primary evidence is a **target-specific, hash-pinned ST411/12509
   resident segment covering at least `0x080272e0..0x0802b8f4`**.

3. **Secure provisioning is machine-bound and not generally reproducible**

   The Windows transport secret is protected through a machine-scoped DPAPI
   path. For the original research machine this problem was successfully
   bridged once: the legitimate Windows secret was exported locally, imported
   into a root-only Linux store, and a real read-only E4 validation against the
   physical sensor returned `MATCH`.

   Therefore this is **not the immediate blocker for continuing on that
   specific laptop**.

   It is, however, a major blocker for turning the work into a generally
   reproducible Linux solution. There is currently no demonstrated
   factory-preserving Linux provisioning procedure that can derive or establish
   the correct transport secret for an arbitrary `27c6:5125` without relying on
   the original Windows machine-bound material or modifying persistent device
   state.

### What this means

The project is not stopped because the USB framing, TLS profile, or image format
are completely unknown. Much of that path has already been reconstructed.

It is stopped because the remaining uncertainty sits exactly at a
safety-critical boundary:

```text
known host-side cold-start sequence
        |
        v
A2 / 0x70
        |
        v
missing target resident code
        |
        ?
        v
safe, factory-preserving D1/TLS transition
```

Until the missing resident behaviour can be established from new primary
evidence, reproducing the full Windows cold-start sequence would require
executing commands whose persistent effects cannot yet be proven.

For that reason:

```text
PRE_D1_PATH_CLEARED=false
LIVE_TLS_HANDSHAKE_VERIFIED=false
```

Development is therefore **paused at a documented evidence boundary**, not
declared complete and not abandoned. A new target-specific resident firmware
source, or another independently verifiable source describing these receiver
paths, would materially change the situation.

In short:

```text
blocked for the current PoC:
  resident A2/0x70 semantics and lifetime

blocked for general public reproducibility:
  clean factory-preserving transport-secret provisioning
```

No new live work, operator kit or retry of the historical TLS attempt is
authorized by this handoff.

## Required next primary evidence

The single most useful discriminator is:

> A target-specific, hash-pinned ST411/12509 resident source covering at least
> aligned addresses `0x080272e0..0x0802b8f4`.

It may be a legitimate firmware segment, combined image, symbolized build, or
another independently verifiable description of both receiver bodies. It must
be attributable to the target/version; bytes from ST411/12109 or another model
are comparative evidence only. Do not send secrets, biometric material or
proprietary blobs without a lawful sharing basis. Metadata and a reproducible
provenance description are valuable first.

## Suggested engineering continuation

If that source becomes available:

1. verify provenance, size and SHA-256 without executing it;
2. map A2 `0x080272e1` and `0x70` `0x0802b8f5` in the target address space;
3. classify their arguments, state destinations, rollback and flash/nonvolatile
   reachability;
4. determine whether both are positively factory-preserving;
5. review the observed cold-start order and identify a justified minimum;
6. implement target-correct D1 (`d7`) only in a new, independently reviewed,
   bounded design;
7. only after authorization and review, attempt one diagnostic live handshake;
8. use future authorized acquisitions to define the Linux `FpImage` contract;
9. then address enroll, verify, matching, libfprint, fprintd and desktop login.

If no new resident evidence appears, useful work remains limited to review,
documentation, synthetic tests and upstream architectural discussion. Repeating
the same local static searches will not cross the boundary.

## Reproducible synthetic tests

The public tests use only data generated in the test process. They verify:

- CRC-32/MPEG-2 parameters and corruption rejection;
- packed-12 encode/decode round trips, including boundary values;
- the `80x64` transpose is a bijection;
- an exact 7684-byte synthetic record decodes to 5120 12-bit u16 samples;
- malformed lengths and CRCs fail closed.

Run from the public tree:

```text
python3 -m unittest discover -s tests -v
```

These tests validate the clean-room codec contract. They do not validate USB,
the physical sensor, the transport secret, TLS with the device, image quality
or biometric matching.

## Public repository contents

```text
README.md
Goodix 27c6 5125 manuale tecnico.md
.gitignore
docs/EVIDENCE.md
docs/REFERENCES.md
src/goodix5125_cleanroom.py
tests/test_cleanroom.py
```

No project license has been selected:

```text
PUBLICATION_LICENSE_STATUS=NOT_SELECTED
```

Before publishing, the maintainer must choose an appropriate license or keep
the default copyright status. Do not infer a license from referenced projects.

**Create a fresh Git repository from this sanitized tree. Do not publish the
historical private research repository.**

## Non-redistributed source material

The technical model used private primary evidence that is intentionally absent:

- OEM Windows DLLs, executables and driver package files;
- the proprietary embedded ST411/12509 APP payload;
- complete disassembly, decompiler and string dumps;
- private USB captures and decrypted/application payloads;
- DPAPI/cache containers, transport secrets and operator results;
- biometric payloads, images, features and templates;
- vendored community repositories and firmware collections;
- chronological analysis bundles.

Identifiers and hashes are retained in the evidence and references indexes so
claims can be audited by the original researcher without redistributing the
sources.

## References

See [docs/REFERENCES.md](docs/REFERENCES.md) for upstream/community projects,
non-redistributed OEM sources, private captures and standards. Community code
is referenced, not vendored.

## Glossary

| Term | Meaning in this project |
| --- | --- |
| A0 | Goodix outer control/command frame. |
| B0 | Goodix outer wrapper carrying one TLS record. |
| APP | Main target firmware application payload available to private static analysis. |
| Resident code | Target code mapped below the available APP payload. |
| D1 | A0 command that triggers the observed TLS transition. |
| E4 | Read/query of the OEM validator under selector `0xbb020003`. |
| `out A` | Legitimate 32-byte machine/device transport material after Windows unprotection; never public data. |
| Validator | `KDF_OEM(out A)`, compared through E4; not the TLS PSK. |
| Factory-preserving | Positively shown not to alter firmware or persistent factory/secure state for the named path. |
| ChicagoHS | Windows driver state/path that owns the decoded `80x64` u16 frame. |
| WBF | Windows Biometric Framework. |
| UMDF | Windows User-Mode Driver Framework. |
| `FpImage` | libfprint image container whose final mapping remains a Linux-side decision. |
