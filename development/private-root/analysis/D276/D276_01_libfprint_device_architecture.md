# D276/01 — architettura production libfprint/FpImageDevice

```text
OUTCOME=READY
ADVANCEMENT=ARCHITECTURAL_CORRECTIVE_RELEASE_TAIL_REENTRANCY_AND_LIFETIME_BOUNDARIES_CLOSED_OFFLINE
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=NATIVE_LGPL_IMPLEMENTATION_ABSENT; TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS_UNRESOLVED; PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED; ENROLLMENT_STAGE_POLICY_NOT_SELECTED; TARGET_DEVICE_TIMEOUT_UNKNOWN; ORIENTATION_POLARITY_PPMM_AND_TARGET_BIOMETRIC_QUALITY_UNRESOLVED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_f370bd2f2775c09f53abf0b1da00581786a456c9_ON_main_PLUS_WORKTREE_FILES_Goodix_27c6_5125_manuale_tecnico.md_analysis_D276_D276_01_libfprint_device_architecture.md_analysis_D276_D276_01_libfprint_device_architecture.json

PRODUCTION_LIBFPRINT_TOPOLOGY=NATIVE_IN_PROCESS_C_LGPL_CLEANROOM
REJECTED_TOPOLOGIES=GPL_OUT_OF_PROCESS_HELPER_WITH_IPC,PYTHON_EMBEDDED_IN_LIBFPRINT
DECISION_CONFIDENCE=HIGH
USB_TRANSPORT_OWNER=GOODIX_FPIMAGE_DEVICE_OPEN_EPOCH_CONTEXT
TLS_SESSION_OWNER=GoodixDeviceContext
SECRET_BOUNDARY_OWNER=GoodixDeviceContext
TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS=UNRESOLVED
SECRET_HANDOFF_POLICY=ONE_HANDOFF_PER_TLS_SESSION
CROSS_ACTIVATION_TLS_REUSE_TARGET_PROVEN=false
FDT_LIFECYCLE_OWNER=GOODIX_FPIMAGE_DEVICE_OPEN_EPOCH_CONTEXT
LIBFPRINT_EVENT_CONTEXT_MODEL=ONE_GLIB_MAIN_CONTEXT_WITH_ASYNC_FPI_USB_TRANSFER_AND_ONE_PHYSICAL_IN_READER
CANCELLATION_MODEL=HOST_IO_CANCEL_AND_DRAIN_INVALIDATE_GENERATION_MARK_PROTOCOL_SESSION_POISONED_QUIESCENCE_UNKNOWN_NO_MASKED_RESUME
HOST_ONLY_TERMINAL_CLEANUP=PROVEN_IN_EXISTING_BOUNDED_RUNTIME
LIBFPRINT_CANCEL_DEVICE_SIDE_PROTOCOL=UNPROVEN
DEVICE_SIDE_CANCEL_COMMAND=NONE_PROVEN
NO_UNPROVEN_CANCEL_COMMAND_ALLOWED=true
PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL=UNRESOLVED
GOODIX_RELEASE_TAIL_ORDER=FINGER_IMAGE_0X34_EXACT_ACK_IRQ0200_DERIVE_VALIDATE_DOWN_TABLE_0X20_EXACT_ACK_POST_UP_B0_CONSUME_DISCARD_0X50_EXACT_ACK_NAV_CONSUME_GOODIX_RELEASE_TAIL_COMPLETE_FINGER_OFF_REPORT_FALSE
FINGER_OFF_REPORT_POINT=AFTER_GOODIX_RELEASE_TAIL_COMPLETE
POST_UP_B0_DELIVERED_TO_LIBFPRINT=false
AWAIT_FINGER_ON_GATES=REARM_0X32_ONLY
AWAIT_FINGER_ON_DOES_NOT_GATE=POST_UP_0X20,POST_UP_B0,NAV_0X50
NON_ENROLL_FINGER_OFF_REENTRANCY=SYNCHRONOUS_DEACTIVATE_ALLOWED_AFTER_RELEASE_TAIL_NO_SUBSEQUENT_GOODIX_COMMAND
ENROLL_REARM_GATE=AWAIT_FINGER_ON_AND_GOODIX_RELEASE_TAIL_COMPLETE_AND_FRESH_SAME_CYCLE_DOWN_TABLE
LIBFPRINT_ENROLLMENT_AGGREGATION=FRAMEWORK_OWNED_VERIFIED
PROJECT_EXTRA_FPIMAGE_AGGREGATOR_REQUIRED=false
LOCAL_LIBFPRINT_DEVICE_GLUE=NOT_YET_IMPLEMENTED
LOCAL_LIBFPRINT_DEVICE_GLUE_ARCHITECTURE=CLOSED_D276_01
GPL_TO_LGPL_CODE_COPY_ALLOWED=false
MECHANICAL_TRANSLATION_ALLOWED=false
CLEANROOM_NATIVE_REIMPLEMENTATION_REQUIRED_IF_SELECTED=true
CLEANROOM_LABEL=PROJECT_ENGINEERING_PROVENANCE_CONTROL_NOT_LEGAL_CONCLUSION
NEXT_PRIMARY_BOUNDARY=LOCAL_LIBFPRINT_DEVICE_GLUE_SLICE_1_HOST_ONLY
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_DEVICE_TIMEOUT=UNKNOWN
REAL_USB_ACCESS=false
REAL_SENSOR_COMMAND_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
LIVE_AUTHORIZED=false
```

