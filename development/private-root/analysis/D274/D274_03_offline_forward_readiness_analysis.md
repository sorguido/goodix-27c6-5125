# D274/03 parallel offline forward analysis — differential Linux readiness

```text
ARTIFACT_CLASS=PARALLEL_OFFLINE_FORWARD_ANALYSIS
DEPENDS_ON_D274_03_QUALIFICATION=false
MODIFIES_D274_03=false
MODIFIES_LIVE_CRITICAL=false
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
BASELINE_APPROVAL=false

WINDOWS_NATIVE_QUALIFICATION_ROLE=HOST_ONLY_EXECUTABLE_QUALIFICATION_WITH_GOODIX_ABSENT
WINDOWS_NATIVE_QUALIFICATION_CLOSES_SECOND_CYCLE_EVIDENCE=false
FUTURE_D274_03_LIVE_ROLE=EXPLICIT_ONE_SHOT_SECOND_CYCLE_OBSERVATION_ONLY
TARGET_TIMEOUT_SEMANTICS_CLOSED_BY_SUCCESSFUL_D274_LIVE=false

LIBFPRINT_ENROLLMENT_AGGREGATION=FRAMEWORK_OWNED_VERIFIED
PROJECT_EXTRA_FPIMAGE_AGGREGATOR_REQUIRED=false
LOCAL_LIBFPRINT_DEVICE_GLUE=NOT_YET_IMPLEMENTED

ROCKY_GOODIXGF_LICENSE=LGPL-2.1-or-later
ROCKY_GOODIXGF_DIRECT_REUSE_POSSIBLE_AFTER_PER_FILE_AUDIT=true
GPL_TO_LGPL_EXPRESSION_CROSSING_ALLOWED=false

LINUX_TLS_1_2_PSK_TARGET_STATUS=LIVE_PROVEN_D245
PERSISTENT_TLS_RUNTIME_STATUS=IMPLEMENTED_D260
LINUX_TLS_REBUILD_REQUIRED=false

A2_0X70_COLD_START_CANONICAL_REACHABILITY=ALLOWED_BOUNDED_EXISTING_PATH
A2_0X70_FDT_RECOVERY_REENTRY_REACHABILITY=FORBIDDEN_FAIL_CLOSED
PERSISTENT_COMMAND_FAMILIES_REACHABLE=false

IMPLEMENTATION=SKIPPED_NO_INDEPENDENT_SAFE_SEAM
```

## Scopo e metodo

Analisi differenziale end-to-end tra lo stato corrente del progetto e il percorso
Linux completo rappresentato dallo snapshot Rockytkg `227eba219fa9e3fbac5bd59aca79f624f67cd11b`
(`Rockytkg/PROVENANCE.md`), svolta interamente OFFLINE, senza Goodix, senza libusb
reale, senza Windows VM e senza alcuna dipendenza dall'osservazione del secondo
ciclo che D274/03 dovrà ancora catturare. La base del branch di sessione coincide
esattamente con `origin/main` (`5964d9703d31ccbb3e71ef142bfd2394a37c9932`);
working tree iniziale pulito, nessuna divergenza preesistente.

Il candidato Windows D274/03 resta **congelato** per la qualification nativa
successiva; non è stato toccato alcun file D274/03 né alcun live-critical set.

## Due ruoli distinti di D274/03 (BLOCKER 1)

È falsa l'affermazione che la qualification Windows D274/03 (Goodix assente)
possa chiudere l'evidenza del secondo ciclo. I due ruoli vanno distinti
esplicitamente:

- **`D274_03_WINDOWS_NATIVE_QUALIFICATION_WITH_GOODIX_ABSENT`** — qualifica
  esclusivamente la parte *host-only eseguibile*: Windows PowerShell 5.1 runtime,
  Git/repository gate, TShark/USBPcap/preflight, ACL/privacy, selector/same-run
  gates, simulazione pre-authority, hard-disable / host-side executable closure.
  Il sensore è assente, quindi **non può osservare né chiudere alcuna evidenza
  del secondo ciclo**.
