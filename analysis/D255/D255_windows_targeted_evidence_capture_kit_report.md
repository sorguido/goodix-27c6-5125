# D255 corrective Windows targeted evidence acquisition kit report

## Outcome

```text
OUTCOME=READY; CORRECTIVE_KIT_PREPARED_FOR_NEW_AI_PM_REVIEW
ADVANCEMENT=NON_HARDWARE_EXECUTABLE_CORRECTION; NO_NEW_DEVICE_EVIDENCE
EXECUTABLE_CLOSURE=PASS_OFFLINE_STATIC_AND_SYNTHETIC; NATIVE_WINDOWS_SELFTEST_PENDING_AI_PM_REVIEW
RESIDUAL_BLOCKER_OR_RISK=NO_REAL_WINDOWS_CAPTURE; POWERSHELL_NATIVE_RUNTIME_NOT_AVAILABLE_ON_LINUX_HOST
CANONICAL_DOCUMENTATION=UPDATED; D255_CURRENT_STATE_AND_CORRECTIVE_HISTORY
BUNDLE=analysis/D255/D255_windows_targeted_evidence_capture_kit_bundle.zip; SHA256=STEP_LOCAL_SIDECAR

INITIAL_HEAD=08edf292fde7404bb86422b43dd2075cc29d359d
D255_INITIAL_AI_PM_REVIEW=FAIL_EXECUTABILITY_AND_TIME_CORRELATION
D255_CORRECTIVE_STATUS=READY_FOR_AI_PM_REVIEW
READY_FOR_AI_PM_REVIEW=true
```

The first D255 bundle was not approved for hardware. Its advertised Windows
PowerShell 5.1 support depended on modern .NET APIs, and its ISO-only OEM-log
parser could not correlate the observed Goodix `[MMDD-HH:MM:SS:mmm]` format.
This corrective revision closes both implementation gaps without Windows,
USB, VM, TShark, network, or device execution. A new AI-PM review is still
required; this status is not `READY_FOR_OPERATOR_RUN`.

## Corrective implementation

The launcher now supports Windows PowerShell 5.1 and PowerShell 7+ using
`SHA256.Create()`/`ComputeHash()`, `BitConverter`, and a canonical relative-path
helper based on `Path.GetFullPath`. The helper requires the child path to start
with the normalized base plus a directory separator, so sibling prefixes such
as `C:\run2` are rejected for `C:\run`. It never calls `Path.GetRelativePath`.

`-SelfTestOnly` is independent from `-PreflightOnly` and needs no target,
authorization, or TShark selector. It checks runtime edition/version, the
SHA-256 `abc` known answer, relative path success, sibling-prefix rejection,
clock-anchor creation/parsing, JSON serialization, and collision semantics.
The self-test is implemented but could not be natively executed because this
Linux host has neither `powershell` nor `pwsh`.

```text
POWERSHELL51_API_AUDIT=PASS; ALL_USED_RUNTIME_APIS_AVAILABLE_TO_WINDOWS_POWERSHELL_5_1_OR_REPLACED
POWERSHELL51_UNSUPPORTED_API_COUNT=0
POWERSHELL51_COMPATIBILITY_STATUS=PASS_STATIC_CONTRACT; NATIVE_SELFTEST_PENDING_WINDOWS
POWERSHELL7_COMPATIBILITY_STATUS=PASS_STATIC_CONTRACT; NATIVE_SELFTEST_PENDING_WINDOWS
POWERSHELL_SELFTEST_MODE=IMPLEMENTED_NOT_EXECUTED; POWERSHELL_RUNTIME_UNAVAILABLE_ON_HOST
POWERSHELL_SELFTEST_HARDWARE_ACTION_COUNT=0
```

The future live branch now performs, in order, tool/interface/path/disk/log
gates, target-absence gate, run directory and clock anchor, OEM-log before
snapshot, cache before snapshot, runtime self-check, and remaining non-hardware
setup. Only then does it test the exact authorization, record consumption, and
attempt to start TShark. Every pre-consumption failure emits
`D255_AUTHORIZATION_CONSUMED=false`; a TShark start failure after consumption
consumes the one run and cannot auto-retry.

