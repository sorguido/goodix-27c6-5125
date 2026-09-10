<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D280/01 — template FP3 attraverso close/open e identify production-shaped

Data: 2026-09-10
Branch: `development`
Boundary precedente: D279 chiuso live sul fixed-eight enrollment APP12509.

## Decisione e scopo

D280 è un nuovo milestone perché la run reale D279/57 ha chiuso il precedente
confine enrollment e ha prodotto nuova evidenza target. D280/01 affronta il
successivo confine tecnico sostanziale verso un driver Linux utilizzabile:
comporre enrollment, ownership del template, una nuova open epoch e identify
single-acquisition senza aggirare `one-action-per-open`.

Lo step è esclusivamente offline e usa due prove complementari:

1. il test production-shaped attraversa l'intera catena open, pre-session RX,
   secure session, TLS, bootstrap, enrollment a otto stage, close/open e
   identify; usa backend e materiale sintetici e il test double SIGFM;
2. il build esatto Fedora 44/libfprint 1.94.100 usa R2 e SIGFM Rockytkg reali,
   serializza il template nelle API pubbliche FP3, distrugge il print in
   memoria, chiude e riapre il device virtuale, deserializza i soli byte e li
   usa come gallery identify.

Questa separazione è intenzionale: la vecchia copia Rockytkg/libfprint usata
dal grande harness production-shaped ha una primitiva storica SIGFM
`fp_print_serialize()` non idonea a questa prova; la snapshot di provenance non
è stata modificata. La vera closure FP3 appartiene al sorgente target Fedora
già corretto e usato dal build production.

## Implementazione

`test_goodix_d278_secure_session.c` aggiunge un caso end-to-end che:

- completa 8/8 stage enrollment e drena il primo backend;
- chiude il primo context, verificando release di interfaccia e materiale;
- riapre lo stesso `FpDevice`, ottenendo un context/backend/TLS epoch nuovo;
- esegue un identify con una sola acquisizione, match e nessun re-arm;
- chiude e riapre ancora soltanto per il caso no-match, anch'esso con una sola
  acquisizione e senza retry;
- chiude ogni epoch con claim/release/material-release esattamente bilanciati;
- registra zero submit USB reali e zero famiglie persistenti note.

Il SIGFM test double ora rende configurabile soltanto lo score di match, così
lo stesso percorso framework viene provato con risultato positivo e negativo.
Non simula serializzazione: quella resta coperta dal test target-native.

`test_goodix_fedora44_nbis_action.c` ora:

- produce un template SIGFM reale da otto raster sintetici strutturati;
- serializza FP3 e conserva soltanto la sequenza byte in un blob host-side;
- chiude, verifica la distruzione del context e riapre;
- deserializza il blob, verifica compatibilità e metadati e completa identify
  con score reale osservato `1026/40`;
- rifiuta fail-closed un FP3 con header corrotto;
- non salva il blob su disco e non esegue fprintd.

Nessun file production sensor-reaching è cambiato: il delta è un aumento della
closure eseguibile e della conoscenza canonica.

## Verifiche

Comandi eseguiti:

```text
libfprint-driver/tests/run_goodix_d278_secure_session_test.sh
libfprint-driver/tests/run_goodix_fedora44_nbis_action_test.sh \
  /tmp/goodix-d279-57-approved.LlqGn8/opencv-rpms
```

Risultati:

```text
SECURE_SESSION_NORMAL_TESTS=26/26_PASS
SECURE_SESSION_SANITIZER_TESTS=26/26_PASS
D280_01_OPERATOR_STRUCTURAL_TESTS=10/10_PASS
D279_57_HASH_PINNED_AUDIT_TESTS=2/2_PASS
D280_01_TLS_SUCCESS_CONTRACT=HANDSHAKE_1_TERMINAL_0_SECRET_ZEROIZED
D280_01_RUNTIME_COUNTER_SCENARIOS=7/7_PASS
D280_01_PRODUCTION_SHAPED_ENROLL_CLOSE_OPEN_IDENTIFY=PASS
D280_01_SUCCESSFUL_IDENTIFY_ACQUISITION_COUNT=1
D280_01_MISMATCH_IDENTIFY_ACQUISITION_COUNT=1
D280_01_IDENTIFY_REARM_COUNT=0
D280_01_PRODUCTION_SHAPED_SIGFM_IMPLEMENTATION=TEST_DOUBLE
D280_01_FP3_SURVIVES_CLOSE_REOPEN=PASS
D280_01_TRUE_SIGFM_TWO_OPEN_EPOCH_REUSE=PASS
D280_01_CORRUPT_FP3_REJECTED=PASS
D280_01_TEMPLATE_PERSISTED_TO_DISK=false
D280_01_FPRINTD_EXECUTION_COUNT=0
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
LIVE_EXECUTION_PERFORMED=false
```

Il build target continua inoltre a verificare registry unico `27c6:5125`, ABI
fprintd installata a 47 simboli e pacchetto
`fprintd-1.94.5-5.fc44.x86_64`. Gli RPM OpenCV 4.13 preesistenti sono stati
validati contro il manifest hash-pinned ed estratti sotto `/tmp`; nessun
pacchetto è stato installato e il sandbox Flatpak è stato eseguito senza rete.

## Claim consentiti e non-claim alla closure offline pre-live

È provato offline che:

- il template SIGFM FP3 prodotto dalla vera action target-native è
  serializzabile, deserializzabile e riusabile dopo close/open;
- il grafo production-shaped compone enrollment e identify in context completi
  distinti, preservando una sola action per epoch;
- identify match e no-match terminano dopo una sola acquisizione, senza re-arm,
  retry o cleanup incompleto;
- FP3 manifestamente corrotto viene rifiutato prima dell'action.

Alla closure offline non era ancora provato che (stato superseded dalla
sezione live seguente dove applicabile):

- un template biometrico autentico sia persistito o riusabile;
- il target Linux reale completi identify o restituisca un match;
- la soglia SIGFM `40` abbia adeguate proprietà FAR/FRR;
- fprintd salvi/ricarichi il template o che D-Bus, PAM, login e sudo funzionino;
- il sensore non modifichi stato persistente non appartenente alle famiglie
  note osservate.

## Operator boundary preparato offline

La review AI-PM ha accettato la composizione offline e, senza aprire un
micro-step D280/02, ha completato nello stesso D280/01
`operator_kit/d280-01-ephemeral-template-reuse/`. Il client e il launcher:

- autorizzano esattamente due action, una enrollment e una identify, in due
  open epoch; il secondo epoch è subordinato al PASS dell'audit del primo;
- verificano baseline compilata/runtime, HEAD/origin, live-critical set,
  artefatti hash-bound e grant single-use prima dell'USB;
- rifiutano prima dell'USB un host dove `/run` non sia `tmpfs`, creano una
  directory dedicata root `0700` e verificano di nuovo `TMPFS_MAGIC` dall'fd;
- creano FP3 soltanto con `O_EXCL|O_NOFOLLOW|O_CLOEXEC`, owner root, modo
  `0600` e limite 16 MiB sotto `/run/goodix-d280-01/`;
- cancellano i buffer host, distruggono il print enrollment prima del close e
  rimuovono il pathname FP3 prima dell'identify; client e trap tentano cleanup
  anche su errore o segnale;
- rifiutano l'export se il template o la directory RAM correlata sono ancora
  presenti ed esportano soltanto `operator.log` e `summary.env`, mai byte o
  hash del template;
- espongono audit separati per enrollment e identify, zero retry/reopen
  transport/reset/clear-halt, backend drenato e famiglie persistenti note;
- estraggono dal blocco terminale del log i contatori osservati di action,
  enrollment, identify, open, reopen e close. Valori mancanti, duplicati,
  malformati o incoerenti rendono la run non-PASS; i limiti `*_MAX` restano
  separati dai valori osservati.

