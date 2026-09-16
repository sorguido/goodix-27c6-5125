<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D292/02 — source-of-truth e build production riproducibile

Baseline task: `0bda0dc239cad9c5d62cbb906f1c1fc7183c753b`  
Target: Fedora 44 KDE x86_64, Goodix `27c6:5125` / APP12509  
Scope: build e test esclusivamente offline; nessun install/deploy, USB, materiale protetto o live.

## Esito

A3 e A4 sono chiusi. `production/` è l'unica autorità di composizione: il
builder ricostruisce in una directory temporanea il tree pristine Fedora
44/libfprint 1.94.100 dal commit
`f609c865f760768edb6a9e404b863ccd0569e1c8`, applica la patch production
rigenerabile e copia il subset locale Goodix/SIGFM/R2 elencato e hashato. Il
tree `reference/` già modificato serve soltanto al drift check della patch;
operator kit Dxxx e aree test non sono input del prodotto.

```text
D292_02_OUTCOME=PASS_SOURCE_OF_TRUTH_AND_REPRODUCIBLE_BUILD
PHASE_A_A3=COMPLETED
PHASE_A_A4=COMPLETED
CANONICAL_COMPOSITION_ROOT=production/
PRODUCTION_TRANSLATION_UNITS=77
GENERATED_TRANSLATION_UNITS=3
LOCAL_AND_ROCKY_HEADER_INPUTS=32
FEDORA_DOWNSTREAM_DELTA_FILES=16
PRODUCT_PATCH_FILES=15
HISTORICAL_TEST_ONLY_DELTA_FILES=1
NEWLY_GUARDED_TEST_HOST_ONLY_SYMBOLS=39
PRODUCTION_TEST_HOST_ONLY_SYMBOLS=0
BUILD_TEST_AREA_DEPENDENCIES=0
```

## Compatibilità target osservata

Il controllo read-only ha rilevato Fedora 44 KDE x86_64, libfprint
`1.94.100-1.fc44`, fprintd/fprintd-pam `1.94.5-5.fc44`, OpenSSL 3.5.8,
GLib 2.88.3, libgusb 0.4.9 e opencv-core 4.13.0. `opencv-devel` non è
installato sull'host, ma i cinque RPM locali 4.13 passano il manifest SHA-256.
Il Flatpak SDK 25.08 installato è il commit
`b90ed309cc1d505dea48b6a2121c5dcfac22868120eee643b0596d31f96b9bb8`;
la build osserva Meson 1.9.2 e GCC/G++ 15.2. `/usr/libexec/fprintd` dipende da
`libfprint.so.2` e richiede 47 simboli versionati `LIBFPRINT_2.0.0`, tutti
forniti dall'artefatto canonico. L'assenza host di toolchain C++/header OpenCV
è irrilevante perché la build usa soltanto SDK e RPM pinned.

## Composizione e separazione

`production/source-files.tsv` e `source-files.sha256` definiscono i 30 TU e 32
header non-upstream; il tree Fedora pristine rappresenta il resto dei 77 TU e
degli header upstream senza duplicazione massiva. `downstream-paths.txt`
genera una patch di 15 file production. Il delta Git complessivo dalla
baseline pristine è invece 16: quattro input build/ABI (`meson.build`,
`meson_options.txt`, `libfprint/meson.build`, `libfprint.ver`), undici file
core e il solo `tests/meson.build`, storico e deliberatamente escluso dalla
patch prodotto.

Nel JSON schema 2 `d292_02_task_baseline` identifica esplicitamente
`0bda0dc239cad9c5d62cbb906f1c1fc7183c753b`, mentre
`d292_01_inventory_baseline` preserva la provenance dello snapshot A1. Il
checker impone uguaglianza esatta e unicità fra path TSV e path hashati,
30 TU/32 header, file regolari versionati e path relativi sicuri; impone inoltre
che i 15 `downstream-paths.txt` coincidano col delta Git documentato meno il
solo `tests/meson.build`.

La policy stabile è `GOODIX_PRODUCTION_DIRECT_ENROLL_PROFILE`; il precedente
identificatore D282 non entra in builder, compile commands o libreria. La
modalità Meson `goodix_production_minimal` non configura test/examples e
compila fuori l'emulazione test di `fpi-device.c`. I 39 simboli identificati
da D292/01 come host/test-only sono ora sotto `GOODIX_ENABLE_TEST_SEAMS`; i 12
simboli shared/internal restano production. Il test focalizzato conferma che
le seam rimangono esercitabili in build test.

Il builder è unprivileged, usa `flatpak --unshare=network`, richiede output
assoluto nuovo/vuoto e non enumera USB, non carica materiali runtime e non
installa/deploya. I template `.pc`, l'header GUsb e il manifest OpenCV sono
copie canoniche sotto `production/build-support/`, verificate per digest.

## Verifiche eseguite

```text
production/check-source.sh = PASS
SOURCE_MANIFEST_PATH_SET=PASS (30 TU, 32 header, 0 prefix vietati)
DOWNSTREAM_PATH_SET=PASS (15 production = delta documentato meno 1 test-only)
python3 analysis/D292/validate_d292_01_inventory.py = PASS
production/build.sh normal /tmp/goodix-d292-normal-root-fixed = PASS
(cd /tmp && <repo>/production/build.sh normal /tmp/goodix-d292-normal-cwd-fixed) = PASS
NORMAL_BINARY_SHA256=11f829bd8aa912aef92a00eb68a15b4b5ab430fafd948fec944da33f9c1482a2
NORMAL_BINARY_BYTE_IDENTICAL_ACROSS_CWD=true
production/build.sh sanitizer /tmp/goodix-d292-sanitizer-fixed = PASS
focused GOODIX_ENABLE_TEST_SEAMS normal + ASan/UBSan = PASS
REAL_USB_SUBMIT=0
HOST_TEST_ONLY_SYMBOLS_IN_PRODUCTION=0/39
FPRINTD_REQUIRED_LIBFPRINT_2_0_0=47/47
SONAME=libfprint-2.so.2
RPATH_OR_RUNPATH=false
GOODIX_D282_POLICY_IN_CANONICAL_BUILD_OR_OUTPUT=false
```

Il licensing boundary non cambia: Fedora/libfprint e SIGFM conservano le
licenze originarie, i file locali mantengono le licenze per-file e il subset
R2 GPL mantiene il combined work nel regime GPL-compatible già documentato.

## Residui e prossimo boundary

Phase A non viene dichiarata chiusa automaticamente: serve la review di
closure A5 sulla superficie distribuibile/provenance e sulla coerenza fra
manifest, documentazione e artefatto. D285 (`/usr/local`, wrapper
`LD_LIBRARY_PATH`, provisioning/path dei materiali protetti) resta evidenza
storica e problema delle fasi multi-user/packaging successive; non è una
dipendenza della build canonica. Nessun move/red tag è autorizzato in questo
step.

```text
CURRENT_PHASE=A
PHASE_A_CLOSED=false
NEXT_BOUNDARY=PHASE_A_A5_DISTRIBUTION_PROVENANCE_CLOSURE_REVIEW
NEW_LIVE_REQUIRED_NOW=false
```
