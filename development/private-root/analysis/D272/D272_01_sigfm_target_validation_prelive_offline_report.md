# D272/01 — SIGFM target-validation pre-live, offline only

```text
OUTCOME=BLOCKED_POST_FIRST_IMAGE_UP_TABLE_SECOND_CYCLE_AND_OPENCV4_DEV
ADVANCEMENT=NEW_OFFLINE_MULTIFRAME_MODEL_AND_SIGFM_EXCEPTION_PRIVACY_SEAM
EXECUTABLE_CLOSURE=FAIL
RESIDUAL_BLOCKER_OR_RISK=0X34_UP_TABLE_SOURCE_FRESHNESS_UNKNOWN;SECOND_CYCLE_AFTER_REARM_NOT_TARGET_OBSERVED;TARGET_TIMEOUT_AND_POST_UP_0X50_GATE_NOT_CLOSED;REAL_SIGFM_BUILD_BLOCKED_OPENCV4_DEV
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=analysis/D272/D272_01_sigfm_target_validation_prelive_offline_bundle.zip
BUNDLE_SHA256=SEE_EXTERNAL_SIDECAR
```

## Esito

D272 produce avanzamento tecnico offline ma non autorizza una run. Il modello
multi-frame bounded e il seam SIGFM exception/privacy-preserving esistono e
sono testati sinteticamente. Due classi di requisito impediscono `READY`:

1. il lifecycle target non è chiuso per una futura sessione: la tabella up
   inviata con `0x34` è osservata ma non ha source/freshness contract; dopo il
   re-arm finale la capture non mostra una seconda iterazione completa;
2. OpenCV4 development files non sono presenti né sull'host né nel Flatpak SDK
   installato, quindi il wrapper non può essere linkato ed eseguito contro il
   vero SIGFM locale.

Non è stato installato nulla, non è stato aperto USB e il percorso future-live
del nuovo kit è hard-disabled.

## Audit lifecycle target

Fonte primaria: `analysis/D263/D263_01_post_arm_order.json`, che riferisce la
capture privata hash-gated senza includerla nel bundle.

| Ordine | Transizione | Classificazione | Evidenza/limite |
| --- | --- | --- | --- |
| 1 | first image | `OBSERVED`, `VERIFIED` | packet 231; D268 ha provato live decode e raster 80×64 |
| 2 | `0x34 {0a01 || up_table12}` | `OBSERVED` | packet 233; valore sessione noto, origine/freshness `UNKNOWN` |
| 3 | ACK `34/01` | `OBSERVED` | packet 235; il modello richiede ACK esatto |
| 4 | IRQ `0x0200` | `OBSERVED` | packet 237; finger-up fortemente supportato, timeout target `UNKNOWN`; Rocky solo `THIRD_PARTY_CORROBORATION` |
| 5 | `0x20 {0100}` + ACK | `OBSERVED` | packet 238/241 |
| 6 | immagine post-up | `OBSERVED` | packet 243; la semantica no-finger/qualità resta `UNKNOWN` |
| 7 | `0x50 {0100}` + ACK + response | `OBSERVED` | packet 244/247/249; passaggio obbligatorio omesso nel riepilogo breve del task |
| 8 | `0x32` re-arm + ACK | `OBSERVED` | packet 251/253 |
| 9 | next IRQ2 → `0x22`/ACK → next image | `INFERRED` | la forma è osservata prima della first image a packet 220–231, non dopo packet 251 |

La sequenza implementata include quindi `0x50`; ometterlo avrebbe inventato un
ciclo diverso dall'OEM. ACK mancanti, IRQ errati, response inattese, duplicate,
timeout o raster non validi causano stop immediato. Il solo loop è limitato dal
numero di sample esplicito (2–8); nessun retry, recovery A2/`0x70`, reopen o
secondo reader esiste. Il path D268 non viene modificato e resta terminale alla
prima immagine.

`core/multiframe_validation.py` è intenzionalmente un modello con channel
iniettato: non viene aggiunto `0x34` alla physical allowlist e non viene
collegato a `PersistentRuntimeCoordinator`. Fornire 12 byte non chiude la loro
provenienza: in assenza della tabella il contract fallisce
`up_table_source_unresolved`.

## Seam SIGFM LGPL

`libfprint-driver/goodix_sigfm_metrics.cpp` usa l'ABI reale dichiarato da
`Rockytkg/libfprint/libfprint/sigfm/sigfm.h` e il mapper D269; non reimplementa
extractor o matcher. L'API C opaca offre solo extract, match e destroy
effimeri:

- mapping fisso `round(sample*255/4095)`, 80×64 e 5120 byte;
- gate `<25` distinto;
- score `0` valido e distinto da score negativo/error;
- classi separate per NULL, mapping, extract/match exception e matcher error;
- `catch (...)` sul confine C, incluso cleanup;
- nessuna serializzazione SIGFM/FP3, file, rete, USB o TLS.

