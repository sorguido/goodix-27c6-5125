# D268/02 — Post-live first-image evidence closure e definizione del prossimo boundary

**Reasoning: HIGH**  
**Modello consigliato: AI Free**  
**Execution mode: OFFLINE ONLY**  
**Expected working branch: `development`**

## Contesto minimo

D268/01 ha preparato il nuovo Kit Operatore first-image. La review AI-PM ha approvato come baseline live-critical:

```text
c03d32e8647444495e6615e41c2839cbddd62143
```

L'Utente ha quindi autorizzato **una sola run live D268**, eseguita esclusivamente tramite Kit Operatore italiano.

La run è conclusa con questo riepilogo osservato dal terminale:

```text
OUTCOME = PASS_D268_FIRST_IMAGE_LIVE
APPROVED_BASELINE_SHA = c03d32e8647444495e6615e41c2839cbddd62143
LIVE_ATTEMPT_INVOCATION_COUNT = 1
D268_MARKER_CLAIMED = True

USB_OPEN_COUNT = 1
TRANSPORT_SESSION_COUNT = 1
TLS_OBJECT_COUNT = 1
TLS_HANDSHAKE_COUNT = 1
SECRET_MATERIALIZATION_COUNT = 1

FINAL_FDT_ARM_COUNT = 1
IRQ2_FINGER_DOWN_COUNT = 1
COMMAND_22_ATTEMPT_COUNT = 1
COMMAND_22_ACK_VALIDATION_COUNT = 1
FIRST_B0_COUNT = 1

FIRST_IMAGE_DECODE_STATUS = SUCCESSFUL_RASTER_DECODE
FIRST_IMAGE_DECODE_STAGE = successful_raster_decode
FIRST_IMAGE_DECODE_EXCEPTION = None
FIRST_IMAGE_PAYLOAD_TRAILER_CLASS = 0X88
FIRST_IMAGE_PAYLOAD_CHECKSUM_POLICY = NO_CHECK_0X88_ACCEPTED
FIRST_IMAGE_PAYLOAD_CHECKSUM_MATCH = False
FIRST_IMAGE_RECORD_CRC_MATCH = True
FIRST_IMAGE_RASTER_SHAPE = [80, 64]

RETRY_COUNT = 0
RECOVERY_COUNT = 0
REOPEN_COUNT = 0
PERSISTENT_DEVICE_WRITE_COUNT = 0
FORBIDDEN_POST_IMAGE_COMMAND_COUNT = 0

TERMINAL_BOUNDARY = STOP_AFTER_FIRST_IMAGE
LIVE_RESULT = PASS_STOP_AFTER_FIRST_IMAGE
FAILURE_CLASS = NESSUNO
HOST_CLEANUP_STATUS = COMPLETATO
FPRINTD_RESTORE_STATUS = VEDI_REPORT_OPERATORE
SECRET_ZEROIZED = True
```

**La run non deve essere ripetuta.** Il marker D268 è consumato e nessuna nuova autorizzazione live è implicita.

---

## Obiettivo

Chiudere **offline** la nuova evidenza live first-image, aggiornare organicamente il manuale canonico e definire il prossimo vero boundary tecnico dopo il raster 80×64.

Questo step non deve modificare la semantica live-critical né eseguire hardware.

---

## 1. Verifica iniziale

Prima di lavorare:

1. determina la Git root reale;
2. leggi linee guida canoniche, `AGENTS.md`, manuale tecnico e D267/03, D267/04, D268/01 pertinenti;
3. verifica branch, HEAD e worktree;
4. non cambiare branch;
5. non sovrascrivere modifiche utente non correlate.

La run live appartiene alla baseline approvata `c03d32e...`; eventuali commit successivi di sola documentazione non devono essere retroattivamente confusi con quella baseline.

---

## 2. Evidenza live da classificare

Registra come **osservato target-specific live**:

```text
FIRST_IMAGE_B0_LIVE_PROVEN=true
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_ADDITIVE_CHECKSUM_MISMATCH_LIVE_OBSERVED=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_RASTER_SHAPE=80x64
FIRST_IMAGE_RECEIVED=true
```

Il punto essenziale è:

```text
trailer = 0x88
payload additive checksum match = false
policy = NO_CHECK_0X88_ACCEPTED
record CRC = true
decode = successful_raster_decode
shape = 80x64
```

Questa è ora evidenza primaria sul target APP12509, non più semplice corroborazione statica/OEM/third-party.

Mantieni però distinta la causalità storica D267/01:

- **osservato in D267/01**: primo B0 ricevuto, poi `first_image_decode_failed`;
- **osservato in D268**: il primo payload immagine usa `0x88`, non coincide con l'additive checksum, CRC record valido, raster 80×64;
- **inferenza causale forte**: D267/01 è molto probabilmente fallito sul precedente parser strict additive checksum;
- **non osservato direttamente**: il trailer effettivo della run D267/01.

Non riscrivere D267/01 come se il suo `0x88` fosse stato registrato allora.

---

## 3. Safety closure

Consolida come osservato dalla run:

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

### Fprintd restore

Il terminale espone soltanto:

```text
FPRINTD_RESTORE_STATUS=VEDI_REPORT_OPERATORE
```

Il codice D268 però esegue `restore_fprintd()` nel `finally`; se tale callback solleva eccezione, registra `fprintd_restore_failure` e forza:

