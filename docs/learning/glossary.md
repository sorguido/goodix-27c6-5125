<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Glossary

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

## Callback

A function arranged to run when an asynchronous event finishes, such as a USB
transfer completing or image processing returning a result.

## Claim

Temporary exclusive use of the fingerprint device by one `fprintd` client.
Claiming prevents unrelated clients from mixing operations on the same reader.

## Daemon

A background service. `fprintd` is a daemon that waits for fingerprint requests
from other parts of Linux.

## D-Bus

A structured inter-process messaging system. It acts like an operating-system
intercom between clients and services such as `fprintd`.

## Descriptor

Numbers describing the pattern around a feature point. SIGFM compares these
descriptors rather than requiring two fingerprint images to be pixel-for-pixel
identical.

## Driver

Software that knows how to operate particular hardware. The Goodix driver
translates `libfprint` actions into the protocol used by USB `27c6:5125`.

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

## Host

The main computer running Linux, as opposed to the fingerprint sensor itself.

## Interrupt / IRQ

A message from hardware that an event occurred. A validated Goodix finger-down
IRQ tells the driver to move from waiting to image capture.

## `libfprint`

The Linux fingerprint library that supplies common device behavior, drivers,
image processing hooks, template handling, and matching. This project builds a
Goodix-enabled version for `fprintd` to load.

## MATCH

A valid comparison where at least one enrolled sample reaches the configured
similarity threshold. It is not a claim of pixel identity or perfect accuracy.

## Minutiae

Traditional fingerprint features such as ridge endings and bifurcations. They
are common in fingerprint systems, but this project's production SIGFM format
uses its own keypoint-and-descriptor representation rather than only a classic
minutiae list.

## NO MATCH

A valid comparison where no enrolled sample reaches the match threshold. It is
different from a capture or processing error.

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
conversation. The project uses the reader's existing PSK and does not publish,
replace, or provision it.

## Raster

A rectangular grid of pixel or sensor values. The decoded Goodix image is an
80×64 raster.

## Register

A small numbered location inside a device used to control or report some part
of its operation. The driver uses only the understood, target-bound runtime
configuration path.

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
integrity-checked conversation between host and reader using the existing PSK.

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
