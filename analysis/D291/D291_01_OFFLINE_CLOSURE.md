<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D291/01 — riesame post-live della stabilità biometrica

> Il nome storico del file è conservato per evitare frammentazione. Questo
> documento non dichiara più una closure D291.

## Decisione

Le evidenze aggregate successive a `6ccacbcd28b06db9a7f3174d3d5c0350f87b164f`
confermano il risultato transport di D291 ma smentiscono la precedente
conclusione che la sola lifetime della baseline R2 fosse una root cause
dimostrata. Il correttivo ha prodotto un MATCH reale, ma non stabilità
biometrica ripetibile.

```text
D291_MULTI_VERIFY_TRANSPORT=PROVEN
D291_MAX_TRIES_3_PAM_CONTROL=WORKING
D291_BASELINE_PINNING=IMPLEMENTED_NOT_VALIDATED
D291_BASELINE_LIFETIME_ROOT_CAUSE=NOT_PROVEN
D291_BIOMETRIC_STABILITY=OPEN
D291_CLOSURE=NOT_ALLOWED
NEW_LIVE_REQUIRED_NOW=false
PM_DECISION=REPLAN
```

## Evidenza live aggregata

La candidate `8ed02cc3467899c8b1e6f914cc5870e04b6ff4e0` aveva già
provato tre `VerifyStart` espliciti, una acquisizione per epoch, reopen reale
alle epoch 2/3, TLS e drain corretti e zero retry, reset, clear-halt o famiglie
persistenti. Le tre acquisizioni terminarono NO_MATCH: il primo dito era
deliberatamente errato; i due contatti successivi erano l'indice destro
registrato e produssero rispettivamente 133 e 119 keypoint, con otto score
zero.

La candidate `6ccacbc` conserva invece la prima baseline R2 nel logical open.
La live Human Gate ha dato:

- tentativo 1, dito errato: 108 keypoint, otto score zero;
- tentativo 2, indice destro: 151 keypoint, score `0,0,0,0,47` e MATCH sul
  quinto sample, con baseline riusata.

Due serie normali immediatamente successive, avviate come invocazioni
indipendenti, hanno poi dato sei NO_MATCH su sei contatti con l'indice destro.
Ogni prima epoch aveva `reopen=0`, `sigfm_baseline_pinned=1` e quindi una
baseline appena acquisita; le epoch successive avevano il reuse atteso. I
keypoint osservati nelle due serie sono `129,145,122` e `124,112,106`, mentre
ogni confronto contro gli otto sample ha score zero.

Nel solo corpus post-`6ccacbc` consegnato all'AI risultano otto VERIFY fisiche:
un MATCH e sette NO_MATCH; il primo NO_MATCH era deliberatamente un dito
errato. Il campione è piccolo e condizionato e non consente una stima
statistica di FRR, ma è sufficiente a impedire qualunque claim di stabilità.
Le ulteriori riuscite riferite dall'operatore non sono quantificate perché i
relativi log non fanno parte dell'evidenza consegnata.

Il MATCH a score 47 supera di soli 7 punti la soglia 40. È prova funzionale
valida, non margine robusto paragonabile al 376 osservato in D289 o agli score
più elevati presenti nelle precedenti evidenze versionate.

## Confronto del primo epoch: pre-D291 contro `6ccacbc`

Il confronto del codice fra `02c0cd0` e `6ccacbc` stabilisce quanto segue:

1. `GoodixDeviceContext` è allocato con `g_new0`, quindi una nuova `img_open`
   parte con `sigfm_baseline_valid=false`;
2. pre-D291, `context_post_tls_image()` copiava la B0 della sessione in un
   buffer locale e passava quella B0 con il frame a
   `goodix_fpimage_pipeline_new_sigfm()`;
3. in `6ccacbc`, al primo epoch dello stesso nuovo logical open, la medesima
   B0 di sessione viene prima copiata nel context e poi passata, senza
   trasformazioni, allo stesso entrypoint con lo stesso frame;
4. teardown/reopen, reset dei contatori USB e controllo PAM `max-tries=3`
   avvengono soltanto dopo il risultato della prima action e non possono
   modificarne score o keypoint.

Ne consegue una equivalenza code-path del raster R2 del primo epoch,
condizionata a input B0/frame identici. I byte reali degli input non sono
registrati, quindi non è possibile provare che due contatti fisici abbiano
ricevuto input identici né riprodurre il risultato live.

```text
FIRST_FRESH_EPOCH_R2_CODE_PATH_EQUIVALENT=true
EQUIVALENCE_CONDITION=identical_B0_and_frame_inputs
REAL_INPUT_IDENTITY_ACROSS_RUNS=NOT_PROVEN
D291_FIRST_EPOCH_REGRESSION_BY_BASELINE_REUSE=DISPROVEN
```

In particolare, la spiegazione “baseline mantenuta troppo a lungo tra
invocazioni `sudo` indipendenti” è esclusa dagli audit: ogni nuova invocazione
parte con `reopen=0` e pinna una nuova B0.

## Perché 100–150 keypoint possono coesistere con otto score zero

