# D278/12 — secure-session reentry-prefixed fino al secondo B0, host-only

```text
OUTCOME=READY
ADVANCEMENT=NEW_NATIVE_C_HOST_ONLY_PROTOCOL_BOUNDARY_REACHED_REENTRY_PREFIX_THROUGH_RETAINED_TLS_TO_TWO_ACQUISITIONS
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=SECOND_IMAGE_RASTER_NOT_TARGET_PROVEN;ORIENTATION_UNRESOLVED;POLARITY_UNRESOLVED;TARGET_PHYSICAL_PPMM_UNKNOWN;ENROLLMENT_STAGE_POLICY_NOT_SELECTED;REAL_USB_PATH_NOT_AUTHORIZED_OR_EXECUTED;PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_b704d52ccc292c4fc669373c7eb8d8b296518ff7_ON_main_PLUS_CURRENT_WORKTREE_DIFF_PLUS_analysis/D278/D278_12_reentry_secure_session_to_two_acquisition_host_only.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_docs/LICENSING_AND_PROVENANCE.md_PLUS_libfprint-driver/goodix_image_decoder.[ch]_PLUS_libfprint-driver/goodix_post_tls_lifecycle.[ch]_PLUS_libfprint-driver/goodix_secure_session.[ch]_PLUS_libfprint-driver/goodix_fpimage_device.[ch]_PLUS_STEP_LOCAL_TESTS_AND_RUNNERS

D278_12_BASELINE=b704d52ccc292c4fc669373c7eb8d8b296518ff7

D278_11_LIVE_OUTCOME=PASS
D278_11_ONE_SHOT_CONSUMED=true
D278_11_RERUN_AUTHORIZED=false

REENTRY_PREFIXED_NATIVE_SECURE_SESSION_TARGET_PROVEN=true
REENTRY_RECOVERY_A2_TO_TLS_TARGET_PROVEN=true
NATIVE_TLS12_PSK_HANDSHAKE_WITH_REENTRY_RECOVERY_TARGET_PROVEN=true

REAL_USB_RX_FRAGMENTATION_DIFFERS_FROM_SYNTHETIC_REFERENCE=OBSERVED
LOGICAL_PROTOCOL_SEQUENCE_UNAFFECTED=true
D278_11_LIVE_PHYSICAL_IN_SUBMIT_COUNT=26
D278_11_LIVE_PHYSICAL_OUT_SUBMIT_COUNT=19
D278_11_LIVE_MAX_OUTSTANDING_IN=1
D278_11_LIVE_MAX_OUTSTANDING_OUT=1

D275_STOP_AFTER_SECOND_IMAGE_TARGET_PROVEN=true
D275_FDT_TABLE_MISMATCH_CAUSALITY=LIVE_VALIDATED

POST_TLS_TWO_ACQUISITION_NATIVE_C_INTEGRATION_IMPLEMENTED=true
REENTRY_PREFIXED_NATIVE_C_TO_SECOND_B0_HOST_ONLY_PROVEN=true
SAME_OPEN_EPOCH_USB_OWNER_HOST_ONLY_PROVEN=true
SAME_TLS_SESSION_THROUGH_SECOND_B0_HOST_ONLY_PROVEN=true
TLS_HANDSHAKE_COUNT_MAX=1
SECRET_HANDOFF_COUNT_MAX=1
TRANSPORT_REOPEN_COUNT=0

FIRST_IMAGE_PIPELINE_HOST_ONLY_PROVEN=true
SECOND_B0_LIFECYCLE_HOST_ONLY_PROVEN=true
SECOND_IMAGE_PIPELINE_HOST_ONLY_PROVEN=true
SECOND_IMAGE_RASTER_TARGET_PROVEN=false

RELEASE_TAIL_ORDER_HOST_ONLY_PROVEN=true
FRESH_SAME_CYCLE_DOWN_TABLE_GATE_HOST_ONLY_PROVEN=true
REARM_EXACTLY_ONCE_HOST_ONLY_PROVEN=true
THIRD_CYCLE_COMMAND_COUNT=0

PHYSICAL_RX_FRAGMENTATION_INVARIANCE_HOST_ONLY_PROVEN=true
MAX_PHYSICAL_IN_OUTSTANDING=1
MAX_PHYSICAL_OUT_OUTSTANDING=1

RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0

ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
ENROLLMENT_STAGE_POLICY=NOT_SELECTED

REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false

FUTURE_REENTRY_PREFIXED_NATIVE_TWO_ACQUISITION_LIVE_READY_FOR_AI_PM_REVIEW=false
```

