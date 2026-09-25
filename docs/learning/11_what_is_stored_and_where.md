<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# 11. What is stored, and where?

## ❓ Does the sensor remember my enrolled finger?

In this project's architecture, **the enrolled template lives on the Linux
host**, under fprintd's storage area (`/var/lib/fprint/`). It is not enrolled
into the reader as a new permanent sensor record.

| Kind of data | Where it belongs | What happens |
|---|---|---|
| Enrolled biometric templates | Host, managed by fprintd | Preserved across this project's reinstall/removal; manage them through KDE/fprintd. |
| Current baseline, session, and capture state | Runtime memory | Temporary; rebuilt as needed. |
| Factory firmware and persistent reader state | Sensor | Intentionally left unchanged by the supported path. |
| Device-specific compatibility material | Protected host directory | Validated, root-only input used to operate the intended reader. |
| Raw capture/image working data | Runtime pipeline | Sensitive working data, not documentation or report material. |

The protected material and biometric templates are different. Compatibility
material helps establish the expected device conversation. A fingerprint
template represents an enrolled user's features. Neither belongs in the source
tree, an issue report, or this guide.

**Volatile** means temporary and lost or rebuilt when a session ends or power
changes. **Persistent** means intended to survive those events. Runtime
configuration can affect the current session without rewriting persistent
factory configuration.

Uninstalling project software preserves both the protected material and
fprintd templates. Preservation is not deletion: users who want to remove an
enrollment should use the normal KDE or fprintd interface.

## ✅ What to remember

The sensor measures; the host matches and stores enrolled templates in this
design. Factory identity, runtime state, and user biometrics are separate kinds
of data with separate safety rules.

[← Previous](10_login_sudo_polkit_and_lockscreen.md) · [Contents](README.md) · [Next →](12_safety_and_factory_preservation.md)
