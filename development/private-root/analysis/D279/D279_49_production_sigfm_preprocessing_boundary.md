<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/49 — production SIGFM preprocessing boundary

## Closure

```text
OUTCOME=READY
ADVANCEMENT=ROCKYTKG_R2_PREPROCESSING_PROMOTED_TO_PURE_PRODUCTION_COMPONENT
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
ROCKYTKG_R2_KAT=PASS_BYTE_IDENTICAL_TO_D279_48
FORBIDDEN_SYMBOL_AUDIT=PASS
ASAN_UBSAN=PASS_OFFLINE_FREEDESKTOP_SDK_25_08
USB_OR_LIVE_ACTION_COUNT=0
SECRET_ACCESS_COUNT=0
```

D279/49 riusa direttamente gli stadi algoritmici di
`Rockytkg/src/goodix_imgproc.c` e il contratto parametri del relativo header,
commit preservato `227eba219fa9e3fbac5bd59aca79f624f67cd11b`. La copia production
rimane `GPL-2.0-or-later` ed è registrata come `ADAPTED_FROM_ROCKY` nel ledger.

```text
UPSTREAM_SOURCE_SHA256=177113b3e4e7d71b567850ea5f6ca02738987a2f11a793aa0ae303a585510043
UPSTREAM_HEADER_SHA256=6e7539dab531aa3da4a19317f8240bab32f6f1ce901890eed2366909fbe840d1
ADAPTED_SOURCE_SHA256=fca46d0ffb02d09db844cbf5bbb808231aeefdb4934a62c20a633a3513310008
ADAPTED_HEADER_SHA256=6287c8f310e28ba629d4dd95bc716698dc6d6460eb86b9c1ac7e394663b23398
```

L'adattamento minimo elimina la dipendenza dall'intero `goodix_dev`, gli
override `GOODIX_IMGPROC_*`, `getenv` e i dump su file. Li sostituisce con una
vista pura di frame/baseline 16-bit little-endian. Non vengono importati
transport, USB, TLS, PSK, firmware, provisioning, lifecycle o stato persistente.

Il wrapper `goodix_sigfm_preprocess_r2()` accetta esclusivamente i raster
canonici u16/12-bit 80×64, valida integralmente input e capacità prima di
mutare l'output, converte esplicitamente in little-endian e fissa:

```text
baseline_offset=2048
flatfield_radius=12
percentile_low=1
percentile_high=99
enhance=SIGFM
unsharp_boost=0.8
unsharp_sigma=1.5
```

Il KAT sintetico già usato da D279/48 produce SHA-256
`2ff834cdef0316b3280d86a46fa75881c50bff3f4240e03dc31c24f6fc4153b3`.
L'audit dei simboli indefiniti esclude environment/file/network/USB/TLS e
famiglie `gx_*` sensor-reaching. Sul solo host Fedora manca il runtime ASan;
la stessa suite ASan/UBSan passa però nell'SDK Freedesktop 25.08 già presente,
offline e senza installare dipendenze. LeakSanitizer resta disabilitato nel
sandbox perché incompatibile con il suo ptrace boundary.

## Scope e prossimo confine

Lo slice non modifica ancora `goodix_fpimage_device`, action, template o
serializzazione. La baseline D279/48 è session-local/experimental e non viene
elevata a no-finger equivalence production.

```text
KEEP=LOCAL_APP12509_USB_TLS_FDT_LIFECYCLE_AND_CANONICAL_DECODER
ADAPT=SIGFM_METRIC_SEAM_TO_BASELINE_AWARE_R2_INPUT
NEXT_PRIMARY_BOUNDARY=OFFLINE_REAL_SIGFM_SAMPLE_OWNERSHIP_COPY_SERIALIZE_DESERIALIZE_MATCH
```
