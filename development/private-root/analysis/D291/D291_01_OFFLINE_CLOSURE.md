<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D291/01 — closure live Rocky-first della stabilità biometrica

> Il nome storico del file è conservato per evitare frammentazione. La closure
> è stata riesaminata sui risultati sanitizzati prodotti dalla live Utente.

## Decisione

Le evidenze aggregate successive a `6ccacbcd28b06db9a7f3174d3d5c0350f87b164f`
avevano confermato il transport ma non la stabilità biometrica. Il riesame
Rocky-first ha quindi selezionato e implementato la coverage/diversity
dell'enrollment. La candidate
`cbf582f4dcdb7eeb6c8381223c84d37363386870` ha ora superato il gate reale:
re-enrollment completato, dito errato respinto e quattro serie registrate su
quattro concluse con MATCH. Il boundary funzionale D291 è chiuso.

```text
D291_MULTI_VERIFY_TRANSPORT=PROVEN
D291_MAX_TRIES_3_PAM_CONTROL=PROVEN
D291_BASELINE_PINNING=IMPLEMENTED_NOT_VALIDATED
D291_BASELINE_LIFETIME_ROOT_CAUSE=NOT_PROVEN
D291_BIOMETRIC_STABILITY_GATE=PASS
D291_CLOSURE=PROVEN_ON_TARGET
D291_STATUS=CLOSED
ROCKY_DIFFERENTIAL_COMPLETED=true
MATERIAL_ROCKY_DERIVED_PRODUCTION_DELTA_IMPLEMENTED=true
ROOT_CAUSE_EXCLUSIVE_ATTRIBUTION=NOT_REQUIRED_FOR_CLOSURE
OLD_ENROLLMENT_POLICY=SUPERSEDED
NEW_LIVE_REQUIRED_NOW=false
PM_DECISION=ACCEPT_AND_CONTINUE
```

## Differential Rocky-first e scelta production

Sono stati letti e confrontati direttamente:

- `Rockytkg/src/goodixgf.c`;
- `Rockytkg/src/goodix_capture.c`;
- `Rockytkg/src/goodix_imgproc.c`;
- `Rockytkg/include/goodix.h`;
- `Rockytkg/docs/libfprint-integration.md`;
- `Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp`;
- i rami image/enroll del fork libfprint materializzato nello snapshot.

| Ordine | Differenza | Ragione target-specific provata per divergere? | Decisione |
| --- | --- | --- | --- |
| lifecycle VERIFY | Rocky conserva `goodix_dev` nel logical open; APP12509 locale chiude e ricostruisce il grafo fra `VerifyStart` espliciti | sì: transcript e live target-local provano cleanup/reopen e una acquisition per action; il worker Rocky dipende da transport/recovery differenti | `LIFECYCLE_DELTA=NONE` |
| baseline/calibration | Rocky `img_base` è stato di device con gestione deriva e percorso di persistenza; la B0 locale è input di normalizzazione sessione | sì: non è provata equivalenza semantica e non è consentito importare persistenza/reset | `BASELINE_DELTA=NONE` |
| preprocessing | Rocky usa subtraction, low-frequency/flat-field, percentile stretch e unsharp su 80x64 | no divergenza residua: D279/49 ha già adattato direttamente `gx_imgproc_to8bit()` e `GX_IMGPROC_SIGFM_PARAMS` | `PREPROCESSING_DELTA=NONE` |
| enrollment diversity | locale fixed-eight accettava ogni pressione; Rocky separa contatti da sample utili con 3/8/2/MAD<8 | no | `ADAPT_FROM_ROCKY` |
| retry | Rocky usa retry scan per duplicato enrollment ma termina un VERIFY valido NO_MATCH | no | stessa distinzione in production |
| threshold | Rocky 20, locale 40 | il corpus target ha score diversi, ma nessun corpus calibrante sufficiente; abbassare non risolve score zero | conservare 40 |

Questa scelta riusa la parte Rocky che agisce soltanto sul raster host e non
importa provisioning, firmware, PSK, worker USB, reset, comandi persistenti o
override ambientali.

## Implementazione

`libfprint-driver/goodix_enrollment_diversity.[ch]` è l'adattamento minimo di
`gf_enroll_frame_dup()` e della relativa convergenza:

```text
MIN_ACCEPTED_SAMPLES=3
MAX_ACCEPTED_SAMPLES=8
DUPLICATE_STREAK_TO_CONVERGE=2
DUPLICATE_IF_MAD_U8_STRICTLY_LT=8
MAX_PHYSICAL_CONTACTS=20
```

Il limite 20 è l'unica estensione target-local alla policy: rende impossibile
un enrollment illimitato se l'operatore continua a fornire duplicati prima di
raggiungere il minimo. Il selector conserva e poi azzera le copie U8 accettate;
non possiede API USB, TLS, sender o persistenza.

Il modello, la pipeline e il command plan distinguono ora stage fisici
osservati da stage consegnati. Il callback può:

- richiedere un retry esplicito, liberando l'immagine pendente senza avanzare
  il template;
- richiedere convergenza, facendo diventare l'immagine corrente lo stage
  finale e conservando il terminal hold fino al release-ready APP12509.

`goodix_fpimage_device.c` classifica l'esatto raster R2 U8 usato per
l'estrazione SIGFM. Sul duplicato chiama
`fpi_image_device_retry_scan(FP_DEVICE_RETRY_GENERAL)`; su convergenza aggiorna
`nr_enroll_stages` prima di consegnare l'ultimo sample. VERIFY e IDENTIFY non
attraversano il selector. Un loro NO_MATCH valido resta terminale per la
singola action; soltanto PAM può creare il secondo o terzo `VerifyStart`.

La production build aggiunge il nuovo helper al Meson target. Licenza e
provenance sono registrate in `docs/LICENSING_AND_PROVENANCE.md`.

## Compatibilità template

Preprocessing R2, `GSF1`/FP3, struttura SIGFM, matcher e soglia 40 sono
invariati. Il template fixed-eight esistente resta quindi strutturalmente
leggibile e confrontabile. Non è però rappresentativo della nuova policy di
coverage: per validare questo correttivo serve un re-enrollment reale. Questa è
una necessità sperimentale, non una migrazione di formato.

## Evidenza live finale e decisione PM

L'Utente ha eseguito il kit dalla candidate completa `cbf582f4...`. Il
`summary.env` e i cinque audit sanitizzati presenti nella directory risultato
sono internamente coerenti:

```text
D291_01_LIVE_RESULT=PASS_REENROLL_AND_4_MATCHED_SERIES
ENROLL_ACCEPTED_SAMPLE_COUNT=8
ENROLL_PHYSICAL_CONTACT_COUNT=8
ENROLL_RETRY_COUNT=0
SERIES_1=WRONG_FINGER_NO_MATCH_THEN_REGISTERED_MATCH
SERIES_2=REGISTERED_MATCH_FIRST_TRY
SERIES_3=REGISTERED_MATCH_FIRST_TRY
SERIES_4=REGISTERED_MATCH_FIRST_TRY
REGISTERED_FINGER_MATCH_SERIES=4/4
REGISTERED_FINGER_FIRST_TRY_MATCH_SERIES=3/4
PAM_MAX_TRIES=3
STOP_ON_FIRST_MATCH=true
NO_FOURTH_ATTEMPT=true
HIDDEN_VERIFY_RETRY_COUNT=0
TEMPLATE_INCLUDED=false
```

L'enrollment reale ha riportato una sola action, otto stage e otto contatti,
TLS uno, 204 submit reali, zero retry secure/post-TLS, reset, clear-halt e
famiglie persistenti, zero outstanding, drain e context close. L'assenza di
retry scan non rende inattiva la policy: gli otto contatti sono stati giudicati
distinti dal criterio Rocky-derived e il template risultante ha superato il
gate multi-serie.

Il dito errato ha prodotto 111 keypoint e otto score zero. I MATCH registrati
hanno score 7900, 7665, 488 e 91 con soglia invariata a 40. Nel secondo epoch
della prima serie il MATCH termina l'action prima del release-tail, ma l'audit
prova una sola acquisition, zero retry, zero outstanding, drain e chiusura del
contesto: è coerente con lo stop immediato al MATCH.

