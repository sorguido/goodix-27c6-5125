<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# 12. Safety and factory preservation

## Linux support ≠ reprogramming the sensor

The project's principle is simple: use the reader through checked, temporary
runtime operations instead of taking destructive shortcuts merely to make a
demo work.

The supported path does not flash firmware, replace firmware, provision or
replace the pre-shared key, write one-time-programmable (OTP) memory, clear the
application, or alter persistent device identity. It preserves the factory
firmware, persistent factory state, protected key material, and the original
Windows-compatible path.

```text
SUPPORTED                              OUTSIDE THE PATH
checked runtime preparation            firmware flashing
existing protected compatibility data  new/replaced device key
temporary session state                permanent factory writes
host-side templates                    sensor reprovisioning
```

## 🏠 A rented-room analogy

You can arrange a desk and turn on a lamp while using a room. You should not
replace the locks or knock down a wall. Runtime setup is the desk arrangement;
factory firmware, identity, and keys are the locks and structure.

The implementation rejects unknown or unsafe protocol states. "Fail closed"
means it stops rather than improvising a potentially unsafe command. A
successful match proves that one authentication worked; it does not prove
every future Fedora version, every Goodix reader, or exhaustive Windows
compatibility.

For formal boundaries, read [Security and privacy](../SECURITY.md),
[Validation and limitations](../VALIDATION.md), and the
[canonical technical manual](../../TECHNICAL_MANUAL.md#safety-and-support-limits).

## ✅ The journey in one sentence

Your desktop asks Linux's authentication layers; fprintd asks libfprint; the
Goodix driver safely prepares the existing reader, detects and captures a
touch; the image pipeline builds features; and the matcher returns MATCH or
NO MATCH against a host-stored enrollment.

[← Previous](11_what_is_stored_and_where.md) · [Contents](README.md) · [Glossary →](glossary.md)
