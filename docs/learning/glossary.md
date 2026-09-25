<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Beginner glossary

**Asynchronous operation** — Work that starts now and reports completion later,
so the program does not freeze while waiting.

**Baseline** — A measurement of the sensor without a finger, used as a reference
when interpreting a later touch.

**Biometric template** — A reusable representation of fingerprint features for
comparison. It is sensitive data, even though it is not simply a raw picture.

**Callback** — A function asked to run later when an operation completes or an
event happens.

**D-Bus** — A Linux message-delivery system that lets separate programs request
services from one another.

**Daemon** — A background program that waits to perform a service. fprintd is a
daemon.

**Driver** — Software that knows how to operate a particular kind of hardware.

**Enrollment** — Teaching the system a finger by collecting accepted samples
and building a template for later comparisons.

**Features / keypoints** — Useful distinctive pattern information extracted
from an image. "Minutiae" is a common feature term, but this guide uses the
current SIGFM implementation's more accurate word, keypoints.

**Firmware** — Software already inside a hardware device.

**fprintd** — Linux's background fingerprint service. It accepts requests from
the rest of the system and uses libfprint.

**Interrupt (IRQ)** — A device's short "pay attention" notification, used here
as part of reporting finger contact and release.

**libfprint** — A library that gives Linux software a common interface to many
fingerprint readers and their drivers.

**MATCH / NO MATCH** — The comparison outcomes "corresponds to an enrolled
template" and "does not correspond." NO MATCH is not the same as capture error.

**PAM (Pluggable Authentication Modules)** — Linux's shared framework for
arranging authentication methods such as passwords and fingerprints.

**Persistent** — Intended to survive a restart or loss of power.

**PolicyKit** — A Linux mechanism through which desktop applications can ask a
user to authorize a privileged action.

**Pre-shared key (PSK)** — A secret already known to both ends and used here to
establish protected communication. It is not a fingerprint template.

**Raster** — An image represented as rows and columns of pixels.

**Register** — A small named or numbered setting/value inside a device. Exact
register work is an engineering detail, not a requirement for reading this guide.

**Runtime** — The period while software is operating, and the temporary state
used during that period.

**SIGFM** — The feature extractor and matcher used by this project's current
image pipeline.

**TLS (Transport Layer Security)** — A way to create a protected communication
channel. This reader uses TLS 1.2 with its existing PSK.

**USB (Universal Serial Bus)** — The connection that carries commands, replies,
and data between the host and reader.

**Verification** — Capturing a new touch and comparing its representation with
an already enrolled template.

**Volatile** — Temporary state that is lost or rebuilt after a session or power
change.

[← Safety](12_safety_and_factory_preservation.md) · [Back to contents](README.md)
