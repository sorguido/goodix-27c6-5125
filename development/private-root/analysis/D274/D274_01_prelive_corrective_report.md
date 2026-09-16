# D274/01 corrective — finalizzazione in-place (review AI-PM successiva)

```text
OUTCOME=CORRECTIVE_CLOSED_OFFLINE_THREE_DEFECTS_FIXED_IN_PLACE
ADVANCEMENT=NON_HARDWARE_OFFLINE_EVIDENCE_INTEGRITY_BOUNDARIES_TIGHTENED
EXECUTABLE_CLOSURE=PASS_OFFLINE_PYTHON_POWERSHELL_STATIC_AND_REAL_SCHEMA_VALIDATION
RESIDUAL_BLOCKER_OR_RISK=WINDOWS_NATIVE_SELFTEST_PREFLIGHT_SIMULATION_NOT_EXECUTED;WINDOWS_NATIVE_ACL_BEHAVIOR_TEST_NOT_AVAILABLE;D263_WORKFLOW_UNKNOWN;SECOND_TARGET_CYCLE_NOT_OBSERVED;SEPARATE_AI_PM_REVIEW_AND_WINDOWS_NATIVE_OFFLINE_QUALIFICATION_REQUIRED
CANONICAL_DOCUMENTATION=UPDATED — sezione canonica D274 e sintesi alta
BUNDLE=analysis/D274/D274_01_prelive_corrective_bundle.zip
```

## Esito

Il corrective D274/01 non committato è stato finalizzato in-place (nessun
D274/02, nessun "corrective 2"). La review AI-PM successiva ha individuato tre
difetti reali ancora presenti nel corrective corrente e li ha corretti, più un
rafforzamento del contract runtime evidence. Nessun accesso USB, hardware,
decriptazione, o mutazione ACL; `D274_REAL_CAPTURE_CAPABILITY=0`,
`D274_HARD_DISABLED=true`, `LIVE_EXECUTION=NOT_PERFORMED`.

### A. TLS record length interpretata little-endian (errata)

`classify_b0` leggeva `frame.raw[7:9]` come little-endian e le fixture
codificavano la lunghezza del record TLS in little-endian (`17 03 03 25 1e`). Il
record layer TLS è network byte order (big-endian): l'header realistico è
`17 03 03 1e 25` (7717 = `0x1e25`). Corretto: il classificatore usa
`int.from_bytes(frame.raw[7:9], "big")`; le fixture codificano la lunghezza TLS
in big-endian; la lunghezza outer B0 Goodix (`raw[1:3]`) resta little-endian.
Aggiunto `test_28_tls_record_length_endianness` che costruisce esplicitamente
l'header `17 03 03 1e 25` (FINGERPRINT_B0) e la variante little-endian
`17 03 03 25 1e` (B0_OTHER), più i controlli negativi alert / wrong-length /
incoherent / host→device. La fixture sintetica non può ridefinire la semantica
TLS.

```text
D274_TLS_RECORD_LENGTH_ENDIAN=BIG_ENDIAN_NETWORK_ORDER
D274_GOODIX_B0_LENGTH_ENDIAN=LITTLE_ENDIAN
D274_REALISTIC_TLS_HEADER_1703031E25_ACCEPTED=true
D274_SYNTHETIC_LITTLE_ENDIAN_TLS_LENGTH_ACCEPTED=false
```

### B. Il check ACL non chiudeva davvero la privacy

