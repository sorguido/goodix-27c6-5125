# D255 TShark pre-attach readiness corrective report

## Closure

```text
OUTCOME=READY_FOR_AI_PM_REVIEW; TSHARK_PREATTACH_FILE_RACE_CORRECTED_OFFLINE
ADVANCEMENT=NON_HARDWARE_EXECUTABLE_CORRECTION; NO_NEW_DEVICE_EVIDENCE
EXECUTABLE_CLOSURE=PASS_OFFLINE_STATIC_AND_SYNTHETIC_CONTROL_FLOW; NATIVE_WINDOWS_SELFTEST_AND_TSHARK_BEHAVIOR_PENDING
RESIDUAL_BLOCKER_OR_RISK=CORRECTED_LAUNCHER_NOT_RERUN_IN_NATIVE_WINDOWS; AI_PM_REVIEW_NEW_EXACT_BASELINE_AND_NEW_USER_AUTHORIZATION_REQUIRED_BEFORE_LIVE
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=analysis/D255/D255_windows_targeted_evidence_capture_kit_bundle.zip; SHA256=STEP_LOCAL_SIDECAR
CORRECTIVE_INITIAL_HEAD=999483362af23f67790eb6e54f4c02bb48bd6cd5

OBSERVED_WINDOWS_FAILURE=D255_FAIL_CLOSED_CAPTURE_PROCESS_ALIVE_BUT_OUTPUT_FILE_NOT_CREATED
AUTHORIZATION_CONSUMED=true
GOODIX_ATTACHED_TO_VM=false
TSHARK_PREATTACH_READINESS_SEMANTICS=PROCESS_STARTED_AND_ALIVE_TARGET_ABSENT; NO_FRAME_OR_VALID_PCAP_CLAIM
PREATTACH_PCAP_FILE_REQUIRED=false
FINAL_PCAP_VALIDATION_PRESERVED=true
EMPTY_OEM_LOG_CANDIDATES_SUPPORTED=true
EMPTY_ARRAY_CLASS_AUDIT=PASS
REAL_USB_OPEN_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0

D255_INITIAL_AI_PM_REVIEW=FAIL_EXECUTABILITY_AND_TIME_CORRELATION
D255_SECOND_AI_PM_REVIEW=FAIL_CURRENT_VM_RECOGNITION_PATH_ASSUMPTION
D255_THIRD_AI_PM_REVIEW=FAIL_PREATTACH_SENSOR_UI_GATE_AND_RESTORE_OVERCLAIM
D255_REAL_PREFLIGHT_OBSERVATION=FAIL_UNPROVEN_OEM_LOG_REQUIREMENT
D255_PRIOR_LIVE_PATH_OBSERVATION=FAIL_PARAMETER_ARGUMENT_VALIDATION_EMPTY_ARRAY_BEFORE_AUTHORIZATION
D255_LATEST_LIVE_PATH_OBSERVATION=FAIL_PREATTACH_PCAP_FILE_CREATION_RACE_AFTER_AUTHORIZATION
D255_CORRECTIVE_STATUS=READY_FOR_AI_PM_REVIEW; NATIVE_WINDOWS_READINESS_SELFTEST_PENDING
READY_FOR_AI_PM_REVIEW=true
READY_FOR_OPERATOR_RUN=false
```

This remains a correction of D255, not D256. It was performed entirely
offline. No VM, Windows OEM component, TShark live capture, USB device, finger,
enrollment, account mutation, PIN mutation, provisioning, firmware operation,
PSK operation or persistent command was used.

The latest operator invocation stopped before attach and before any
sensor-reaching action, but it did consume the one-run authorization and did
start TShark. It therefore cannot be repeated under the consumed authorization.

## Latest observed Windows failure: pre-attach pcapng race

The single authorized run on baseline
`999483362af23f67790eb6e54f4c02bb48bd6cd5` completed pre-hardware setup,
recorded authorization consumption and started TShark on `USBPcap1`. After the
fixed two-second grace period the TShark process was alive, but the launcher
failed solely because `raw/wire.pcapng` did not yet exist:

```text
D255_FAIL_CLOSED: capture process is alive but output file was not created
```

Goodix was never attached to the Windows guest and no sensor-reaching action
occurred. A later read-only check observed the zero-byte pcapng in the run
directory with a last-write time several seconds after the premature gate.
This is direct evidence of delayed host-side file materialization, not device
or capture-process failure.

The corrected pre-attach contract is now exactly: TShark was started, remains
alive after the short grace period, and `27c6:5125` is still absent from the
guest. `CAPTURE_PROCESS_STARTED` records that meaning; the retained
`CAPTURE_STARTED` compatibility marker explicitly makes the same process-only
claim. Neither marker claims that a file, frame or valid pcapng already exists.
The launcher checks that the file has materialized after attach and passive
bootstrap, then preserves the terminal requirements: capture process exit code
zero, file present, file nonempty and TShark readback of at least one frame.
Only after those terminal checks can it emit
`D255_CAPTURE_RESULT=CAPTURED_PENDING_OFFLINE_VALIDATION`.

