# D255 Windows VM APP12509 evidence capture operator guide

## Status and non-authority

D255 has acquired the required capture. The authorized run completed cold
attach and all zero-finger cancel/re-entry operator phases; TShark wrote a
readable 27,684-byte pcapng with 218 frames. Only host-side finalization failed
because Windows PowerShell 5.1 exposed a null/unavailable ExitCode. The existing
run has been recovered offline and no new live capture is required or authorized.

```text
WINDOWS_EXECUTION_ENVIRONMENT=VIRTUAL_MACHINE
VM_USB_PASSTHROUGH_METHOD=OPERATOR_GUI_MANUAL_ATTACH
D255_OPERATOR_AUTHORIZATION_REQUIRED=true
D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true
D255_FINGER_INTERACTION_ALLOWED=false
D255_EXPECTED_FINGER_INTERACTION_COUNT=0
READY_FOR_OPERATOR_RUN=false
NEW_LIVE_CAPTURE_REQUIRED=false
```

The launcher never starts/stops the VM and never attaches/detaches USB. Do not
perform enrollment, provisioning, firmware/IAP, PSK replacement, device
disable/enable, service restart, maintenance, or account/PIN changes. Keep raw
USB, OEM logs, cache and guest topology under the private repository's
canonical `captures/` directory. Public bundles must exclude raw evidence.

## Pre-attach account boundary

With Goodix absent from the guest, Windows Hello Fingerprint may legitimately
be hidden, unavailable, or not configurable. Fingerprint UI availability is
therefore not a pre-authorization gate. Pre-attach checks cover only:

```text
VM_WINDOWS_RUNNING=true
GOODIX_PRESENT_IN_GUEST=false
SETTINGS_SIGNIN_OPTIONS_PAGE_ACCESSIBLE=true
CURRENT_VM_FINGERPRINT_ENROLLMENT=NOT_COMPLETED
NO_NEW_PIN_CREATION_ALLOWED=true
ACCOUNT_PREREQUISITES_READY=true
SENSOR_DEPENDENT_UI_AVAILABILITY=UNKNOWN_BEFORE_ATTACH
PREATTACH_FINGERPRINT_UI_REQUIRED=false
```

Classify `WINDOWS_HELLO_PIN_STATE` as exactly one of:

```text
ALREADY_CONFIGURED
NOT_CONFIGURED
UNKNOWN
NOT_REQUIRED_BY_CURRENT_ACCOUNT_POLICY
```

Also classify whether current account policy requires a PIN for fingerprint
setup as `REQUIRED`, `NOT_REQUIRED`, or `UNKNOWN`. A `NOT_CONFIGURED` PIN with
`REQUIRED` policy fails before authorization. Never create/modify a PIN or use
registry/account workarounds.

## Methodological review before any future run

1. **What changes?** Pre-attach readiness now requires only a started/live
   TShark process and Goodix still absent from the guest. It does not require
   an already-created or nonempty pcapng. File materialization is checked after
   attach/bootstrap and final validation remains exit-zero, present, nonempty
   and readable with at least one frame.
2. **What hypothesis is tested?** The prior failure was caused solely by
   delayed host-side pcapng creation while TShark was healthy; removing that
   premature file gate should allow the operator attach prompt without
   weakening capture evidence validation.
3. **If it fails at the same point?** Do not authorize another repetition.
   Preserve the redacted TShark exit/path/stdout/stderr diagnostics and return
   them to AI-PM; investigate native TShark/USBPcap process behavior with a
   hardware-free Windows reproducer before proposing a different live method.

## Required initial state and host check

```text
VM_WINDOWS_RUNNING=true
GOODIX_PRESENT_ON_LINUX_HOST=true
GOODIX_PRESENT_IN_WINDOWS_GUEST=false
GUEST_USB_CAPTURE_RUNNING=false
D255_AUTHORIZATION_CONSUMED=false
```

The human operator may locate the host device read-only with `lsusb -d
27c6:5125` and inspect the exact device node with `fuser`. Do not use `sudo`,
kill a holder, stop fprintd, or change ownership. Independently confirm in the
guest that `Get-PnpDevice -PresentOnly` has no `VID_27C6&PID_5125`.

## Guest self-test, shared-path simulation and preflight

Run the hardware-free self-test first:

