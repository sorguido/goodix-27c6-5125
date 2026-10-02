<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# 9. What is stored, and where

## The common misconception

> Does the fingerprint sensor itself remember my finger?

Not in this project's architecture.

The reader contains firmware, factory information, its pairing records, and
temporary working state. The enrolled Linux fingerprint templates live on the
host under Fedora's `fprintd` storage, and the Linux pairing key lives in its own
root-only host directory.

## Four different kinds of data

| Kind | Where it lives | What it is for | Project behavior |
| --- | --- | --- | --- |
| Factory and persistent reader state | Inside the sensor | Device identity, firmware, existing secure setup, calibration/factory state | Preserved; the supported path does not reprogram it |
| Host pairing state | Host: `/var/lib/fprint/goodix-5125-state-v2/` | The locally generated Linux pairing key and its authenticated receipts | Created on first use; root-only; preserved during removal |
| Optional legacy device material | Host: `/var/lib/goodix-5125-poc/` | Compatibility input for the legacy path | Imported only when you supply a bundle; read from a root-only directory; preserved during removal |
| Enrolled fingerprint templates | Host: `/var/lib/fprint/` | Stores user/finger metadata and SIGFM feature samples for later matching | Managed by Fedora `fprintd`; preserved during project removal |

These categories are related, but they are not interchangeable.

## Sensor state

The sensor has firmware and persistent state that existed before Linux support.
It also has **volatile state** used only while the current operation is active:
the selected mode, secure-session state, finger-detection tables, and current
capture lifecycle.

Volatile means it is working memory, not a permanent user database.

```text
sensor persistent state: preserve
sensor session state:    prepare, use, close
Linux pairing key:       generate once, store root-only
Linux user templates:    store on host
```

## Host-side pairing state and legacy material

On first use the driver generates a Linux pairing key locally, records it with a
single bounded write to the reader, and stores it in the root-only
`/var/lib/fprint/goodix-5125-state-v2/` directory. That directory holds two
crash-safe generations, each pairing the key with a receipt authenticated by it.
The receipt binds the reader identity, application, chip profile and
configuration digests, and records whether the pairing transaction is prepared,
active, or needs recovery. The key never leaves the host and is never shared with
Windows.

Optionally, the installer also imports five user-supplied legacy files into the
root-only `/var/lib/goodix-5125-poc/` directory. The driver validates their
shape, metadata, hashes, and cross-bindings before use, and keeps them side by
side with the pairing state without modifying them.

This material helps bind the runtime to the intended device and existing OEM
compatibility path. It is not an enrolled fingerprint template.

One legacy input is a Windows dynamic-link library (DLL) from the original
equipment manufacturer (OEM). The project parses validated data from it; it does
not run the DLL as Linux code.

## Host-side biometric templates

During enrollment, `libfprint` builds an `FpPrint` containing accepted SIGFM
samples plus metadata such as the finger label and compatible device. It
serializes that record, and `fprintd` saves it under `/var/lib/fprint/` for the
user.

During verification:

1. `fprintd` loads the appropriate saved template;
2. `libfprint` validates and deserializes its SIGFM samples;
3. the new probe is compared with those samples in memory;
4. the result is returned to `fprintd` and the authentication consumer.

The raw image is processed in memory. It is not the normal long-term record
saved by this flow.

## Why uninstall preserves templates

The driver and the user's biometric records have different lifecycles.

Removing or reinstalling the project software should not silently delete an
enrolled fingerprint. The normal and emergency removal paths therefore preserve
`/var/lib/fprint/` templates, the state-v2 pairing directory, and any
`/var/lib/goodix-5125-poc/` legacy material. Neither path writes to the reader.

Use KDE or the normal `fprintd` tools when you intentionally want to delete an
enrolled finger.

## Privacy rules

Treat all of the following as private:

- the state-v2 pairing directory;
- the optional five-file device-material bundle;
- PSKs or other keys;
- fingerprint templates;
- raw or processed fingerprint images;
- USB captures that may contain protected traffic;
- private OEM binary contents.

Do not place them in the repository, screenshots, public logs, or issue
attachments.

## ✅ What to remember

- The sensor is not the Linux fingerprint-template database in this project.
- Factory/persistent state belongs to the reader and is preserved.
- The Linux pairing key is generated once and lives in a root-only host
  directory.
- Optional legacy device material lives in a separate protected host directory.
- Enrolled SIGFM templates live in Fedora's host-side `fprintd` storage.
- Raw images are processed in memory, not saved as the normal template format.
- Removing the project preserves pairing state, legacy material and templates by
  default.

---

[← Previous: Desktop authentication](08_desktop_authentication.md) | [Up: Learning home](README.md) | [Next: Safety and factory preservation →](10_safety_and_factory_preservation.md)
