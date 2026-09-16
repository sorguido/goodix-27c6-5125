# D256 corrective — terminal-cancel / post-arm quiescence closure

## Outcome

`READY`: the existing D255 raw was re-audited offline without modification.
The corrective closes the observed OEM host/bus terminal-stop contract as
path-bounded USB quiescence. It does not claim that the sensor internally
disarmed or expired its FDT mode.

The raw remains 27,684 bytes, 218 readable frames and SHA-256
`802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`.
All 206 target USBPcap packets are retained as sanitized metadata; raw payload,
cache, OTP, PSK and biometric material remain excluded.

## Two distinct cancel contracts

The first D256 result remains valid and is explicitly path-bounded:

```text
accepted 0x32 frame 198
→ first operator cancel with zero target packets
→ pending bulk-IN completion canceled at frame 202
→ same device/endpoints through re-entry
→ accepted new 0x32 request/ACK at frames 214/216
```

Therefore:

```text
REENTRY_WITHOUT_EXPLICIT_USB_RESTORE_PROVEN=true
RESTORE_REQUIRED_FOR_REENTRY=false
```

The corrective adds the terminal window:

```text
new 0x32 frame 214
→ accepted ACK frame 216
→ pending bulk-IN submission frame 217
→ REENTRY_WAITING_NO_FINGER / REENTRY_CANCEL_BEGIN
→ REENTRY_CANCEL_END / REENTRY_END / OPERATOR_PHASES_COMPLETE
→ canceled bulk-IN completion frame 218
→ end of raw capture, with no further packet
```

Frame 218 is the last frame of the 218-frame pcapng. The TShark stderr records
`218 packets captured`; preflight records a 600-second duration and the final
host marker occurs 602.543790 seconds after `CAPTURE_PROCESS_STARTED`. The raw
therefore remained at frame 218 through final capture closure at the configured
duration boundary.

The marker-derived interval from frame 218 to the `RUN_FAILED` host
finalization marker is 491.125998 seconds. This is the reported
`POST_TERMINAL_CANCEL_CAPTURE_WINDOW_SECONDS`; the exact process-exit timestamp
was not recorded, so the value is explicitly a last-frame-to-finalization-marker
interval rather than a fabricated device timestamp. `RUN_FAILED` is used only
as host-side boundary/finalization evidence.

## Derived terminal-window evidence

| Observation | Result |
| --- | ---: |
| ACK new arm → terminal cancel begin | 7.007266 s |
| terminal cancel begin → end | 7.170485 s |
| terminal cancel end → canceled completion | 7.559943 s |
| canceled completion → host finalization marker | 491.125998 s |
| all/target packets during terminal operator cancel | 0 / 0 |
| packets after cancel end, before completion | 0 |
| packets from cancel end through completion | 1, frame 218 |
| all/target packets after frame 218 | 0 / 0 |
| non-bulk URBs in frame-214→218 target window | 0 |
| abort/reset/reconfiguration/descriptor events | 0 |
| target continuity | bus/device `1:2`, endpoints `0x01/0x81` |

The only terminal completion is function `0x0009`, endpoint `0x81`,
`USBD_STATUS_CANCELED`. It is positive evidence that the host canceled the
pending bulk-IN request. No device-side restore command, pipe abort/reset,
clear-stall, control/descriptor/configuration/interface transition or
re-enumeration is observed.

```text
TERMINAL_CANCEL_PENDING_BULK_IN_CANCELED=true
EXPLICIT_USB_TERMINAL_RESTORE_OBSERVED=false
TERMINAL_CANCEL_ABORT_OR_RESET_OBSERVED=false
TERMINAL_CANCEL_REENUMERATION_OBSERVED=false
POST_TERMINAL_CANCEL_CAPTURE_WINDOW_SECONDS=491.125998
POST_TERMINAL_CANCEL_TARGET_USB_PACKET_COUNT=0
POST_TERMINAL_CANCEL_TOTAL_PACKET_COUNT=0
OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN=true
```

This proves the OEM host/bus behavior for the observed zero-finger path: the
pending read is canceled and the bus remains quiescent for the rest of the
capture. USB silence does not expose the sensor's volatile internal FDT state.

## Decomposed stop decision

The former opaque `SAFE_STOP_AFTER_FDT_ARM=UNRESOLVED` is superseded by four
separate decisions:

1. Host/bus terminal-stop contract:
   `CLOSED_OBSERVED_PATH_BOUNDED_USB_QUIESCENCE`.
2. USB quiescence:
   `OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN=true`.
3. Internal state:
   `PRIOR_ARM_DISARM_PROVEN=false`,
   `PRIOR_ARM_LIFETIME_AFTER_CANCEL=UNOBSERVED`,
   `DEVICE_INTERNAL_FDT_STATE_AFTER_CANCEL=UNOBSERVED`.
4. Factory persistence:
   no new device-side factory-persistence claim follows from USB silence; the
   existing factory-preserving requirements remain unchanged.

This is Task E `Caso A`: no observable host/bus terminal-stop component is
missing in the current corpus. The residual unknown is internal volatile state.
A future AI-PM review may therefore assess separately factory-preserving and
Windows-compatibility requirements, internal-disarm requirements and FDT
live-readiness. D256 does not authorize an FDT live run or an operator kit.

## URB classification corrective

The semantic table now includes:

```text
0x0002  URB_FUNCTION_ABORT_PIPE
0x001e  URB_FUNCTION_SYNC_RESET_PIPE_AND_CLEAR_STALL
0x0030  URB_FUNCTION_SYNC_RESET_PIPE
0x0031  URB_FUNCTION_SYNC_CLEAR_STALL
```

No local WDK header, Wireshark source tree or TShark binary is installed on the
offline Linux host, so the requested local independent provenance check is
recorded as `UNAVAILABLE_ON_OFFLINE_LINUX_HOST`; no network source was used.
None of these numeric codes occurs in the terminal window, which contains only
`0x0009`, so this parser robustness correction does not change the empirical
D256 result.

## Verification and supersession

The real hash-gated audit passes, as do 13 focused D256 tests and the three
narrow D255 regressions. Tests cover both cancel contracts, marker order,
frames 214/216/217/218, final-frame status, zero packets during and after the
terminal cancel, derived durations, reset/abort classification, sanitizer and
raw hash/size/mtime immutability. `git diff --check` is part of final closure.

The previous `D256_offline_usb_lifecycle_contract_audit_bundle.zip` is
`SUPERSEDED_BY_D256_TERMINAL_CANCEL_CORRECTIVE` and remains preserved. The
current step-local review artifact is
`D256_terminal_cancel_corrective_bundle.zip`.

```text
EXECUTABLE_CLOSURE=PASS_OFFLINE
CURRENT_CORPUS_EXHAUSTED_FOR_REENTRY_RESTORE_QUESTION=true
CURRENT_CORPUS_EXHAUSTED_FOR_INTERNAL_ARM_LIFETIME_QUESTION=true
REAL_USB_OPEN_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
```
