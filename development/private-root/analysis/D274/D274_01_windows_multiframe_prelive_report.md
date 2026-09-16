# D274/01 — Windows OEM multi-frame evidence kit — offline pre-live

```text
OUTCOME=READY — D274_PRELIVE_KIT_READY_FOR_AI_PM_REVIEW
ADVANCEMENT=NON_HARDWARE_EXECUTABLE_EVIDENCE_ACQUISITION_AND_SANITIZATION_PATH_CLOSED_OFFLINE
EXECUTABLE_CLOSURE=PASS_OFFLINE_PYTHON_AND_STATIC_ONLY_WINDOWS_NATIVE_NOT_AVAILABLE
RESIDUAL_BLOCKER_OR_RISK=WINDOWS_NATIVE_SELFTEST_PREFLIGHT_AND_SIMULATION_NOT_EXECUTED;D263_WORKFLOW_UNKNOWN;SECOND_TARGET_CYCLE_NOT_OBSERVED;SEPARATE_AI_PM_REVIEW_BASELINE_APPROVAL_AND_ONE_RUN_AUTHORIZATION_REQUIRED
CANONICAL_DOCUMENTATION=UPDATED — stato alto e sezione D274/01
BUNDLE=analysis/D274/D274_01_windows_multiframe_prelive_bundle.zip
```

## Esito

D274/01 prepara il percorso minimo per una futura osservazione passiva del
secondo ciclo OEM Windows e non esegue hardware. Il kit PowerShell è distinto
da D255/D268 e può eseguire solo self-test, preflight e simulazione
pre-autorizzazione. Il flag nominale della futura run termina sempre
`HARD_DISABLED_D274_01` prima di TShark, attach, prompt o azione hardware;
`D274_REAL_CAPTURE_CAPABILITY=0` non è configurabile.

Il postprocessor Python è offline, hash-gated e privacy-preserving. Richiede
USBPcap linktype 249, un solo `27c6:5125` e A8 APP12509 nella stessa capture,
quindi riconosce l'esatta sequenza fino al secondo B0. Esporta soltanto
metadata di framing e timing. Non decripta né serializza B0, plaintext, raster,
pixel, template, hash biometrici o secret.

## Audit del workflow OEM

```text
D263_CAPTURE_WORKFLOW_CLASS=UNKNOWN
WINDOWS_OEM_WORKFLOW_SELECTED=WINDOWS_HELLO_SETUP_CANDIDATE_NO_COMMIT
```

La capture positiva D263 è il file recuperato nel corpus D230. Il corpus
preserva pcap, hash e componenti OEM, ma non UI, comando di acquisizione,
marker o workflow. D255 dimostra un percorso Windows Hello setup zero-finger,
ma è una capture distinta e priva del sottoalbero positivo. Windows Hello
setup è quindi soltanto un candidato futuro conservativo; non è attribuito
alla capture D263.

Qualunque richiesta UI di commit enrollment, mutazione account/PIN/credenziali
o terzo dito è terminale. Non sono autorizzati cancellazione di enrollment
esistenti, policy/registry workaround, restart service o mutation PnP.

## Sequenza e stop

Il success stop è esclusivamente:

```text
first IRQ2 → 0x22 → ACK 0x01 → first B0
→ 0x34 → ACK 0x01 → IRQ0200 → 0x20 → ACK 0x01 → post-up B0
→ exact 0x50 → ACK 0x01 → exact A0 0x50 NAV 2417/2410
→ 0x32 → ACK 0x01 → second IRQ2 → 0x22 → ACK 0x01 → second B0 → STOP
```

`0x51` non è NAV. Echo errato, status diverso da `0x01`, sequenza ambigua,
duplicati, re-enumeration, secondo target, terzo ciclo, deadline, terminal UI o
marker non monotoni falliscono chiusi e non autorizzano retry.

La state machine PowerShell mantiene distinti marker operatore e wire facts.
Il marker umano `SECOND_B0_OBSERVED` delimita soltanto la finestra; il fatto
packet-level viene sempre derivato offline dal pcap.

## Timing bounded

