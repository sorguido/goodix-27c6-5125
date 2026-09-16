# D254 — external APP12509 FDT evidence cross-audit

## Closure

```text
OUTCOME=NEW_EXTERNAL_EVIDENCE_PRODUCED; D253_BOOTSTRAP_REDUCED_BUT_NOT_CLOSED; RESTORE_NOT_REDUCED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=OFFLINE_PARSERS_AND_HASH_GATES_PASS; NO_LIVE_PATH_CREATED_OR_AUTHORIZED
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md UPDATED

D254_OUTCOME=BLOCKED
D254_LIVE_BOUNDARY=BLOCKED
NEXT_MINIMUM_LIVE_BOUNDARY=NONE
D254_LIVE_EXECUTION=NOT_PERFORMED
REQUIRES_MORE_PRIMARY_EVIDENCE=true
```

D254 used public network sources read-only and parsed them offline. External
clones, WBDI raw text, ZIP and PCAP remained under
`/tmp/goodix-d254-external/`; the project contains only hash-gated sanitized
derivatives. No external code was copied into project runtime code.

## Source A identity and licensing

`yanxinwu946/goodix-5125-linux` was pinned at commit
`d39e34f240270bb13c3977a7fa99973c346fa81f`, tree
`165cc7ffc3380b8fdd106e069e5a874c48b11077`, fetched 2026-08-22. The pinned
tree has no root `LICENSE`; its README claims an inherited LGPL-2.1 scope.
The two `goodix5125` files carry `LGPL-2.1-or-later` SPDX identifiers; the
three inherited driver files carry LGPL-2.1-or-later file headers. The
`goodix-fp-dump` scripts are covered only by that directory's MIT license and
have no per-file header. `wbdi_utf8.log` has no explicit license. D254 uses
all of them as evidence only. Exact paths, hashes, notices and copyright
attribution are in `D254_provenance.json`.

The history shows `goodix5125.c` was introduced at
`e95fc2b8394d2fb36ffc0adba730b4b61af2024b`; this is history, not an
independent capture. The current pinned header calls its per-chip constants
"verified empirically" (lines 9 and 72), declares firmware
`GF_ST411SEC_APP_12509` (line 28), and supplies this 12-byte table:

```text
b3 b3 c3 c3 a8 a8 b5 b5 a8 a8 b7 b7
```

That is a `COMMENT_ASSERTION` attached to `THIRD_PARTY_CODE`, not
`WIRE_CAPTURE_EVIDENCE`. No source-A APP12509 wire capture establishes how the
constant was derived. The local target's seed is different:

```text
local target:      ad ad bd bd a3 a3 b1 b1 a6 a6 b2 b2
source A constant: b3 b3 c3 c3 a8 a8 b5 b5 a8 a8 b7 b7
WBDI first seed:   af af bf bf a4 a4 b8 b8 a8 a8 b7 b7
```

Therefore `EXTERNAL_12509_SEED_MATCH_LOCAL_TARGET=false`. The differences
are evidence consistent with device/config/session dependence, but the
available one-session corpora cannot distinguish those causes.

### Source A claimed-12509 implementation

The scan state machine at `goodix5125.c:537-584` performs:

```text
QUERY_MCU
-> 0x36 with the static table
-> NAV
-> 0x36 with the first IRQ100-derived table
-> read register 0x82
-> four OTP-derived DAC register writes
-> 0x20 image wait
```

There are exactly two manual FDT sends. It does not arm `0x32`, send `0x34`,
or implement the local target's `IRQ2 -> 0x22` path. Deactivation/close resets
host transfer state and eventually closes TLS/transport, but emits no proven
device mode restore. The README simultaneously labels device activation,
finger detection and PAM as complete while stating that image capture fails
without a plaintext per-device PSK. The code path and README claims are thus
experimental implementation evidence, not proof of a complete factory-
preserving APP12509 lifecycle. `exp5125_v3.py` describes three rounds but its
executed path contains only the static and first learned manual sends;
`fdt_seed_probe.py` lists candidate seeds but includes no captured results.

## Source A WBDI log: correct device class

The hash-gated 1123-line log reports:

```text
VID:PID=27c6:5110                 line 14
driver=1.1.124.12                 line 22
firmware=GF_ST411SEC_APP_12117    line 82
chipid=0x2504                     line 176
sensor type=12, 80x64             line 180
```