- **`FUTURE_D274_03_EXPLICITLY_AUTHORIZED_LIVE_ONE_SHOT_WITH_GOODIX_ATTACHED`** —
  solo dopo qualification PASS + AI-PM freeze review + baseline approval +
  autorizzazione esplicita, potrà osservare:
  `0x32` re-arm ACK → second `IRQ0002` → second `0x22` → ACK `0x01` → second
  fingerprint `B0` → STOP. Questo è l'unico boundary stretto del live one-shot:
  *second-cycle existence/order after re-arm*.
- Un eventuale D274/03 live riuscito **non** è prova del timeout semantico del
  device: una success path bounded da deadline host dimostra solo che il ciclo è
  avvenuto entro la finestra osservata, non il timeout interno del sensore.

## Sintesi della mappa differenziale

Il progetto ha già chiuso offline (o ha un modello offline fail-closed) tutto il
percorso da cold-start a prima immagine, inclusi decode canonico, mapping
`u16 → FpImage` (D269/D270), policy di feature-extraction (D271) e lifecycle
multi-frame (D273). I veri gap che richiedono il target o che restano
architetturalmente aperti sono:

- **secondo/successivo ciclo di capture dopo re-arm** — `TARGET_EVIDENCE_REQUIRED`,
  boundary stretto del futuro live one-shot D274/03 (D272/D273: re-arm osservato
  con ACK, ma seconda iterazione completa non osservata);
- **orientation / polarity / ppmm** — `TARGET_EVIDENCE_REQUIRED`, separato dal
  D274/03 one-shot (D269/D271);
- **qualità biometrica / threshold di match e verify** — `TARGET_EVIDENCE_REQUIRED`,
  richiede distribuzioni di score target, non chiuse dal D274/03 one-shot;
- **glue device libfprint e lifecycle fprintd** — non ancora implementati
  localmente; Rockytkg `goodixgf.c` è `LGPL-2.1-or-later` e può essere valutato
  per riuso/adattamento diretto nel dominio LGPL dopo audit per-file di
  SPDX/licenza/copyright/origini/provenance; le porzioni firmware-update/PSK e
  ogni espressione GPL-only restano escluse (`GPL_TO_LGPL_EXPRESSION_CROSSING_ALLOWED=false`).

Nessun seam è stato implementato in questo corrective: il collector
`goodix_capture_aggregation` aggiunto nello step precedente è stato rimosso dopo
review AI-PM perché l'enrollment aggregation multi-stage è di proprietà del
framework libfprint (vedi sotto).

## Matrice differenziale (riassunto; dettaglio in `D274_03_offline_forward_matrix.json`)

| # | Componente | Classificazione | Dipende da D274/03 one-shot |
| --- | --- | --- | --- |
| 1 | cold-start / TLS (Linux) | `LOCAL_CLOSED` (D245 live-proven; D260 runtime) | NO |
| 2 | FDT arm | `LOCAL_CLOSED` | NO |
| 3 | IRQ/event routing | `LOCAL_PARTIAL` (timeout target non chiuso) | NO (timeout richiede target evidence separata) |
| 4 | first image | `LOCAL_CLOSED` | NO |
| 5 | finger-up | `LOCAL_PARTIAL` (`TARGET_EVIDENCE_REQUIRED` per timeout) | NO |
| 6 | re-arm | `LOCAL_PARTIAL` (osservato ACK, 2° ciclo no) | YES_SECOND_CYCLE_OBSERVATION |
| 7 | second/subsequent capture cycle | `TARGET_EVIDENCE_REQUIRED` | YES_SECOND_CYCLE_OBSERVATION |
| 8 | image decode | `LOCAL_CLOSED` | NO |
| 9 | u16 → FpImage | `LOCAL_CLOSED` (D269/D270) | NO |
| 10 | orientation / polarity / ppmm | `TARGET_EVIDENCE_REQUIRED` | NO (target evidence separata) |
| 11 | feature extraction | `LOCAL_PARTIAL` (+ `HOST_ONLY_WORK_AVAILABLE` SIGFM) | NO |
| 12 | matching | `HOST_ONLY_WORK_AVAILABLE` (SIGFM sintetico; OpenCV reale bloccato) | NO (qualità/threshold target-richiesti) |
| 13 | enrollment aggregation | `FRAMEWORK_OWNED` (libfprint) | NO |
| 14 | verification | `LOCAL_PARTIAL` (policy; qualità target-richiesta) | NO |
| 15 | libfprint device glue | `ROCKY_REUSE_CANDIDATE_LGPL` (direct reuse/adapt dopo audit; parti unsafe escluse) | NO |
| 16 | fprintd-facing lifecycle | `ROCKY_CORROBORATION_ONLY` | NO |
| 17 | cleanup / cancel | `LOCAL_CLOSED` | NO |
| 18 | persistent-write exclusion | `LOCAL_CLOSED` (allowlist fail-closed) + `ROCKY_UNSAFE_FOR_PROJECT` classificato | NO |

