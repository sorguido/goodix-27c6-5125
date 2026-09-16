# D273/01 — chiusura offline post-first-image e build SIGFM reale

```text
OUTCOME=PARTIAL_CLOSURE_UP_TABLE_AND_POST_0X50_CLOSED_SECOND_TARGET_CYCLE_AND_REAL_SIGFM_BUILD_BLOCKED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_AND_OFFLINE_MODEL_CORRECTED
EXECUTABLE_CLOSURE=FAIL_REAL_SIGFM_NOT_AVAILABLE
RESIDUAL_BLOCKER_OR_RISK=SECOND_TARGET_CYCLE_AFTER_REARM_NOT_OBSERVED;TARGET_TIMEOUT_POLICY_UNCLOSED;OPENCV4_DEV_NOT_AVAILABLE;BIOMETRIC_QUALITY_UNPROVEN
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
BUNDLE=analysis/D273/D273_01_post_first_image_multiframe_sigfm_bundle.zip
```

## Risultato

D273 riduce due blocker D272 senza forzare la closure. Il dataflow OEM dimostra
che il body del `0x34` non contiene una costante: usa la tabella FDT-up volatile
di sessione a `0x180580838`, aggiornata dal gestore dell'IRQ `0x0002`. L'IRQ
`0x0200` aggiorna, nel ramo normale, la tabella FDT-down poi consumata dal nuovo
`0x32`. La correlazione con la capture rende forte il requisito di freshness
same-cycle, ma la capture positiva termina all'ACK del re-arm e non osserva una
seconda iterazione completa.

Il packet 249 è ora chiuso come risposta NAV A0 al `0x50`: non è un B0/TLS e
non è una fingerprint image. La forma osservata è control `0x50`, lunghezza
fisica/outer dichiarata 2417 e inner dichiarata 2410. Il call-flow
`chicagoHUget_navdata` (`0x180067874`) invia il mode 5 e consegna il NAV buffer
di sessione al caller. Questa occorrenza è distinta causalmente dal `0x50` del
bootstrap, pur riusando opcode e body.

Il build reale SIGFM resta non disponibile: host e SDK Flatpak installato non
forniscono `opencv4.pc` né header OpenCV. Nel SDK sono stati compilati con
warning severi adapter, wrapper e nuovo harness synthetic-only; la compilazione
del vero `sigfm.cpp` si arresta esattamente su
`opencv2/core/mat.hpp: No such file or directory`. Nessun pacchetto è stato
installato e il risultato non è promosso a PASS.

## Census delle capture locali

Il census programmatico ha trovato due sole capture target-specific pertinenti:

| Fonte | SHA-256 | Ruolo | Esito pertinente |
| --- | --- | --- | --- |
| `analysis/D230/work/GoodixExport/rilevamento.pcapng` | `50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b` | riferimento OEM positivo | una sequenza positiva; termina a packet 253 |
| `captures/D255_20260822T205631772Z_85c8c41f/raw/wire.pcapng` | `802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c` | riferimento OEM zero-finger | nessun IRQ2/record positivo; non chiude il loop |

Finestra positiva, indici USBPcap zero-based:

| Packet | Direzione | Framing | Evento | Classe |
| ---: | --- | --- | --- | --- |
| 220 | OUT | A0, 24 byte | `0x32` | `OBSERVED` |
| 223 | IN | A0, 10 byte | ACK `0x32/0x01` | `OBSERVED` |
| 225 | IN | A0, 24 byte | IRQ `0x0002` | `OBSERVED` |
| 227 | OUT | A0, 10 byte | `0x22` | `OBSERVED` |
| 229 | IN | A0, 10 byte | ACK `0x22/0x01` | `OBSERVED` |
| 231 | IN | B0/TLS, 7726 byte | fingerprint record, contenuto omesso | `OBSERVED`; decode live provato separatamente in D268 |
| 233 | OUT | A0, 22 byte | `0x34` | `OBSERVED` |
| 235 | IN | A0, 10 byte | ACK `0x34/0x01` | `OBSERVED` |
| 237 | IN | A0, 24 byte | IRQ `0x0200` | `OBSERVED` |
| 238 | OUT | A0, 10 byte | `0x20` | `OBSERVED` |
| 241 | IN | A0, 10 byte | ACK `0x20/0x01` | `OBSERVED` |
| 243 | IN | B0/TLS, 7726 byte | post-up image record, contenuto omesso | `OBSERVED` |
| 244 | OUT | A0, 10 byte | `0x50` | `OBSERVED` |
| 247 | IN | A0, 10 byte | ACK `0x50/0x01` | `OBSERVED` |
| 249 | IN | A0, 2417 byte | NAV response `0x50`, inner 2410 | `OBSERVED` + `VERIFIED_STATICALLY` |
| 251 | OUT | A0, 24 byte | re-arm `0x32` | `OBSERVED` |
| 253 | IN | A0, 10 byte | ACK `0x32/0x01` | `OBSERVED` |

Non esistono packet successivi nella fonte. Il JSON census conserva solo
metadata di framing; nessun contenuto B0, plaintext, raster o hash biometrico.

## Dataflow delle tabelle FDT

Il DLL non è stato eseguito. L'analisi statica hash-gated mostra:

1. `0x180028480` inizializza/aggiorna le globali di sessione: down
   `0x180580818`, up `0x180580838`, oppure entrambe in base al selector.
2. Il dispatcher IRQ `0x180028530`, nel ramo IRQ `0x0002`, passa la regione raw
   a `0x180029314`. La stringa OEM identifica l'operazione come acquisizione
   della base up mentre il mode corrente è FDT-down.
