# D256 — Offline USB lifecycle contract audit

## Outcome

`READY`: the complete 218-packet D255 pcapng was parsed offline and the 206
USBPcap packets belonging to the target `bus 1 / device 2` were rendered as a
sanitized metadata timeline.  The raw pin is verified at 27,684 bytes and
SHA-256 `802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`;
hash, size and mtime remained unchanged.

The minimum observed contract is:

```text
accepted 0x32 arm (frame 198)
→ operator cancel interval with zero target USBPcap packets
→ one canceled pending bulk-IN completion (frame 202)
→ same bus/device and bulk endpoints
→ re-entry traffic
→ accepted new 0x32 (request frame 214, ACK frame 216)
```

The canceled bulk-IN completion is positive evidence of host-request
cancellation.  It is not an abort-pipe URB, reset, reconfiguration,
re-enumeration, descriptor replay or proven device-side disarm.

## Primary USBPcap audit

All function codes observed in the capture are retained numerically.  The
semantic names in the timeline are limited to the corresponding Windows WDK
`URB_FUNCTION` ABI values carried by USBPcap; the audit returns
`SEMANTICS_UNRESOLVED` for any value outside its bounded table.  In the
critical frame-198→216 window all 19 target packets have function `0x0009`
(`BULK_OR_INTERRUPT_TRANSFER`).  There are no functions for select
configuration/interface, control transfer, descriptor fetch, abort pipe,
reset pipe or clear stall.

The target remains `1:2` and uses only bulk OUT `0x01` and bulk IN `0x81`.
There is no device descriptor replay and no second enumeration episode.
Consequently D256 proves transport continuity and the acceptance of re-arm
without an explicit USB restore; it does not prove that the prior internal arm
was cleared, expired or overwritten.

```text
USBPCAP_LIFECYCLE_AUDIT=PASS_COMPLETE_TARGET_PACKET_TIMELINE
CANCEL_TO_REENTRY_DEVICE_CONTINUITY=SAME_BUS_DEVICE_AND_BULK_ENDPOINTS
HOST_SIDE_PENDING_BULK_IN_CANCELLATION_OBSERVED=true
EXPLICIT_USB_RESTORE_OBSERVED=false
ABORT_OR_RESET_OBSERVED=false
REENUMERATION_OBSERVED=false
REENTRY_WITHOUT_EXPLICIT_USB_RESTORE_PROVEN=true
NEW_FDT_ARM_ACCEPTED_ON_REENTRY=true
RESTORE_REQUIRED_FOR_REENTRY=false
PRIOR_ARM_DISARM_PROVEN=false
PRIOR_ARM_LIFETIME_AFTER_CANCEL=UNOBSERVED
SAFE_STOP_AFTER_FDT_ARM=UNRESOLVED
```

`RESTORE_REQUIRED_FOR_REENTRY=false` is bounded to the observed OEM path: the
new arm was accepted without an explicit USB restore.  It is not a universal
claim that restoration is useless or that stopping after an arm is safe.

## Controls `0x50` and `0x97`

Neither control is a new D255 discovery.  Both were already in the D230 census
and were only absent from the local `KNOWN_CONTROLS` allowlist used by the
D255 sanitizer.

| control | D255 occurrence | wire contract | correlation | bounded class |
| --- | --- | --- | --- | --- |
| `0x50` | frame 150, one OUT | A0, payload 2, logical 10, physical 64 | ACK frame 152 `B0/50/01`; A0/50 logical/physical 2417 follows at frame 154 | D230-known sensor/mode family; exact semantics unresolved; bootstrap-local and not lifecycle restore |
| `0x97` | frame 40, one OUT | A0, payload 2, logical 10, physical 64 | no ACK or response before the next OUT | builder-proven wire coordinate of logical `SetDriverState` `0x96`; initial-query-local and not lifecycle restore |

The bounded D230 static anchor for `0x97` is `SetDriverState` at
`0x18005c724`, with immediate A0 builder callsites `0x18005c83e` and
`0x18005c8d0`.  D230 has no dedicated fixed `0x50` builder; its exact dynamic
mode semantics remain unresolved.  No open-ended DLL reverse engineering was
performed.

## Bounded static corroboration

The already identified `gfOnCancel` slice
`0x18001fa90..0x18001fd31` was checked again.  It contains no direct call to
the known A0 builders.  Already indexed D0 lifecycle strings exist in the DLL,
but strings do not prove that D0Entry/D0Exit occurred in D255 and no direct
USB restore dataflow emerged.

```text
gfOnCancel=HOST_REQUEST_CANCELLATION_NO_DIRECT_A0_SEND_PROVEN
STATIC_LIFECYCLE_CORROBORATION=EXHAUSTED_NO_NEW_DATAFLOW
```

The pcapng remains the primary source for the bus behavior actually observed.

## Bootstrap claim

The D255 target cache result is preserved without promoting correlation to
causality.  The 13,520-byte `goodix.dat` layout and CRC are valid, its OTP
prefix matches the target, and its sanitized FDT12 value equals the first D255
wire seed.  This establishes
target binding, layout validity and equality for the first `0x36` of this cold
attach.  The callback/dataflow causality and any general freshness or lifetime
remain unproved.

```text
BOOTSTRAP_CACHE_LAYOUT_TARGET_VALID=true
BOOTSTRAP_CACHE_OTP_BOUND=true
BOOTSTRAP_CACHE_FDT12_EQUALS_FIRST_WIRE_SEED=true
BOOTSTRAP_SEED_SOURCE_CORRELATED=true
BOOTSTRAP_SEED_DATAFLOW_CAUSALITY_PROVEN=false
BOOTSTRAP_SEED_FRESHNESS_SCOPE=FIRST_0x36_IN_THIS_D255_COLD_ATTACH_ONLY; GENERAL_LIFETIME_UNPROVEN
BOOTSTRAP_SEED_SOURCE_STATUS=TARGET_CACHE_WIRE_CORRELATION_PROVEN_CAUSALITY_UNPROVEN_FRESHNESS_NOT_GENERALIZED
```

## Residual boundary

The former search for a required restore before OEM re-entry is exhausted by
the current corpus.  The narrowed blocker is terminal-stop behavior and the
lifetime of a prior FDT arm when no subsequent re-arm occurs.  D256 neither
requests an equivalent new capture nor creates a D257/operator kit.

```text
CURRENT_CORPUS_EXHAUSTED_FOR_THIS_RESTORE_QUESTION=true
STRATEGIC_BLOCKER=DETERMINE_TERMINAL_STOP_BEHAVIOR_AND_PRIOR_ARM_LIFETIME_WHEN_NO_SUBSEQUENT_REARM_OCCURS
```

## Verification and safety

The audit was executed from the repository root against the real hash-gated
raw.  Eight D256 tests cover the known packet decode, direction/endpoint/
transfer, unresolved function handling, marker boundaries, continuity versus
re-enumeration, `0x50`/`0x97`, sanitizer and raw immutability.  Three narrowly
relevant D255 regressions also pass.  `git diff --check` is part of final
closure.

```text
EXECUTABLE_CLOSURE=PASS_OFFLINE
REAL_USB_OPEN_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
```