```powershell
& "C:\path\d255-windows-evidence-capture.ps1" `
  -SelfTestOnly `
  -OutputRoot "D:\Goodix-D255-SelfTest"
```

Expected: `D255_POWERSHELL_SELFTEST=PASS`,
`D255_CAPTURE_READINESS_SELFTEST=PASS`, hardware action count zero and
authorization not consumed. The readiness cases cover a live process with a
missing file, a live process with a zero-byte file, an exited process and the
strong terminal pcap contract.

Before any real preflight or authorization, exercise the shared live-path
setup with synthetic files only:

```powershell
& "C:\path\d255-windows-evidence-capture.ps1" `
  -PreAuthorizationSimulationOnly `
  -OutputRoot "D:\Goodix-D255-Preauth-Simulation" `
  -SimulationOemLogState "ABSENT"
```

Expected: `EMPTY_OEM_LOG_CANDIDATES_BINDING=PASS`,
`EMPTY_CACHE_ROOTS_BINDING=PASS`, `AUTHORIZATION_CONSUMED=false`,
`REAL_CAPTURE_STARTED=false`, `REAL_USB_OPEN_COUNT=0` and
`REAL_HARDWARE_ACTION_COUNT=0`. Repeat with `-SimulationOemLogState "PRESENT"`;
the expected source-specific result is `PRESENT_OEM_LOG_SNAPSHOT=PASS`. This
mode rejects an authorization string, TShark path, capture interface and real
log/cache path, and it calls the same evidence-snapshot setup function used by
the live branch.

Then open Settings → Accounts → Sign-in options only far enough to classify
the account/PIN state. Do not require or try to open Fingerprint recognition.
Enumerate capture interfaces with `tshark -D`. Select the sole USBPcap
interface, or all candidates simultaneously if the virtual controller cannot
be determined before attach; never guess one among several.

Example with an already configured PIN:

```powershell
& "C:\path\d255-windows-evidence-capture.ps1" `
  -PreflightOnly `
  -OutputRoot "D:\Goodix-D255-Raw" `
  -TsharkPath "C:\Program Files\Wireshark\tshark.exe" `
  -CaptureInterface "USBPcap1" `
  -VmGuestReadyConfirmation "VM_WINDOWS_RUNNING_GOODIX_ABSENT_FROM_GUEST" `
  -AccountPrerequisiteConfirmation "SIGNIN_OPTIONS_CHECKED_NO_NEW_PIN_CHANGE" `
  -WindowsHelloPinState "ALREADY_CONFIGURED" `
  -FingerprintSetupPinRequirement "UNKNOWN"
```

Expected: `D255_PREFLIGHT_ONLY=PASS`, account prerequisites ready, sensor UI
availability unknown before attach, hardware action count zero and
authorization not consumed. OEM/WBDI logs are optional evidence sources: when
none is discoverable, the report must say `OEM_LOG_STATUS=ABSENT` and continue.
If logs exist, automatic discovery or an explicit `-OemLogPath` preserves their
before/after snapshots and reports `OEM_LOG_STATUS=PRESENT`. Goodix cache is
reported independently as `GOODIX_CACHE_STATUS=PRESENT|ABSENT`; its absence is
not disguised as log absence. An explicitly supplied unreadable log or cache
path remains a pre-authorization failure.

## Authorized single run — not currently authorized

Only after positive AI-PM review, approval of the exact live-critical commit
SHA, and explicit one-run authorization may the same command be run without
`-PreflightOnly` and with:

```powershell
  -CaptureDurationSeconds 300 `
  -Authorization "--i-authorize-one-d255-windows-oem-evidence-capture"
```

All guest absence, interface, account, explicitly configured path, disk,
clock/topology and runtime gates precede authorization consumption. Optional
log/cache availability is recorded before authorization but is not itself a
live-critical gate. After the short grace period, readiness means only that
TShark is still alive and Goodix is still absent from the guest. The pcapng may
still be missing or zero bytes. Perform exactly one manual host→VM GUI attach
only after that process-readiness marker. Do not detach/re-attach.

The evidence ordering later enforced from markers and wire is:

```text
VM_GUEST_READY
GUEST_TOPOLOGY_BEFORE
ACCOUNT_PREREQUISITES_CHECKED
CAPTURE_PROCESS_STARTED
CAPTURE_STARTED
VM_USB_ATTACH_BEGIN
VM_USB_ATTACH_END
GUEST_27C6_5125_PRESENT
A8_APP12509_PROVEN              # derived from exact target wire response
PASSIVE_BOOTSTRAP_SETTLED
HELLO_SETUP_UI_CHECK_BEGIN
```

`CAPTURE_STARTED` is retained for postprocessor compatibility and means
"TShark process active before attach"; it does not assert file creation,
nonempty content or any captured frame. After attach and passive bootstrap the
launcher requires the pcapng to have materialized. At the bounded end it still
requires TShark exit code zero, a present nonempty pcapng and successful
one-frame readback before reporting captured evidence.

Only then open Settings → Accounts → Sign-in options → Fingerprint recognition
(Windows Hello) → Set up/Add a fingerprint, without touching the sensor. The
launcher presents a closed four-choice prompt:

```text
READY_WAITING_FOR_FINGER
UI_UNAVAILABLE
NEW_PIN_REQUIRED
UNEXPECTED_PREREQUISITE
```

`READY_WAITING_FOR_FINGER` continues through two zero-finger cancellations:

```text
HELLO_SETUP_UI_READY
OEM_SESSION_BEGIN
OEM_WAITING_NO_FINGER
CANCEL_NO_FINGER_BEGIN
CANCEL_NO_FINGER_END
REENTRY_BEGIN
REENTRY_WAITING_NO_FINGER
REENTRY_CANCEL_BEGIN
REENTRY_CANCEL_END
REENTRY_END
```

Every other choice is terminal for the restore phase. Do not create a PIN,
change account/UI path, perform recognition, touch the sensor, detach, retry,
or reopen the wizard. The run remains consumed, but TShark is allowed to reach
its bounded duration. The launcher then requires TShark exit zero, a nonempty
file, and a successful one-frame readback check before emitting:

```text
D255_RUN_RESULT=PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE
D255_RESTORE_PHASE_RESULT=WINDOWS_HELLO_SETUP_PREREQUISITE_MISSING_AFTER_ATTACH
BOOTSTRAP_EVIDENCE_PRESERVED=true
RESTORE_EVIDENCE_ACQUIRED=false
RESTORE_CLOSED=false
PARTIAL_CAPTURE_STOP_METHOD=BOUNDED_CAPTURE_TIMER_EXHAUSTED
PARTIAL_CAPTURE_FILE_VALIDATION=TSHARK_EXIT_ZERO_OR_UNAVAILABLE_NONEMPTY_READABLE_PCAPNG
```

## Offline postprocessing and restore semantics

Process the private run only from Linux, directly from the private repository:

```bash
python3 analysis/D255/d255_postprocess_windows_evidence.py \
  --run-dir captures/D255_20260822T205631772Z_85c8c41f \
  --manifest captures/D255_20260822T205631772Z_85c8c41f/recovery_manifest.json \
  --manifest-sha256 deb08f42b3fe4d3991f1e9bf9283e77fcf4f4c6f42383aa3c0efc82750dcedaa \
  --output-dir /tmp/D255_sanitized
```

The recovery manifest distinguishes original files, newly recovered metadata
and post-capture snapshots that cannot be reconstructed retroactively.

The postprocessor accepts full and partial result classes. A partial UI result
does not require cancel/re-entry markers, but still requires capture-before-
attach, one descriptor episode, guest PnP proof and exact target A8 APP12509.
It preserves bootstrap/cache/first-`0x36` analysis and reports no restore
evidence.

For a full run, successful OEM re-entry or acceptance of a new `0x32` arm proves
only re-entry. It does not prove that the prior FDT arm was disarmed. The
sanitized result separately reports host cancel, wire sequence, device close,
D0Exit/D0Entry, re-entry, new-arm acceptance, device-side cancel proof, prior
arm lifetime, restore evidence class and:

```text
DEVICE_FDT_DISARM_PROVEN=false
RESTORE_CLOSED=false
RESTORE_CLOSURE_DECISION=AI_PM_REVIEW_REQUIRED
```

Any IRQ `0x0002`, exact `0x22 [01 00]`, or correlated image-sized path in the
operator window invalidates restore evidence. No result authorizes retry.
