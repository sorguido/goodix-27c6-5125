<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Licensing and provenance

Licensing is per file. A directory name or a combined binary's license does not
change the original copyright or grant of any source file.

## Components

| Component | Source/version | License and use |
| --- | --- | --- |
| libfprint base | Fedora libfprint 1.94.100 | Upstream per-file terms, predominantly LGPL-2.1-or-later; public library ABI and core |
| Goodix driver | Project source | Per-file SPDX, predominantly LGPL-2.1-or-later; device, transport, secure session and image integration |
| APP12509 pairing crypto | Project source; focused refactor of the project-authored D190 implementation and qualified PSK PoC | LGPL-2.1-or-later; pure fixed-profile BB010003/BB020003 derivation, with no USB, persistence, DLL loading or external implementation copied |
| APP12509 CONFIG90 derivation | Adapted from Rockytkg, commit `227eba219fa9e3fbac5bd59aca79f624f67cd11b`, `src/goodix_init.c` and `src/goodix_otp.c` | GPL-2.0-or-later; pure ChicagoHS type-12 template, OTP patch mapping and finalizer only |
| APP12509 BB010002 parser | Project source; structure qualified from multiple legitimate opaque Windows values | LGPL-2.1-or-later; validation only, with no decryption, protected-byte synthesis or embedded private fixture |
| APP12509 state-v2 | Project source | LGPL-2.1-or-later; host-only root-protected PSK/receipt generations, authenticated crash recovery and side-by-side legacy-state import, with no USB or pairing writer |
| APP12509 live preflight | Project source; independently implemented from the repository's documented command contracts | LGPL-2.1-or-later; bounded A2/A8/E4/chip/OTP read-only discovery and CONFIG90 derivation, with no persistent command or retry |
| APP12509 pairing provision boundary | Minimal adaptation of the project-authored qualified writer in `development/psk` | GPL-2.0-or-later; fixed E0 construction, one-logical-write guard, exact ACK/completion parser and readback/TLS proof gates; no USB ownership, automatic retry or firmware command |
| APP12509 pairing activation | Project source | LGPL-2.1-or-later; crash-safe PREPARED reservation, state-v2 reconciliation and bounded orchestration of the separately licensed pairing-provision boundary, readbacks, TLS and ACTIVE promotion |
| SIGFM | Rockytkg's materialized libfprint fork, commit `7ebe0c809b4d1df3400e84299a4ec4acdea84590` | LGPL-2.1-or-later; feature extraction and matching |
| Image preprocessing | Adapted from Rockytkg, commit `227eba219fa9e3fbac5bd59aca79f624f67cd11b` | GPL-2.0-or-later; device-independent preprocessing subset |
| OpenCV | Fedora OpenCV 4 packages (actual installed version recorded at build) | Fedora expression `BSD-3-Clause AND Apache-2.0 AND ISC`; required runtime libraries |
| libgusb | Fedora system library | LGPL-2.1-or-later; USB dependency, not privately bundled |
| OpenSSL | Fedora system library | Apache-2.0; TLS dependency |
| Lifecycle and Plasma selector tools | Project source | GPL-2.0-or-later; ordinary Linux-PAM APIs, Python standard library and Fedora tools |
| Windows VM Material Builder | Project source; historical finalizer/parser at `fa98461` | GPL-2.0-or-later; Python/Tkinter and existing `cryptography` dependency |
| USBPcap, separately downloaded by explicit action | Official pinned 1.5.4.0 | Driver GPLv2; CMD BSD-2-Clause; interactive upstream license acceptance; installer not redistributed |

Fedora supplies fprintd, its PAM module, Plasma, sudo and PolicyKit. Their
implementations are not copied into private replacement consumers by this
architecture. Each separately supplied package retains its own license.

## Combined library and notices

The Goodix-enabled libfprint incorporates GPL-2.0-or-later preprocessing and
links Apache-2.0 components. Applicable later-version grants allow the combined
library to be conveyed under GPL-3.0-or-later. Individual source files retain
their own notices and licenses; GPL code is not relabelled as LGPL.

Library build outputs include the applicable license texts, OpenCV's license
corpus read from the installed Fedora RPM license files, source manifests and
build provenance. Each local build records the actual package versions and
payload hashes. Those records describe the produced software; they do not
constitute an exhaustive dependency SBOM.

## Source provenance

The exact target-specific source paths, licenses and origins are recorded in
[`production/source-files.tsv`](../production/source-files.tsv), with digests in
[`production/source-files.sha256`](../production/source-files.sha256).
The [Fedora libfprint provenance record](../reference/libfprint-fedora44-1.94.100/PROVENANCE.md)
identifies the original archive/source-package hashes and downstream changes.

