<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Glossary

## A0 / B0 message classes

Two outer message types used by this Goodix protocol. `A0` carries checked
control commands, acknowledgements, typed replies, and events. `B0` wraps TLS
records, including the protected baseline and image data after the handshake.

## ACK

Short for acknowledgement: a device reply confirming that it accepted a
command at the protocol level. An ACK is not automatically proof that every
later result is correct; some phases also require a separate typed reply.

## Authentication

The process of checking that someone is allowed to act as a particular user.
A password or fingerprint can provide evidence to that process.

## Asynchronous operation

Work that starts now and finishes later. USB transfers and fingerprint image
processing are asynchronous, so completion is reported through callbacks
instead of making the whole desktop wait in one blocked function.

## Baseline

A reference measurement. This driver records a no-finger baseline so later
sensor readings and images can be interpreted relative to the empty sensor.

## Biometric template

A saved, machine-readable representation of biometric features. In this
project, a template contains SIGFM feature samples and metadata; it is not just
a normal fingerprint photograph.

## Binary file

A file whose bytes represent structured data rather than ordinary text. A
protected binary record must not be opened and saved through a text editor or
converted to a string of hexadecimal characters.

## Callback

A function arranged to run when an asynchronous event finishes, such as a USB
transfer completing or image processing returning a result.

## Claim

Temporary exclusive use of the fingerprint device by one `fprintd` client.
Claiming prevents unrelated clients from mixing operations on the same reader.

## Command value / opcode

A numeric label that tells a device which operation or message is being used.
This guide calls values such as `0xA8` Goodix command values. "Opcode" is the
common shorter term.

## Daemon

A background service. `fprintd` is a daemon that waits for fingerprint requests
from other parts of Linux.

## CRC

Cyclic redundancy check: an arithmetic check that helps detect corrupted
bytes. The image record and the serialized sample envelope use CRC-32/MPEG-2;
other CRC-32 variants do not necessarily produce the same result. A valid CRC
is not proof of origin.

## D-Bus

A structured inter-process messaging system. It acts like an operating-system
intercom between clients and services such as `fprintd`.

## DAC

Digital-to-analog converter. The current driver labels four runtime register
phases as DAC tuning steps. Think of them as four electronic adjustment values;
the guide does not claim an exact physical meaning for each value.

## Descriptor

Numbers describing the pattern around a feature point. SIGFM compares these
descriptors rather than requiring two fingerprint images to be pixel-for-pixel
identical.

## Driver

Software that knows how to operate particular hardware. The Goodix driver
translates `libfprint` actions into the protocol used by USB `27c6:5125`.

## Endpoint

A numbered USB communication channel. For the qualified Goodix bulk traffic,
`0x01` carries host-to-reader data and `0x81` carries reader-to-host data.

## Enrollment

The process of collecting several useful views of one finger and saving their
feature representations as a template.

## Factory state

Persistent information and configuration originally associated with the
reader, including firmware and secure setup. The supported project path is
designed to preserve it.

## Feature / keypoint

A locally distinctive part of a processed fingerprint image used by the
matcher. The current SIGFM path stores keypoints and descriptors.

## Finger detection (FDT)

The lightweight sensor process used to notice that a finger has arrived or
left. It is separate from capturing the full fingerprint image.

## Firmware

Software stored inside a hardware device. The target reader reports
`GF_ST411SEC_APP_12509`; the supported path does not replace it.

## `fprintd`

Fedora's fingerprint background service. It exposes operations over D-Bus,
manages clients and permissions, calls `libfprint`, and stores host templates.

## Hash / cryptographic digest / SHA-256

A compact data fingerprint calculated from some bytes. The driver compares a
calculated digest with an expected one to detect missing, changed, or
reader-mismatched material without treating the digest as the secret itself.
SHA-256 produces 32 bytes, commonly written as 64 hexadecimal characters.
Per-reader digests can still be private evidence; compare them locally.

## Host

The main computer running Linux, as opposed to the fingerprint sensor itself.

## Host pairing

The single bounded write through which Linux registers its own locally generated
key with the reader, while leaving the reader's existing factory and Windows
pairing records untouched. It happens at most once per key generation, is never
retried automatically, and is proven by readback and an encrypted handshake
before the key is used.

## Host pairing state

