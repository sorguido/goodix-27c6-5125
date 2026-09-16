# D266/03 — nuova authority post-router e namespace one-shot D267

## Esito

```text
OUTCOME=D266_03_READY_FOR_AI_PM_BASELINE_REVIEW
ADVANCEMENT=POST_ROUTER_NEW_ONE_SHOT_AUTHORITY_CLOSED_OFFLINE
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=0x22_AND_FIRST_IMAGE_REMAIN_NOT_LIVE_PROVEN
```

Lo step è stato eseguito esclusivamente offline sul branch `codex`, partendo da
`65b8ec198603c347b89107fe5b7b28cf84fbd318` con worktree pulito. Branch,
parent, ref remote e bundle D266/02 corrispondevano alle precondizioni del
prompt. Nessun USB reale, secret reale, TLS live, marker reale, servizio fprintd
o comando device è stato raggiunto.

## Decisione D266/02 e immutabilità D265

La review D266/02 è recepita come `PASS_AS_FAIL_CLOSED_AUDIT`. Il dry-run D265
ha rifiutato correttamente il router post-fix perché la propria authority
storica conserva il blob pre-D266. Non è un difetto del fail-closed gate.

I tre file storici richiesti sono byte-identici a HEAD:

| File | SHA-256 |
| --- | --- |
| `analysis/D265/D265_01_live_critical_manifest.json` | `c1cb60cce1deb9a43008c3adf6f8e179df1f01fb6aabd3318a6374d8630dc673` |
| `operator_kit/d265-first-image-once.sh` | `d4f49fc2699790984175e5feea505f712194ebce2a4baac30715e57e9dd70bf6` |
| `tools/d265_live_first_image_once.py` | `f5501cf1d90bb5b2b873c7a22f8d41b4db23c6b96bffd2ce1243b71665dab1e4` |

`D265_02_RETRY_AUTHORIZED=false` e nessun marker/flag/report D265 viene
riutilizzato dal nuovo path.

## Nuova authority D267

Il candidate usa:

```text
launcher  = operator_kit/d267-first-image-once.sh
tool      = tools/d267_live_first_image_once.py
live flag = --i-authorize-one-d267-first-image-live-attempt
baseline  = D267_APPROVED_LIVE_BASELINE_SHA
marker    = /var/lib/goodix-5125-poc/d267-first-image-single-use.marker
report    = /var/lib/goodix-5125-poc/d261-results/d267-first-image-final.json
```

L'authority contiene 20 file: i due entrypoint e 18 dipendenze transitivamente
live-critical della call graph production. Include il router accettato D266:

```text
core/usb_runtime.py
sha256=c4e62b0786d7710eb0625b033258636597b9aa8f40259ce5a1f669b0e160385b
```

Il manifest dichiara `baseline_approved=false`. Il verifier live non si affida
agli hash mutabili del JSON: richiede full commit SHA lowercase, risoluzione
commit esatta, `HEAD == approved SHA`, worktree pulito, tuple autoritativa
esatta e byte identity commit/worktree di ogni file.

## Capability e call graph

Classi e nonce D267 sono distinti da D261 e D265. I test provano entrambe le
direzioni di rigetto: D265 non può mintare marker/live-I/O D267 e D267 non può
mintare il path D265. Il marker viene creato `O_EXCL`/`0600`, scritto
completamente e fsyncato prima del minting; la marker capability è one-shot.

La call graph production verificata è:

```text
D267 launcher/tool
→ D267ProductionDependencies
→ CtypesLibusbBackend
→ LibusbRuntimeTransport
→ SharedFrameRouter
→ _RouterEventSource
→ PersistentRuntimeCoordinator(STOP_AFTER_FIRST_IMAGE)
```

Esiste un solo proprietario fisico EP81 e nessun event-source bypass. La wait
IRQ2 mantiene la deadline assoluta di 15000 ms; il prompt dito avviene una sola
volta immediatamente prima di quella wait. Senza IRQ2 vi sono zero tentativi
`0x22`; con IRQ2 sintetico ve n'è esattamente uno. Il candidate `0x22` resta
`FIXED64_ZERO_TAIL`, senza retry, recovery, reopen o nuova famiglia di write
persistente. Cleanup, zeroizzazione e restore restano indipendenti.

## Executable closure e test

Il launcher è stato eseguito da `/tmp`:

```text
D267_OPERATOR_DRY_RUN=PASS
REAL_USB_ACCESS_COUNT=0
REAL_SECRET_READ_COUNT=0
REAL_DEVICE_COMMAND_COUNT=0
MARKER_MUTATION_COUNT=0
FPRINTD_MUTATION_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_TLS_HANDSHAKE_COUNT=0
```

Risultati:

- nuovi unittest D266/03: 21/21 PASS;
- router D266: 8/8 PASS;
- suite mirata router/runtime/first-image: 37/37 PASS;
- discovery completa: 303 eseguiti, 299 PASS, 1 FAIL, 3 ERROR;
- i quattro esiti non-PASS sono le classi D261/pytest già note; zero failure
  nuovi sono attribuibili a D266/03;
- pytest non è stato installato.

I tre JSON D260 rigenerati meccanicamente dalla discovery sono stati
ripristinati byte-identici a HEAD e restano fuori dal delta.

## Riesame metodologico pre-live

1. Il metodo cambia realmente perché il router accettato consegna ora IRQ2
   nella call graph concreta D267 e l'authority one-shot non riusa D265.
2. Una futura run separatamente approvata testerebbe se IRQ2 fisico raggiunge
   `_RouterEventSource` e se l'unico `0x22` fixed64 è accettato dal target.
3. Se fallisse ancora nella wait IRQ2, non si ripeterebbe lo stesso tentativo:
   si fermerebbe il live e si cercherebbe evidenza capace di discriminare
   emissione fisica e delivery host prima di definire un metodo diverso.

## Readiness massima

```text
D266_01_ROUTER_FIX_ACCEPTED=true
D266_02_FAIL_CLOSED_AUDIT_ACCEPTED=true
D265_HISTORICAL_MANIFEST_UNCHANGED=PASS
D265_HISTORICAL_OPERATOR_UNCHANGED=PASS
D265_MARKER_NAMESPACE_NOT_REUSED=PASS
D267_AUTHORIZATION_NAMESPACE_DISTINCT=PASS
D267_MARKER_NAMESPACE_DISTINCT=PASS
D267_OPERATOR_DRY_RUN=PASS
D267_OPERATOR_CANDIDATE_READY_OFFLINE=true
D266_ROUTER_POST_FIX_HASH_PINNED=PASS
READY_FOR_NEW_BASELINE_APPROVAL_REVIEW=true
BASELINE_APPROVED_FOR_NEW_ATTEMPT=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
D265_02_RETRY_AUTHORIZED=false
DEVICE_IRQ2_PHYSICAL_EMISSION_DURING_D265_02=UNDETERMINED
0x22_FIXED64_LIVE_PROVEN=false
FIRST_IMAGE_LIVE_PROVEN=false
```

Il manuale canonico è aggiornato organicamente. Il bundle di review è
`analysis/D266/D266_03_post_router_authority_corrective_bundle.zip`; il digest
esterno è registrato nel sidecar omonimo `.sha256` per evitare ricorsione.