## 1. Scope, baseline e metodo

D276/01 resta una decisione architetturale e questo correttivo ne precisa il
release tail, la reentrancy, il lifetime TLS e il cancel; non implementa né
abilita un driver hardware. La baseline del correttivo coincide con quella
richiesta:

```text
branch=main
HEAD=f370bd2f2775c09f53abf0b1da00581786a456c9
initial_worktree=CLEAN
origin/main=f370bd2f2775c09f53abf0b1da00581786a456c9
```

Sono stati letti integralmente governance, manuale, prompt, runtime GPL
pertinente, helper LGPL già locali, API della copia libfprint 1.94.5 e le fonti
Rockytkg richieste con la relativa provenance. Non è stato aperto il device,
non è stato materializzato alcun secret, non è stato contattato fprintd e non è
stato eseguito alcun comando sensore.

Classificazione usata:

- **verificato localmente**: codice/API presenti nel repository o evidenza
  target consolidata nel manuale e negli artefatti D275;
- **decisione architetturale**: scelta production derivata dai requisiti e
  ancora da implementare;
- **corroborazione esterna**: Rockytkg e Issue #1, mai promossi ad autorità
  target-specific APP12509;
- **ignoto**: proprietà non chiuse da evidenza locale.

La pagina pubblica della Issue #1 è stata consultata. Nel rendering disponibile
durante D276/01 erano visibili l'issue e la sua descrizione, non i commenti; il
report terza parte già verificato e canonizzato dal progetto resta quindi
quello registrato nel manuale. Non viene introdotta alcuna nuova claim esterna.

## 2. Evidenza locale che vincola la scelta

Il singolo run bounded D275 ha provato sul target una sola sessione USB, un solo
oggetto server TLS, un solo handshake, un solo handoff del secret e un solo
reader fisico fino al secondo B0, senza retry o reopen. I contatori sono fatti
run-specific da preservare; non provano il riuso della stessa sessione TLS fra
più activation libfprint entro `img_open`→`img_close` e non sono un motivo per
incorporare il runtime Python in production.

La copia locale libfprint dichiara versione `1.94.5`. L'audit dei sorgenti
conferma:

- `FpImageDeviceClass` espone `img_open`, `img_close`, `activate`,
  `change_state` e `deactivate`;
- ogni callback deve completare mediante la corrispondente API
  `fpi_image_device_*_complete()`;
- il driver deve accettare `deactivate` in qualunque momento della capture;
- la cancellazione di enroll/verify/identify/capture entra nel percorso
  `fpi_image_device_deactivate(..., TRUE)`;
- `fpi_device_get_cancellable()` è destinato anche ai transfer asincroni
  `fpi_usb_transfer_submit()`;
- il driver può assumere che le chiamate libfprint avvengano sullo stesso
  thread, pur dovendo gestire la reentrancy di cancel; i callback verso
  `FpImageDevice` devono quindi rimanere nel main context proprietario;