```text
AUTHORIZATION_GATE_ORDER=TOOL_INTERFACE_PATH_DISK_LOG->TARGET_ABSENCE->CLOCK_AND_LOG_CACHE_BEFORE_SNAPSHOTS->RUNTIME_SELF_CHECK->ALL_SETUP_COMPLETE->EXACT_AUTHORIZATION->CONSUMPTION_RECORD->TSHARK_START->FUTURE_ATTACH
AUTHORIZATION_CONSUMED_BEFORE_HARDWARE=true; CONSUMED_IMMEDIATELY_BEFORE_TSHARK_START
```

The launcher writes a pre-capture `run_clock.json` and `CLOCK_ANCHOR` marker,
then a post-capture `run_clock_end.json` consistency anchor. It captures
before/after OEM-log size, SHA-256 and mtime metadata and retains both raw
snapshots local-only. The postprocessor compares exact bytes and reports
unchanged, append/growth, truncation, or replacement/rotation. Only a verified
append delta is correlated as a new log window.

The sanitizer now recognizes ISO-8601 with an explicit offset/Z and Goodix
`[MMDD-HH:MM:SS:mmm]`. Goodix local timestamps gain a UTC instant only when
the explicit run year, UTC offset, Windows timezone ID, start/end clock
anchors, and marker window select exactly one candidate. Same-day, midnight,
and unambiguous year rollover are covered. Offset changes, malformed/out-of-
window dates, or non-reconstructible log rotation fail closed without timezone
or year invention.

Each sanitized OEM event contains only event label, source/line index,
`timestamp_source`, `timestamp_utc`, `time_correlation_quality`, and bounded
window classification; the raw line is never exported. If a critical
restore/cancel event cannot be anchored, the result forces
`RESTORE_MODEL=INCONCLUSIVE_OEM_TIME_CORRELATION`, `RESTORE_CLOSED=false`, and
does not promote host-only cancel or USB-close claims.

## Verification

```text
PYTHON_COMPILE=PASS
D252_REPRODUCIBLE_AUDIT=PASS
D253_REPRODUCIBLE_AUDIT=PASS
D254_DEDICATED_TESTS=PASS; TESTS=5
D255_DEDICATED_EXPANDED_TESTS=PASS; TESTS=27
FULL_SUPPORTED_UNIT_SUITE=PASS; TESTS=172
GIT_DIFF_CHECK=PASS
POWERSHELL_NATIVE_SYNTAX_AND_SELFTEST=NOT_AVAILABLE_ON_LINUX_HOST
POWERSHELL_FALLBACK_STATIC_SYNTAX_AND_CONTRACT=PASS
```

The synthetic Goodix fixture uses the requested realistic sequence:
`[0822-08:14:10:100] gfOnCancel`,
`[0822-08:14:10:130] D0Exit`, and
`[0822-08:14:10:900] D0Entry`. All three map to UTC, with cancel/D0Exit in the
cancel window and D0Entry in re-entry. The same fixture produces eight
timestamped recognized events and zero untimed events.

```text
OEM_LOG_TIMESTAMP_FORMATS=ISO8601|GOODIX_MMDD_LOCAL
OEM_LOG_TIMESTAMPED_EVENT_COUNT_SYNTHETIC=8
OEM_LOG_UNTIMED_EVENT_COUNT_SYNTHETIC=0
OEM_LOG_TIME_CORRELATION_SYNTHETIC=EXACT_ANCHORED
WBDI_MMDD_CANCEL_CORRELATION_TEST=PASS
WBDI_MIDNIGHT_ROLLOVER_TEST=PASS
WBDI_YEAR_ROLLOVER_TEST=PASS
WBDI_AMBIGUITY_FAIL_CLOSED_TEST=PASS
OEM_LOG_ROTATION_TESTS=PASS; UNCHANGED|GREW|TRUNCATED|REPLACED_OR_ROTATED
```

## Safety and unresolved boundary

No corrective command opened USB or ran Windows/OEM software. Bootstrap and
restore remain open until a separately reviewed and explicitly authorized
single Windows OEM capture supplies primary target evidence.

```text
BOOTSTRAP_CLOSED=false
RESTORE_CLOSED=false
D255_LIVE_EXECUTION=NOT_PERFORMED
D255_HARDWARE_BOUNDARY=NOT_AUTHORIZED

REAL_WINDOWS_CAPTURE_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_TLS_HANDSHAKE_COUNT=0
REAL_D4_SEND_COUNT=0
REAL_AF_SEND_COUNT=0
REAL_FDT_SEND_COUNT=0
REAL_IMAGE_COMMAND_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_PERSISTENT_WRITE_FAMILY_COUNT=0
```
