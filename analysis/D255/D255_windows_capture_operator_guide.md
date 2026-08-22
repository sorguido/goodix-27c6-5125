# D255 Windows VM APP12509 evidence capture operator guide

## Status, boundary, and authority

D255 prepared this kit offline. It did not start Windows, a VM, USBPcap,
TShark, or the Goodix device. AI-PM review is not authorization and the future
run is not yet authorized.

```text
WINDOWS_EXECUTION_ENVIRONMENT=VIRTUAL_MACHINE
VM_PLATFORM=NOT_CANONICALLY_PRESERVED
VM_USB_PASSTHROUGH_METHOD=OPERATOR_GUI_MANUAL_ATTACH
VM_USB_PASSTHROUGH_METHOD_PROVENANCE=HISTORICAL_METHOD_NOT_CANONICALLY_PRESERVED
GUEST_USB_CAPTURE_METHOD=TSHARK_WITH_USBPCAP
GUEST_USB_CAPTURE_INTERFACE_MODEL=ONE_UNAMBIGUOUS_INTERFACE_OR_SIMULTANEOUS_ALL_RELEVANT_INTERFACES

D255_OPERATOR_AUTHORIZATION_REQUIRED=true
D255_AUTHORIZATION_CONSUMED_AFTER_PRE_HARDWARE_SETUP=true
D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true
D255_FINGER_INTERACTION_ALLOWED=false
D255_EXPECTED_FINGER_INTERACTION_COUNT=0
```

The repository does not preserve a canonical hypervisor product or attach
command. Do not substitute an assumed hypervisor CLI, USB redirection, or
hostdev workflow. Keep the VM already running and use the reviewed manual GUI
attach available to the operator. The launcher never starts/stops the VM and
never attaches/detaches USB.

The factory Windows path must not perform completed enrollment, provisioning,
firmware update, IAP, PSK replacement, reset, device disable/enable, service
restart, or maintenance. Raw USB, OEM logs, and cache copies remain in an
operator-selected private directory outside Git.

## Canonical Windows-state distinction

```text
HISTORICAL_NATIVE_WINDOWS_STATE=PRIOR_OPERATIONAL_CAPTURE_HISTORY_EXISTS; NOT_PROOF_OF_CURRENT_VM_UI_STATE
CURRENT_WINDOWS_VM_STATE=FINGERPRINT_ENROLLMENT_NOT_COMPLETED
CURRENT_WINDOWS_VM_FINGERPRINT_ENROLLMENT=NOT_COMPLETED
NORMAL_RECOGNITION_UI_AVAILABLE=NOT_PROVEN
D175_UI_PATH=NONE; PASSIVE_COLD_ATTACH_WITHOUT_WINDOWS_HELLO_OR_FINGER
RILEVAMENTO_UI_PATH=NOT_CANONICALLY_PRESERVED
```

The surviving `analysis/D230/work/GoodixExport/rilevamento.pcapng` is a
USBPcap pcapng with SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
The corpus historically classifies it in the D175 cold-attach line and cites a
second independent capture now absent. The original capture command, tool
version, hypervisor, passthrough action, WBDI path, and UI path are not
preserved. D175's useful boundary is passive cold attach plus automatic OEM
initialization; it does not prove recognition or enrollment availability in
the current VM.

## Selected UI path and zero-enrollment contract

The selected path is the normal Windows Settings setup wizard:

```text
Windows Settings
-> Accounts
-> Sign-in options
-> Fingerprint recognition (Windows Hello)
-> Set up / Add a fingerprint
```

It is used only to arm acquisition, reach the waiting state, and cancel twice
without touching the sensor. A template cannot be completed from zero samples;
that is the bounded offline justification for using this path. The exact VM
account prerequisite still requires guest preflight.

```text
SELECTED_WINDOWS_UI_PATH=WINDOWS_HELLO_SETUP_NO_FINGER
REQUIRES_PREEXISTING_FINGERPRINT=false
REQUIRES_PREEXISTING_PIN=POSSIBLE; IF_REQUIRED_IT_MUST_ALREADY_EXIST
NO_EXISTING_FINGERPRINT_REQUIRED=true
NO_NEW_PIN_CREATION_ALLOWED=true
CREATES_FINGERPRINT_TEMPLATE_IF_ZERO_FINGER=false
ZERO_FINGER_CANCEL_EXPECTED_SIDE_EFFECT_CLASS=VOLATILE_OEM_WBF_SESSION_AND_UI_CANCEL_ONLY
D255_OPERATOR_UI_PATH_READY=true; CONDITIONAL_ON_PREFLIGHT_CONFIRMATIONS
```