## 1. Scope ed evidenza canonizzata

Lo step è stato eseguito sulla branch `main`, con `HEAD` iniziale identico alla
baseline richiesta `b704d52ccc292c4fc669373c7eb8d8b296518ff7` e worktree
inizialmente pulita. Non sono stati eseguiti USB reale, `sudo`, fprintd, lettura
di materiali protetti, operator kit, provisioning, flash, IAP o scritture
persistenti. Non è stato creato alcun launcher o percorso live nuovo.

Il prompt D278/12 fornisce la nuova evidenza live D278/11 da integrare nel
manuale canonico. La run one-shot consumata ha esito `PASS` sulla baseline
`b704d52ccc292c4fc669373c7eb8d8b296518ff7` e trace esatto:

```text
REENTRY_RECOVERY_A2,A8,E4,OEM_COLD_START_A2_1,CHIP_82,OTP_A6,
OEM_COLD_START_A2_2,MODE_70,DAC_220,DAC_236,DAC_238,DAC_23A,
CONFIG_90,D1,TLS,STOP
```

Contatori live D278/11: open/claim/release/close `1/1/1/1`, command `14`, ACK
`13`, typed `8`, TLS `1`, handoff secret `1`, IN fisici `26`, OUT fisici `19`,
massimo outstanding `1/1`. Retry, reopen, reset, clear-halt, persistent write,
application data, finger e image sono `0`; cleanup, drain e zeroizzazione del
materiale project-owned sono riusciti. La differenza rispetto ai `18` IN del
riferimento sintetico è classificata come frammentazione/completion fisica:
non cambia il transcript logico.

Questi fatti promuovono la catena reentry-prefixed e il TLS con recovery a
target-proven. Non provano il meccanismo causale di A2, la necessità universale
del prefisso o la nonmutazione NVM assoluta.

## 2. Grafo di ownership implementato

La composizione resta in un solo grafo nativo C/LGPL:

```text
GoodixDeviceContext (open epoch + generation)
  ├── GoodixFpiUsbBackend (un solo owner IN/OUT)
  ├── GoodixUsbRouter (un solo parser incrementale A0/B0)
  ├── GoodixSecureSession
  │     REENTRY_RECOVERY_A2 ... D1 -> GoodixTlsServer -> STOP
  └── GoodixPostTlsLifecycle
        D4 -> AF -> fresh FDT -> first IRQ2/0x22/B0
        -> release 0x34/IRQ0200/0x20/B0/0x50/NAV
        -> gated 0x32 -> second IRQ2/0x22/B0 -> STOP
```

`GoodixSecureSession` notifica `STOP` tramite callback. Il
`GoodixDeviceContext` verifica la stessa generation e l'assenza di terminal
fence; il secure-session consente l'handoff del callback OUT soltanto quando
record queue, B0 e pacing sono vuoti e nessun OUT è outstanding. Il lifecycle
subentra sullo stesso backend. L'oggetto TLS non viene ricreato: tutti i B0
post-handshake continuano a entrare in `goodix_secure_session_handle_b0()` e
nel medesimo `GoodixTlsServer`; il plaintext è inoltrato per callback al
lifecycle.

Gli A0 post-TLS sono instradati dallo stesso router al lifecycle. Non esistono
polling, flag globali, secondo reader, seconda generation, reopen o restart
TLS. Failure di protocollo, trasporto, decoder, generation o cancel è
terminale: invalida le tabelle fresh, azzera il buffer plaintext temporaneo,
cancella il backend e non offre resume.

