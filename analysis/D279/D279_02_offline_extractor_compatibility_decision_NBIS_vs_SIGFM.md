<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/02 — decisione offline di compatibilità extractor NBIS vs SIGFM

## Aggiornamento D279/48 — esperimento discriminante pronto al gate

D279/48 ha chiuso offline l'evaluator richiesto senza cambiare la selection
production. R1 compila direttamente il preprocessing comune Rockytkg
preservato; R2 aggiunge soltanto il suo enhancement SIGFM-specifico. A ogni
checkpoint NBIS e SIGFM ricevono lo stesso raster nativo 80×64 e producono
solo aggregati di feature, gate e score same-session bidirezionali.

La decisione biometrica resta aperta fino a una singola valutazione protetta
ATTEMPT02 e alla successiva classificazione A/B/C/D. In particolare, la
presenza tecnica di SIGFM/OpenCV nel comparator host-only non costituisce una
selezione production o un'autorizzazione a trasferire codice GPL nel driver
LGPL.

```text
NBIS_PIPELINE_COMPATIBLE=true
NBIS_BIOMETRIC_SUITABILITY=CHALLENGED_BY_TARGET_EVIDENCE_PENDING_CONTROLLED_COMPARISON
EXTRACTOR_DECISION=UNDER_BIOMETRIC_REVIEW_ARCHITECTURAL_BASELINE_NBIS_UNCHANGED
D279_48_COMPARISON_EXECUTABLE_CLOSURE=PASS_OFFLINE
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
```

## Aggiornamento D279/47 — suitability biometrica riaperta

La decisione storica sotto resta valida come scelta architetturale basata sul
target Fedora 44/libfprint 1.94.100: NBIS è strutturalmente compatibile e
SIGFM richiede un fork. D279/29 e D279/39–46 aggiungono però evidenza autentica
che D279/02 non possedeva: sui frammenti APP12509 80×64 il path live non trova
minutiae e i migliori preprocessori controllati restano troppo poveri per
provare Bozorth/enrollment robusti.

La suitability biometrica NBIS è quindi formalmente riaperta, senza dichiarare
NBIS inadatto e senza selezionare SIGFM. Il prossimo boundary confronta NBIS e
SIGFM sugli stessi raster prodotti dai checkpoint R1/R2 della pipeline
Rockytkg preservata, senza tuning e con output aggregate-only.

```text
NBIS_PIPELINE_COMPATIBLE=true
NBIS_BIOMETRICALLY_VALIDATED=false
NBIS_BIOMETRIC_SUITABILITY=CHALLENGED_BY_TARGET_EVIDENCE_PENDING_CONTROLLED_COMPARISON
EXTRACTOR_DECISION=UNDER_BIOMETRIC_REVIEW_ARCHITECTURAL_BASELINE_NBIS_UNCHANGED
```

## Esito

```text
D279_02_OUTCOME=READY
EXTRACTOR_DECISION=NBIS
DECISION_CLASS=ARCHITECTURAL_TECHNICAL
NBIS_PIPELINE_COMPATIBLE=true
NBIS_BIOMETRICALLY_VALIDATED=false
SIGFM_PIPELINE_COMPATIBLE=false
SIGFM_BIOMETRICALLY_VALIDATED=false
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
PPMM_EVIDENCE_CLASS=UNKNOWN
NBIS_80X64_COMPATIBILITY=CONDITIONAL
BIOMETRIC_VALIDATION_PENDING=true
EXECUTABLE_CLOSURE=NOT_APPLICABLE
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
```

La decisione è architetturale/tecnica sul target production Fedora 44 /
libfprint 1.94.100. Non prova accuratezza biometrica, FAR/FRR, qualità di
enrollment o matcher performance.

## 1. Baseline e sorgenti ispezionati

```text
REPOSITORY=sorguido/goodix-27c6-5125-private
BRANCH=main
D279_02_BASELINE=924774e9bd7ea10eabdfd540bf8a4be9b8413c99
WORKING_BRANCH=main
initial_worktree=CLEAN
TARGET_OS=Fedora_44_x86_64
TARGET_LIBFPRINT_VERSION=1.94.100
TARGET_LIBFPRINT_PACKAGE=libfprint-1.94.100-1.fc44.x86_64
TARGET_LIBFPRINT_REFERENCE=reference/libfprint-fedora44-1.94.100/source
ROCKYTKG_LIBFPRINT_IS_PRODUCTION_TARGET=false
D278_14_CLOSED_LIVE=true
D279_01_OUTCOME=BLOCKED
CURRENT_LIVE_AUTHORIZED=false
```

