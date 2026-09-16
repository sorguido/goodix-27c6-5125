<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/26 — vera action libfprint a 21 stage

## Esito

Il transcript target-local completo D279/25 è stato eseguito dentro una vera
action asincrona `fp_device_enroll()` sul device virtuale host-only.

```text
OUTCOME=READY_OFFLINE_TRUE_LIBFPRINT_ACTION
ADVANCEMENT=FULL_21_STAGE_CONTEXT_TRANSCRIPT_COMPLETES_ONE_LIBFPRINT_ENROLL_ACTION
CONFIGURED_STAGE_COUNT=21
LIBFPRINT_PROGRESS_COUNT=21
LIBFPRINT_COMPLETION_COUNT=1
LIBFPRINT_PRINT_RETURNED=true
FINAL_DEVICE_STATE=INACTIVE
PRODUCTION_ENROLLMENT_ENABLED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Boundary e safety

L'iniezione di B0 plaintext già decifrato è raggiungibile soltanto quando non
esiste una secure session e il context appartiene a un `operator_epoch` oppure
a un device non-production. Il path USB production mantiene la precedenza TLS,
non soddisfa il predicato host-only e continua a rifiutare enrollment prima di
generation e submit. L'audit sorgente conferma che nessun caller production
configura il grafo enrollment.

Il transcript conserva 125 comandi completion-gated, 188 A0, 21 B0 primari,
21 B0 ausiliari opachi e 21 coppie finger-down/finger-up. Non introduce retry,
reopen, reset, clear-halt o famiglie di scrittura persistente.

## Verifiche

```text
FOCUSED_ACTION_NORMAL=PASS
FOCUSED_ACTION_ASAN_UBSAN=PASS
FPIMAGE_DEVICE_TESTS=27/27_PASS_NORMAL;27/27_PASS_ASAN_UBSAN
ENROLLMENT_MODEL_AND_PIPELINE_REGRESSION=PASS_NORMAL;PASS_ASAN_UBSAN
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
PRODUCTION_CONFIGURATION_CALLER_PRESENT=false
HOST_ONLY_PLAINTEXT_INJECTION_PRODUCTION_REACHABLE=false
```

La vera action usa la source map host storica e il double SIGFM. La build
Fedora 44 compila e collega NBIS nativo, ma non esegue l'extractor su queste
fixture. Pertanto `NBIS_BIOMETRICALLY_VALIDATED=false` e la qualità dei raster
reali resta il futuro boundary hardware/biometrico.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_REAL_NBIS_ACTION_MECHANICS_THEN_MINIMAL_PRODUCTION_USB_ONE_SHOT_BINDING
```
