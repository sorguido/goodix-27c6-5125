# D277/01 — confine nativo A8 su USB reale

## Esito

La singola run autorizzata è terminata fail-closed al primo tentativo di
`g_usb_device_open()`, prima di claim, submit IN o submit OUT. L’autorizzazione
è stata consumata conservativamente sul primo tentativo di open del target
selezionato; non è stato effettuato alcun secondo tentativo.

```text
OUTCOME=BLOCKED_ENVIRONMENT_USB_OPEN_FAILED
NATIVE_FPI_USB_A8_PATH_TARGET_PROVEN=false
NATIVE_FPI_USB_A0_ROUTER_TARGET_PROVEN=false
LIVE_AUTHORIZATION_CONSUMED=true
LIVE_AUTHORIZED=false
A8_COMMAND_SUBMIT_COUNT=0
RETRY_COUNT=0
TRANSPORT_REOPEN_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

Il target era univoco (`27c6:5125`, bus 1, address 4, port 7), ma il nodo
`/dev/bus/usb/001/004` risultava `root:root`, modalità `0664`, senza ACL
aggiuntive. L’esecutore `uid=1000`, gruppi `1000,65534`, disponeva quindi solo
del permesso `other::r--`, non di scrittura. Poiché il `GError` originale non è
stato serializzato dall’harness, il nesso causale è classificato come
`STRONG_INFERENCE_USB_OPEN_REJECTED_BY_DEVICE_NODE_PERMISSIONS`, non come errno
osservato direttamente. Nessun `sudo`, cambio udev, unbind o mutazione host è
stato eseguito.

## Harness e percorso verificato host-only

È stato aggiunto un eseguibile test-only GPL, non installato e non registrato,
con un’unica modalità sensor-reaching e un solo frame immutabile:

```text
a00600a6a803000000ff
```

Il binding effimero crea un vero subclass `FpDevice` USB che possiede il
`GUsbDevice`; i trasferimenti live possono attraversare soltanto
`GoodixFpiUsbBackend` e il relativo `FpiUsbTransfer`, mentre tutti gli IN sono
consegnati all’esistente `GoodixUsbRouter`. Non esistono opzioni frame/opcode,
retry, reopen o reset. Il timeout A8 resta 1000 ms tramite cancellazione
host-side del cancellable della generation.

I file production D276/04 sono rimasti byte-identici alla baseline approvata
`95f40ca791011d637e2040a87014bbb8e946275e` durante la run.

## Verifiche pre-live

- D277: 6/6 test normali e 6/6 ASAN/UBSAN PASS;
- D276/03: 8/8 normali e 8/8 ASAN/UBSAN PASS;
- D276/04: 5/5 normali e 5/5 ASAN/UBSAN PASS;
- ACK e response nello stesso receive: PASS, senza armare un secondo IN;
- ACK/response frammentati su receive sequenziali: PASS;
- firmware errato e B0: fail-closed;
- secondo OUT e secondo IN concorrente: rifiutati;
- timeout/cancel: drain senza secondo comando;
- audit simboli: nessun percorso `libusb_*` parallelo; il live binary risolve
  le sole API bulk GUsb usate da `FpiUsbTransfer`;
- LeakSanitizer: non supportato nel sandbox Flatpak; ASAN e UBSAN restano PASS.

Harness live effimero:

```text
path=/tmp/goodix-d277-a8-build/d277_native_a8_once
sha256=e9f3f0043bf55bc3e43934eab24bdf24e73f149d3869503aaaf2ad61021e49ed
```

## Telemetria della singola run

```text
USB_OPEN_ATTEMPT_COUNT=1
USB_OPEN_COUNT=0
USB_CLAIM_COUNT=0
A8_COMMAND_SUBMIT_COUNT=0
BULK_IN_SUBMIT_COUNT=0
A8_LOGICAL_ACK_COUNT=0
A8_TYPED_RESPONSE_COUNT=0
MAX_OUTSTANDING_BULK_IN=0
SECOND_READER_API_PATH=ABSENT
RETRY_COUNT=0
TRANSPORT_REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
DEVICE_SIDE_CANCEL_COMMAND_COUNT=0
SECRET_MATERIALIZATION_COUNT=0
TLS_HANDSHAKE_COUNT=0
FINGER_WAIT_COUNT=0
IMAGE_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
HOST_CACHE_WRITE_COUNT=0
TERMINAL_CLEANUP_COMPLETED=true
```

## Closure

```text
OUTCOME=BLOCKED_ENVIRONMENT_USB_OPEN_FAILED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_CURRENT_OPERATOR_CONTEXT_USB_OPEN_BLOCKER
EXECUTABLE_CLOSURE=FAIL_TARGET_LIVE;PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=NATIVE_A8_A0_PATH_UNPROVEN;CURRENT_USER_LACKS_USB_NODE_WRITE_PERMISSION;NEW_LIVE_AUTHORIZATION_REQUIRED_AFTER_HOST_PERMISSION_REVIEW;GLOBAL_HARDWARE_EQUIVALENCE_UNPROVEN;PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_95f40ca791011d637e2040a87014bbb8e946275e_PLUS_HEAD_95f40ca791011d637e2040a87014bbb8e946275e_PLUS_WORKTREE_DIFF_PLUS_analysis/D277/D277_01_native_a8_real_usb.md_PLUS_analysis/D277/D277_01_native_a8_real_usb.json
```
