# D271/01 — Libfprint feature-extraction policy offline

## Esito

```text
OUTCOME=READY — D271_01_FEATURE_EXTRACTION_POLICY_CLOSED_OFFLINE
ADVANCEMENT=ARCHITECTURAL_NON_HARDWARE_LIBFPRINT_EXTRACTOR_POLICY_CLOSED_WITH_PRECISE_VALIDATION_BOUNDARY
EXECUTABLE_CLOSURE=NOT_APPLICABLE
FEATURE_EXTRACTOR_POLICY=CLOSED_OFFLINE
SIGFM_STATUS=CANDIDATE_FOR_VALIDATION
NBIS_STATUS=BLOCKED_UNKNOWN_PHYSICAL_PPMM_AND_TARGET_LOCAL_MINUTIA_DENSITY_UNPROVEN
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
```

D271/01 chiude una policy architetturale offline, non prova una pipeline
biometrica. SIGFM è l'unico candidato tecnicamente candidabile alla prossima
validazione perché il call-flow locale accetta il raster `80x64`, non richiede
`ppmm`, possiede un gate di qualità esplicito e dispone di corroborazione terza
parte sulla stessa geometria. Non è selezionato per produzione. NBIS resta
bloccato: `80x64` supera il suo minimo strutturale, ma il `ppmm` fisico è ignoto
e non è provato che la geometria target produca le almeno 10 minutiae richieste
da Bozorth per uno score non nullo.

## Baseline e confini

- Git root: `/home/guido/Repository/goodix-27c6-5125_private`.
- Branch iniziale: `development`.
- HEAD iniziale: `3e9a2a5b71669ffba12889f65a06fa2a2f6aa096`.
- D270 ancestor check: `PASS` (`HEAD` coincide con il commit D270 approvato).
- Worktree iniziale: pulito.
- Fonte API/software: `Rockytkg/libfprint`, versione dichiarata `1.94.5`,
  gitlink materializzato `7ebe0c809b4d1df3400e84299a4ec4acdea84590`.
- Provenance Rockytkg: commit snapshot
  `227eba219fa9e3fbac5bd59aca79f624f67cd11b`.
- Modalità: `OFFLINE_ONLY`; zero USB, fprintd, secret, capture nuova o
  decrittazione biometrica.

Non è stato aggiunto o modificato codice eseguibile. Gli output sono report,
JSON, manuale canonico e bundle step-local; quindi
`EXECUTABLE_CLOSURE=NOT_APPLICABLE`.

## Call-flow locale ricostruito

| Passaggio | Callsite locale | Input e metadata | Ownership/lifetime | Failure/requisiti |
| --- | --- | --- | --- | --- |
| costruzione | `fp-image.c:51-78` | width, height; `width*height` u8 | `FpImage` possiede `data` | allocazione GLib; nessuno stride |
| ingresso device | `fpi-image-device.c:497-528` | `FpImage`, algoritmo di classe | il callback asincrono riceve una ref | stato deve essere CAPTURE e action valida |
| scelta extractor | `fpi-image-device.c:515-527`; `fp-image-device.c:183-195` | default NBIS o override SIGFM | copia per task | SIGFM solo se algoritmo esatto |
| NBIS preprocessing | `fp-image.c:331-370,550-569` | copia u8, width, height, flags, ppmm | task possiede copia e output temporanei | applica H/V/invert; depth 8; `get_minutiae` |
| SIGFM extraction | `fp-image.c:307-328,521-538`; `sigfm.cpp:117-130` | copia u8, width, height; niente flags/ppmm | task → `FpImage::sigfm_info` | SIFT/OpenCV; failure se keypoint `<25` |
| feature → print | `fpi-print.c:153-212` | minutiae o `SigfmImgInfo` | NBIS copia in XYT; SIGFM passa il puntatore all'array owning del print | feature deve esistere |
| enrollment | `fpi-image-device.c:295-318`; `fpi-print.c:46-64` | un print per stage | copia XYT/SIGFM nel template multi-stage | base: 5 stage; retry non incrementa |
| verify | `fpi-image-device.c:320-344` | template + singolo probe | temporanei GObject | BZ3 o SIGFM secondo algorithm |
| identify | `fpi-image-device.c:345-375` | gallery + singolo probe | come verify | primo template sopra soglia |
| NBIS matcher | `fpi-print.c:230-268`; `bozorth3.c:642-671` | XYT, max 200 minutiae | template-owned | score 0 con `<10` minutiae; threshold driver |
| SIGFM matcher | `fpi-print.c:285-313`; `sigfm.cpp:132-213` | keypoint + descrittori | template-owned | errore negativo su eccezione; threshold driver |
| persistenza template | `fp-print.c:637-770,773-958` | `FP3` GVariant | buffer serializzato owned dal caller | SIGFM salva keypoint+descriptor; deserialize fail-closed |

