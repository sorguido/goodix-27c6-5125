# D268/02 — Post-live first-image evidence closure (corrective AI-PM)

## Esito

```text
OUTCOME=READY — D268_02_FIRST_IMAGE_LIVE_EVIDENCE_CLOSED
ADVANCEMENT=LIVE_FIRST_IMAGE_BOUNDARY_CLOSED_AND_LINUX_LIBFPRINT_BOUNDARY_DEFINED
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT; ORIENTATION_UNRESOLVED
CANONICAL_DOCUMENTATION=UPDATED
LIVE_EVIDENCE_CLOSURE=PASS
D267_01_CAUSAL_CLASSIFICATION=STRONG_CAUSAL_INFERENCE
FPRINTD_RESTORE_EVIDENCE_CLASS=VERIFIED_BY_CONTROL_FLOW_NOT_EXTERNAL_STATE_OBSERVATION
D220_CLOSURE_PRESERVED=true
NEXT_PRIMARY_BOUNDARY=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT
FIRST_IMAGE_RECEIVED=true
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_RASTER_SHAPE=80x64
D267_01_CAUSE=STRONG_CAUSAL_INFERENCE
D268_RETRY_AUTHORIZED=false
LIVE_AUTHORIZED=false
HIGH_LEVEL_CANONICAL_STATE_COHERENCE=PASS
D268_TABLE_FPRINTD_WORDING=PASS
```

D268/02 è **OFFLINE ONLY**. Non esegue hardware, non usa `sudo`, non apre USB
reale, non materializza secret reali, non esegue una seconda run D268 e non
modifica la semantica live-critical. La run D268 one-shot appartiene alla baseline
approvata `c03d32e8647444495e6615e41c2839cbddd62143` ed è conclusa; il marker è
consumato e nessuna nuova autorizzazione live è implicita.

La review AI-PM del primo bundle ha classificato `LIVE_EVIDENCE_CLOSURE=PASS` e
ha richiesto corrective su coerenza canonica, precisione epistemica e scelta del
prossimo boundary. Questo corrective li applica senza degradare l'evidenza live.

## Verifica iniziale

- Git root reale: `/home/guido/Repository/goodix-27c6-5125_private`.
- Branch corrente: `development`; HEAD: `c03d32e8647444495e6615e41c2839cbddd62143`
  (baseline approvata D268).
- Worktree pulito salvo i file di prompt/artefatti D268/02 non tracciati.
- Nessun cambio di branch; nessuna modifica a `core/`, `tools/`, `operator_kit/`.

## Micro-corrective documentale (finale)

La review AI-PM del corrective D268/02 ha dato
`HIGH_LEVEL_CANONICAL_STATE_COHERENCE=FAIL` e `D268_TABLE_FPRINTD_WORDING=FAIL_MINOR`.
Questo micro-corrective è **esclusivamente documentale**: non introduce alcuna
nuova decisione tecnica e non crea D268/03. Ha qualificato come storiche/superseded
le frasi D257 (fresh-FDT non autorizzato), D259 (plumbing UNIMPLEMENTED) e D264/D265
(`0x22`/first image non live-proven) nel manuale, ha aggiunto una sintesi di stato
corrente post-D268 all'inizio di `## Stato del progetto`, e ha corretto la
formulazione fprintd nella tabella D268 (cleanup/zeroizzazione riusciti; restore
callback completata senza eccezione; stato esterno finale fprintd non osservato
indipendentemente). Tutto il resto del D268/02 approvato è preservato.

## Evidenza live classificata (invariata, corretta)

```text
FIRST_IMAGE_B0_LIVE_PROVEN=true
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_ADDITIVE_CHECKSUM_MISMATCH_LIVE_OBSERVED=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_RASTER_SHAPE=80x64
FIRST_IMAGE_RECEIVED=true
```

Punto essenziale: `trailer=0x88`, `payload additive checksum match=false`,
`policy=NO_CHECK_0X88_ACCEPTED`, `record CRC=true`, `decode=successful_raster_decode`,
`shape=80x64`.

## Classificazione epistemica D267/01 (corretta)

```text
D267_01_FIRST_B0_RECEIVED=OBSERVED
D267_01_FIRST_IMAGE_DECODE_FAILED=OBSERVED
D267_01_ACTUAL_TRAILER=UNKNOWN
D268_FIRST_IMAGE_TRAILER_0X88=OBSERVED_TARGET_LIVE
D268_ADDITIVE_CHECKSUM_MATCH_FALSE=OBSERVED_TARGET_LIVE
OLD_STRICT_ADDITIVE_PARSER_MISMATCH_WITH_0X88=VERIFIED
D267_01_CAUSE=STRONG_CAUSAL_INFERENCE
```

