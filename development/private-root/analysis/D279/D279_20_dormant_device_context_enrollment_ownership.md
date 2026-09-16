<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/20 — ownership dormant enrollment nel device context

## Esito

Il `GoodixDeviceContext` può adottare un binding enrollment già costruito solo
nel perimetro operator-epoch host-only, sulla stessa generation e sullo stesso
backend. L'adozione è esclusa se secure session, TLS o lifecycle post-TLS legacy
sono presenti, evitando contesa sul singolo callback OUT del backend.

```text
OUTCOME=READY_OFFLINE_DORMANT_CONTEXT_OWNERSHIP
ADVANCEMENT=CONTEXT_OWNS_CANCEL_DRAIN_AND_COMPLETE_ENROLLMENT_GRAPH
CONTEXT_CONSTRUCTS_BINDING=false
CONTEXT_SUBMITS_BINDING=false
PRODUCTION_CALLER_PRESENT=false
PRODUCTION_ENROLLMENT_ACTIVATION_GATE=RETAINED
LIVE_EXECUTION_PERFORMED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Lifetime e failure

Una costruzione binding riuscita prende ownership di
`GoodixEnrollmentPostTlsEvents`; dopo l'adozione il context possiede quindi il
grafo completo. Il terminal fence cancella il binding in modo idempotente e il
free del context verifica prima che backend e OUT del binding siano drenati.
La regressione mantiene un OUT sintetico outstanding durante lo stop dell'epoch,
verifica cancellation singola e zero commit, consegna la completion cancellata
e solo allora distrugge context, binding, events, backend e router.

```text
D279_14_TO_20_TESTS=9/9_PASS_NORMAL;9/9_PASS_ASAN_UBSAN
FPIMAGE_DEVICE_TESTS=26/26_PASS_NORMAL;26/26_PASS_ASAN_UBSAN
PENDING_OUT_AT_CONTEXT_STOP=1
COMMIT_AFTER_CONTEXT_CANCEL_COUNT=0
CONTEXT_FREE_AFTER_BACKEND_DRAIN=true
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
```

La build e i test usano soltanto seam host-only. Il context non costruisce il
binding, non serializza e non invia. La vfunc production continua a respingere
enrollment prima di allocare una generation.

## Confine residuo

L'ownership non risolve ancora l'handoff tra secure session/post-TLS legacy e
il nuovo grafo enrollment, né collega le callback di avanzamento/completion a
libfprint. Questi punti richiedono un design offline che garantisca ownership
esclusiva del callback backend e conservi il gate production prima di qualsiasi
abilitazione live.

Il valore 21 resta un profilo target-local osservato in ATTEMPT02, non una
costante OEM universale. Il B0 ausiliario viene preservato opacamente; un suo
ruolo in quality, template o NBIS rimane indeterminato.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_SECURE_TO_ENROLLMENT_HANDOFF_AND_LIBFPRINT_CALLBACK_DESIGN_WITH_ACTIVATION_GATE
```