- `fpi_image_device_report_finger_status(self, TRUE/FALSE)` traduce lo stato in
  `FP_FINGER_STATUS_PRESENT/NONE` e guida le transizioni interne;
- `fpi_image_device_image_captured()` avvia l'estrazione asincrona e porta lo
  stato da `CAPTURE` a `AWAIT_FINGER_OFF`;
- da `AWAIT_FINGER_OFF`, `report_finger_status(FALSE)` porta prima a `IDLE` e,
  nel caso non-enroll, chiama sincronicamente `deactivate`; nell'enroll il nuovo
  `AWAIT_FINGER_ON` arriva solo quando sia finger-off sia minutiae completion
  sono avvenuti, in qualunque ordine;
- l'aggregazione enrollment è già del framework:
  `fpi_print_add_print()` → incremento `enroll_stage` →
  `fpi_device_enroll_progress()`;
- il default locale `IMG_ENROLL_STAGES=5` è un default di framework, non
  evidenza che il target supporti cinque acquisizioni production;
- `FpiUsbTransfer` è l'API interna preferita sopra GUsb, supporta submit
  asincrono cancellabile e non consente due submit concorrenti dello stesso
  oggetto.

## 3. Valutazione delle topologie

| Topologia | Vantaggi reali | Costi/rischi production | Decisione |
|---|---|---|---|
| A. runtime nativo C in-process | un processo e un main context; un solo owner USB/TLS/FDT; integrazione diretta con `GCancellable`, `FpiUsbTransfer` e `FpImageDevice`; packaging libfprint naturale; nessun protocollo IPC | richiede una reimplementazione minima C/LGPL indipendente del protocollo/TLS già espresso nel core GPL; richiede test di equivalenza e audit provenance | **selezionata** |
| B. helper GPL out-of-process + IPC | massimizza il riuso del runtime Python già live-proven; il secret può restare nel processo helper | divide il lifecycle fra driver e helper; richiede protocollo IPC, autenticazione/ACL, propagazione cancellazione, crash/restart e packaging coordinato; un restart rischia un reopen implicito e la duplicazione dello state owner, anche se il solo helper apre fisicamente USB | **respinta per production**; utilizzabile solo come harness di ricerca non device glue |
| C. Python embedded in libfprint/fprintd | evita IPC e può riusare il codice Python | GIL e embedding nel main loop; teardown interpreter/TLS/USB fragile; eccezioni Python nel processo fprintd; dipendenze e installazione non upstream-shaped; confine GPL/LGPL opaco e maggiore blast radius | **respinta** |

La topologia A è l'unica che rende strutturale — non soltanto convenzionale —
un owner unico per istanza `FpImageDevice`, trasporto, reader, TLS/secret e
lifecycle Goodix. Questo non decide se un oggetto/sessione TLS sopravviva a più
activation nello stesso open epoch. La difficoltà della reimplementazione è un
costo implementativo controllabile; le ambiguità di ownership delle altre due
topologie sarebbero invece parte permanente dell'architettura production.

La scelta non fissa ancora la libreria crittografica concreta. Il requisito
congelato è un server TLS 1.2 PSK nativo, in-process e alimentato da BIO/memoria
dal medesimo router B0. La selezione OpenSSL/GnuTLS deve essere un audit
build-time ristretto nel successivo slice TLS, mantenendo suite, identity,
single handoff e zeroizzazione già provati; non può introdurre un processo o un
socket esterno.

Packaging production: il driver entra nel build Meson di libfprint come gli
altri driver nativi, con dipendenze C dichiarate e risolte a build-time. Non
introduce daemon, unità systemd, socket/DBus privati, `PYTHONPATH`, ambiente
virtuale o processo TLS. La dependency del provider crittografico deve essere
esplicita e fail-closed quando assente; non sono ammessi `dlopen` opportunistici
o fallback a subprocess.

## 4. Modello di ownership production

Una istanza futura del driver contiene un solo `GoodixDeviceContext`, creato
per l'**open epoch** e distrutto al `close`. Questo contesto è l'unico owner di:

