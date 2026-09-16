<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/23 — progressione enrollment nei command slot

## Esito

Il binding host-testabile collega ora gli input accettati alla successiva
azione outbound del grafo senza richiedere un pump esterno generico.

```text
OUTCOME=READY_OFFLINE_GRAPH_READY_PROGRESSION
ADVANCEMENT=PARAMETRIC_GRAPH_TO_COMPLETION_GATED_BINDING
PRODUCTION_ENROLLMENT_ENABLED=false
PRODUCTION_CALLER_PRESENT=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Contratto

- dopo un A0 accettato o un messaggio plaintext completo, il binding legge il
  prossimo evento tipizzato;
- soltanto `COMMAND_20/22/32/34/36/50` causano un singolo submit;
- IRQ, ACK, NAV, B0 e plaintext frammentario non causano submit;
- il comando resta pending e non viene commit finché il backend non completa
  positivamente la stessa generazione;
- non esiste retry automatico; errore, input durante OUT o completion stale
  restano fail-closed.

La regressione del primo confine osserva auto-submit `0x22` dopo IRQ2, zero
commit prima della completion, un solo commit dopo completion positiva e
nessun nuovo submit dopo ACK `0x22`, quando il grafo attende il B0 primario.
I primi due byte del B0 non inviano; il resto completa il messaggio, consegna
l'immagine e produce esattamente il secondo submit (`0x34`).

```text
D279_14_TO_23_TESTS=10/10_PASS_NORMAL;10/10_PASS_ASAN_UBSAN
FPIMAGE_DEVICE_REGRESSION=26/26_PASS_NORMAL;26/26_PASS_ASAN_UBSAN
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
GRAPH_READY_SUBMIT_COUNT_AFTER_IRQ2=1
GRAPH_READY_SUBMIT_COUNT_AFTER_PARTIAL_PRIMARY_B0=1
GRAPH_READY_SUBMIT_COUNT_AFTER_COMPLETE_PRIMARY_B0=2
COMMIT_BEFORE_COMPLETION=0
AUTOMATIC_RETRY_COUNT=0
CONFIGURABLE_STAGE_PROFILES=2;3;21
ATTEMPT02_OBSERVED_STAGE_COUNT=21
OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
AUXILIARY_B0_APPLICATION_SEMANTICS=UNDETERMINED
```

Il prossimo confine è l'ownership nel `GoodixDeviceContext` al callback
first-arm D279/21. Quel passaggio resta offline e non autorizza la rimozione
del gate production enrollment.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_CONTEXT_OWNED_FIRST_ARM_HANDOFF_TO_PARAMETRIC_ENROLLMENT_GRAPH_WITH_GATE
```
