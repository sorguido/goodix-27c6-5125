# D268/02 — Corrective AI-PM su manuale canonico e next boundary

**Modello consigliato: AI Free**  
**Reasoning: HIGH**  
**Execution mode: OFFLINE ONLY**  
**Expected working branch: `development`**

## Contesto

La review AI-PM del primo bundle D268/02 ha classificato:

```text
D268_02_AI_PM_REVIEW=CORRECTIVE_REQUIRED
LIVE_EVIDENCE_CLOSURE=PASS
BUNDLE_INTEGRITY=PASS
SANITIZATION=PASS
CANONICAL_MANUAL_COHERENCE=FAIL
NEXT_BOUNDARY_SELECTION=FAIL
D220_CLOSURE_PRESERVED=false
LIVE_AUTHORIZED=false
D268_RETRY_AUTHORIZED=false
```

La closure probatoria della run live D268 è buona e **non va rifatta né reinterpretata**.

La run D268 resta chiusa come:

```text
OUTCOME=PASS_D268_FIRST_IMAGE_LIVE
FIRST_IMAGE_RECEIVED=true
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_RASTER_SHAPE=80x64
D268_RETRY_AUTHORIZED=false
LIVE_AUTHORIZED=false
```

Il corrective riguarda principalmente **coerenza canonica del manuale, precisione epistemica e scelta del prossimo boundary**.

---

## 1. Preparazione

Prima di modificare file:

1. determina la Git root reale;
2. leggi `AGENTS.md`, linee guida canoniche, manuale tecnico corrente e gli artefatti D218–D220, D267/01–D267/04, D268/01–D268/02 pertinenti;
3. verifica di essere sul branch `development`;
4. registra full HEAD e stato worktree;
5. non cambiare branch e non sovrascrivere modifiche utente non correlate.

Non eseguire hardware, `sudo`, USB reale, secret reale o qualunque live.

---

## 2. Preserva integralmente la closure live D268

Non degradare né riscrivere l'evidenza già corretta.

Mantieni come **osservato target-specific live**:

```text
FIRST_IMAGE_B0_LIVE_PROVEN=true
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_ADDITIVE_CHECKSUM_MISMATCH_LIVE_OBSERVED=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_RASTER_SHAPE=80x64
FIRST_IMAGE_RECEIVED=true
```

Mantieni anche:

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

Non autorizzare una seconda run.

---

## 3. Correggi la classificazione epistemica D267/01

Il manuale non deve dire che la causa di D267/01 sia stata “verificata” direttamente.

La classificazione corretta è:

```text
D267_01_FIRST_B0_RECEIVED=OBSERVED
D267_01_FIRST_IMAGE_DECODE_FAILED=OBSERVED
D267_01_ACTUAL_TRAILER=UNKNOWN

D268_FIRST_IMAGE_TRAILER_0X88=OBSERVED_TARGET_LIVE
D268_ADDITIVE_CHECKSUM_MATCH_FALSE=OBSERVED_TARGET_LIVE
OLD_STRICT_ADDITIVE_PARSER_MISMATCH_WITH_0X88=VERIFIED

D267_01_CAUSE=STRONG_CAUSAL_INFERENCE
```

Formula quindi D267/01 come **inferenza causale forte**, non come osservazione retroattiva del trailer `0x88`.

---

## 4. Correggi la classificazione fprintd

Il terminale D268 esponeva:

```text
FPRINTD_RESTORE_STATUS=VEDI_REPORT_OPERATORE
```

Il report protetto non era leggibile senza privilegi.

Dal control-flow D268 è verificabile che:

```text
FPRINTD_RESTORE_CALLBACK_COMPLETED_WITHOUT_EXCEPTION=VERIFIED_BY_CONTROL_FLOW
```

perché una failure del callback avrebbe prodotto cleanup incompleto e non
`PASS_STOP_AFTER_FIRST_IMAGE`.

