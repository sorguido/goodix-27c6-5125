<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D292/01 — inventario della sorgente production

> Snapshot storico dell'input a D292/02. Lo stato canonico corrente, inclusi
> source-of-truth, delta a 16 file e separazione delle seam, è in
> `D292_02_SOURCE_OF_TRUTH_AND_REPRODUCIBLE_BUILD.md`; il JSON/validator D292
> sono stati avanzati allo schema corrente.

Baseline: `420894d093c04b2dc31980cf9292389362dfc6f0`  
Target: Fedora KDE, Goodix USB `27c6:5125` / APP12509  
Scope: audit host-only; nessun file spostato/cancellato, nessun codice o licensing boundary modificato.

## Esito

A1 è chiuso: l'attuale build production è derivabile senza ambiguità dal Meson
e comprende 77 translation unit versionate più tre generate. Il file set
machine-readable include anche il tree Fedora baseline, 32 header locali/Rocky
derivati dalla closure degli include, il delta downstream completo e gli input
di orchestrazione correnti. `D292_01_PRODUCTION_FILE_SET.json` viene verificato
direttamente contro Meson, Git, dichiarazioni/definizioni, call-site, esistenza
e mapping licenza/provenance.

```text
D292_01_OUTCOME=PASS_ARCHITECTURAL_INVENTORY
CURRENT_PHASE=A
PHASE_A_A1=COMPLETED
PRODUCTION_TRANSLATION_UNITS=77
GENERATED_TRANSLATION_UNITS=3
LOCAL_AND_ROCKY_HEADER_INPUTS=32
FEDORA_DOWNSTREAM_DELTA_FILES=15
PRODUCTION_COMPILED_FORBIDDEN_PREFIX_COUNT=0
SOURCE_OF_TRUTH_CONSOLIDATED=false
BUILD_PIPELINE_INDEPENDENT_FROM_HISTORICAL_TOOLING=false
```

## Grafo reale corrente

```text
reference/libfprint-fedora44-1.94.100/source
  meson.build + libfprint/meson.build
  libfprint core/private (15 TU) + NBIS (32 TU)
             |
             +-- libfprint-driver/ (29 TU locali)
             |     `-- R2 GPL: goodix_sigfm_preprocess.c + goodix_imgproc.c
             `-- Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp (1 TU LGPL)
                            |
operator_kit/d282-01-fprintd-target/build-inner.sh
  Meson: drivers=goodix_27c6_5125, SIGFM, DIRECT_ENROLL_PROFILE
  Flatpak SDK 25.08 + OpenSSL + OpenCV 4.13 + host GUsb
                            |
                 libfprint-2.so.2.0.0
                            |
D285: /usr/local runtime + LD_LIBRARY_PATH wrapper
                            |
      system /usr/libexec/fprintd 1.94.5 (D-Bus/storage FP3)
                            |
                   PAM / KDE consumers
```

Il runtime fprintd non viene costruito da `reference/fprintd-fedora44-1.94.5/`:
usa il binario Fedora installato e l'ABI `LIBFPRINT_2.0.0`. D291 riusa senza
variazioni il builder D282 e sostituisce soltanto la libreria nel runtime D285.

La candidate/runtime contiene `libfprint-2.so.2.0.0`, GUsb e le quattro librerie
OpenCV necessarie, manifest hash e symlink SONAME. I materiali runtime sono
letti dai cinque path fissi sotto `/var/lib/goodix-5125-poc/`; non entrano nel
repository o nel package.

## Delta Fedora, input non-TU e generated input

Il tree chiamato `reference/` è in realtà anche la fork production corrente.
Il confronto Git con la baseline pristine
`f609c865f760768edb6a9e404b863ccd0569e1c8` produce esattamente 15 path:
tre input production build/ABI (`source/meson.build`,
`source/libfprint/meson.build`, `source/libfprint/libfprint.ver`), undici file
core production (`fp-print.c`, `fpi-print.c/.h`, `fp-image.c`,
`fp-image-device.c`, `fpi-image-device.c/.h`, `fpi-image.c`, `fpi-image.h`,
`fp-image-device-private.h`, `fpi-device.c`) e un delta esclusivamente test,
`source/tests/meson.build`. Il builder genera `fp-enums.c`, `fpi-enums.c` e
`fpi-drivers.c`; quest'ultimo registra `fpi_device_goodix_27c6_5125_get_type`.