La baseline coincide con `EXPECTED_HEAD` del prompt. D278/14 non è stata
riaperta. D279/01 resta storicamente `BLOCKED` sulla registrazione USB; questo
step chiude soltanto il boundary extractor.

Sorgenti primarie:

- `reference/libfprint-fedora44-1.94.100/source` (upstream v1.94.100, nessuna
  patch Fedora attiva; `PROVENANCE.md`)
- `libfprint-driver/` (classe Goodix corrente)
- `Rockytkg/` (snapshot storico; non target production; clean-room: struttura e
  intent, nessun port)
- `analysis/D279/D279_01_...md`, `analysis/D271/D271_01_...md`
- sezioni canoniche del manuale su D269–D271, D278/14, D279/01

## 2. Dataset pre-auditato

Nessuna evidenza contraria è emersa. I marker restano:

```text
TARGET_REAL_GOODIX_ACQUISITIONS_EXIST=true
TARGET_REAL_DECODED_RASTER_DATASET_IN_MAIN=false
LABELED_SAME_FINGER_DATASET_AVAILABLE=false
LABELED_DIFFERENT_FINGER_DATASET_AVAILABLE=false
BIOMETRIC_MATCHER_BENCHMARK_READY=false
DATASET_STATE_CHANGED=false
```

D274/03 non esporta raster biometrici. D255 non è un dataset decodificato
etichettato. I raster live D278/14 non sono persistiti su `main` come immagini
riusabili.

## 3. Contratto NBIS in libfprint 1.94.100 e uso di `ppmm`

### Call-flow (stadi scale-dependent marcati)

```text
Goodix decoded raster 80x64 u8
  → FpImage (fp_image_new; ppmm=0.0 di default GObject; flags driver)
  → fpi_image_device_image_captured()          fpi-image-device.c:469-488
  → fp_image_detect_minutiae()                 fp-image.c:461
  → thread: hflip/vflip/invert flags           fp-image.c:308-316
  → get_minutiae(..., ppmm)                    getmin.c:99-175
       → lfs_detect_minutiae_V2()              SCALE-INDEPENDENT (pixel)
       → gen_quality_map()                     SCALE-INDEPENDENT
       → combined_minutia_quality(ppmm)        SCALE-DEPENDENT (solo quality)
  → FpImage->minutiae
  → fpi_print_set_type(FPI_PRINT_NBIS)         fpi-image-device.c:285
  → fpi_print_add_from_image()
       → minutiae_to_xyt() → lfs2nist_minutia_XYT()
         coordinate in pixel, y-flip; reliability calcolata e poi scartata
  → fpi_print_bz3_match() → bozorth_to_gallery()
         XYT pixel; soglia default 40; MIN_COMPUTABLE_BOZORTH_MINUTIAE=10
```

### Dove `ppmm` è consumato

Unico sito NBIS: `combined_minutia_quality()` in
`nbis/mindtct/quality.c:236`:

```text
radius_pix = sround(RADIUS_MM * ppmm)
RADIUS_MM = 11.0 / 19.69    # lfs.h:635
```

Effetto concreto: dimensione del vicinato per la reliability in scala di grigi.
Non entra in binarizzazione, mappe di direzione, detection, geometria XYT o
Bozorth3.

In `fpi-print.c:119-153`, `minutiae_to_xyt()` calcola
`c[i].col[3] = sround(minutia->reliability * 100.0)` e poi copia solo
`x, y, theta` nel `xyt_struct`. C'è un commento XXX che osserva che la quality
non viene usata per selezionare le minutiae. Bozorth3 non ha un campo quality.

`fp_image_new()` non assegna `ppmm`; resta `0.0` per zero-init
(`fp-image.c:50-57, 157-159`). Il commento di `fp_image_get_ppmm()`
(`fp-image.c:385-388`) parla di 500 DPI per “most drivers”: è prosa, non
enforcement. `DEFAULT_PPI 500` in `lfs.h:277-279` non è referenziato nel
call-flow libfprint. L'unico driver upstream che assegna `ppmm` è
`secugen.c:1682` (`19.685`). Tutti gli altri lasciano `0.0`.