```text
FpImageDevice instance
└── GoodixDeviceContext (open epoch; owning GLib main context)
    ├── borrowed GUsbDevice + claimed interface
    ├── GoodixUsbRouter
    │   ├── one physical bulk-IN transfer at a time
    │   ├── A0/B0 incremental parser
    │   └── logical waiters/queues (never readers)
    ├── GoodixTlsServer (owner unico; lifetime cross-activation UNRESOLVED)
    ├── ScopedSecret (un handoff protetto per sessione TLS; memory only)
    ├── GoodixLifecycle (cold start + FDT/acquisition state)
    ├── activation-local GCancellable
    └── generation/terminal fence
```

Regole non negoziabili del contesto:

1. solo `GoodixUsbRouter` può eseguire un bulk-IN fisico;
2. ACK, A0 event/NAV e B0 TLS/image sono demultiplexati dopo il medesimo parser;
3. un waiter logico non chiama mai USB direttamente;
4. TLS non legge l'endpoint: consuma e produce byte esclusivamente attraverso
   il router B0;
5. il lifecycle Goodix è una sola state machine; `FpImageDevice` resta la
   state machine framework, non viene ricopiata;
6. `change_state` è un input del lifecycle Goodix, non una seconda policy di
   enrollment;
7. ogni callback asincrono verifica open epoch, activation generation e fence
   terminale prima di inviare comandi o notificare libfprint;
8. un errore terminale o una cancellazione in fase non quiescente marca la
   sessione di protocollo `POISONED/QUIESCENCE_UNKNOWN`; non sono consentiti
   recovery, reset, retry, resume mascherato, nuova TLS o reopen implicito;
9. il `GoodixDeviceContext` resta owner di TLS e secret, ma il lifetime della
   sessione TLS attraverso activation multiple resta `UNRESOLVED`; ogni
   sessione TLS ammette esattamente un handoff del secret.

Il `GUsbDevice` viene fornito da libfprint con
`fpi_device_get_usb_device()`. Il driver possiede il claim dell'interfaccia e
il protocollo svolto sull'oggetto durante l'open epoch; non crea un secondo
handle libusb/GUsb e non affianca un thread di lettura bloccante.

## 5. Mapping Goodix ↔ FpImageDevice verificato

Tutte le API `fpi_image_device_*` sotto elencate sono chiamate nel main context
proprietario. L'implementazione preferita usa `FpiUsbTransfer` asincroni; non è
richiesto un worker thread. Se in futuro un calcolo CPU-only usa un worker, il
worker non può possedere USB/TLS/FDT e deve rimandare il risultato al context
prima di toccare `FpImageDevice`.