### Nota di lifetime SIGFM

Il callback di extraction sposta `SigfmImgInfo` dal task nel `FpImage`, poi
`fpi_print_add_from_image()` inserisce lo stesso puntatore nell'array owning del
`FpPrint`, senza copy/clear esplicito. `FpImage::finalize()` non libera
`sigfm_info`; l'array del print usa `sigfm_free_info`. Il percorso principale
una-extraction/una-addizione è coerente e il print trattiene una reference
all'immagine, ma il trasferimento è implicito: riutilizzare lo stesso
`FpImage::sigfm_info` in più print non è dimostrato sicuro e va mantenuto fuori
dal futuro contract.

## Audit SIGFM

### Input, algoritmo e metadata

`sigfm_extract()` crea una `cv::Mat(height,width,CV_8UC1)`, copia esattamente
`width*height` byte, crea una mask tutta uno e chiama
`cv::SIFT::create()->detectAndCompute()`. Non applica resize, contrast
normalization, polarity conversion o `FpImage::flags`; non riceve `ppmm`.

L'output `SigfmImgInfo` contiene `std::vector<cv::KeyPoint>` e `cv::Mat`
descrittori. Il wrapper libfprint richiede almeno 25 keypoint. Non esiste un
minimo width/height esplicito nel glue SIGFM; `80x64` è quindi
`ARCHITECTURALLY_SUPPORTED`, ma l'esito del gate dipende dal contenuto e non è
provato dal solo shape.

### Matcher e score

Il matcher:

1. usa `BFMatcher::knnMatch(..., k=2)`;
2. applica ratio test `0.75`;
3. restituisce 0 se i match descrittore sono meno di 5;
4. accetta coppie di match la cui lunghezza relativa differisce al massimo di
   circa `0.05`;
5. conta coppie di trasformazioni angolari coerenti entro circa `0.05`.

Lo score è quel conteggio finale, non una probabilità. Il default generico
`FpImageDevice` è 40; Rockytkg imposta 20. Il 20 è
`THIRD_PARTY_IMPLEMENTATION_CHOICE`, non threshold APP12509 locale.

### Orientation, scale e polarity

- rotation: il matcher codifica una coerenza di rotazione rigida, ma non vi è
  un test locale di rotazione e il calcolo non prova invarianza generale;
- scale: SIFT usa scale-space, ma il matcher geometrico accetta soltanto circa
  il 5% di variazione nelle distanze; `SCALE_INVARIANCE=NOT_PROVEN`;
- orientation flags: ignorati completamente da SIGFM;
- polarity: nessuna inversione o doppia estrazione; non provata irrilevanza;
- natural orientation: non necessaria per accettare byte coerenti, ma stabilità
  inter-capture e tolleranza restano da validare.

I test SIGFM locali (`sigfm/tests.cpp`) coprono principalmente round-trip
binario e usano una fixture 256×256; non provano 80×64, soglie, rotation, scale
o polarity.

