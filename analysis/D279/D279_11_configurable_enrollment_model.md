<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/11 — modello enrollment parametrico host-only

## Esito

Il primo delta successivo all'analisi ATTEMPT02 introduce
`goodix_enrollment_model.[ch]`: un oracle C LGPL metadata-only, privo di
backend USB/TLS e di qualunque sender. Il modello riproduce esattamente le tre
forme osservate — prima transizione con NAV, transizioni intermedie ripetute e
transizione terminale senza re-arm — senza modificare il lifecycle D275 né i
vfunc production, dove l'enrollment resta respinto prima di ogni submit.
`goodix_enrollment_pipeline.[ch]` lo compone poi con la pipeline canonica per
costruire e consegnare un `FpImage` soltanto per ciascun B0 primario. La
fixture `FpImageDevice` completa applica inoltre al solo target 27c6:5125 la
policy osservata di 21 stage e chiude un problema reale di ordering terminale,
senza promuovere 21 a costante OEM universale.
`goodix_enrollment_command_plan.[ch]` aggiunge infine un piano host-only non
serializzabile: compone lo stesso oracle e la pipeline immagine, ma restituisce
soltanto intenti tipizzati per i sei controlli osservati.
`goodix_enrollment_command_body.[ch]` materializza separatamente il solo body
logico, con binding fail-closed a stage e ruolo FDT; non costruisce frame A0.

