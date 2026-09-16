<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/51 — Fedora 44 libfprint SIGFM print core

## Closure

```text
OUTCOME=READY
ADVANCEMENT=FEDORA44_LIBFPRINT_1_94_100_SIGFM_PRINT_TYPE_MATCH_AND_STRICT_FP3_FORWARD_PORTED
EXECUTABLE_CLOSURE=PASS_HOST_ONLY_REAL_SIGFM_FOCUSED_LINK
REAL_SIGFM_IMPLEMENTATION=ROCKYTKG_SIGFM_CPP_AT_7EBE0C809B4D1DF3400E84299A4EC4ACDEA84590
REAL_SIGFM_KEYPOINTS_SYNTHETIC=220
FP3_MULTI_SAMPLE_ROUNDTRIP=PASS_BYTE_IDENTICAL
FP3_CORRUPTION_REJECTION=PASS
SAMPLE_COUNT_BOUND=1_TO_21
ASAN_UBSAN_TEST_DOUBLE=PASS_FREEDESKTOP_SDK_25_08
NBIS_REGRESSION_BUILD=PASS
USB_OR_LIVE_ACTION_COUNT=0
SECRET_ACCESS_COUNT=0
SYSTEM_PACKAGE_INSTALL_COUNT=0
```

## Implementazione

Il fork target conserva il layout e la state machine Fedora 44/libfprint
1.94.100. Il port introduce `FPI_PRINT_SIGFM` e adatta dal fork Rockytkg:

- template con più campioni e probe singolo;
- copy indipendente dei campioni;
- dispatch del matcher con soglia esplicita;
- payload FP3 `(a(ay))`.

Il port non riusa il raw ownership del fork Rockytkg. Ogni elemento è un
`GoodixSigfmSample` D279/50; copy/free/match/serialize/deserialize attraversano
il confine C che contiene le eccezioni C++. Ogni `ay` FP3 è un envelope `GSF1`
validato, non il payload ABI-native non autenticato esposto direttamente dal
fork di riferimento.

Il numero di campioni persistibili è 1..21, corrispondente agli stage Goodix
correnti. Il probe di match deve contenerne esattamente uno. La
deserializzazione rifiuta tipo GVariant errato, count fuori limite, size oltre
il massimo D279/50, envelope/payload non canonico o corrotto e tipo enum
sconosciuto. Una build senza `GOODIX_LIBFPRINT_SIGFM` rifiuta esplicitamente
serializzazione e deserializzazione SIGFM invece di cadere nel ramo RAW.

`fp_print_equal()` serializza canonicamente entrambi i campioni, confronta i
byte e usa la funzione di release che azzera i buffer intermedi.

## Verifiche

La suite sintetica focalizzata compila i sorgenti target `fp-print.c` e
`fpi-print.c` con il seam SIGFM e copre:

- copy multi-sample;
- match success/fail/errore;
- serialize → deserialize → serialize byte-identico;
- corruzione CRC rifiutata;
- count zero e 22 rifiutati;
- ASan e UBSan, LeakSanitizer disabilitato per il boundary ptrace Flatpak.

```sh
sh libfprint-driver/tests/run_goodix_fedora44_sigfm_print_test.sh
```

La closure reale verifica i cinque RPM OpenCV già pin D279/48, li estrae in
`/tmp` e collega gli stessi sorgenti core al `sigfm.cpp` preservato. Il raster
è sintetico e produce 220 keypoint; non è evidenza biometrica né una
validazione della soglia production.

```sh
sh libfprint-driver/tests/run_goodix_fedora44_sigfm_print_real_test.sh \
  /tmp/goodix-d27950-opencv/rpms
```

Il test focalizzato costruisce prima la libreria target standard per ottenere
gli header enum/config e verificare la regressione NBIS; ricompila poi i due
sorgenti core con il seam SIGFM. Il grafo Meson production non abilita ancora
il macro né compila OpenCV/SIGFM: questo è un boundary esplicito, non un claim
di package closure.

## Review PM

La review ha corretto il fallback iniziale di una build senza backend: il tipo
SIGFM non può più raggiungere il ramo RAW. Ha inoltre aggiunto un default
fail-closed per enum sconosciuti e una closure separata con l'implementazione
Rockytkg reale. Il percorso NBIS non è stato modificato e la build esatta
1.94.100 continua a passare.

```text
REVIEW_DECISION=ACCEPT_AND_CONTINUE
PRODUCTION_MESON_SIGFM_ENABLED=false
IMAGE_ACTION_SIGFM_ENABLED=false
THRESHOLD_PRODUCTION_VALIDATED=false
NEXT_PRIMARY_BOUNDARY=OFFLINE_SIGFM_IMAGE_ACTION_AND_PRODUCTION_MESON_BINDING
REVIEW_SET=GIT_NATIVE_D279_51_DIFF
```