Failure modes osservati: il wrapper trasforma `<25` keypoint in errore GIO e il
base image-device in retry generico; il matcher cattura eccezioni e restituisce
`-1`, poi convertito in `FP_DEVICE_ERROR_DATA_INVALID`; meno di 5 match produce
score 0; la deserializzazione cattura eccezioni e restituisce NULL. Al contrario
`sigfm_extract()` non ha un proprio `try/catch` o controllo NULL intorno a SIFT:
un'eccezione OpenCV in extraction non è contenuta dal codice SIGFM locale. Anche
`fp_print_equal()` non implementa il tipo SIGFM e raggiunge un assert: non è il
matcher verify/identify, ma resta un limite del fork da non confondere con una
pipeline production-ready.

### Enrollment

Il template contiene una struttura SIGFM per ogni stage. Il base image-device
usa 5 stage. Rockytkg configura un enrollment dinamico 3–8 stage e threshold
20 sull'esatta geometria 80×64; questa è una pipeline terza parte funzionante,
ma include preprocessing GPL proprio e non stabilisce sufficienza del mapping
D269 né qualità sul target locale.

## Audit NBIS

### Risoluzione e qualità

`get_minutiae()` passa `ppmm` a `combined_minutia_quality()`, che calcola:

```text
radius_pix = round(RADIUS_MM * ppmm)
```

Il raggio guida le statistiche locali che contribuiscono alla reliability di
ogni minutia. `ppmm=0` non è una misura semanticamente valida e 500 DPI non è
assegnabile per convenienza.

### Geometria 80×64

LFSv2 usa `MAP_BLOCKSIZE_V2=8`; `block_offsets()` rifiuta solo width o height
inferiori al blocksize. `80×64` supera quindi il limite e produce nominalmente
10×8 blocchi. Sono inoltre usate window 24, offset 8 e padding calcolato; non è
emerso un altro rifiuto dimensionale esplicito.

Supporto strutturale non significa supporto biometrico. Il print NBIS conserva
fino a 200 minutiae XYT; Bozorth restituisce score zero quando probe o gallery
ne hanno meno di 10. Il wrapper extraction fallisce già se non trova minutiae,
ma non impone 10 prima della creazione del template. Quindi la sola futura
misura fisica sbloccherebbe la correttezza semantica della quality radius, non
proverebbe la sufficienza della geometria `80x64`.

### Orientation e polarity

NBIS applica i flag H/V/inversione prima dell'estrazione e poi li rimuove dallo
stato copiato. Questa capacità non decide quali flag siano corretti per
APP12509. Con flag zero, D269 conserva soltanto l'ordine canonico del decoder.

## Evidenza target-specifica

Il riesame ha incluso D218–D220, D268–D270, `docs/EVIDENCE.md`, codice decoder,
artefatti testuali `gfusb.dll`/OEM e stringhe dei consumer algoritmo locali.
Risultato:

- `80x64 u16` e transpose wire→raster sono target-proven;
- `AlgoChicago.dll` consuma direttamente u16/12-bit;
- nessuna fonte misura active area, DPI o ppmm;
- nessuna fonte stabilisce natural orientation o ridge/valley polarity;
- le stringhe `rotate90`/`rotate_negative90` trovate in `AlgoChicagoT.dll` non
  appartengono al consumer target `AlgoChicago.dll` e non sono promosse;
- nessuna capture reale è stata decrittata o analizzata biometricamente in
  D271.

```text
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
TARGET_PPMM_EVIDENCE_CLASS=UNKNOWN
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
```

## Licensing boundary

- `Rockytkg/libfprint` dichiara `LGPLv2.1+`.
- `sigfm.cpp/.h` dichiarano `LGPL-2.1-or-later` e richiedono OpenCV4.
- NBIS locale reca l'avviso NIST public-domain.
- `Rockytkg/src/goodixgf.c` è LGPL-2.1-or-later e può essere letto come
  implementazione/corroborazione dopo audit.
