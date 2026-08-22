# D257 — fresh-FDT candidate consolidation and live-readiness gate

## Closure

```text
OUTCOME=READY_OFFLINE_IMPLEMENTATION_AND_READINESS_DECISION_CLASS_A
ADVANCEMENT=ARCHITECTURAL_IMPLEMENTATION_AND_REAL_OFFLINE_REPLAY_CLOSURE; NO_DEVICE_SIDE_ADVANCEMENT_CLAIMED
EXECUTABLE_CLOSURE=PASS_OFFLINE; LIVE_PATH_NOT_CREATED
RESIDUAL_BLOCKER_OR_RISK=SEED_FRESHNESS_AND_CURRENT_ATTEMPT_PROVENANCE
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md UPDATED ORGANICALLY
BUNDLE=analysis/D257/D257_fresh_fdt_candidate_live_readiness_bundle.zip
```

D257 is entirely offline. It did not enumerate or open USB, start a capture,
attach a VM, contact a sensor, use a finger, read a live secret, mutate
`fprintd`, invoke `sudo`, create an operator kit, or authorize a live run.

## Decision

D257 selects Class A:

```text
FDT_OFFLINE_CANDIDATE_CLOSED=true
HOST_BUS_LIFECYCLE_READY=true
INTERNAL_PRIOR_ARM_STATE=NON_BLOCKING_EPISTEMIC_UNKNOWN
SEED_PROVIDER_IMPLEMENTED=true
SEED_FRESHNESS_IS_SOLE_LIVE_BLOCKER=true
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
```

The internal lifetime/disarm unknown remains factually unchanged. It is not an
implementation blocker because D255/D256 already show the OEM host contract:
cancel the pending receive, emit no restore command, continue through the
OEM-style session state path, accept another `0x32`, and on terminal cancel
cancel the pending bulk-IN and remain USB-quiescent. No concrete additional
factory-state or Windows-compatibility risk is established by the unobservable
internal state alone.

The remaining blocker is narrower: the current corpus contains one target
APP12509 cache snapshot and one correlated first-wire-seed occurrence. That
pair validates this input for the D255 cold attach but cannot establish how
long the FDT12 remains fresh or whether the same snapshot is valid for a
future cold attach.

## Methodological pre-live review

No live run is proposed by this step. For any later review, the required three
answers are:

1. The method changes from an unbounded restore/disarm question to an explicit
   read-only cache input, a code-enforced OEM lifecycle, and a single
   freshness/provenance gate.
2. The new technical hypothesis would be that a cache snapshot proven current
   for that cold attach, with exact target CRC and OTP binding, supplies the
   correct first `0x36` seed without special recovery commands.
3. If a future authorized run failed at that boundary, there would be no retry,
   A2/`0x70` injection or cosmetic re-run. The next action would be offline
   audit of the seed snapshot/provenance and the exact terminal evidence before
   any different experiment.

## Core lifecycle

`core/fdt_lifecycle.py` adds a project-authored GPL offline model with these
states:

```text
INITIALIZED_POST_D4
→ AF_STATE_KNOWN
→ FDT_BOOTSTRAP_SAMPLING
→ FDT_BOOTSTRAP_READY
→ FDT_ARMED_WAIT
→ HOST_WAIT_CANCELED
→ SESSION_REENTRY
→ FDT_ARMED_WAIT
→ HOST_WAIT_CANCELED
→ TERMINAL_STOPPED
```

The independent first-image branch reaches `FIRST_IMAGE_RECEIVED`; an invalid
transition reaches `FAILED_CLOSED`. `FULL_COLD_START_REQUIRED` is a distinct
delegation boundary and cannot be represented as re-entry.

Every transition has a monotonically increasing sequence number and session
generation. Attempt latches precede the abstract transport call. The module
contains no retry loop and its device-command set is only `0x36`, `0x32` and
`0x22`. A2, `0x70`, E0, A4, F0 and F4 are absent from that allowlist. Both
cancel transitions and terminal stop contain zero device commands.

`core/post_d4.py` accepts the lifecycle as an optional observer. On the fresh
path it records the `0x32` arm before submission, records the exact `0x22`
post-IRQ2 attempt before submission, reaches `FIRST_IMAGE_RECEIVED` only after
the canonical image validator succeeds, and fails the lifecycle closed on
event, command or image errors. Historical behavior without the observer is
preserved.

## Explicit seed provider

`core/fdt_seed.py` accepts only a caller-supplied path and caller-supplied
64-byte target OTP identity. It does not search `C:\ProgramData`, use an
environment fallback, derive a seed from a PSK, or contain a D255/Rocky/claimed
12509 constant.

The exact target-observed layout is:

| Region | Offset | Bytes |
| --- | ---: | ---: |
| OTP identity | 0 | 64 |
| FDT12 | 64 | 12 |
| navigation baseline | 76 | 3,200 |
| image baseline | 3,276 | 10,240 |
| CRC-32/MPEG-2, little-endian | 13,516 | 4 |
| total |  | 13,520 |

Validation order is regular explicit file, stable read, exact size/layout,
target-observed little-endian CRC, constant-time OTP match and non-empty FDT12.
Only the FDT12 is returned. Provenance records hashes, size, layout, CRC and
binding status; raw OTP and seed are not rendered. The input file hash and
mtime remain unchanged during the real D255 replay.