```text
result = FAIL_CLOSED_CLEANUP_INCOMPLETE
```

La run ha invece restituito:

```text
LIVE_RESULT=PASS_STOP_AFTER_FIRST_IMAGE
```

Quindi è lecito classificare:

```text
FPRINTD_RESTORE_CALLBACK_COMPLETED_WITHOUT_EXCEPTION=VERIFIED_BY_CONTROL_FLOW
```

Non promuovere automaticamente questo fatto a osservazione indipendente dello stato esterno del servizio.

Il report protetto canonico previsto è:

```text
/var/lib/goodix-5125-poc/d261-results/d268-first-image-final.json
```

Se è leggibile **senza** `sudo`, ispezionalo e confrontalo con il summary.  
Se non è leggibile con i normali permessi, **non usare sudo, non cambiare permessi e non bloccare lo step**: documenta il limite e usa il summary live sopra + il control-flow verificabile del codice.

---

## 4. Nessun nuovo live / nessuna modifica runtime

Vietato in questo step:

- accesso USB reale;
- `sudo`;
- nuova run D268;
- cancellazione/riuso del marker;
- secret reale;
- TLS/device reale;
- nuovi comandi sensor-reaching;
- modifiche a `core/`, `tools/` o `operator_kit/` che cambino comportamento live;
- nuova autorizzazione o nuova baseline live.

La run D268 è one-shot conclusa.

---

## 5. Manuale tecnico canonico

Aggiorna organicamente:

```text
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

Il manuale deve riflettere chiaramente che il boundary first-image è ora **chiuso live**.

Aggiorna almeno:

- stato alto/canonico del progetto;
- D268/01 da “Kit ready offline” a “run live conclusa PASS”;
- semantica image `0x88` ora target-proven;
- additive checksum mismatch osservato live;
- CRC-32/MPEG-2 del record osservato valido live;
- decode raster `80x64` live-proven;
- D267/01 riclassificato con inferenza causale forte ma non retroattivamente “osservato `0x88`”;
- safety telemetry essenziale;
- marker/autorizzazione D268 consumati;
- regola permanente già decisa dall'Utente: qualunque futuro live esclusivamente tramite Kit Operatore dedicato in italiano;
- prossimo boundary tecnico.

Evita duplicazioni append-only: aggiorna anche tabelle/stato corrente/roadmap se presenti.

---

## 6. Definizione del prossimo vero boundary

Esamina il repository e il manuale per stabilire quale sia il **primo confine non ancora chiuso dopo `FIRST_IMAGE_RECEIVED`**.

Non assumere automaticamente che il prossimo step sia già enrollment o matcher.

Valuta in ordine logico almeno:

```text
raw raster semantics / orientation / transpose
image normalization / usable intensity range
quality / finger-vs-background semantics
eventual preprocessing expected by libfprint
capture lifecycle needed for repeated frames
boundary toward biometric pipeline
matcher/enrollment integration only when prerequisites are actually closed
```

Per ciascun candidato distingui:

- già chiuso;
- parzialmente chiuso;
- non implementato;
- non provato target-specific;
- blocker reale vs semplice lavoro futuro.

Scegli **un solo prossimo boundary principale** e spiega perché massimizza l'avanzamento tecnico senza nuova cerimonia.

Se il prossimo boundary richiede implementazione nuova/architetturale, non implementarlo in D268/02: definisci il task successivo per review AI-PM.

---

## 7. Artefatti D268/02

Crea sotto:

```text
analysis/D268/
```

almeno:

```text
D268_02_post_live_first_image_closure_report.md
D268_02_live_evidence_summary.json
D268_02_execution_manifest.json
D268_02_bundle_manifest.json
```

Il JSON evidence summary deve contenere solo metadata sanitizzati e nessun dato biometrico.

Non includere raw image, raster, pixel o plaintext: è sufficiente documentare shape/status/policy/CRC.

Per questo step:

```text
EXECUTABLE_CLOSURE=NOT_APPLICABLE
```

salvo che tu modifichi accidentalmente un percorso eseguibile, cosa che non è richiesta.

---

## 8. Git e bundle

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

Produci un vero ZIP step-local non cumulativo:

```text
analysis/D268/D268_02_post_live_first_image_closure_bundle.zip
analysis/D268/D268_02_post_live_first_image_closure_bundle.zip.sha256
```

Il bundle deve contenere soltanto il review set D268/02 e le porzioni/file canonici realmente modificati necessari alla review.

Non includere:

- bundle precedenti;
- report protetto raw se contiene materiale non necessario;
- capture;
- B0/TLS plaintext;
- raster/pixel;
- immagini;
- PSK/secret;
- materiale biometrico.

---

## 9. Closure finale

Usa i sei campi canonici.

Massimo outcome atteso:

```text
OUTCOME=READY — D268_02_FIRST_IMAGE_LIVE_EVIDENCE_CLOSED
ADVANCEMENT=LIVE_FIRST_IMAGE_BOUNDARY_CLOSED_AND_NEXT_BIOMETRIC_BOUNDARY_DEFINED
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=<next technical boundary, not first-image decode>
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=<path + sha256>
```

In aggiunta, riporta sinteticamente:

```text
FIRST_IMAGE_RECEIVED=true
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_RASTER_SHAPE=80x64
D268_RETRY_AUTHORIZED=false
LIVE_AUTHORIZED=false
```