## 3. Contratto lifecycle

Il bootstrap eseguito è:

```text
D4 -> AF -> 0x36 -> IRQ0100 -> 0x50/NAV
-> 0x36 -> IRQ0100 -> 0x82 -> 0x20/B0
-> 0x36 -> IRQ0100 -> first 0x32
```

La prima acquisizione richiede `IRQ0002/flags003f`, deriva la FDT-up come
`0x80,((raw>>1)+0x1d)`, emette esattamente un `0x22`, decifra il primo B0 e
decodifica la prima immagine. Il release tail è vincolato a:

```text
image -> 0x34/ACK -> IRQ0200 -> fresh down-table
-> 0x20/ACK -> post-up B0 consumed/discarded
-> 0x50/ACK -> NAV -> release complete -> finger off
```

La down-table usa `0x80,(raw>>1)` ed è legata a IRQ, generation e ciclo
correnti. Il secondo `0x32` è consentito una sola volta dopo la congiunzione
`release complete + fresh down-table + AWAIT_FINGER_ON`. Seguono secondo
`IRQ0002`, secondo `0x22`, secondo B0 e stop; non è emesso un terzo ciclo.

Ogni A0 OUT è fixed64 con zero-tail. Echo e status ACK sono esatti (`0x01` nel
post-TLS). NAV, IRQ, flags, body length e ordine sono strict. La suite controlla
anche i byte esatti delle FDT-up/down nei command body.

La risposta tipizzata `0x82` non è scaffolding morto: il byte soglia guida due
classificazioni host-side dei delta assoluti sui sei word FDT, prima→seconda e
seconda→terza lettura. L'arm finale richiede che entrambe le coppie siano
classificabili nella stessa generation; la classe within/outside è telemetria e
non cambia wire, payload o blocking, coerentemente con il confine D259. Nel
vettore deterministico entrambe le classificazioni risultano within `0x20`.

## 4. Decoder e pipeline immagine

Il nuovo decoder C indipendente usa il contratto neutro canonico:

```text
plaintext 7693
-> declared 7690
-> data 7689
-> prefix 5 + record 7684
-> packed12 7680 + CRC-32/MPEG-2 4
-> 5120 sample -> raster 80x64
```

Il marker image-specific `0x88` salta solo il checksum additivo; framing,
classe image, rifiuto POV, lunghezze e CRC restano obbligatori. Il mapping è
quello canonico `wire_index -> (wire_index % 64) * 80 + wire_index / 64`.
Poiché `GoodixTlsServer` legge al massimo 4096 byte per callback, il lifecycle
ricompone l'immagine in base alla length dichiarata, rifiuta overflow/extra e
azzera il buffer temporaneo prima di proseguire.

Nel percorso reale del `GoodixDeviceContext`, il callback immagine invoca
`goodix_device_context_emit_image_ready()`, che costruisce un vero `FpImage`
80×64 tramite `goodix_fpimage_pipeline_new()`. La suite composta prova due
decode completi; la regressione `FpImageDevice` e quella della pipeline provano
la costruzione del vero oggetto libfprint. Orientation, polarity e ppmm non
sono inventati.

## 5. Prova host-only composta

Il test
`/goodix/d278/reentry-tls-to-two-acquisitions-composed` non somma soltanto
fixture isolate. Esegue nella stessa istanza di backend/router:

1. le 14 fasi reentry-prefixed;
2. un handshake OpenSSL TLS 1.2 PSK reale in Memory BIO;
3. handoff del backend drenato senza cambiare identità TLS;
4. D4, AF e fresh-FDT;
5. bootstrap B0 cifrato;
6. prima immagine 7693-byte cifrata, spezzata da `SSL_read_ex` e ricomposta;
7. release tail e post-up B0 cifrato classificato non-image;
8. rearm gated exactly-once;
9. seconda immagine cifrata e stop dopo il secondo B0.

