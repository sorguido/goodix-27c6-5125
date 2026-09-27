<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Windows material builder: development candidate audit

This source application is not a supported release until Windows VM validation
passes. No firmware or Linux runtime change is part of this feature.

## Contract and reuse

The five-file contract comes from `docs/DEVICE_MATERIALS.md`, the learning guide,
`deployment/materials.py`, and the production C units `goodix_action_binding`,
`goodix_runtime_inputs`, `goodix_target_material`, `goodix_runtime_material`.
The ten-field manifest, qualified OEM DLL, CONFIG90 layout/finalizer, FDT CRC
and OTP cross-binding are unchanged. Python calls the installer's existing
byte validator; native crypto equivalence is tested with synthetic materials.

`binding.py` extracts the pure PE/crypto functions from the project-authored
`tools/device-materials/Finalize-Goodix5125TransportMaterial.py` at `fa98461`
(GPL-2.0-or-later). `framing.py` reuses `parse_a0` from the shared parser at
that commit, unchanged. The old PowerShell wrapper/core, CONFIG90 and response
extractors were inspected. Their CLI, loose transfer files, digest reporting,
lenient container handling and Linux-only output publication are not reused.
The ctypes DPAPI implementation follows the documented entropy and native API
sequence of the historical BSD-2-Clause core (copyright 2026 sorguido).

New code: bounded PCAP/pcapng and USB attachment/transfer analysis, diagnostics,
Windows file/DPAPI/prerequisite/install wrappers, retained capture lifecycle,
and a thin Tkinter view. No new packet, GUI, installer or packaging framework.
Python's standard library and the existing `cryptography` dependency suffice.

## Official USBPcap audit

