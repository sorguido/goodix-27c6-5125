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

## Claim consentiti e non-claim

È provato offline che:

- il template SIGFM FP3 prodotto dalla vera action target-native è
  serializzabile, deserializzabile e riusabile dopo close/open;
- il grafo production-shaped compone enrollment e identify in context completi
  distinti, preservando una sola action per epoch;
- identify match e no-match terminano dopo una sola acquisizione, senza re-arm,
  retry o cleanup incompleto;
- FP3 manifestamente corrotto viene rifiutato prima dell'action.

Non è provato che:

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
di enrollment, identify match e identify no-match. **INFERRED:** il target
reale dovrebbe applicare la stessa semantica al futuro epoch identify perché
usa lo stesso lifecycle. **UNKNOWN:** esito e telemetria del futuro identify
reale restano non provati senza nuova Human Gate.

Il preflight completo ha ricostruito la libreria target esatta e il client con
baseline `UNAPPROVED_FOR_LIVE`; il self-test ha rifiutato prima di
`fp_context_new()`. Le suite production-shaped 26/26 normale e 26/26
sanitizer e la suite Fedora/SIGFM reale sono PASS. La verifica strutturale del
kit è 10/10 PASS, include i sette scenari dei contatori e riconcilia l'audit live
D279/57; l'auditor hash-pinned è 2/2 PASS. Nessun USB è stato enumerato e
nessuna esecuzione live è stata effettuata.

La breve presenza host-side di un template autentico sarebbe nuova
manipolazione di dato biometrico sensibile. Il percorso ordinario non lo
scrive su SSD: usa `tmpfs`, azzera i buffer posseduti, rimuove il file prima
dell'identify e la directory nel cleanup. Restano residui possibili in RAM,
swap/ibernazione, core dump e crash non intercettabile; non è dichiarata
cancellazione fisica universale. Questo rischio deve essere accettato
esplicitamente insieme alla nuova Human Gate.

## Closure e prossimo confine

```text
OUTCOME=HUMAN_REQUIRED
ADVANCEMENT=POST_CLOSE_FP3_REUSE_AND_PRODUCTION_SHAPED_IDENTIFY_COMPOSED
EXECUTABLE_CLOSURE=PASS_OFFLINE_OPERATOR_KIT_PLUS_NORMAL_SANITIZER_AND_EXACT_FEDORA44_SIGFM
RESIDUAL_BLOCKER_OR_RISK=AUTHENTIC_TEMPLATE_REUSE_REQUIRES_NEW_LIVE_AND_RAM_SWAP_CRASH_BIOMETRIC_RISK_ACCEPTANCE
CANONICAL_DOCUMENTATION=MANUAL_AND_THIS_REPORT
REVIEW_SET=GIT_NATIVE
CURRENT_LIVE_AUTHORIZED=false
```

Il prossimo confine autonomo è esaurito: il kit sostanziale è pronto ma non ha
una baseline approvata. Eseguirlo, accedere USB o creare anche temporaneamente
un template autentico richiede una nuova Human Gate specifica. Solo un PASS
autentico renderebbe sensato isolare poi fprintd/on-disk e l'integrazione
end-user; nessuna run è autorizzata da questo report.
