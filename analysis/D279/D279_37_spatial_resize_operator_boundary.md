# D279/37 — resize spaziale pinned e operator boundary

## Obiettivo e ipotesi

D279/37 isola la più piccola ipotesi ancora discriminante dopo l'aggregate
autentico D279/35: il raster nativo 80×64 può essere troppo piccolo perché
NBIS estragga minutiae utilizzabili, mentre un resize spaziale fattore 2 o 3
può cambiare materialmente l'esito.

La matrice è intenzionalmente limitata a nove varianti: i tre mapping di
intensità D279/34, orientamento `identity`, polarità `normal` e fattori spaziali
1/2/3. Il fattore 1 bypassa l'interpolazione e riproduce i tre controlli
D279/35 corrispondenti. I fattori 2 e 3 usano direttamente
`fpi_image_resize()` del tree Fedora 44/libfprint 1.94.100 pinned, cioè pixman
bilineare; non esiste una reimplementazione Python del resize.

## Implementazione offline

Il nuovo helper C accetta esclusivamente frame 8-bit nativi via stdin e un
fattore 1..3. Per i fattori 2/3 costruisce un `FpImage`, invoca il resize pinned
e passa il buffer risultante allo stesso `get_minutiae()` D279/34 con
`g_lfsparms_V2`, `ppmm=0` e `remove_perimeter_pts=false`. I buffer immagine C e
Python owned vengono azzerati prima del rilascio.

Il target Meson è test-only e `install: false`. Il build abilita pixman
includendo AES3500 esclusivamente nella configurazione offline: il helper non
collega i driver e la scansione statica respinge entry point USB/production.
Nessun file del driver Goodix production è stato modificato.

Un primo build con il solo driver Goodix ha prodotto correttamente
`Libfprint compiled without pixman support` e il helper ha fallito chiuso. È
evidenza che l'eventuale futura adozione production richiederebbe un'esplicita
dipendenza Meson da pixman; la disponibilità di `fpi_image_resize()` nel tree
non basta. Il corrective offline attiva il feature switch esistente tramite
AES3500 e pinna runtime e header pixman 0.46.4 dalla stessa SDK Flatpak 25.08.

## Aggregate e privacy

`d279_37_spatial_resize_evaluator.py` conserva soltanto frame count, presenza,
soglia 10, minimo, mediana e massimo per baseline/primario/ausiliario. Non
esporta conteggi per-frame, raster o template. Il runner protetto riusa il
reader `openat`/`O_NOFOLLOW` e il writer esclusivo D279/35 già revisionati, ma
usa una nuova operation e un nuovo namespace grant:

```text
D279_37_ONE_OFFLINE_PROTECTED_SPATIAL_RESIZE_EVALUATION
```

Il grant D279/35 consumato non è accettato. La nuova run consumerà il proprio
marker prima di leggere il transport e non autorizza retry.

## Verifiche

```text
D279_31_THROUGH_D279_37_PYTHON_TESTS=26/26_PASS
D279_37_EXACT_TARGET_LIBFPRINT=1.94.100
D279_37_PINNED_PIXMAN=0.46.4
D279_37_FACTOR_1_CONTROL=D279_34_EXACT_NBIS_PATH
D279_37_NORMAL_AND_ASAN_UBSAN=PASS
D279_37_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
TARGET_PSK_ACCESSED=false
REAL_RASTER_EVALUATED_COUNT=0
LIVE_OR_USB_ACTION_COUNT=0
```

Il preflight ha verificato pipe Python→C, fattori 1/2/3 su frame sintetici,
simboli `fpi_image_resize`/NBIS materialmente definiti nel helper, caricamento
del pixman pin-nato e cleanup della directory effimera. Non è stata eseguita
`--prepare-approved-analysis`, perché richiede HEAD e origin sul futuro full
SHA approvato.

## Review live-critical

- l'unico collegamento Meson nuovo è un executable test non installato;
- helper, evaluator e operator runner non espongono enumerazione, open, claim,
  submit o contesti USB;
- nessuna seam/iniezione host-only aggiunta è raggiungibile dal percorso USB
  production;
- la produzione Goodix corrente non abilita pixman e non usa il resize;
- i timeout di chiusura pipe sono esclusivamente safety bound del processo
  host offline: non esiste path device e non implicano quiescenza o timeout
  sensor-side;
- sender e allowlist delle famiglie persistenti non sono modificati; la loro
  assenza resta un guardrail e non prova assenza di altra persistenza.

## Criterio di lettura della futura evidenza

Un aumento di frame primari con almeno 10 minutiae o un aumento ampio e
selettivo del massimo primario rispetto al controllo e alla baseline
supporterebbe la scala spaziale come causa. Un aumento simile anche sulla
baseline indicherebbe invece artefatti di interpolazione. Se fattori 2 e 3 non
producono un segnale discriminante, non verrà preparato un retry equivalente:
il passo successivo sarà riesaminare la relazione primary/aux e l'accumulo
multi-frame, che richiedono un metodo diverso.

## Human Gate

La closure offline è completa, ma nessuna valutazione autentica D279/37 è
autorizzata. Dopo commit e pubblicazione approvata, il gate deve nominare il
full SHA esatto e autorizzare una sola:

```text
D279_37_ONE_OFFLINE_PROTECTED_SPATIAL_RESIZE_EVALUATION
```

Il perimetro comprende una lettura in-memory della PSK dal transport protetto
e una valutazione aggregate-only dei 43 raster ATTEMPT02 già acquisiti. Esclude
USB/live, sensore, fprintd, retry, seconda lettura, modifica/copia del
transport e persistenza di raster/template.

## Closure

```text
OUTCOME=READY_FOR_HUMAN_GATE_ONE_OFFLINE_PROTECTED_SPATIAL_RESIZE_EVALUATION
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_AND_OPERATOR_BOUNDARY_REACHED
EXECUTABLE_CLOSURE=PASS_OFFLINE_ONLY
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
D279_35_AUTHORIZATION_CONSUMED=true
TARGET_PSK_ACCESSED_BY_AI=false
REAL_RASTER_EVALUATED_COUNT=0
LIVE_OR_USB_ACTION_COUNT_BY_AI=0
RETRY_AUTOMATICO=false
RESIDUAL_BLOCKER_OR_RISK=EXPLICIT_FULL_SHA_HUMAN_APPROVAL_AND_REMOTE_PUBLICATION_AUTHORITY_REQUIRED
CANONICAL_DOCUMENTATION=GOODIX_MANUAL_D279_37
REVIEW_SET=GIT_NATIVE
```
