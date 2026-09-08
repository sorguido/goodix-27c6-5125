<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/52 — Fedora 44 SIGFM image action and production Meson binding

## Closure

```text
OUTCOME=READY
ADVANCEMENT=REAL_SIGFM_FPIMAGE_ACTION_AND_PRODUCTION_MESON_BOUNDARY_CLOSED_OFFLINE
EXECUTABLE_CLOSURE=PASS_HOST_ONLY_REAL_SIGFM_21_STAGE_ACTION
PRODUCTION_MESON_SIGFM_ENABLED=true
STANDARD_DRIVER_REGISTRY=PASS_EXACT_27C6_5125
ENROLL_STAGE_ADVANCES_ONLY_AFTER_APPEND=true
SIGFM_APPEND_FAILURE_ATOMIC=true
PRODUCTION_IDENTIFY_ACTION_ENABLED=false
FPRINTD_STORAGE_INTEROP_VALIDATED=false
TARGET_BIOMETRIC_VALIDATION=false
USB_OR_LIVE_ACTION_COUNT=0
SECRET_OR_CAPTURE_ACCESS_COUNT=0
SYSTEM_PACKAGE_INSTALL_COUNT=0
```

## Implementazione

Il fork Fedora 44/libfprint 1.94.100 conserva la state machine corrente e
aggiunge il selector privato NBIS/SIGFM derivato semanticamente dal fork
Rockytkg preservato. Per il driver `goodix_27c6_5125`, la vera action
`FpImageDevice` seleziona SIGFM, esegue extraction asincrona dal raster R2 e
costruisce `FpPrint` SIGFM. Il dispatch identify usa il matcher SIGFM quando il
tipo selezionato è SIGFM; la production allowlist Goodix resta però enrollment
only in questo boundary.

Il bootstrap post-TLS non tratta più la B0 FDT come plaintext opaco: la
reassembla secondo il contratto canonico, la decodifica in 80x64 u16 e mantiene
il risultato come baseline della sessione. Ogni B0 primaria consegna il raster
u16 originale al seam enrollment, che applica l'esatta trasformazione R2
D279/49 prima di creare l'immagine libfprint. Baseline, source raster e sample
SIGFM sono posseduti e cancellati nei rispettivi teardown.

Il grafo Meson Goodix compila il preprocessore R2 GPL, il wrapper SIGFM
D279/50, l'autentico `Rockytkg/.../sigfm.cpp` e OpenCV4, con C++17. Il combined
build risultante è GPL-compatible; le licenze e i fatti storici dei file
upstream restano invariati e distinti.

## Corrective: append atomico e avanzamento stage

La API upstream `fpi_print_add_print()` restituisce `void`, mentre
`goodix_sigfm_sample_copy()` può fallire. D279/52 introduce
`fpi_print_add_print_checked()` e mantiene la vecchia funzione soltanto come
wrapper compatibile. La variante checked valida tipo e cardinalità, copia il
sample, e muta il template solo dopo il successo.

La vera action usa un helper che incrementa `enroll_stage` esclusivamente dopo
l'append riuscito. Un errore di copy lascia il template invariato, non emette
progress, completa l'action con errore e avvia la disattivazione. Il test double
inietta un'eccezione nel copy e verifica esattamente destination length 0 e
stage 3 invariato.

## Verifiche offline

Suite core con test double, normale e ASan/UBSan:

```sh
./libfprint-driver/tests/run_goodix_fedora44_sigfm_print_test.sh
```

Copertura: multi-sample/round-trip, payload corrotto, bounds, append failure
atomico e stage invariato. Tutti i cinque test passano.

Build production e SIGFM reale con gli RPM Fedora 44 OpenCV 4.13 già
hash-pinned:

```sh
./libfprint-driver/tests/run_goodix_fedora44_sigfm_print_real_test.sh \
  /tmp/goodix-d27950-opencv/rpms
```

Marker finali:

```text
D279_52_PRODUCTION_MESON_SIGFM_SOURCE_CLOSURE=PASS
D279_51_REAL_SIGFM_KEYPOINTS=220
D279_51_REAL_SIGFM_FP3_MATCH_ROUNDTRIP=PASS
D279_52_PRODUCTION_MESON_SIGFM_ENABLED=true
D279_52_IMAGE_ACTION_SIGFM_COMPILED=true
REAL_USB_ACCESS_COUNT=0
LIVE_EXECUTION_PERFORMED=false
```

Azione reale `FpImageDevice`, preprocessing R2, 21 stage e registry:

```sh
./libfprint-driver/tests/run_goodix_fedora44_nbis_action_test.sh \
  /tmp/goodix-d27950-opencv/rpms
```

Il nome NBIS del runner è mantenuto soltanto per compatibilità storica. Il test
usa un raster strutturato deterministico non biometrico e attraversa il vero
extractor Rockytkg/OpenCV. Marker finali:

```text
D279_52_FEDORA44_NATIVE_SIGFM_ACTION=PASS
D279_52_SIGFM_PROGRESS_COUNT=21
D279_52_R2_PREPROCESSING_IN_ACTION=true
D279_52_STANDARD_DRIVER_REGISTRY=PASS
D279_52_NATIVE_SIGFM_ACTION_21_STAGE=PASS
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_SUBMIT=0
```

La regressione completa post-TLS D278/12 passa dopo l'introduzione della
baseline decodificata, normale e ASan/UBSan. Nessun comando di questi test
enumera o apre il sensore.

## Review PM e limiti probatori

La review ha corretto due difetti prima della closure: mancata propagazione del
copy failure verso lo stage enrollment e mancato cleanse del baseline nel
teardown del device context. Ha inoltre verificato la registrazione attraverso
il tool standard, non con un registrar custom.

La soglia SIGFM continua a usare il campo storico `bz3_threshold` con default
40. Questo prova soltanto il wiring: D279/48 non contiene different-finger e
non giustifica soglia, FAR/FRR o accuratezza production. Il test azione ripete
un input sintetico e non è evidenza biometrica. fprintd, storage installato,
compatibilità daemon e vera action identify restano non verificati.

```text
REVIEW_DECISION=ACCEPT_AND_CONTINUE
RESIDUAL_BLOCKER_OR_RISK=FPRINTD_STORAGE_AND_IDENTIFY_ACTION_INTEROP_NOT_YET_CLOSED;SIGFM_THRESHOLD_NOT_PRODUCTION_VALIDATED
CANONICAL_DOCUMENTATION=UPDATED
NEXT_PRIMARY_BOUNDARY=OFFLINE_FPRINTD_STORAGE_AND_SIGFM_IDENTIFY_INTEROP_REVIEW
REVIEW_SET=GIT_NATIVE_BASELINE_90848D1D4D01E975F9552E104D226DBD6C50DA13_PLUS_D279_52_DIFF
```
