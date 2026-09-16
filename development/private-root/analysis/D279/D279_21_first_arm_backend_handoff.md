<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/21 — handoff backend al confine del primo arm

## Esito

Il modello enrollment parametrico assume correttamente come primo inbound un
IRQ2, ma il protocollo deve prima completare il bootstrap post-TLS e l'arm
iniziale. `GoodixPostTlsLifecycle` espone ora un handoff opzionale configurato
prima dello start: dopo la completion fisica e l'ACK positivo del primo `0x32`,
rilascia il callback OUT e passa al nuovo owner prima di consumare IRQ2.

```text
OUTCOME=READY_OFFLINE_FIRST_ARM_HANDOFF_CONTRACT
ADVANCEMENT=EXCLUSIVE_BACKEND_OWNERSHIP_BOUNDARY_BEFORE_FIRST_IRQ2
DEFAULT_TWO_CAPTURE_PATH_CHANGED=false
PRODUCTION_HANDOFF_CALLER_PRESENT=false
PRODUCTION_ENROLLMENT_ACTIVATION_GATE=RETAINED
LIVE_EXECUTION_PERFORMED=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
```

## Contratto e verifica

L'handoff è accettato soltanto con lifecycle avviato, completion OUT già
ricevuta e backend OUT drenato. Il vecchio owner disinstalla il proprio callback
prima di invocare il successore, entra in STOP e non esegue retry o comandi
compensativi. Il free successivo non rimuove il callback del nuovo owner.

La fixture percorre i nove comandi host-only del bootstrap fino all'arm
iniziale, poi installa un nuovo callback e ne osserva una completion prima e
una dopo il free del lifecycle legacy.

```text
D278_12_PLUS_D279_21_TESTS=10/10_PASS_NORMAL;10/10_PASS_ASAN_UBSAN
BOOTSTRAP_COMMAND_COUNT_TO_FIRST_ARM_ACK=9
BOOTSTRAP_ACK_COUNT=8
IMAGE_DELIVERY_BEFORE_HANDOFF_COUNT=0
FINGER_EVENT_BEFORE_HANDOFF_COUNT=0
BACKEND_OUTSTANDING_AT_HANDOFF=0
NEW_OWNER_COMPLETION_AFTER_OLD_FREE=PASS
AUTOMATIC_RETRY_COUNT=0
HANDOFF_CALLBACK_REJECTION=TERMINAL_FAIL_CLOSED
FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
```

## Limiti

Il test non dimostra equivalenza temporale live. In ATTEMPT02 Windows ha
eseguito due re-entry dopo pause host lunghe; non è provato se un caller Linux
che prosegue subito ne abbia bisogno. L'handoff non è ancora configurato da
`GoodixDeviceContext` e nessun path production costruisce il grafo enrollment.

Il profilo resta parametrico: 21 è il numero di stage riusciti osservato sul
target in ATTEMPT02, non una costante OEM universale. Il payload B0 ausiliario
resta conservato opacamente e la sua funzione quality/template/NBIS non è
determinata.

```text
NEXT_PRIMARY_BOUNDARY=OFFLINE_CONTEXT_FIRST_ARM_HANDOFF_TO_PARAMETRIC_ENROLLMENT_GRAPH_WITH_LIBFPRINT_CALLBACKS_AND_GATE
```