### Correttivo AI-PM: contratto TLS

La prima versione del gate D280 richiedeva erroneamente
`tls.terminal_completion_count == 1`. L'evidenza autentica D279/57 osserva
invece handshake `1`, terminal completion `0` e secret zeroized `true`. La
lettura del codice verifica che il contatore cresce soltanto nel percorso
`terminal()` del TLS server (peer close, record/error/fence anomali); il
normale successo production raggiunge `GOODIX_SECURE_PHASE_STOP` e libera il
TLS già completato senza sintetizzare un evento terminale.

La semantica corretta del successo nominale, ora applicata a entrambi gli
epoch D280, è quindi:

```text
TLS_HANDSHAKE_COUNT=1
TLS_TERMINAL_COMPLETION_COUNT=0
TLS_SECRET_ZEROIZED=true
```

**OBSERVED:** questi tre valori provengono dal live D279/57 hash-pinned.
**VERIFIED:** call-site e lifecycle spiegano `0` come assenza di terminale TLS
anomalo; il test production-shaped verifica lo stesso contratto dopo il close
di enrollment, identify match e identify no-match. **INFERRED allo stato
pre-live:** il target avrebbe dovuto applicare la stessa semantica all'epoch
identify perché usa lo stesso lifecycle. La successiva run autentica,
riesaminata sotto, ha confermato handshake `1` e terminal completion `0` anche
nel secondo epoch.

Il preflight completo ha ricostruito la libreria target esatta e il client con
baseline `UNAPPROVED_FOR_LIVE`; il self-test ha rifiutato prima di
`fp_context_new()`. Le suite production-shaped 26/26 normale e 26/26
sanitizer e la suite Fedora/SIGFM reale sono PASS. La verifica strutturale del
kit è 10/10 PASS, include i sette scenari dei contatori e riconcilia l'audit live
D279/57; l'auditor hash-pinned è 2/2 PASS. Nessun USB è stato enumerato e
nessuna esecuzione live è stata effettuata.

La breve presenza host-side di un template autentico costituiva nuova
manipolazione di dato biometrico sensibile, accettata nella Human Gate poi
consumata. Il percorso ordinario non lo
scrive su SSD: usa `tmpfs`, azzera i buffer posseduti, rimuove il file prima
dell'identify e la directory nel cleanup. Restano residui possibili in RAM,
swap/ibernazione, core dump e crash non intercettabile; non è dichiarata
cancellazione fisica universale. Questo rischio deve essere accettato
esplicitamente insieme alla nuova Human Gate.

## Evidenza live autentica e review indipendente

La Human Gate è stata eseguita una sola volta sulla baseline completa
`6cbcb9af88fa5401895208e9fd5217a6374ffb85`; il grant è consumato e non
autorizza retry. I soli due artefatti sanitizzati, senza FP3, sono importati
byte-identici in
`captures/D280_01/D28001_20260910T082439Z_6cbcb9af/sanitized/`:

```text
operator.log SHA-256 = 6b30227b831eb1f534a97afdff18a264985f93a587d030ea2016a62690bc7580
summary.env SHA-256  = 8589963046c5c020158ab365032a6ba3d2565869fa4195e32ef3c263aae592a4
TEMPLATE_INCLUDED_IN_EXPORT=false
```

L'auditor deterministico
`analysis/D280/d280_01_authentic_live_reuse_audit.py` rilegge i due hash,
l'esatto codice al commit live tramite Git e tutti i predicati del gate. Il
log non stampava ogni campo della struct: perciò il report distingue i valori
`OBSERVED` dai valori `VERIFIED_BY_*_CONTROL_FLOW`, senza promuovere questi
ultimi a osservazioni wire.

### Confronto completo di `common_audit_pass()`