TShark stdout and stderr are redirected to run-local diagnostic files. Capture
failures now report process state, exit code when available, a redacted
command/argument summary, output-path state and redacted bounded stdout/stderr.
No dependency was added.

## Observed Windows failure and control-flow proof

The earlier operator invocation on baseline
`74a1ebda24166ac026ef7ed55c15f0d21e4593e3` reached the live-only
pre-authorization setup after the passing self-test and preflight. With
`OEM_LOG_SOURCE_COUNT=0`, PowerShell rejected the mandatory `Candidates`
argument before entering `Write-OemLogSnapshot`:

```text
ParameterBindingValidationException
ParameterArgumentValidationErrorEmptyArrayNotAllowed
```

The source order proves that the earlier failure happened before authorization consumption:
the before-log/cache snapshots and shared setup call precede the exact
authorization comparison; `$script:AuthorizationConsumed = $true`,
`authorization_consumed.json` and `Start-Process` follow it. Consequently the
earlier failed invocation performed no attach, opened no USB device, started no
real capture and did not consume that one-run authorization. This historical
state is distinct from the latest, consumed TShark race failure described
above.

## Empty-array class correction and audit

`Write-OemLogSnapshot`, `Write-FileSnapshot`, `Get-TargetedFiles` and the new
shared `Invoke-D255PreAuthorizationEvidenceSetup` now state their empty-array
contracts explicitly. `Write-D255JsonArray` serializes a zero-row snapshot as
literal `[]`, avoiding a second empty-input binding ambiguity. Capture
interfaces remain semantically non-empty: binding is accepted so the function
can issue the explicit D255 failure instead of a generic PowerShell binder
error.

| FUNCTION_OR_PARAMETER | CAN_BE_EMPTY_IN_REAL_RUN | CURRENT_BEHAVIOR | FIX_OR_JUSTIFICATION | TEST |
| --- | --- | --- | --- | --- |
| top-level `OemLogPath` | yes | optional `@()` | unchanged; discovery may still yield zero | zero-log preflight/static contract |
| resolved OEM candidate list / `Write-OemLogSnapshot.Candidates` | yes | empty snapshot allowed | `AllowEmptyCollection`; writes `[]`, no fictitious log | shared-path ABSENT simulation contract |
| top-level `CacheRoot` | yes | optional user list; built-in roots still resolved | unchanged; unreadable explicit roots remain fail-closed | static contract |
| `Get-TargetedFiles.Roots` / `Write-FileSnapshot.Roots` | yes at function boundary | zero files is valid | explicit empty support and `[]` metadata | empty-root simulation contract |
| shared setup `OemLogCandidates` / `CacheRoots` | yes | empty evidence sources allowed | `AllowEmptyCollection` on both | horizontal contract test |
| top-level/shared capture interface lists | no in live/preflight | terminal if zero | generic binding replaced by explicit `at least one capture interface` failure; simulator supplies synthetic selector | capture-interface and shared-setup tests |
| USBPcap candidates / selector matches | no | terminal if zero/ambiguous | unchanged safety/provenance gate | single/capture-all tests |
| UI choice, marker and manifest event collections | no external empty binding; internally constructed | fixed enumerations or naturally empty output lists | no change required | static syntax/safety and postprocessor tests |

No additional pre-authorization gate was removed. Guest absence/topology,
USBPcap closure, account/PIN policy, explicit-path readability, runtime,
output collision/free space, exact authorization and capture-process liveness each
protect device safety, evidence provenance or executable closure. The prior
mandatory OEM-log existence requirement was the ceremonial gate and remains
removed. The only post-start gate removed is the requirement that the capture
file be created within two seconds; it protected no device-side condition.
The other local timing gates are retained: the bounded duration constrains the
capture and the 30-second post-attach PnP deadline checks actual target
enumeration rather than host file buffering.

## Shared live-path pre-authorization simulation

`-PreAuthorizationSimulationOnly` creates only synthetic cache/log fixtures,
rejects authorization, TShark, real interface selectors and real evidence
paths, and invokes the same `Invoke-D255PreAuthorizationEvidenceSetup` function
used by the live branch. It stops before the authorization comparison and
before `Start-Process`. ABSENT and PRESENT modes respectively require:

```text
EMPTY_OEM_LOG_CANDIDATES_BINDING=PASS
PRESENT_OEM_LOG_SNAPSHOT=PASS
EMPTY_CACHE_ROOTS_BINDING=PASS
AUTHORIZATION_CONSUMED=false
REAL_CAPTURE_STARTED=false
REAL_USB_OPEN_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
```

