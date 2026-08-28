<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D276/03 — GoodixUsbRouter A0/B0 single-receive host-only

## Closure

```text
OUTCOME=READY
ADVANCEMENT=NEW_C_LGPL_SINGLE_RECEIVE_ROUTER_AND_SYNTHETIC_EXECUTION_EVIDENCE
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=HARDWARE_EQUIVALENCE_UNPROVEN;PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED;TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS_UNRESOLVED;TARGET_DEVICE_TIMEOUT_UNKNOWN;ENROLLMENT_STAGE_POLICY_NOT_SELECTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_b16f5289023354adc5c0c42bed12572ab6249e85_BRANCH_work_PATHS_LISTED_BELOW
```

## Implementazione ed evidenza

Il nuovo `GoodixUsbRouter` è transport-agnostic e posseduto dal
`GoodixDeviceContext` dell'open epoch. Esiste un solo entry point per completion
fisica; i consumer A0/B0 ricevono `GBytes` owned in ordine. Il parser conserva i
byte fra chunk, emette più frame concatenati e chiude fail-closed outer type,
length e finalizzazione troncata impossibili. Generation e token outstanding
separati impediscono a callback N-1 di consumare la receive di N. Cancellation
chiude il fence, invalida la generation e non invia alcun comando.

Gli otto test sintetici coprono A0 ACK, IRQ `0x0002`, IRQ `0x0200`, NAV e B0
opaco solo come marker consumer-side, senza attribuire al router semantiche
inner non canonizzate. Coprono inoltre split di header/body, concatenazione,
ordering/exactly-once, cancellation durante delivery, callback stale e
transcript malformati/troncati.

```text
GOODIX_USB_ROUTER_IMPLEMENTED=true
A0_B0_INCREMENTAL_PARSER=PASS
A0_B0_DEMUX=PASS
DELIVERY_ORDER_PRESERVED=true
DELIVERY_EXACTLY_ONCE=true
PHYSICAL_RECEIVE_OWNER_COUNT=1
MAX_OUTSTANDING_RECEIVES=1
SECOND_READER_API_PATH=ABSENT
STALE_GENERATION_CALLBACK=IGNORED
CANCEL_TERMINAL_FENCE=PASS
MALFORMED_TRANSCRIPTS_FAIL_CLOSED=PASS
NORMAL_TEST_RUN=PASS
SANITIZER_TEST_RUN=PASS
DETERMINISM_RUNS=2
REAL_USB_ACCESS=false
REAL_SENSOR_COMMAND_COUNT=0
REAL_TLS_HANDSHAKE_WITH_DEVICE_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
VID_PID_PRODUCTION_REGISTRATION=false
LIVE_AUTHORIZED=false
```

## Test realmente eseguiti

Due invocazioni separate di `libfprint-driver/tests/run_goodix_usb_router_test.sh`:
ogni invocazione ha compilato con warning severi ed eseguito 8/8 test normali e
8/8 test ASAN/UBSAN. È stata inoltre rieseguita la suite D276/02 integrata:
14/14 normal e 14/14 sanitizer PASS. Nell'immagine Codex i metadata GLib-dev
non erano preinstallati; pacchetti Ubuntu sono stati solo scaricati ed estratti
sotto `/tmp` (nessun `sudo`, nessuna installazione) per fornire header/pkg-config.

Altri check: `git diff --check`, audit statico dell'unico simbolo completion,
assenza di API USB/TLS/device e verifica Git di branch/diff/worktree. Il
workflow dedicato ripete lo stesso gate sul clean checked-in tree.

## Provenance, safety e limiti

Nuovo codice LGPL indipendente basato solo sul manuale e D276/01. Nessun codice
GPL o esterno è stato consultato/importato; GLib è la sola API terza usata. Le
fixture sono sintetiche, senza capture, secret o dati biometrici. Non sono
presenti `FpiUsbTransfer`, `GUsbDevice`, VID:PID, TLS o accessi a device.

Non risultano provati: quiescenza device-side dopo cancel, equivalenza hardware,
timeout target, lifetime TLS cross-activation, stage enrollment, orientation,
polarity, ppmm o qualità biometrica.

## Review set

Baseline: `b16f5289023354adc5c0c42bed12572ab6249e85`; branch: `work`.

Path D276/03:

- `.github/workflows/d276-usb-router-host-only.yml`
- `libfprint-driver/goodix_usb_router.[ch]`
- `libfprint-driver/goodix_fpimage_device.[ch]`
- `libfprint-driver/tests/test_goodix_usb_router.c`
- `libfprint-driver/tests/run_goodix_usb_router_test.sh`
- `libfprint-driver/tests/run_goodix_fpimage_device_test_inner.sh`
- `Goodix 27c6 5125 manuale tecnico.md`
- `docs/LICENSING_AND_PROVENANCE.md`
- `analysis/D276/D276_03_usb_router_host_only.{md,json}`

```text
NEXT_PRIMARY_BOUNDARY=D276_04_NATIVE_TLS_MEMORY_BIO_AND_ASYNC_FPI_USB_BACKEND_HOST_ONLY
```