```text
D291_SECOND_VERIFY_REACHES_SENSOR=PROVEN
D291_THIRD_VERIFY_REACHES_SENSOR=PROVEN
D291_ONE_ACQUISITION_PER_VERIFY_START=PROVEN
D291_STOP_ON_MATCH=PROVEN
D291_NO_HIDDEN_VERIFY_RETRY=PROVEN
D291_NO_FOURTH_VERIFY=PROVEN
D291_ROCKY_DERIVED_ENROLLMENT_DIVERSITY=LIVE_VALIDATED
D291_REENROLLMENT=PASS
D291_WRONG_FINGER_REJECTION=PASS
D291_REGISTERED_SERIES_MATCHED=4/4
D291_BIOMETRIC_STABILITY_GATE=PASS
D291_FACTORY_PRESERVING=PROVEN_FOR_THIS_LIVE
```

Il risultato prova che il percorso diversity Rocky-derived ha prodotto un
template reale stabile secondo il gate D291 e sostituisce la policy
fixed-eight precedente. Non prova che l'assenza di diversity fosse l'unica
causa dei NO_MATCH storici: non esiste un confronto A/B controllato con le
stesse pressioni, e l'operatore ha variato deliberatamente centro, lati e punta.

## Evidenza live aggregata precedente

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
D291_DIVERSITY_UNIT_NORMAL=4/4_PASS
D291_DIVERSITY_UNIT_ASAN_UBSAN=4/4_PASS
D291_DIVERSITY_FORBIDDEN_SENSOR_SYMBOL_AUDIT=PASS
D291_DYNAMIC_PIPELINE_NORMAL_ASAN_UBSAN=PASS
D291_PRODUCTION_SHAPED_DUPLICATE_CONVERGENCE=PASS
D278_D291_FULL_NORMAL=30/30_PASS
D278_D291_FULL_ASAN_UBSAN=30/30_PASS
FPIMAGE_DEVICE_FULL_NORMAL=32/32_PASS
FPIMAGE_DEVICE_FULL_ASAN_UBSAN=32/32_PASS
D291_OPERATOR_KIT_CONTRACT=14/14_PASS
D291_OPERATOR_KIT=HISTORICAL_CLOSED_DO_NOT_RERUN
FULL_RELEVANT_OFFLINE_REGRESSION=PASS
PRODUCTION_BUILD=PASS
ABI_PREFLIGHT=PASS
REAL_USB_ACCESS=0
REAL_SENSOR_ACCESS=0
FACTORY_PRESERVING=true
```

I test host-only provano la decisione strict-MAD, i limiti, il retry senza
avanzamento, la convergenza dinamica, l'ownership e il terminal hold. Non
provano che la nuova copertura migliori la stabilità su un dito reale.
Il preflight finale è stato eseguito con
`operator_kit/d282-01-fprintd-target/run-d282-01.sh --offline-preflight`
e directory RPM OpenCV assoluta: build Meson/ninja della libfprint production,
assenza di test seam/RPATH e ABI richiesta dall'esatto fprintd Fedora 44 sono
PASS. Il processo ha riportato `REAL_SENSOR_ACCESSED=false` e
`LIVE_EXECUTION_PERFORMED=false`.

## Stato runtime e boundary successivo

Il ramo success del kit non invoca `rollback`: lascia installati runtime e
template nuovi, aggiorna nello state D285 manifest, path e hash del template,
elimina il backup root-only e disarma le trap. Questo comportamento è confermato
sia dal sorgente riesaminato sia dal marker PASS prodotto. Il kit è ora
`HISTORICAL_CLOSED_DO_NOT_RERUN` e conserva il contenuto soltanto per audit.

Il prossimo boundary è Phase A della roadmap: consolidare una sola
source-of-truth production e una build/patch series mantenibile, separando
codice distribuibile, reference tree e seam di test. Non richiede una nuova
live D291.

```text
ROOT_CAUSE_EXCLUSIVE_ATTRIBUTION=NOT_REQUIRED_FOR_CLOSURE
ROCKY_DERIVED_DIVERSITY_PATH=LIVE_PROVEN_EFFECTIVE
OLD_ENROLLMENT_POLICY=SUPERSEDED
D291_REPEAT_LIVE_REQUIRED=false
D291_REENROLL_REQUIRED=false
NEXT_BOUNDARY=PHASE_A_PRODUCTION_SOURCE_CONSOLIDATION
```