D267/01 non viene riscritto come se avesse registrato `0x88` allora: il trailer
effettivo resta `UNKNOWN`; la causa è inferenza causale forte, non osservazione
retroattiva.

## Safety closure

```text
USB_OPEN_COUNT=1
TRANSPORT_SESSION_COUNT=1
TLS_OBJECT_COUNT=1
TLS_HANDSHAKE_COUNT=1
SECRET_MATERIALIZATION_COUNT=1
FINAL_FDT_ARM_COUNT=1
IRQ2_FINGER_DOWN_COUNT=1
COMMAND_22_ATTEMPT_COUNT=1
COMMAND_22_ACK_VALIDATION_COUNT=1
FIRST_B0_COUNT=1
RETRY_COUNT=0
RECOVERY_COUNT=0
REOPEN_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
FORBIDDEN_POST_IMAGE_COMMAND_COUNT=0
HOST_CLEANUP_STATUS=COMPLETATO
SECRET_ZEROIZED=true
```

## Fprintd restore (corretto)

```text
FPRINTD_RESTORE_CALLBACK_COMPLETED_WITHOUT_EXCEPTION=VERIFIED_BY_CONTROL_FLOW
EXTERNAL_FPRINTD_FINAL_STATE=NOT_INDEPENDENTLY_OBSERVED
FPRINTD_RESTORE_EVIDENCE_CLASS=VERIFIED_BY_CONTROL_FLOW_NOT_EXTERNAL_STATE_OBSERVATION
```

Il report protetto non è leggibile senza privilegi; non si usa `sudo` e non si
promuove il fatto a osservazione indipendente dello stato esterno del servizio.

## Closure canonica D218–D220 preservata (recuperata)

```text
D220_WINDOWS_PREPROCESSOR_CONSUMES_U16_NO_U8_ADAPTER_JUSTIFIED=true
INTENSITY_CONTRACT=DIRECT_U16_CONSUMED_PROVEN
ORIENTATION_CONTRACT=UNRESOLVED
NEXT_BLOCKER=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT
D220_CLOSURE_PRESERVED=true
```

Windows/`AlgoChicago.dll` consuma direttamente il raster `u16`/12-bit; non è
giustificato alcun adapter `u16 → u8` ricostruito dal contratto Windows;
l'orientamento resta non risolto; la decisione successiva è Linux-specifica.

## Prossimo boundary (corretto)

```text
NEXT_PRIMARY_BOUNDARY=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT
```

Parte dal nuovo fatto D268 (`target live image → valid image record → decoded
raster 80x64 u16`) e dalla conoscenza D220 (Windows consuma u16 direttamente, nessun
adapter u8). Sottoproblemi per il prossimo step (senza assumere la soluzione):

```text
libfprint image representation requirements
u16/12-bit -> Linux/libfprint mapping
scaling / clipping / normalization policy
orientation / transpose / flags
quality/preprocessing ownership
whether conversion belongs in GPL core or LGPL libfprint glue
```

Non si implementa codice in D268/02: il task successivo è definito per review AI-PM.

## Aggiornamenti manuale canonico

- "Stato del progetto": enumerazione dei confini ora **chiusi live** (A8, E4, TLS,
  D4, AF, fresh-FDT bounded path, IRQ2, `0x22`, ACK `0x22`, primo B0, decode prima
  immagine, raster `80x64`); vecchi blocker D252/D253/D259/D264 marcati storici.
- Tabella stato: D253 qualificata `HISTORICAL / SUPERSEDED BY D267+D268`; riga
  Codec immagine aggiornata a CRC record validato live + decode eseguito live.
- "Current critical boundary": next boundary = decisione engineering Linux/libfprint,
  con integrazione closure D218–D220.
- Nuova sottosezione `### D218–D220` in "Stato implementazione Linux".
- Roadmap: estesa da D268 alla decisione Linux/libfprint.
- D267/01 wording: classificazione epistemica esatta (strong causal inference).
- D268/02: next boundary corretto e campi richiesti presenti.

## Artefatti D268/02

```text
analysis/D268/D268_02_post_live_first_image_closure_report.md
analysis/D268/D268_02_live_evidence_summary.json
analysis/D268/D268_02_execution_manifest.json
analysis/D268/D268_02_bundle_manifest.json
analysis/D268/D268_02_post_live_first_image_closure_bundle.zip
analysis/D268/D268_02_post_live_first_image_closure_bundle.zip.sha256
```

`EXECUTABLE_CLOSURE=NOT_APPLICABLE`. Nessun raw image, raster, pixel, TLS plaintext,
PSK o materiale biometrico nei derivati.
