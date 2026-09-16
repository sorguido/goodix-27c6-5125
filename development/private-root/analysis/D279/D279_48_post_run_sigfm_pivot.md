<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/48 — closure autentica, classe B e pivot SIGFM

## Esito

```text
OUTCOME=READY
ADVANCEMENT=AUTHENTIC_COMPARATIVE_EVIDENCE_ABSORBED_AND_SIGFM_ARCHITECTURE_SELECTED
EXECUTABLE_CLOSURE=PASS_FOR_ATTACHED_SUMMARY_VALIDATION
D279_48_AUTHENTIC_RUN=PASS
D279_48_CLASS=B
EXTRACTOR_DIRECTION=SIGFM
NBIS_PARAMETER_SEARCH=STOP
CURRENT_LIVE_AUTHORIZED=false
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
```

La prima run autorizzata ha consumato il grant ma si è fermata prima della
lettura del materiale protetto: il reduced snapshot ometteva
`src/goodix5125_cleanroom.py`, import transitivo di `core/post_d4.py`. I commit
`286443207...` e `36999004...` hanno aggiunto la regressione e chiuso la
dependency closure prima della seconda autorizzazione.

La seconda run, sulla baseline completa
`36999004b9971f7004aaaa4da85d7c2d1afc79d1`, ha prodotto l'aggregate autentico
`AUTHENTIC_ROCKY_NBIS_SIGFM_AGGREGATE_READY`. Il summary allegato ha SHA-256
`71ec1922eb97f4804d7e228b09ef3edede04cbc4b3799eff433a418c1efa1ff3` e passa
il validator canonico D279/48. È conservato byte-identico come
`analysis/D279/D279_48_SUCCESS_summary.json` (37.475 byte); il file
`D279_48_authentic_aggregate_review.json` è soltanto una review derivata e non
lo sostituisce. Il campo interno della run resta correttamente
`PENDING_AUTHENTIC_AGGREGATE_REVIEW_A_B_C_OR_D`; la classe B è la decisione
della review successiva, non un valore riscritto nell'output primario.

## Evidenza comparativa

NBIS e SIGFM hanno ricevuto gli stessi raster byte-per-byte, nativi 80×64 e
senza resize. R1 è la catena comune Rockytkg; R2 aggiunge soltanto l'unsharp
SIGFM Rockytkg, boost 0,8 e sigma 1,5.

- NBIS non produce alcun frame Bozorth-computable su 42 in R1 o R2 e nessuno
  score eleggibile.
- SIGFM supera il gate di 25 keypoint in tutti i 42 frame a entrambi i
  checkpoint.
- R1: keypoint primary min/med/max 87/120/132, auxiliary 39/117/133; nel
  paired-cycle 40/42 direzioni hanno score nonzero e almeno 20, mediana 238047.
- R2: mediane keypoint primary/auxiliary 128/132; paired-cycle ancora 40/42,
  mediana 310975 e massimo 624104.

La classificazione è:

```text
B=SIGFM_MATERIALLY_OUTPERFORMS_NBIS_ON_SAME_INPUT
NBIS_PIPELINE_COMPATIBLE=true
NBIS_BIOMETRICALLY_VALIDATED=false
NBIS_BIOMETRIC_SUITABILITY=MATERIALLY_OUTPERFORMED_BY_SIGFM_ON_AUTHENTIC_SAME_INPUT
```

Il dataset contiene un solo dito/sessione, nessun different-finger control e
non autorizza claim FAR/FRR, accuratezza o soglia production. Il B0 iniziale
ATTEMPT02 resta un riferimento sperimentale, non una vera no-finger baseline
Rockytkg provata equivalente.

## KEEP / ADAPT / REPLACE / RETIRE