| Predicato | Valore autentico | Base | Esito |
|---|---:|---|---|
| `context_closed` | true | OBSERVED | PASS |
| `production_action_consumed` | true | VERIFIED: identify production avviata | PASS |
| `usb_backend_drained` | true | OBSERVED | PASS |
| `usb_interface_claimed` | false | VERIFIED: release precede snapshot del close riuscito | PASS |
| `usb_outstanding_count` | 0 | OBSERVED | PASS |
| `usb_out_outstanding_count` | 0 | OBSERVED | PASS |
| `runtime_material_present` | false | VERIFIED: owner liberato prima dello snapshot | PASS |
| `runtime_handoff_views_cleared` | true | VERIFIED: secure graph completato | PASS |
| `runtime_material.owner_free_count` | 1 | VERIFIED: singolo owner dell'open epoch | PASS |
| `runtime_material.descriptor_cleansed` | true | VERIFIED: `goodix_runtime_material_free()` | PASS |
| `runtime_material.fdt_seed_cleansed` | true | VERIFIED: `goodix_runtime_material_free()` | PASS |
| `tls.handshake_count` | 1 | OBSERVED | PASS |
| `tls.terminal_completion_count` | 0 | OBSERVED | PASS |
| `tls.project_secret_zeroized` | true | VERIFIED: TLS free precede snapshot | PASS |
| `secure.retry_count` | 0 | OBSERVED | PASS |
| `secure.transport_reopen_count` | 0 | OBSERVED | PASS |
| `secure.device_reset_count` | 0 | OBSERVED | PASS |
| `secure.clear_halt_count` | 0 | OBSERVED | PASS |
| `post_tls.retry_count` | 0 | OBSERVED | PASS |
| `post_tls.reopen_count` | 0 | VERIFIED: zero-init, nessun increment path | PASS |
| `post_tls.device_reset_count` | 0 | VERIFIED: zero-init, nessun increment path | PASS |
| `post_tls.clear_halt_count` | 0 | VERIFIED: zero-init, nessun increment path | PASS |
| somma famiglie persistenti note | 0 | OBSERVED | PASS |

### Confronto completo di `identify_audit_pass()`

| Predicato | Atteso dal gate live | Valore autentico | Base | Esito storico |
|---|---:|---:|---|---|
| `first_image_pipeline_count` | 1 | 1 | OBSERVED | PASS |
| `release_tail_complete_count` | 1 | 1 | OBSERVED | PASS |
| `single_acquisition_terminal_count` | 1 | 1 | OBSERVED | PASS |
| `rearm_0x32_count` | 0 | 0 | OBSERVED | PASS |
| `second_image_pipeline_count` | 0 | 0 | VERIFIED: single-acquisition → STOP | PASS |
| `third_cycle_command_count` | 0 | 0 | VERIFIED: STOP non accetta altri comandi | PASS |
| `terminal` | **true** | **false** | VERIFIED: è il flag d'errore TERMINAL | **FAIL** |
| `backend_drained` | true | true | VERIFIED: lifecycle free su backend drenato | PASS |
| `terminal_cleanup_completed` | true | true | VERIFIED: lifecycle free prima dello snapshot | PASS |

L'unico predicato che ha causato
`EPOCH2_IDENTIFY_AUDIT_PASS=false` è dunque `post_tls.terminal == true`.
`lifecycle_fail()` porta lo state machine in
`GOODIX_POST_TLS_PHASE_TERMINAL` e imposta quel flag. Il profilo nominale
`GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION`, dopo il release NAV,
porta invece a `GOODIX_POST_TLS_PHASE_STOP` e incrementa
`single_acquisition_terminal_count`. La parola “terminal” nel nome del
contatore significa conclusione della singola acquisizione, non errore.

Il gate è corretto in `!audit->post_tls.terminal`; non cambia alcun comando,
transizione o profilo sensor-reaching. La stampa audit futura espone inoltre
tutti i campi prima impliciti. La regressione production-shaped verifica
esplicitamente STOP/non-TERMINAL, backend drain, cleanup, assenza di seconda
pipeline e di terzo ciclo. La regressione Python è legata direttamente ai due
artefatti autentici e fallisce chiusa su una loro mutazione.