Comportamento `ppmm=0.0`: `get_minutiae()` non valida il campo; `radius_pix=0`;
il vicinato collassa a un pixel; la reliability in scala di grigi è 0; restano
solo i gradi della quality map. L'estrazione non abortisce.

Nessuno scaling interno nel core. Alcuni driver upsamplano in proprio
(vfs7552 2×, aes4000 3×, aes3500 2×): workaround driver-local, non contratto
framework.

### Risposte contrattuali

```text
NBIS_REQUIRES_PPMM_FIELD_FOR_EXECUTION=false
NBIS_REQUIRES_ACCURATE_PHYSICAL_PPMM_FOR_EXTRACTION=false
NBIS_REQUIRES_ACCURATE_PHYSICAL_PPMM_FOR_QUALITY=true
NBIS_REQUIRES_ACCURATE_PHYSICAL_PPMM_FOR_MINUTIAE_GEOMETRY=false
NBIS_REQUIRES_ACCURATE_PHYSICAL_PPMM_FOR_MATCHING=false
LIBFPRINT_CANONICAL_DEFAULT_OR_FALLBACK_PPMM=none
```

Matching: Bozorth3 è su coordinate pixel. Con `ppmm` identico (anche `0.0`) tra
enroll e probe, la geometria relativa è coerente. `true` per la quality
significa soltanto il raggio del vicinato, campo poi scartato prima del matcher.

Il gate locale D270/D271
`goodix_fpimage_pipeline_check_ppmm_requirement(... NBIS) → PHYSICAL_PPMM_REQUIRED`
è una policy di progetto, non un requisito hard di libfprint 1.94.100. D279/02
la supersede come blocker architetturale. Non è modificata in questo step.

## 4. Scala fisica APP12509

```text
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
PPMM_EVIDENCE_CLASS=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
```

Candidati esaminati:

| Sorgente | Valore | Classe |
|---|---|---|
| manuale canonico / D269–D271 | UNKNOWN | OBSERVED (stato di progetto) |
| `Rockytkg/src/goodixgf.c:281` `500.0/25.4` | ~19.685 | HYPOTHESIZED / THIRD_PARTY; commento “ppmm solo per display”; ridge-spacing 9–10 px ivi citato è stima visiva, non prova target |
| geometria ChicagoHS 80×64 | pixel count | VERIFIED per i pixel, UNKNOWN per il pitch |
| commento `fp_image_get_ppmm` / `DEFAULT_PPI 500` | convenzione 500 DPI | INFERRED, non target-specific |
| OTP/FDT/OEM cache D255, metadata D274/03 | framing/process | OBSERVED, nessun pitch |
| ricerca esterna GF_ST411SEC_APP_12509 / 27c6:5125 | nessun datasheet pitch/DPI | UNKNOWN; un report TechInsights 7.45 µm riguarda un die in-display, non questo sensore |

Nessun valore è stato inventato né derivato da ridge spacing, dita umane o
medie di popolazione.

## 5. Viabilità tecnica 80×64

Hard minimum NBIS: `MAP_BLOCKSIZE_V2=8` (`lfs.h:326`); `block_offsets()`
rifiuta solo `iw < 8` o `ih < 8` (`block.c:111-116`). 80×64 supera il limite
(10×8 blocchi). Window 24, offset 8.

Bozorth3 richiede ≥10 minutiae per uno score non zero (`bozorth.h:122`).
`fp_image_detect_minutiae` fallisce se `num == 0` (`fp-image.c:342-346`), ma
non impone 10 prima del template.

`FPI_IMAGE_PARTIAL` attiverebbe `remove_perimeter_pts` (fascia 10 px): su
80×64 sarebbe distruttivo. Il frame Goodix è un press completo, non uno swipe
fragment; `PARTIAL` è UNPROVEN e non va impostato.

Comparatori upstream (area statica, non swipe):

| Driver | Raster nativo | ppmm | Trasformazione | Comparabile? |
|---|---|---|---|---|
| vfs7552 | 112×112 | 0.0 | upsample 2× → 224×224 | più vicino; comunque upsampla |
| aes4000 | 96×96 press | 0.0 | enlarge 3× | press-type; upsampla |
| aes3500 | analogo | 0.0 | enlarge 2× | analogo |
| secugen | 300×400 (da 956×688) | 19.685 | flip H/V | non comparabile (molto più grande) |
| elan | 144×64 / 96×96 | 0.0 | swipe assembly | commento noto su NBIS e immagini piccole; modello di acquisizione diverso |