La capture positiva osserva ACK del primo `0x32` → IRQ2 in 7.108 s e il tratto
dal primo arm all'ACK del re-arm in 8.383 s. D255 osserva 62.884 s da
attach-begin a UI-ready. La durata massima futura è quindi una deadline unica
host-side di 180 s, con margine sopra entrambe le osservazioni:

```text
D274_HOST_CAPTURE_DEADLINE_POLICY=EVIDENCE_BOUNDED_NOT_DEVICE_TIMEOUT_CLAIM
D274_HOST_CAPTURE_DEADLINE_SECONDS=180
DEVICE_SEMANTIC_TIMEOUT=UNKNOWN
```

## Verifiche offline

- 22 test D274 sintetici: PASS, inclusi happy path e tutti i failure richiesti;
- fixture pcapng sintetica completa: PASS, senza claim target;
- capture APP12509 storica hash-gated: expected
  `failure_class=MISSING_SECOND_IRQ2`, nessuna promozione;
- suite D272 exact ACK/privacy/operator: 19 PASS;
- corrective D273 NAV/provenance: PASS, `0x51` rifiutato;
- invocazione D274 da Git root e da `/tmp`: PASS;
- py_compile, JSON parse e `git diff --check`: PASS;
- PowerShell nativo: `NOT_AVAILABLE` (`pwsh` assente sull'host Fedora), non
  convertito in PASS;
- privacy scan del review set/bundle: PASS.

## Stato probatorio e safety

```text
D274_PRELIVE_WINDOWS_MULTIFRAME_EVIDENCE_KIT=READY_FOR_AI_PM_REVIEW
D274_REAL_CAPTURE_CAPABILITY=0
D274_HARD_DISABLED=true
D274_SECOND_CYCLE_TARGET_OBSERVATION=NOT_EXECUTED
D274_POSTPROCESSOR_STATUS=PASS_OFFLINE_HASH_GATED_SANITIZED
D274_EVIDENCE_SCHEMA_STATUS=PASS
D274_SYNTHETIC_SECOND_CYCLE_FIXTURE=PASS
D274_PRIVACY_CONTRACT=PASS_METADATA_ONLY_NO_B0_CONTENT
SECOND_CYCLE_STATUS=TARGET_CAPTURE_NOT_OBSERVED_STATIC_COMPONENTS_PARTIALLY_VERIFIED
D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01
D273_NAV_CLASSIFICATION_WIRE_CONTROL=EXACT_0X50
D273_0X51_NAV_ALIAS_ACCEPTED=false
GENERIC_WIRE_TO_LOGICAL_MASK_REMOVED=true
OPENCV4_DEV_ENVIRONMENT=NOT_AVAILABLE
REAL_SIGFM_BUILD=BLOCKED_OPENCV4_DEV_NOT_AVAILABLE
REAL_SIGFM_EXECUTABLE_CLOSURE=FAIL_NOT_AVAILABLE
WINDOWS_ENROLLMENT_COMMIT_AUTHORIZED=false
WINDOWS_ACCOUNT_MUTATION_AUTHORIZED=false
WINDOWS_PIN_MUTATION_AUTHORIZED=false
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_WINDOWS_ACCOUNT_MUTATION_COUNT=0
REAL_WINDOWS_ENROLLMENT_COMMIT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

Il prossimo boundary è la review AI-PM del kit. Nessuna D274/02 o capture è
automaticamente autorizzata. Soltanto dopo review servirebbero una baseline
live-critical completa esplicitamente approvata e una distinta autorizzazione
one-shot dell'Utente.

```text
GIT_ROOT=/home/guido/Repository/goodix-27c6-5125_private
STARTING_HEAD=3b2fef1bbf196c8c0fc5122521997fbb953016ea
FINAL_WORKTREE_STATUS=DIRTY_EXPECTED_D274_01_UNCOMMITTED_CHANGES_ONLY
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_D274_PRELIVE_KIT
NEXT_BOUNDARY_PREREQUISITE=REVIEW_AND_SEPARATE_EXPLICIT_LIVE_BASELINE_APPROVAL_AND_ONE_RUN_AUTHORIZATION
```
