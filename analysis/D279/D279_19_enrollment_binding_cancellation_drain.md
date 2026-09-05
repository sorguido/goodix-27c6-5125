<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/19 — cancellation terminale e drain OUT enrollment

## Esito

Il binding dormant verso `GoodixFpiUsbBackend` dispone ora di una cancellation
idempotente. La sequenza recinta prima il backend, rende terminale la
transazione e impedisce il free del binding finché la completion dell'OUT
fisico pending non è stata osservata.

```text
OUTCOME=READY_OFFLINE_BINDING_CANCELLATION_AND_DRAIN
ADVANCEMENT=TERMINAL_FENCE_AND_DETERMINISTIC_OUT_LIFETIME
AUTOMATIC_RETRY_COUNT=0
PRODUCTION_CALLER_PRESENT=false
PRODUCTION_ENROLLMENT_ACTIVATION_GATE=RETAINED
LIVE_EXECUTION_PERFORMED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Contratto verificato

La regressione usa router e backend host-only con seam asincrona. Dopo un solo
OUT sintetico, due richieste di cancel producono una sola cancellation
auditata. Finché la completion è pending il binding non è distruttibile. La
completion cancellata della stessa generation drena l'OUT, ma la transazione
già terminale non committa il comando preparato.

```text
D279_14_TO_19_TESTS=9/9_PASS_NORMAL;9/9_PASS_ASAN_UBSAN
CANCELLATION_IDEMPOTENT=true
CAN_FREE_BEFORE_OUT_COMPLETION=false
CAN_FREE_AFTER_CANCELLED_OUT_COMPLETION=true
COMMIT_AFTER_CANCELLATION_COUNT=0
BACKEND_REAL_SUBMIT_COUNT=0
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
```

La cancellazione non invia comandi compensativi, non riapre il backend e non
ritenta. Questo prova il lifetime/drain host del solo OUT, non la quiescenza del
sensore o la correttezza live del workflow OEM.

## Confine residuo

Il binding non è ancora posseduto dal `GoodixDeviceContext`; nessun codice
production lo costruisce o lo invoca. Il prossimo passo autonomo può introdurre
ownership dormant e teardown ordinato nel context mantenendo il rifiuto
pre-activation di `FPI_DEVICE_ACTION_ENROLL`.

Il modello resta parametrico. Il valore 21 descrive gli stage riusciti
osservati sul target in ATTEMPT02, non una costante OEM universale. Il payload
B0 ausiliario continua a essere preservato e consegnato come dato opaco; il suo
eventuale ruolo quality/template/NBIS resta non determinato.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_DEVICE_CONTEXT_DORMANT_ENROLLMENT_OWNERSHIP_WITH_ACTIVATION_GATE
```
