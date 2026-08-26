# D274/03 parallel offline forward analysis — differential Linux readiness

```text
ARTIFACT_CLASS=PARALLEL_OFFLINE_FORWARD_ANALYSIS
DEPENDS_ON_D274_QUALIFICATION=false
MODIFIES_D274_03=false
MODIFIES_LIVE_CRITICAL=false
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
BASELINE_APPROVAL=false
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

## Sintesi della mappa differenziale

Il progetto ha già chiuso offline (o ha un modello offline fail-closed) tutto il
percorso da cold-start a prima immagine, inclusi decode canonico, mapping
`u16 → FpImage` (D269/D270), policy di feature-extraction (D271) e lifecycle
multi-frame (D273). I veri gap che richiedono il target o che restano
architetturalmente aperti sono:

- **secondo/successivo ciclo di capture dopo re-arm** — `TARGET_EVIDENCE_REQUIRED`
  (D272/D273: re-arm osservato con ACK, ma seconda iterazione completa non
  osservata; timeout target non chiuso);
- **orientation / polarity / ppmm** — `TARGET_EVIDENCE_REQUIRED` (D269/D271);
- **qualità biometrica / threshold di match e verify** — `TARGET_EVIDENCE_REQUIRED`;
- **glue device libfprint e lifecycle fprintd** — non ancora implementati localmente;
  Rockytkg `goodixgf.c` (LGPL) è solo *reference* da reimplementare clean-room,
  con le porzioni firmware-update/PSK marcate `ROCKY_UNSAFE_FOR_PROJECT`.

Avanzamento software realizzato in questo step (un solo seam host-only): il
collector di capture decodificate `goodix_capture_aggregation` in
`libfprint-driver/` (LGPL), che assembra un enroll-set bounded di `FpImage`
reali via il pipeline D270, senza alcun comando device, USB, TLS, file, retry o
scrittura persistente. Vedi `D274_03_offline_forward_seam_report.md`.

## Matrice differenziale (riassunto; dettaglio in `D274_03_offline_forward_matrix.json`)

| # | Componente | Classificazione | Dipende da D274 |
| --- | --- | --- | --- |
| 1 | cold-start / TLS | `LOCAL_PARTIAL` (+ `ROCKY_REUSE_CANDIDATE_GPL` per Linux) | no (qualification TLS è su Windows D274/03) |
| 2 | FDT arm | `LOCAL_CLOSED` | no |
| 3 | IRQ/event routing | `LOCAL_PARTIAL` (timeout target non chiuso) | parzialmente |
| 4 | first image | `LOCAL_CLOSED` | no |
| 5 | finger-up | `LOCAL_PARTIAL` (`TARGET_EVIDENCE_REQUIRED` per timeout) | sì (timeout) |
| 6 | re-arm | `LOCAL_PARTIAL` (osservato ACK, 2° ciclo no) | sì (2° ciclo) |
| 7 | second/subsequent capture cycle | `TARGET_EVIDENCE_REQUIRED` | **sì** |
| 8 | image decode | `LOCAL_CLOSED` | no |
| 9 | u16 → FpImage | `LOCAL_CLOSED` (D269/D270) | no |
| 10 | orientation / polarity / ppmm | `TARGET_EVIDENCE_REQUIRED` | sì |
| 11 | feature extraction | `LOCAL_PARTIAL` (+ `HOST_ONLY_WORK_AVAILABLE` seam SIGFM) | parzialmente |
| 12 | matching | `HOST_ONLY_WORK_AVAILABLE` (SIGFM sintetico; OpenCV reale bloccato) | sì (qualità) |
| 13 | enrollment aggregation | `LOCAL_PARTIAL` (seam host-only aggiunto questo step) | no (collez. host) / sì (glue driver) |
| 14 | verification | `LOCAL_PARTIAL` (policy; qualità target-richiesta) | sì |
| 15 | libfprint device glue | `ROCKY_REUSE_CANDIDATE_LGPL` (reference; reimpl clean-room; parti unsafe escluse) | n/a |
| 16 | fprintd-facing lifecycle | `ROCKY_CORROBORATION_ONLY` | n/a |
| 17 | cleanup / cancel | `LOCAL_CLOSED` | no |
| 18 | persistent-write exclusion | `LOCAL_CLOSED` (allowlist fail-closed) + `ROCKY_UNSAFE_FOR_PROJECT` classificato | no |

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
- **`CANDIDATE_HYPOTHESIS_FOR_D274`** — dopo il re-arm finale il target rilascia
  un secondo `IRQ2 → 0x22 → ACK → immagine` analogo al primo; la freschezza
  same-cycle della up-table (`0x180580838`) è il prerequisito. Da verificare su
  D274/03 (Windows, Goodix assente) e su una futura run Linux.
- **`MUST_NOT_IMPLEMENT_BEFORE_TARGET_EVIDENCE`** — qualsiasi codice che *emetta* il
  secondo ciclo, assuma la semantica no-finger/post-up dell'immagine, o fissi il
  timeout target. Il nuovo seam host-only non emette alcun comando device e resta
  al di fuori di questo confine.

I frame immagine TLS restano separati per costruzione (demux A0/B0 in `post_d4`);
cancel/stop/re-entry sono modellati host-only in `fdt_lifecycle.py` senza recovery
A2/`0x70` né reopen. Assunzioni Rockytkg non ancora provate localmente: timeout
target, semantica seconda iterazione, comportamento `0x34` fuori dalla sessione.

## C. Audit no-write / factory-preserving

Percorsi nel nostro runtime (`core/fdt_lifecycle.py`, `core/persistent_runtime.py`):

- allowlist `SAFE_DEVICE_COMMANDS = {0x20,0x22,0x32,0x36,0x50,0x82}`;
- `PERSISTENT_COMMAND_FAMILIES = {0xE0,0xA4,0xF0,0xF4}` e
  `SPECIAL_RECOVERY_COMMANDS = {0xA2,0x70}` sono **irraggiungibili per
  costruzione** (`_record` fail-closed);
- nessun retry automatico, nessun USB-reset/recovery, nessuna scrittura host di
  PSK/cache, nessun firmware/IAP/ClearApp.

Percorsi nello snapshot Rockytkg (solo classificazione, nessun riuso espressivo):

- `goodix_fwupdate.c`: `0xA4` ClearApp, `0xF0`/`0xF4` trasferimento firmware IAP,
  `0xA2 {2,20}` hard-reset MCU → **`ROCKY_UNSAFE_FOR_PROJECT`**;
- `goodix_psk.c`: `gx_psk_write_to_mcu` (scrittura PSK su MCU) e `gx_psk_store_save`
  (scrittura `psk.bin` su filesystem host) → **`ROCKY_UNSAFE_FOR_PROJECT`**;
- `goodix_otp.c`: letture OTP (read-only di per sé, ma superficie di readback
  sensibile) → solo host-side separabile, non riusato per path device.

Verdetto: il nostro codice possiede già una policy globale sufficiente a rendere
tali famiglie irraggiungibili; il nuovo seam non introduce alcuna API
sensor-reaching e non altera tale policy.

## D. Gap Linux/libfprint (offline, da raster sintetico a lifecycle)

Partendo da un raster sintetico/fixture compatibile col contratto corrente
(`80x64` u16/12-bit), offline oggi è chiudibile:

- **API/ownership/state-machine**: `goodix_u16_to_fpimage` (D269) + `goodix_fpimage_pipeline`
  (D270) + nuovo `goodix_capture_aggregation` (questo step) → costruzione, lifetime,
  ownership e collezione bounded di `FpImage` reali: **chiuso offline**;
- **enrollment aggregation**: libfprint gestisce multi-stage internamente; il
  collector host-only appena aggiunto è il pezzo mancante lato driver-collection:
  **parzialmente chiuso offline** (policy + collector; il loop driver reale no);

Richiede target reale (NON chiudibile offline):

- **orientation/polarity/ppmm** (D269/D271);
- **metriche/threshold SIGFM** (OpenCV4-dev assente; build reale bloccato, D272/D273);
- **qualità biometrica / verify-match affidabile**;
- **glue device libfprint** (`goodixgf.c` solo reference LGPL da reimplementare
  clean-room, escluse le parti unsafe).

Componenti già presenti che NON devono essere reinventati: decoder canonico
(`src/goodix5125_cleanroom.py`), mapping D269, pipeline D270, policy feature-extraction
D271, seam SIGFM D272, lifecycle multi-frame D273, allowlist no-write in
`fdt_lifecycle.py`/`persistent_runtime.py`.

## Decisione sul seam

È stato implementato **un solo** seam host-only (`goodix_capture_aggregation`),
perché soddisfa tutti i criteri: mancante, indipendente da D274, non assume
semantica target non provata (flags=0, ppmm unknown), senza USB/reale/persistent
write, senza nuove dipendenze, non tocca D274/03 né live-critical, testabile con
fixture sintetiche. La verifica di build/run nel sandbox corrente è bloccata
dall'assenza di `gcc`/`glib`/`flatpak org.freedesktop.Sdk` (stessa condizione del
blocco OpenCV4-dev in D272/D273); lo script `run_goodix_capture_aggregation_test.sh`
riproduce esattamente l'harness D270 e l'audit forbidden-symbol passa per revisione
statica (nessun simbolo `libusb_/usb_/fopen/open/read/write/socket/SSL_/mbedtls_/gnutls_`).

```text
IMPLEMENTATION=IMPLEMENTED_ONE_SAFE_HOST_ONLY_SEAM
SEAM_PATH=libfprint-driver/goodix_capture_aggregation.{c,h}
SEAM_BUILD_VERIFICATION=BUILD_BLOCKED_SANDBOX_TOOLCHAIN_ABSENT; FORBIDDEN_SYMBOL_AUDIT_PASS; RUN_SCRIPT_READY_FOR_DEV_ENV
```
