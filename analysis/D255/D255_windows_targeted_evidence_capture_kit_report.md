# D255 corrective post-attach UI and restore-semantics report

## Closure

```text
OUTCOME=READY; POSTATTACH_UI_AND_CONSERVATIVE_RESTORE_CORRECTIVE_PREPARED_FOR_AI_PM_REVIEW
ADVANCEMENT=NON_HARDWARE_EXECUTABLE_CORRECTION; NO_NEW_DEVICE_EVIDENCE
EXECUTABLE_CLOSURE=PASS_OFFLINE_STATIC_AND_SYNTHETIC; NATIVE_WINDOWS_SELFTEST_PENDING_AI_PM_REVIEW
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=analysis/D255/D255_windows_targeted_evidence_capture_kit_bundle.zip; SHA256=STEP_LOCAL_SIDECAR
INITIAL_HEAD=feff1de25132d4e47dc9fe11a5f12509269c1696

D255_INITIAL_AI_PM_REVIEW=FAIL_EXECUTABILITY_AND_TIME_CORRELATION
D255_SECOND_AI_PM_REVIEW=FAIL_CURRENT_VM_RECOGNITION_PATH_ASSUMPTION
D255_THIRD_AI_PM_REVIEW=FAIL_PREATTACH_SENSOR_UI_GATE_AND_RESTORE_OVERCLAIM
D255_CORRECTIVE_STATUS=READY_FOR_AI_PM_REVIEW
READY_FOR_AI_PM_REVIEW=true
READY_FOR_OPERATOR_RUN=false
```

This is a third correction of D255, not D256. It was performed entirely
offline. No VM, Windows OEM component, TShark live capture, USB device, finger,
enrollment, account mutation, PIN mutation, provisioning, firmware operation,
PSK operation or persistent command was used.

## Account prerequisites and post-attach UI gate

The launcher no longer treats the sensor-dependent Fingerprint Setup wizard as
available while Goodix is absent. Pre-authorization state covers guest absence,
the accessible Sign-in options page, incomplete enrollment, the no-new-PIN
rule, an explicit PIN-state model and the current policy requirement.

```text
ACCOUNT_PREREQUISITES_READY=true
WINDOWS_HELLO_PIN_STATE_MODEL=ALREADY_CONFIGURED|NOT_CONFIGURED|UNKNOWN|NOT_REQUIRED_BY_CURRENT_ACCOUNT_POLICY
SENSOR_DEPENDENT_UI_AVAILABILITY_BEFORE_ATTACH=UNKNOWN_BEFORE_ATTACH
PREATTACH_FINGERPRINT_UI_REQUIRED=false
OLD_UI_CONFIRMATION_REMOVED=true
NEW_ACCOUNT_CONFIRMATION=SIGNIN_OPTIONS_CHECKED_NO_NEW_PIN_CHANGE
```

`NOT_CONFIGURED` plus a `REQUIRED` setup-PIN policy fails before authorization;
the launcher has no registry/account mutation path. The confirmation is checked
after USBPcap interface closure, and all remaining path/disk/log/cache/runtime
gates still precede exact authorization and TShark start.

After capture start, one manual attach and guest PnP proof, the postprocessor
requires exact target A8 APP12509 before the passive-bootstrap marker. Only
then does the launcher open a structured four-choice UI gate:

```text
POSTATTACH_HELLO_UI_GATE=READY_WAITING_FOR_FINGER|UI_UNAVAILABLE|NEW_PIN_REQUIRED|UNEXPECTED_PREREQUISITE
AUTHORIZATION_GATE_ORDER=GUEST_ABSENCE->USBPCAP_INTERFACE_CLOSURE->ACCOUNT_PREREQUISITES->PATH_DISK_LOG_CACHE_RUNTIME->EXACT_AUTHORIZATION->CONSUMPTION->CAPTURE_START->SINGLE_ATTACH->PNP->WIRE_A8->PASSIVE_BOOTSTRAP->HELLO_UI_GATE
```

