<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D270/01 — Libfprint FpImage pipeline integration offline

```text
OUTCOME=READY — D270_01_FPIMAGE_OBJECT_PIPELINE_PARTIALLY_CLOSED
ADVANCEMENT=REAL_LOCAL_FPIMAGE_CONSTRUCTION_AND_LIFETIME_VERIFIED_WITH_UNKNOWN_PPMM_FAIL_CLOSED
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=PPMM_ORIENTATION_POLARITY_AND_BIOMETRIC_QUALITY_UNRESOLVED;EXTRACTOR_NOT_SELECTED
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=analysis/D270/D270_01_libfprint_fpimage_pipeline_bundle.zip
BUNDLE_SHA256=SEE_EXTERNAL_SIDECAR
MODEL_USED=OPENAI_CODEX_GPT_5_FAMILY_EXACT_DEPLOYMENT_UNAVAILABLE
REASONING=HIGH
GIT_ROOT=/home/guido/Repository/goodix-27c6-5125_private
STARTING_HEAD=a2ef8e5c5888d4324aab9844139fbe9b269d67ad
FINAL_WORKTREE_STATUS=DIRTY_EXPECTED_D270_STEP_LOCAL_CHANGES_UNCOMMITTED
LIVE_EXECUTION=NOT_PERFORMED
REAL_USB_OPEN_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

## Baseline e scope

- Git root: `/home/guido/Repository/goodix-27c6-5125_private`.
- Branch: `development`.
- Starting HEAD: `a2ef8e5c5888d4324aab9844139fbe9b269d67ad`.
- Worktree iniziale: pulito.
- Modalità: `OFFLINE_ONLY`, fixture esclusivamente sintetiche.
- Nessun USB reale, secret, fprintd, sudo, capture biometrica, enrollment,
  matching, installazione o modifica della copia libfprint locale.
- Provenance libfprint: snapshot locale dichiarato 1.94.5, gitlink upstream
  `7ebe0c809b4d1df3400e84299a4ec4acdea84590`.

## Contratto FpImage locale verificato

L'oggetto reale è creato da `fp_image_new(width,height)`, che chiama
`g_object_new()` con proprietà construct-only. `fp_image_constructed()` alloca
con `g_malloc0(width*height)`. Il buffer è quindi posseduto dal GObject, non
copiato o preso in ownership dal caller. `fp_image_get_data()` restituisce
`transfer none`; `fp_image_finalize()` libera data, binarized e minutiae. Il
caller conserva il GObject attraverso il normale refcount e ne termina la vita
con `g_object_unref()`.

`width=80`, `height=64`, `data_length=5120`; non esiste stride nel tipo e tutti
i path locali usano righe packed, quindi lo stride implicito è 80. I default
reali da zero-initialization sono `flags=0`, `ppmm=0.0`, data inizialmente zero,
binarized/minutiae/SIGFM info null e campo interno `ref_count=0`;
`fp_image_init()` è vuoto. Il commento del getter sui 500 ppi non imposta alcun
default.

## Implementazione D270

`libfprint-driver/goodix_fpimage_pipeline.c` introduce un owner opaco LGPL. Il
constructor:

1. valida puntatori e count esatto;
2. alloca `FpImage(80,64)` tramite l'API locale reale;
3. passa direttamente `FpImage::data` al solo adapter D269;
4. verifica width, height, stride implicito, length, flags e stato orientation;
5. conserva l'unico riferimento GObject iniziale fino alla free.

Non esiste buffer pixel temporaneo né requisito di lifetime per l'input oltre
la chiamata. Il test usa un weak pointer GObject e verifica che la free
finalizzi davvero l'immagine. Nessuna formula D269 è stata modificata.

```text
PIXEL_REPRESENTATION_CONTRACT=CLOSED_OFFLINE
INTENSITY_QUANTIZATION_CONTRACT=CLOSED_OFFLINE
FPIMAGE_OBJECT_CONSTRUCTION=CLOSED_OFFLINE
FPIMAGE_BUFFER_OWNERSHIP=CLOSED_OFFLINE
FPIMAGE_DIMENSION_CONTRACT=CLOSED_OFFLINE
FPIMAGE_WIDTH=80
FPIMAGE_HEIGHT=64
FPIMAGE_PACKED_BYTES=5120
FPIMAGE_STRIDE=IMPLICIT_WIDTH_80
```

## Semantica bounded di ppmm

`FpImage` non dispone di un marker unknown e il core non valida `ppmm` prima
dei consumer. D270 non usa né `0.0` né `500/25.4` come misura. Lo zero storage
resta un dettaglio osservabile della zero-initialization; lo stato semantico
autorevole è separato nell'owner opaco:

```text
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
TARGET_PPMM_EVIDENCE_CLASS=UNKNOWN
UNKNOWN_PPMM_SEMANTICS=EXPLICITLY_BOUNDED
ROCKYTKG_GOODIX_PPMM_500DPI=THIRD_PARTY_CORROBORATION
```

Il call-flow locale NBIS copia `self->ppmm`, lo passa a `get_minutiae()` e usa
`radius_pix = sround(RADIUS_MM * ppmm)` nella quality. Non esistono assert,
fallback o default core che rendano semanticamente valido zero. Il gate D270
restituisce quindi `PHYSICAL_PPMM_REQUIRED` per NBIS.

SIGFM copia solo `width*height` pixel e passa image/width/height a
`sigfm_extract()`. Il gate restituisce OK per il solo requisito ppmm, ma ciò non
seleziona SIGFM e non autorizza feature extraction, matching o enrollment.

## Matrice downstream

| Livello | Consuma ppmm | Eseguibile con unknown | Risultato semanticamente valido | Gate D270 |
| --- | --- | --- | --- | --- |
| FpImage construction | no | sì, eseguito | sì, per oggetto/rappresentazione | PASS |
| preprocessing bounded D269 | no | sì, eseguito | sì, solo mapping fixed | PASS |
| SIGFM extraction | no, verificato | tecnicamente sì | non validato/né selezionato | STOP prima dell'uso feature |
| NBIS minutiae/quality | sì, verificato | non autorizzato | no con ppmm ignoto | BLOCKED |
| feature extraction | algorithm-dependent | non chiuso | non dimostrato | BLOCKED oltre i soli gate extractor |
| matching | non direttamente dopo feature valide | non autorizzato | non dimostrato | BLOCKED |
| enrollment | dipende da extraction/matching | non autorizzato | non dimostrato | BLOCKED |

La matrice machine-readable è in
`analysis/D270/D270_01_downstream_matrix.json`.

## Orientation, polarity e preprocessing

```text
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
FPIMAGE_FLAGS=0
```

Zero flags significa solo assenza di trasformazioni giustificate. D270 non
introduce flip, rotate, transpose, inversione, auto-orientation, min/max,
percentili o altre normalizzazioni frame-local. La transpose wire→raster già
chiusa resta distinta dalla natural fingerprint orientation.

## Verifica eseguibile

Il runner usa l'SDK Flatpak locale `org.freedesktop.Sdk//25.08`, esplicitamente
senza rete, perché l'host non espone header GLib tramite pkg-config. Compila
l'esatto `Rockytkg/libfprint/libfprint/fp-image.c`; gli stub test-only servono
solo a risolvere i simboli degli extractor e abortiscono se attraversati.

