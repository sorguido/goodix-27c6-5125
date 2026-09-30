<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix USB 27c6:5125 technical manual

This is the authoritative public technical reference for this repository's
Goodix USB `27c6:5125` support. It explains the current implementation from the
USB reader to Fedora authentication consumers, including the secure session,
image and biometric pipeline, system integration, installation, recovery, and
qualification boundary.

The implementation is intentionally narrow. A successful result on the
qualified target must not be generalized to a different Goodix reader,
firmware, distribution, desktop, or authentication policy. Start with
[Installation](docs/INSTALLATION.md) for deployment instructions and use this
manual when reviewing, maintaining, or diagnosing the design.

## Contents

1. [Purpose and support scope](#1-purpose-and-support-scope)
2. [Hardware and device identity](#2-hardware-and-device-identity)
3. [System architecture and ownership](#3-system-architecture-and-ownership)
4. [libfprint driver architecture](#4-libfprint-driver-architecture)
5. [Protected device material and secure transport](#5-protected-device-material-and-secure-transport)
6. [Device initialization and secure-session lifecycle](#6-device-initialization-and-secure-session-lifecycle)
7. [Finger detection, capture, release, and cancellation](#7-finger-detection-capture-release-and-cancellation)
8. [Image decoding and preprocessing](#8-image-decoding-and-preprocessing)
9. [SIGFM extraction, serialization, and matching](#9-sigfm-extraction-serialization-and-matching)
10. [Enrollment, verification, and identification](#10-enrollment-verification-and-identification)
11. [Templates, storage, and multi-user behavior](#11-templates-storage-and-multi-user-behavior)
12. [fprintd integration](#12-fprintd-integration)
13. [Authentication consumers](#13-authentication-consumers)
14. [SELinux and host integration](#14-selinux-and-host-integration)
15. [Build and runtime dependencies](#15-build-and-runtime-dependencies)
16. [Installation, update, and rollback](#16-installation-update-and-rollback)
17. [Removal and emergency recovery](#17-removal-and-emergency-recovery)
18. [Factory preservation, security, and privacy](#18-factory-preservation-security-and-privacy)
19. [Qualification and known limitations](#19-qualification-and-known-limitations)
20. [Troubleshooting and diagnostic principles](#20-troubleshooting-and-diagnostic-principles)
21. [Developer invariants, licensing, and references](#21-developer-invariants-licensing-and-references)

## 1. Purpose and support scope

The project adds one image-based fingerprint reader to Fedora's existing
`libfprint`/`fprintd` architecture. It is not a generic Goodix driver family and
does not replace Fedora's authentication stack.

### 1.1 Qualified target

| Dimension | Current boundary |
| --- | --- |
| USB identity | Goodix `27c6:5125` |
| Reader application | `GF_ST411SEC_APP_12509` |
| Host | Fedora 44 KDE, x86_64 |
| Accounts | Local accounts |
| Mandatory access control | SELinux Enforcing |
| Daemon and consumers | Fedora `fprintd`, PAM, Plasma, KScreenLocker, sudo, and PolicyKit |
| Reader population | One integrated reader within the qualified target scope |

Other configurations are **not qualified**. That wording means there is not
enough evidence to claim support; it does not prove that every other
configuration is incompatible.

### 1.2 Support boundary

The implementation enforces parser, material, lifecycle and ownership checks.
These checks do not establish statistical recognition accuracy or compatibility
with unlisted systems. Support is limited to the hardware/software scope above;
the [validation reference](docs/VALIDATION.md) records the release support basis.

## 2. Hardware and device identity

The driver registers only USB vendor/product ID `27c6:5125`; discovery itself is
based on that ID. A biometric activation proceeds only after local material has
passed open-time validation and the live secure bootstrap has confirmed the
supported `GF_ST411SEC_APP_12509` identity and target binding.

Interface 0 supplies the bulk transport used by the implementation:

| Property | Current value |
| --- | --- |
| Bulk OUT endpoint | `0x01` |
| Bulk IN endpoint | `0x81` |
| Bulk endpoint maximum packet size | 64 bytes |
| Observed interrupt IN endpoint | `0x82`; not used as a separate protocol-event channel by this implementation |
| Outbound B0 TLS chunk | Fixed 64-byte submission, zero-padded as needed |
| Canonical image geometry | 80 × 64 pixels |
| Canonical sample count | 5,120 |
| Driver identifier | `goodix_27c6_5125` |

The `IRQ` labels used later in this manual name Goodix protocol notifications,
not a separately used USB interrupt endpoint. Host commands, responses, secure
records, and acquisition notifications are all coordinated over bulk IN/OUT by
one router.

The implementation does not claim a physical DPI, pixels-per-millimetre value,
or final human-facing orientation. The 80 × 64 raster has a stable canonical
orientation for preprocessing and matching; that is different from a calibrated
physical orientation claim.

Firmware flashing, application replacement, key provisioning, OTP writes,
factory-data writes, and persistent identity or mode changes are outside the
supported path.

### 2.1 USB transport and A0/B0 framing

The 64-byte endpoint maximum packet size is a USB bus-packet property, not a
Goodix frame-length rule. The host USB stack may packetize one bulk submission;
the receive router correspondingly accumulates bounded input and recognizes A0
or B0 frames from their declared logical lengths rather than from transfer
boundaries.

An A0 logical frame has this production layout:

| Offset | Size | Field | Current rule |
| --- | ---: | --- | --- |
| `0` | 1 | Outer type | `0xA0` |
| `1..2` | 2 | Outer payload length | Little-endian; `body_length + 4` |
| `3` | 1 | Outer additive tag | `(0xA0 + length_low + length_high) mod 256` |
| `4` | 1 | Wire control | Command or response control carried on the wire |
| `5..6` | 2 | Inner length | Little-endian; body plus the final checksum |
| `7..n-2` | variable | Body | Phase-specific bounded bytes |
| `n-1` | 1 | Inner additive checksum | Chosen so `checksum_control + inner_length + sum(body) + checksum` is `0xAA` modulo 256 |

The codec deliberately accepts a wire control and a checksum control as
separate inputs. The required checksum coordinate is defined by the specific
builder and phase; it must not be inferred generically from the wire control.
Ordinary pre-TLS secure-session commands use the wire control itself, while D1
carries wire control `0xD1` with checksum control `0xD0`. The post-TLS lifecycle
builder uses `control & 0xFE`, for example wire control `0xAF` with checksum
control `0xAE`. These encoding rules imply no broader control-bit semantics.

Current production has two A0 physical-submission regimes. The pre-TLS
secure-session builder submits each complete logical frame directly at its
exact length. The post-TLS lifecycle builder requires a logical frame no longer
than 64 bytes, copies it into a zero-initialized 64-byte buffer, and submits all
64 bytes. USB packetization beneath either bulk request is separate. B0 has the
same four-byte outer shape with type `0xB0`, and its payload is exactly one
complete TLS record. B0 is only a Goodix transport wrapper: it adds no cipher,
authentication, compression, or key layer beyond TLS itself.

| Quantity | Meaning in the current implementation |
| --- | --- |
| TLS record length | Exact record emitted by OpenSSL, including the TLS record's own header; becomes the B0 payload length |
| B0 logical-frame length | Four-byte Goodix header plus the complete TLS record |
| Pre-TLS A0 USB submission length | Exact A0 logical-frame length in one bulk request |
| Post-TLS A0 USB submission length | Fixed 64 bytes; the zero-filled tail follows the logical frame |
| B0 USB submission length | Always 64 bytes per staged request; the last request copies the remaining logical bytes into a zero-initialized 64-byte buffer |

Only one physical OUT is outstanding. For B0, the next 64-byte staging chunk is
submitted only after the preceding completion succeeds for the active action
generation; the record is complete only after every chunk completion. Stale
generation callbacks cannot advance the current record. Consecutive outbound
B0 logical records are separated by 10 ms after the preceding record completes;
this processing interval is required between records, not between the 64-byte
chunks of one record. On receive, the single router similarly owns one
outstanding bulk IN, tolerates fragmented or coalesced USB completions, and
delivers a frame only after its complete bounded logical length is present.

## 3. System architecture and ownership

The public runtime keeps the normal Fedora ownership boundaries. Only the
device-specific `libfprint` implementation, its narrowly required private
libraries, protected reader material, and a small Plasma Login selector are
project-owned.

```mermaid
flowchart LR
    Reader["Goodix USB 27c6:5125"]
    Driver["Project libfprint runtime<br/>USB, TLS, image, SIGFM"]
    Daemon["Fedora fprintd<br/>D-Bus ownership and storage"]
    PAM["Fedora PAM"]
    KDE["Plasma Login and KScreenLocker"]
    CLI["sudo"]
    PK["PolicyKit agents"]

    Reader <--> Driver
    Driver <--> Daemon
    Daemon <--> PAM
    PAM --> KDE
    PAM --> CLI
    PAM --> PK
```

| Layer | Responsibility | Explicit non-responsibility |
| --- | --- | --- |
| Reader | Sensing, Goodix command protocol, TLS client role | Linux user identity and host template storage |
| Goodix driver | USB framing, secure session, capture, preprocessing, SIGFM extraction/matching, cancellation fences | D-Bus authorization, PAM policy, account lifecycle |
| `libfprint` | Device/action abstraction and print serialization | System user authorization |
| Fedora `fprintd` | D-Bus API, exclusive client claim, action orchestration, per-user template files | Goodix protected-material acquisition |
| Fedora PAM and KDE | Authentication policy and user interaction | USB or biometric algorithm implementation |
| Installer/recovery tools | Build, validation, system integration, safe replacement/removal | Biometric authentication and reader reprogramming |

The stock daemon remains `/usr/libexec/fprintd`. A systemd drop-in sets only a
private `LD_LIBRARY_PATH` so that this daemon resolves the project-built
`libfprint` and its four required OpenCV libraries. The project does not ship a
forked `fprintd`, greeter, sudo, PolicyKit service, or global PAM policy.

This separation matters during failure: a driver action may fail without
granting authentication; a PAM consumer may refuse a fingerprint even when the
driver works; and removal can expose current Fedora authentication files without
restoring an obsolete snapshot.

## 4. libfprint driver architecture

The device is implemented as an image device with enroll, verify, identify,
press/release reporting, and cancellation support. One per-open device context
owns the resources that must agree about an action:

| Context member | Role |
| --- | --- |
| Protected-material view | Validated target identity, transport material, configuration, and FDT data |
| USB backend | Bounded asynchronous bulk transfers on interface 0 |
| Frame router | Sole owner of physical bulk-IN reception and A0/B0 demultiplexing |
| Secure-session machine | Ordered pre-TLS bootstrap and response validation |
| TLS engine | In-memory TLS 1.2 PSK server state and recordization |
| Post-TLS lifecycle | Baseline, FDT preparation, finger detection, image, release, and STOP |
| Biometric pipeline | Decode, preprocess, SIGFM extract or match |
| Action fences | Generation tokens, cancellation state, callback drains, and poison state |

### 4.1 Open and close boundary

Opening the libfprint device validates and binds runtime material, allocates the
context, and claims USB interface 0. It deliberately submits no USB traffic.
Activation is the boundary that starts receive synchronization and the secure
reader preparation for an enroll, verify, or identify action.

Closing fences new work, invalidates the active generation, drains host-side
callbacks, releases the USB interface, and clears context and secret state. This
is the recovery boundary after a poisoned or uncertain transport epoch.

### 4.2 Single receive owner

There is never a competing USB reader for command and TLS traffic. The router
owns the physical bulk-IN stream and directs validated frames to either:

- A0 command/response processing; or
- B0 TLS-record processing.

Logical protocol lengths are not inferred from the size of one USB transfer.
Parsers accumulate bounded input, validate framing and checksums, reject trailing
or out-of-phase data, and only then deliver a typed event to the active state
machine.

### 4.3 Action generations and stale work

Every activation has a generation. Asynchronous callbacks and results are
accepted only for the generation that created them. Cancellation invalidates
that generation and waits for outstanding host callbacks to drain.

Generation checks prevent an old callback from completing a new action, but do
not prove that the reader cannot still emit old bytes. A bounded quiet-IN
synchronization therefore precedes every new secure session. If a clean boundary
cannot be proven, the context is poisoned and must be closed rather than reused.

## 5. Protected device material and secure transport

The legacy compatibility path cannot invent the target's existing PSK or
factory-derived runtime data. When that path is used, the user supplies exactly
five protected files from a lawfully available compatible environment. They stay
outside the source tree and are imported into `/var/lib/goodix-5125-poc/` as
root-owned, root-only material. A fresh host installation may instead omit this
bundle and prepare the separate state-v2 location; installation itself performs
no reader access or pairing.

| File | Technical role | Security treatment |
| --- | --- | --- |
| `target-material-manifest.json` | Declares the schema, USB/application target, and digests binding all material and selected live responses | Bounded ASCII JSON; exact schema and fields required |
| `transport-material.bin` | Carries the existing TLS PSK and compatibility validator in a versioned envelope | Secret; never generated, printed, or distributed by the project |
| `target-config-90.bin` | Supplies the validated 224-byte runtime configuration record | Length, structure, finalizer, and manifest binding checked |
| `gfusb.dll` | Provides a qualified OEM compatibility data source | Parsed as inert bounded data; never loaded or executed |
| `fdt-cache.bin` | Supplies the validated FDT seed/cache associated with the target | Length, CRC, manifest binding, and live reader binding checked |

The source tree also contains a pure fixed-profile APP12509 derivation for the
102-byte `BB010003` envelope and its 32-byte `BB020003` SHA-256 validator. Its
offline contract matches the five non-circular D190 OEM-oracle known answers
and the qualified complete-envelope vector. It has no USB or persistence
surface. A second pure boundary derives the complete 224-byte ChicagoHS
type-12 CONFIG90 from a strict 64-byte OTP record and rejects unknown chips,
CRC failures and ambiguous calibration fields. Its output is byte-identical to
the qualified target configuration. A separate validator accepts the common
332-byte DPAPI structure of the available legitimate `BB010002` values while
treating their protected regions as opaque; it neither decrypts nor synthesizes
them. The production runtime now enters a read-only coordinator only after an
explicit libfprint action. Enumeration, ordinary open, installer, boot and an
uninitialized login do not load material or claim USB. During migration, the
coordinator uses the legacy owner when no bounded live preflight is available.
With complete live evidence it derives CONFIG90, constructs the full target
binding and may select a matching state-v2 generation. A state-only activation
without that evidence fails before USB claim. The production pairing writer
remains absent.

The bounded read-only preflight applies to both a direct enrollment action and
the identify action that stock fprintd uses as its enrollment duplicate check.
It validates the target, reads `BB010002` and the current `BB020003` validator,
and derives CONFIG90 before the strict secure session is allowed to rely on
legacy pairing state. A structurally valid `BB020003` record whose 32-byte value
differs from the expected validator is a pairing-state mismatch, not a malformed
typed response; it fails closed before TLS or runtime configuration writes.

The host-only state-v2 boundary uses two fixed-size generations. Each generation
contains a 32-byte PSK record and a receipt authenticated by that PSK. The
receipt binds VID:PID, exact application, chip profile, OTP digest and CONFIG90
digest, and records `PREPARED`, `ACTIVE` or `RECOVERY_REQUIRED` transaction
state plus the minimum optional 12-byte FDT table. Files are regular,
non-linked, root-owned mode `0600` below a root-owned mode `0700` directory;
loads use no-follow opens and writes synchronize each temporary file, atomic
rename and containing directory. A complete older generation remains the only
choice until the replacement secret and receipt both validate. After an
interrupted pairing attempt, reconciliation only compares the live validator
with the candidate and optional prior validator: candidate match retries TLS,
prior match uses the prior state, and any other result requires recovery. It
never authorizes a speculative second pairing write. Legacy import is
side-by-side and records the source digest without changing or removing the old
bundle. The production coordinator can select an ACTIVE match or a PREPARED
candidate for TLS retry, but exposes no pairing write or host-state promotion
operation. Prior-generation, external-replacement and ambiguous recovery results
fail closed for a later explicit recovery boundary.

The manifest binds the bundle to `27c6:5125`, the supported application, the
other four files, and target responses used during initialization. File names,
types, modes, ownership, hard-link count, sizes, formats, and digests are checked
before import. The native runtime loader repeats the security-critical content
checks. Symlinks, extra files, writable-by-others inputs, malformed structures,
and a bundle belonging to another target fail closed.

The installed directory is mode `0700`; its regular files are root-owned mode
`0600`. Import uses no-replace semantics. An already installed valid bundle is the
canonical source for ordinary updates and reinstalls. An explicit external bundle
is accepted only when byte-identical to that set; an install is not an
implicit mechanism for swapping one reader's secrets for another's.

See [Device materials](docs/DEVICE_MATERIALS.md) for the complete public
contract and acquisition boundary. Do not attach these files, their contents,
raw USB captures, or derived secrets to a bug report.

The [Windows Material Builder](tools/windows_material_builder/README.md) is the
supported acquisition path for creating the protected five-file bundle inside
the reader's qualified Windows VM. That VM uses USB passthrough, the qualified
Goodix OEM driver, and the original Windows user/DPAPI context. The builder
validates the captured reader/application identity and required material,
recovers the existing PSK through Windows DPAPI, verifies same-reader bindings,
builds the canonical bundle, and validates all five files before publication.

The Linux installer independently validates the bundle before import. The
canonical material contract and acquisition boundary remain defined in
[Device materials](docs/DEVICE_MATERIALS.md); implementation details of the
Windows acquisition tool are documented in the
[builder audit](tools/windows_material_builder/AUDIT.md).

### 5.1 TLS roles and boundaries

The reader is the TLS client and the host driver is the TLS server. The session
uses TLS 1.2 with the reader's existing PSK. OpenSSL runs over memory BIOs; TLS
records are carried inside the validated B0 transport rather than on a socket.
The implementation pins `PSK-AES128-GCM-SHA256` (TLS codepoint `0x00A8`),
disables session tickets, and requires the exact client identity
`Client_identity`.

The implementation:

- accepts only the expected PSK identity/secret relationship;
- copies the PSK into the TLS engine through one controlled callback;
- clears temporary secret buffers after the TLS engine has copied them;
- retains one TLS engine for post-handshake control and image records;
- rejects unexpected record types, lengths, phase changes, and extra bytes; and
- fails closed rather than downgrading or manufacturing replacement material.

The pre-TLS compatibility validator and the PSK have different roles. A valid
compatibility response does not reveal or replace the secret, and the OEM DLL is
not treated as the unique identity of a physical reader.

## 6. Device initialization and secure-session lifecycle

In the supported stock-fprintd path, every biometric activation starts from an
owned USB interface and a fresh transport epoch. No normal action assumes that
a prior process left the reader in a useful state. A compiled prepared-login
interface is a separate exception discussed in
[Preparation latency](#122-preparation-latency); no current public consumer
invokes it.

```mermaid
flowchart TD
    Opened["Open: validate material and claim USB"] --> Syncing["Activate and establish quiet receive boundary"]
    Syncing --> Bootstrap["Pre-TLS bootstrap and TLS 1.2 PSK"]
    Bootstrap --> Prepare["FDT readings and baseline preparation"]
    Prepare --> Armed["Finger detection armed"]
    Armed --> Image["Finger down and complete image"]
    Image --> Host["Host extraction or matching<br/>runs independently"]
    Image --> Release["Action-specific release sequence"]
    Release --> Kind{"Enrollment action?"}
    Kind -- Yes --> EnrollGate{"Stage result and enrollment<br/>release sequence ready?"}
    Host --> EnrollGate
    EnrollGate -- Retry or intermediate stage --> Armed
    EnrollGate -- Terminal template stage --> EnrollDone["Enrollment complete"]
    EnrollDone --> Closing["Fence and close resources"]
    Kind -- No --> Stop["Verify or identify protocol STOP"]
    Stop --> Drain["USB backend drained"]
    Host --> TerminalGate{"Host outcome and<br/>STOP plus drain known?"}
    Drain --> TerminalGate
    TerminalGate -- Eligible clean NO_MATCH and explicit next action --> Syncing
    TerminalGate -- Match or error --> Closing
    Syncing -. Cancel or error .-> Closing
    Bootstrap -. Cancel or error .-> Closing
    Prepare -. Cancel or error .-> Closing
    Armed -. Cancel or error .-> Closing
    Image -. Cancel or error .-> Closing
    Release -. Cancel or error .-> Closing
    Host -. Processing error .-> Closing
```

### 6.1 Pre-session receive synchronization

Activation first arms the receive path and looks for a bounded quiet boundary.
Received bytes are discarded during this synchronization phase and the receive
is rearmed; no protocol command is sent first. A zero-byte USB timeout after the
250 ms quiet interval, with the backend drained, is the successful boundary.

This is not an unlimited flush. At most 16 received completions, 64 KiB of data,
or two seconds total are allowed. A non-timeout transfer error, an empty
successful completion, or exhaustion of a hard bound fails closed and poisons
the epoch.

The code does not use blind USB resets, clear-halt loops, factory writes, or
unbounded command retries to force progress. Those operations would hide the
actual state and could cross the factory-preservation boundary.

### 6.2 Pre-TLS bootstrap

The secure bootstrap is a strict phase machine. Its durable responsibilities are:

1. recover the supported application command context;
2. confirm the exact application identity;
3. validate target compatibility against the supplied material;
4. read and bind the expected chip/factory responses without writing them;
5. perform the required operations treated as session/runtime mode and register setup;
6. send the validated configuration record; and
7. enter the transport state in which the reader initiates TLS.

The current phase order is:

```text
REENTRY_RECOVERY_A2
→ A8
→ E4
→ OEM_COLD_START_A2_1
→ CHIP_82
→ OTP_A6
→ OEM_COLD_START_A2_2
→ MODE_70
→ DAC_220 → DAC_236 → DAC_238 → DAC_23A
→ CONFIG_90
→ D1
→ TLS
```

The phase contracts are deliberately narrower than informal command names:

| Phase/control | Known role | Required response contract | Runtime/persistence evidence boundary |
| --- | --- | --- | --- |
| Re-entry `A2` | Establish the bounded project re-entry state before identification | ACK plus the target-pinned three-byte typed A2 response | Temporary session preparation; not a USB reset, retry loop, or factory reset |
| `A8` | Return and confirm the supported application identity | ACK plus exact typed `GF_ST411SEC_APP_12509` response | Read/check only |
| `E4` | Validate the existing target/material compatibility binding | ACK plus the expected typed validator response | Does not expose, replace, or provision the PSK |
| Cold-start `A2` #1 | First supported sensor-reset step in the known cold-start path | ACK plus the target-pinned three-byte typed A2 response | Exact request resets the sensor side in current evidence; classified as volatile, not absolute NVM readback proof |
| `0x82` | Read and bind a four-byte target response | ACK plus a four-byte digest-pinned typed response | Read/check; not claimed to be an immutable chip identifier |
| `A6` | Read and bind factory/OTP-related data | ACK plus a 64-byte digest-pinned typed response | Read/check, never an OTP write |
| Cold-start `A2` #2 | Second supported sensor-reset step in the known cold-start path | ACK plus the same target-pinned A2 response shape | Same bounded volatile classification as the first cold-start A2 |
| `0x70` | Select the supported runtime mode | ACK only | Runtime/session mode; no absolute NVM non-mutation claim |
| Four `0x80` DAC writes | Apply validated values to registers `0x0220`, `0x0236`, `0x0238`, and `0x023A` | ACK only for each write | Validated runtime register values; not firmware, OTP, identity, or provisioning |
| `0x90` | Download/write the validated 224-byte configuration | ACK plus exact typed success body `01 00` | Configuration write path classified as runtime for the exact supported replay; it is not a read and not universal NVM proof |
| `D1` | Change from A0 command traffic to B0-wrapped TLS | No ordinary A0 ACK; the reader's B0/TLS ClientHello is required | Transport transition only |

For every ACK-bearing phase above, current production accepts only status
`0x01` or `0x07`, requires the exact command echo and two-byte ACK body, and
does not assign invented names or bit meanings to those status values. The ACK
itself is an A0 outer frame with inner control `0xB0`; that must not be confused
with an outer B0 TLS wrapper. ACK-plus-typed phases require two distinct logical
responses in order, while ACK-only phases complete on the strict ACK. D1 instead
changes the expected outer class directly to B0/TLS.

`CHIP_82` is an implementation phase name for a checked four-byte
target-bound response, not a claim that the value is an immutable chip ID.
`OTP_A6` is a read and check of a 64-byte factory/OTP-related response; it does
not write OTP. The four DAC phases apply the validated runtime values for
registers `0x0220`, `0x0236`, `0x0238`, and `0x023A`, and `CONFIG_90` sends the
validated 224-byte configuration.

The command-level conversation, including the phase names needed for protocol
review, is documented in the public
[real Goodix conversation appendix](docs/learning/appendix_real_goodix_conversation.md).
That appendix is descriptive; protected payloads and secrets remain outside the
repository.

### 6.3 Post-TLS preparation

After the TLS handshake, the driver drains the handshake boundary before
starting the post-handshake control and protected-data exchange. It then:

1. selects and validates the expected post-TLS controller state;
2. gathers the first two fresh FDT readings;
3. reads the returned threshold and classifies the first measured delta;
4. obtains a no-finger baseline image;
5. gathers a third reading and validates the second delta; and
6. arms finger detection.

The current post-TLS bootstrap is:

```text
A0 D4
→ A0 AF and typed AE controller state
→ A0 0x36 with current table → IRQ 0x0100 → first fresh reading
→ A0 0x50/NAV
→ A0 0x36 → IRQ 0x0100 → second fresh reading
→ post-TLS A0 0x82 → threshold and first-delta classification
→ A0 0x20 → B0/TLS no-finger baseline image
→ A0 0x36 → IRQ 0x0100 → third fresh reading
→ second-delta check
→ A0 0x32 arm
```

FDT preparation is part of each fresh action's trusted state. A threshold or
baseline from an uncertain epoch is not silently reused.

The lifecycle represents a missing persisted FDT seed explicitly. In that
mode, the first `0x36` carries an all-zero 12-byte table; it is not confused
with a supplied seed. Exactly three clean no-finger readings are allowed and
there is no automatic retry. Only after both measured deltas pass does the
lifecycle expose the learned 12-byte FDT table as a candidate for later local
state persistence. Touch flags, malformed or duplicate frames, timeout, or
temperature/drift classification failure terminate the attempt and clear that
candidate. The decoded image baseline remains action-local and is never part
of the persistence interface. Legacy activation marks its imported seed as
supplied. State-v2 activation uses the authenticated 12-byte table when present
and represents an absent table as a zero seed; the later live qualification
gate must prove the explicit missing-seed lifecycle before enabling
self-initialization.

### 6.4 FDT table derivation and arming

FDT state is fresh, action-local, and generation-scoped. Each accepted event
must belong to the active generation and have exactly six little-endian 16-bit
raw channel words. Reserved touch-flag bits outside the low six bits fail
closed. Let `R[i]` be raw channel word `i` and `T[i]` its touch bit:

| Boundary | Required event | Derived 12-byte table for channel `i` |
| --- | --- | --- |
| Baseline learning/refresh | Control `0x36`, IRQ `0x0100`, flags zero | `table[2i] = 0x80`; `table[2i+1] = (R[i] >> 1) & 0xFF`; components `0x00` and `0xFF` are rejected |
| Finger-down up-table | Control `0x32`, IRQ `0x0002`, at least one valid touch bit | `table[2i] = 0x80`; active channel: `table[2i+1] = (R[i] >> 1) + 0x1D`; inactive channel: `0x1B`; overflow is rejected |
| Release down-table | Control `0x34`, IRQ `0x0200`, flags zero | `table[2i] = 0x80`; `table[2i+1] = R[i] >> 1`; overflow is rejected |

The preparation sequence issues `0x36` and accepts IRQ `0x0100` readings to
learn/refresh the current table. Three fresh readings participate in the
current bootstrap; measured deltas are checked against the returned threshold
before the first arm. Command `0x32` arms finger-down detection with body prefix
`08 01`, the validated 12-byte current table (the fresh down-table on re-arm),
and the applicable little-endian timestamp. IRQ `0x0002` is the finger-down
boundary used before image acquisition; its raw words and touch mask also
produce the up-table later used by `0x34` in the release path.

In the ordinary contact path, the IRQ `0x0200` release event must yield a fresh
valid down-table before reuse.
Re-arm uses that table and the re-arm timestamp, never a stale table from
another generation. Submission is allowed only after the complete release tail
has reached the re-arm gate, libfprint is again awaiting a finger, a fresh
down-table is valid, and no re-arm has already been submitted. Failure of any
formula, phase, generation, flag, threshold, or lifecycle gate terminates the
action instead of silently reusing old FDT state.

For the repeated enrollment zero-mask alternative, an exact `0x36 / IRQ 0x0100`
with zero flags derives the DOWN table locally: each channel contributes
`0x80, R[i] >> 1`, with every shifted value constrained to 1–254. All six raw
words and the current stage relationship are checked before the temporary
12-byte table is committed atomically. There is no partial update, wrapping or
truncation. This stricter local rule does not change bootstrap or global FDT
acceptance. The resulting table and normal re-arm timestamp belong to this
contact; a passive late release cannot update a table already used by an
in-flight request.

### 6.5 Target enrollment image-choice semantics

The qualified OEM implementation maps PID5125 to project8 and chip `0x2504` to
sensor type12 (ChicagoHU). Its enrollment image-choice path preserves the
already preprocessed primary when the manual FDT sample has no active channels.
Optional command `0x20` requires more than five active channels, software
finger-down and an available retry slot on that target. Zero skips supplementary
acquisition, clears software finger-down, and leaves a later `0x32` conditional
on another request. These request-specific OEM rules are not a universal Linux
image-quality policy or proof of physical finger removal.

The image-choice option supports configuration overrides; its effective value
cannot be inferred from a USB trace alone. On chip `0x2504`, primary acquisition
bypasses a separate manual-sample path that would refine the UP table, while the
retry IRQ0100 path uses the DOWN-table helper. Skipping optional acquisition
therefore still requires the local DOWN-table derivation above.

The first `0x34` monitor is already armed when manual `0x36` runs. The OEM host
waits for manual-sample completion without draining the independent IRQ0200
notification, whose consumer can also conditionally refresh background data.
The Linux zero branch performs no such background refresh. OEM host control
flow establishes neither a firmware flush nor a guarantee about late release
bytes across contacts. Rockytkg supplies SIGFM/preprocessing code, not evidence
for the Goodix IRQ/FDT/re-arm protocol.

## 7. Finger detection, capture, release, and cancellation

### 7.1 Capture command graphs

Once armed, a verify/identify acquisition follows this order. A0 remains the
control protocol; protected image data travels as TLS records in B0.

```text
IRQ 0x0002 (finger down)
→ A0 0x22 image request
→ B0/TLS complete image record
→ A0 0x34 release request
→ IRQ 0x0200 release notification
→ A0 0x20 plus B0/TLS post-release protected-data payload
→ A0 0x50/NAV transition
→ protocol STOP phase
→ independent USB backend drain
```

`STOP` is the clean protocol phase; backend drain is a separate required
predicate. Neither means that the fingerprint matched. Image processing starts
as soon as the image is delivered and can finish before or after device release,
so the driver waits for the host biometric result, protocol phase, and backend
drain required by that action before teardown or permitted reuse.

In the ordinary verify/identify path, finger-up is not reported to libfprint
until the complete release tail has been accepted. This prevents the user interface from inviting another contact while
the previous contact is still active at the protocol layer.

Enrollment uses a dedicated multi-contact graph. Every contact begins with
`IRQ 0x0002`, A0 `0x22` plus its acknowledgement, and a primary B0/TLS image.
The first contact then establishes its navigation/re-arm path:

```text
A0 0x34/ACK → IRQ 0x0200
→ A0 0x20/ACK → opaque auxiliary B0/TLS payload
→ A0 0x32/ACK
→ A0 0x50/ACK → NAV
→ A0 0x32/ACK → re-arm
```

Later contacts with nonzero IRQ0100 flags use the repeated/terminal path:

```text
A0 0x34/ACK
→ A0 0x36/ACK → IRQ 0x0100
→ A0 0x20/ACK → opaque auxiliary B0/TLS payload
→ A0 0x34/ACK → IRQ 0x0200
→ intermediate/retry: A0 0x32/ACK → re-arm
→ terminal: finish only after the template-stage decision and release are ready
```

Thus intermediate enrollment contacts do not enter the verify/identify STOP
path, and the terminal enrollment path does not invent a `0x50/NAV` tail. Stage
delivery in this ordinary path is deferred until the corresponding release
boundary is safe. The zero-mask alternative is described in
[Enrollment zero-mask recovery](#74-enrollment-zero-mask-recovery).

### 7.2 One acquisition per explicit verification attempt

Verify and identify perform one physical capture for each explicit client
action. The driver does not hide an automatic loop behind one `VerifyStart`.
A clean `NO_MATCH` may be followed by a new explicit action after full release,
STOP, drain, material reacquisition, and a fresh transport epoch.

A `MATCH` or processing error terminates the current claim's reusable series.
Errors after the transport becomes uncertain also poison the device context.
This conservative boundary prevents a stale secure session or queued byte from
being interpreted as a new authentication attempt.

### 7.3 Cancellation

Cancellation is a host-side terminal fence, not a claim that a specific
device-side cancel command exists. It:

- invalidates the action generation;
- stops accepting new completions;
- cancels host asynchronous transfers;
- waits for callbacks and backend work to drain; and
- marks the epoch non-reusable if clean quiescence is not demonstrated.

The next action uses teardown and reacquisition. Cancellation and suspend/resume
do not establish arbitrary on-device quiescence or recovery from every power-loss
state; a new action must still pass its receive and secure-session boundaries.

### 7.4 Enrollment zero-mask recovery

A repeated enrollment contact can produce a valid `control=0x36 / IRQ=0x0100 /
flags=0x0000` after its primary B0 image has arrived. The production driver has
an explicit `ZERO_MASK_RECOVERY` transition for this case. It is enabled only
for ENROLL and requires all of the following:

- the graph expects the repeated-contact IRQ0100, after the first contact;
- exactly one primary is held for the current contact;
- no OUT is pending and no previous zero window remains open;
- frame, control, checksum and 16-byte body are valid; and
- all six shifted raw words are in 1–254, as specified in section 6.4.

The primary is preserved and delivered at most once through ordinary
preprocessing, quality, diversity and SIGFM/template processing. Optional
image-choice `0x20`, auxiliary B0 and final auxiliary `0x34` are skipped. The
software finger-down state is cleared; a zero mask itself does not count as a
quality pass. An accepted sample advances at most one stage. Extraction/quality
failure keeps the existing terminal policy, while a diversity rejection can
produce the existing visible retry within the normal 20-contact bound.

For a nonterminal zero, the graph waits for the ordinary host next-sample
request. A new `0x32` requires completed host evaluation, libfprint awaiting a
finger, the A0 handler unwound, a valid local DOWN table, remaining contact
budget, free OUT ownership and no cancellation/error/terminal fence. Permission
is consumed once per transition. There is no timer-based permission, hidden
retry or separate extra-contact loop.

A terminal zero can finish enrollment without `0x32` or waiting for IRQ0200.
Errors, including OUT32 failure with IN still pending, notify the context and
follow its terminal fence, cancellation and drain path. Old-generation or
post-fence callbacks cannot change state. If strict recovery is unavailable,
an exact valid zero retains a typed unusable-contact diagnosis and terminal
GENERAL error without additional acquisition. Malformed frames and incompatible
states remain protocol errors.

#### Bounded late-release handling

After a nonterminal zero enters primary processing, a host stale-release window
remains open until the first valid IRQ0002 after actual `0x32` completion and
ACK32. Within this window, one exact `control=0x34 / IRQ=0x0200 / flags=0`, with
valid checksum, body and bounded raw words, is consumed as the previous contact's
release. This exception also applies while host processing or OUT32 is pending
and after ACK32. It changes no FDT, sample, stage, retry or contact callback and
sends no command. A second such release fails closed. IRQ0002 before effective
32/ACK and malformed or incompatible events fail closed.

The first valid new IRQ0002 closes this window. Subsequent IRQ0200 is handled
only by the ordinary graph and fails in an incompatible slot. There is no
proved contact/request identifier in the wire event: an old release arriving in
the new contact's ordinary release slot can be indistinguishable from a current
release and can be accepted as current. The boundary is a bounded host rule,
not a firmware barrier. A timeout, silent interval, drained host queue or fresh
software generation does not resolve this ambiguity. Cross-action firmware
release separation is likewise not proved by memory/ownership isolation.

The normal libfprint progress/completion callbacks carry the result to fprintd
and KDE. An accepted zero sample continues the same enrollment without a
synthetic retry or error-status substitution. The diagnostic fallback uses
terminal GENERAL: stock fprintd maps it to `enroll-unknown-error` rather than
forwarding the detailed driver message. A terminal retry would be misleading
for the examined KDE consumer, which treats retry status as a request for
another scan despite the completion flag. Driver-specific causes belong in
metadata diagnostics, not fabricated UI success.

## 8. Image decoding and preprocessing

An accepted image-class TLS application plaintext contains one packed sensor
image. Bounds are fixed and checked before allocation or conversion.

| Representation | Size or shape | Validation |
| --- | --- | --- |
| Packed samples | 7,680 bytes | Exactly 5,120 12-bit samples |
| Image record | 7,684 bytes | Exactly 7,680 packed bytes plus a strict 4-byte record CRC |
| TLS application plaintext | 7,693 bytes | Image class/control, declared length, additive/no-check policy, exact outer structure, and no trailing data |
| Canonical raster | 80 × 64 unsigned 16-bit samples | Values constrained to 12-bit range |
| SIGFM input | 80 × 64 unsigned 8-bit image | Produced by the active preprocessing chain |

The decoder unpacks paired 12-bit values and transposes the sensor's wire order
into the canonical 80 × 64 raster. The image-specific `0x88` no-check marker
permits omission of the additive image-payload checksum, but the record
CRC32/MPEG-2 is always verified. That exception must not be interpreted as
accepting an unchecked record.

### 8.1 Active preprocessing chain

Matching does not use a simple global 12-bit-to-8-bit scaling. It uses the
retained no-finger baseline and the current image:

```mermaid
flowchart LR
    TLS["Bounded TLS image record"]
    Decode["Length, class, checksum, CRC<br/>12-bit unpack and transpose"]
    U16["Canonical 80 × 64 u16 raster"]
    Base["Signed baseline correction<br/>+2048 working offset"]
    Flat["12-bit flat-field normalization<br/>radius 12"]
    Stretch["Percentile stretch<br/>1st to 99th"]
    Sharp["Unsharp enhancement<br/>boost 0.8, sigma 1.5"]
    U8["80 × 64 u8 SIGFM input"]
    Feature["SIFT feature extraction"]

    TLS --> Decode --> U16 --> Base --> Flat --> Stretch --> Sharp --> U8 --> Feature
```

The baseline correction preserves signed differences in a bounded 12-bit
working range. Local flat-field normalization compensates for spatial response;
the percentile stretch avoids allowing a small number of extremes to define the
entire contrast range; and the unsharp stage strengthens local ridge structure
before feature extraction.

Each fresh stock transport session obtains and validates its own FDT baseline.
For SIGFM normalization, however, the first decoded baseline in a
verify/identify series is pinned across clean rollovers in the same libfprint
open context. A rollover obtains a new session baseline for protocol preparation
but continues to normalize against that pinned reference. Enrollment sets and
pins its own initial baseline for all contacts in the action, replacing any
baseline used by its preceding duplicate check. The pinned raster is finally
cleansed when the device context closes.

Sensitive wrapper buffers such as retained baseline, frame, and candidate data
are explicitly cleared where implemented. Not every preprocessing temporary is
guaranteed to be overwritten before it is freed, and complete clearing of
internal allocations made by external libraries such as OpenCV cannot be
guaranteed.

## 9. SIGFM extraction, serialization, and matching

The active biometric implementation is SIGFM, using SIFT features through
OpenCV. It is not the stock NBIS minutiae pipeline.

### 9.1 Feature extraction

The extractor requires the exact 80 × 64, 8-bit input and accepts between 25
and 1,024 validated keypoints. Coordinates must lie inside the image and all
keypoint and descriptor values must be finite. The descriptor matrix must have
one 128-element floating-point row per keypoint.

OpenCV is used only for the bounded feature/matcher operations needed by SIGFM:
SIFT extraction, descriptor matching, and their `core`, `features2d`, `flann`,
and `imgproc` dependencies. USB, TLS, image decoding, baseline correction, and
the surrounding state machines do not depend on OpenCV algorithms.

### 9.2 Serialized sample envelope

Each accepted sample is serialized in a strict `GSF1` envelope. The envelope
contains a version, endianness marker, keypoint count, payload length, and CRC32
around the SIGFM payload. Deserialization rechecks:

- the exact header and supported version;
- integer bounds and total length;
- the 25–1,024 keypoint gate;
- image-coordinate and finite-value constraints;
- the expected descriptor matrix shape;
- CRC correctness; and
- canonical reserialization.

Malformed or non-canonical records are errors, not non-matches. Enrolled sample
envelopes are stored as sensitive libfprint print data, not as public interchange
files.

### 9.3 Matcher and cutoff

The matcher applies nearest-neighbour descriptor ratio filtering followed by
geometric-consistency scoring. Current constants include a `0.75` descriptor
ratio; at least five ratio-test descriptor hits are required before constructing
pairwise records, and at least five length-coherent angle records are required
before final scoring. Pairwise displacement-length and angular coherence each
uses a `0.05` tolerance. The current libfprint cutoff is a score of 40.

That cutoff is an implementation and target-functional threshold. It has **not**
been calibrated into a universal false-acceptance or false-rejection rate and
must not be presented as a security-strength measurement or generalized beyond
the supported reader/application scope.

## 10. Enrollment, verification, and identification

### 10.1 Action comparison

| Action | Candidate print set | Physical acquisitions | Terminal behavior |
| --- | --- | --- | --- |
| Enroll duplicate precheck | Existing prints in the user's gallery | One identify acquisition | Existing match stops as duplicate; clean no-match permits enrollment to begin |
| Enroll | New finger | Repeated explicit contacts, bounded at 20 | Completes with 4–8 stored samples or terminates with an error by the contact ceiling |
| Verify | One selected print | One per explicit action | Match, no-match, or processing error |
| Identify | A gallery of prints | One per explicit action | First score meeting cutoff, clean no-match after all samples, or error |

When fprintd verifies one known template it uses verify. When it verifies `any`
against multiple enrolled fingers, or checks enrollment for an existing print,
the driver advertises and uses identify.

### 10.2 Dynamic enrollment policy

Enrollment balances diversity with convergence rather than requiring exactly
eight stored contacts.

| Rule | Value |
| --- | --- |
| Minimum distinct samples before convergence can finish | 3 |
| Maximum distinct/stored samples | 8 |
| Consecutive duplicate-like contacts for convergence | 2 |
| Maximum physical contacts, including retries | 20 |
| Duplicate-like threshold | Mean absolute pixel difference below 8 on the 5,120-byte processed raster |

For every accepted-quality image, the processed raster is compared with all
distinct accepted rasters. A duplicate-like contact before convergence requests
a retry and is not silently stored. Once at least three distinct samples exist,
the second consecutive duplicate-like contact completes convergence and that
terminal image is retained. This gives a final template of 4–8 samples. Eight
distinct samples also complete enrollment.

The 20-contact ceiling includes duplicate retries and prevents an unbounded or
hidden capture loop. Exhaustion is a terminal error that fences the context, not
a reusable no-match. Allocation, preprocessing, extraction, or serialization
failure likewise terminates the action; it does not increment a stage behind
the user's back.

```mermaid
flowchart TD
    Contact["Physical contact"] --> Process["Capture and preprocess"]
    Process --> Compare{"Duplicate-like to an accepted raster?"}
    Compare -- No --> Add["Add distinct sample<br/>reset duplicate streak"]
    Add --> Eight{"8 distinct?"}
    Eight -- Yes --> Done8["Complete with 8 samples"]
    Eight -- No --> Limit{"20-contact ceiling reached?"}
    Compare -- Yes --> Enough{"At least 3 distinct and<br/>second consecutive duplicate?"}
    Enough -- Yes --> AddFinal["Retain terminal sample<br/>complete with 4–8 samples"]
    Enough -- No --> Limit
    Limit -- No --> More
    Limit -- Yes --> Fail["Enrollment exhausted"]
    More --> Contact
```

The structural libfprint SIGFM container permits up to 21 sample envelopes, but
the active enrollment policy stores only 4–8. Container capacity does not change
the enrollment rule.

### 10.3 Match outcomes and retry ownership

The driver reports a biometric `MATCH`, clean `NO_MATCH`, or processing/device
error. It does not reinterpret a parser, TLS, template, or allocation failure as
a wrong finger.

Retry policy belongs to the client stack. In the installed Plasma Login PAM
entry, stock `pam_fprintd` is configured with `max-tries=3 timeout=30`. A clean
no-match may let PAM request another explicit attempt. An untouched-reader
timeout ends that PAM call with authentication information unavailable; it
should not be described as three automatic consecutive 30-second waits.

## 11. Templates, storage, and multi-user behavior

Protected reader material and biometric templates are different data classes:

| Data | Scope | Owner | Location | Removed by project removal? |
| --- | --- | --- | --- | --- |
| Reader material | System-wide, target-bound | Project runtime/root | `/var/lib/goodix-5125-poc/` | No |
| State-v2 pairing state | System-wide, target-bound | Project runtime/root | `/var/lib/fprint/goodix-5125-state-v2/` | No |
| Biometric template | Per local username/finger | Fedora `fprintd` | `/var/lib/fprint/` | No |
| Raw image | One in-memory action | Driver process | Not intentionally persisted | Not applicable |

fprintd stores an FP3 print containing metadata and one or more `GSF1` SIGFM
sample envelopes. The storage hierarchy is conceptually:

```text
/var/lib/fprint/<username>/<driver>/<device-id>/<finger-hex>
```

For this implementation the driver name is `goodix_27c6_5125`; the current
device identifier is `0`. fprintd checks driver/device compatibility when loading
a print. The final path component is fprintd's hexadecimal identifier for one of
the standard ten finger positions. The driver does not store templates on the
reader.

fprintd resolves the D-Bus caller's UID through the system account database.
Normal operations target that caller's username; acting on another username is
subject to fprintd/PolicyKit authorization. New local accounts do not require a
driver reinstall: their storage appears lazily when they enroll.

The project does not install an account-deletion hook. Renaming or deleting a
username does not automatically migrate or erase its template directory, and a
later reuse of the same username can encounter retained biometric state. Remove
enrollments through KDE or fprintd before deleting or renaming an account when
cleanup is required.

## 12. fprintd integration

Fedora's stock `fprintd` remains the system authority for fingerprint clients.
It is normally D-Bus activated, serializes ownership through its device claim,
maps clients to users, starts libfprint actions, reports status to PAM/KDE, and
stores the resulting templates.

The service unit remains Fedora-owned and its `ExecStart` remains
`/usr/libexec/fprintd`. The project installs only:

```text
/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf
```

with the private library directory in `LD_LIBRARY_PATH`. The installer rejects
an unrecognized local service drop-in, an incompatible effective executable,
`LD_PRELOAD`, or a conflicting library environment rather than composing with
unknown authentication code. Fedora-packaged drop-ins under `/usr/lib` remain
eligible when the resulting service still satisfies those checks.

### 12.1 Claim and action lifetime

One D-Bus client claims a device before beginning an action. The driver can
perform clean explicit action rollovers inside a claim, notably:

- a no-match identify duplicate check followed by enrollment; and
- a clean no-match followed by another explicit verify/identify request.

Every rollover still performs full release/STOP/drain and establishes fresh
action resources. A match, processing error, cancellation with uncertain state,
or transport error ends that reusable series.

### 12.2 Preparation latency

The device is not prepared during libfprint open and stock fprintd does not
prepare it before PAM starts a biometric action. The secure bootstrap, TLS, FDT,
and baseline work therefore occurs after the user selects fingerprint. Allow
roughly one second for preparation before placing the finger in Plasma Login;
this is a startup allowance, not a fixed protocol timing guarantee.

Removing that interval would require a consumer/daemon design that prepares the
reader earlier and safely transfers ownership of the prepared state. The current
release deliberately keeps stock fprintd and accepts the bounded startup cost.

The compiled driver contains a private prepared-login interface that can create
TLS/FDT/baseline state before an authentication action, attach the first verify
or identify action to it, and retain a clean drained session for at most three
explicit no-match attempts. Stock fprintd and the Fedora greeter do not call
that interface, so it is not part of the installed consumer path or current
qualification.

## 13. Authentication consumers

| Consumer | Integration | How fingerprint is selected | Password boundary |
| --- | --- | --- | --- |
| Plasma Login | Project PAM selector plus stock `pam_fprintd` | Submit an empty password field explicitly | A nonempty password immediately enters Fedora's vendor PAM chain |
| KScreenLocker | Stock Fedora PAM/authselect path | Current Fedora policy/UI | Password remains available |
| Ordinary sudo | Stock Fedora PAM/authselect path | May offer fingerprint before password | Untouched reader normally times out to password in about 30 seconds |
| PolicyKit/KDE agent | Stock Fedora PAM/authselect path | Current Fedora policy/UI | Password remains available |

### 13.1 Plasma Login selector

The supported Fedora Plasma Login stack is password-oriented, so the project owns a
small prefix at `/etc/pam.d/plasmalogin` and a module at
`/usr/local/lib64/goodix-plasma-login/pam_goodix_login_gate.so`.

```mermaid
flowchart TD
    Submit["Plasma Login submission"] --> Token{"Password field empty?"}
    Token -- No --> Reset["Reset project prefix state"]
    Token -- Yes --> Shape{"Current vendor PAM shape<br/>passes strict compatibility check?"}
    Shape -- No --> Reset
    Shape -- Yes --> SELinux["pam_selinux_permit.so"]
    SELinux -- PAM_IGNORE --> Finger["Stock pam_fprintd<br/>max-tries=3, timeout=30"]
    SELinux -- Any other result --> Reset
    Finger -- Match --> Account["Current Fedora account/session processing"]
    Finger -- No match, timeout, or error --> Reset
    Reset --> Vendor["Include current Fedora<br/>/usr/lib/pam.d/plasmalogin"]
    Vendor --> Password["Normal Fedora password result"]
```

The gate only selects a path. It never authenticates, opens the reader, spawns a
helper, copies a password, or persists/logs a password. Fingerprint routing is
enabled only if the installed Fedora vendor file and its included authentication
files have the expected compatible shape. On a future incompatible layout, the
gate fails safe to Fedora's password path. A failed fingerprint attempt grants
nothing; PAM continues through the current Fedora authentication include with
the token supplied by the greeter.

The prefix also calls `pam_selinux_permit.so`. Only its `PAM_IGNORE` result
continues to `pam_fprintd`; any other result skips fingerprint, resets the
project prefix state, and delegates to the current Fedora authentication stack.
The reset step never grants authentication.

Account, password, and session processing always include the current Fedora
vendor file. No frozen vendor PAM copy is installed. Removal deletes the
project-owned service file first, exposing Fedora's current configuration.

### 13.2 KScreenLocker, sudo, and PolicyKit

No project-specific configuration is installed for these consumers. They use
fingerprint only when the host's current Fedora authentication policy enables
`pam_fprintd`; the installer does not change authselect or global PAM files.

The supported Fedora configuration uses authselect `with-fingerprint` for
KScreenLocker, ordinary sudo and the KDE PolicyKit agent. Other sudo variants or
PolicyKit action/agent combinations are outside the stated support scope.
Password-encrypted KWallet is independent and may still ask for a password after
fingerprint login.

## 14. SELinux and host integration

SELinux remains Enforcing. The installation has two narrow SELinux effects:

| Effect | Purpose | Security boundary |
| --- | --- | --- |
| Exact local file-context mapping for `/var/lib/goodix-5125-poc(/.*)?` | Let `fprintd_t` read validated protected material with the Fedora `fprintd_var_lib_t` type | Ownership is recorded; unrelated mappings are not changed |
| Installer-generated priority-400 module `goodix_5125_hugepage` | Suppress the known denied oneTBB read probe of `nr_hugepages` | `dontaudit` only; grants no read permission |

The module generated by this installer contains the narrow
type/class/permission relationship
`fprintd_t -> sysctl_vm_t:file read`. It exists because the bundled OpenCV path
can cause oneTBB to probe `/proc/sys/vm/nr_hugepages`; denial is non-fatal but
otherwise creates a known audit event.

Module lifecycle identification uses the exact name and priority reported by
`semodule`. A single pre-existing entry named `goodix_5125_hugepage` at priority
400 is treated as this module without inspecting its content, and removal later
deletes that identity. Such a name/priority collision is not part of the clean
qualified baseline and should be resolved before installation.

Because SELinux policy is type-based, the suppression can also hide a different
denied read with the same source type, target type, class, and permission. The
absence of that AVC is therefore not proof that no such access was attempted.
The rule still grants no access. Both normal and emergency removal delete the
project module and restore Fedora's normal audit visibility.

The systemd service drop-in does **not** hide the sysctl path or weaken the
service sandbox. Its only current setting is the private runtime
`LD_LIBRARY_PATH`.

## 15. Build and runtime dependencies

### 15.1 Fedora packages

| Purpose | Packages |
| --- | --- |
| Bootstrap | `git`, `python3` |
| Build toolchain | `gcc`, `gcc-c++`, `meson`, `ninja-build`, `pkgconf-pkg-config`, `binutils` |
| Development headers | `glib2-devel`, `libgusb-devel`, `openssl-devel`, `opencv-devel`, `pam-devel` |
| Runtime/integration | `fprintd`, `fprintd-pam`, `policycoreutils-python-utils` |

The builder runs as the invoking unprivileged user and requires Fedora 44
x86_64. It constructs a source inventory by content, so a source-only copy does
not depend on Git history. It builds the Goodix-enabled libfprint, selector, and
native material checker; verifies ABI and stock-fprintd symbol resolution;
performs validation checks; and records relevant package versions and source
digests.

### 15.2 Private and system libraries

The private runtime contains the built libfprint and only the resolved Fedora
OpenCV SONAME files for `core`, `features2d`, `flann`, and `imgproc`, with the
links and notices needed by the build. A restricted OpenCV package description
prevents unrelated modules from entering the link closure.

Fedora's `libgusb`, OpenSSL, GLib, PAM, and remaining system libraries continue
to resolve from system locations. The build verifies that `/usr/libexec/fprintd`
loads the intended private libfprint without unresolved symbols and that
non-production helper symbols are not exported.

The installed source/provenance records are content and package evidence, not a
claim of a byte-reproducible build or an exhaustive software bill of materials.

## 16. Installation, update, and rollback

`install.sh` is the public entry point. It must be run by a normal user, resolves
its own source directory, and invokes the build/install orchestrator. A read-only
privileged material preflight precedes package installation. The build runs as the
normal user, then a privileged apply phase revalidates material and replaces the
project-owned integration. Protected bytes never enter the clone or build output;
installed material is never copied back to Home. The package-manager step also
uses sudo to install Fedora prerequisites.

```mermaid
flowchart TD
    Material["Privileged read-only material selection"] --> Packages["Fedora prerequisites"]
    Packages --> Build["Normal-user source build<br/>and validation checks"]
    Build --> Preflight["Privileged host and authentication preflight"]
    Preflight --> Existing["Validate selected material again;<br/>native binding check for installed set"]
    Existing --> Lock["Exclusive lifecycle lock"]
    Lock --> Quiet["Temporarily inhibit and quiesce fprintd"]
    Quiet --> Recheck["Recheck material and software state"]
    Recheck --> Snapshot["Snapshot project-owned integration"]
    Snapshot --> Replace["If present, remove an existing<br/>valid project installation"]
    Replace --> Recovery["Install recovery tools<br/>and SELinux module"]
    Recovery --> Native["Preserve installed set, or import new<br/>material with native binding check"]
    Native --> Deploy["Labels, runtime, selector,<br/>PAM entry last"]
    Deploy --> Verify["Verify receipts and stopped service"]
    Verify --> ReleaseSuccess["Restore verified<br/>activation-mask state"]
    ReleaseSuccess -- Success --> Done["Installation complete<br/>fprintd remains stopped"]
    ReleaseSuccess -- Failure --> Cleanup["Final cleanup incomplete<br/>installed state may remain; recovery retained"]
    Replace -- Body failure --> Rollback["Restore prior project state<br/>or report incomplete rollback"]
    Recovery -- Body failure --> Rollback
    Native -- Body failure --> Rollback
    Deploy -- Body failure --> Rollback
    Verify -- Body failure --> Rollback
    Rollback --> ReleaseFailure["Restore verified<br/>activation-mask state"]
    ReleaseFailure -- Success --> Failed["Installation failed"]
    ReleaseFailure -- Failure --> Cleanup
```

### 16.1 Preflight

Before project-owned integration mutation, the installer requires:

- Fedora 44 on x86_64 with SELinux Enforcing;
- a trusted, package-owned Fedora Plasma Login PAM file;
- the stock fprintd unit and `/usr/libexec/fprintd` executable;
- no unrecognized local fprintd drop-in or preload; and
- either no project library setting or exactly the expected project setting.

Material-source precedence is fixed:

1. Any existing `/var/lib/goodix-5125-poc/` must pass installed-set validation:
   root:root ownership, exact `0700`/`0600` permissions, directory/regular-file
   types without links, exactly five files, manifest, hashes and cross-file bindings.
   Valid installed material takes precedence over the default Home bundle, which
   is not read. Missing files, corruption or metadata drift cause STOP without fallback.
2. Only when installed legacy material and project software are absent does the
   installer validate the normal user's `~/goodix-5125-materials/` (or explicit
   `--materials`).
3. If neither material source exists on a first install, the installer creates
   `/var/lib/fprint/goodix-5125-state-v2/` as root-owned mode `0700` and records a
   state-v2-only runtime. It does not open USB or initialize pairing. An older
   installed runtime whose receipt still requires missing legacy material stops
   for review; a state-v2-only runtime updates without a bundle.

The preliminary privileged check is read-only and repeats at apply time. A
root-owned copy of the built native checker validates an installed set's E4
binding without opening USB before the lifecycle transaction. The same bytes and
metadata are revalidated under the lock before replacement. For first import,
native validation runs on private root-owned staging inside the transaction before
atomic publication; failure rolls back the software transaction. No installed set
is recreated from a stale snapshot if it disappears during preparation.

`--check` remains unprivileged and does not request sudo or install packages.
When installed material exists, its output explicitly defers protected-content
validation to the privileged phase; it does not claim that set is valid.
The PAM selector
separately checks the exact vendor, `password-auth`, and `postlogin` shapes at
authentication time before it enables the fingerprint path.

### 16.2 Quiescence and activation inhibition

Install, update, and removal take an exclusive lifecycle lock. They temporarily
mask fprintd through a verified `/run/systemd/system/fprintd.service` link, reload
systemd, stop the service, and require all of these before replacing runtime
code:

```text
ActiveState=inactive
MainPID=0
LoadState=masked
```

A mask that predates the operation is preserved. A temporary mask created by the
operation is removed only after its inode and target still prove ownership.
Unknown ownership is retained and reported rather than deleted by assumption.

The integrated reader remains connected. Lifecycle tools do not enumerate it,
open USB, send commands, initiate capture, or start any post-install biometric
action. Stopping an already active daemon may allow that daemon to perform its
normal cleanup.

### 16.3 Installed paths

| Path | Owner and purpose |
| --- | --- |
| `/usr/local/lib64/goodix-27c6-5125/` | Private libfprint/OpenCV runtime, links, notices, and receipts |
| `/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf` | Private runtime environment for stock fprintd |
| `/var/lib/goodix-5125-poc/` | Preserved root-only protected reader material |
| `/var/lib/fprint/goodix-5125-state-v2/` | Preserved root-only crash-safe pairing state |
| `/usr/local/lib64/goodix-plasma-login/` | PAM selector module and metadata |
| `/etc/pam.d/plasmalogin` | Project-owned opt-in prefix and includes of current Fedora PAM |
| `/usr/local/bin/goodix-uninstall` | Receipt-validating normal removal |
| `/usr/local/bin/goodix-force-remove` | Fixed-inventory emergency removal |
| `/usr/local/share/goodix-recovery/` | Recovery receipt and metadata |

Recovery commands are installed before riskier authentication integration. The
Plasma PAM entry is installed last, after runtime and removal paths are ready.
Successful installation leaves fprintd stopped; the next normal consumer causes
Fedora to activate it.

### 16.4 Update and material retention

The single documented bootstrap fast-forwards an existing clone or clones it
again when absent, then runs the same installer. The installer reports
`GOODIX_INSTALL_MODE` automatically:

| Valid material source | Project software | Mode |
| --- | --- | --- |
| Installed set | Present and passing software preflight | `UPDATE` |
| Installed set | Absent, including after normal or emergency removal | `REINSTALL` |
| Home or explicit bundle; installed set absent | Absent | `FIRST_INSTALL` |
| No legacy bundle; state-v2 prepared or initially empty | Absent | `FIRST_INSTALL` |

A valid existing installation is removed and replaced transactionally while
fprintd is quiescent. Existing templates are never part of replacement. The
installed material retains its bytes and file paths; default Home material is
ignored even if different. An explicit `--materials` bundle must validate and
match the installed set byte-for-byte, or the operation stops. There is no implicit
reader/bundle replacement.

The repository clone may be removed after successful installation; runtime and
removal commands are independent of it. The Home staging copy is not technically
required for ordinary updates or reinstalls with valid installed material.
State-v2-only updates and reinstalls preserve their state directory. A separate
secure backup remains necessary while the legacy compatibility source is used.

### 16.5 Rollback boundary

Before replacement, the installer snapshots project-owned software and records
the material-label state and whether the SELinux module was already present. On
a failure inside the replacement body it attempts to restore the previous
project runtime, integration, labels, and prior module presence. Recovery tools
are retained where possible if rollback is incomplete.

Releasing the temporary activation mask is the final lifecycle step. A failure
there occurs outside the replacement body's rollback handler: it reports final
cleanup as incomplete and retains recovery commands, even if project software
was already installed. That outcome is not an installation success.

Rollback is not a host snapshot. It does not remove Fedora packages installed
earlier by the package manager, undo unrelated host changes, or delete newly
imported protected material. A missing final success marker or an
`incomplete rollback` result is failure and requires recovery.

## 17. Removal and emergency recovery

Two standalone commands are installed because the safe choice depends on the
integrity of the project installation.

| Property | `goodix-uninstall` | `goodix-force-remove` |
| --- | --- | --- |
| Intended use | Healthy installation from a working desktop | Partial, damaged, or login-blocking project state |
| Receipts and hashes | Required and validated | Not required |
| Inventory | Recorded project ownership, links, and expected files | Fixed narrow list of project paths |
| Missing/partial files | Refuses unexplained drift | Tolerates absence and continues safely |
| Clone/build directory needed | No | No |
| Fedora vendor PAM shape needed | No | No |
| Data preservation | Material and templates preserved | Material and templates preserved |

Both use the same safety order:

1. remove the project Plasma Login entry;
2. remove the fprintd runtime drop-in and reload service configuration;
3. inhibit activation and prove fprintd quiescent;
4. remove the project SELinux module;
5. remove the selector and owned material-label effect;
6. remove the private runtime only when quiescence is proven; and
7. remove recovery commands last, only after complete success.

If activation inhibition or service quiescence cannot be proven, the private
fprintd runtime that an old daemon might still have loaded is retained and the
operation reports failure. Material labels are likewise not changed under an
uncertain live runtime. A pre-existing service mask is never claimed as
project-owned.

Both commands preserve:

- `/var/lib/goodix-5125-poc/` and all five material files;
- `/var/lib/fprint/` and enrolled templates;
- staging files and the public clone;
- firmware, existing keys, and persistent reader state.

The owned material file-context mapping can be removed and current Fedora labels
reapplied without reading or changing file contents. Restart after successful
removal so no old login or authentication process retains project code.
Normal removal preserves a compatible mapping recorded as pre-existing;
emergency removal deletes only the exact known project mapping and leaves
unrelated SELinux rules untouched.

Removal exposes the current Fedora configuration. It does not replay a saved PAM
snapshot or repair an independently broken password stack. Emergency use still
requires a working console and administrative password; follow
[Uninstall and emergency recovery](docs/UNINSTALL.md) exactly.

## 18. Factory preservation, security, and privacy

### 18.1 Factory-preserving command boundary

Supported operation uses only allowlisted reads and commands treated by the
implementation as session/runtime operations needed for initialization and
capture. It excludes:

- firmware flashing or in-application programming;
- application clearing or replacement;
- OTP or factory-data writes;
- PSK generation, replacement, or provisioning;
- persistent VID:PID or mode changes; and
- unknown command families used as speculative recovery.

Failure at an unknown phase stops the action. The driver does not try arbitrary
reset/write sequences in the hope of recovering.

This is a code and protocol design property, not proof from an exhaustive
factory-state readback. Successful Linux use does not establish universal
Windows interoperability or absolute non-mutation under every device failure.

### 18.2 Secret and biometric handling

Protected material is outside the repository, imported root-only, and never
printed by the normal tools. The OEM DLL is parsed for bounded compatibility
data and is never loaded as executable code. Selected project buffers—including
the PSK/material transfer buffers and specific normalization wrapper buffers—are
explicitly cleared at their lifetime boundary. This is not a claim that every
project-owned image or feature allocation is overwritten before release.

Raw images are processed in memory and are not intentionally persisted.
Templates are sensitive derivative biometric data stored by fprintd; they are
not reversible promises of anonymity and must be protected and deleted through
normal biometric management when no longer needed.

The project cannot guarantee erasure of copies made inside third-party library
allocators, kernel buffers, crash dumps, or external diagnostic tooling. Do not
enable indiscriminate debug capture on a production account.

Normal-level journal messages can contain biometric-derived metadata such as
keypoint counts and per-template-sample match scores/outcomes. They do not
intentionally contain raw images or serialized templates, but journal exports
should still be treated as sensitive and redacted to the minimum needed for a
report.

### 18.3 Authentication safety boundary

A fingerprint result is only one input to Fedora authentication policy. The
driver never grants a login itself. PAM account/session checks, D-Bus/PolicyKit
authorization, and password recovery remain Fedora responsibilities.

Password access must be kept working before installation and during updates.
The selector is designed so a nonempty Plasma Login password reaches Fedora's
current vendor path without a forced fingerprint wait. Other consumers can
offer fingerprint first according to stock Fedora policy, so an untouched
reader may have to time out before password entry.

See [Security and privacy](docs/SECURITY.md) for reporting rules and the concise
threat boundary.

## 19. Qualification and known limitations

| Limitation | Consequence |
| --- | --- |
| One reader/application and Fedora target | No compatibility claim for other Goodix devices, firmware, distributions, desktops, architectures, or multiple readers |
| Local-account qualification only | Network/LDAP/AD account behavior is not established |
| No FAR/FRR study | Score 40 is not a universal biometric security calibration |
| Unknown physical DPI/orientation/polarity | Do not label captures 500 DPI or promise a natural-facing or calibrated-polarity raster |
| Device material is user-supplied | The Windows Material Builder creates the bundle inside the reader's qualified Windows VM using USB passthrough, the qualified OEM driver and the original Windows user/DPAPI context; native or bare-metal Windows acquisition and cross-reader interchangeability are outside the qualified scope, and a different installed/staged bundle is not silently swapped |
| Secure preparation starts with the action | Allow roughly one second after Plasma fingerprint selection before contact |
| Stock policy controls most consumers | Altered authselect/PAM may not offer fingerprints; the installer does not rewrite global policy |
| PAM layout evolves | Future Fedora changes may cause the Plasma selector to fall back to password until reviewed |
| KWallet is separate | A password-encrypted wallet may prompt after fingerprint login |
| Account cleanup is not automated | Username rename/delete/reuse requires deliberate template management |
| Hotplug and physical removal | Disconnect/reconnect during an action or lifecycle operation is not qualified |
| Concurrency beyond stock serialization | Competing low-level clients or bypass of fprintd's claim model is not qualified |
| Late IRQ0200 after zero-mask recovery | One release before the valid new IRQ2 is consumed passively; same-byte stale/current release in a later compatible slot is not distinguishable (section 7.4) |
| Fault/stale-traffic boundary | Process crashes, injected faults, and exhaustive late-byte or cross-generation behavior are outside the qualified scope |
| SELinux audit suppression is type-based | The known denied read tuple can be hidden even when caused by a future process path |
| Factory/Windows boundary | No exhaustive factory-state readback or guarantee across Windows interoperability, power-loss scenarios, or future OS updates |

See [Validation scope and known limitations](docs/VALIDATION.md) for the release
support basis. The protocol limits in this manual apply independently of a
successful installation or authentication attempt.

## 20. Troubleshooting and diagnostic principles

Diagnose by ownership layer. A successful build does not prove USB; a successful
USB action does not prove PAM; and a working password does not prove biometric
matching.

| Symptom | First boundary to inspect | Safe evidence |
| --- | --- | --- |
| Reader absent | USB identity/hardware | `lsusb -d 27c6:5125` (from `usbutils`) and non-secret kernel messages |
| Service fails before opening reader | Runtime linking/systemd | `systemctl status fprintd`, service journal, exact loader error |
| Material rejected | Staging/import contract | Exact validator error and file metadata, never file contents |
| TLS/bootstrap failure | Target binding or protocol phase | Exact phase/error name with protected bytes redacted |
| Capture but processing error | Image bounds/preprocessing/template parser | Error class and action, never image/template data |
| Enrollment A0 mismatch after accepted contacts | Expected enrollment event and contextual FDT flags | Exact mismatch, contact/stage counters and cleanup state; see section 20.3 |
| Clean no-match | Biometric result | Authentication-attempt context and enrolled finger label; do not recast as transport failure |
| Plasma password works, fingerprint path does not | Empty-field selection, PAM compatibility, preparation timing | Whether input was empty and the first non-secret PAM/fprintd error |
| Other consumers omit fingerprint | Fedora authselect/PAM policy | Current host policy; no manual project workaround |
| Removal refuses drift | Receipt/ownership protection | Use the exact reported path; choose documented emergency removal only when needed |

### 20.1 Safe operating rules

- Stop at the first meaningful error and preserve its exact non-secret text.
- Treat a missing final success marker or an incomplete rollback as failure.
- Do not disable SELinux, bypass a preflight check, hide/disconnect the reader,
  edit Fedora PAM manually, or delete material/templates as a diagnostic shortcut.
- Do not run KDE enrollment, `fprintd-enroll`, and verification clients
  concurrently; fprintd intentionally serializes its device claim.
- After a cancellation or transport error, allow fprintd to close/reopen the
  device instead of issuing USB resets or replaying commands manually.
- Use `goodix-uninstall` for intact state and `goodix-force-remove` for a partial
  or damaged project installation.
- Keep the reader connected and a working password available throughout install
  and removal.

### 20.2 What to report

Include the Fedora version, kernel version, USB identity, reader application if
known, project revision, exact command or consumer, action being performed,
first non-secret error, and whether password/desktop access still works.

Do **not** share the material directory, manifest, transport material, OEM DLL,
FDT cache, configuration payload, raw USB captures, fingerprint images,
templates, core dumps containing them, or unredacted secret-bearing logs.

### 20.3 A0 and enrollment recovery diagnostics

Enrollment mismatch diagnostics identify the expected event, observed control,
classified IRQ/flags and contextual flag policy, with contact/stage counts.
`pending_primary` is an accounting indicator: observed primary samples exceed
completed plus retry stages. It is not direct buffer inspection. At the repeated
IRQ0100 slot it identifies a primary not yet delivered; earlier keypoint counts
describe earlier samples and do not establish this sample's quality.

The `unexpected post-TLS A0 frame or state` error instead reports the
preparation/capture phase, expected event, control, body length, classified
IRQ/flags, ACK state, FDT reading count, baseline readiness and rejection.
Only `0x32`, `0x34` and `0x36` with exact IRQ body shape are classified as IRQs;
opaque AE controller-state bytes are not printed as IRQ data. A zero bootstrap
mask can still fail material or delta checks. Without phase and rejected-frame
metadata, a generic A0 error does not establish a common cause across these paths.

`GOODIX_ZERO_MASK_RECOVERY` records primary preservation, omitted optional
commands, re-arm and passive late-release counts. Its closed-record totals are
cumulative within the action and must be correlated with individual sample
records. The general epoch audit's `enroll_rearm32` also includes ordinary
contacts, whereas `rejected` counts rejected actions, not frames or poor images.
`enroll_contacts`, `enroll_stages` and `enroll_retry_scans` count acquired primary
images, completed stages and retry stages respectively. After client Release,
`outstanding=0`, `drained=1`, `context_closed=1` and `persistent=0` report host
cleanup and command-family accounting. These records contain no raw FDT/image/
template/material bytes and are not an independent USB trace or exhaustive
factory-state readback.

## 21. Developer invariants, licensing, and references

### 21.1 Invariants for changes

A change to the driver, builder, or integration should preserve all of these
boundaries unless it explicitly redesigns and requalifies them:

1. exact USB/application targeting and fail-closed material binding;
2. no firmware, OTP, key, factory-data, or persistent-mode writes;
3. one owner for bulk-IN routing and strict A0/B0 phase validation;
4. TLS 1.2 PSK with reader as client and host as server;
5. bounded 80 × 64 image parsing with record CRC verification;
6. baseline-aware active preprocessing before SIGFM;
7. strict `GSF1` parsing and sensitive template handling;
8. one acquisition per explicit verify/identify action;
9. bounded 4–8-sample enrollment and 20-contact ceiling;
10. release/STOP/drain before clean reuse, with poison on uncertainty;
11. stock fprintd/PAM/KDE ownership and working password fallback;
12. service quiescence before runtime replacement or removal;
13. preservation of protected material and fprintd templates; and
14. no expansion of qualification claims without matching evidence.

Changes must preserve the invariants above and remain within the qualification
boundary defined in [Validation scope and known limitations](docs/VALIDATION.md).
Expanding that boundary requires corresponding technical evidence.

### 21.2 Licensing and provenance

Licensing is per file. The combined Goodix-enabled libfprint is conveyed under
GPL-3.0-or-later because it combines components with compatible but distinct
licenses, including GPL-2.0-or-later preprocessing and Apache-2.0-linked code.
Individual source files retain their own SPDX declarations.

The SIGFM implementation is derived from the documented Rockytkg fork; the
preprocessing/diversity work records its upstream adaptation point. Fedora's
libfprint 1.94.100 source and package provenance are retained in the public
reference tree. The builder installs source-content digests, Fedora package
versions, OpenCV notices, and license texts needed to review the produced
runtime. These records do not claim a complete SBOM.

Use these public references for further detail:

- [Installation](docs/INSTALLATION.md)
- [Removal and emergency recovery](docs/UNINSTALL.md)
- [Security and privacy](docs/SECURITY.md)
- [Validation and limitations](docs/VALIDATION.md)
- [Protected device-material contract](docs/DEVICE_MATERIALS.md)
- [Licensing and provenance](docs/LICENSING_AND_PROVENANCE.md)
- [External references](docs/REFERENCES.md)
- [Build and validation checks](production/README.md)
- [Driver source overview](libfprint-driver/README.md)
- [Learning guide](docs/learning/README.md)

The source itself remains the final authority for exact parser bounds and state
transitions. When this manual and the current implementation differ, treat that
as a documentation defect to resolve—not permission to weaken a runtime check.