The four SIGFM files are `sigfm.cpp`, `sigfm.h`, `binary.hpp` and `img-info.hpp`
under `Rockytkg/libfprint/libfprint/sigfm/`. Their notices identify Matthieu
Charette, Natasha England-Elbro, Timur Mangliev and other credited contributors.
The preprocessing files `libfprint-driver/rockytkg-imgproc/goodix_imgproc.c`
and `.h` derive from Rockytkg's `src/goodix_imgproc.c` and
`include/goodix_imgproc.h` at the commit above. Firmware, provisioning, USB
control and debug-dump behavior are not incorporated with that subset.

Local lifecycle and recovery code uses this project's ownership/receipt formats;
no new external implementation or license boundary is introduced by the removal
tools. The Plasma selector uses public Linux-PAM interfaces without copying
PAM, fprintd or Plasma source into a private replacement component.

`libfprint-driver/goodix_pairing_crypto.[ch]` refactors the existing
project-authored `goodix_action_binding.c` algorithm into a fixed APP12509
profile. The producer/KDF key and GCM AAD are protocol constants already
qualified by the five non-circular D190 OEM-oracle known answers and the
project-authored single-write PoC. Rockytkg is retained as a differential
reference at commit `227eba219fa9e3fbac5bd59aca79f624f67cd11b`; no Rockytkg
or OEM source expression is copied into this LGPL module.

`libfprint-driver/goodix_config90.[ch]` adapts the ChicagoHS type-12 template
and named OTP calibration patches from Rockytkg's `src/goodix_init.c` and
`src/goodix_otp.c` at commit `227eba219fa9e3fbac5bd59aca79f624f67cd11b`.
It retains GPL-2.0-or-later and excludes USB transport, provisioning, firmware
and persistence behavior. `libfprint-driver/goodix_bb010002.[ch]` is a
project-authored structural validator derived from comparison of legitimate
opaque values; no protected value or decryption implementation is included.

`libfprint-driver/goodix_self_state.[ch]` is project-authored. It stores the
PSK separately from a PSK-authenticated fixed-size receipt, uses two atomic
generation slots with file and directory synchronization, and binds state to
the target, application, chip profile, OTP digest and CONFIG90 digest. It has
no USB transport or pairing-write implementation. Its legacy-import boundary
accepts only already validated caller-owned material and leaves the original
bundle untouched for rollback.

`libfprint-driver/goodix_runtime_coordinator.[ch]` is project-authored. It
combines the existing legacy loader, CONFIG90 derivation and state-v2 reader
behind an activation-only selection boundary. It contains no USB transport or
pairing writer; its only mutation is host-side ACTIVE promotion after a separate
TLS proof. No third-party implementation is copied.

`libfprint-driver/goodix_live_preflight.[ch]` is project-authored from the
documented APP12509 A0 command/response contracts and reuses the local A0 codec.
It accepts only the exact application, qualified chip profiles, valid OTP and
structurally valid live `BB010002`, derives CONFIG90 locally, and contains no
persistent command. `libfprint-driver/goodix_pairing_provision.[ch]` adapts only
the fixed E0 layout, response contract and one-write guard from the
project-authored GPL PoC in `development/psk`; it therefore retains
GPL-2.0-or-later. It owns neither USB transport nor state persistence and cannot
retry a transaction. `libfprint-driver/goodix_pairing_activation.[ch]` is
project-authored LGPL orchestration. It durably reserves the transaction through
state-v2, delegates the single E0 frame and proof contract to the GPL provision
boundary, routes the two exact readbacks, and promotes host state only after TLS.
It introduces no copied external implementation; the combined library remains
subject to the licensing boundary described above.

## Excluded material

The Windows builder's [audit](../tools/windows_material_builder/AUDIT.md) records
its exact reuse, supported qualified-VM boundary, official USBPcap release URL
and installer SHA-256. No USBPcap source or binary is incorporated into the
application; the app invokes the separately installed official program.
Historical PowerShell DPAPI behavior (BSD-2-Clause, copyright 2026 sorguido) was
inspected as a reference; its C# implementation and transfer-file workflow are
not copied into the app. The builder source and tests are publishable without
Git history or private evidence. They are separate from the Linux runtime payload
and do not add Windows/Python GUI dependencies to `production/build-public.py`.

Open-source licenses in this tree do not grant rights to distribute OEM firmware
or binaries, reader secrets, private captures, factory data, fingerprint images
or templates. Those items are excluded from public source and software payloads.
The runtime consumes a separately supplied legitimate device-material bundle.

Preserve original notices and corresponding source when
redistributing components. [References](REFERENCES.md) and
[acknowledgements](../ACKNOWLEDGEMENTS.md) identify the upstream projects.