`Test-D274PrivateOutputRoot` elencava `Write/Modify/FullControl` ma ometteva
`Read`, quindi un ACE `Everyone: Read` non veniva respinto. Controllava inoltre
`AceType` anziché `AccessControlType` (il discriminante allow/deny su
`FileSystemAccessRule`) e confrontava principal in forma nominale (non robusto su
Windows localizzato). Corretto in `operator_kit/d274-windows-multiframe-evidence.ps1`:
il mask include ora `Read` (intercettando anche `ReadAndExecute`/`ReadData` via
band); il discriminante è `AccessControlType -eq Allow`; l'`IdentityReference` è
normalizzata a `SecurityIdentifier` tramite `Translate(...)`; la traduzione SID
fallita è fail-closed; i quattro SID canonici (S-1-1-0, S-1-5-32-545, S-1-5-11,
S-1-5-32-546) sono rifiutati se concedono un diritto coperto dal mask. Nessun
`Set-Acl`/`icacls`; D274 resta pre-live. `test_22` ora include source guard che
falliscono se compare `.AceType`, se manca `AccessControlType`, se manca
`FileSystemRights]::Read`, se manca `Translate(...)`/`SecurityIdentifier`, se
mancano i quattro SID, o se compaiono `Set-Acl`/`icacls`.

```text
D274_OUTPUT_ROOT_PRIVACY_POLICY_SOURCE_CONTRACT=PASS
D274_OUTPUT_ROOT_PRIVACY_CONTRACT=CLOSED_OFFLINE_PREFLIGHT_POLICY
D274_OUTPUT_ROOT_REPARSE_POINT_ACCEPTED=false
D274_BROAD_ACL_ACCEPTED=false
D274_BROAD_ACL_READ_ACCEPTED=false
D274_ACL_ALLOW_DISCRIMINATOR=AccessControlType
D274_ACL_IDENTITY_NORMALIZATION=SecurityIdentifier
WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=NOT_AVAILABLE
```

Il contract è una closure source/policy offline, non una verifica nativa Windows.

### C. Il fallback strict-local trattava float come integer

Il validator locale accettava `1.5` per uno schema che richiede
`"type": "integer"`. Corretto in `test_d274_postprocess_multiframe_evidence.py`:
`integer` ⇒ `isinstance(node, int)` (bool escluso); `number` ⇒ `int` o `float`.
`test_29_local_validator_integer_vs_number` forza il validator locale
(indipendente da `jsonschema`) con fixture negative `frame=1.5`,
`physical_length=7726.5`, `declared_outer_length="7726"`, proprietà `raw` extra,
campo richiesto mancante, e positive `frame=int`, `relative_timestamp_ms=float`.

```text
D274_LOCAL_SCHEMA_INTEGER_SEMANTICS=STRICT_INTEGER_ONLY
```

### Rafforzamento — runtime evidence contract

Il producer ora esegue, prima della serializzazione,
`validate_evidence_document_strict`: set esatto di proprietà top-level, campi
richiesti, privacy booleans false, allowlist strict dei frame metadata, `frame`
integer, campi di lunghezza integer, `direction` enum, shape outer-wrapper,
`timestamp` number, e forbid-list esatta dei campi privacy-sensitive
(`raw`/`body`/`payload`/`plaintext`/`image`/`raster`/`pixel`/`hash`/`descriptor`/
`template`/`secret`/`psk`). Nessuna dipendenza runtime da `jsonschema`.
`test_30_runtime_evidence_contract_validation` verifica il fail-closed su tipo
errato e campo vietato.

```text
D274_RUNTIME_EVIDENCE_CONTRACT_VALIDATION=PASS_LOCAL_STRICT
```

## Regressions D274 preservate e rieseguite

Target `27c6:5125` unico; A8 APP12509 nella stessa capture; hash gate;
re-enumeration rejection; secondo target rejection; NAV exact `0x50` 2417/2410;
`0x51` non NAV; ACK exact `0x01`; first cycle historical → missing second IRQ2;
deadline host-side 180 s; nessun device-timeout claim; hard-disable PowerShell;
zero hardware. 30/30 test superati da Git root e da cwd esterno con
`PYTHONPATH`.

## Stato probatorio e safety