Nessun `FpImageDevice` upstream consegna un'area statica 80×64 senza upsample.
Questo non è un rifiuto strutturale del core. L'upsample altrui è enhancement
driver-local, non meccanismo standard per scala ignota.

```text
NBIS_80X64_COMPATIBILITY=CONDITIONAL
```

Strutturalmente accettato; informazionalmente povero; usabilità biometrica
target non provata. Non incompatibile.

## 6. Audit adattamenti immagine

Semantica Goodix corrente (live-proven decode, non da alterare):

```text
width=80  height=64
depth_wire=u16_12bit_0_4095
adapter=round(v*255/4095) → u8
row_major dopo transpose column-major wire
flags=0
ppmm unset / PHYSICAL_PPMM_UNKNOWN
crop=none  pad=none
orientation=canonical_preserved, natural_unresolved
polarity=unresolved
contrast=nessuna normalizzazione per-frame
```

| Trasformazione | Classificazione |
|---|---|
| impostare `ppmm` target-specific | REQUIRED_BY_UPSTREAM_CONVENTION se si volesse quality corretta; BLOCKED_BY_UNKNOWN_VALUE; non necessario per extract/match |
| H_FLIP / V_FLIP | UNPROVEN |
| COLORS_INVERTED | UNPROVEN; Windows `AlgoChicago` consuma u16 senza inversione; Rockytkg inverte per SIGFM, non è prova APP12509 |
| FPI_IMAGE_PARTIAL | UNPROVEN (press completo) |
| crop | UNPROVEN |
| contrast / unsharp / percentile (GPL Rockytkg imgproc) | LIKELY_BIOMETRIC_ENHANCEMENT, UNPROVEN sul target; non copiare |
| resampling / upsample | UNPROVEN; inventerebbe scala |
| rotazione extra | UNPROVEN; il transpose wire→raster è già REQUIRED_BY_FORMAT |

NBIS, dopo i flag, assume ridge scure su fondo chiaro (`detect.c` commento
0=ridge). Con flags=0 si consegna il raster canonico. Polarità resta unresolved
e non va inventata.

## 7. Razionale storico SIGFM

SIGFM entra nel fork Rockytkg (`libfprint/sigfm/`, `FPI_DEVICE_ALGO_SIGFM`,
`FPI_PRINT_SIGFM`), non in upstream. La classe locale la copia in
`libfprint-driver/goodix_fpimage_device.c:786`.

Motivazioni documentate nel fork:

1. raster 80×64 troppo piccolo per un singolo print (`goodixgf.c:35-38, 507-510`);
2. commento elan.c: NBIS “doesn't like small images”;
3. SIFT dichiarato insensibile a scala/rotazione; `ppmm` “solo display”;
4. preprocessing GPL unsharp perché i keypoint su 80×64 sono pochi.

```text
SIGFM_ORIGINAL_SELECTION_REASON=PARTIALLY_VERIFIED
SIGFM_TARGET_SPECIFIC_NECESSITY=NOT_PROVEN
```

Le limitazioni NBIS citate (immagini piccole, quality-radius `ppmm`) sono
documentate in generale. Non è provato che su APP12509 NBIS sia inutilizzabile,
né che SIGFM sia necessario. Il fork storico è fonte implementativa, non prova
target-specific.

SIGFM ignora `FpImage::ppmm` e i flag di orientation/polarity; richiede
OpenCV/C++, serializza keypoint nel print, è accoppiato a enroll multi-stage e
a un preprocessing GPL che questo progetto non ha importato nel dominio LGPL.

## 8. Delta minimo SIGFM su 1.94.100

```text
SIGFM_CAN_BE_DRIVER_LOCAL_ONLY=false
SIGFM_REQUIRES_MAINTAINED_LIBFPRINT_FORK=true
SIGFM_MINIMUM_DELTA_SUMMARY=Preserving SIGFM on Fedora 44 libfprint 1.94.100 requires patching the upstream core: SIGFM print/device types and algorithm selector, FpImage/FpPrint extraction matching equality and FP3 serialization, C++ OpenCV implementation, Meson and packaging. The Goodix driver change is one line and cannot be isolated.
```

