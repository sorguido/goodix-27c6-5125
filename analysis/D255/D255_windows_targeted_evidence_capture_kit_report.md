# D255 corrective Windows VM targeted evidence capture kit report

## Closure

```text
OUTCOME=READY; CORRECTIVE_VM_AWARE_ZERO_FINGER_KIT_PREPARED_FOR_NEW_AI_PM_REVIEW
ADVANCEMENT=NON_HARDWARE_EXECUTABLE_CORRECTION; NO_NEW_DEVICE_EVIDENCE
EXECUTABLE_CLOSURE=PASS_OFFLINE_STATIC_AND_SYNTHETIC; NATIVE_WINDOWS_SELFTEST_PENDING_AI_PM_REVIEW
RESIDUAL_BLOCKER_OR_RISK=NO_REAL_WINDOWS_CAPTURE; UI_PREREQUISITE_AND_POWERSHELL_NATIVE_RUNTIME_REQUIRE_GUEST_PREFLIGHT
CANONICAL_DOCUMENTATION=UPDATED; D255 VM BOUNDARY, WINDOWS STATE, SETUP PATH, ZERO-FINGER INVARIANT
BUNDLE=analysis/D255/D255_windows_targeted_evidence_capture_kit_bundle.zip; SHA256=STEP_LOCAL_SIDECAR

INITIAL_HEAD=922134e21ec40ef4346df555eb8a4c096f56b2a9
```

This is the second correction of D255, not D256. The first AI-PM review found
PowerShell 5.1 and WBDI time-correlation defects. The next review found that
the corrected kit still assumed a normal recognition prompt although the
current project VM has no completed fingerprint enrollment. This revision
closes that same operator boundary offline. It did not start a VM, open USB,
run Windows/OEM software, use a finger, or execute TShark.

```text
D255_INITIAL_AI_PM_REVIEW=FAIL_EXECUTABILITY_AND_TIME_CORRELATION
D255_SECOND_AI_PM_REVIEW=FAIL_CURRENT_VM_RECOGNITION_PATH_ASSUMPTION
D255_CORRECTIVE_STATUS=READY_FOR_AI_PM_REVIEW
READY_FOR_AI_PM_REVIEW=true
READY_FOR_OPERATOR_RUN=false
```

## VM and cold-attach boundary

The local corpus preserves USBPcap format and historical cold-attach behavior,
but not the hypervisor product or passthrough command. The kit therefore uses
one explicit manual GUI attach and adds no host-side attach automation.

```text
WINDOWS_EXECUTION_ENVIRONMENT=VIRTUAL_MACHINE
VM_PLATFORM=NOT_CANONICALLY_PRESERVED
VM_USB_PASSTHROUGH_METHOD=OPERATOR_GUI_MANUAL_ATTACH
VM_USB_PASSTHROUGH_METHOD_PROVENANCE=HISTORICAL_METHOD_NOT_CANONICALLY_PRESERVED
GUEST_USB_CAPTURE_METHOD=TSHARK_WITH_USBPCAP
USBPCAP_INTERFACE_SELECTION=ONE_UNAMBIGUOUS_OR_CAPTURE_ALL_RELEVANT
GOODIX_PRESENT_IN_GUEST_BEFORE_CAPTURE=false
CAPTURE_STARTED_BEFORE_VM_USB_ATTACH=true
VM_USB_ATTACH_COUNT_EXPECTED=1
AUTOMATIC_DETACH_REATTACH_ALLOWED=false
GUEST_GOODIX_27C6_5125_PRESENCE_PROOF=READ_ONLY_PNP_SNAPSHOT_AND_CAPTURED_USB_DEVICE_DESCRIPTOR
A8_APP12509_PROOF_REQUIRED=true
VM_BOUNDARY_SYNTHETIC_TESTS=PASS
```

The PowerShell launcher requires the VM already running, the target absent
from guest PnP, guest/UI prerequisite confirmations, a read-only topology
snapshot, USBPcap interface closure, and all existing clock/log/cache/path/
runtime gates before authorization. When multiple USBPcap interfaces are
reported, the operator must select all candidates for simultaneous capture or
preflight fails as ambiguous. After authorization the launcher proves TShark
and its output exist, emits a single attach prompt, verifies one guest PnP
target, and never offers detach/re-attach.

