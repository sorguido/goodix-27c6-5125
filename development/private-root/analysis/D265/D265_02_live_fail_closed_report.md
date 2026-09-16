# D265/02 — post-mortem live fail-closed

## Esito

`OUTCOME=D265_02_LIVE_FAIL_CLOSED` e
`ADVANCEMENT=D265_02_FAILURE_LOCALIZED_TO_PRE_0x22_EVENT_DELIVERY`.
L'unico live autorizzato è stato eseguito e consumato sulla baseline
`2e57aa95cbe7d5eb468c12882cfa3a1a4d457e6d`. Questo step è esclusivamente
offline: nessun retry, accesso USB, secret read, marker/service mutation o
comando device è stato eseguito durante il post-mortem.

## Evidenza live primaria

La telemetria terminale sanitizzata registra una sola invocazione, marker
claimed, una apertura USB, una sessione transport, un oggetto e handshake TLS,
una materializzazione secret e un final FDT arm. Dopo il prompt dito la wait si
è chiusa con `TimeoutError:libusb_bulk_timeout:0x81`.

```text
FINAL_FDT_ARM_COUNT=1
IRQ2_FINGER_DOWN_COUNT=0
COMMAND_22_ATTEMPT_COUNT=0
COMMAND_22_ACK_VALIDATION_COUNT=0
FIRST_B0_COUNT=0
RETRY_COUNT=0
RECOVERY_COUNT=0
REOPEN_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
FORBIDDEN_POST_IMAGE_COMMAND_COUNT=0
HOST_CLEANUP_STATUS=COMPLETED
SECRET_ZEROIZED=true
```

L'operatore riferisce di aver appoggiato il dito dopo
`D265_OPERATOR_ACTION = APPOGGIA_UN_DITO_ORA`; non vi è stato output immediato
e il fail-closed è comparso dopo alcuni secondi. La descrizione non è una
misura di timing e non prova che il device abbia emesso IRQ2.

## Report protetto già prodotto

La lettura operatore, effettuata senza nuovo traffico USB, del report protetto
`/var/lib/goodix-5125-poc/d261-results/d265-first-image-final.json` conferma:

```text
PROTECTED_REPORT_PRESENT=true
PROTECTED_REPORT_RESULT=FAIL_CLOSED
PROTECTED_REPORT_FAILURE_CLASS=TimeoutError:libusb_bulk_timeout:0x81
PROTECTED_REPORT_RETRY_COUNT=0
PROTECTED_REPORT_DESTINATION_PREFLIGHT_PASSED=true
SECRET_OWNERSHIP_TRANSFERRED_TO_COORDINATOR=true
```

Il JSON non espone lo stato fprintd. Pertanto
`FPRINTD_RESTORE_STATUS=SEE_OPERATOR_REPORT_NOT_DIRECTLY_PROVEN_BY_PROTECTED_JSON`;
non viene inferito `PASS`.

## Localizzazione della failure

La baseline consegna a `SharedFrameRouter.receive_event()` soltanto i frame che
`_is_irq100()` riconosce come A0 `control=0x36` con data prefix `00 01`. Il
runtime first-image attende invece un evento FDT e procede solo se
`event.irq == 2`. Il decorator D265 stampa il prompt immediatamente prima della
wait da 15000 ms e delega al vero event source: la prompt timing logic è
corretta e non causa la classificazione.

Quindi, sulla baseline eseguita:

- se IRQ2 arriva fisicamente, il router lo lascia nella vista non-event e la
  wait continua fino al timeout;
- se IRQ2 non arriva fisicamente, la stessa wait termina comunque in timeout.

Il live non può distinguere i due casi. La failure è localizzata al delivery
software pre-`0x22`, non al device e non alla policy fisica di `0x22`.

```text
D265_02_ROUTER_IRQ2_DELIVERY_DEFECT=PROVEN_FROM_EXECUTED_BASELINE
DEVICE_IRQ2_PHYSICAL_EMISSION_DURING_D265_02=UNDETERMINED
D265_02_FIRST_IMAGE_PATH_WAS_SOFTWARE_BLOCKED_BEFORE_0x22=true
```

## Interpretazione safety e stato

`0x22` non è mai stato inviato. Il live non ne prova né smentisce
l'accettazione target; nessuna first image è stata raggiunta. Lo stato interno
device dopo D265/02 non è osservabile e resta `UNKNOWN`. Non risultano retry,
recovery, reopen, write persistenti o comandi post-image vietati. Cleanup host
completato e secret zeroizzato sono osservati nella telemetria terminale.

```text
0x22_FIXED64_LIVE_PROVEN=false
FIRST_IMAGE_LIVE_PROVEN=false
POST_D265_02_DEVICE_INTERNAL_STATE=UNKNOWN
LIVE_AUTHORIZATION_CONSUMED=true
D265_02_RETRY_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED_FOR_NEW_ATTEMPT=false
```

## Test gap e verifiche offline

La fixture D265 `PromptingEventSource` delega a un event source sintetico nei
test. Anche le suite first-image D263/D264 iniettano `ScriptedEventSource`; non
attraversano il router libusb concreto. Gli harness D261 attraversano
`SharedFrameRouter`, ma i casi evento usano solo IRQ `0x0100`. Manca quindi il
test di integrazione in cui un logical A0/FDT IRQ2 passa da
`SharedFrameRouter.receive_event()` al first-image runtime.

Verifiche eseguite senza hardware:

- confronto byte-exact dei tre file richiesti con il commit eseguito: PASS;
- fixture diretta sul router concreto: IRQ2 non consegnato da
  `receive_event()`, timeout osservato, IRQ2 successivamente consegnato dalla
  vista command: PASS;
- `python3 -m unittest` D263 first-image/public run: 18/18 PASS;
- D265 `--dry-run` da cwd esterno: PASS, tutti i side-effect counter reali a 0;
- `pytest`: non disponibile nell'ambiente (`No module named pytest`);
- suite storica D261: 18 PASS, 1 FAIL e 1 ERROR per drift/metadata già presenti
  nella baseline corrente e fuori scope; il suo test demux concreto passa ma
  copre soltanto IRQ `0x0100`.

`TEST_GAP_CLASSIFICATION=SYNTHETIC_EVENT_SOURCE_BYPASS_AND_MISSING_CONCRETE_ROUTER_IRQ2_INTEGRATION_TEST`.
Nessuna correzione di codice è inclusa in D265/02.