## B. Audit del boundary repeated-cycle

Confronto tra il modello D272/D273 (locale) e il lifecycle Rockytkg
(`goodix_capture.c`, `goodix_init.c`).

- **`PROVEN_LOCALLY`** — prima immagine (`IRQ2 → 0x22 → ACK → B0`); `0x34 {up_table}`
  con ACK `34/01`; `IRQ 0x0200` finger-up dopo ACK `0x34`; `0x20 {0100}` + ACK;
  immagine post-up; `0x50 {0100}` + ACK + response NAV; `0x32` re-arm + ACK
  (D272 `REARM_0X32_STATUS=OBSERVED_WITH_ACK`).
- **`CORROBORATED_EXTERNALLY`** — Issue #1 Rockytkg: enrollment fprintd 8 capture,
  verify match/no-match, PAM; ma su unità con PSK assente (status `0x01`) e PSK
  *riprovisionata una volta* → **non** prova la preservazione della PSK
  Windows/factory. Trattata come `THIRD_PARTY_CORROBORATION`, non prova target.
- **`CANDIDATE_HYPOTHESIS_FOR_FUTURE_LIVE`** — dopo il re-arm finale il target
  rilascia un secondo `IRQ2 → 0x22 → ACK → immagine` analogo al primo; la
  freschezza same-cycle della up-table (`0x180580838`) è il prerequisito. Da
  verificare su una **futura run live esplicitamente autorizzata con Goodix
  collegato** (`FUTURE_D274_03_EXPLICITLY_AUTHORIZED_LIVE_ONE_SHOT_WITH_GOODIX_ATTACHED`),
  NON sulla qualification Windows con Goodix assente.
- **`MUST_NOT_IMPLEMENT_BEFORE_TARGET_EVIDENCE`** — qualsiasi codice che *emetta* il
  secondo ciclo, assuma la semantica no-finger/post-up dell'immagine, o fissi il
  timeout target.

I frame immagine TLS restano separati per costruzione (demux A0/B0 in `post_d4`);
cancel/stop/re-entry sono modellati host-only in `fdt_lifecycle.py` senza recovery
A2/`0x70` né reopen. Assunzioni Rockytkg non ancora provate localmente: timeout
target, semantica seconda iterazione, comportamento `0x34` fuori dalla sessione.

## C. Audit no-write / factory-preserving

Percorsi nel nostro runtime (`core/fdt_lifecycle.py`, `core/persistent_runtime.py`):

- allowlist `SAFE_DEVICE_COMMANDS = {0x20,0x22,0x32,0x36,0x50,0x82}`;
- `PERSISTENT_COMMAND_FAMILIES = {0xE0,0xA4,0xF0,0xF4}` sono **irraggiungibili
  per costruzione** (nessun provisioning/firmware/IAP/ClearApp/persistent write);
- `SPECIAL_RECOVERY_COMMANDS = {0xA2,0x70}` **non** sono globalmente
  irraggiungibili: sono raggiungibili solo nei loro bounded canonical cold-start
  positions già autorizzati/provati via `core/cold_start.py`, e restano vietati
  come retry/recovery/FDT re-entry/session repair/fallback automatico; dentro
  `FdtLifecycle._record()` sono esclusi fail-closed
  (`A2_0X70_FDT_RECOVERY_REENTRY_REACHABILITY=FORBIDDEN_FAIL_CLOSED`);
- nessun retry automatico, nessun USB-reset/recovery, nessuna scrittura host di
  PSK/cache, nessun firmware/IAP/ClearApp.

Percorsi nello snapshot Rockytkg (solo classificazione, nessun riuso espressivo):

- `goodix_fwupdate.c`: `0xA4` ClearApp, `0xF0`/`0xF4` trasferimento firmware IAP,
  `0xA2 {2,20}` hard-reset MCU → **`ROCKY_UNSAFE_FOR_PROJECT`**;
