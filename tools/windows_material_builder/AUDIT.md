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
provides interface discovery, new-device capture and its own elevated worker.
With `-o -`, the unelevated relay creates the named pipe and writes its bytes to
stdout; the elevated instance writes to that pipe. The builder preserves
`-d`, `--capture-from-new-devices`, `-s 65535` and `-o -`, with raw-only stdout,
discarded stderr and no interactive stdin. Its Python helper uses CREATE_NO_WINDOW;
no console sharing or upstream job topology is a builder prerequisite.

## Bounded stop contract

This is a dedicated-qualified-VM experiment. Its sole normal USBPcap stop is
`%SystemRoot%\System32\taskkill.exe /F /T /IM USBPcapCMD.exe`, intentionally
covering all instances of that exact executable name and their process trees.
There is no unrelated-instance preflight, console input/probe, private stop exit
marker, CaptureJob, member-count check or TerminateJobObject fallback.

The unelevated helper resolves System32 through GetSystemDirectoryW, initializes
COM and calls [ShellExecuteExW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shellexecuteexw)
with verb `runas`, the absolute taskkill path and fixed parameters. Its
[SHELLEXECUTEINFOW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-shellexecuteinfow)
flags include NOCLOSEPROCESS, NOASYNC, FLAG_NO_UI and NO_CONSOLE, with SW_HIDE.
Windows still shows the security consent prompt. The GUI remains unelevated;
no PowerShell is involved in elevation and no taskkill output is captured as
user-visible diagnostics. The returned process handle must signal within 15 s.
Its exit code is checked and its handle is closed, including on error.

After taskkill completes, [Toolhelp process enumeration](https://learn.microsoft.com/en-us/windows/win32/toolhelp/taking-a-snapshot-and-viewing-processes)
checks exact `USBPcapCMD.exe` names, case-insensitively, under a five-second
budget with 50 ms polling. Each snapshot closes, bounds its entry walk and
requires NO_MORE_FILES for a complete negative result; API errors fail closed.
Only taskkill exit zero plus verified absence permits acceptance. A successful
exit alone never suffices. This follows the documented
[TASKKILL switches](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/taskkill)
without adding another executable name or stop retry.

The helper checks native relay liveness before initiating stop. Any earlier
exit, including zero, remains failure even if raw parses. One TASKKILL cleanup
attempt also runs on cancellation, startup timeout, invalid control/EOF or
capture failure. It cannot clear the earlier error. After verified absence the
helper waits up to five seconds for its relay, closes the native process handle,
flushes/closes raw and exits. Normal acquisition requires helper exit zero,
USBPCAP_ABSENT, RAW_CLOSED and bounded status EOF. The parent then flushes/fsyncs
the retained file and checks unchanged bounded size at three 50 ms intervals.
Only afterward does acquire call the unchanged strict capture.analyze.

The parent's helper wait is 90 s, including interactive UAC; status EOF and
reader join are each bounded by two seconds. On outer timeout it terminates
only its own Python helper with a five-second wait, marks cleanup unverified
and refuses the acquisition. This is not another USBPcap stop mechanism.
Denial, taskkill timeout, abrupt helper death or delayed Windows consent can
leave native activity unresolved. Closing handles does not prove cleanup or
cancel the OS consent service. No automatic retry or material success follows.

Cancel uses the same stop and always ends CAPTURE_CANCELLED, including during
UAC/stop; analysis is skipped or its result discarded. Raw is retained for all
outcomes. Allowlisted status lines and bounded numeric exit codes exclude
arbitrary stdout/stderr, exception text, paths, PIDs, payloads and reader hashes.
Fully valid container, target, APP and all four unambiguous materials are still
required for Diagnose and build. Partial evidence has no Build action.

## Material and privacy boundaries

The operator reports PASS for the retained real capture: source validation,
container/target/APP12509, CONFIG90/A2/CHIP82/A6, A6/FDT binding, DPAPI recovery,
five-file construction and final bundle validation, with EXIT_CODE=0. The
remaining unqualified boundary is embedded capture lifecycle. Detailed live
history belongs only in the ignored internal manual. This task opens no private
capture, OEM input or bundle and performs no Windows, USB or DPAPI operation.

Material extraction is unchanged: the exact initial UNKNOWN 255-to-assigned
CONTROL descriptor transition, one target/epoch, strict USB pairing, framed A0
checksums and exact APP12509 remain mandatory. CONFIG90 uses logical control
0x90, admitting observed wire 0x90 and compatible wire 0x91, with its 224-byte
body, DAC layout and finalizer checks. Typed A2/chip82/A6, ambiguity checks and
A6/FDT binding remain intact. The shared parse_a0 implementation, source-ctime
compatibility, DPAPI, five-file bundle and Linux runtime are unchanged.

CONFIG90_MISSING still offers no timed retry. Only otherwise qualified missing
A2/chip82/A6 evidence can offer the existing explicit 30-to-60-second allowance.
These are engineering bounds, not completeness guarantees. Historical positive
capture UI/trigger provenance remains unknown; it does not invalidate currently
accepted same-recording material. Never combine readers or recordings.

The bounded parser handles classic PCAP and supported EPB pcapng, rejects
truncation and retains file order even when timestamps decrease. The upstream
[buffer writer](https://github.com/desowin/usbpcap/blob/1.5.4.0/USBPcapDriver/USBPcapBuffer.c)
obtains timestamps before its serialization lock. Fractional classic timestamps
still obey their microsecond/nanosecond bounds. No private fixture is committed.

## Verification and next operator gate

Offline coverage exercises absolute path/fixed parameters/elevation, wait before
native enumeration, denied UAC, taskkill and enumeration failures/timeouts,
remaining USBPcap, early native exit, no console/Job path, bounded parent wait,
raw-only stdout, handle closure, flush/stability, safe statuses and retained raw.
Integrated acquisition covers valid/truncated PCAP and Cancel during startup,
stop and analysis. Linux ctypes mocks do not qualify Windows ABI, consent
service timing or native termination on the VM.

Verification scope: builder with the production C material loader; deployment,
production and recovery Python suites; A0, post-TLS and image-device C suites
both normally and with ASan/UBSan in the existing network/device-disabled SDK.
The public source copy excludes .git and development, exercises the builder,
production checks and CLI, and verifies every source-ledger hash. Production
payload dependencies are unchanged. Public TECHNICAL_MANUAL.md remains untouched.

The [single final Windows acquisition](README.md#current-gate-one-final-full-windows-acquisition)
updates source only, starts detached, accepts USBPcap UAC, attaches only at the
prompt, waits the ordinary 30 seconds without sensor contact and accepts TASKKILL
UAC. Require verified shutdown, all material checks and **Diagnose and build**.
Stop before Build private bundle; the backend already passed separately. If
embedded lifecycle still fails, mark EMBEDDED_USBPCAPCMD_CAPTURE=REJECTED and
pivot to the proven existing-capture input flow. No equivalent recapture or
further q/console/Job Object diagnostics are authorized by this gate.
