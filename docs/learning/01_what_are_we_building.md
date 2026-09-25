<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# 1. What are we building?

## 👀 What you see

You place a finger on the reader. The login screen, lock screen, `sudo` prompt,
or an authorization window accepts or rejects it. In fingerprint settings, you
can instead teach the computer a finger. That teaching step is **enrollment**.

## 🧠 What is really happening

The screen does not recognize fingerprints. It asks a chain of specialists.
The last specialist exchanges messages with a tiny computer inside the sensor.
That computer detects contact and sends measurements. Software turns those
measurements into an image, extracts useful pattern information, and compares
it with a previously enrolled representation.

```text
Level 1: touch → recognized
Level 2: Linux asks its fingerprint service
Level 3: the Goodix driver prepares, detects, and captures
Level 4: image → features → template → MATCH / NO MATCH
```

A **template** is the reusable biometric representation. It is not a password,
and in this project it is kept by the host computer rather than enrolled into
the reader.

## 🏠 A simple analogy

Imagine a hotel. The application is the guest at the desk. A receptionist
routes the request, a specialist operates the camera, and a clerk compares the
new portrait with the file on record. No single person performs every job.

## ✅ What to remember

- The visible prompt is only the top layer.
- Capturing a usable image is not the same as recognizing a person.
- Enrollment builds a reference; verification compares against it.
- This project adds a Goodix hardware path while keeping Fedora's normal
  fingerprint service and authentication components.

[← Contents](README.md) · [Next: From Fedora to the sensor →](02_from_fedora_to_the_sensor.md)