- `goodix_psk.c`: `gx_psk_write_to_mcu` (scrittura PSK su MCU) e `gx_psk_store_save`
  (scrittura `psk.bin` su filesystem host) → **`ROCKY_UNSAFE_FOR_PROJECT`**;
- `goodix_otp.c`: letture OTP (read-only di per sé, ma superficie di readback
  sensibile) → solo host-side separabile, non riusato per path device.

Verdetto: il nostro codice rende le famiglie persistent ancora irraggiungibili e
confina `0xA2`/`0x70` al solo cold-start canonico (`core/cold_start.py`),
vietandoli come recovery/retry/re-entry; nessun seam è stato aggiunto in questo
corrective.

## D. Gap Linux/libfprint (offline, da raster sintetico a lifecycle)

Partendo da un raster sintetico/fixture compatibile col contratto corrente
(`80x64` u16/12-bit), offline oggi è chiudibile:

- **API/ownership/state-machine**: `goodix_u16_to_fpimage` (D269) +
  `goodix_fpimage_pipeline` (D270) → costruzione, lifetime e ownership di
  `FpImage` reali: **chiuso offline**;
- **enrollment aggregation**: di proprietà del framework libfprint
  (`FpImageDevice`, `fpi-image-device.c:302-306`):
  `fpi_print_add_print(enroll_print, print)` → `priv->enroll_stage += 1` →
  `fpi_device_enroll_progress(...)`; il driver consegna una `FpImage` alla volta
  via `fpi_image_device_image_captured()`. **Non è richiesto alcun aggregatore
  FpImage extra lato progetto** (`PROJECT_EXTRA_FPIMAGE_AGGREGATOR_REQUIRED=false`).

Richiede target reale (NON chiudibile offline):

- **orientation/polarity/ppmm** (D269/D271);
- **metriche/threshold SIGFM** (OpenCV4-dev assente; build reale bloccato, D272/D273);
- **qualità biometrica / verify-match affidabile**;
- **glue device libfprint** (`goodixgf.c` LGPL-2.1-or-later: riuso/adattamento
  diretto possibile dopo audit per-file; escluse le parti unsafe).

Componenti già presenti che NON devono essere reinventati: decoder canonico
(`src/goodix5125_cleanroom.py`), mapping D269, pipeline D270, policy feature-extraction
D271, seam SIGFM D272, lifecycle multi-frame D273, allowlist no-write in
`fdt_lifecycle.py`/`persistent_runtime.py`.

## Decisione sul seam (corrective AI-PM)

Lo step precedente aveva implementato `goodix_capture_aggregation`
(4 file in `libfprint-driver/`). La review AI-PM (BLOCKER 2) ha stabilito che
non è uno seam chiaramente mancante:

- `fpi-image-device.c:302-306` esegue già l'enrollment/template aggregation
  multi-stage nel framework libfprint;
- `goodixgf.c` consegna ogni `FpImage` singolarmente via
  `fpi_image_device_image_captured()` e conserva copie 8-bit di frame già
  accettati solo per una propria euristica di diversità/duplicate detection
  (policy target-quality-dependent, diversa dall'aggregazione di framework);
- `goodix_fpimage_pipeline.c` mantiene l'ownership del proprio `FpImage`
  (`goodix_capture_aggregation_get_image()` restituiva un puntatore borrowed);
- il collector aggiunto non implementava l'enrollment aggregation reale di
  libfprint, non era necessario per consegnare una capture al framework,
  introduceva retention multi-image non motivata e non aveva un consumer reale.

I 4 file sono stati **rimossi** in questo corrective. Nessun altro seam è stato
aggiunto. `IMPLEMENTATION=SKIPPED_NO_INDEPENDENT_SAFE_SEAM`.

```text
IMPLEMENTATION=SKIPPED_NO_INDEPENDENT_SAFE_SEAM
LIBFPRINT_ENROLLMENT_AGGREGATION=FRAMEWORK_OWNED_VERIFIED
PROJECT_EXTRA_FPIMAGE_AGGREGATOR_REQUIRED=false
LOCAL_LIBFPRINT_DEVICE_GLUE=NOT_YET_IMPLEMENTED
```