- build strict del nuovo codice: PASS;
- vero FpImage, 80×64/5120, KAT D269 e input immutato: PASS;
- ownership e weak-finalization: PASS;
- invalid count/null/sample oltre 4095 e output owner invariato: PASS;
- determinismo e frame-content independence: PASS;
- gate NBIS fail-closed / gate ppmm SIGFM: PASS;
- audit simboli I/O/USB/TLS vietati nel production helper: PASS;
- ASan/UBSan: PASS;
- run da Git root: PASS;
- run da `/tmp`: PASS;
- regressione adapter D269 strict: PASS;
- allocation fault injection interna a `fp_image_new()`: NOT_AVAILABLE
  (GLib abort-on-OOM; non è stato introdotto un allocator globale di test).

## Closure

```text
FPIMAGE_OBJECT_CONSTRUCTION=CLOSED_OFFLINE
FPIMAGE_BUFFER_OWNERSHIP=CLOSED_OFFLINE
FPIMAGE_DIMENSION_CONTRACT=CLOSED_OFFLINE
NBIS_PPMM_REQUIREMENT=REQUIRED_VERIFIED
NBIS_WITH_UNKNOWN_PPMM=BLOCKED
SIGFM_PPMM_REQUIREMENT=NOT_CONSUMED_VERIFIED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
NEXT_PRIMARY_BOUNDARY=LIBFPRINT_FEATURE_EXTRACTION_POLICY_OFFLINE
NEXT_BOUNDARY_PREREQUISITE=TARGET_EVIDENCE_OR_EXPLICIT_BOUNDS_FOR_ORIENTATION_POLARITY_PPMM_AND_BIOMETRIC_QUALITY
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
```