3. `0x180029314` valida i sei word raw, costruisce word codificati da
   `raw/2 + offset contestuale` (fallback `0x15`), applica touchflag e policy
   mode-dependent, quindi aggiorna `0x180580838`.
4. Il builder FDT-up `0x1800250d0–0x1800251b5` copia direttamente quella
   globale nel body `0a 01 || table12` del `0x34`.
5. Nel ramo IRQ `0x0200`, `0x180029210` deriva normalmente la tabella down a
   `0x180580818`; il builder FDT-down la usa nel successivo `0x32` insieme a un
   timestamp corrente.

Conclusione:

```text
UP_TABLE12_SOURCE=OEM_SESSION_GLOBAL_GF_FDT_UP_BASE_VA_0X180580838
UP_TABLE12_DERIVATION=IRQ_0X0002_RAW_BASE_VALIDATION_THEN_PER_WORD_HALF_PLUS_CONTEXT_OFFSET_ENCODING_AND_MODE_DEPENDENT_COMMIT_BY_0X180029314
UP_TABLE12_LIFETIME=VOLATILE_OEM_PROCESS_SESSION_GLOBAL_INITIALIZABLE_BY_CALLBACK_0X180028480_AND_UPDATED_BY_FDT_IRQ_HANDLING
UP_TABLE12_FRESHNESS_REQUIREMENT=0X34_MUST_CONSUME_THE_MOST_RECENT_VALID_IRQ_0X0002_DERIVED_TABLE_FROM_THE_SAME_FINGER_DOWN_CYCLE
```

Il valore catturato `808780948081807a807f8086` resta un'istanza di sessione,
non una costante APP12509.

## Contratto `0x50` e seconda iterazione

`chicagoHUget_navdata` invoca il dispatcher mode 5 e copia il NAV buffer di
sessione al caller. Nel path di analisi OEM a `0x180068cf2` la chiamata segue
una wait FDT riuscita; il risultato entra nei confronti/aggiornamenti delle
baseline. La capture prova l'ordine ACK → A0 NAV response → re-arm, ma non
isola un singolo predicato scalare che, da solo, governi packet 251.

Il dispatcher OEM supporta ripetutamente IRQ2 e apprendimento up; builder e
consumer per immagine esistono. L'ownership dell'intero edge
`re-arm → next IRQ2 → next 0x22 → next fingerprint B0` nello stesso lifecycle
non è però chiusa univocamente dal call graph locale. Rocky implementa il
concetto di ciclo e apprendimento up/down, ma diverge nella coda post-`0x34`
e vale solo come `THIRD_PARTY_CORROBORATION`. Perciò:

```text
SECOND_CYCLE_STATIC_CALLFLOW=PARTIALLY_VERIFIED_EVENT_DRIVEN_COMPONENTS_LOOP_OWNERSHIP_NOT_FULLY_CLOSED
SECOND_CYCLE_STATUS=TARGET_CAPTURE_NOT_OBSERVED
MULTIFRAME_CONTRACT=PARTIALLY_CLOSED_TARGET_SECOND_CYCLE_NOT_OBSERVED_AND_TARGET_TIMEOUTS_UNCLOSED
```

## Correzione del modello offline

`core/multiframe_validation.py` non riusa più una coppia fissa up/down:

- la tabella up iniziale deve dichiarare sorgente IRQ2 e generation 0;
- l'IRQ `0x0200` deve consegnare una tabella down della generation corrente;
- il `0x32` usa proprio tale tabella e un timestamp per transizione;
- l'IRQ2 successivo deve consegnare la up table della generation seguente;
- source IRQ, lunghezza o generation errati falliscono chiuso;
- `NAV_RESPONSE` resta il nome corretto, ma ora richiede anche la forma target
  A0 2417/2410 oltre a control `0x50`.

Exact ACK `0x01`, rejection di `0x07`, single-reader, zero retry/reopen/recovery,
sample bound e terminal last sample restano invariati. Nessun allowlist USB o
coordinator live include il nuovo percorso; D268 resta `STOP_AFTER_FIRST_IMAGE`.

## Build recipe SIGFM reale

Quando un ambiente già predisposto fornirà `g++`, header e librerie OpenCV4:

1. creare una directory con `mktemp -d /tmp/goodix-d273-real-sigfm.XXXXXX`;
2. compilare `goodix_u16_to_fpimage.c` con GCC C11 e warning severi;
3. compilare con G++ C++17 e warning severi
   `goodix_sigfm_metrics.cpp`, il vero
   `Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp` e
   `test_goodix_sigfm_metrics_real.cpp`, usando gli include locali e
   `pkg-config --cflags opencv4`;
4. linkare i quattro oggetti con `pkg-config --libs opencv4` in
   `$tmp/test-goodix-sigfm-real`;
5. eseguire quel binary dalla directory temporanea; ripetere con
   ASan/UBSan solo se la build OpenCV selezionata è compatibile.

L'harness usa soltanto u16 sintetici deterministici, non serializza nulla e
accetta esclusivamente success/failure tipizzate del vero extractor. Non prova
qualità, sufficienza target, separazione same/different finger, polarity,
orientation o threshold production.

## Safety e closure

```text
MULTIFRAME_MODEL_EXECUTABLE_CLOSURE=PASS_OFFLINE
REAL_SIGFM_EXECUTABLE_CLOSURE=FAIL_NOT_AVAILABLE
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_BIOMETRIC_CAPTURE_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

La minima evidenza residua è descritta in
`D273_01_target_evidence_gap.json`. D273 non crea un Operator Kit e non
autorizza una run live.
