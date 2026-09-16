<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/50 — real SIGFM ownership and strict storage

## Closure

```text
OUTCOME=READY
ADVANCEMENT=REAL_SIGFM_COPY_MATCH_AND_STRICT_SAMPLE_STORAGE_EXECUTABLY_CLOSED
EXECUTABLE_CLOSURE=PASS_HOST_ONLY_REAL_SIGFM_OPENCV_4_13
REAL_SIGFM_KEYPOINTS_SYNTHETIC=220
REAL_SIGFM_IDENTICAL_FIXTURE_SCORE=160
REAL_SIGFM_STRICT_STORAGE_ROUNDTRIP=PASS
CORRUPTION_REJECTION=PASS
ASAN_UBSAN_TEST_DOUBLE=PASS_FREEDESKTOP_SDK_25_08
USB_OR_LIVE_ACTION_COUNT=0
SECRET_ACCESS_COUNT=0
SYSTEM_PACKAGE_INSTALL_COUNT=0
```

Il wrapper C++ `goodix_sigfm_metrics.cpp` usa direttamente le API della
reference preservata `sigfm.cpp` per extraction, keypoint count, copy, match,
serialize, deserialize e free. Non reimplementa SIFT o il matcher geometrico.
Ogni eccezione C++ resta contenuta prima del confine C.

Il precedente entrypoint u16/D269 resta compatibilità storica. Il nuovo
`goodix_sigfm_extract_pixels()` riceve invece i 5.120 byte già prodotti dal
preprocessore R2 D279/49. Il gate è 25..1024 keypoint; 25 resta una soglia
operativa Rockytkg, non una soglia biometrica/security validata.

## Envelope strict `GSF1`

La serializzazione Rockytkg preservata è nativa: `size_t`, `int`, `float` e
layout OpenCV. D279/50 non la espone senza controllo. La racchiude in `GSF1`
con versione, header length, endian marker, keypoint count, payload length e
CRC-32/IEEE. Il formato corrente è esplicitamente limitato a x86_64
little-endian con int/float a 32 bit.

Prima di chiamare il deserializer Rockytkg vengono verificati:

- size totale non oltre 553.004 byte e assenza di trailing data;
- 25..1024 keypoint e identico count interno;
- record keypoint di 28 byte con float finiti, scale positiva, angle e
  coordinate coerenti con 80×64;
- matrice `CV_32FC1`, righe uguali ai keypoint e 128 colonne SIFT;
- tutti i descriptor float finiti;
- CRC valido.

Dopo il deserialize l'oggetto deve restituire lo stesso count e serializzarsi
byte-identico al payload originale. Soltanto allora l'ownership passa al
caller. Buffer intermedi e serializzati liberati tramite il wrapper vengono
azzerati; le allocazioni interne C++/OpenCV non offrono una garanzia completa
di zeroization.

## Executable closure reale

`run_goodix_sigfm_storage_real_test.sh` accetta i cinque RPM Fedora 44 OpenCV
4.13 già digest-pinned da D279/48, li verifica e li estrae esclusivamente sotto
`/tmp`. Compila il C++ nell'SDK Freedesktop 25.08 offline e collega il runtime
Fedora host come già provato dal kit D279/48. Nessun pacchetto è installato.

La fixture è sintetica e non target-derived. Il risultato 220 keypoint/score
160 prova soltanto l'esecuzione reale di extract/copy/storage/match; non è
evidenza FAR/FRR o threshold production. La suite con test double copre anche
errori, ownership e ASan/UBSan.

## Scope e prossimo confine

Questo slice non modifica ancora il core libfprint 1.94.100, FP3 o le action.

```text
KEEP=ROCKYTKG_SIGFM_IMPLEMENTATION
ADAPT=LIBFPRINT_1_94_100_PRINT_TYPE_MULTI_SAMPLE_FP3_VERIFY_IDENTIFY
NEXT_PRIMARY_BOUNDARY=OFFLINE_FEDORA44_LIBFPRINT_1_94_100_SIGFM_PRINT_FORWARD_PORT
RESIDUAL_RISK=GSF1_IS_ABI_PINNED_AND_THRESHOLD_20_OR_25_NOT_BIOMETRICALLY_VALIDATED
```