| Evento / lifecycle Goodix | Owner production | API libfprint 1.94.5 verificata | Thread/context | Teardown/cancel |
|---|---|---|---|---|
| device open | `GoodixDeviceContext` | `img_open` → `fpi_image_device_open_complete(dev, error)` | owning GLib main context; claim GUsb, cold-start/TLS asincroni | failure: chiude TLS/secret, rilascia claim, completa con errore; nessun retry |
| device close | stesso contesto | `img_close` → `fpi_image_device_close_complete(dev, error)` | stesso context; base richiede device inattivo | fence terminale, cancella eventuale I/O host, attende callback, chiude TLS, zeroizza secret, rilascia claim; nessun comando recovery |
| activate / start acquisition | `GoodixLifecycle` nello stesso contesto | `activate` → `fpi_image_device_activate_complete(dev, error)` | stesso context; crea cancellable/generation dell'azione e arma il reader | completa success solo dopo arm valido; errore fail-closed, nessun reopen |
| framework attende dito | framework `FpImageDevice`, osservato dal driver | `change_state(...AWAIT_FINGER_ON)` | stesso context | abilita/re-abilita la sola state machine Goodix; non incrementa stage |
| finger-down IRQ `0x0002` | router + lifecycle unici | `fpi_image_device_report_finger_status(dev, TRUE)`; l'API interna pubblica `PRESENT` e porta `AWAIT_FINGER_ON → CAPTURE` | callback del solo reader nel context | se generazione stale/cancelled, nessuna notifica/comando |
| richiesta/capture `0x22`, ACK, B0 immagine | lifecycle + TLS dello stesso contesto | helper LGPL D269/D270 crea `FpImage(80,64)`; poi `fpi_image_device_image_captured(dev, image)` | stesso context; il riferimento iniziale dell'immagine è ceduto e non riusato dal driver | parse/CRC/shape/helper failure → `fpi_image_device_session_error()`; nessun retry wire |
| attesa finger-up | lifecycle unico | dopo image delivery, framework è `AWAIT_FINGER_OFF`; driver emette il solo `0x34` con tabella up same-generation già provata | stesso context | cancellazione ferma la receive host-side; nessun cancel command device-side |
| finger-up IRQ `0x0200` e release tail | router + lifecycle unici | prima deriva/valida down-table same-cycle, poi `0x20`/ACK esatto, consuma/scarta il B0 post-up, `0x50`/ACK esatto e consuma NAV; solo a `GOODIX_RELEASE_TAIL_COMPLETE` chiama `fpi_image_device_report_finger_status(dev, FALSE)` | stesso context; nessun comando Goodix dopo la callback nella stessa stack frame | il B0 post-up non passa mai a `fpi_image_device_image_captured()`; cancellation già intervenuta interrompe il tail e applica il fence terminale |
| prosecuzione enrollment / re-arm | framework decide lo stage; lifecycle esegue solo il ciclo fisico | solo `change_state(...AWAIT_FINGER_ON)` + `GOODIX_RELEASE_TAIL_COMPLETE` + down-table fresca same-cycle autorizzano `0x32`; nessuna chiamata driver a `fpi_print_add_print()` | continuazione separata che ricontrolla generation/fence | `AWAIT_FINGER_ON` non gatea `0x20`, B0 post-up o NAV `0x50`; non parte una acquisizione 3–8 per policy locale |
| deactivate normale | `GoodixDeviceContext` | `deactivate` → `fpi_image_device_deactivate_complete(dev, error)` | stesso context | cancella il cancellable di activation, drena l'unico transfer e invalida generation; nessun riuso TLS cross-activation è inferito e la policy resta irrisolta |
| cancellation azione | libfprint avvia deactivate; driver esegue cleanup host | base: cancel di enroll/verify/identify/capture → `fpi_image_device_deactivate(..., TRUE)`; driver termina phase-correctly | stesso context; cancella/draina I/O, invalida generation | nessun cancel device-side è provato o ammesso; se il lifecycle non è quiescente marca `POISONED/QUIESCENCE_UNKNOWN`, vieta resume/recovery/retry/reopen e lascia irrisolta la quiescenza production |
| errore fail-closed | lifecycle/context unico | `fpi_image_device_session_error(dev, error)` durante sessione attiva; `*_complete(..., error)` durante open/activate/close | stesso context | marca `POISONED`, invalida generation, deactivation/cleanup exactly-once; nessuna recovery implicita |
| retry biometricamente giustificato | framework/driver, solo dopo evidenza futura | `fpi_image_device_retry_scan()` | stesso context | **non usato nel primo driver** per timeout, protocollo, TLS, CRC o qualità non provata; non autorizza resend wire |

### Gate di coordinamento fra le due state machine legittime

Esistono due state machine, ma hanno ruoli distinti e non duplicati:

- `FpImageDevice` possiede azione, stato dito, feature extraction, match e
  aggregazione enrollment;
- `GoodixLifecycle` possiede esclusivamente la sequenza wire e la freschezza
  FDT.

Il punto di sincronizzazione essenziale è `change_state`:

```text
FpImageDevice AWAIT_FINGER_ON
        + GOODIX_RELEASE_TAIL_COMPLETE
        + fresh same-cycle down-table
        -> unico re-arm fisico / unica wait IRQ2

IRQ2 -> report TRUE -> FpImageDevice CAPTURE
B0 image -> image_captured -> FpImageDevice AWAIT_FINGER_OFF
IRQ0200 -> derive/validate down table
        -> 0x20/exact ACK -> consume/discard post-up B0
        -> 0x50/exact ACK -> consume NAV
        -> GOODIX_RELEASE_TAIL_COMPLETE
        -> report FALSE -> FpImageDevice IDLE

non-enroll: FpImageDevice richiede deactivate
enroll:     solo il successivo AWAIT_FINGER_ON, insieme agli altri due gate,
            autorizza 0x32 e il ciclo fisico seguente
```