### Rivalutazione della run consumata

Il risultato originale non viene riscritto:

```text
ORIGINAL_RUN_RETURN_CODE=1
ORIGINAL_EPOCH2_IDENTIFY_AUDIT_PASS=false
ORIGINAL_D280_01_EPHEMERAL_TEMPLATE_REUSE_PASS=false
```

Applicando deterministicamente il contratto corretto agli stessi dati, tutti
i predicati passano e non serve una nuova live:

```text
CORRECTED_CONTRACT_EPOCH2_IDENTIFY_AUDIT_PASS=true
CORRECTED_CONTRACT_D280_01_EPHEMERAL_TEMPLATE_REUSE_PASS=true
```

La stessa evidenza è sufficiente per elevare a `VERIFIED_LIVE`:

- serializzazione FP3 del print prodotto dall'enrollment autentico;
- riuso dei soli byte FP3 attraverso close/open;
- deserializzazione FP3 autentica e compatibilità col device riaperto;
- identify con una sola acquisizione, senza re-arm o retry;
- match biometrico del dito che l'operatore era istruito a riutilizzare, con
  una callback match e zero no-match/retry.

Questi claim non provano una soglia FAR/FRR, il comportamento con dita diverse,
fprintd/storage/PAM/login/sudo o assenza assoluta di persistenza sensor-side.
La telemetria osserva soltanto zero famiglie persistenti note.

## Closure e prossimo confine

```text
OUTCOME=PASS
ADVANCEMENT=AUTHENTIC_FP3_SERIALIZE_CLOSE_OPEN_DESERIALIZE_SINGLE_ACQUISITION_IDENTIFY_MATCH_VERIFIED_LIVE
EXECUTABLE_CLOSURE=PASS_AFTER_DETERMINISTIC_CORRECTED_CONTRACT_RE_EVALUATION
ORIGINAL_RUN_RETURN_CODE=1
AUDIT_BUG_ONLY_FAILED_PREDICATE=post_tls.terminal_expected_true_actual_false
D280_01_LIVE_BASELINE=6cbcb9af88fa5401895208e9fd5217a6374ffb85
D280_01_GRANT_CONSUMED=true
D280_01_RETRY_AUTHORIZED=false
D280_01_AUTHENTIC_EVIDENCE_TESTS=4/4_PASS
D280_01_OPERATOR_STRUCTURAL_TESTS=11/11_PASS
D280_01_SECURE_SESSION_NORMAL=26/26_PASS
D280_01_SECURE_SESSION_ASAN_UBSAN=26/26_PASS
D280_01_FEDORA44_SIGFM_ACTION=PASS
D280_01_OFFLINE_PREFLIGHT=PASS_REFUSED_BEFORE_USB
SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false
CANONICAL_DOCUMENTATION=MANUAL_AND_THIS_REPORT
REVIEW_SET=GIT_NATIVE
CURRENT_LIVE_AUTHORIZED=false
NEXT_PRIMARY_BOUNDARY=D281_01_OFFLINE_FPRINTD_STORAGE_AND_END_USER_CONTROL_PLANE_INTEGRATION
```

D280/01 e la milestone D280 sono chiusi. Il prossimo boundary sostanziale non
è un altro test del protocollo Goodix: è D281/01, una integrazione fprintd
offline e isolata che eserciti, in un unico slice, daemon/D-Bus, storage FP3,
reload in un nuovo processo e identify/verify attraverso una device seam
virtuale esplicitamente incapace di enumerare USB. Il test deve usare
`STATE_DIRECTORY` temporanea, bus privato e dati sintetici; deve validare
ownership, permessi, naming, load/corruption/delete e ABI della libreria
costruita. Installazione di sistema, `/var/lib/fprint`, PAM/login/sudo,
materiale biometrico autentico e sensore reale restano fuori scope e soggetti
a Human Gate separati.
