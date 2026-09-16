<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D269/01 — Linux u16/12-bit → libfprint contract

```text
OUTCOME=READY — D269_01_PIXEL_REPRESENTATION_CONTRACT_CLOSED_PPMM_LOCALIZED
ADVANCEMENT=FPIMAGE_PPMM_SEMANTICS_AUDITED_AND_FULL_PIPELINE_PREREQUISITE_LOCALIZED
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=TARGET_APP12509_PHYSICAL_PPMM_UNRESOLVED; ORIENTATION_AND_POLARITY_UNRESOLVED; BIOMETRIC_QUALITY_OF_FIXED_MAPPING_NOT_YET_PROVEN
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=analysis/D269/D269_01_linux_u16_libfprint_contract_bundle.zip
BUNDLE_SHA256=SEE_EXTERNAL_SIDECAR
ADAPTER_BYTES_UNCHANGED=true
RUNTIME_CODE_CHANGE_REQUIRED=false
PIXEL_REPRESENTATION_CONTRACT=CLOSED_OFFLINE
INTENSITY_QUANTIZATION_CONTRACT=CLOSED_OFFLINE
FULL_FPIMAGE_PIPELINE_CONTRACT=NOT_YET_CLOSED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_PPMM_EVIDENCE_CLASS=UNKNOWN
ROCKYTKG_GOODIX_PPMM_500DPI=THIRD_PARTY_CORROBORATION
NEXT_PRIMARY_BOUNDARY=LIBFPRINT_IMAGE_PIPELINE_INTEGRATION_OFFLINE
NEXT_BOUNDARY_PREREQUISITE=RESOLVE_OR_EXPLICITLY_BOUND_PPMM_SEMANTICS
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

## Scope e baseline

- Execution mode: `OFFLINE ONLY`.
- Branch: `development`.
- ORIGINAL_D269_01_STARTING_HEAD: `b3c094e28eb407f937c884423cf265551cc2a32e`.
- D269_01_CORRECTIVE_STARTING_HEAD: `e60b571f6fe2a54be76726582777029d36d202f1`.
- HEAD iniziale (corrective): `e60b571f6fe2a54be76726582777029d36d202f1`.
- Worktree iniziale: pulito.
- Nessun accesso USB/hardware, TLS, secret o fprintd; nessun `sudo`.
- Nessuna modifica a core, decoder, tool o path live-critical.
- Fonte libfprint locale: snapshot materializzato, versione dichiarata `1.94.5`, gitlink upstream preservato `7ebe0c809b4d1df3400e84299a4ec4acdea84590`.

## Risultato del gate API libfprint

```text
LIBFPRINT_IMAGE_PIXEL_CONTRACT=PACKED_GRAYSCALE_U8_ONE_BYTE_PER_PIXEL
LIBFPRINT_IMAGE_BIT_DEPTH=8
LIBFPRINT_IMAGE_DIMENSION_CONTRACT=WIDTH_HEIGHT_CONSTRUCT_ONLY_DATA_LENGTH_WIDTH_X_HEIGHT_STRIDE_IMPLICIT_WIDTH
LIBFPRINT_IMAGE_ORIENTATION_MECHANISM=V_FLIPPED_H_FLIPPED_COLORS_INVERTED_FLAGS_NO_ROTATE_OR_TRANSPOSE_FLAG
LIBFPRINT_IMAGE_OWNERSHIP_CONTRACT=FPIMAGE_GOBJECT_OWNS_ALLOCATED_DATA
LIBFPRINT_PREPROCESSING_EXPECTATION=DRIVER_SUPPLIES_U8;STANDARD_PATH_ONLY_APPLIES_FLAGS_THEN_NBIS_8BIT;SIGFM_CONSUMES_U8_COPY_DIRECTLY
```

Evidenza locale principale:

- **OSSERVATO** — `Rockytkg/libfprint/meson.build:1-2`: versione `1.94.5`.
- **OSSERVATO** — `libfprint/fpi-image.h:54-74`: `width`, `height`, `flags`, `guint8 *data`; nessuno stride o formato high-bit-depth.
- **VERIFICATO** — `libfprint/fp-image.c:51-78,136-154,440-456`: dimensioni construct-only; allocazione e lunghezza `width*height`.
- **VERIFICATO** — `libfprint/fp-image.c:258-370`: flip/inversione opzionali, poi NBIS con bit depth `8`.
- **VERIFICATO** — `libfprint/fp-image.c:520-569`: i due path downstream copiano esattamente `width*height` byte; SIGFM non applica i flag.
- **OSSERVATO** — `libfprint/fpi-image-device.c:483-527`: il driver consegna un `FpImage`, poi il path selezionato avvia NBIS o SIGFM.
- **INFERITO** — non esiste stride separato: tutti i path locali indicizzano il buffer come righe packed di `width` byte.
- **VERIFICATO** — nessun helper locale libfprint converte u16 o normalizza intensità; la “normalizzazione” standard documentata consiste nei flag flip/inversione prima di NBIS.

Ownership/lifetime: `fp_image_new()` restituisce un GObject che alloca e libera
il proprio `data`; i path asincroni copiano il buffer e trattengono l'oggetto
come source object del task. Il futuro glue deve quindi allocare `FpImage(80,64)`,
riempire i 5120 byte di `data` e consegnare l'oggetto secondo la convenzione
`fpi_image_device_image_captured()`.

## Audit delle opzioni intensity

| Opzione | Monotonicità / stabilità | Effetto e precedente | Decisione |
| --- | --- | --- | --- |
| A. high-bit truncation `v>>4` | monotona, fixed, cross-frame stabile; non reversibile | precedente locale soltanto nei dump GPL Rockytkg; perde i quattro bit bassi e usa una quantizzazione `floor(v/16)` | non scelta: valida alternativa bounded, ma B esprime esattamente gli endpoint del dominio 0..4095 |
| B. linear full-range | monotona non-decrescente, fixed, cross-frame stabile; non reversibile 12→8 | AES3K espande fixed 4-bit→8-bit; preserva ordine ed endpoint senza leggere il frame | **scelta**, con round-to-nearest |
| C. frame min/max | monotona intra-frame ma semanticamente instabile fra frame | ELAN contiene un precedente driver-specifico; aumenta contrasto ma può amplificare outlier/rumore | esclusa dal contratto bounded |
| D. percentili/contrast | adattiva, clipping e significato inter-frame variabile | Rockytkg la usa insieme a baseline/flat-field/enhancement nel core GPL | esclusa: richiede un successivo contratto quality/preprocessing |
| E. helper libfprint | N/A | nessun helper u16→u8 o intensity normalization trovato; esistono solo flags e resize u8 | non disponibile |
| F. Goodix/Rockytkg | adattiva e matcher-specifica | `goodixgf.c` LGPL chiama un helper concreto GPL con baseline, flat-field, percentili e enhancement | corroborazione soltanto; nessun riuso espressivo nel glue LGPL |

```text
INTENSITY_MAPPING_DECISION=FIXED_LINEAR_FULL_RANGE_ROUND_NEAREST_12BIT_TO_8BIT
INTENSITY_MAPPING_FORMULA=round(sample*255/4095)
INTENSITY_MAPPING_EVIDENCE_CLASS=VERIFIED_ENGINEERING_DECISION_FROM_LOCAL_API_AND_FIXED_RANGE_PRECEDENT
INTENSITY_MAPPING_STABILITY=FRAME_CONTENT_INDEPENDENT_CROSS_FRAME_STABLE_MONOTONIC_NONDECREASING
WINDOWS_CONTRACT_REUSED=false
```

Il mapping è un **Linux engineering contract**, non una ricostruzione Windows.
Conserva ordine ed endpoint ed evita dipendenza dal contenuto globale del frame.
Non prova che il contrasto risultante sia ottimale per NBIS o SIGFM: quella è
una decisione quality separata e dovrà usare evidenza biometrica appropriata.

## Orientation e transpose

Il decoder canonico (`src/goodix5125_cleanroom.py:66-85`) esegue già la
trasposizione wire→raster `80x64`. Libfprint 1.94.5 espone flip verticale,
orizzontale e inversione colori, ma nessun rotate/transpose flag. Rockytkg
imposta `COLORS_INVERTED`, ma il suo comportamento è corroborazione su altra
implementazione/hardware e nel fork SIGFM quel flag non modifica l'input.

```text
WIRE_TO_CANONICAL_RASTER_TRANSPOSE=IMPLEMENTED_IN_CANONICAL_GPL_DECODER
CANONICAL_RASTER_TO_FINGERPRINT_NATURAL_ORIENTATION=UNRESOLVED
ORIENTATION_CONTRACT=UNRESOLVED
ADAPTER_ORIENTATION_ACTION=PRESERVE_CANONICAL_RASTER_AND_SET_ZERO_FLAGS
```

Zero flags non dichiara che l'immagine sia già orientata naturalmente: dichiara
soltanto che D269/01 non inventa una trasformazione. Metadata separati rendono
la futura decisione visibile e testabile.

## Licensing e ownership

```text
U16_TO_LIBFPRINT_OWNER=LGPL_LIBFPRINT_DRIVER_GLUE
LICENSING_BOUNDARY_STATUS=PASS_INDEPENDENT_LGPL_ADAPTER_NO_GPL_EXPRESSION_TRANSFERRED
GPL_TO_LGPL_DATA_CONTRACT=OWNED_80X64_U16_12BIT_CANONICAL_RASTER_PLUS_METADATA
```

La conversione esiste solo perché `FpImage` richiede u8 e appartiene quindi al
glue LGPL. Il core GPL resta proprietario del decode/validate Goodix e produce
il raster canonico u16. L'adapter è una nuova implementazione locale indipendente
basata sul contratto API e su una formula matematica elementare. Non copia né
adatta `Rockytkg/src/goodix_imgproc.c`; il ledger non richiede una nuova riga di
import.

## Adapter bounded

```text
ADAPTER_IMPLEMENTATION_GATE=PASS
ADAPTER_PATH=libfprint-driver/goodix_u16_to_fpimage.c
INPUT=80x64/5120 uint16_t samples in 0..4095
OUTPUT=5120 packed uint8_t pixels; width=80; height=64; stride=80; flags=0
```

L'helper valida puntatori, sample count, capacità output e l'intero range prima
di modificare output/metadata. Non muta l'input. Non ha allocazione, I/O,
filesystem, USB, TLS, secret, fprintd o persistenza. È il seam puro esatto che
il futuro glue userà per riempire `FpImage::data`; la costruzione GObject e la
consegna nella pipeline sono intenzionalmente il prossimo step offline.

## Audit correttivo FpImage::ppmm (post review AI-PM)

Il corrective non modifica il converter (`ADAPTER_BYTES_UNCHANGED=true`,
`RUNTIME_CODE_CHANGE_REQUIRED=false`). Audit semantico del campo `ppmm`
secondo la gerarchia probatoria obbligatoria.

A. Significato semantico: `FpImage::ppmm` è un `gdouble` "pixels per millimeter"
(`fpi-image.h:63`), risoluzione di scansione dichiarata dell'immagine.

B. Inizializzazione: `fp_image_init()` è vuoto (`fp-image.c:157-160`); il campo
non è una GObject property né viene impostato in `fp_image_new()`. Il valore
effettivo di default nel clone locale è `0.0` per zero-initialization della
memoria GObject instance; nessun driver/libfprint core vi scrive un default
500 DPI (il commento di `fp_image_get_ppmm()` documenta solo che "è assunto
fisso a 500 ppi per la maggior parte dei driver", ma non è un valore impostato).

C. Consumatori downstream reali: NBIS sì; SIGFM no.

D. NBIS richiede `ppmm` semanticamente: SÌ. `fp_image_detect_minutiae_thread_func`
passa `data->ppmm` a `get_minutiae(...)` (`fp-image.c:370`); a valle
`combined_minutia_quality()` calcola `radius_pix = sround(RADIUS_MM * ppmm)`
(`nbis/mindtct/quality.c:236`). Il raggio di neighborhood per l'affidabilità
delle minuzie dipende quindi dalla risoluzione.

E. SIGFM usa o ignora `ppmm`: lo ignora. `fp_image_sigfm_extract_thread_func`
chiama `sigfm_extract(data->image, data->width, data->height)`
(`fp-image.c:315`): solo immagine, larghezza, altezza.

F. Default effettivo locale: `ppmm == 0.0` se il driver non lo imposta
(zero-init). Nessun default 500 DPI cablato in libfprint core.

G. Evidenza locale target-specific APP12509 per il valore fisico: **NESSUNA**.
L'unica assegnazione trovata nel corpus è `Rockytkg/src/goodixgf.c:281`
`fimg->ppmm = 500.0 / 25.4;`, con commento esplicito (righe 279-280) che il
ppmm è "solo per display" e che SIGFM è insensibile alla risoluzione. Nessuna
misura OEM, capture o dato target APP12509 fissa ppmm/DPI.

H. Il contratto pipeline può essere dichiarato chiuso? NO per il full pipeline:
`ppmm` è un prerequisito esplicito del prossimo boundary.

```text
LIBFPRINT_IMAGE_PPMM_FIELD=OBSERVED
FPIMAGE_PPMM_INITIAL_VALUE=0.0
FPIMAGE_PPMM_INITIALIZATION_PATH=NONE_IN_LIBFPRINT_CORE; DRIVER_WRITES_FIMG_PPMM_DIRECTLY
LIBFPRINT_NBIS_CONSUMES_PPMM=VERIFIED
NBIS_PPMM_CALLSITE=fp-image.c:370 -> get_minutiae -> combined_minutia_quality -> radius_pix=RADIUS_MM*ppmm
NBIS_PPMM_SEMANTIC_ROLE=resolution-scaled minutia reliability neighborhood radius
SIGFM_PPMM_CONSUMPTION=NO
ROCKYTKG_GOODIX_PPMM_500DPI=THIRD_PARTY_CORROBORATION
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
TARGET_PPMM_EVIDENCE_CLASS=UNKNOWN
PIXEL_REPRESENTATION_CONTRACT=CLOSED_OFFLINE
INTENSITY_QUANTIZATION_CONTRACT=CLOSED_OFFLINE
FULL_FPIMAGE_PIPELINE_CONTRACT=NOT_YET_CLOSED
NEXT_PRIMARY_BOUNDARY=LIBFPRINT_IMAGE_PIPELINE_INTEGRATION_OFFLINE
NEXT_BOUNDARY_PREREQUISITE=RESOLVE_OR_EXPLICITLY_BOUND_PPMM_SEMANTICS
```

## Verifica

- GCC C11 strict (`-Wall -Wextra -Werror -pedantic`): PASS.
- Unit/KAT sintetici da Git root: PASS.
- Stesso binario eseguito da `/tmp`: PASS.
- Oggetto adapter `nm -u`: nessun simbolo indefinito, quindi nessuna dipendenza I/O/runtime esterna: PASS.
- Regressioni `test_cleanroom`, `test_d267_04_image_no_check`, `test_d268_01_operator_kit`: 29/30 PASS.
  Osservazione residua (fuori scope corrective): `test_d268_01_operator_kit ::
  test_full_lowercase_sha_is_mandatory_and_dirty_tree_fails_closed` fallisce in
  questo ambiente (guard worktree-dirty non solleva); è pre-esistente, estraneo
  al corrective ppmm e all'adapter (byte-identico) e non viene corretto qui.
- `git diff --check`: PASS.
- ASan/UBSan: SKIP, runtime linker non installati; non necessario per la closure.

Le fixture sono gradienti e valori sintetici; nessun pixel o raster biometrico
reale è stato letto, scritto o incluso nel bundle.

## Prossimo boundary unico

```text
NEXT_PRIMARY_BOUNDARY=LIBFPRINT_IMAGE_PIPELINE_INTEGRATION_OFFLINE
NEXT_BOUNDARY_PREREQUISITE=RESOLVE_OR_EXPLICITLY_BOUND_PPMM_SEMANTICS
PIXEL_REPRESENTATION_CONTRACT=CLOSED_OFFLINE
INTENSITY_QUANTIZATION_CONTRACT=CLOSED_OFFLINE
FULL_FPIMAGE_PIPELINE_CONTRACT=NOT_YET_CLOSED
```

La prossima attività deve integrare il seam in un vero `FpImage` locale e
provare offline allocation/copy/lifetime e consegna alla pipeline rilevante.
Il full pipeline contract resta `NOT_YET_CLOSED` finché `FpImage::ppmm` non è
risolto con evidenza target-specific APP12509 o esplicitamente bound come
non risolto dal glue. Orientation/polarity e quality/preprocessing restano
rischi espliciti, ma non vengono risolti per supposizione in D269/01.
Enrollment/matcher e repeated capture non sono ancora il confine immediato.

```text
D268_RETRY_AUTHORIZED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```
