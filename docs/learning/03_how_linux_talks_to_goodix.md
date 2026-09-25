<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# 3. How Linux talks to Goodix

## 🔌 Messages, not magic

Universal Serial Bus (**USB**) is the cable and shared delivery system. The driver sends carefully shaped
messages and receives replies. The sensor has firmware—software already inside
the device—which interprets those messages.

```text
driver              USB                 sensor firmware
  |  command          |                         |
  |------------------>|------------------------>|
  |                   |            reply/data  |
  |<------------------|<------------------------|
```

Operations are **asynchronous**: the driver starts work and receives a callback
when a transfer finishes, rather than freezing while it waits. It owns one
fingerprint action at a time, bounds its transfers, checks reply shape and
order, and cleans up before another action.

## 🏠 A parcel analogy

USB is the courier, not the language in the parcel. Goodix's protocol defines
the envelope and conversation. The driver checks the address, expected reply,
and current step. A surprising parcel is rejected rather than guessed at.

Some later traffic travels through an encrypted session. Encryption protects
the conversation, but does not change the layers above it: fprintd still asks
libfprint for enrollment or verification.

> 🔎 **Repository view:** USB ownership and routing live in
> [`goodix_fpi_usb_backend.c`](../../libfprint-driver/goodix_fpi_usb_backend.c)
> and [`goodix_usb_router.c`](../../libfprint-driver/goodix_usb_router.c).

## ✅ What to remember

- USB transports messages; the Goodix driver understands their meaning.
- "Asynchronous" means start now, finish through a later notification.
- Unexpected protocol state fails closed; it is not treated as a fingerprint.

[← Previous](02_from_fedora_to_the_sensor.md) · [Contents](README.md) · [Next →](04_waking_up_and_preparing_the_sensor.md)
