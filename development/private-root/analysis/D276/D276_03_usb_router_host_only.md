<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D276/03 — GoodixUsbRouter A0/B0 single-receive host-only

## Closure

```text
OUTCOME=READY
ADVANCEMENT=HOST_ONLY_EXECUTABLE_VALIDATION_PASS_CLEAN_TREE
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=HARDWARE_EQUIVALENCE_UNPROVEN;PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED;TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS_UNRESOLVED;TARGET_DEVICE_TIMEOUT_UNKNOWN;ENROLLMENT_STAGE_POLICY_NOT_SELECTED
CANONICAL_DOCUMENTATION=UPDATED
D276_03_OUTCOME=READY
D276_03_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D276_03_CI_VALIDATED_COMMIT=49e7e9d108d14fc7a9910d97022cd4baa829c5e4
D276_03_MERGED_MAIN_COMMIT=474aa2b931977a2c748098c4e510764ad7ee7f42
D276_03_GITHUB_ACTIONS_PUSH_RUN=33184060807
D276_03_GITHUB_ACTIONS_PR_RUN=33184064239
D276_03_GITHUB_ACTIONS_RESULT=PASS
REVIEW_SET=BASELINE_MAIN_66f2d4354689e61b57c96bc6b039095cd91d100d_PLUS_CORRECTIVE_RUNTIME_d8ddaa72835662a92db857f55551810649a2b1c5_PLUS_CI_VALIDATED_COMMIT_49e7e9d108d14fc7a9910d97022cd4baa829c5e4_PLUS_GITHUB_ACTIONS_PUSH_33184060807_PR_33184064239_PLUS_MERGED_MAIN_474aa2b931977a2c748098c4e510764ad7ee7f42
```

## Implementazione ed evidenza

Il nuovo `GoodixUsbRouter` è transport-agnostic e posseduto dal
`GoodixDeviceContext` dell'open epoch. Esiste un solo entry point per completion
fisica; i consumer A0/B0 ricevono in ordine un `GBytes` borrowed/transfer-none valido durante la callback e devono chiamare `g_bytes_ref()` per trattenerlo. Il parser conserva i
byte fra chunk, emette più frame concatenati e chiude fail-closed outer type,
length e finalizzazione troncata impossibili. Generation e token outstanding
separati impediscono a callback N-1 di consumare la receive di N. Cancellation
chiude il fence, invalida la generation e non invia alcun comando.

I test sintetici coprono A0 ACK, IRQ `0x0002`, IRQ `0x0200`, NAV e B0
opaco solo come marker consumer-side, senza attribuire al router semantiche
inner non canonizzate. Coprono inoltre un B0 il cui header (incluso LE16 length) e body attraversano più receive, zero delivery prima del frame completo, concatenazione,
ordering/exactly-once, cancellation durante delivery, callback stale e
transcript malformati/troncati.

```text
GOODIX_USB_ROUTER_IMPLEMENTED=true
A0_B0_INCREMENTAL_PARSER=PASS
A0_B0_DEMUX=PASS
B0_SPLIT_ACROSS_RECEIVES=PASS
GBytes_CALLBACK_OWNERSHIP=TRANSFER_NONE_BORROWED_DURING_CALLBACK
DELIVERY_ORDER_PRESERVED=true
DELIVERY_EXACTLY_ONCE=true
PHYSICAL_RECEIVE_OWNER_COUNT=1
MAX_OUTSTANDING_RECEIVES=1
SECOND_READER_API_PATH=ABSENT
STALE_GENERATION_CALLBACK=IGNORED
CANCEL_TERMINAL_FENCE=PASS
MALFORMED_TRANSCRIPTS_FAIL_CLOSED=PASS
D276_03_NORMAL_TEST_RUN=PASS
D276_03_SANITIZER_TEST_RUN=PASS
D276_03_DETERMINISM_RUNS=2
D276_03_ROUTER_TESTS_PER_NORMAL_RUN=8/8_PASS
D276_03_ROUTER_TESTS_PER_SANITIZER_RUN=8/8_PASS
D276_02_FPIMAGE_REGRESSION_NORMAL=PASS
D276_02_FPIMAGE_REGRESSION_SANITIZER=PASS
CLOUD_WORK_ONLY=true
REAL_USB_ACCESS=false
REAL_SENSOR_COMMAND_COUNT=0
REAL_TLS_HANDSHAKE_WITH_DEVICE_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
VID_PID_PRODUCTION_REGISTRATION=false
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_AUTHORIZED=false
```

## Test realmente eseguiti

Due invocazioni separate di `libfprint-driver/tests/run_goodix_usb_router_test.sh`:
ogni invocazione ha compilato con warning severi ed eseguito 8/8 test normali e
8/8 test ASAN/UBSAN. È stata inoltre rieseguita la suite D276/02 integrata:
14/14 normal e 14/14 sanitizer PASS. Nell'immagine Codex i prerequisiti GLib-dev mancanti sono stati installati direttamente come root, senza `sudo`, prima delle esecuzioni host-only.

Altri check: `git diff --check`, audit statico dell'unico simbolo completion,
assenza di API USB/TLS/device e verifica Git di branch/diff/worktree. Il
workflow dedicato ha ripetuto lo stesso gate sul clean checked-in tree al commit
`49e7e9d108d14fc7a9910d97022cd4baa829c5e4`: le run push 33184060807 e PR
33184064239 sono PASS; single-reader audit, audit dei simboli real-USB vietati
e clean checked-in tree sono PASS. Il commit validato è stato integrato in
`main` da `474aa2b931977a2c748098c4e510764ad7ee7f42`.

## Provenance, safety e limiti

Nuovo codice LGPL indipendente basato solo sul manuale e D276/01. Nessun codice
GPL o esterno è stato consultato/importato; GLib è la sola API terza usata. Le
fixture sono sintetiche, senza capture, secret o dati biometrici. Non sono
presenti `FpiUsbTransfer`, `GUsbDevice`, VID:PID, TLS o accessi a device.

Non risultano provati: quiescenza device-side dopo cancel, equivalenza hardware,
timeout target, lifetime TLS cross-activation, stage enrollment, orientation,
polarity, ppmm o qualità biometrica.

## Review set

Baseline `main`: `66f2d4354689e61b57c96bc6b039095cd91d100d`; corrective runtime:
`d8ddaa72835662a92db857f55551810649a2b1c5`; commit validato dalla CI:
`49e7e9d108d14fc7a9910d97022cd4baa829c5e4`; merge su `main`:
`474aa2b931977a2c748098c4e510764ad7ee7f42`.

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
