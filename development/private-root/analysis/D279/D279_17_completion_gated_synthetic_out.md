<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/17 — transazione OUT sintetica completion-gated

## Esito

`goodix_enrollment_outbound_transaction.[ch]` collega il serializer a uno sink
astratto host-testable. La sequenza è strettamente:

```text
prepare → serialize fixed64 → one pending sink call
        → positive completion with same generation
        → lifecycle command commit → inbound ACK becomes expected
```

Il comando non viene committato al planner al momento del sink call. Doppio
OUT, inbound durante OUT pending, completion senza pending, generation stale,
errore di completion o sink rejection rendono la transazione terminale. Non
esiste retry automatico.

```text
OUTCOME=READY_OFFLINE_COMPLETION_GATED_SYNTHETIC_OUT
ADVANCEMENT=FULL_ITERATIVE_MODEL_WITH_TRANSACTIONAL_SYNTHETIC_OUT
ATTEMPT02_OBSERVED_STAGE_COUNT=21
OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
ATTEMPT02_PROFILE_SYNTHETIC_OUT_COUNT=125
REAL_BACKEND_DEPENDENCY=false
PRODUCTION_ENROLLMENT_ENABLED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Verifica

I profili 2/3/21 usano la transazione per ogni comando: nel profilo 21 tutti
i 125 fixed64 passano da sink e completion positiva prima del commit. La suite
combinata verifica inoltre generation stale e ACK anticipato, entrambi senza
commit. Passano 7/7 test normal e ASan/UBSan; l'audit sorgente/simboli esclude
il backend USB reale.

```text
D279_14_TO_17_TESTS=7/7_PASS_NORMAL;7/7_PASS_ASAN_UBSAN
ATTEMPT02_PROFILE_SYNTHETIC_FIXED64_BUILD_COUNT=125
ATTEMPT02_PROFILE_POSITIVE_COMPLETION_COUNT=125
ATTEMPT02_PROFILE_COMMIT_AFTER_COMPLETION_COUNT=125
STALE_GENERATION=FAIL_CLOSED_NO_COMMIT
EARLY_ACK_WHILE_OUT_PENDING=FAIL_CLOSED_NO_COMMIT
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
RETRY_COUNT=0
REAL_USB_SUBMIT_COUNT=0
EXECUTABLE_CLOSURE=PASS_SYNTHETIC_SINK_ONLY
```

La build production-shaped passa senza warning nuovi della transazione,
mantiene registry standard/NBIS e non enumera, apre, reclama o invia su USB.

## Confine residuo

La transazione non è collegata a `GoodixFpiUsbBackend`. Il successivo passo
offline può creare un binding production dormant, verificato solo con le seam
esistenti, lasciando intatto il rifiuto di `FPI_DEVICE_ACTION_ENROLL` prima
dell'attivazione. Abilitare o eseguire quel percorso resterà un Human Gate.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_DORMANT_ENROLLMENT_FPI_USB_BACKEND_BINDING_WITH_ACTIVATION_GATE
```
