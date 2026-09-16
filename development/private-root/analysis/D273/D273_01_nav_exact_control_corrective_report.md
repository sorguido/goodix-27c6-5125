# D273/01 — Corrective 2: remove residual 0x50 mask classification

Step-local, deterministic corrective on the D273 corrective-1 commit
`7c991143e3670f6262f23e6159edde9e240c4287` (parent D273 primary
`5ef14c5051726fe6bc6624de86d3885f3306776e`), branch `development`.

No USB, no secrets, no fprintd, no biometric capture, no persistent device
write. The D273 technical conclusions are unchanged; only the last
mask-based equivalence is removed from the D273 census classifier.

## Residual defect

`analysis/D273/d273_01_offline_capture_audit.py` retained, in the NAV response
classifier, the condition:

```python
elif direction == "device_to_host" and (wire_control & 0xFE) == 0x50:
```

This is still semantically too permissive: a hypothetical wire `0x51` would be
classified `A0_0X50_NAV_RESPONSE` without evidence that such equivalence holds.
The claim `GENERIC_WIRE_TO_LOGICAL_MASK_REMOVED=true` from corrective 1 was
therefore not yet literally true for the D273 audit.

## Correction

```python
elif direction == "device_to_host" and wire_control == 0x50:
```

No `& 0xfe` / `& 0xFE`, masking, parity or even/odd normalization is used to
classify the D273 NAV response. `NAV_RESPONSE_WIRE_CONTROL = EXACT_0X50`.

## Mandatory checks (all PASS)

- synthetic `0x50` device→host A0 frame → `A0_0X50_NAV_RESPONSE`;
- synthetic `0x51` device→host A0 frame → NOT `A0_0X50_NAV_RESPONSE`, remains
  `A0_COMMAND_OR_RESPONSE` (generic A0 path);
- source guard on `d273_01_offline_capture_audit.py` fails closed if
  `wire_control & 0xfe` / `wire_control & 0xFE` reappears;
- census regeneration deterministic;
- packet 249 unchanged: `outer_wrapper=0xa0`, `wire_control=0x50`,
  `physical_length=2417`, `declared_outer_length=2417`,
  `declared_inner_length=2410`, `classification=A0_0X50_NAV_RESPONSE`,
  `logical_control=NOT_DERIVED`;
- D1 wire `0xd1` → `logical_control=NOT_DERIVED` (no false 0xd0);
- ACK echo/status preserved;
- no B0/plaintext/raster/pixel serialized;
- Rocky provenance check unchanged (`PASS`, canonical commit
  `227eba219fa9e3fbac5bd59aca79f624f67cd11b`).

## Preserved state (unchanged)

```text
MULTIFRAME_CONTRACT=PARTIALLY_CLOSED_TARGET_SECOND_CYCLE_NOT_OBSERVED_AND_TARGET_TIMEOUTS_UNCLOSED
UP_TABLE12_SOURCE=OEM_SESSION_GLOBAL_GF_FDT_UP_BASE_VA_0X180580838
POST_0X50_RESPONSE_STATUS=OBSERVED_A0_0X50_NAV_RESPONSE_LENGTHS_2417_2410
SECOND_CYCLE_STATUS=TARGET_CAPTURE_NOT_OBSERVED_STATIC_COMPONENTS_PARTIALLY_VERIFIED
D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01
ACK_0X07_ACCEPTED=false
REAL_SIGFM_EXECUTABLE_CLOSURE=FAIL_NOT_AVAILABLE
ROCKY_PROVENANCE_CORRECTIVE=PASS
```

## Manuale: integrazione organica

La review AI-PM ha approvato il corrective tecnico ed evidenziato che il manuale
era stato aggiornato in forma troppo append-only (nuovo heading separato
`### D273/01 corrective 2: ...`). Il manuale è stato quindi riconsolidato: il
primo corrective e il corrective 2 confluiscono in un'unica sezione
`### D273/01 corrective: verità probatoria, provenance Rocky e exact NAV
control`; i tre campi exact-control (`D273_NAV_CLASSIFICATION_WIRE_CONTROL`,
`D273_0X51_NAV_ALIAS_ACCEPTED`, `GENERIC_WIRE_TO_LOGICAL_MASK_REMOVED`) sono
integrati nello stato canonico alto post-D273 accanto ai campi `0x50`, non
solo nella provenance storica in fondo. Nessun blocker D273, nessun live flag e
nessun `NEXT_PRIMARY_BOUNDARY` nuovo è stato introdotto.

## Closure

```text
CORRECTIVE2_EXECUTABLE_CLOSURE=PASS
GENERIC_WIRE_TO_LOGICAL_MASK_REMOVED=true
NAV_RESPONSE_WIRE_CONTROL_CONTRACT=CLOSED_EXACT_0X50
WIRE_0X51_NAV_ALIAS_ACCEPTED=false
ROCKY_PROVENANCE_CORRECTIVE=PASS
TECHNICAL_CORRECTIVE_REVIEW=PASS
CANONICAL_MANUAL_ORGANIC_INTEGRATION=PASS
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