`sigfm_extract()` usa SIFT e il conteggio keypoint misura soltanto quanti punti
locali vengono estratti dalla probe. `sigfm_match_score()` applica poi un
confronto distinto:

- BFMatcher KNN sui descrittori;
- ratio test `0.75` fra primo e secondo vicino;
- minimo cinque corrispondenze descrittore;
- coerenza geometrica fra coppie, con tolleranza relativa `0.05` su lunghezza
  e angolo;
- score finale dato dai voti geometricamente coerenti.

Se meno di cinque descrittori superano il ratio test, oppure se le
corrispondenze non producono almeno cinque relazioni geometriche coerenti, il
matcher restituisce esattamente zero. Cento o più keypoint provano quindi che
la cattura non è vuota; non provano sovrapposizione descrittiva o geometrica
con uno specifico template.

## Riesame dei test offline

Il precedente test integrato cambiava `baseline_b`/`baseline_c` ma manteneva
il frame grezzo costruito sopra `baseline_a`. In quel modello, riusare
`baseline_a` conserva per costruzione lo stesso raster, mentre usare la B0
della nuova sessione lo altera. Il test provava correttamente la meccanica del
pinning, ma non la continuità biometrica reale e non poteva identificare la
root cause osservata live.

Il test è ora nominato
`/goodix/d291/fixed-raw-baseline-pinning-mechanics` e i marker non dichiarano
più la stabilità. È stata aggiunta una regressione host-only al preprocessing
R2 con due sessioni modellate in modo accoppiato:

```text
frame_A = B0_A + rilievo_locale
frame_B = B0_B + lo_stesso_rilievo_locale
```

Con la B0 propria di ciascuna sessione i raster R2 risultano byte-identici. Con
`frame_B` normalizzato dalla vecchia `B0_A`, oltre metà dei pixel cambia nel
fixture deterministico. Questo non è dato biometrico reale e non dimostra che
il pinning abbia causato uno specifico NO_MATCH; dimostra però che la vecchia
fixture aveva incorporato l'assunzione da provare e che una B0 stale può
alterare l'input SIGFM quando B0 e frame cambiano insieme.

Il repository non contiene una coppia riutilizzabile e decodificata di B0 e
frame per le VERIFY in esame. I pcap raw storici non costituiscono una fixture
R2 pronta: il payload applicativo è nel canale TLS e non è disponibile qui
come coppia canonica sanitizzata. Non è quindi possibile riprodurre offline la
variabilità reale delle run o attribuire causalmente gli score zero a
preprocessing, posa/pressione, template coverage o matcher.

```text
SESSION_COUPLED_BASELINE_MODEL_TEST=PASS
REAL_DECODED_B0_FRAME_FIXTURE_AVAILABLE=false
REAL_LIVE_VARIABILITY_OFFLINE_REPRODUCED=false
```

## Verifiche offline del riesame

```text
SIGFM_R2_KAT=PASS
SESSION_COUPLED_BASELINE_MODEL=PASS
SIGFM_PREPROCESS_FORBIDDEN_SYMBOL_AUDIT=PASS
SIGFM_PREPROCESS_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D278_D291_FULL_NORMAL=29/29_PASS
D278_D291_FULL_ASAN_UBSAN=29/29_PASS
D291_REAL_ROCKY_OPENCV_SIGFM=PASS
D291_OPERATOR_KIT_CONTRACT=14/14_PASS
D291_OPERATOR_KIT=HISTORICAL_ONLY_DO_NOT_RERUN
REAL_USB_ACCESS=0
REAL_SENSOR_ACCESS=0
FACTORY_PRESERVING=true
```

L'assenza di una fixture reale impedisce di trasformare questi PASS host-only
in una closure biometrica.

## Boundary successivo

Non viene implementata una nuova correzione production: scegliere fra B0
per-sessione, B0 pinned o un'altra strategia senza una causa riproducibile
sarebbe un cambio speculativo. Non viene preparata né richiesta una nuova live
equivalente. Il passo metodologicamente corretto è prima acquisire o
identificare evidenza già esistente che renda osservabili, per la stessa
VERIFY, almeno l'identità/deriva non biometrica della B0 e metriche del raster
R2/descrittori senza versionare immagini biometriche. Solo dopo una diagnosi
causale si potrà proporre il delta production minimo e un eventuale Human
Gate distinto.

Il precedente kit `d291-01-multi-verify` è stato reso fail-closed: ogni
invocazione termina con exit code 4 prima di build, privilegi, runtime, PAM,
USB o sensore. Il contenuto restante è conservato soltanto per audit.

```text
ROOT_CAUSE_IDENTIFIED=false
CORRECTIVE_PRODUCTION_CHANGE_AUTHORIZED=false
REPEAT_EQUIVALENT_LIVE_ALLOWED=false
OFFLINE_COMPARATIVE_DIAGNOSIS=COMPLETED_WITH_EVIDENCE_GAP
RESIDUAL_BLOCKER=NO_REAL_DECODED_B0_FRAME_VARIABILITY_FIXTURE
```
