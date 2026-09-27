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
stdout; the elevated instance writes to that pipe. In an existing kill-on-close
job, upstream creates neither a breakaway relay nor a replacement job. Its
[read thread](https://github.com/desowin/usbpcap/blob/1.5.4.0/USBPcapCMD/thread.c)
monitors the duplex pipe for disconnection even without new sensor traffic.
Pipe closure can initiate worker exit, but is not used as proof that it exited.
The direct-file worker termination branch is not used by the builder.

## Bounded stop contract

The GUI owns one unnamed, non-inheritable Windows Job Object with
KILL_ON_JOB_CLOSE and neither breakaway flag. It creates the unelevated Python
helper, assigns its exact Popen handle to this job, then sends START. Before
START, the helper cannot launch USBPcap. The GUI is outside this job and retains
its sole job handle. Assignment failure terminates only the blocked helper's
known handle. The existing hidden console and raw-only native stdout remain;
no q injection, console probes, stderr collection or manual stop is involved.

Before reporting capture readiness to the user, the owner requires three total
and three active processes in the job: helper, relay and elevated pipe writer.
It also reads the bounded [job member list](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list),
requires the helper PID and two distinct native members, and opens only those
members with SYNCHRONIZE and PROCESS_QUERY_LIMITED_INFORMATION. Their
[image paths](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-queryfullprocessimagenamew)
must match the selected pinned USBPcap executable. This prevents a console host
or unrelated job member from satisfying a count-only check. The two native
handles remain owned until cleanup, avoiding PID reuse during the exit wait.
IDs and image paths are never logged. No global process enumeration or
process-name-based termination is used. Missing/extra members, denied query/wait
rights or unexpected topology fail before the attach prompt. Population checks
continue during acquisition and immediately before STOP.

The [Windows job contract](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
contains descendants without breakaway; nested-job accounting is included.
The pinned upstream source defines the expected relay/elevated-worker topology;
runtime membership checks enforce it rather than assuming UAC inherited the job.
An environment that cannot meet this boundary is rejected, not silently relaxed.

On normal completion, STOP reaches the helper through its existing private pipe.
The helper requires the relay to be alive, calls TerminateProcess on its owned
relay handle with the private marker `0x47584350`, and waits at most five seconds.
Only API success and that exact resulting exit code permit RELAY_TERMINATED.
A pre-stop exit, failed call, other exit code or timeout remains failure. The
helper closes raw and exits zero; the owner requires both that completion marker
and status EOF. Parent helper wait is ten seconds; status EOF wait is two seconds.

The owner then calls [TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject)
on its private job, waits for both retained native handles to signal, and queries
active-process accounting until zero. These waits share one five-second deadline.
This catches a pipe worker that did not exit on disconnect. The helper's own
process handle is also waited. Only after this verified quiescence does the
owner open the retained raw, fsync it, check its bounded size is unchanged, close
it, and check size again. No arbitrary stability sleep or interactive exit is
required. Job close remains a cleanup backstop on failure or owner exit; it
cannot turn failed quiescence verification into success.

Only then may acquire call the existing strict parser. Fully parseable container,
paired target transfers, exact target/APP identity and all mandatory material
classes are required for **Diagnose and build**. Partial/ambiguous evidence shows
**Capture incomplete**, with no Build action; existing eligible retry policy is
unchanged. A valid PCAP never excuses process-cleanup failure. An expected native
termination code never substitutes for container/material validation. Worker
nonzero exits are not newly accepted.

Cancel always remains CAPTURE_CANCELLED after cleanup; analysis is skipped when
cancellation is already requested and its result is discarded if cancellation
arrives during analysis. Early death, broken control/status, timeout, quiescence,
flush or stability failure retains raw and cannot publish usable acquisition.
Telemetry remains limited to 64 allowlisted lifecycle lines: ownership, explicit
stop reason, exits, quiescence, flush, EOF and failures. No arbitrary stderr,
exception strings, paths, process IDs, payloads or reader-specific hashes enter
that trace. The previous q/probe code and its theory-specific tests are removed.

## Material and privacy boundaries

The operator's retained full captures pass normal read-only target/APP12509,
CONFIG90/A2/chip82/A6 diagnosis. The no-reader test establishes that q remains
pending in the shared console after successful injection; that interactive
requirement is retired. Detailed live traces and development chronology remain
only in the non-public development manual. This corrective opens no private
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

Offline coverage exercises the job ownership/handshake, exact native image
membership, retained handles, termination marker, early crashes, API failures,
shared cleanup deadline, empty scope before fsync, EOF, file stability, raw-only
stdout, retained failures/cancel, status privacy and post-stop strict parsing.
The integrated workflow tests valid and truncated synthetic captures and Cancel
during stop/analysis. Mocked Linux ctypes tests do not qualify Windows ABI,
UAC job inheritance or cross-integrity query/wait permissions.

Verification scope: builder with the production C material loader; deployment,
production and recovery Python suites; A0, post-TLS and image-device C suites
both normally and with ASan/UBSan in the existing network/device-disabled SDK.
The public source copy excludes .git and development, exercises the builder,
production checks and CLI, and verifies every source-ledger hash. Production
payload dependencies are unchanged. Public TECHNICAL_MANUAL.md remains untouched.

The [single final Windows acquisition](README.md#current-gate-one-final-full-windows-acquisition)
updates source only, starts detached, accepts UAC, attaches only at the prompt
and uses the ordinary 30-second window without touching the sensor. Require
verified shutdown plus all material checks and **Diagnose and build**. Stop
before Build private bundle; DPAPI/bundle is not this gate. If internal stop
still fails, do not request another equivalent capture or another console
instrumentation cycle. Reuse the known external workflow or an already-valid
retained capture for the next fallback decision.
