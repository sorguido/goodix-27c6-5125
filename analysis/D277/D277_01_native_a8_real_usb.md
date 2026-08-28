# D277/01 — confine nativo A8 su USB reale

## Esito della prima run autorizzata

La singola run autorizzata dello step originale è terminata fail-closed al primo
tentativo di `g_usb_device_open()`, prima di claim, submit IN o submit OUT.
L’autorizzazione è stata consumata conservativamente sul primo tentativo di open
del target selezionato; non è stato effettuato alcun secondo tentativo.

```text
OUTCOME=BLOCKED_ENVIRONMENT_USB_OPEN_FAILED
NATIVE_FPI_USB_A8_PATH_TARGET_PROVEN=false
NATIVE_FPI_USB_A0_ROUTER_TARGET_PROVEN=false
LIVE_AUTHORIZATION_CONSUMED=true
AUTHORIZATION_CONSUMPTION_POLICY=CONSERVATIVE_ON_FIRST_TARGET_OPEN_ATTEMPT
LIVE_AUTHORIZED=false
A8_COMMAND_SUBMIT_COUNT=0
RETRY_COUNT=0
TRANSPORT_REOPEN_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

Il target era univoco (`27c6:5125`, bus 1, address 4, port 7), ma il nodo
`/dev/bus/usb/001/004` risultava `root:root`, modalità `0664`, senza ACL
aggiuntive. L’esecutore `uid=1000`, gruppi `1000,65534`, disponeva quindi solo
del permesso `other::r--`, non di scrittura. Poiché il `GError` originale non era
stato serializzato dall’harness, il nesso causale era classificato come
`STRONG_INFERENCE_USB_OPEN_REJECTED_BY_DEVICE_NODE_PERMISSIONS`, non come errno
osservato direttamente. Nessun `sudo`, cambio udev, unbind o mutazione host è
stato eseguito.

## Correttivo host-only D277/01

Lo stesso D277/01 è stato riaperto per un correttivo host-only. Non è stata
eseguita una nuova run live; sono vietate dall’autorizzazione corrente tutte le
operazioni sensor-reaching.

Modifiche apportate a `tools/d277_native_a8_once.c`:

1. **Failure observability** — `g_usb_device_open()`, `claim_interface()`,
   `release_interface()` e `close()` preservano ora `ERROR_DOMAIN`,
   `ERROR_CODE` e `ERROR_MESSAGE` in strutture serializzabili nel JSON di
   output. I failure precedenti all’esistenza di un `GError` restano
   `NOT_AVAILABLE`.
2. **Permission preflight host-only** — prima di qualsiasi
   `g_usb_device_open()` l’harness risolve il device node
   `/dev/bus/usb/BBB/DDD`, ne verifica esistenza, tipo, uid/gid/mode, uid/gid
   e gruppi dell’esecutore, e consulta `access(W_OK)`. Se il nodo non è
   scrivibile, il gate fallisce con
   `BLOCKED_ENVIRONMENT_USB_NODE_NOT_WRITABLE` e **non** consuma
   l’autorizzazione live. Il preflight è read-only, senza chmod/chown/ACL/udev,
   sudo, open, claim o transfer.
3. **Test host-only** — aggiunti test per la formattazione del device node, la
   classificazione mode/uid/gid (owner/group/other e root bypass), i casi di
   nodo non esistente, file regolare, readable-not-writable, writable-owner e
   la serializzazione di un `GError` sintetico. ACL parsing non è stato
   implementato; la decisione è documentata nel sorgente.
4. **Semantica autorizzazione** — distinzione canonica esplicita tra la run
   precedente (`live_authorization_consumed=true`) e lo stato attuale:
   `previous_live_attempt_terminated=true`,
   `device_contact_or_real_submit_occurred=false`,
   `current_live_authorized=false`,
   `new_user_authorization_required_for_any_new_open_claim_or_submit=true`.

I file production D276/04 sono rimasti byte-identici alla baseline approvata
`95f40ca791011d637e2040a87014bbb8e946275e`.

## Verifiche post-correttivo

- D277: 13/13 test normali e 13/13 ASAN/UBSAN PASS;
- D276/02: 15/15 normali e 15/15 ASAN/UBSAN PASS;
- D276/03: 8/8 normali e 8/8 ASAN/UBSAN PASS;
- D276/04: 5/5 normali e 5/5 ASAN/UBSAN PASS (LeakSanitizer disabilitato nella
  sandbox Flatpak locale, come noto).

## Telemetria della singola run (conservata)

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

## Stato di autorizzazione corrente

```text
PREVIOUS_LIVE_ATTEMPT_TERMINATED=true
DEVICE_CONTACT_OR_REAL_SUBMIT_OCCURRED=false
USB_OPEN_COUNT=0
USB_CLAIM_COUNT=0
A8_COMMAND_SUBMIT_COUNT=0
CURRENT_LIVE_AUTHORIZED=false
NEW_USER_AUTHORIZATION_REQUIRED_FOR_ANY_NEW_OPEN_CLAIM_OR_SUBMIT=true
```

## Closure

```text
D277_01_HOST_ONLY_CORRECTIVE=READY_FOR_AI_PM_REVIEW
OUTCOME=BLOCKED_ENVIRONMENT_USB_OPEN_FAILED_HOST_ONLY_CORRECTIVE_COMPLETE
ADVANCEMENT=HOST_SIDE_OBSERVABILITY_AND_PERMISSION_PREFLIGHT_IMPROVEMENT_NO_DEVICE_SIDE_PROGRESS
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=NATIVE_A8_A0_PATH_UNPROVEN;CURRENT_USER_LACKS_USB_NODE_WRITE_PERMISSION;NEW_LIVE_AUTHORIZATION_REQUIRED_AFTER_HOST_PERMISSION_REVIEW;GLOBAL_HARDWARE_EQUIVALENCE_UNPROVEN;PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_95f40ca791011d637e2040a87014bbb8e946275e_PLUS_TOOLS_d277_native_a8_once.c_PLUS_analysis/D277/D277_01_native_a8_real_usb.md_PLUS_analysis/D277/D277_01_native_a8_real_usb.json_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_dot_github/workflows/d276-native-tls-usb-host-only.yml
```