`AWAIT_FINGER_ON` gatea soltanto il re-arm `0x32`: il tail
`0x20 → B0 post-up → 0x50 → NAV` è parte del rilascio corrente e deve
completarsi prima della notifica finger-off, salvo cancellation già intervenuta.
Il gate composito impedisce al glue di catturare in anticipo mentre SIGFM sta
ancora elaborando l'immagine e impedisce che un IRQ2 venga notificato quando il
framework non è pronto. Non viene mantenuto un contatore stage nel driver.

## 6. Open epoch, cancellation e terminal fence

### Open

`img_open` crea il contesto e reclama l'interfaccia. Il singolo run D275 ha
osservato cold-start factory-preserving, un oggetto/handshake TLS e un handoff
del secret fino al secondo B0; D276 non promuove questo fatto a policy di
lifetime cross-activation. Al
momento di `fpi_image_device_open_complete(NULL)` non rimane un bulk-IN pendente:
il pending reader lungo appartiene alla activation e usa il suo cancellable.

Il secret viene acquisito dal boundary host protetto già autorizzato, validato
read-only, consegnato una sola volta per sessione TLS e mantenuto soltanto nella
forma/tempo strettamente necessari. Non esistono provisioning, cache PSK o
fallback secret.

### Activate/deactivate

Ogni `activate` crea una generation e un cancellable locali. Tutti i transfer
dell'azione usano quel cancellable; la cancellazione del `GCancellable`
libfprint vi è propagata. `deactivate`, sia normale sia per cancel:

1. chiude il terminal fence per nuove submit/notifiche;
2. cancella il solo transfer attivo tramite il cancellable locale;
3. aspetta che l'eventuale callback ritorni e tratta
   `G_IO_ERROR_CANCELLED` come esito host atteso, senza inferirne quiescenza
   device-side;
4. rilascia waiter/queue/transcript in memoria dell'activation;
5. chiama esattamente una volta `fpi_image_device_deactivate_complete()`.

La fase conta: se la cancellazione arriva mentre `activate` non ha ancora
chiamato `fpi_image_device_activate_complete()`, la base non considera ancora
il device attivo e può ignorare la richiesta di deactivate. Il callback
cancellato deve allora chiudere la generation e completare **activate** con
`G_IO_ERROR_CANCELLED`, senza chiamare `deactivate_complete()`. Analogamente un
cancel durante `img_open` completa **open** con errore dopo cleanup. Solo dopo
un `activate_complete(NULL)` riuscito il percorso terminale usa
`deactivate_complete()`.

`HOST_ONLY_TERMINAL_CLEANUP=PROVEN_IN_EXISTING_BOUNDED_RUNTIME`, ma
`LIBFPRINT_CANCEL_DEVICE_SIDE_PROTOCOL=UNPROVEN` e nessun comando device-side
di cancel è provato. Il driver cancella/draina I/O host, invalida generation e
non invia comandi non compresi. Se la cancellazione interviene in un lifecycle
non quiescente, marca la sessione di protocollo
`POISONED/QUIESCENCE_UNKNOWN`: nessun resume nella stessa sessione, recovery,
reset, retry, TLS restart o reopen automatico. Il normale lifecycle framework
potrà proseguire soltanto secondo una futura policy esplicita; la quiescenza
production dopo cancel arbitrario resta `UNRESOLVED`.

Poiché `report_finger_status(FALSE)` può invocare sincronicamente
`change_state` o `deactivate`, il release tail Goodix deve essere già completo
prima della callback. Nessun comando Goodix viene sottomesso nella stessa stack
frame dopo una callback libfprint che può causare deactivate. Il solo `0x32` è
una continuazione separata, autorizzata dal gate composito
`AWAIT_FINGER_ON + GOODIX_RELEASE_TAIL_COMPLETE + fresh same-cycle down-table`
e dal ricontrollo generation/terminal fence. Se cancellation è già intervenuta,
il tail non prosegue e prevale il fence terminale.

### Close ed errori

`img_close` è l'unico owner della distruzione dell'open epoch: invalida ogni
generation, drena I/O, chiude/zeroizza TLS e secret, rilascia l'interfaccia e
distrugge il contesto. Il cleanup prosegue best-effort anche se una fase
precedente fallisce, conservando il primo errore utile. Non invia reset, A2,
`0x70`, restore, provisioning o altri comandi di recovery.

