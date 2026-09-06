# D279/35 — operator kit per analisi offline protetta one-shot

## Obiettivo

Portare il progetto al Human Gate per una sola analisi autentica dei frame OEM
ATTEMPT02, senza nuova acquisizione e senza anticipare la lettura della PSK
protetta. Il kit deve congelare sorgenti, capture e NBIS su uno SHA completo e
persistire esclusivamente metriche aggregate.

## Contratto del kit

`operator_kit/d279-35-offline-protected-evaluation/` offre quattro fasi:

1. `--offline-preflight`, eseguibile senza gate e solo da utente non-root;
2. `--prepare-approved-analysis <SHA>`, da snapshot `git archive` del full SHA;
3. `--write-grant <SHA> <file>`, grant deterministico single-use;
4. `--run-approved-analysis ...`, avvio manuale con `sudo` dopo Human Gate.

Le prime due fasi non leggono `/var/lib/goodix-5125-poc`. La run consuma
atomicamente il grant prima di qualunque metadata/accesso al transport
protetto, poi usa `openat`/`O_NOFOLLOW` e verifica directory `0:0/0700`, file
`0:0/0600`, lunghezza 88, hash production e stabilità del descriptor.

La PSK di 32 byte resta caller-owned, viene azzerata in `finally` e alimenta il
composer D279/33. I 43 raster vivono soltanto nel processo e vengono passati
all'evaluator D279/34; l'unico file di successo è un JSON aggregate-only. Non
esistono codice USB, fprintd, enrollment, sender o path immagine.

La preparazione pinna tramite hash helper, libfprint, libgusb, capture, runner e
tutte le dipendenze Python che interpretano/decrittano/decodificano i dati. Le
directory grant, marker e risultato richiedono owner/mode esatti e rifiutano
symlink; output e collisioni sono fail-closed.

## Verifica offline

Il preflight completo ha prodotto:

```text
PYTHON_TESTS_D279_31_THROUGH_D279_35=19/19_PASS
D279_34_EXACT_TARGET_LIBFPRINT=1.94.100
D279_34_NORMAL_AND_ASAN_UBSAN=PASS
D279_35_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
TARGET_PSK_ACCESSED=false
REAL_RASTER_EVALUATED_COUNT=0
LIVE_OR_USB_ACTION_COUNT=0
```

Sono inoltre verdi sintassi shell/Python e `git diff --check`. Il path
autentico non è stato eseguito, perché leggerebbe protected material e richiede
autorizzazione separata.

## Closure

```text
OUTCOME=READY_FOR_HUMAN_GATE_ONE_OFFLINE_PROTECTED_EVALUATION
ADVANCEMENT=MATERIAL_OPERATOR_BOUNDARY_REACHED
EXECUTABLE_CLOSURE=PASS_OFFLINE_ONLY
PROTECTED_TRANSPORT_PATH=/var/lib/goodix-5125-poc/transport-material.bin
AUTHORIZED_PROTECTED_READ_COUNT=0
TARGET_PSK_ACCESSED=false
REAL_RASTER_EVALUATED_COUNT=0
RASTER_OR_TEMPLATE_EXPORT_PRESENT=false
LIVE_OR_USB_ACTION_COUNT=0
RETRY_AUTOMATICO=false
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
RESIDUAL_BLOCKER_OR_RISK=EXPLICIT_FULL_SHA_HUMAN_APPROVAL_REQUIRED
CANONICAL_DOCUMENTATION=GOODIX_MANUAL_D279_35
REVIEW_SET=GIT_NATIVE
```

## Human Gate

Dopo commit, push e review PM, il gate dovrà indicare il full SHA esatto e
autorizzare precisamente:

```text
D279_35_ONE_OFFLINE_PROTECTED_EVALUATION
```

L'autorizzazione non comprenderà USB, live, retry, seconda valutazione,
modifica/copia del transport, persistenza di raster/template o qualunque
operazione sul sensore.
