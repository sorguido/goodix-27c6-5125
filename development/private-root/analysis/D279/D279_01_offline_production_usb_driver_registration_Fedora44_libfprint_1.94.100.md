<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/01 — registrazione USB production Fedora 44/libfprint 1.94.100

## Esito

```text
D279_01_OUTCOME=BLOCKED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=NOT_REACHED_BLOCKED_BEFORE_IMPLEMENTATION
RESIDUAL_BLOCKER_OR_RISK=FEDORA_44_LIBFPRINT_1_94_100_HAS_ONLY_NBIS_IMAGE_EXTRACTION_WHILE_THE_CANONICAL_GOODIX_CLASS_SELECTS_SIGFM_AND_TARGET_PPMM_IS_UNKNOWN
CANONICAL_DOCUMENTATION=UPDATED_UNCOMMITTED_FOR_HUMAN_REVIEW
```

D279/01 si arresta prima dell'implementazione. Il target production esatto
non espone il contratto SIGFM richiesto dalla classe Goodix corrente. Eliminare
la selezione SIGFM cambierebbe la pipeline in NBIS; importare/portare SIGFM nel
core 1.94.100 allargherebbe materialmente lo scope e modificherebbe più
componenti libfprint. Entrambe le alternative sono vietate dal prompt.

## Baseline

```text
branch=main
D279_01_BASELINE=f609c865f760768edb6a9e404b863ccd0569e1c8
origin/main=f609c865f760768edb6a9e404b863ccd0569e1c8
initial_worktree=CLEAN
final_SHA=NOT_CREATED_BLOCKED
WORKING_BRANCH=main
USE_DEVELOPMENT=false
SEPARATE_TASK_BRANCH_CREATED=false
ORCHESTRATION_ENABLED=false
```

È stato eseguito `git fetch --prune origin`; `main`, `origin/main` e la baseline
attesa coincidevano, senza ahead/behind.

## Base libfprint target

```text
TARGET_OS=Fedora_44_x86_64
TARGET_LIBFPRINT_VERSION=1.94.100
TARGET_LIBFPRINT_PACKAGE=libfprint-1.94.100-1.fc44.x86_64
TARGET_LIBFPRINT_RUNTIME_SONAME=libfprint-2.so.2
TARGET_FPRINTD_PACKAGE=fprintd-1.94.5-5.fc44.x86_64
TARGET_LIBFPRINT_REFERENCE=reference/libfprint-fedora44-1.94.100/source
ROCKYTKG_LIBFPRINT_VERSION=1.94.5
ROCKYTKG_LIBFPRINT_IS_PRODUCTION_TARGET=false
```

`reference/libfprint-fedora44-1.94.100/PROVENANCE.md` e la spec Fedora sono
stati letti integralmente. La reference è l'upstream v1.94.100 estratto dallo
SRPM Fedora, senza patch Fedora attive. Rockytkg 1.94.5 è stato usato soltanto
per identificare la provenienza storica dell'estensione SIGFM, non come target
production e non come fonte di implementazione D279.

## Blocker verificato

La classe Goodix esistente conserva esplicitamente la policy selezionata:

```c
img_class->algorithm = FPI_DEVICE_ALGO_SIGFM;
```

Il target Fedora 44/libfprint 1.94.100 verificato localmente ha invece questo
contratto:

- `FpImageDeviceClass` contiene `bz3_threshold`, geometria e callback, ma non
  contiene un campo `algorithm`;
- `FpiPrintType` contiene soltanto `UNDEFINED`, `RAW` e `NBIS`;
- non esistono `FPI_DEVICE_ALGO_SIGFM`, `FPI_PRINT_SIGFM` o sorgenti SIGFM;
- `fpi_image_device_image_captured()` invoca sempre
  `fp_image_detect_minutiae()`, crea un print `FPI_PRINT_NBIS` e usa
  `fpi_print_bz3_match()`.

Quindi l'attuale sorgente Goodix non può compilare invariato contro l'API
1.94.100, e la semplice rimozione della riga SIGFM non è una correzione
meccanica: selezionerebbe NBIS. Il contratto canonico D269–D271/D276 lascia
`TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN` e blocca NBIS perché il suo percorso di
quality/minutiae usa `FpImage::ppmm`. Inventare un valore ppmm è espressamente
vietato.

Portare SIGFM dal fork storico richiederebbe almeno nuovi tipi print, extraction
asincrona, matching, ownership, serializzazione/deserializzazione, dipendenza
OpenCV/C++ e integrazione Meson nel core 1.94.100. Non sarebbe più la minima
registrazione USB D279/01, e il prompt vieta espressamente architectural
widening, duplicazione o porting sostanziale per forzare il build.