Gli input non-TU sono rappresentati senza duplicare ogni header upstream:
l'intero tree Fedora 44/libfprint 1.94.100 è l'input baseline con provenance;
sono invece elencati singolarmente i 29 header `libfprint-driver/`, i tre header
SIGFM Rocky, i due script D282, i due template pkg-config sotto `tests/` e il
manifest hash degli RPM OpenCV usati dal builder corrente.

Il combined work conserva le licenze per-file: core Fedora/libfprint LGPL,
NBIS pubblico dominio NIST, SIGFM LGPL, sorgenti locali prevalentemente LGPL e
R2 GPL-2.0-or-later. La presenza di R2 mantiene il risultato nel regime
GPL-compatible già approvato; D292 non cambia tale boundary.

## Superficie simboli non protetta

L'audit non usa più tre marker campione. Il validator deriva dall'header tutti
i 52 prototipi espliciti esterni non protetti da
`GOODIX_ENABLE_TEST_SEAMS`, ne verifica la definizione e classifica i call-site;
registra inoltre i due simboli GType generati dalle macro GLib. L'esito è:

- 1 entrypoint registry/runtime production;
- 12 simboli shared/internal realmente richiamati dal flusso production;
- 39 simboli richiamati soltanto da test/tool host, oppure senza call-site;
- 0 simboli ambigui e 0 call-site production per i 39 simboli test/host-only.

Le quattro sezioni dell'header esplicitamente etichettate instrumentation,
assertions, gate e fake injection contengono 24 dichiarazioni, ma sette sono
anche usate internamente dal runtime production. L'etichetta di sezione non è
quindi una classificazione sufficiente: A3 deve separare i 39 simboli realmente
test/host-only preservando i 12 shared/internal necessari.

## Classificazione delle superfici

| Superficie | Classificazione corrente | Confine rilevante |
| --- | --- | --- |
| `libfprint-driver/` | mista production/test | top-level e `rockytkg-imgproc/` alimentano Meson; `tests/` non è compilato ma fornisce oggi due template pkg-config alla build |
| `reference/libfprint-fedora44-1.94.100/source/` | mista production/reference/test/docs | fork production corrente; solo i gruppi Meson inventariati entrano nella libreria |
| `Rockytkg/` | mista reference/production | solo `libfprint/libfprint/sigfm/sigfm.cpp` entra come TU; tre header SIGFM sono input; il resto è reference/storico |
| `operator_kit/` | tooling operatore/storico | D282 è ancora dipendenza della build e D285 del deploy; non è sorgente compilato |
| `analysis/` | evidenza/review/test | nessuna TU production; D282 è incluso nel vecchio critical archive ma non compilato |
| `captures/` | evidenza privata | nessuna dipendenza build/runtime |
| `tests/`, `libfprint-driver/tests/` | test/fixture | nessuna TU production; due `.pc.in` sono però build dependency improprie |
| `reference/fprintd-fedora44-1.94.5/` | reference | audit del consumer; non compilato né linkato |
| `core/`, `tools/`, `src/`, `poc/` | storico/reference/tooling sviluppatore | non entrano nella libreria production corrente |
| `GoodixArtifacts/opencv-4.13-rpms/` | dipendenza binaria terza | input del builder, non sorgente project-owned |
| `docs/`, manuale, governance, `LICENSES/` | documentazione/licensing | non runtime |

## Audit preliminare storico / red tag

