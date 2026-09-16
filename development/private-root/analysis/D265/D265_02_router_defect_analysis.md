# D265/02 — analisi deterministica del difetto router IRQ2

## Baseline analizzata

Commit eseguito e HEAD iniziale:
`2e57aa95cbe7d5eb468c12882cfa3a1a4d457e6d`.

| File | Git blob | SHA-256 |
| --- | --- | --- |
| `core/usb_runtime.py` | `50a71487ebf45ae7a8c49cbe04013c042d910c65` | `a19c0ffb93a7e1dc7d4b08a0fed9ed738a9d51bb72e4327d16a41b4cb15dc278` |
| `core/persistent_runtime.py` | `9a1ae5a8b06106f7620d8ca3395aedb088209728` | `42efbc29d2cebc06d3a83fd37cb410d9412dd6d20f0ffc7e3348338a70d79641` |
| `tools/d265_live_first_image_once.py` | `dba083b094d166b2d3be650372541862fc137247` | `f5501cf1d90bb5b2b873c7a22f8d41b4db23c6b96bffd2ce1243b71665dab1e4` |

Il confronto `git diff --exit-code <baseline> -- <tre file>` è PASS e gli
SHA-256 dei blob estratti dal commit coincidono con la working tree iniziale.

## Catena causale byte-level

In `core/usb_runtime.py`, `_is_irq100(frame)` restituisce true soltanto se:

```text
outer kind = PLAIN
payload control = 0x36
len(data) >= 2
data[0:2] = 00 01
```

`SharedFrameRouter._pop(event=True)` seleziona un frame se e solo se
`_is_irq100(frame) is True`; `receive_event()` usa esattamente questa vista.
Ogni altro frame valido, incluso un logical A0/FDT IRQ `0x0002`, resta nel lato
`event=False` e può essere restituito da `receive_command()`.

Il concrete adapter `_RouterEventSource.wait_event()` chiama direttamente
`router.receive_event(timeout_ms)`. In `core/persistent_runtime.py` il path
first-image esegue:

```text
wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS=15000)
→ parse FDT event
→ require event.irq == 2
→ increment IRQ2 counter
→ only then attempt 0x22
```

`tools/d265_live_first_image_once.py` avvolge questo event source con
`PromptingEventSource`: alla prima wait da 15000 ms stampa il prompt e delega
allo stesso `wait_event()`. Non cambia frame, predicato o queue selection.

## Conseguenza deterministica

```text
physical IRQ 0x0100 -> _is_irq100=true  -> event queue -> runtime
physical IRQ 0x0002 -> _is_irq100=false -> non-event  -> NOT runtime event
```

Se IRQ2 arriva, resta accodato nel lato command e l'event wait prosegue; se non
arriva, la wait prosegue allo stesso modo. In entrambi i casi il timeout EP81 è
compatibile con l'osservazione live. Perciò l'emissione fisica IRQ2 è
indeterminabile dalla telemetria D265/02.

## Riproduzione offline sul router concreto

Una fixture ha fornito al `SharedFrameRouter` un singolo frame IRQ2 sintetico e
poi ha sollevato `TimeoutError:libusb_bulk_timeout:0x81` sul bulk-IN successivo.
Risultato:

```json
{
  "command_delivery_count": 1,
  "event_delivery_count": 0,
  "fixture": "SYNTHETIC_OFFLINE",
  "irq2_is_irq100": false,
  "physical_in_calls": 2,
  "queued_after_event_wait": 1,
  "receive_command_then_delivers_irq2": true,
  "receive_event_result": "TimeoutError:libusb_bulk_timeout:0x81"
}
```

Questa prova conferma il comportamento del codice eseguito; non è evidenza di
un IRQ2 reale nella run.

## Gap dei test precedenti

- `tests/test_d263_phase2_first_image_terminal.py` usa `ScriptedEventSource` e
  consegna direttamente IRQ2 al coordinator.
- `tests/test_d263_phase2_public_run.py` costruisce frame/event source
  sintetici e non attraversa `SharedFrameRouter`.
- `tests/test_d264_03_prelive_operator.py` integra il coordinator con event
  source sintetici; non usa il demux libusb reale per IRQ2.
- `tests/test_d265_live_first_image_once.py` prova il decorator del prompt con
  delegate sintetici.
- L'harness D261 usa il router concreto, ma i frame classificati come eventi
  sono esclusivamente IRQ `0x0100`, esattamente la classe supportata dal
  predicato corrente.

La distinzione conclusiva è:

```text
prompt timing logic = correct
real router event classification = incomplete for IRQ2
```

## Decisione

`D265_02_ROUTER_IRQ2_DELIVERY_DEFECT=PROVEN_FROM_EXECUTED_BASELINE`.
`DEVICE_IRQ2_PHYSICAL_EMISSION_DURING_D265_02=UNDETERMINED`.
`D265_02_FIRST_IMAGE_PATH_WAS_SOFTWARE_BLOCKED_BEFORE_0x22=true`.

Nessun code fix è applicato in D265/02. La correzione richiede uno step
offline successivo con test del router concreto, review AI-PM, merge, nuova
baseline full-SHA esplicitamente approvata e nuova autorizzazione live.
