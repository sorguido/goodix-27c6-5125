<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/24 — handoff enrollment posseduto dal context

## Esito

Il `GoodixDeviceContext` compone ora, dietro configurazione esplicita offline,
il bootstrap post-TLS D279/21 e il binding parametrico D279/23.

```text
OUTCOME=READY_OFFLINE_CONTEXT_OWNED_FIRST_ARM_HANDOFF
ADVANCEMENT=POST_TLS_BOOTSTRAP_TO_PARAMETRIC_ENROLLMENT_CONTEXT_OWNERSHIP
PRODUCTION_ENROLLMENT_ENABLED=false
PRODUCTION_CONFIGURATION_CALLER_PRESENT=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Ownership e routing

- prima dello start il context possiede un event layer preparato ma nessun
  binding e non effettua submit;
- il lifecycle legacy invoca l'handoff soltanto dopo il primo `0x32/ACK`, con
  OUT zero e callback backend rilasciato;
- il binding acquisisce l'event layer e il context diventa l'unico owner;
- A0 e plaintext TLS successivi sono instradati al binding;
- dopo una completion OUT positiva la callback del binding ri-arma un IN solo
  se il grafo attende input;
- failure/cancellazione applicano la terminal fence e il free attende drain.

La regressione attraversa nove comandi bootstrap, otto ACK più la risposta AF,
effettua un solo handoff e instrada il primo IRQ2 tramite il router del context.
Il primo comando enrollment `0x22` resta completion-gated; dopo il commit viene
ri-armata la ricezione protocollo. La cancellazione con IN pendente drena prima
della distruzione.

```text
POST_TLS_BOOTSTRAP_COMMAND_COUNT=9
FIRST_ARM_HANDOFF_COUNT=1
FIRST_ENROLLMENT_IRQ2_COUNT=1
FIRST_ENROLLMENT_GRAPH_READY_SUBMIT_COUNT=1
OUT_COMMIT_BEFORE_COMPLETION=0
POST_COMPLETION_PROTOCOL_RX_REARM=PASS
FPIMAGE_DEVICE_TESTS=27/27_PASS_NORMAL;27/27_PASS_ASAN_UBSAN
D279_14_TO_24_TESTS=10/10_PASS_NORMAL;10/10_PASS_ASAN_UBSAN
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
AUTOMATIC_RETRY_COUNT=0
CONFIGURABLE_STAGE_PROFILES=2;3;21
ATTEMPT02_OBSERVED_STAGE_COUNT=21
OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
AUXILIARY_B0_APPLICATION_SEMANTICS=UNDETERMINED
```

Il test di composizione usa due stage per ridurre il costo, ma non rende due o
21 una costante universale. Il B0 ausiliario continua a essere affidato a un
consumer opaco obbligatorio; la sua rilevanza applicativa non è determinata.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_CONTEXT_FULL_PARAMETRIC_ENROLLMENT_TRANSCRIPT_AND_LIBFPRINT_STAGE_DELIVERY_WITH_GATE
```
