<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# 🎓 Goodix Behind the Scenes

You touch the fingerprint reader. A moment later, Linux says yes or no.

That tiny action crosses several layers of software, a USB connection, a
secure conversation with the sensor, an image-processing pipeline, and a
biometric comparison. This guide opens those layers one at a time.

> [!IMPORTANT]
> This is an educational guide, not the canonical technical specification.
> For exact implementation details, evidence, provenance, and support limits,
> use the [Technical manual](../../TECHNICAL_MANUAL.md) and
> [Validation](../VALIDATION.md) pages.

## Who this guide is for

This guide assumes that you can use a normal computer but have never needed to know
what PAM, D-Bus, `fprintd`, `libfprint`, a biometric template, or a USB driver
does.

You do not need to read source code. Optional source links are included for
curious readers, but the story stands on its own.

The project-specific parts describe the tested Goodix USB `27c6:5125` reader,
firmware `GF_ST411SEC_APP_12509`, and Fedora 44 KDE setup. Other Linux systems
may arrange the upper layers differently.

## The four zoom levels

```text
Level 1 — what you see
Touch the reader → the computer accepts or rejects the fingerprint

Level 2 — Linux
KDE / sudo / PolicyKit → PAM → fprintd → libfprint

Level 3 — Goodix
prepare → secure channel → detect finger → capture → decode

Level 4 — biometrics
image → features → template → comparison → MATCH / NO MATCH
```

You can stop after any chapter and still keep a useful mental picture.

## Reading order

1. [A two-minute tour](01_what_are_we_building.md) — the complete journey on one page.
2. [From Fedora to the sensor](02_from_fedora_to_the_sensor.md) — the Linux layers and why they are separate.
3. [Preparing a tiny computer](03_preparing_the_sensor.md) — identity, runtime setup, and the secure channel.
4. [From finger detection to image](04_from_finger_to_image.md) — the doorbell, the camera, and the image bytes.
5. [From image to fingerprint template](05_from_image_to_template.md) — preprocessing, features, and SIGFM.
6. [Enrollment](06_enrollment.md) — how several touches become a reusable template.
7. [Verification and matching](07_verification_and_matching.md) — MATCH, NO MATCH, retry, and cancellation.
8. [Login, lock screen, sudo, and PolicyKit](08_desktop_authentication.md) — one fingerprint stack, different experiences.
9. [What is stored, and where](09_what_is_stored.md) — sensor state, device material, and host templates.
10. [Safety and factory preservation](10_safety_and_factory_preservation.md) — why Linux support does not mean reprogramming the reader.
11. [Glossary](glossary.md) — plain-English definitions for the important terms.

## One rule to carry through the whole book

The physical sensor does not make the final decision by itself in this
project. It helps produce an image. The host then turns that image into a
biometric representation and compares it with templates stored by Fedora.

```text
sensor measures → driver decodes → libfprint compares → Linux decides
```

That separation explains most of the architecture you are about to meet.

---

[Start chapter 1 →](01_what_are_we_building.md)