Il buffer u8 controllato dal wrapper viene azzerato. `SigfmImgInfo` viene
distrutto alla fine della finestra di confronto. Il wrapper non può promettere
erasure di copie dell'allocator/OpenCV né dell'input u16 `const` posseduto dal
caller; il caller deve limitarne e terminare la lifetime. Nessun oggetto
biometrico o hash immagine è persistito.

Il test double è autorizzato solo a verificare plumbing: mapper invariato,
dimensioni, ripetibilità, keypoint count, gate, score, eccezioni e conteggio
alloc/free. Non produce claim su SIFT, qualità target, orientation, polarity o
soglia.

## Piano futuro, non eseguito

Un'unica run futura, solo dopo chiusura dei blocker e nuova autorità, avrebbe al
massimo sei ruoli anonimi `A1,A2,A3,B1,B2,B3`. Le coppie interne ad A o B
misurano la relazione same-finger; le coppie A:B la relazione
different-finger. Il report conserverebbe soltanto status, keypoint count/gate,
relazione, match status/score e failure class. Nessun nome, dito anatomico,
pixel, descrittore, template o hash immagine.

Tre sample per gruppo consentono solo un primo controllo di stabilità e
overlap. Non giustificano calibrazione production e non assumono threshold 20
o 40. L'obiettivo resta
`FEASIBILITY_AND_THRESHOLD_CANDIDATE_VALIDATION`.

## Verifica offline

- lifecycle/operator/privacy Python: PASS;
- regressione runtime D260/D263/D266/D267/D268: 60 test PASS;
- seam SIGFM da Git root e da cwd esterno: strict C/C++ warning audit PASS;
- forbidden symbol audit: PASS;
- seam SIGFM synthetic: PASS normale e ASan/UBSan;
- regressione D269/D270 FpImage: PASS normale e ASan/UBSan;
- kit esatto da Git root e `/tmp`: PASS, tutti i contatori reali zero;
- flag `--future-live`: hard-disabled con exit 1;
- OpenCV4-dev/real SIGFM build: BLOCKED, quindi executable closure FAIL.

I test D260 rigenerano file storici durante l'esecuzione; tali modifiche
derivate sono state eliminate e i blob D260 sono rimasti identici a HEAD.

## Riesame metodologico pre-live

1. Deve cambiare il metodo: chiusura target della tabella up, seconda
   iterazione e gate `0x50`, più build SIGFM reale in ambiente OpenCV4-dev.
2. Solo allora si testerà l'ipotesi che una up-table current-session permetta
   release/re-arm e che i raster target producano metriche preliminarmente
   separabili.
3. Un nuovo fallimento allo stesso punto interromperà il live e riporterà il
   lavoro all'audit offline; non autorizzerà una replica.

```text
MODEL_USED=OPENAI_CODEX_GPT_5_FAMILY_EXACT_DEPLOYMENT_NOT_EXPOSED
REASONING=HIGH
GIT_ROOT=/home/guido/Repository/goodix-27c6-5125_private
STARTING_HEAD=fdc52d04995d65d1e2a895a373e1fe7e24e6fa9f
D271_BASELINE_ANCESTOR_CHECK=PASS
FINAL_WORKTREE_STATUS=DIRTY_EXPECTED_D272_STEP_LOCAL_CHANGES_UNCOMMITTED

FEATURE_EXTRACTOR_POLICY=CLOSED_OFFLINE_SIGFM_VALIDATION_CANDIDATE
SIGFM_STATUS=OFFLINE_METRIC_SEAM_SYNTHETIC_PASS_REAL_BUILD_BLOCKED_OPENCV4_DEV
SIGFM_EXCEPTION_CONTAINMENT=CLOSED_OFFLINE_AT_C_ABI
SIGFM_METRIC_PRIVACY_CONTRACT=CLOSED_OFFLINE_NO_SERIALIZATION
MULTIFRAME_CAPTURE_LIFECYCLE_STATUS=OFFLINE_MODEL_PASS_LIVE_INTEGRATION_BLOCKED
POST_FIRST_IMAGE_0X34_STATUS=OBSERVED_PAYLOAD_UP_TABLE_PROVENANCE_AND_FRESHNESS_UNKNOWN
FINGER_UP_IRQ_0200_STATUS=OBSERVED_AFTER_0X34_ACK_TARGET_TIMEOUT_UNKNOWN
POST_FINGER_UP_0X20_STATUS=OBSERVED_WITH_ACK_AND_B0_SEMANTICS_NOT_QUALITY_PROVEN
REARM_0X32_STATUS=OBSERVED_WITH_ACK_SECOND_CYCLE_COMPLETION_NOT_OBSERVED
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
NEXT_PRIMARY_BOUNDARY=POST_FIRST_IMAGE_MULTIFRAME_CONTRACT_CLOSURE_AND_REAL_SIGFM_BUILD
NEXT_BOUNDARY_PREREQUISITE=TARGET_CLOSE_0X34_UP_TABLE_AND_SECOND_CYCLE_PLUS_EXISTING_OPENCV4_DEV_ENVIRONMENT

BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
REAL_USB_OPEN_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_BIOMETRIC_CAPTURE_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```