| Tratto | Decisione corrente |
| --- | --- |
| D279/03 | ADAPT: conservare registry/USB ID/build target; sostituire il consolidamento NBIS con SIGFM/OpenCV |
| D279/04–09 | KEEP: material owner, input, open/close e activation secure graph |
| D279/10 | KEEP: evidence authority dei 21 stage primari e 21 B0 ausiliari |
| D279/11–26 | KEEP/ADAPT: conservare grafo, lifecycle, sender, ownership e action mechanics; rimuovere wording/gate extractor-specifici |
| D279/27 | REPLACE: action nativa NBIS superseded |
| D279/28 | KEEP USB/TLS/FDT/lifecycle e one-shot; ADAPT preprocessing, extractor e action binding |
| D279/29–30 | KEEP come evidenza autentica del failure NBIS; authority live consumata |
| D279/31–33 | KEEP: reconstruction/decrypt/composer matcher-independent |
| D279/34–47 | RETIRE/HISTORICAL: parameter search NBIS, senza cancellazione Git |
| D279/48 | KEEP: comparator, provenance e pivot evidence |

## Delta Rockytkg minimo e licensing

Reference preservate:

```text
ROCKYTKG_COMMIT=227eba219fa9e3fbac5bd59aca79f624f67cd11b
ROCKYTKG_LIBFPRINT_SIGFM_COMMIT=7ebe0c809b4d1df3400e84299a4ec4acdea84590
TARGET_LIBFPRINT=Fedora_44_1.94.100
```

Audit per-file iniziale:

- `Rockytkg/src/goodix_imgproc.c` e
  `Rockytkg/include/goodix_imgproc.h`: GPL-2.0-or-later, copyright Rockytkg;
  riuso diretto/minimo autorizzato nel percorso production GPL-compatible.
- `Rockytkg/libfprint/libfprint/sigfm/{sigfm.cpp,sigfm.h,binary.hpp,img-info.hpp}`:
  LGPL-2.1-or-later con copyright e notice dei tre autori; riuso diretto
  compatibile. `tests.cpp`, `tests-embedded.hpp` e doctest non sono necessari
  al prodotto minimo.
- i punti di integrazione `fp-image`, `fpi-image`, `fpi-image-device`,
  `fp-print`, `fpi-print` e Meson del fork sono LGPL-2.1-or-later; vanno
  forward-portati semanticamente su 1.94.100, non copiati wholesale dalla base
  1.94.5.
- `goodixgf.c` non va importato: il progetto conserva il proprio stack
  APP12509 già provato. Firmware, provisioning, ClearApp, PSK/OTP e recovery
  Rockytkg restano esclusi.

OpenCV Fedora 44 dichiara componenti BSD-3-Clause/Apache-2.0/ISC; la
distribuzione combinata con il preprocessore GPL-2.0-or-later deve scegliere
termini GPL-compatible che soddisfino anche Apache-2.0, senza alterare le
licenze per-file. La conclusione operativa iniziale è
`GPL_3_OR_LATER_COMPATIBLE_COMBINED_DISTRIBUTION_CANDIDATE`, da chiudere con
license texts/notices e package audit prima di distribuzione, non un blocker
all'implementazione privata/offline.

## Primo confine implementativo

Il forward-port minimo deve includere: SIGFM/SIFT e OpenCV condizionali al
driver Goodix; tipo print SIGFM interno; extraction gate; feature ownership;
multi-sample add/copy/free; FP3 serialize/deserialize strict; verify/identify;
preprocessing Rockytkg R2; integrazione del riferimento B0 session-local e
della primary image nel grafo esistente. La primary resta un sample per
pressione e l'auxiliary resta opaca.

Il target reale ha libfprint 1.94.100, fprintd 1.94.5 e OpenCV core/imgproc
4.13; mancano localmente features2d, flann, opencv-devel, gcc-c++, Meson e
Ninja. Il primo build usa SDK/RPM estratti hash-pinned e `DESTDIR` temporaneo:
nessuna installazione di sistema è autorizzata.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_FEDORA44_LIBFPRINT_1_94_100_MINIMAL_SIGFM_FORWARD_PORT
NEXT_IMPLEMENTATION_POLICY=MAXIMUM_SAFE_DIRECT_ROCKYTKG_REUSE
FACTORY_PRESERVING_GOODIX_STACK=PRESERVE
CANONICAL_PRIMARY_EVIDENCE=analysis/D279/D279_48_SUCCESS_summary.json
REVIEW_SET=PRIMARY_AGGREGATE_PLUS_DERIVED_REVIEW_PLUS_OPERATOR_LOGS_PLUS_CANONICAL_DOCUMENTATION
```