The Linux host has no `pwsh`/`powershell`, so this revision verifies the shared
control flow, empty-collection attributes, explicit JSON-array handling and
safety boundary with the fallback parser/static suite. Native Windows runs of
both simulation states remain required before `READY_FOR_OPERATOR_RUN=true`.

## OEM log and Goodix cache availability

The real Windows preflight had already established a passing D255 self-test,
zero hardware actions, unconsumed authorization, one USBPcap interface and a
readable `C:\ProgramData\Goodix` cache root, but no `goodix*.log` or
`wbdi*.log`. The launcher incorrectly converted that optional evidence absence
into a terminal preflight gate.

The earlier optionality correction removed only the zero-source gate; this
class correction also makes the live snapshot binding itself empty-safe. Explicitly
supplied unreadable `-OemLogPath` and `-CacheRoot` values still fail before
authorization. Automatic discovery and before/after snapshots remain active
when logs exist. Preflight V4 and sanitized output now classify the sources
independently:

```text
OEM_LOG_STATUS=PRESENT|ABSENT
OEM_LOG_SOURCE_COUNT=<n>
GOODIX_CACHE_STATUS=PRESENT|ABSENT
GOODIX_CACHE_SOURCE_COUNT=<n>
```

Empty log/cache metadata is serialized as a valid JSON array. The offline
postprocessor accepts a manifest with no OEM-log files, preserves cache/wire
analysis and reports `OEM_LOG_TIME_CORRELATION=UNAVAILABLE_NO_OEM_LOG` instead
of inventing log evidence. No USB, VM, capture, authorization, single-shot or
cleanup gate was weakened.

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
after USBPcap interface closure, and all explicitly configured path, disk and
runtime gates still precede exact authorization and TShark start. Optional
log/cache availability is reported rather than used as a gate.

After capture-process readiness, one manual attach and guest PnP proof, the postprocessor
requires exact target A8 APP12509 before the passive-bootstrap marker. Only
then does the launcher open a structured four-choice UI gate:

```text
POSTATTACH_HELLO_UI_GATE=READY_WAITING_FOR_FINGER|UI_UNAVAILABLE|NEW_PIN_REQUIRED|UNEXPECTED_PREREQUISITE
AUTHORIZATION_GATE_ORDER=GUEST_ABSENCE->USBPCAP_INTERFACE_CLOSURE->ACCOUNT_PREREQUISITES->EXPLICIT_PATHS_DISK_RUNTIME->SOURCE_AVAILABILITY_REPORT->EXACT_AUTHORIZATION->CONSUMPTION->CAPTURE_START->SINGLE_ATTACH->PNP->WIRE_A8->PASSIVE_BOOTSTRAP->HELLO_UI_GATE
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
POWERSHELL51_COMPATIBILITY_STATUS=PASS_STATIC_CONTRACT; CORRECTED_NATIVE_SELFTEST_AND_PREFLIGHT_PENDING_WINDOWS
EMPTY_ARRAY_CLASS_AUDIT=PASS_STATIC_AND_SYNTHETIC_CONTRACT
SHARED_PREAUTHORIZATION_SIMULATION=IMPLEMENTED_NOT_EXECUTED_ON_NATIVE_WINDOWS
WBDI_MMDD_CANCEL_CORRELATION_TEST=PASS
OEM_LOG_ROTATION_TESTS=PASS
```

The dedicated D255 suite passes 54 tests, including the missing-file,
zero-byte-file, exited-process, post-attach materialization and strong final
validation contracts. D252/D253 audits, the five-test D254
suite, the full supported repository suite and `git diff --check` pass. Native
PowerShell is unavailable on this Linux host; `-SelfTestOnly` and
the corrected `-PreflightOnly` plus both `-PreAuthorizationSimulationOnly`
states therefore remain future guest checks after review. The pre-correction
native self-test was observed PASS in the VM, but it does not substitute for
rerunning the corrected file. The next native evidence must first exercise
`-SelfTestOnly` and confirm `D255_CAPTURE_READINESS_SELFTEST=PASS`; after
AI-PM review and approval of an exact new live-critical commit, any live run
requires a new explicit one-run authorization. No successful real capture
exists.

```text
BOOTSTRAP_CLOSED=false
RESTORE_CLOSED=false
D255_LIVE_PATH_ATTEMPT=FAILED_PREATTACH_AFTER_TSHARK_START
D255_LIVE_CAPTURE=NOT_PERFORMED
D255_HARDWARE_BOUNDARY=NOT_AUTHORIZED

AUTHORIZATION_CONSUMED=true
GOODIX_ATTACHED_TO_VM=false
SENSOR_REACHING_ACTION=false
REAL_WINDOWS_CAPTURE_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_PERSISTENT_WRITE_FAMILY_COUNT=0
```
