<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/01 attempt 02 — analisi post-live e correttivo offline

## Decisione AI-PM

```text
OUTCOME=CORRECTIVE
ADVANCEMENT=NEW_TARGET_RUN_EVIDENCE_AND_DETERMINISTIC_FPRINTD_CALL_FLOW_ROOT_CAUSE
EXECUTABLE_CLOSURE=PASS_OFFLINE_63_OF_63_PLUS_DIRECT_PROFILE_NORMAL_AND_ASAN_UBSAN
RESIDUAL_BLOCKER_OR_RISK=ATTEMPT_02_CONSUMED;NO_NEW_BASELINE_GRANT_OR_LIVE_AUTHORIZATION
CANONICAL_DOCUMENTATION=GOODIX_TECHNICAL_MANUAL_UPDATED
REVIEW_SET=GIT_NATIVE
```

L'attempt 02 sulla baseline
`cc2452e52809d2adeccce83a9fe493a241770832` è chiuso. Il grant one-shot è
consumato e `RETRY_AUTHORIZED=false`. Non è stata eseguita né autorizzata una
nuova run durante questa analisi.

## Evidenza primaria e limite dell'export

Gli allegati sono importati byte-identici sotto
`captures/D282_01/D28201_ATTEMPT_02_cc2452e5/sanitized/` e verificati ai
digest riportati nella relativa `PROVENANCE.md`.

**OSSERVATO negli allegati:** candidate esatta mappata; target unico prima del
consumo; live e accesso sensore eseguiti; RC 1; grant consumato; retry vietato;
servizio, staging, libreria di sistema e storage preesistente ripristinati.

**OSSERVATO nel transcript console fornito dall'operatore:** SELinux Enforcing
ha registrato un AVC sulla lettura OpenCV di `nr_hugepages`; dopo un solo
contatto dell'indice destro il client ha stampato, nell'ordine,
`enroll-stage-passed` e `enroll-unknown-error`, poi è terminato senza chiedere
un secondo contatto.

`operator.log` contiene però soltanto `EXACT_LIBRARY_MAP_VERIFIED=true`; il
launcher della baseline raccoglieva journal e audit soltanto dopo enrollment e
verify riusciti. Il return immediato sul primo failure ha quindi escluso
`GOODIX_D282_EPOCH_AUDIT`, warning fprintd e contatori Goodix/TLS dall'export.
Quei valori esatti restano **NON OSSERVATI** e non vengono inventati.

## Root cause verificata

Il sorgente esatto fprintd Fedora 44 è deterministico:

1. `fprint_device_enroll_start()` vede `FP_DEVICE_FEATURE_IDENTIFY`, carica la
   gallery D282 isolata e chiama `fp_device_identify()` prima di ENROLL;
2. al termine senza match `enroll_identify_cb()` emette
   `enroll-stage-passed` con `done=false` e chiama subito `enroll_start()`;
3. soltanto `enroll_start()` invoca `fp_device_enroll()`.

Il primo contatto osservato appartiene quindi al controllo anti-duplicato
IDENTIFY, non allo stage 1/8 dell'enrollment. Il messaggio
`enroll-stage-passed` osservato è il marker di transizione fprintd
IDENTIFY→ENROLL.

Nel driver della baseline la prima activation production imposta
`production_action_consumed=true` per l'intera open epoch. La seconda
activation ENROLL viene contata e respinta prima di generation, TLS o submit
USB con `FP_DEVICE_ERROR_NOT_SUPPORTED` (`close/reopen required`). fprintd
mappa tale errore a `enroll-unknown-error`. Questa catena spiega esattamente
l'ordine osservato e l'assenza di un secondo contatto.

```text
ROOT_CAUSE=FPRINTD_DUPLICATE_IDENTIFY_THEN_ENROLL_COLLIDES_WITH_GOODIX_ONE_ACTION_PER_OPEN_EPOCH_FENCE
FIRST_CONTACT_ACTION=IDENTIFY
ACTUAL_ENROLL_SENSOR_ACQUISITION_COUNT=0
SECOND_ACTION_ATTEMPT=ENROLL_REJECTED_PRE_GENERATION
SECOND_SENSOR_REACHING_ACTION_COUNT=0
PRODUCTION_ACTION_FENCE_EFFECTIVE=true
```

L'AVC `nr_hugepages` precede un IDENTIFY completato fino al callback senza
errore che emette `enroll-stage-passed`; non può quindi essere la causa del
successivo rigetto ENROLL. Non si propone `audit2allow`, `semodule` o alcuna
modifica persistente SELinux.

## Stato protocollo, TLS, cleanup e storage

Il transcript e il call-flow verificano una sola acquisizione IDENTIFY e zero
reachability sensore della seconda action. L'export non contiene tuttavia
l'audit epoch: i valori esatti di submit, TLS, B0, release tail, drain, retry,
reopen, reset e clear-halt restano non osservati. Il summary osserva invece
rollback completo, servizio ripristinato, staging rimosso, libreria di sistema
invariata e storage preesistente invariato. Nessun FP3 può essere stato creato:
ENROLL è stato respinto prima della generation e lo storage D282 è stato poi
rimosso dal rollback.

## Correttivo offline

Il correttivo non allenta il fence e non autorizza quattro action/undici
contatti. La sola candidate D282 viene compilata con
`GOODIX_D282_DIRECT_ENROLL_PROFILE`: conserva VERIFY ma rimuove IDENTIFY dai
feature bit pubblicizzati. Il sorgente fprintd esatto prende così il ramo
diretto `enroll_start()` e la sequenza torna entro l'autorità originaria:
un ENROLL da otto contatti e due VERIFY da un contatto ciascuno.

Il launcher raccoglie inoltre, prima di ogni return di failure enrollment, RC,
conteggi client, journal fprintd, audit epoch e AVC filtrati/sanitizzati. Un
futuro failure non potrà più produrre un `operator.log` di una sola riga.

## Riesame metodologico pre-live

1. **Cosa cambia realmente?** La feature IDENTIFY non viene pubblicizzata
   nella build D282, quindi fprintd non consuma un'azione preliminare; inoltre
   la diagnostica failure viene raccolta prima del rollback.
2. **Quale nuova ipotesi viene testata?** Con il ramo fprintd diretto, ENROLL è
   la prima e unica action della prima open epoch e può raggiungere gli otto
   stage già provati live dal percorso Goodix, restando entro 3 action e 10
   contatti autorizzabili.
3. **Se fallisce nello stesso punto?** Nessun tentativo equivalente. Si usa
   l'audit tipizzato ora preservato per distinguere action, generation, TLS,
   lifecycle e cleanup e si torna a un correttivo offline.

La preparazione di una nuova candidate, la sua approvazione full-SHA, un nuovo
grant e una nuova autorizzazione live restano decisioni separate.

## Verifica del correttivo

La matrice D282 completa passa `63/63` fuori dal solo vincolo socket del
sandbox corrente. I quattro test aggiunti legano il call-flow fprintd esatto,
il profilo build-only, la raccolta evidence-before-return e i digest degli
allegati importati. Il test C dedicato istanzia la classe USB Goodix e osserva
`IDENTIFY=false`, `VERIFY=true` sia nella build normale sia sotto ASan/UBSan.
`bash -n`, `sh -n`, confronto byte-per-byte degli allegati e `git diff --check`
sono PASS.