The postprocessor requires an exact `27c6:5125` USB device descriptor after
`CAPTURE_STARTED` and within the single attach markers. It rejects a descriptor
before capture, no enumeration, more than one target bus/device, a detach
marker, or mismatched A8 device identity. Exact wire A8
`GF_ST411SEC_APP_12509` must occur after attach and before the OEM session;
VID/PID alone is insufficient.

## Windows UI and zero-finger boundary

```text
CURRENT_WINDOWS_VM_FINGERPRINT_ENROLLMENT=NOT_COMPLETED
NORMAL_RECOGNITION_UI_AVAILABLE=NOT_PROVEN
D175_UI_PATH=NONE; PASSIVE_COLD_ATTACH_NO_HELLO_NO_FINGER
SELECTED_WINDOWS_UI_PATH=WINDOWS_HELLO_SETUP_NO_FINGER
REQUIRES_PREEXISTING_FINGERPRINT=false
REQUIRES_PREEXISTING_PIN=POSSIBLE; MUST_ALREADY_EXIST_IF_REQUIRED
NO_NEW_PIN_CREATION_ALLOWED=true
D255_OPERATOR_UI_PATH_READY=true; CONDITIONAL_ON_GUEST_PREFLIGHT
```

The launcher now names only Settings → Accounts → Sign-in options → Fingerprint
recognition → Set up/Add a fingerprint. It opens the wizard, waits, cancels,
reopens, waits, and cancels again without a finger. `-AllowReentryFinger` and
every recognition-prompt instruction were removed. A new or modified PIN,
unexpected enrollment prerequisite, or unavailable setup path is terminal
`WINDOWS_HELLO_SETUP_PREREQUISITE_MISSING` with no automatic retry.

```text
D255_FINGER_INTERACTION_ALLOWED=false
D255_EXPECTED_FINGER_INTERACTION_COUNT=0
D255_ZERO_FINGER_INVARIANT_ENFORCED=true
ZERO_FINGER_SYNTHETIC_TEST=PASS
FINGER_IRQ_INVALIDATION_TEST=PASS
CMD22_INVALIDATION_TEST=PASS
IMAGE_PATH_INVALIDATION_TEST=PASS
```

The postprocessor evaluates the complete operator window from
`OEM_WAITING_NO_FINGER` through `REENTRY_CANCEL_END`. It counts target IRQ
`0x0002`, exact `0x22 [01 00]`, and image-sized inbound B0 records. Any positive
count produces `INVALID_FINGER_INTERACTION`, forces `RESTORE_CLOSED=false`, and
prevents the run from closing D255.

The dedicated D255 suite passes 37 tests, including guest-before absence,
guest-after presence, target enumeration in capture, pre-capture attach
invalidation, same-address second-attach episode invalidation, interface
selection contracts, UI marker order, and the four zero-finger fixtures.

## Existing corrective contracts retained

The PowerShell 5.1 implementation still uses `SHA256.Create()`/
`ComputeHash()`, `BitConverter`, and the canonical relative-path helper. Its
`-SelfTestOnly` remains hardware-free. Authorization follows every pre-device
gate and is consumed before TShark start; a post-consumption start failure is
terminal. Clock anchors, MMDD correlation, midnight/year rollover, log
rotation detection, hash-gated inputs, and secret/biometric redaction remain.

```text
POWERSHELL51_COMPATIBILITY_STATUS=PASS_STATIC_CONTRACT; NATIVE_SELFTEST_PENDING_WINDOWS
POWERSHELL_SELFTEST_MODE=IMPLEMENTED_NOT_EXECUTED; POWERSHELL_RUNTIME_UNAVAILABLE_ON_HOST
WBDI_MMDD_CANCEL_CORRELATION_TEST=PASS
OEM_LOG_ROTATION_TESTS=PASS
AUTHORIZATION_GATE_ORDER=ALL_GUEST_INTERFACE_PATH_CLOCK_LOG_CACHE_TOPOLOGY_UI_RUNTIME_GATES->EXACT_AUTHORIZATION->CONSUMPTION_RECORD->TSHARK_START->SINGLE_MANUAL_ATTACH
```

## Safety and unresolved device boundary

```text
BOOTSTRAP_CLOSED=false
RESTORE_CLOSED=false
D255_LIVE_EXECUTION=NOT_PERFORMED
D255_HARDWARE_BOUNDARY=NOT_AUTHORIZED

REAL_WINDOWS_CAPTURE_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_PERSISTENT_WRITE_FAMILY_COUNT=0
```

The offline correction is ready for AI-PM review only. A positive review would
not itself approve a baseline or authorize the future one-shot capture.
