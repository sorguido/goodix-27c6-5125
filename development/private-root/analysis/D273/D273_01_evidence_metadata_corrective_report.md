# D273/01 — Corrective evidence metadata: wire-control truth + Rocky provenance

Step-local, deterministic corrective on the already-pushed D273 baseline
`5ef14c5051726fe6bc6624de86d3885f3306776e` (parent
`062c05a1fbe198c858eaeba4b86db1d24eb79f39`), branch `development`.

No USB, no secrets, no fprintd, no biometric capture, no persistent device
write. The D273 technical conclusions are unchanged; only probative metadata
and Rocky provenance are restored to truth.

## Defect 1 — wrong Rocky provenance in the evidence matrix

`analysis/D273/D273_01_multiframe_evidence_matrix.json` recorded
`rocky_snapshot_commit = 227eba177a44b2eea645be81c995246ceb8119e5`
(erroneous). The canonical provenance verified in `Rockytkg/PROVENANCE.md` is
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`. The matrix is corrected to the
exact canonical commit.

A programmatic check (`d273_01_evidence_metadata_corrective_test.py`,
`rocky_provenance_aligned_to_canonical`) reads the commit from
`Rockytkg/PROVENANCE.md` (single normative source) and compares it against the
value recorded in the matrix; no second hard-coded normative source is
introduced. Rocky classification remains `THIRD_PARTY_CORROBORATION` only.

## Defect 2 — generic `wire_control & 0xfe` derivation

`analysis/D273/d273_01_offline_capture_audit.py` computed
`logical_control = wire_control & 0xfe` for every A0 frame. This is not a
general project contract; the canonical manual (§Trasporto USB) requires wire
and logical control to stay distinct and states that deducing the logical with
`wire & 0xfe` is not always correct. The census therefore produced semantically
false metadata: e.g. the D1 wire `0xd1` frame (packet 114) was published with
`logical_control = 0xd0`.

Correction:

- the exact `wire_control` is always preserved;
- no universal `logical_control` is derived by masking;
- a semantic `logical_control` is emitted only for ACKs (real observed echo)
  and is marked `NOT_DERIVED` for every other A0 frame;
- for the relevant D273 boundaries (`0x32`, `0x22`, `0x34`, `0x20`, `0x50`)
  the exact observed control is used, with no generic rule;
- packet 249 stays `outer_wrapper=A0`, `wire/control observed=0x50`,
  `physical/outer length=2417`, `inner length=2410`,
  `classification=A0_0X50_NAV_RESPONSE`;
- ACK echo/status are preserved as observed;
- no B0 plaintext/raster/payload content is serialized.

## Regeneration

Deterministic regeneration of:

- `analysis/D273/D273_01_capture_census.json`
- `analysis/D273/D273_01_multiframe_evidence_matrix.json`

The regeneration is byte-identical on replay (checked by the corrective test).

## Mandatory checks (all PASS)

- odd control D1 wire `0xd1` is NOT falsely published as logical `0xd0`;
- packet 249 remains classified `A0_0X50_NAV_RESPONSE`;
- ACK echo/status are preserved;
- regenerated census is deterministic;
- no payload B0/plaintext/raster is serialized;
- Rocky provenance in matrix equals canonical commit from `Rockytkg/PROVENANCE.md`.

## Canonical state preserved (unchanged)

```text
MULTIFRAME_CONTRACT=PARTIALLY_CLOSED_TARGET_SECOND_CYCLE_NOT_OBSERVED_AND_TARGET_TIMEOUTS_UNCLOSED
UP_TABLE12_SOURCE=OEM_SESSION_GLOBAL_GF_FDT_UP_BASE_VA_0X180580838
UP_TABLE12_FRESHNESS_REQUIREMENT=0X34_MUST_CONSUME_THE_MOST_RECENT_VALID_IRQ_0X0002_DERIVED_TABLE_FROM_THE_SAME_FINGER_DOWN_CYCLE
POST_0X50_RESPONSE_STATUS=OBSERVED_A0_0X50_NAV_RESPONSE_LENGTHS_2417_2410
SECOND_CYCLE_STATUS=TARGET_CAPTURE_NOT_OBSERVED_STATIC_COMPONENTS_PARTIALLY_VERIFIED
D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01
ACK_0X07_ACCEPTED=false
OPENCV4_DEV_ENVIRONMENT=NOT_AVAILABLE
REAL_SIGFM_BUILD=BLOCKED_OPENCV4_DEV_NOT_AVAILABLE
REAL_SIGFM_EXECUTABLE_CLOSURE=FAIL_NOT_AVAILABLE
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
```

## Closure

```text
CORRECTIVE_EXECUTABLE_CLOSURE=PASS
GENERIC_WIRE_TO_LOGICAL_MASK_REMOVED=true
ODD_CONTROL_FALSE_DERIVATION_TEST=PASS
PACKET_249_NAV_CLASSIFICATION=A0_0X50_NAV_RESPONSE
CAPTURE_CENSUS_DETERMINISM=PASS
ROCKY_PROVENANCE_CORRECTIVE=PASS
ROCKY_CANONICAL_COMMIT=227eba219fa9e3fbac5bd59aca79f624f67cd11b
REAL_SIGFM_EXECUTABLE_CLOSURE=FAIL_NOT_AVAILABLE
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_BIOMETRIC_CAPTURE_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

The historical D273 primary bundle
(`D273_01_post_first_image_multiframe_sigfm_bundle.zip` and its `.sha256`)
is preserved unchanged.