It is therefore
`CROSS_FAMILY_OEM_LIFECYCLE_EVIDENCE_5110_APP12117`, never direct APP12509
proof.

### Reconstructed OEM baseline lifecycle

The parser verifies this observed successful initialization:

```text
13520-byte base-file read -> CRC check -> live-OTP binding -> NAV/image load
-> manual stage 0 -> NAV -> manual stage 1 -> read-reg/FDT delta
-> 0x20 baseline image -> manual stage 2 -> base validation
-> 13520-byte base-file save -> final FDT-down using learned stage-2 table
```

The exact FDT rows are:

| Stage | Seed line/value | IRQ100 line/raw | Learned table | Next use |
| ---: | --- | --- | --- | --- |
| 0 | 471 `afafbfbfa4a4b8b8a8a8b7b7` | 482 `5e017f0147016f014f016d01` | `80af80bf80a380b780a780b6` | stage 1 |
| 1 | 521 `80af80bf80a380b780a780b6` | 532 `5e017f01490170014f016f01` | `80af80bf80a480b880a780b7` | stage 2 |
| 2 | 599 `80af80bf80a480b880a780b7` | 610 `5e017e014901700150016f01` | `80af80bf80a480b880a880b7` | final FDT-down |

Answers to the required lifecycle questions:

1. In the observed path this is a fixed orchestration of named stages 0, 1
   and 2. No failed attempt, retry branch or convergence predicate is
   observed; it must not be re-described as a generic three-retry loop.
2. The first seed is strongly inferred to be the FDT12 field loaded from the
   base file. The exact 13520-byte size agrees with
   `OTP64+FDT12+NAV3200+IMAGE10240+CRC4`; direct field-copy logging is absent,
   so this is an inference rather than wire proof.
3. The file is first validated and loaded, yet this successful initialization
   still refreshes the baselines and saves the full file at line 630. Later
   runtime checks show `base_is_valid=0` at line 845 followed by image/NAV
   refresh and another save at line 910; a later `base_is_valid=1` at line
   1099 returns without another save. It is therefore validate-and-refresh,
   not unconditional regeneration on every check. One trace still cannot
   establish every cold-init branch.
4. The evidenced lifecycle fields are OTP binding, FDT12, NAV3200,
   IMAGE10240 and CRC4. No freshness timestamp, temperature or firmware field
   is established.
5. Only one WBDI device/session is present, so session-to-session seed change
   is unknown.
6. The three distinct corpus seeds support a device/config-dependent
   hypothesis. Cross-family differences cannot prove the dependency or make
   any seed portable to the local target.

```text
EXTERNAL_OEM_FDT_PASS_MODEL=FIXED_THREE_SUCCESSFUL_NAMED_STAGES_IN_OBSERVED_INIT; NOT_OBSERVED_AS_RETRY_LOOP
EXTERNAL_OEM_INITIAL_SEED_SOURCE=BASEFILE_FDT12_STRONGLY_INFERRED; DIRECT_COPY_NOT_LOGGED
EXTERNAL_OEM_BASEFILE_ROLE=OTP_BOUND_CRC_CACHE_LOADED_THEN_REFRESHED_AND_SAVED_IN_THIS_INIT
EXTERNAL_OEM_BASEFILE_OTP_BINDING=FILE_OTP64_COMPARED_WITH_LIVE_OTP
EXTERNAL_OEM_FDT_LOOP_STOP_CRITERION=ORCHESTRATOR_COMPLETES_STAGES_0_1_2; NO_CONVERGENCE_PREDICATE_OBSERVED
CROSS_FAMILY_RELEVANCE_TO_D253=STRONG_LIFECYCLE_AND_CACHE_FORMAT_CORROBORATION; NOT_TARGET_SEED_VALIDATION
```

## Source B: Issue #63 capture

The public attachment was accessible without privileged authentication.

```text
ISSUE63_ATTACHMENT_SHA256=61e1d5354cb9617cd602b8ee465aa6693381d00899a7f50af3d10ee89b86bc3c
ISSUE63_PCAP_SHA256=5b2e9649b8acdbf93bbb19275feb32203dacc50d727ef2222d58162fbd1b63d0
ISSUE63_CAPTURE_DEVICE=27c6:5125 (descriptor inside capture)
ISSUE63_FIRMWARE=UNKNOWN
```

The USBPcap contains 752 records and begins mid-session at an already armed
`0x32`; it contains no A8/version query, NAV or cold-start bootstrap. The
sanitized A0 census is:

| Direction | Controls |
| --- | --- |
| OUT | `0x20=14`, `0x22=21`, `0x32=37`, `0x34=35`, `0x36=22`, `0xaf=1`, `0xd5=1` |
| IN | `0x32=36`, `0x34=13`, `0x36=22`, `0xae=1`, `0xb0=129` |

There are 21 IRQ2, 22 IRQ100, 13 IRQ200 and 35 image-sized B0 records. Every
observed IRQ2 is followed by exact `0x22 [01 00]`, independently
corroborating the local target's current command choice on a 5125 whose
firmware remains unknown. After IRQ100, the next command is `0x20` 14 times
and a new `0x32` eight times. This is enrollment-cycle evidence, not biometric
semantic ground truth.

All 22 outbound `0x36` frames have logical A0 length 22 and physical USB
length 64. Nonzero bytes outside A0 occur only at physical offsets 40-45:
`cb f2 ca 66 f8 7f`. The local target has the same offsets but different bytes
(`cb f2 e2 be fb 7f`). This independently supports a staging-residue
interpretation. It does not prove zero-tail equivalence because neither
capture contains a zero-tail target `0x36`.

No A2 or `0x70` restore occurs. The capture contains positive finger cycles
only and ends on IRQ200 after an acknowledged `0x34`; it contains no operator
cancel, no-finger timeout, close, suspend or error recovery. Later `0x32`
acceptance establishes re-entry on successful cycles, not deterministic
safe-stop from an armed no-finger state.

## Source C and five-axis comparison

The preserved Rocky commit is
`227eba219fa9e3fbac5bd59aca79f624f67cd11b` (APP12508 implementation axis).
Its sampler starts with zeros or cached data and permits at most three retry
attempts, returning after the first valid IRQ100; it is not the WBDI fixed
three-successful-stage sequence. Rocky sends `0x20` after IRQ2, stores the
same 13520-byte base-file layout, and its cancel is only a host flag. Rocky's
Issue #1 reply identifies APP12508 as its own tested hardware. A later user
reports a working native APP12509 stack, but also reports replacing the PSK;
that is useful `THIRD_PARTY_LIVE_REPORT` corroboration, not factory-PSK-
preserving bootstrap/cancel evidence.

The complete property-by-property matrix, with an evidence class in every
cell, is in `D254_comparison_matrix.json` and `.csv`. Variants remain explicit:
local target and Issue63 use post-IRQ2 `0x22`; Rocky APP12508 and WBDI
5110/APP12117 use `0x20`. No unproved autodetection was added and the current
local target model was not reverted.

## D253 reopening decision

Bootstrap evidence is materially improved: the OEM cross-family log closes
the cache layout and demonstrates that a first seed can be a host-cached,
OTP-bound lifecycle field which is then replaced by IRQ100-derived tables.
It does **not** prove that the local APP12509 first seed is optional, safe when
zero/stale, correctly derived, or fresh. The source-A claimed-12509 constant
does not match the local target and has no independent wire provenance.
Thus `BOOTSTRAP_BLOCKER_REDUCED=true`, but `BOOTSTRAP_CLOSED=false`.

Restore is not materially reduced. Repeated successful cycles and the absence
of explicit cancel in third-party code do not establish a device-side stop or
deterministic volatile lifetime. Thus `RESTORE_BLOCKER_REDUCED=false` and
`RESTORE_CLOSED=false`.

The single highest-value next acquisition is:

```text
ONE SANITIZED WINDOWS 27c6:5125 APP12509 TRACE
FROM COLD-START BASE-FILE VALIDATION AND FIRST-0x36 SEED SOURCE
THROUGH 0x32 ARM, THEN OPERATOR CANCEL WITHOUT FINGER,
FOLLOWED BY DETERMINISTIC RE-ENTRY
```

This is an external evidence request, not a proposed Linux live sequence.

## Safety counters

```text
LOCAL_USB_OPEN_COUNT=0
LOCAL_TLS_HANDSHAKE_COUNT=0
LOCAL_D4_SEND_COUNT=0
LOCAL_AF_SEND_COUNT=0
LOCAL_FDT_SEND_COUNT=0
LOCAL_IMAGE_COMMAND_COUNT=0
LOCAL_FINGER_INTERACTION_COUNT=0
LOCAL_PERSISTENT_WRITE_FAMILY_COUNT=0
```