Nessun move è autorizzato. In particolare `operator_kit/d282-01-fprintd-target/`,
`operator_kit/d285-01-persistent-sudo/`, `libfprint-driver/tests/support/d279/`,
il tree Fedora sotto `reference/` e il subset SIGFM di `Rockytkg/` hanno ancora
dipendenze dirette di build/deploy/provenance. `analysis/D282` è ancora incluso
nel vecchio live-critical archive. Prima di qualsiasi `red tag/` occorre
disaccoppiare tali riferimenti e ripetere audit import/build/test/script/docs,
provenance, licensing e dipendenze production.

## Blocker A3/A4 e scelta minima

1. La source-of-truth è distribuita fra tre alberi e usa path relativi al layout
   repository; il delta Fedora non è una patch series riproducibile separata.
2. Build e deploy dipendono da operator kit D282/D285 e la build usa due
   template sotto `tests/`; la libreria compilata non contiene TU da
   `analysis/`, `operator_kit/` o `tests/`, ma la pipeline non è autonoma.
3. `goodix_fpimage_device.[ch]` espone senza guard 39 simboli con soli call-site
   test/tool host o senza caller. Altri 12 simboli apparentemente mescolati alle
   sezioni test sono invece chiamati dal flusso production interno. Il define
   test non è abilitato, ma la separazione simbolo/file richiesta da A3/A4 non
   è chiusa.
4. Il comportamento production dipende dal nome storico
   `GOODIX_D282_DIRECT_ENROLL_PROFILE`; va trasformato in policy production
   esplicita e testata, senza riaprire il protocollo chiuso.
5. D285 resta installazione single-user `/usr/local`, non package; i path
   `/var/lib/goodix-5125-poc` e il wrapper `LD_LIBRARY_PATH` non sono ancora un
   contratto production mantenibile.

La scelta minima compatibile col licensing esistente è conservare Fedora
44/libfprint 1.94.100 come baseline target e il regime GPL-compatible corrente,
ma trasformare il delta documentato in una source-of-truth downstream unica e
riproducibile: patch series/tree production esplicito che incorpori i sorgenti
locali e il solo subset SIGFM/R2 ledgered, con builder non-Dxxx e senza
dipendenze da `tests/`. Nessuna reimplementazione SIGFM, cambio di licensing o
move storico è necessario. Il prossimo boundary è definire/validare questa
topologia A3 e poi provarne clean build normal/sanitizer e ABI in A4.

## Verifica

```text
python3 analysis/D292/validate_d292_01_inventory.py
D292_01_INVENTORY_CHECK=PASS
D292_01_COMPILED_TRANSLATION_UNIT_COUNT=77
D292_01_GENERATED_TRANSLATION_UNIT_COUNT=3
D292_01_LOCAL_AND_ROCKY_HEADER_INPUT_COUNT=32
D292_01_DOWNSTREAM_DELTA_COUNT=15
D292_01_DOWNSTREAM_PRODUCTION_BUILD_INPUT_COUNT=3
D292_01_DOWNSTREAM_PRODUCTION_CORE_COUNT=11
D292_01_DOWNSTREAM_TEST_ONLY_COUNT=1
D292_01_UNPROTECTED_EXPLICIT_SYMBOL_COUNT=52
D292_01_REGISTRY_RUNTIME_SYMBOL_COUNT=1
D292_01_SHARED_INTERNAL_PRODUCTION_SYMBOL_COUNT=12
D292_01_TEST_HOST_ONLY_UNPROTECTED_SYMBOL_COUNT=39
D292_01_AMBIGUOUS_SYMBOL_COUNT=0
D292_01_TEST_HOST_ONLY_PRODUCTION_CALL_SITE_COUNT=0
D292_01_HEADER_LABELED_SYMBOL_COUNT=24
D292_01_PRODUCTION_COMPILED_FORBIDDEN_PREFIX_COUNT=0
D292_01_BUILD_TEST_AREA_DEPENDENCY_COUNT=2
D292_01_GOODIX_ENABLE_TEST_SEAMS=false
D292_01_TARGET=FEDORA_KDE_APP12509
```
