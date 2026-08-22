# D255 Windows targeted evidence acquisition kit report

## Outcome

```text
OUTCOME=READY
ADVANCEMENT=NON_HARDWARE_EXECUTABLE_EVIDENCE_ACQUISITION_PREPARATION
EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC_AND_STATIC; WINDOWS_RUNTIME_PENDING_FUTURE_AUTHORIZED_RUN
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=analysis/D255/D255_windows_targeted_evidence_capture_kit_bundle.zip; SHA256=RECORDED_IN_STEP_LOCAL_SIDECAR
D255_OUTCOME=WINDOWS_EVIDENCE_ACQUISITION_KIT_PREPARED
D255_LIVE_EXECUTION=NOT_PERFORMED
D255_HARDWARE_BOUNDARY=NOT_AUTHORIZED
READY_FOR_AI_PM_REVIEW=true
```

D255 prepared a fail-closed Windows collection script and an independent Linux
offline sanitizer.  It performed no Windows capture or local hardware action.
The bootstrap and restore blockers remain open until a future operator run
produces target-specific primary evidence.

## Initial state and historical evidence

```text
INITIAL_HEAD=7322f405735986d78b1ac3d14fd355695b0e0019
INITIAL_BRANCH=main
INITIAL_WORKTREE=CLEAN
PREVIOUS_CAPTURE_METHOD=WINDOWS_OEM_COLD_ATTACH_CAPTURE; EXACT_LAUNCH_PROCEDURE_NOT_RETAINED
PREVIOUS_CAPTURE_TOOL=USBPCAP_PCAPNG_FORMAT; WIRESHARK_TSHARK_VERSION_UNKNOWN
PREVIOUS_CAPTURE_BOUNDARY=BEFORE_USB_ENUMERATION_THROUGH_OEM_INIT_AND_IMAGE_CYCLES; NO_EXPLICIT_CANCEL_WINDOW
RECOMMENDED_D255_CAPTURE_METHOD=TSHARK_WITH_USBPCAP_IN_WINDOWS_VM_STARTED_BEFORE_REVIEWED_GUI_USB_ATTACH
```

The surviving primary capture is a USBPcap pcapng recovered from the
operator-provided `GoodixExport.zip`.  The manual classifies it and one now
missing independent capture as cold attach.  The current repository does not
retain the old launch command, tool version, VM product, passthrough command,
or log path.  D255 therefore reuses only the proved capture format and boundary
and records every previously missing selector explicitly.

The D255 parser read the surviving primary capture in a read-only smoke test:
255 USBPcap packets, 107 reconstructed A0/B0 frames, one unambiguous bus/device
pair, and exact A8 identity `GF_ST411SEC_APP_12509`.  No raw payload was emitted.

## Methodological pre-live review

1. **What changes relative to the last attempt?**  The next action observes the
   normal Windows OEM producer, host cache, OEM log, and USB wire together; it
   does not replay another Linux FDT sequence.
2. **What new hypothesis is tested?**  The first APP12509 `0x36` seed is equal
   to and temporally sourced from the FDT12 field of an OTP-bound host cache;
   normal UI cancel is either host-only plus close or has an observable bounded
   device command sequence followed by deterministic re-entry.
3. **What happens if it fails at the same point?**  No retry.  Missing seed or
   restore evidence leads to targeted cache/log/trigger analysis; it does not
   authorize another Linux FDT live attempt.

## Capture design