The ready choice enters the existing zero-finger cancel/re-entry sequence. Any
other choice is terminal without retry, alternate UI, PIN/account change,
recognition, finger or detach/re-attach.

## Partial-bootstrap preservation

The non-ready UI branch is a consumed but valid partial result rather than a
capture failure. It lets the bounded TShark timer expire, requires exit zero,
nonempty capture and a read-only one-frame TShark validation, then snapshots
after-state and writes the hash-gated manifest.

```text
FULL_RUN_RESULT_CLASS=FULL_ZERO_FINGER_CANCEL_REENTRY
PARTIAL_RUN_RESULT_CLASS=PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE
PARTIAL_BOOTSTRAP_RESULT_SUPPORTED=true
BOOTSTRAP_EVIDENCE_PRESERVED_ON_UI_UNAVAILABLE=true
RESTORE_EVIDENCE_ACQUIRED_ON_UI_UNAVAILABLE=false
PARTIAL_CAPTURE_STOP_METHOD=BOUNDED_CAPTURE_TIMER_EXHAUSTED
PARTIAL_CAPTURE_FILE_VALIDATION=TSHARK_EXIT_ZERO_NONEMPTY_PCAPNG
```

The postprocessor accepts the partial marker without cancel/re-entry markers,
while retaining strict capture-before-attach, single topology, descriptor,
guest PnP and APP12509 A8 gates. It still extracts first `0x36`, physical tail,
cache/log correlation and sanitized bootstrap metadata.

## Conservative cancel/restore model

The sanitizer now reports independent observations for host cancel, cancel
wire sequence, device close, D0Exit, D0Entry, OEM re-entry, new `0x32`
acceptance, device-side cancel proof and prior-arm lifetime. Evidence classes
are bounded to:

```text
NO_RESTORE_EVIDENCE
HOST_CANCEL_ONLY
HOST_CANCEL_WITH_DEVICE_CLOSE
HOST_CANCEL_WITH_D0EXIT_REENTRY
EXPLICIT_DEVICE_CANCEL_COMMAND_OBSERVED
REENTRY_ACCEPTS_NEW_ARM_PRIOR_ARM_STATUS_UNKNOWN
INCONCLUSIVE_OEM_TIME_CORRELATION
```

Re-entry is not disarm. Even exact A8 re-entry or an ACKed new `0x32` cannot
auto-promote prior-arm lifetime or close restore:

```text
OEM_CANCEL_REENTRY_PROVEN_MODEL=EXACT_REENTRY_WIRE_SEQUENCE
DEVICE_FDT_DISARM_PROVEN_MODEL=EXPLICIT_TARGET_SPECIFIC_DISARM_REQUIRED
REENTRY_ALONE_CAN_CLOSE_RESTORE=false
RESTORE_CLOSURE_DECISION=AI_PM_REVIEW_REQUIRED
RESTORE_CLOSED_DEFAULT=false
```

Zero-finger invalidation remains active for IRQ2, exact `0x22 [01 00]` and the
correlated image path. A partial UI branch reports restore not acquired rather
than failing for absent cancel markers.

## Offline verification

```text
ZERO_FINGER_SYNTHETIC_TEST=PASS
VM_BOUNDARY_SYNTHETIC_TESTS=PASS
PARTIAL_BOOTSTRAP_SYNTHETIC_TEST=PASS
REENTRY_DOES_NOT_CLOSE_RESTORE_TEST=PASS
POWERSHELL51_COMPATIBILITY_STATUS=PASS_STATIC_CONTRACT; NATIVE_SELFTEST_PENDING_WINDOWS
WBDI_MMDD_CANCEL_CORRELATION_TEST=PASS
OEM_LOG_ROTATION_TESTS=PASS
```

The dedicated D255 suite passes 44 tests. D252/D253 audits, the five-test D254
suite, the full supported repository suite and `git diff --check` pass. Native
PowerShell is unavailable on this Linux host; `-SelfTestOnly` and
`-PreflightOnly` therefore remain future guest checks after review. No real
capture exists.

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