Non promuovere però questo fatto a osservazione indipendente dello stato esterno finale del servizio.

Usa una formulazione equivalente a:

```text
FPRINTD_RESTORE_CALLBACK_COMPLETED_WITHOUT_EXCEPTION=VERIFIED_BY_CONTROL_FLOW
EXTERNAL_FPRINTD_FINAL_STATE=NOT_INDEPENDENTLY_OBSERVED
```

---

## 5. Recupera e reintegra la closure canonica D218–D220

Il primo D268/02 ha scelto come prossimo boundary una nuova analisi generica di
orientation / transpose / normalizzazione del raster.

Questa scelta è incompleta perché il progetto aveva già chiuso una parte
fondamentale del problema in D218–D220.

Recupera dagli artefatti/manuale storico le conclusioni effettivamente supportate
e reintegrale organicamente nel manuale corrente, senza inventare dati.

La decisione canonica da preservare è almeno:

```text
D220_WINDOWS_PREPROCESSOR_CONSUMES_U16_NO_U8_ADAPTER_JUSTIFIED
INTENSITY_CONTRACT=DIRECT_U16_CONSUMED_PROVEN
ORIENTATION_CONTRACT=UNRESOLVED
NEXT_BLOCKER=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT
```

Il significato da preservare è:

- Windows/AlgoChicago consuma direttamente il raster `u16` / 12-bit;
- non è giustificato inventare un adapter `u16 -> u8` come ricostruzione del contratto Windows;
- orientation resta non risolta;
- la successiva decisione è **Linux-specifica**, non una nuova campagna statica Windows.

Non creare una nuova indagine statica sull'immagine se D220 l'aveva già chiusa come non utile.

---

## 6. Correggi il prossimo boundary

Il prossimo boundary principale deve essere:

```text
LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT
```

Questo boundary deve partire dal fatto nuovo D268:

```text
target live image
→ valid image record
→ decoded raster 80x64 u16
```

e dalla conoscenza D220:

```text
Windows preprocessing consumes u16 directly
→ no Windows-derived u8 adapter
```

La domanda tecnica successiva è quindi come rappresentare/adattare correttamente il raster Goodix `80x64 u16/12-bit` verso il contratto Linux/libfprint, mantenendo distinta:

- semantica del sensore;
- contratto Windows già ricostruito;
- engineering decision Linux;
- orientation ancora `UNRESOLVED`.

### Non implementare ancora il nuovo boundary in questo corrective

D268/02 deve soltanto definire correttamente il task successivo.

Nel report specifica i sottoproblemi che il prossimo step dovrà affrontare, ad esempio:

```text
libfprint image representation requirements
u16/12-bit -> Linux/libfprint mapping
scaling / clipping / normalization policy
orientation / transpose / flags
quality/preprocessing ownership
whether conversion belongs in GPL core or LGPL libfprint glue
```

ma senza assumere in anticipo la soluzione.

---

## 7. Aggiorna realmente lo “Stato del progetto”

La sezione alta del manuale contiene ancora blocker storici espressi come se fossero correnti.

Riconciliala con lo stato attuale.

Deve essere immediatamente chiaro che sono ora **chiusi live**:

```text
A8
E4
TLS 1.2 PSK
D4
AF
fresh-FDT bounded path
IRQ2
0x22
ACK 0x22
first B0
first image decode
80x64 raster
```

I vecchi blocker D259/D264/D253 ecc. possono restare come storia, ma vanno marcati
esplicitamente come storici/superseded dove necessario.

Non cancellare provenance utile: aggiorna lo stato canonico e lascia la storia nel suo contesto.

---

## 8. Correggi tabelle e roadmap stale

Rivedi almeno le righe che oggi risultano semanticamente stale.

### D253

La riga storica può dire che **a D253** `0x22` e first-image non erano ancora live-proven,
ma non deve concludere al presente che “restano blocker”.

Qualifica come:

```text
HISTORICAL / SUPERSEDED BY D267+D268
```

o equivalente.

### Codec immagine

La riga:

```text
Codec immagine | confermato offline | record 7684 -> raster u16 80x64
```

deve riflettere lo stato corrente:

- algoritmo codec già confermato offline;
- record CRC validato live;
- decode eseguito live;
- raster `80x64` live-proven.

### Roadmap

La roadmap corrente deve portare esplicitamente da D268 alla decisione Linux/libfprint,
non a una nuova campagna generica sul raster Windows.

---

## 9. Timestamp metadata

Nel primo bundle D268/02 alcuni JSON usavano:

```text
generated_utc = <timestamp con offset +02:00>
```

Correggi il naming o il valore.

Accettabile:

```text
generated_at = 2026-...+02:00
```

oppure:

```text
generated_utc = 2026-...Z
```

Non chiamare `utc` un timestamp locale con offset `+02:00`.

---

## 10. Artefatti D268/02 da rigenerare

Rigenera nello stesso step D268/02, senza creare D268/03.

Mantieni almeno:

```text
analysis/D268/D268_02_post_live_first_image_closure_report.md
analysis/D268/D268_02_live_evidence_summary.json
analysis/D268/D268_02_execution_manifest.json
analysis/D268/D268_02_bundle_manifest.json
```

Il report deve contenere chiaramente:

```text
LIVE_EVIDENCE_CLOSURE=PASS
D267_01_CAUSAL_CLASSIFICATION=STRONG_CAUSAL_INFERENCE
FPRINTD_RESTORE_EVIDENCE_CLASS=VERIFIED_BY_CONTROL_FLOW_NOT_EXTERNAL_STATE_OBSERVATION
D220_CLOSURE_PRESERVED=true
NEXT_PRIMARY_BOUNDARY=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT
EXECUTABLE_CLOSURE=NOT_APPLICABLE
LIVE_AUTHORIZED=false
D268_RETRY_AUTHORIZED=false
```

Nessun raw image, raster, pixel, TLS plaintext, PSK o materiale biometrico nei derivati.

---

## 11. Manuale canonico

Aggiorna organicamente:

```text
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

Non limitarti ad aggiungere un nuovo paragrafo D268/02.

Aggiorna ricorsivamente:

- stato alto;
- tabella stato;
- roadmap;
- closure D218–D220;
- D267/01 wording;
- D268 live closure;
- next boundary.

Il manuale deve risultare leggibile anche da chi non conosce le chat e deve condurre logicamente dallo stato attuale al prossimo task Linux/libfprint.

---

## 12. Git

Non eseguire:

```text
commit
push
merge
rebase
reset
amend
branch creation/switch
history rewrite
```

---

## 13. Bundle finale

Produci un nuovo vero ZIP step-local, non cumulativo:

```text
analysis/D268/D268_02_post_live_first_image_closure_bundle.zip
analysis/D268/D268_02_post_live_first_image_closure_bundle.zip.sha256
```

Sostituisci il bundle D268/02 precedente con la versione corretta.

Il bundle deve contenere soltanto il review set D268/02 necessario.

---

## 14. Closure finale

Usa i sei campi canonici.

Massimo outcome:

```text
OUTCOME=READY — D268_02_FIRST_IMAGE_LIVE_EVIDENCE_CLOSED
ADVANCEMENT=LIVE_FIRST_IMAGE_BOUNDARY_CLOSED_AND_LINUX_LIBFPRINT_BOUNDARY_DEFINED
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT; ORIENTATION_UNRESOLVED
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=<path + sha256>
```

Aggiungi sinteticamente:

```text
D220_CLOSURE_PRESERVED=true
FIRST_IMAGE_RECEIVED=true
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_RASTER_SHAPE=80x64
D267_01_CAUSE=STRONG_CAUSAL_INFERENCE
D268_RETRY_AUTHORIZED=false
LIVE_AUTHORIZED=false
```