Every invalid condition returns `SEED_PROVIDER_RESULT=FAIL_CLOSED` with a
specific reason. There is no zero, random, historical, Rocky, claimed-12509 or
PSK-derived fallback.

## Bounded freshness/source audit

The D230–D256 bounded corpus contains:

- one target cache file of exactly 13,520 bytes;
- one D255 `before` snapshot, with no recoverable `after` snapshot;
- one APP12509 cache-FDT12 ↔ first-`0x36` wire-seed pair;
- no target OEM log for the D255 run;
- no second target session pair from which lifetime can be inferred.

D254 observes validate/refresh/save in a 5110/APP12117 OEM trace. Rockytkg has
a writeback implementation. Both are useful corroboration but neither proves
APP12509 freshness or writeback behavior. The bounded known `gfusb.dll`
call-sites add no target writeback/freshness dataflow beyond D253–D256; no
generalized DLL reverse engineering was performed.

```text
SEED_FRESHNESS_GENERALIZATION=UNPROVEN
CURRENT_CORPUS_EXHAUSTED_FOR_SEED_FRESHNESS_GENERALIZATION=true
```

The minimum future seed precondition is an explicit 13,520-byte snapshot with
the target little-endian CRC valid, exact OTP64 identity binding, and primary
current-cold-attach provenance establishing that its FDT12 is the input for
that attempt. D257 does not itself satisfy that future-current provenance.

## Offline replay scenarios

### Scenario 1 — D255 fresh bootstrap, cancel and re-entry

The replay reads the private D255 cache and capture by hash-gated repository
reference. It extracts the device identity in memory, validates the cache,
and proves that the returned FDT12 equals the first wire seed without emitting
either value. It then replays the three manual FDT stages and the two `0x32`
arms bounding the observed cancel/re-entry contract. All five logical requests
are byte-exact against D255. The lifecycle performs host cancel, session
re-entry, second arm, terminal host cancel and stop with no A2/`0x70` or device
restore command.

This is a projected FDT subsequence. It does not claim that inter-stage
NAV/base-image work in the full OEM trace is causally optional.

### Scenario 2 — target IRQ2 → `0x22` → first image

This scenario is deliberately separate from D255. It uses D230/D253 target
protocol facts and the D249 canonical synthetic, non-biometric image fixture.
After IRQ2, exact `0x22 [01 00]` is attempted once; ACK echo `0x22` is checked;
the 7,684-byte canonical record validates and the lifecycle reaches
`FIRST_IMAGE_RECEIVED`.

### Scenario 3 — invalid cache

CRC corruption, OTP mismatch with a recomputed valid CRC, wrong size/layout,
and an absent all-zero FDT12 all produce their specific fail-closed result.
The fallback seed count is zero.

### Scenario 4 — lifecycle cancel/re-entry

Cancel and terminal stop emit zero device commands. Re-entry injects neither
A2 nor `0x70`. Full cold-start is a distinct external boundary. Persistent
command families remain unreachable.

The physical bytes previously observed outside the declared `0x36` A0 frame
remain classified as transport staging residue. D257 adds no USB backend or
physical submission policy, so this is not promoted into a second offline
protocol blocker; any future live-critical transport composition still
requires normal review against the established transport contract.

## Verification

```text
python3 -m unittest discover -s tests -v                          184 passed
python3 analysis/D253/d253_offline_audit.py --repo .              PASS
(cd analysis/D256 && python3 test_d256_usb_lifecycle_contract_audit.py)
                                                                  13 passed
python3 analysis/D257/d257_offline_replay.py --repo-root .         PASS
external-cwd invocation with absolute script/repository paths      PASS
python3 -m py_compile (D257/core touched Python files)              PASS
git diff --check                                                   PASS
```

The D255 regression suite also passed inside the focused run; the historical
D256 test requires execution from its own directory because it imports its
adjacent audit module by name. No test opened USB.

## Required closure fields

```text
HOST_BUS_TERMINAL_STOP_CONTRACT=CLOSED_OBSERVED_PATH_BOUNDED_USB_QUIESCENCE
OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN=true
INTERNAL_PRIOR_ARM_STATE_CLASS=NON_BLOCKING_EPISTEMIC_UNKNOWN
NO_SPECIAL_FDT_RECOVERY_COMMAND_POLICY=DEFAULT
A2_REENTRY_INJECTION=0
0x70_REENTRY_INJECTION=0

SEED_PROVIDER_IMPLEMENTED=true
SEED_CACHE_LAYOUT_VALIDATION=PASS
SEED_OTP_BINDING_VALIDATION=PASS
SEED_CRC_VALIDATION=PASS
SEED_FRESHNESS_GENERALIZATION=UNPROVEN
CURRENT_CORPUS_EXHAUSTED_FOR_SEED_FRESHNESS_GENERALIZATION=true

FRESH_FDT_OFFLINE_REPLAY=PASS
IRQ2_0x22_PATH=PASS_EXACTLY_ONCE
FIRST_IMAGE_OFFLINE_CLOSURE=PASS_SYNTHETIC_NON_BIOMETRIC_CODEC_FIXTURE
PERSISTENT_COMMAND_FAMILIES_REACHABLE=false

FDT_OFFLINE_CANDIDATE_CLOSED=true
HOST_BUS_LIFECYCLE_READY=true
SEED_FRESHNESS_IS_SOLE_LIVE_BLOCKER=true
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false

REAL_USB_OPEN_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
```
