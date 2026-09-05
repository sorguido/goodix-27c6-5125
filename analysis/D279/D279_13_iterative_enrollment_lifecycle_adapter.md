<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/13 — adapter lifecycle enrollment iterativo, zero sender

## Esito

Il modello host-only raggiunge una composizione eseguibile completa delle
sequenze osservate: oracle parametrico, derivazione FDT dinamica e costruzione
dei body interni sono ora un'unica transazione `observe → prepare → commit`.
Il profilo 21 riproduce i 125 comandi enrollment-only di ATTEMPT02, ma il
numero 21 resta un input target-local e non una costante OEM universale.

```text
OUTCOME=READY_OFFLINE_ITERATIVE_LIFECYCLE_ADAPTER
ADVANCEMENT=MATERIAL_ARCHITECTURAL_AND_EXECUTABLE_ADVANCEMENT
CONFIGURABLE_STAGE_PROFILES=2;3;21
ATTEMPT02_OBSERVED_STAGE_COUNT=21
OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
AUXILIARY_B0_APPLICATION_SEMANTICS=UNDETERMINED
PRODUCTION_ENROLLMENT_ENABLED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Contratto transazionale

`goodix_enrollment_lifecycle_adapter.[ch]` accetta:

- IRQ2/IRQ0200 solo con la rispettiva sorgente FDT di 12 byte;
- PRIMARY_B0 solo con il raster canonico;
- gli altri eventi senza payload.

`prepare` risolve l'intent corrente, richiede il timestamp solo per `0x32`,
lega il materiale allo stage e costruisce esclusivamente il body interno.
L'output resta in cache fino a `commit`: un secondo `prepare` restituisce gli
stessi byte senza leggere un nuovo timestamp. Un'osservazione mentre esiste un
comando non committato o un commit di evento diverso rendono l'adapter
terminale. Non esistono retry automatici.

Il B0 ausiliario dopo `0x20` resta un evento protocol-internal nel primo
modello, ma il contenuto cifrato e l'eventuale ruolo in quality, template o
NBIS non sono determinati e non vengono dichiarati inutili.

## Verifica

La fixture percorre profili 2, 3 e 21 stage con raster e FDT sintetici. Nel
profilo target-local verifica 125 prepare/commit, 21 timestamp, 21 immagini,
21 derivazioni up/down, 41 risoluzioni `0x34`, 20 `0x36` previous-stage e 21
`0x32` current-stage. Ogni prepare viene ripetuto per provare la cache.

```text
D279_13_TESTS=3/3_PASS_NORMAL;3/3_PASS_ASAN_UBSAN
ATTEMPT02_PROFILE_COMMANDS=125
PREPARE_CACHE_TIMESTAMP_STABILITY=PASS
PENDING_COMMAND_OBSERVATION=FAIL_CLOSED
WRONG_PREPARED_COMMAND_COMMIT=FAIL_CLOSED
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
RETRY_COUNT=0
A0_FRAME_BUILD_COUNT=0
SUBMIT_COUNT=0
EXECUTABLE_CLOSURE=PASS_HOST_ONLY_ZERO_SENDER
```

La build production-shaped compila lo stesso sorgente contro Fedora 44 /
libfprint 1.94.100, mantiene la registrazione standard `27c6:5125` e NBIS e
non esegue enumerazione, open, claim o submit USB. I warning `switch-enum`
sono quelli storici di secure-session/post-TLS, non introdotti dall'adapter.

## Confine residuo

L'adapter non interpreta A0, non gestisce ACK/IRQ dal parser TLS production e
non raggiunge il backend. Il successivo confine offline è progettare e testare
il binding tra eventi post-TLS tipizzati e adapter, lasciando ancora separata
e disabilitata qualunque emissione production.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_POST_TLS_EVENT_BINDING_WITH_SENDER_GATE_RETAINED
```