| Area | Classificazione |
|---|---|
| `FpiPrintType` + `FPI_PRINT_SIGFM` | LIBFPRINT_PRIVATE_CORE + PUBLIC_API_OR_ABI |
| `FpImageDeviceClass.algorithm` | LIBFPRINT_PRIVATE_CORE + PUBLIC_API_OR_ABI |
| branch in `image_captured` / minutiae_detected | LIBFPRINT_PRIVATE_CORE |
| `SigfmImgInfo` su `FpImage` + API extract | LIBFPRINT_PRIVATE_CORE + PUBLIC_API_OR_ABI |
| `fpi_print_sigfm_match` | LIBFPRINT_PRIVATE_CORE |
| serialize/deserialize/equal FP3 | LIBFPRINT_PRIVATE_CORE + DATA_FORMAT_COMPATIBILITY |
| Meson `subdir(sigfm)` + C++ | BUILD_SYSTEM |
| `dependency('opencv4')` | NEW_DEPENDENCY + PACKAGING |
| SONAME `libfprint-2.so.2` con struct size change | PUBLIC_API_OR_ABI |
| fprintd via serialize/equal | DATA_FORMAT_COMPATIBILITY |
| manutenzione ad ogni update Fedora | PACKAGING |

Clean-room: nessun codice SIGFM è stato copiato o portato in questo step.

## 9. Matrice di decisione

| Criterio | NBIS | SIGFM |
|---|---|---|
| Nativo in Fedora 44 libfprint 1.94.100 | sì | no |
| Evidenza target-specific sufficiente per l'architettura | sì (contratto sorgente) | no necessità target-proven |
| Delta dipendenze | zero | OpenCV4 + libstdc++ |
| Modifiche al core libfprint | nessuna | estese (tipi, extract, match, ABI) |
| Compatibilità fprintd | path nativo `FPI_PRINT_NBIS` | richiede serialize/equal nuovi |
| Serializzazione/storage | formato NBIS esistente | nuovo payload FP3 |
| Manutenzione | allineata a Fedora | fork permanente |
| Upstreamability | alta | bassa (SIGFM mai in 1.94.100) |
| Assunzioni biometriche nascoste | non inventare `ppmm`; flags=0 | preprocessing GPL storico, threshold 20, gate 25 keypoint |
| Idoneità 80×64 | strutturale sì; biometrica unproven | fork: architetturalmente sì; target unproven |
| `ppmm` verificato necessario? | no per extract/match | no |
| Testabilità host-only prima del live | sì (contratto già tracciato) | solo sul fork, non sul target |
| Benchmark biometrico empirico | NO | NO |

Principio applicato: preferire il path nativo a delta minore se la correttezza
tecnica non richiede parametri target inventati. Preferire SIGFM solo se NBIS
è inidoneo o SIGFM è materialmente necessario. Manca il benchmark, ma non è un
blocker architetturale.

## 10. Test host-only

```text
HOST_ONLY_NBIS_RUNTIME_TEST=NOT_RUN
REASON=libfprint-devel_and_glib2-devel_not_installed;_mindtct_in_tree_requires_glib;_source_contract_already_determines_execution_ppmm_and_size_acceptance
```

Il runtime `libfprint-1.94.100-1.fc44.x86_64` è installato; i simboli
`fp_image_new` / `fp_image_detect_minutiae` sono esportati. Senza header non è
stato costruito un harness. Un fixture sintetico 80×64 avrebbe potuto provare
solo `API_ACCEPTANCE` / `SIZE_CONSTRAINT` / `PPMM_HANDLING`, già coperti dal
sorgente (`block_offsets` ≥8, `get_minutiae` senza check su `ppmm`). Non è
stato creato un test cerimoniale.

Nessun raster biometrico reale è stato creato o committato.

## 11. Compatibilità pipeline vs validazione biometrica

```text
NBIS_PIPELINE_COMPATIBLE=true
NBIS_BIOMETRICALLY_VALIDATED=false
SIGFM_PIPELINE_COMPATIBLE=false
SIGFM_BIOMETRICALLY_VALIDATED=false
```

`NBIS_PIPELINE_COMPATIBLE=true` significa: il path nativo 1.94.100 accetta
strutturalmente 80×64, esegue senza `ppmm` fisico, e matching/enroll usano XYT
pixel. Non significa matcher accurato.

