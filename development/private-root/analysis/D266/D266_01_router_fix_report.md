# D266/01 — correzione offline del router eventi FDT

## Esito

```text
OUTCOME=D266_01_READY_FOR_AI_PM_REVIEW
ADVANCEMENT=CONCRETE_ROUTER_EVENT_CLASSIFICATION_FIXED_OFFLINE
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=0x22_AND_FIRST_IMAGE_REMAIN_NOT_LIVE_PROVEN
```

Lo step è stato eseguito sul branch `codex`, HEAD iniziale
`c68398db24c7a1689e3056b771df83b479a1c7ef`, senza USB reale, secret reale,
marker, fprintd o comandi device.

## Diff concettuale e contratto

Il router usava `_is_irq100()` come sinonimo di «evento», riconoscendo soltanto
A0 `control=0x36` con prefisso dati `00 01`. Il fix minimo lo sostituisce con
`_is_fdt_event()`, che:

1. valida l'outer frame con `parse_outer()`;
2. richiede `kind == PLAIN` (A0);
3. delega payload, checksum, famiglia control e IRQ a `parse_fdt_event()`.

Il parser canonico valida la famiglia FDT; il router applica poi una allowlist
più stretta di coppie control/IRQ target-specific osservate nelle capture:
IRQ100 manual-sample (`0x36/0x0100`), IRQ2 finger-down (`0x32/0x0002`) e
IRQ200 finger-up (`0x34/0x0200`). Non introduce una regola «ogni A0 è evento»
né promuove le ulteriori varianti generiche del parser senza evidenza target.
ACK `0xB0`, B0/TLS, response normali e altre combinazioni FDT restano
command-side.

Il router conserva un'unica lista ordinata di frame. Ogni consumer rimuove il
primo frame della propria vista: l'ordine relativo per vista è preservato e i
frame dell'altra vista restano accodati. `_read_lock`, limite di 64 frame e
deadline monotonic assoluta non sono stati modificati.

## Verifica sul router concreto

`tests/test_d266_irq_event_router.py` contiene otto test offline:

- IRQ `0x0100` e IRQ `0x0002` sono consegnati una volta da
  `SharedFrameRouter.receive_event()`;
- IRQ2 non viene consegnato da `receive_command()`;
- ACK, response A0 normale e A0 FDT non allowlisted dal router non vengono rubati
  dalla vista eventi;
- gli interleaving `command→event`, `event→command`,
  `command→IRQ2→command` e `IRQ100→command→IRQ2` terminano senza perdita,
  duplicazione o coda residua;
- frame dell'altra vista riducono il timeout residuo e non rinnovano la
  deadline;
- il tentativo reentrante riproduce
  `concurrent_physical_in_reader_forbidden`.

## Seam first-image concreto

La rehearsal usa soltanto fixture sintetiche:

```text
synthetic bulk-IN A0 IRQ2
→ SharedFrameRouter
→ _RouterEventSource
→ PersistentRuntimeCoordinator._run_first_image_terminal()
→ exactly one logical 0x22 [01 00]
→ synthetic ACK/B0/image 80x64
```

Il caso positivo produce un solo tentativo `0x22`, zero retry e zero famiglie
di scrittura persistente. Il caso senza IRQ2 termina sul timeout bulk-IN
sintetico con zero submit `0x22`. La fixture non può aprire libusb, leggere un
secret, mutare marker/fprintd o raggiungere hardware.

## Risultati test

- nuovi test D266: `8 PASS`;
- suite mirata router/runtime/first-image: `37 PASS`;
- regressione generale `unittest`: `282` eseguiti, `278 PASS`, `1 FAIL`,
  `3 ERROR`;
- i due esiti D261 (`18 PASS / 1 FAIL / 1 ERROR`) riproducono drift già
  documentato: classe eccezione capability e dry-run baseline drift;
- gli altri due errori sono import di moduli pytest-only D264/D265 con
  `pytest` non installato. Nessuna dipendenza è stata aggiunta;
- il test D261 pertinente al demux/deadline passa.

Nessun failure della regressione generale attraversa il nuovo classifier o i
test D266. Gli artefatti D260 rigenerati dal loro harness durante la suite sono
stati ripristinati byte-identici a HEAD e restano fuori dal diff.

## Limiti residui

La patch prova il routing software offline. Non prova che il device abbia
fisicamente emesso IRQ2 durante D265/02, non prova l'accettazione live del
fixed64 `0x22` e non prova la prima immagine live. L'autorizzazione D265/02
resta consumata e il retry resta vietato. Prima di qualunque nuova run servono
review AI-PM, eventuale merge, nuova baseline full-SHA esplicitamente
approvata e autorizzazione live separata.

```text
D265_02_RETRY_AUTHORIZED=false
DEVICE_IRQ2_PHYSICAL_EMISSION_DURING_D265_02=UNDETERMINED
0x22_FIXED64_LIVE_PROVEN=false
FIRST_IMAGE_LIVE_PROVEN=false
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED_FOR_NEW_ATTEMPT=false
```