Le asserzioni finali sono handshake `1`, handoff `1`, secure command `14`,
post-TLS command `15`, due image callback, stesso puntatore TLS, max IN/OUT
outstanding `1/1`, retry/reopen/third cycle `0`.

Il test `d278-12/full-fragmented` percorre lo stesso lifecycle con header e
body separati in chunk da `1/2/5/11/23` byte, ACK+typed concatenati e un numero
di receive fisici maggiore di `18`; il risultato logico e la telemetria sono
identici alla variante unfragmented.

## 6. Verifica eseguita

Tutti i comandi seguenti sono host-only e sono stati eseguiti dal cwd reale
del repository. Il Flatpak SDK è stato avviato con rete disabilitata; le seam
USB hanno mantenuto `REAL_USB_SUBMIT=0`.

| Verifica | Esito |
|---|---|
| `run_goodix_d278_secure_session_test.sh` | 14/14 normal + 14/14 ASAN/UBSAN PASS; include composed end-to-end e retained TLS |
| `run_goodix_d278_12_post_tls_test.sh` | 6/6 normal + 6/6 ASAN/UBSAN PASS; repeat deterministico interno, FDT/order/gate/fragmentation/failure |
| `run_goodix_fpimage_device_test.sh -q` | 17/17 normal + 17/17 ASAN/UBSAN PASS; ownership `GoodixDeviceContext` e vero framework |
| `run_goodix_usb_router_test.sh` | 8/8 normal + 8/8 ASAN/UBSAN PASS |
| `run_goodix_fpimage_pipeline_test.sh` | normal + ASAN/UBSAN PASS; forbidden-symbol audit PASS |
| `python3 -m unittest tests.test_d275_01_production_multiframe` | 7/7 PASS |
| D278/12 source/provenance audit | PASS |
| D278/12 undefined-symbol recovery/TLS audit | PASS |
| `git diff --check` e `sh -n` runner | PASS |

La copertura corrisponde ai criteri T1–T19: full path, ownership unico,
regressione D278/11, FDT exact, ordine release, rejection stale/cross-generation,
rearm una volta, secondo ciclo, nessun terzo, post-up classification, prima e
seconda pipeline, frammentazione/concatenazione, cancel/generation, failure
secure, audit provenance/symbol, regressioni e sanitizer.

## 7. Provenance e safety

`goodix_image_decoder.[ch]` e `goodix_post_tls_lifecycle.[ch]` sono
`LGPL-2.1-or-later` e implementati indipendentemente dai fatti neutrali
canonici. Non includono, importano o traducono sorgenti GPL; l'audit blocca
riferimenti a implementazioni GPL e simboli di reset, clear-halt, control
transfer o TLS indipendente. Il TLS resta nel modulo nativo esistente.

Le famiglie flash/IAP, provisioning, PSK write, OTP write, factory write e
configurazione persistente non sono implementate né raggiungibili. I contatori
retry/reopen/reset/clear-halt/persistent write restano strutturalmente zero.

## 8. Limiti e decisione live

`SECOND_IMAGE_RASTER_TARGET_PROVEN=false` non contraddice D275/04. D275/04
prova sul target il secondo B0 e lo stop wire-driven, ma non conserva o valida
una seconda raster come evidenza target. D278/12 prova host-only che un secondo
payload immagine sintetico valido attraversa decoder e pipeline C. La futura
prova della seconda raster target richiederebbe nuova esecuzione live, nuova
baseline approvata e nuova autorizzazione esplicita.

D278/12 non seleziona la policy enrollment, non registra il VID:PID, non
installa il driver e non prepara operator kit. `CURRENT_LIVE_AUTHORIZED=false`
e `READY_FOR_LIVE=false`; pertanto anche
`FUTURE_REENTRY_PREFIXED_NATIVE_TWO_ACQUISITION_LIVE_READY_FOR_AI_PM_REVIEW`
resta `false`.
