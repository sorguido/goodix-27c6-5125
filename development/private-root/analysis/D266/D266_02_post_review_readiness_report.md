# D266/02 — post-review execution-readiness

## Esito

```text
OUTCOME=D266_02_CORRECTIVE_REQUIRED
ADVANCEMENT=POST_ROUTER_FIX_OPERATOR_GATE_DEFECT_LOCALIZED_OFFLINE
EXECUTABLE_CLOSURE=FAIL
RESIDUAL_BLOCKER_OR_RISK=D265_DRY_RUN_PINS_PRE_D266_CORE_USB_RUNTIME_HASH
```

D266/02 è stato eseguito esclusivamente offline sul branch `codex`, a partire
da `7a2ceff54f2fc27332a9f2a531ce4af5d90cf9a2`. La review AI-PM di D266/01 è
recepita come `PASS` e il fix router è accettato. Il codice del router non è
stato modificato in questo step.

La massima readiness richiesta non è raggiunta: il dry-run ufficiale D265/01
fallisce correttamente chiuso sulla byte identity del router aggiornato. Non è
stata applicata una correzione live-critical nello step di ratifica.

## Integrità D266/01

Verificato:

- `analysis/D266/D266_01_irq_event_router_fix_bundle.zip` è un vero ZIP;
- non esiste alcun `.zip.b64` in `analysis/D266/`;
- il sidecar SHA-256 verifica il digest
  `9f2bce490597e35c7609b474d25c22f007cd6163a96d2cf447024001e2f24318`;
- `unzip -t` passa senza errori;
- il path-set ZIP coincide con `D266_01_bundle_manifest.json`;
- tutti i membri con hash dichiarato coincidono; il manifest stesso è coperto
  dall'hash esterno, come dichiarato;
- nomi e contenuto del review set non includono secret, plaintext TLS, raw USB,
  marker/cache protetta o dati biometrici; le sole occorrenze lessicali della
  scansione sono i flag sanitization impostati a `false` nel manifest;
- il delta Git `c68398db24c7a1689e3056b771df83b479a1c7ef` →
  `7a2ceff54f2fc27332a9f2a531ce4af5d90cf9a2` contiene il fix minimo
  `core/usb_runtime.py`, il nuovo test D266, manuale e artefatti D266/01. Nel
  live-critical set modifica soltanto il router previsto.

## Router e seam first-image

```text
IRQ100_CONCRETE_ROUTER_EVENT_DELIVERY=PASS
IRQ2_CONCRETE_ROUTER_EVENT_DELIVERY=PASS
NORMAL_COMMAND_ROUTING=PASS
INTERLEAVED_ROUTING_NO_LOSS=PASS
ABSOLUTE_DEADLINE_PRESERVED=PASS
SINGLE_PHYSICAL_IN_OWNER_PRESERVED=PASS
SYNTHETIC_IRQ2_TO_0x22_END_TO_END=PASS
NO_IRQ2_ZERO_0x22_ATTEMPTS=PASS
```

`python3 -m unittest -v tests.test_d266_irq_event_router` passa 8/8. La suite
mirata router/runtime/first-image passa 37/37. Queste sono prove offline su
fixture sintetiche e non diventano evidenza device-side.

## Audit del percorso operatore D265/01

L'audit statico conferma il percorso production:

```text
operator_kit/d265-first-image-once.sh
→ tools/d265_live_first_image_once.py
→ FutureProductionDependencies.construct_runtime()
→ LibusbRuntimeTransport
→ SharedFrameRouter + transport.event_source (_RouterEventSource)
→ PersistentRuntimeCoordinator.run(STOP_AFTER_FIRST_IMAGE)
```

Non è emerso un event source alternativo nel vero call graph. Restano invariati:

- opt-in first-image esatto e singolo;
- prompt dito emesso una volta immediatamente prima di `wait_event(15000)`;
- deadline IRQ2 assoluta/bounded nel router;
- nessun retry, recovery o reopen;
- `0x22` irraggiungibile prima della delivery e validazione IRQ2;
- `0x22` costruito come `build_finger_image()` e materializzato con policy
  operativa fixed64 zero-tail;
- cleanup TLS/secret/transport nel coordinator e restore segnali/fprintd nel
  wrapper restano indipendenti e fail-closed;
- nessuna famiglia di scrittura persistente introdotta dal delta D266.

Il dry-run ufficiale è stato eseguito da `/tmp` con:

```text
/home/guido/Repository/goodix-27c6-5125_private/operator_kit/d265-first-image-once.sh --dry-run
```

Esito osservato:

```text
D265_OPERATOR_DRY_RUN=FAIL_CLOSED
FAILURE=byte_identity:core/usb_runtime.py
REAL_USB_ACCESS_COUNT=0
REAL_SECRET_READ_COUNT=0
REAL_DEVICE_COMMAND_COUNT=0
MARKER_MUTATION_COUNT=0
FPRINTD_MUTATION_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

La causa è deterministica. Il manifest storico D265/01 attende SHA-256
`a19c0ffb93a7e1dc7d4b08a0fed9ed738a9d51bb72e4327d16a41b4cb15dc278`
per `core/usb_runtime.py`; il blob D266/01 accettato ha SHA-256
`c4e62b0786d7710eb0625b033258636597b9aa8f40259ce5a1f669b0e160385b`.
Il gate rifiuta quindi, come progettato, una tree diversa dalla propria autorità
D265. Questo preserva la safety ma impedisce l'executable closure post-fix.

Il corrective dovrà creare una nuova autorità candidate post-D266 e collegarla
al dry-run/verifier senza retro-modificare lo snapshot storico D265. Poiché ciò
incide sul gate live-critical, richiede uno step separato e nuova review.

## Regressione generale e gap ambientale

`python3 -m unittest discover -s tests -v` riproduce esattamente D266/01:
282 eseguiti, 278 PASS, 1 FAIL e 3 ERROR. I due esiti D261 sono il drift storico
della classe eccezione capability e del dry-run; gli altri due errori sono gli
import dei moduli pytest-only D264/03 e D265/01 con `pytest` assente. Nessun
failure è attribuibile al classifier D266.

`pytest` non è installato e non è stata aggiunta alcuna dipendenza. La verifica
statica conferma che il delta D266/01 non modifica
`tests/test_d264_03_prelive_operator.py`,
`tests/test_d265_live_first_image_once.py`, launcher/tool D265,
`core/future_first_image_operator.py`, `core/persistent_runtime.py` o
`core/post_d4.py`.

La suite generale rigenera tre JSON D260; sono stati riportati byte-identici a
HEAD e non compaiono nel diff finale D266/02.

## Stato e limiti

```text
D266_01_AI_PM_REVIEW=PASS
D266_01_ROUTER_FIX_ACCEPTED=true
D266_01_CORRECTIVE_REQUIRED=false
D266_02_LIVE_CRITICAL_CODE_CHANGE_COUNT=0
READY_FOR_NEW_BASELINE_APPROVAL_REVIEW=false
BASELINE_APPROVED_FOR_NEW_ATTEMPT=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
DEVICE_IRQ2_PHYSICAL_EMISSION_DURING_D265_02=UNDETERMINED
D265_02_RETRY_AUTHORIZED=false
0x22_FIXED64_LIVE_PROVEN=false
FIRST_IMAGE_LIVE_PROVEN=false
```

Nessun hardware, secret reale, marker, fprintd, cache protetta o stato device è
stato letto o modificato.