```text
COLD_INIT_TRIGGER=WINDOWS_VM_NORMAL_USB_COLD_ATTACH_WITH_USBPCAP_ALREADY_ACTIVE
DEVICE_SIDE_EFFECT_CLASS=NORMAL_OEM_ENUMERATION_AND_VOLATILE_SESSION_INITIALIZATION
FACTORY_PRESERVING_EVIDENCE=HISTORICAL_TARGET_COLD_ATTACH_CAPTURES_PLUS_NO_MAINTENANCE_COMMAND_REQUESTED; NOT_ABSOLUTE_DEVICE_NVM_PROOF
WINDOWS_COMPATIBILITY_RISK=LOW_BUT_NONZERO_NORMAL_ATTACH_RISK; NO_PERSISTENT_CHANGE_INTENDED
WINDOWS_CAPTURE_TOOL=TSHARK_WITH_USBPCAP_EXTCAP
WINDOWS_OEM_LOG_SOURCE=EXPLICIT_OR_TARGETED_DISCOVERY_OF_WBDI.LOG/_WBDI_.LOG; EXACT_TARGET_PATH_UNKNOWN_UNTIL_PREFLIGHT
BASEFILE_DISCOVERY_METHOD=READ_ONLY_TARGETED_GOODIX_ROOT_SCAN_PLUS_13520_BYTE_LAYOUT_VALIDATION
TARGET_FIRMWARE_PROOF_METHOD=A8_QUERY_REPLY_IN_CAPTURE_MUST_EQUAL_GF_ST411SEC_APP_12509
OPERATOR_MARKER_METHOD=UTC_TSV_MARKERS_WRITTEN_AROUND_EACH_GUI_BOUNDARY
CANCEL_NO_FINGER_METHOD=NORMAL_WINDOWS_HELLO_UI_CANCEL_BETWEEN_EXACT_MARKERS
REENTRY_PROOF_METHOD=REOPEN_NORMAL_WINDOWS_HELLO_UI; PREFER_WIRE_REARM_WITHOUT_FINGER
```

Cold attach is selected because the historical target evidence is already
classified at that boundary and the capture can begin before enumeration.
Windows Biometric Service restart and PnP disable/enable are documented but not
selected: the repository does not prove that either reproduces the complete
target init, and PnP mutation is less conservative.  No host wrapper is added
because no canonical hypervisor command is preserved.

The PowerShell script requires one exact authorization, creates a unique
directory, refuses collisions and ambiguous selectors, requires a readable OEM
log source, snapshots only targeted Goodix roots, starts bounded-duration
TShark before VM attach, and separates every GUI action with UTC markers.  It
does not automate service restart, PnP, VM control, Windows Hello, firmware, or
device commands.  `-PreflightOnly` performs tool/path/interface/disk/log/target
checks with the target required absent from the guest.

## Offline sanitizer

`d255_postprocess_windows_evidence.py` has no USB, TLS, network, subprocess, or
firmware path.  It:

- verifies the manifest and every raw input SHA-256 before parsing;
- parses USBPcap pcapng without external packages and selects the target by A8;
- reconstructs logical A0 frames and physical `0x36` submissions/tails;
- validates the hypothesized `64+12+3200+10240+4` cache layout and
  CRC-32/MPEG-2 in either stored byte order;
- compares the first wire FDT12 with cache and already printed OEM log values;
- correlates arm, no-finger cancel, close/reset/idle/rearm, and re-entry;
- emits allowlisted OEM event labels and hashes, never log lines, OTP, image,
  TLS, PSK, secret, or biometric payloads.

Equality is explicitly reported as correlation, not causal proof.  Missing or
wrong A8 identity is terminal and produces no sanitized evidence directory.

## Verification

`pwsh` and Windows PowerShell are unavailable on this Linux host, so the prompt-
approved fallback static PowerShell lexer/contract checks were used.  A real
Windows `-PreflightOnly` invocation remains part of the future operator phase,
not evidence acquired during D255.

```text
PYTHON_COMPILE=PASS
D252_REPRODUCIBLE_AUDIT=PASS
D253_REPRODUCIBLE_AUDIT=PASS
FULL_REPOSITORY_UNIT_SUITE=PASS; TESTS=172
D254_DEDICATED_TESTS=PASS; TESTS=5
D255_DEDICATED_TESTS=PASS; TESTS=15
D255_REAL_PRIMARY_CAPTURE_READ_ONLY_SMOKE=PASS; PACKETS=255; FRAMES=107; FIRMWARE=GF_ST411SEC_APP_12509
POWERSHELL_NATIVE_SYNTAX_CHECK=NOT_AVAILABLE
POWERSHELL_FALLBACK_STATIC_SYNTAX_AND_CONTRACT=PASS
```

Covered negative cases include wrong cache size, CRC failure, mismatched seed,
missing A8, missing cancel marker, cancel before arm, absent re-entry, unknown
control, manifest mutation, output collision, missing/wrong authorization, and
raw biometric/OTP/secret redaction.

## Authorization and safety

```text
D255_OPERATOR_AUTHORIZATION_REQUIRED=true
D255_AUTHORIZATION_CONSUMED_ON_START=true
D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true

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

AI-PM review of this kit is not authorization.  A future run requires baseline
approval and a new explicit user authorization for one Windows OEM capture.
