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

Project-pinned release (installation/reboot/prerequisites reported live PASS on the operator VM; complete builder qualification pending): [USBPcap 1.5.4.0](https://github.com/desowin/usbpcap/releases/tag/1.5.4.0).
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
guarantees of completeness. An explicit retry for missing A2/chip82/A6, with CONFIG90 present, may use
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
Windows DPAPI/build, complete capture shutdown, remaining GUI/permission behavior
and the real bundle still require qualification. Installation/UAC/startup and
source checks have the operator-reported live results below. Offline success is not live qualification.
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

The 78 builder tests passed using synthetic inputs, including acceptance of
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

The first operator Windows run stopped at source validation with SOURCE_UNSAFE,
before USBPcap or reader interaction. Reported stable handle snapshots differed
from pathname metadata only in ctime. The fix retains strict handle-before/after
checks and excludes ctime only from Windows handle/path identity, retaining
device, inode, link count, size, mtime and file-type/reparse checks. POSIX checks
are unchanged. Seven focused synthetic tests cover this compatibility case and
rejection boundaries; the operator subsequently confirmed source validation PASS.

Live corrective pass 2 adds 12 tests: three enumeration groups (including full
synthetic PCAP/pcapng success and rejected near-misses), eight lifecycle groups
(console-event fields, explicit LF/Windows CRLF STOP, EOF, nonzero exits, timeouts,
broken pipes, status bounds/privacy and raw retention), and the CONFIG90 stop UI
policy. Console-event tests on Fedora use mocks, not a Windows ABI qualification.


## Live corrective pass 2: enumeration and stop observability

Operator-supplied evidence (not a new live run by the agent):

```text
WINDOWS_SOURCE_CTIME_FIX=LIVE_PASS
USBPCAP_1_5_4_INSTALL_AND_REBOOT=LIVE_PASS
USBPCAP_POST_REBOOT_PREREQUISITES=LIVE_PASS
CAPTURE_START_AND_MANUAL_ATTACH_GATE=LIVE_PASS
PCAP_CONTAINER=LIVE_PASS_174_COMPLETE_RECORDS
USBPCAP_DECODE=LIVE_PASS
ENUMERATION_255_TO_ASSIGNED_TRANSITION=REAL_OBSERVED
CURRENT_PARSER_ENUMERATION_POLICY=CORRECTED_OFFLINE_PENDING_LIVE
CAPTURE_STOP_STATUS=LIVE_FAILURE_DESPITE_COMPLETE_PCAP
APP12509=PASS
A2=PASS
CHIP82=PASS
A6=PASS
CONFIG90=MISSING
BUNDLE_BUILD=NOT_REACHED
DPAPI_LIVE_BUILD=NOT_REACHED
```

The reported PCAP is 20,959 bytes with no trailing data. UAC and READY worked;
attachment occurred only after the prompt, without sensor contact. The operator's
read-only in-memory normalization of the single UNKNOWN-address descriptor pair
allowed the old parser to reach CONFIG90_MISSING. Current private capture and OEM
material were not opened in this corrective pass.

[USBPcap allocation](https://github.com/desowin/usbpcap/blob/1.5.4.0/USBPcapDriver/USBPcapFilterManager.c)
starts the address at 255; its
[device-information query](https://github.com/desowin/usbpcap/blob/1.5.4.0/USBPcapDriver/USBPcapHelperFunctions.c)
assigns the actual address. The parser now permits this only for matching
interface/bus/IRP, CONTROL SETUP/COMPLETE on endpoint 0x80, UNKNOWN submit,
assigned address 1..127, successful completion, and the exact standard 18-byte
device-descriptor request. The response must have the full descriptor header,
legal USB2 endpoint-zero packet size and nonzero configuration count. The assigned
key must have no previous identity/material traffic; identity binds to that key.
Other address changes fail. Control URB function equality is deliberately not
required (observed 11 -> 8); bulk pairing and all material gates remain strict.

`CAPTURE_STOP_ROOT_CAUSE=UNRESOLVED`. Static inspection corroborates the intended
console key-down ASCII q path in the pinned CMD source and pipe-close termination
in its read thread. The Windows INPUT_RECORD layout, inherited stdin, actual q
receipt, exit status, flush and status-pipe timing were not observed individually
in the failed run. Neither a complete PCAP nor an absent process proves clean
shutdown. No exit code is newly accepted and no timeout is relaxed.

The worker now emits only a bounded lifecycle vocabulary: explicit STOP versus
control EOF, q requested/injected, child wait/timeout/exit, raw flush and STOPPED.
The parent records STOP sent, worker exit, status EOF, timeout and forced cleanup
in the private run's `diagnostics/lifecycle.txt` (maximum 64 allowlisted lines).
Unknown/overlong status output fails closed; arbitrary stderr and exception text
are never copied. Success still needs exit zero and STOPPED, now with observed
status EOF; control EOF alone cannot claim an explicit clean stop. The external
failure code remains CAPTURE_PROCESS_FAILED and raw retention is unchanged.
STOP accepts both LF and Windows text-pipe CRLF. Status writes are serialized;
failed status/control pipes cannot skip process cleanup or retained diagnostics.
This is instrumentation, not a claimed fix for the unproven live shutdown cause.

## CONFIG90 provenance and current gate

```text
CONFIG90_PROVENANCE=PARTIAL
CONFIG90_HISTORICAL_WORKFLOW=UNKNOWN
CONFIG90_HISTORICAL_CAPTURE_MODE=UNKNOWN
CONFIG90_LATENESS_EVIDENCE=NONE_FOUND
CONFIG90_60S_POLICY=DISABLED_WHEN_CONFIG90_MISSING
NEXT_GATE=HISTORICAL_TRIGGER_AND_WIRE_CONTRACT_REVIEW_NO_NEW_CAPTURE
```

The retained D232 material-provenance report (C3) and D233 runtime-boundary report
attribute the qualified 224-byte body to the recovered Windows capture in the
D230 corpus, later reused by D263. This identifies the historical source, not a
new comparison against the protected installed bundle. The earlier original
capture is recorded as lost. No private filename, path, digest or body is exported
here. The historical raw source still exists; only container/USB headers and its
single command-control byte at the documented boundary were read in this pass.
Raw size and modification time were unchanged. No OEM file, PSK, current capture
or private bundle was read.

The retained census and those reports establish these zero-based packet indices:

| Event | Packet(s) | Safe metadata |
| --- | --- | --- |
| Last of four preceding DAC writes | 99 | OUT logical 0x80; its ACK follows at 101 |
| CONFIG90 | 103, 105, 107, 109 | OUT A0, logical frame 232 bytes, body 224 bytes |
| CONFIG acknowledgement/response | 111, 113 | IN A0 ACK, then logical 0x90 response |
| Next request | 114 | OUT D1; B0 TLS ClientHello follows at 117 |

**Wire-contract discrepancy:** the historical census, D233 text and the header-only
recheck agree on wire **0x90** at packet 103. The old extractor at `fa98461`
accepted logical `wire & 0xfe == 0x90`; its synthetic example used 0x91. The current
builder/learning contract requires wire 0x91. That rule is unchanged by this pass;
using the old synthetic example as proof of the historical wire value was
unjustified. The discrepancy requires a separate contract review, not a permissive
parser change or a claim that it explains the unread current capture.

The canonical D274 workflow audit explicitly records that the recovered positive
capture lacks the acquisition command, UI markers and OEM workflow. Fresh attach,
already-attached state, re-enumeration, service restart and Windows Hello/enrollment
trigger are therefore UNKNOWN for this exact source. The later image-bearing
traffic in that historical recording does not prove what triggered its earlier
CONFIG90. Neither its capture-all/new-device/list/injected-descriptor settings nor
Wireshark/TShark options can be recovered from those reports. Historical D255 used
a separate TShark-controlled zero-finger workflow and cannot fill this gap.

The docs' attach-once sequence remains a way to record ordinary initialization,
not an established reproducible CONFIG90 acquisition recipe. D255 and the new
operator run both lack CONFIG90; neither establishes impossibility or lateness.
Missing CONFIG90 now offers no default/extended retry in the result screen and
instructs the operator to stop. The bounded 30 -> 60 mechanism remains only for
missing A2/chip82/A6 when CONFIG90 and the other gates pass, as an engineering
option without a completeness guarantee.

**Next human gate:** source-only replacement may be prepared on the existing VM;
preserve OEM files, installed USBPcap and both historical/current recordings.
No new capture is prescribed yet. Supply any existing historical acquisition
command/UI notes for the D230/D263 positive recording (metadata only), and resolve
the 0x90/0x91 acceptance boundary before choosing a new live action. Do not invent
a Hello, service-restart, PnP or firmware procedure to manufacture CONFIG90.
