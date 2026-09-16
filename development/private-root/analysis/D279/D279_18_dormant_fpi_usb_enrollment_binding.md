<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/18 — binding enrollment dormant a GoodixFpiUsbBackend

## Esito

`goodix_enrollment_fpi_usb_binding.[ch]` collega lo sink della transazione a
`goodix_fpi_usb_backend_submit_out()` e riconduce la completion asincrona alla
transazione. La costruzione non invia nulla; richiede un backend con generation
già iniziata. Il codice è volutamente sensor-reaching se e solo se un caller lo
istanzia e invoca senza seam, ma oggi nessun path production lo costruisce e
`goodix_fpimage_device_activate()` continua a respingere
`FPI_DEVICE_ACTION_ENROLL` prima dell'avvio della generation.

```text
OUTCOME=READY_OFFLINE_DORMANT_FPI_USB_BINDING
ADVANCEMENT=PRODUCTION_SHAPED_BACKEND_COMPLETION_CONTRACT
CONSTRUCTION_SUBMITS=false
PRODUCTION_CALLER_PRESENT=false
PRODUCTION_ENROLLMENT_ACTIVATION_GATE=RETAINED
LIVE_EXECUTION_PERFORMED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Verifica

Il test crea il backend senza device, inizia generation 7 e installa la seam
asincrona prima di ogni OUT. Verifica un fixed64 pending, planner non committato,
completion generation 6 ignorata dal backend, completion 7 che effettua il
singolo commit e successivo ACK accettato. `real_submit_count` resta zero.

```text
D279_14_TO_18_TESTS=8/8_PASS_NORMAL;8/8_PASS_ASAN_UBSAN
ASYNC_HOST_SEAM_OUT_COUNT=1
BACKEND_REAL_SUBMIT_COUNT=0
STALE_BACKEND_COMPLETION=IGNORED_NO_COMMIT
SAME_GENERATION_COMPLETION=ONE_COMMIT
AUTOMATIC_RETRY_COUNT=0
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
```

La build production-shaped passa senza warning nuovi del binding, mantiene
registry standard/NBIS e non esegue enumerazione/open/claim/submit USB.

## Rischio e confine residuo

Questo è il primo modulo D279 che contiene una chiamata a un backend capace di
raggiungere il sensore. La non-raggiungibilità corrente dipende dal gate di
activation e dall'assenza di caller production, entrambi verificati nel review
set. Prima di introdurre ownership nel device context servono cancellation,
terminal fence, drain e distruzione deterministica del binding; nessun live è
necessario per tale passo.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_ENROLLMENT_BINDING_CANCELLATION_DRAIN_AND_CONTEXT_OWNERSHIP_WITH_GATE
```