```text
TARGET_1_94_100_FPIMAGE_ALGORITHM_SELECTOR=ABSENT_VERIFIED
TARGET_1_94_100_SIGFM_PRINT_TYPE=ABSENT_VERIFIED
TARGET_1_94_100_SIGFM_EXTRACTION=ABSENT_VERIFIED
TARGET_1_94_100_SIGFM_MATCHING=ABSENT_VERIFIED
TARGET_1_94_100_IMAGE_PATH=NBIS_ONLY_VERIFIED
CURRENT_GOODIX_ALGORITHM=SIGFM
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
NBIS_WITH_UNKNOWN_PPMM=BLOCKED_CANONICAL
MINIMAL_REGISTRATION_WITH_ALGORITHM_PRESERVED=PRESENTLY_UNSATISFIABLE
```

## Implementazione e file

Nessun file di codice, registry, Meson o reference source è stato modificato.
Non sono stati aggiunti `FpIdEntry`, GType production o registrar parziali:
lasciare una registrazione incompleta avrebbe fatto apparire il dispositivo
supportato pur cambiando implicitamente extractor o fallendo il build.

File documentali D279/01 lasciati non committati per review umana, come
richiesto dalla clausola `BLOCKED`:

- `analysis/D279/D279_01_offline_production_usb_driver_registration_Fedora44_libfprint_1.94.100.md` — evidenza e classificazione del blocker;
- `Goodix 27c6 5125 manuale tecnico.md` — stato canonico e prossimo boundary.

## Verifiche e non-run

| Verifica | Classificazione | Esito |
| --- | --- | --- |
| `git fetch --prune origin` e confronto SHA/ahead-behind | PASS | baseline esatta, branch `main`, worktree iniziale pulito |
| lettura integrale governance, prompt, manuale, provenance Fedora e spec | PASS | prerequisiti completati |
| audit D276/D277/D278 e grafo corrente | PASS | classe corrente riusa un solo `GoodixDeviceContext`; SIGFM selezionato |
| audit statico API/call-flow 1.94.100 | FAIL_BLOCKER | API/core image target NBIS-only; selettore e tipi SIGFM assenti |
| build Meson production-shaped 1.94.100 con Goodix | NOT_RUN_EARLY_ARCHITECTURAL_BLOCKER | nessuna implementazione conforme da inserire nel registry |
| regressioni Goodix/SIGFM/sanitizer | NOT_RUN_EARLY_ARCHITECTURAL_BLOCKER | nessun runtime modificato; il prompt impone stop senza ampliare lo scope |
| test hardware/libfprint discovery/fprintd | NOT_RUN_SAFETY_BOUNDARY | vietati da D279/01 |

Il blocker non è una limitazione del solo ambiente di build: deriva dai
sorgenti target committati. L'assenza locale di Meson/devel package non viene
usata come causa della decisione; il Freedesktop SDK 25.08 resta disponibile,
ma non esiste una patch D279 conforme da costruire.

## Safety e invarianti

```text
REAL_USB_ACCESS=0
REAL_USB_OPEN=0
REAL_USB_CLAIM=0
REAL_USB_SUBMIT=0
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
PERSISTENT_DEVICE_WRITE_COUNT=0
FACTORY_STATE_MUTATION=0
WIRE_PROTOCOL_SEMANTICS_CHANGED=false
NO_SUDO_OR_ROOT_USED=true
TARGET_PROTECTED_MATERIAL_ACCESSED=false
FPRINTD_PROVEN=false
PRODUCTION_LIBFPRINT_TARGET_LIVE_PROVEN=false
D278_14_RERUN_REQUIRED=false
D278_14_RERUN_AUTHORIZED=false

SAME_PROVEN_GOODIX_DEVICE_CONTEXT_REUSED=NOT_IMPLEMENTED_BLOCKED
SECOND_USB_BACKEND_CREATED=false
SECOND_USB_ROUTER_CREATED=false
SECOND_SECURE_SESSION_CREATED=false
SECOND_TLS_STACK_CREATED=false
SECOND_POST_TLS_LIFECYCLE_CREATED=false
CUSTOM_PARALLEL_DRIVER_REGISTRY_CREATED=false
PRODUCTION_USB_ID_27C6_5125_REGISTERED=false
LIBFPRINT_1_94_100_PRODUCTION_SHAPED_BUILD=NOT_REACHED_BLOCKED
```

## Prossimo boundary non autorizzato

Serve una decisione architetturale separata, offline e target-1.94.100-specifica
che scelga fra un'integrazione SIGFM mantenibile nel core Fedora 44 e un
extractor production diverso supportato da evidenza target (incluso ppmm dove
necessario). Questa decisione non è presa né pre-autorizzata da D279/01. Solo
dopo la sua chiusura sarà possibile riprendere registrazione USB e Meson senza
cambiare silenziosamente la policy biometrica.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_FEDORA44_LIBFPRINT_1_94_100_EXTRACTOR_COMPATIBILITY_DECISION
```

```text
D279_01_OUTCOME=BLOCKED
```