The crash-safe root-only host directory, `/var/lib/fprint/goodix-5125-state-v2/`,
that holds the Linux PSK and its authenticated pairing receipts. It keeps two
generations so an interrupted operation can be reconciled by reading, never by
guessing or by writing to the reader a second time. Project removal preserves it.

## Hexadecimal / hex / `0x`

A way to write numbers using digits `0`–`9` and letters `A`–`F`. The prefix
`0x` marks hexadecimal notation, so `A8` and `0xA8` name the same numeric value.

## Interrupt / IRQ

A message from hardware that an event occurred. A validated Goodix finger-down
IRQ tells the driver to move from waiting to image capture.

## `libfprint`

The Linux fingerprint library that supplies common device behavior, drivers,
image processing hooks, template handling, and matching. This project builds a
Goodix-enabled version for `fprintd` to load.

## Little-endian

A byte order in which a number's least significant byte comes first. For
example, the two-byte number `0x1234` is stored as `34 12`. It describes
binary storage order, not how to spell a number in JSON.

## Live preflight

A bounded read-only check the driver runs before it relies on any pairing state.
It confirms the reader identity and application, reads the factory/OTP data and
the reader's current pairing record, and derives the session configuration
locally. It sends no persistent command.

## MATCH

A valid comparison where at least one enrolled sample reaches the configured
similarity threshold. It is not a claim of pixel identity or perfect accuracy.

## MCU

Microcontroller unit: the tiny processor that controls the reader's internal
operation. A state query can ask the reader's MCU whether expected conditions
are active without exposing its implementation details.

## Minutiae

Traditional fingerprint features such as ridge endings and bifurcations. They
are common in fingerprint systems, but this project's production SIGFM format
uses its own keypoint-and-descriptor representation rather than only a classic
minutiae list.

## NO MATCH

A valid comparison where no enrolled sample reaches the match threshold. It is
different from a capture or processing error.

## OTP

One-time programmable memory: factory information designed for restricted or
one-time programming. This project reads and validates the expected
factory/OTP-related response; the supported path does not write OTP memory.

## PAM

Pluggable Authentication Modules: Linux's framework for combining
authentication methods and fallback rules for consumers such as login, lock
screen, and `sudo`.

## Persistent

State that survives closing a session or removing power. Factory firmware,
reader key material, and host template files are persistent in different
places.

## PolicyKit

A Linux authorization system used when applications request privileged actions.
On the tested Fedora setup, its KDE authentication dialog can reach the normal
PAM fingerprint path.

## Preprocessing

Preparing decoded image data for feature extraction. The Goodix SIGFM path uses
the no-finger baseline and current finger frame to produce an 8-bit raster.

## Probe

The new feature sample extracted during verification and compared with the
enrolled template.

## PSK

Pre-shared key: secret material already known to both sides of a secure
conversation. The project generates one Linux PSK locally, stores it root-only in
the host pairing state, and registers it with a single bounded
[host pairing](#host-pairing) write. It never replaces factory key material and
never publishes or exports the key.

## Raster

A rectangular grid of pixel or sensor values. The decoded Goodix image is an
80×64 raster.

## Register

A small numbered location inside a device used to control or report some part
of its operation. The driver uses only the understood, target-bound runtime
configuration path.

## Reassembly

Joining ordered fragments into complete protocol messages. One Goodix frame
can span several USB transfers, and a transfer can contain several frames.
Different devices, endpoints or attachment sessions must not be mixed.

## Retry

A request to try a physical touch again because no trustworthy MATCH or NO
MATCH decision was produced, or because enrollment needs different coverage.

## Runtime

The software and temporary state used while the system is operating. Runtime
configuration is not the same as rewriting persistent factory state.

## SIGFM

The feature extraction and matching path used by this project's production
`libfprint`. It turns a preprocessed image into keypoints and descriptors and
computes comparison scores.

## Threshold

The score boundary used to turn a similarity measurement into MATCH or NO
MATCH.

## TLS

Transport Layer Security: the protocol used here to create an encrypted,
integrity-checked conversation between host and reader using the stored Linux
PSK.

## USB

Universal Serial Bus: the physical and protocol connection used by the host to
exchange commands, events, and protected image data with the reader.

## Verification

Capturing a new probe and comparing it with an enrolled template to produce
MATCH, NO MATCH, or an error.

## Volatile

Temporary state that exists only for the current working session and is not
intended as permanent factory or user data.

---

[← Previous: Safety and factory preservation](10_safety_and_factory_preservation.md) | [Up: Learning home](README.md)