- `Rockytkg/src/goodix_imgproc.c` è GPL-2.0-or-later: nessuna sua espressione,
  parametro o pipeline è stata trasferita nel dominio LGPL.
- D271 non modifica il ledger perché non importa/adatta codice esterno.

## Matrice di decisione

| Dimensione | SIGFM | NBIS |
| --- | --- | --- |
| ppmm richiesto | no, verificato | sì, verificato |
| 80×64 | shape accettato; gate ≥25 keypoint; qualità ignota | minimo 8 px superato; ≥10 minutiae per score; qualità ignota |
| orientation | flags ignorati; tolleranza rigida non testata | H/V flags applicabili, ma policy target ignota |
| polarity | non gestita/provata | inversion flag applicabile, ma policy target ignota |
| scala | SIFT scale-space, ma matcher limita distanza ~5%; non invariant-proven | coordinate/minutiae in pixel e quality fisica via ppmm |
| preprocessing | u8 diretto; nessuna normalizzazione interna | flip/invert flags, LFS2 maps/binarization/quality |
| template | keypoint + descrittori per stage | XYT fino a 200 minutiae per stage |
| matching | BF ratio + voto geometrico, threshold driver | Bozorth3, default threshold 40 |
| enrollment | array multi-stage SIGFM | array multi-stage XYT |
| target-local evidence | shape e mapping soltanto; qualità assente | shape e mapping soltanto; ppmm/qualità assenti |
| third-party evidence | pipeline Goodix 80×64 funzionante; threshold 20; 3–8 stage | nessuna equivalente target 12509 |
| licensing | LGPL fork + dipendenza OpenCV4 | LGPL integration + NBIS NIST public-domain |
| blocker | metriche keypoint/match, threshold, polarity/orientation | ppmm fisico + almeno 10 minutiae stabili + threshold |

## Policy e prerequisito successivo

```text
FEATURE_EXTRACTOR_POLICY=CLOSED_OFFLINE
SIGFM_STATUS=CANDIDATE_FOR_VALIDATION
NBIS_STATUS=BLOCKED_UNKNOWN_PHYSICAL_PPMM_AND_TARGET_LOCAL_MINUTIA_DENSITY_UNPROVEN
SIGFM_80X64_SUPPORT_STATUS=ARCHITECTURALLY_SUPPORTED_WITH_MIN_25_KEYPOINT_GATE_TARGET_QUALITY_UNPROVEN
NBIS_80X64_SUPPORT_STATUS=STRUCTURALLY_ACCEPTED_MIN_8PX_BLOCK_BUT_TARGET_USABILITY_BLOCKED
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
NEXT_PRIMARY_BOUNDARY=SIGFM_TARGET_LOCAL_BIOMETRIC_VALIDATION
NEXT_BOUNDARY_PREREQUISITE=AUTHORIZED_PRIVACY_PRESERVING_TARGET_REAL_KEYPOINT_AND_MATCH_METRICS_WITH_D269_FIXED_MAPPING
```

La validazione futura minima deve produrre, con autorizzazione separata e
gestione privacy esplicita:

1. conteggio keypoint per più frame target-reali e tasso di superamento del
   gate `>=25` usando il mapping D269 invariato;
2. determinismo di extraction e round-trip template sugli stessi input;
3. distribuzioni di score same-finger e different-finger sufficienti a
   motivare una soglia, senza assumere 20 o 40;
4. failure rate e cause (`<25`, matcher error, score 0);
5. confronto orientation/polarity soltanto per trasformazioni sostenute da
   evidenza indipendente, ricordando che i flag non agiscono su SIGFM.

Non viene creato un Operator Kit e nessuna run live è autorizzata da D271.

## Safety e closure

```text
LIVE_EXECUTION=NOT_PERFORMED
REAL_USB_OPEN_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=analysis/D271/D271_01_libfprint_feature_extraction_policy_bundle.zip
BUNDLE_SHA256=SEE_EXTERNAL_SIDECAR
```