Timeout USB, frame inatteso, checksum/CRC, stato ACK, TLS o lifecycle errato
sono errori terminali. `TARGET_DEVICE_TIMEOUT=UNKNOWN`: D276 non allarga timeout
e non interpreta un timeout come invito a ritentare.

## 7. FpImage, SIGFM ed enrollment

Il glue riusa i soli helper LGPL già locali:

```text
raster canonico u16 80x64
  -> goodix_u16_to_fpimage (mapping fisso D269)
  -> goodix_fpimage_pipeline
  -> FpImage(80,64), packed u8, flags=0
  -> fpi_image_device_image_captured()
```

Restano invariati:

```text
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
```

Non vengono importati `FPI_IMAGE_COLORS_INVERTED`, `500 DPI`, threshold o
policy dinamica `3..8` da Rockytkg. Il candidato SIGFM e il suo real build
host-only restano validi, ma non sono prova di qualità target.

Il default libfprint locale di cinque stage e il report esterno di otto capture
non selezionano una policy production per APP12509. Fino a una decisione
target-validata, il nuovo driver non deve essere registrato/abilitato come
driver enrollment production. Quando la policy sarà chiusa, l'aggregazione
resterà comunque dentro libfprint; il driver consegnerà una sola `FpImage` per
ciclo richiesto dal framework.

Il contratto offline `2 <= sample_count <= 8` di
`core/multiframe_validation.py` resta un bounded test model. Non diventa né
stage count libfprint né autorità live. L'autorità target Linux rimane
`STOP_AFTER_SECOND_IMAGE`.

## 8. Licensing e reimplementazione indipendente con provenance controllata

La topologia scelta richiede un'implementazione nuova in
`libfprint-driver/`, `LGPL-2.1-or-later`. È vietato copiare, tradurre
meccanicamente o riscrivere riga-per-riga `core/`, `tools/` o componenti Rocky
GPL. Il progetto descrive questa disciplina come **provenance-controlled
independent reimplementation**: è un controllo ingegneristico di provenance,
non una conclusione o garanzia legale
(`CLEANROOM_LABEL=PROJECT_ENGINEERING_PROVENANCE_CONTROL_NOT_LEGAL_CONCLUSION`).

Procedura vincolante per il successivo codice C/LGPL:

1. congelare una specifica neutra di protocollo/lifecycle dai fatti canonici,
   capture sanitizzate, formati e vettori di test; niente struttura del codice
   GPL;
2. registrare per ogni nuovo file autore, SPDX, fonti di fatti e componenti
   terzi consultati;
3. implementare contro specifica, API libfprint locali e primitive TLS/GLib,
   senza traduzione del runtime Python;
4. durante il slice LGPL non consultare, copiare o tradurre il core GPL;
5. usare il runtime GPL soltanto come oracle black-box su transcript sintetici:
   stessi input pubblici/sanitizzati, confronto di frame, transizioni ed errori,
   nessun import/link/copia di espressione;
6. mantenere golden vector privi di secret e dati biometrici; per immagini usare
   fixture sintetiche o metadata permessi;
7. effettuare review differenziale di provenance prima di unire ogni slice;
8. se si riusa una porzione LGPL di `Rockytkg/src/goodixgf.c`, eseguire prima
   audit per-file e ledger. D276 non ne importa alcuna. I valori target non
   provati e la logica dipendente dal core Rocky GPL restano esclusi;
9. rieseguire separatamente safety/behavior sul target solo in un futuro step
   live esplicitamente autorizzato; equivalenza con Rocky non vale come prova.

Il codice Rocky `goodixgf.c` è utile come corroborazione della forma
`FpImageDevice` e della necessità di marshalling al main context, ma la sua
architettura worker/blocking, la policy stage dinamica, `500 DPI`, inversione e
le chiamate al core GPL non sono adottate.

## 9. Minimo percorso implementativo successivo

Il prossimo step locale può essere affidato come task implementativo ristretto,
senza riaprire la topologia:

### Slice 1 — device shell e lifecycle host-only

Creare nel dominio LGPL una classe `FpImageDevice` non ancora registrata per
`27c6:5125`, con:

- `GoodixDeviceContext` e stati `CLOSED/OPENING/INACTIVE/ACTIVATING/ACTIVE/
  DEACTIVATING/POISONED/CLOSING`;
- backend vtable in-memory senza USB/TLS/secret;
- mapping reale `img_open/img_close/activate/change_state/deactivate` e
  callback `report_finger_status/image_captured/session_error`;
- activation-local cancellable, generation e terminal fence;
- test GLib main-loop per cancel in ogni stato, callback stale, completion
  exactly-once e i casi obbligatori
  `NON_ENROLL_FINGER_OFF_SYNCHRONOUS_DEACTIVATE`,
  `ENROLL_FINGER_OFF_WAIT_MINUTIAE`,
  `ENROLL_MINUTIAE_DONE_BEFORE_FINGER_OFF`,
  `ENROLL_FINGER_OFF_BEFORE_MINUTIAE_DONE`,
  `NO_REARM_BEFORE_BOTH_GATES` e `NO_COMMAND_AFTER_DEACTIVATE_FENCE`;
- uso del helper `FpImage(80,64)` già locale con flags zero e ppmm ignoto.

Acceptance: build con warning severi contro la copia libfprint locale, test
host-only, symbol audit senza libusb/OpenSSL/socket/file write nel backend
fake, nessuna registrazione VID:PID, nessuna policy stage scelta.

### Slice 2 — router/protocollo clean-room

Implementare il parser incrementale e un scheduler fake con una sola receive
outstanding. Transcript sintetici devono provare demux A0/B0, IRQ2/IRQ0200,
ACK, immagini, cancellation e nessuna seconda reader API. Il runtime Python è
solo oracle comportamentale.

### Slice 3 — TLS e backend GUsb asincrono

Implementare il TLS server Memory-BIO nativo e poi sostituire il fake con
`FpiUsbTransfer`, mantenendo un solo owner e senza registrare ancora il device.
La dependency TLS va auditata a build-time. Soltanto dopo host-only executable
closure, provenance review, stage-policy decision e nuova baseline live
approvata potrà esistere un task hardware separato.

Lo skeleton non è stato creato in D276/01: senza la separazione in slice sopra
avrebbe anticipato interfacce di backend/TLS non ancora sottoposte a test e non
avrebbe provato altro rispetto alla decisione documentale. Non è quindi stato
aggiunto scaffolding decorativo.

## 10. Stato preservato e limiti

```text
LINUX_FIRST_IMAGE_LIVE_OBSERVED=true
LINUX_IRQ0200_AFTER_0X34=OBSERVED
LINUX_SECOND_IRQ0002=OBSERVED
LINUX_SECOND_0X22=OBSERVED
LINUX_SECOND_B0_LIVE_OBSERVED=true
STOP_AFTER_SECOND_IMAGE_LIVE=PASS
FDT_TABLE_MISMATCH_CAUSALITY=LIVE_VALIDATED

TARGET_DEVICE_TIMEOUT=UNKNOWN
LIVE_AUTHORIZED=false
PERSISTENT_DEVICE_WRITE_COUNT=0
HOST_CACHE_WRITE_COUNT=0
RETRY_COUNT=0
TRANSPORT_REOPEN_AFTER_TLS=false
USB_TRANSPORT_SESSION_COUNT=1
TLS_SERVER_HANDSHAKE_COUNT=1
SECRET_BOUNDARY_HANDOFF_COUNT=1
PRESERVED_D275_COUNTER_SCOPE=ONE_BOUNDED_RUN_TO_SECOND_B0_NOT_CROSS_ACTIVATION_POLICY
TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS=UNRESOLVED
PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL=UNRESOLVED

REAL_SIGFM_BUILD=PASS_HOST_ONLY_WITH_REAL_OPENCV4
REAL_SIGFM_LINK=PASS
REAL_SIGFM_MATCH_PATH=PASS
SIGFM_PPMM_REQUIREMENT=NOT_CONSUMED_VERIFIED
```

D276/01 produce avanzamento architetturale offline. Non produce executable
closure, nuova evidenza hardware, qualità biometrica, supporto a un terzo ciclo,
driver installabile o integrazione fprintd/PAM.