```text
D274_FINGERPRINT_B0_CONTRACT=CLOSED_OFFLINE_STRUCTURAL_7726_TLS_APPLICATION_DATA
D274_GENERIC_B0_AS_FINGERPRINT_ACCEPTED=false
D274_TLS_ALERT_B0_AS_FINGERPRINT_ACCEPTED=false
D274_WRONG_LENGTH_B0_AS_FINGERPRINT_ACCEPTED=false
D274_TLS_RECORD_LENGTH_ENDIAN=BIG_ENDIAN_NETWORK_ORDER
D274_GOODIX_B0_LENGTH_ENDIAN=LITTLE_ENDIAN
D274_REALISTIC_TLS_HEADER_1703031E25_ACCEPTED=true
D274_SYNTHETIC_LITTLE_ENDIAN_TLS_LENGTH_ACCEPTED=false
D274_OUTPUT_ROOT_PRIVACY_POLICY_SOURCE_CONTRACT=PASS
D274_OUTPUT_ROOT_PRIVACY_CONTRACT=CLOSED_OFFLINE_PREFLIGHT_POLICY
D274_OUTPUT_ROOT_REPARSE_POINT_ACCEPTED=false
D274_BROAD_ACL_ACCEPTED=false
D274_BROAD_ACL_READ_ACCEPTED=false
D274_ACL_ALLOW_DISCRIMINATOR=AccessControlType
D274_ACL_IDENTITY_NORMALIZATION=SecurityIdentifier
WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=NOT_AVAILABLE
D274_CREDENTIAL_MUTATION_UI_TERMINAL=true
D274_UNKNOWN_MARKER_ACCEPTED=false
D274_FRAME_METADATA_SCHEMA=STRICT_ADDITIONAL_PROPERTIES_FALSE
D274_LOCAL_SCHEMA_INTEGER_SEMANTICS=STRICT_INTEGER_ONLY
D274_SCHEMA_JSON_PARSE=PASS
D274_SCHEMA_INSTANCE_VALIDATION=PASS
D274_RUNTIME_EVIDENCE_CONTRACT_VALIDATION=PASS_LOCAL_STRICT
D274_PRIVACY_FRAME_METADATA_SHAPE=PASS
D274_PRELIVE_WINDOWS_MULTIFRAME_EVIDENCE_KIT=READY_FOR_AI_PM_REVIEW
D274_REAL_CAPTURE_CAPABILITY=0
D274_HARD_DISABLED=true
D274_SECOND_CYCLE_TARGET_OBSERVATION=NOT_EXECUTED
SECOND_CYCLE_STATUS=TARGET_CAPTURE_NOT_OBSERVED_STATIC_COMPONENTS_PARTIALLY_VERIFIED
D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01
D273_NAV_CLASSIFICATION_WIRE_CONTROL=EXACT_0X50
D273_0X51_NAV_ALIAS_ACCEPTED=false
GENERIC_WIRE_TO_LOGICAL_MASK_REMOVED=true
WINDOWS_NATIVE_EXECUTION_TEST=NOT_AVAILABLE
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_WINDOWS_ACCOUNT_MUTATION_COUNT=0
REAL_WINDOWS_ENROLLMENT_COMMIT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
```

Il prossimo step separato dovrà comunque eseguire nativamente in Windows
`-SelfTestOnly`, `-PreflightOnly`, `-PreAuthorizationSimulationOnly` (incluse le
verifiche ACL native) prima di qualunque source unseal o capture reale. Non viene
aperto D274/02 e non è autorizzata alcuna capture reale.

```text
STARTING_HEAD=21d549b1952d5a56389cc379e9f17aa6dfcbf070
FINAL_WORKTREE_STATUS=DIRTY_EXPECTED_D274_01_CORRECTIVE_UNCOMMITTED_CHANGES_ONLY
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_D274_01_CORRECTIVE
NEXT_BOUNDARY_PREREQUISITE=CORRECTIVE_REVIEW_THEN_WINDOWS_NATIVE_OFFLINE_QUALIFICATION
```