```text
OUTCOME=READY_OFFLINE_MODEL
ADVANCEMENT=MATERIAL_ARCHITECTURAL_ADVANCEMENT
ATTEMPT02_OBSERVED_SUCCESSFUL_STAGE_COUNT=21
OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
MODEL_REQUIRED_STAGE_COUNT=EXPLICIT_PARAMETER_MINIMUM_2
PROFILES_TESTED=2,3,21
PRODUCTION_ENROLLMENT_ENABLED=false
SENSOR_REACHING_CODE_CHANGED=false
PRIMARY_FPIMAGE_DELIVERY_PROFILES=2,3,21
AUXILIARY_B0_FPIMAGE_DELIVERY_COUNT=0
TARGET_LOCAL_FPIMAGEDEVICE_STAGE_POLICY=21
PRODUCTION_EXTRACTION_ALGORITHM=NBIS
FULL_FPIMAGEDEVICE_FIXTURE_EXTRACTION=SIGFM_TEST_DOUBLE
COMMAND_PLAN_21_STAGE_CONTROL_COUNTS=20x21,22x21,32x21,34x41,36x20,50x1
COMMAND_PLAN_SERIALIZED_COMMAND_COUNT=0
COMMAND_PLAN_REAL_SUBMIT_COUNT=0
COMMAND_BODY_A0_FRAME_BUILD_COUNT=0
COMMAND_BODY_REAL_SUBMIT_COUNT=0
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Contratto

Il callback di avanzamento viene emesso soltanto dopo la sequenza primaria
`IRQ2 → 0x22 → ACK → primary B0`. Ogni stage deve poi chiudere la propria
transizione prima che il modello accetti il successivo IRQ2. Nel profilo
ATTEMPT02:

1. lo stage 1 usa `0x34/IRQ0200 → 0x20/B0 → 0x32 → 0x50/NAV → 0x32`;
2. gli stage intermedi usano
   `0x34 → 0x36/IRQ0100 → 0x20/B0 → 0x34/IRQ0200 → 0x32`;
3. lo stage configurato come ultimo usa la stessa forma ripetuta, ma termina a
   IRQ0200 senza re-arm.

Un evento fuori ordine rende terminale l'istanza e non introduce retry. Il
minimo di due stage non è una legge OEM: è il limite del solo profilo modellato,
che necessita sia della forma iniziale sia di quella terminale osservata. Il
conteggio richiesto resta sempre un input esplicito; il modulo non contiene un
default nascosto pari a 21.

Per `FpImageDevice`, consegnare il ventunesimo `FpImage` già al B0 primario
può far terminare l'estrazione asincrona mentre il framework è ancora in
`AWAIT_FINGER_OFF`. Il modello conserva quindi separatamente stage primari
osservati e stage consegnati e, quando il flag esplicito
`defer_terminal_stage_delivery` è attivo, trattiene soltanto l'immagine finale
fino all'IRQ0200 terminale. Il caller può così notificare finger-up prima di
avviare l'ultima estrazione. La provenienza del raster resta il B0 primario;
l'IRQ non trasporta né crea immagine.

Il command-plan classifica `0x22` come acquisizione primaria, `0x20` come
transizione ausiliaria, le due posizioni di `0x34` come preparazione FDT e
finger-up, `0x36` come scan FDT ausiliario, i due ruoli iniziali/inter-stage di
`0x32` e il solo NAV `0x50`. Espone inoltre la classe strutturale del body
(`01 00`, prefisso FDT `0a 01`/`09 01`, oppure FDT+timestamp `08 01`) ma non
possiede body bytes, builder A0, backend o API di submit. Per 21 stage il piano
conta 125 intenti: è la sola porzione enrollment e non include i comandi
bootstrap/re-entry presenti nei conteggi globali ATTEMPT02.

Il contratto body richiede materiale esplicito per lo stesso `stage_index` e
per uno dei ruoli `STAGE_UP`, `STAGE_AUX_SCAN` o `TRANSITION_DOWN`. I semplici
`0x20/0x22/0x50` rifiutano materiale; `0x34` accetta soltanto `STAGE_UP`,
`0x36` soltanto `STAGE_AUX_SCAN`, `0x32` soltanto `TRANSITION_DOWN` con
timestamp dichiarato. Produce esclusivamente 2, 14 o 16 byte interni e offre
clear esplicito; stage stale, ruolo errato, timestamp mancante o intento
marcato wire-serializzabile falliscono prima di produrre output.

Il B0 cifrato successivo a `0x20` è contato e consumato come transizione
protocol-internal, ma non genera callback stage. Questa classificazione non
stabilisce che il suo contenuto sia inutile: eventuali ruoli in quality,
template o NBIS rimangono non determinabili dalla capture cifrata.

## Verifica ed executable closure

`tests/run_goodix_d279_11_enrollment_model_test.sh` compila il modulo con
warning strict e lo esegue normal e ASan/UBSan nell'SDK Freedesktop già
qualificato, senza rete. I sei casi coprono profili 2/3/21, separazione del B0
ausiliario, mismatch fail-closed con diagnostica expected/actual, rifiuto del
callback con e senza `GError`, stabilità dell'audit dopo completion e rifiuto
di una configurazione che inventerebbe una forma single-stage non osservata.
L'audit sorgente e simboli esclude dipendenze USB, TLS, core GPL e sender.
Cinque casi ulteriori costruiscono e consegnano 2/3/21 sequenze di veri
`FpImage`, rifiutano un raster associato al B0 ausiliario, propagano il failure
del consumer, provano che un primary fuori ordine non alloca alcuna immagine e
rilasciano subito l'immagine terminale pending su mismatch.
La build production-shaped Fedora 44 compila entrambi i moduli contro
libfprint 1.94.100 con NBIS e mantiene registry e zero-enumeration verdi.
La fixture framework attraversa inoltre una vera operazione asincrona
`FpImageDevice` per tutti i 21 stage e verifica 21 progress callback, un solo
completion e la chiusura terminale dopo finger-up. Usa però il double SIGFM
storico del test harness, non NBIS: prova la state machine e l'ordering, non la
qualità biometrica né l'esito dell'estrazione production. La suite completa ha
anche trovato e corretto un contatore stale nel controllo concorrente del
double; dopo il corrective passano tutti i 25 casi sia normali sia sanitizer.

```text
D279_11_TESTS=6/6_PASS_NORMAL;6/6_PASS_ASAN_UBSAN
D279_11_FPIMAGE_TESTS=5/5_PASS_NORMAL;5/5_PASS_ASAN_UBSAN
CONFIGURABLE_STAGE_PROFILES=PASS_2_3_21
PRIMARY_B0_LIBFPRINT_STAGE_ACCOUNTING=PASS
AUXILIARY_B0_STAGE_ACCOUNTING=ZERO
UNEXPECTED_EVENT_FAIL_CLOSED=PASS
EXECUTABLE_CLOSURE=PASS_HOST_ONLY_ZERO_SENDER
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FPIMAGEDEVICE_TESTS=25/25_PASS_NORMAL;25/25_PASS_ASAN_UBSAN
FPIMAGEDEVICE_21_STAGE_PROGRESS_AND_COMPLETION=PASS_SIGFM_TEST_DOUBLE
TERMINAL_STAGE_DELIVERY_AFTER_IRQ0200=PASS
NBIS_21_STAGE_BIOMETRIC_ENROLLMENT=NOT_TESTED
COMMAND_PLAN_TESTS=2/2_PASS_NORMAL;2/2_PASS_ASAN_UBSAN
COMMAND_PLAN_21_STAGE_TOTAL_INTENTS=125
COMMAND_PLAN_BODY_SERIALIZATION=ABSENT
COMMAND_BODY_TESTS=2/2_PASS_NORMAL;2/2_PASS_ASAN_UBSAN
COMMAND_BODY_ALL_EIGHT_PURPOSES=PASS
COMMAND_BODY_STAGE_ROLE_BINDING=FAIL_CLOSED
COMMAND_BODY_A0_SERIALIZATION=ABSENT
REAL_TARGET_COMPATIBILITY=PASS_BUILD_API_ABI_ONLY
```

## Confine residuo

Il modello non decodifica payload e non genera comandi. La configurazione
generica resta parametrica; il `FpImageDevice` del target seleziona 21 come
policy target-local derivata dalla sola ATTEMPT02. La fixture attraversa ora
la state machine completa, ma non prova l'estrazione NBIS sui raster reali e
il lifecycle production sensor-reaching resta ancora bounded al secondo B0.
Il command-plan chiude topologia e conteggi e il body layer chiude forma,
ownership e binding stage/ruolo. Resta intenzionalmente irrisolta la
derivazione dinamica delle tre tabelle dai rispettivi IRQ per ogni ciclo; il
successivo passo offline minimo è modellare quella derivazione e l'adapter
lifecycle iterativo, ancora senza collegarlo al backend e senza abilitare il
vfunc.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_DYNAMIC_FDT_DERIVATION_AND_ITERATIVE_LIFECYCLE_ADAPTER_WITH_PRODUCTION_GATE_RETAINED
```