Project-pinned release (live qualification pending for the tested Windows VM baseline): [USBPcap 1.5.4.0](https://github.com/desowin/usbpcap/releases/tag/1.5.4.0).
Installer: `USBPcapSetup-1.5.4.0.exe`, 195040 bytes.
SHA-256, computed from the complete official HTTPS artifact on 2026-09-27:
`87a7edf9bbbcf07b5f4373d9a192a6770d2ff3add7aa1e276e82e38582ccb622`.
It was read into memory only, never executed or vendored.

The upstream [installer source](https://github.com/desowin/usbpcap/blob/1.5.4.0/nsis/USBPcap.nsi)
uses UAC and explicit GPLv2 driver/BSD-2-Clause CMD license pages. Default paths
are `%ProgramFiles%\USBPcap` (native architecture) and its `USBPcapCMD.exe`.
The [upstream site](https://desowin.org/usbpcap/) requires reboot after install.
The GUI launches the interactive installer only on the Install action, then
requires reboot and returns to preflight on relaunch. No silent license flags.
The official installer presents its normal defaults and choices, including
**Detect USB 3.0** (`USBPcapCMD.exe -I` for non-standard root-hub initialization).
This option is not yet independently qualified by the project for the guest
controller. Record its setting and the guest topology at the Human Gate; the
application neither changes that setting nor executes `-I` itself.

The pinned [CMD source](https://github.com/desowin/usbpcap/blob/1.5.4.0/USBPcapCMD/cmd.c)
provides extcap discovery without Wireshark, new-device capture, its own elevated
capture worker, and console `q` shutdown. Stdout mode keeps a pipe to that worker
so closing capture does not use its direct-file TerminateProcess path.
The GUI and DPAPI never elevate. Capture readiness requires both a live process
and the emitted PCAP header. New-device capture omits `-A` and descriptor
injection. Controller selection must use the manual mapping in the learning
guide; unresolved multiple interfaces fail closed. A capture never retries an
attachment automatically.

[USBPcap headers](https://desowin.org/usbpcap/captureformat.html) use link type
249 and little-endian metadata. Version 1.5.4.0 uses SETUP/COMPLETE control
records. The bounded parser also reads existing EPB pcapng evidence, rejects
truncation and separates descriptor epochs before examining A0 streams.

The upstream [buffer writer](https://github.com/desowin/usbpcap/blob/1.5.4.0/USBPcapDriver/USBPcapBuffer.c)
obtains timestamps before acquiring the serialization lock. Consequently packet
timestamps may decrease in file order. PCAP/pcapng records retain file-order
indices; timestamps neither reorder records nor impose monotonic acceptance.
Classic PCAP fractional fields still obey microsecond/nanosecond bounds; EPB
timestamps are unsigned 64-bit ticks with no comparable fractional-field bound.

## Evidence and remaining gate

A read-only historical zero-finger capture audit found unique A2, chip82, A6
and APP12509, but no valid CONFIG90. Size and modification time were unchanged.
This is a negative feasibility result, not a five-file golden fixture. Synthetic
missing-CONFIG90 coverage represents that failure without copying private data.
No private evidence paths, payloads or reader-specific hashes belong here.

The observed typed-response window ended less than eight seconds after the first
descriptor. The candidate allows 30 seconds after guest appearance, with a
90-second manual-attach timeout. These are bounded engineering allowances, not
guarantees of completeness. An explicit missing-evidence-only retry may use
60 seconds: a bounded doubling to test possible late initialization, not a
qualified completeness threshold. Target and APP identity must already pass;
ambiguity or any other failure excludes this option. The existing A6/FDT
comparison is also applied before offering a retry when A6 is available, so a
known mismatch cannot be hidden by a simultaneous missing class. It repeats detached-first
preflight and manual attachment in a fresh run, with no third timing tier. The historical operator also explicitly waited for
passive initialization to settle; only complete capture evidence permits build.

The candidate parser reproduces the missing-CONFIG90 outcome on that retained
capture. Like the historical parser, it never scans opaque traffic or physical
tails for a body; only framed A0 candidates are eligible. It additionally requires
successful USB submission/completion pairing, an exact NUL-terminated runtime A8
identity, one target identity/attachment epoch, full packet snapshots, and
CONFIG90's fixed DAC layout. A repeated descriptor before material traffic is
allowed; a later descriptor or reconfiguration is an ambiguous epoch.

A read-only Welcome action reports only Windows product/version/build and Python
version for the gate; unavailable values remain UNKNOWN without a new OS gate.
Windows DPAPI, UAC, capture lifecycle, permissions, GUI behavior and the complete
real bundle require the operator gate. Offline success is not live qualification.
The installer/runtime remains final authority. Raw captures remain private,
outside the final bundle, on success, failure and retry.

## Public export boundary

The candidate lives entirely under `tools/windows_material_builder`, with a
dependency only on the public `deployment/materials.py` content validator.
Tests use the public synthetic generator in `deployment/test_materials.py`.
The public-source ledger includes the candidate; `production/build-public.py`
continues to build only the Linux payload. Adding Tkinter/cryptography or the
USBPcap installer to that payload would be an unnecessary dependency change.
Export validation must exercise the candidate from a copy with no `.git` or
`development` directory, including its tests and command-line entrypoint.

## Offline verification (2026-09-27)

The 59 builder tests passed using synthetic inputs, including acceptance of
generated material by the compiled production C loader. Existing deployment
(76), production (13) and recovery (48) Python tests passed. The C A0 (51),
post-TLS (19) and image-device (58) suites each passed both normally and under
ASan/UBSan using the existing Freedesktop SDK. These results do not validate
Windows native API behavior or actual reader acquisition.

The corrective pass added 11 tests for timestamp inversions/ranges, explicit
30/60-second retries and retention, mixed missing/A6-mismatch exclusion, installer
wording, and safe baseline metadata reporting. The read-only historical capture
still returns CONFIG90_MISSING, with A2/chip82/A6 and APP12509 passing and raw
size/mtime unchanged; the timestamp correction did not change its classification.

A public source copy without Git history or `development` passed the builder
tests, CLI entrypoint check and complete source-ledger hash verification.
Its inventory excludes raw captures, OEM binaries and material bundles.