If Windows asks to create or modify a PIN, presents only recognition requiring
an enrolled print, begins enrollment before capture, or exposes another
unexpected prerequisite, stop with:

```text
WINDOWS_HELLO_SETUP_PREREQUISITE_MISSING
```

Do not retry automatically and do not improvise a different UI.

## Methodological review before any future run

1. **What actually changes?** The run is now explicitly guest-Windows in a VM,
   starts USBPcap before one manual attach, and uses setup/add-fingerprint with
   two zero-finger cancellations instead of assuming recognition.
2. **What new hypothesis is tested?** The normal setup path can arm, cancel,
   and re-enter without an enrolled print or finger while the same capture
   proves guest enumeration and APP12509 A8 identity.
3. **If it fails at the same point?** The consumed run is not repeated. The
   failure is reviewed offline; any alternative normal OEM/WBF path requires a
   new corrected kit, AI-PM review, baseline approval, and authorization.

## Required initial state

The future run starts exactly here:

```text
VM_WINDOWS_RUNNING=true
GOODIX_PRESENT_ON_LINUX_HOST=true
GOODIX_PRESENT_IN_WINDOWS_GUEST=false
GUEST_USB_CAPTURE_RUNNING=false
D255_AUTHORIZATION_CONSUMED=false
```

The cold-attach invariants are:

```text
GOODIX_PRESENT_IN_GUEST_BEFORE_CAPTURE=false
CAPTURE_STARTED_BEFORE_VM_USB_ATTACH=true
VM_USB_ATTACH_COUNT=1
AUTOMATIC_DETACH_REATTACH_ALLOWED=false
```

### Linux-host read-only preflight

With the VM already running and before authorization, locate the device without
changing ownership:

```bash
lsusb -d 27c6:5125
```

Record its bus/device numbers from `lsusb`, then inspect active users without
`sudo` or service changes:

```bash
fuser /dev/bus/usb/BBB/DDD
```

An empty `fuser` result is evidence that no visible process owns that device
node at that instant; lack of permission is inconclusive. Do not kill a process
or stop Linux fingerprint services as part of D255. Confirm independently in
the guest that `Get-PnpDevice -PresentOnly` has no `VID_27C6&PID_5125`. Together
these checks establish:

```text
GOODIX_VISIBLE_ON_HOST=true
GOODIX_NOT_ASSIGNED_TO_GUEST=true
```

The only ownership transition is `OPERATOR_ACTION_VM_USB_ATTACH` after the
capture-start proof.

## Guest preflight and USBPcap interface gate

First run the hardware-free runtime self-test:

```powershell
& "C:\path\d255-windows-evidence-capture.ps1" `
  -SelfTestOnly `
  -OutputRoot "D:\Goodix-D255-SelfTest"
```

Expected: `D255_POWERSHELL_SELFTEST=PASS`, hardware action count zero, and
authorization not consumed.

In the VM, verify the setup/add-fingerprint path with the target still absent.
Do not create a PIN and do not start enrollment. Then enumerate capture
interfaces with `tshark -D`.

If exactly one USBPcap interface exists, pass it once. If several relevant
USBPcap interfaces exist and the virtual controller cannot be determined
before attach, pass every USBPcap selector so TShark captures them
simultaneously into one pcapng. Selecting only one of several candidates fails
closed as `USBPCAP_INTERFACE_SELECTION=AMBIGUOUS`; never guess an index.

Single-interface example:

```powershell
& "C:\path\d255-windows-evidence-capture.ps1" `
  -PreflightOnly `
  -OutputRoot "D:\Goodix-D255-Raw" `
  -TsharkPath "C:\Program Files\Wireshark\tshark.exe" `
  -CaptureInterface "USBPcap1" `
  -OemLogPath "C:\verified\path\WBDI.log" `
  -VmGuestReadyConfirmation "VM_WINDOWS_RUNNING_GOODIX_ABSENT_FROM_GUEST" `
  -UiPrerequisiteConfirmation "SETUP_NO_FINGER_PATH_VERIFIED_NO_NEW_PIN"