`SIGFM_PIPELINE_COMPATIBLE=false` è relativo al target production 1.94.100
(API/core assenti). Sul fork storico l'algoritmo può consumare 80×64 senza
`ppmm`; quel fork non è il target.

```text
DECISION_CLASS=ARCHITECTURAL_TECHNICAL
BIOMETRIC_ACCURACY_PROVEN=false
BIOMETRIC_VALIDATION_PENDING=true
```

## 12. Incertezze residue

- densità di minutiae NBIS su raster APP12509 reali (≥10 per Bozorth)
- polarità ridge/valley e orientation naturale
- quality map / edge effects su 10×8 blocchi
- soglia `bz3_threshold` default 40 vs. geometria piccola
- eventuale beneficio (non requisito) di un upsample futuro, solo dopo evidenza
- il gate locale `PHYSICAL_PPMM_REQUIRED` per NBIS è ora inconsistente con il
  contratto 1.94.100 e va riallineato nello step implementativo successivo,
  senza assegnare un `ppmm` inventato

## 13. Piano minimo di evidenza biometrica futura

Piano di evidenza soltanto. Non autorizza live, non prepara kit, non richiede
esecuzione immediata.

```text
NUMBER_OF_DISTINCT_FINGERS=5
ACQUISITIONS_PER_FINGER=8
TOTAL_ACQUISITIONS=40
LABEL_SCHEMA=finger_id,acquisition_index,session_id,placement_note,pressure_note
RASTER_FORMAT=canonical_u16_plus_adapter_u8
WIDTH_HEIGHT=80x64
BIT_DEPTH=u16_12bit_and_u8_mapped
ORIENTATION_METADATA=as_captured_canonical_no_extra_transform
PPMM_METADATA_REQUIREMENT=unset_UNKNOWN_do_not_invent
ACQUISITION_CONDITIONS_TO_KEEP_CONSTANT=decoder,adapter_linear,flags=0,no_imgproc
ACQUISITION_CONDITIONS_TO_VARY=placement,repositioning,light_vs_firm_pressure
SAME_FINGER_COMPARISONS=C(8,2)*5=140
DIFFERENT_FINGER_COMPARISONS=all_cross_finger_pairs
SCORES_OR_METRICS_TO_COLLECT=nbis_minutiae_count,bz3_raw_score,quality_map_histogram,enroll_stage_accept,zero_score_rate
PASS_FAIL_INTERPRETATION=architectural_smoke_only;_same_finger_scores_should_exceed_bz3_threshold_more_often_than_different_finger;_not_a_FAR_FRR_certification
CURRENT_LIVE_AUTHORIZED=false
```

## 14. Decisione

```text
EXTRACTOR_DECISION=NBIS
DECISION_CLASS=ARCHITECTURAL_TECHNICAL
NBIS_BIOMETRICALLY_VALIDATED=false
```

Motivi, in ordine:

1. Il path immagine 1.94.100 è NBIS-only, verificato in D279/01 e ritracciato
   qui.
2. `ppmm` fisico accurato non è richiesto per estrazione né matching; non si
   inventa un valore APP12509.
3. 80×64 non è strutturalmente incompatibile.
4. Gli adattamenti richiesti sono bounded: consegnare il raster canonico con
   flags=0 e `ppmm` unset.
5. SIGFM non è necessità target-proven e imporrebbe un fork core + OpenCV.
6. L'assenza di benchmark same/different-finger non è un blocker
   architetturale.

Il gate D269–D271 `NBIS_WITH_UNKNOWN_PPMM=BLOCKED` resta vero come
constatazione che la quality radius non è fisicamente calibrata. Cessa di
essere un veto architetturale sul path production 1.94.100.

## 15. Prossimo passo tecnico minimo (non implementato qui)

Adattare la classe Goodix esistente all'API NBIS-only 1.94.100: non impostare
`FPI_DEVICE_ALGO_SIGFM`, registrare `27c6:5125` nel registry standard,
lasciare `ppmm` unset, preservare il decode D278/14, riallineare il gate locale
ppmm/NBIS al contratto qui ricostruito. Nessun live, nessun fprintd, nessun
cambio protocollo.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_FEDORA44_LIBFPRINT_1_94_100_PRODUCTION_USB_DRIVER_REGISTRATION_WITH_NBIS
```

## Safety

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
D278_14_RERUN_REQUIRED=false
PRODUCTION_USB_ID_27C6_5125_REGISTERED=false
```