```

For multiple interfaces, use `-CaptureInterface "USBPcap1","USBPcap2"`.
Expected preflight output is `D255_PREFLIGHT_ONLY=PASS`, hardware action count
zero, and authorization not consumed.

## Authorized single run — not currently authorized

Only after a new positive AI-PM review, live-critical baseline approval, and a
new explicit one-run authorization:

```powershell
& "C:\path\d255-windows-evidence-capture.ps1" `
  -OutputRoot "D:\Goodix-D255-Raw" `
  -TsharkPath "C:\Program Files\Wireshark\tshark.exe" `
  -CaptureInterface "USBPcap1" `
  -CaptureDurationSeconds 300 `
  -OemLogPath "C:\verified\path\WBDI.log" `
  -VmGuestReadyConfirmation "VM_WINDOWS_RUNNING_GOODIX_ABSENT_FROM_GUEST" `
  -UiPrerequisiteConfirmation "SETUP_NO_FINGER_PATH_VERIFIED_NO_NEW_PIN" `
  -Authorization "--i-authorize-one-d255-windows-oem-evidence-capture"
```

Before consuming authorization, the launcher completes tool/interface/path/
disk gates, guest target absence, clock anchor, OEM log/cache before snapshots,
PowerShell runtime check, UI-prerequisite confirmation, and a read-only guest
PnP topology snapshot. It then consumes the authorization, starts TShark,
proves the process and output file exist, and prompts for exactly one manual
attach. If capture start fails after consumption, the run is consumed.

Follow the prompts exactly:

1. Perform the single manual GUI attach; never detach/re-attach.
2. Wait for guest PnP proof of one `27c6:5125`.
3. Keep the sensor untouched and let passive OEM initialization settle before
   opening any Hello UI.
4. Open setup/add-fingerprint and reach waiting without touching the sensor.
5. Cancel without touching the sensor.
6. Reopen the same setup path, reach waiting, and cancel again without touching
   the sensor.
7. Let the bounded capture finish; do not terminate TShark manually.

The marker/proof timeline is:

```text
VM_GUEST_READY
GUEST_TOPOLOGY_BEFORE
CAPTURE_STARTED
VM_USB_ATTACH_BEGIN
VM_USB_ATTACH_END
GUEST_27C6_5125_PRESENT
A8_APP12509_PROVEN              # derived from wire by the postprocessor
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

The postprocessor requires the target device descriptor inside the capture,
the descriptor after `CAPTURE_STARTED` and within the single attach window, and
exact A8 `GF_ST411SEC_APP_12509` before `OEM_SESSION_BEGIN`. VID/PID or guest
PnP alone is not target-specific proof.

## Private outputs and offline sanitization

The run directory contains `raw/wire.pcapng`, clock anchors, before/after raw
OEM logs and targeted cache snapshots, guest topology snapshots, markers,
preflight/authorization records, and a hash-gated input manifest. These may
contain OTP, TLS, images, biometric material, and machine identifiers. Keep
them outside Git, cloud storage, and support tickets.

Process only from Linux, outside the repository:

```bash
python3 analysis/D255/d255_postprocess_windows_evidence.py \
  --run-dir /external/private/D255_RUN \
  --manifest /external/private/D255_RUN/input_manifest.json \
  --manifest-sha256 MANIFEST_SHA256_FROM_SIDECAR \
  --output-dir /tmp/D255_sanitized
```

The operator window is `OEM_WAITING_NO_FINGER` through
`REENTRY_CANCEL_END`. The postprocessor counts IRQ finger-down `0x0002`, exact
outbound `0x22 [01 00]`, and correlated image-sized B0 transfers. Valid
evidence requires all three counts to be zero:

```text
FINGER_DOWN_IRQ_COUNT_IN_OPERATOR_WINDOWS=0
POST_IRQ2_0x22_COUNT_IN_OPERATOR_WINDOWS=0
FINGER_IMAGE_PATH_COUNT_IN_OPERATOR_WINDOWS=0
FINGER_INTERACTION_DETECTED=false
```

Any positive count yields `D255_EVIDENCE_VALIDITY=INVALID_FINGER_INTERACTION`
and `RESTORE_CLOSED=false`. A pre-capture descriptor yields
`INVALID_DEVICE_ALREADY_ATTACHED`; multiple target device addresses or detach
markers yield `INVALID_VM_USB_TOPOLOGY_CHANGE`; missing target enumeration,
guest PnP proof, A8 identity, markers, or ordering also fails closed. No result
authorizes an automatic retry.
