# D278/05 — causal cut pre-OUT, recovery OEM e sticky `POISONED`

## Closure

```text
OUTCOME=READY
ADVANCEMENT=CROSS_SESSION_CAUSAL_BOUNDARY_CLOSED_OFFLINE_AND_OPEN_EPOCH_POISON_MADE_STICKY_HOST_ONLY
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=DEVICE_PROTOCOL_QUIESCENCE_AFTER_INTERRUPTED_SESSION_UNPROVEN;CROSS_SESSION_FRAME_CAUSAL_IDENTITY_UNPROVEN;OEM_PRE_D1_FAILURE_RECOVERY_UNRESOLVED;ZERO_OUT_DIAGNOSTIC_REQUIRES_SEPARATE_REVIEW_AND_AUTHORIZATION
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_a2d59808ac4b6d3b9a6608bd7b29e329fa42a03e_ON_main_PLUS_CURRENT_WORKTREE_DIFF_PLUS_analysis/D278/D278_05_cross_session_reentry_resolution.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_libfprint-driver/goodix_fpimage_device.c_PLUS_libfprint-driver/tests/test_goodix_fpimage_device.c

ORCHESTRATION_WORK_USED=false
ORCHESTRATION_IGNORED_BYTECODE_RESIDUE=OBSERVED_NONCANONICAL
CROSS_SESSION_REENTRY_ARCHITECTURAL_GAP=PROVEN
CROSS_SESSION_RX_RESIDUAL_CAUSAL_IDENTITY=UNPROVEN
POST_A8_WIRE_CAUSAL_PROVENANCE=UNAVAILABLE
PRECOMMAND_FRAME_EXCLUDES_CURRENT_HOST_COMMAND_CAUSATION=true
PRECOMMAND_FRAME_PREVIOUS_SESSION_IDENTITY=UNPROVEN
OEM_PRE_D1_FAILURE_RECOVERY=UNRESOLVED
POISON_AFTER_NONQUIESCENT_TERMINAL_MUST_BE_STICKY=true
AUTOMATIC_REENTRY_FROM_POISONED=false
FUTURE_ZERO_OUT_PRECOMMAND_DIAGNOSTIC=JUSTIFIED_FOR_SEPARATE_REVIEW
ZERO_OUT_DIAGNOSTIC_IMPLEMENTED=false
ACK_POLICY_CORRECTIVE_REFUTED=false
ACK_POLICY_CORRECTIVE_LIVE_RETESTED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
DO_NOT_RUN_AGAIN=true
```

## Baseline, scope e divergenza non canonica

La root reale è il clone Git corrente, branch `main`, con baseline iniziale
pulita:

```text
BASELINE_HEAD=a2d59808ac4b6d3b9a6608bd7b29e329fa42a03e
BASELINE_ORIGIN_MAIN=a2d59808ac4b6d3b9a6608bd7b29e329fa42a03e
D278_03_POST_CORRECTIVE_LIVE_CRITICAL_BASELINE=4e5d74770bce6e0a9de929b19279038827abff8c
POST_LIVE_CRITICAL_BASELINE_TRACKED_CHANGES=MANUAL_AND_D278_03_D278_04_DOCUMENTATION_ONLY
```

Nessun sorgente o artefatto O001/O002/O003 è versionato nel tree corrente.
Sono tuttavia presenti file bytecode `.pyc` ignorati sotto
`orchestration/**/__pycache__/`, inclusi nomi O002/O003. Sono residui locali
non canonici della parentesi abbandonata: non sono stati letti come autorità,
eseguiti, modificati o inclusi nel review set.

Il task è stato interamente offline. Non sono stati aperti device USB, eseguiti
launcher live, letti store protetti o inviati comandi. Non sono stati usati
`sudo`, rete, reset, clear-halt, retry, reopen, drain, parser permissivi o dati
biometrici. I cinque file live-critical congelati dal prompt non sono stati
modificati. `goodix_fpimage_device.c` non è referenziato né compilato dal
launcher/harness D278/03 e la patch non è quindi transitiva nel path live
D278/03.

## Classificazione

- **OBSERVED**: telemetria target delle due single-shot D278/03.
- **VERIFIED**: proprietà ripetibile di sorgenti, wire contract, test o
  capture locali.
- **INFERRED**: conseguenza necessaria o fortemente sostenuta da più fatti, ma
  non osservata direttamente.
- **HYPOTHESIZED**: spiegazione compatibile non discriminata.
- **UNKNOWN**: corpus insufficiente.

## A. Ricostruzione causale dei terminal point D278/03

### Prima single-shot

| Fase | OUT | ACK | Typed response | Frame asincroni / residui plausibili | Classe |
| --- | --- | --- | --- | --- | --- |
| A8 | trasmesso | consumato e accettato | consumata e validata APP12509 | nessuno osservato | `OBSERVED` dai contatori e dal phase trace |
| E4 | trasmesso | il primo IN E4 è stato consumato dal parser ma non accettato; la shape/status esatti non furono telemetrizzati, status `0x07` resta inferenza storicamente corroborata | non consumata | typed E4 eventualmente già generata, in emissione tardiva o pendente lungo device/controller/kernel; altra emissione device-side ignota | OUT e assenza di typed consumata `OBSERVED`; identità ACK `INFERRED`; produzione/ubicazione typed `HYPOTHESIZED/UNKNOWN` |

I tre IN completati della prima run sono compatibili con ACK A8, typed A8 e
primo frame E4. La run chiuse fence/cancel/release/close dopo quel primo frame
E4, senza protocol close, reset o power-cycle provato. La **typed response E4
non consumata** è quindi il candidato residuale più forte, ma non è provato che
fosse già stata prodotta né dove fosse collocata.

### Seconda single-shot

Prima della nuova A8 erano logicamente compatibili:

1. la typed response E4 della prima run già pending;
2. una emissione E4 tardiva causata dalla prima run;
3. stato APP12509 non quiescente che emette un frame E4-shaped in relazione al
   nuovo traffico senza che esso sia la response memorizzata precedente;
4. dati già bufferizzati lungo endpoint/controller/kernel;
5. altra emissione asincrona device-side non modellata.

Questi sono candidati, non identità dimostrate. Nella seconda run sono invece
`OBSERVED`: nuovo open/claim, nuovo A8 OUT, poi un solo IN
`A0/E4/body_length=41`; nessun ACK o typed A8 è stato consumato e la run è
terminata fail-closed.

Dopo quel terminale il backlog non può essere descritto semplicemente come
“vecchia E4”. Poiché la nuova A8 era già stata trasmessa, sono ora candidati
anche un ACK A8 e una typed response A8 prodotti dalla seconda attività, oltre
agli elementi residui o tardivi precedenti. Generazione, ordine di submit host
e ownership del transfer non identificano la causa dei byte.

### Limite informativo dopo A8

Il wire A0 porta framing, control, length/body e checksum. L'ACK A8 porta echo
e status; la typed A8 porta la shape/versione APP12509. Il wrapper B0 porta
tipo, lunghezza e checksum del wrapper TLS. Nessuno dei due contratti porta
nonce, session ID, open epoch, process ID o timestamp causale device-side.
Inoltre A8 e la risposta APP12509 sono byte-stabili fra run equivalenti.

Di conseguenza una coppia ACK A8 + typed A8 causalmente precedente che arriva
dopo un nuovo A8 è semanticamente indistinguibile da una coppia corrente che
soddisfi gli stessi contratti:

```text
POST_A8_WIRE_CAUSAL_PROVENANCE=UNAVAILABLE
```

Un parser più permissivo non recupererebbe provenance: nasconderebbe il
boundary.

## B. Causal cut pre-OUT

La proposizione debole è valida per causalità host-command:

> Dopo nuovo open/claim e prima di qualsiasi OUT della nuova command stream,
> un frame ricevuto non può essere una risposta causata da un comando host di
> quella stream, perché nessun comando corrente è stato trasmesso.

Essa non identifica l'origine alternativa. Il frame può derivare da attività
precedente, emissione device-side autonoma o tardiva, o buffering non
localizzato. Perciò:

```text
PRECOMMAND_FRAME_EXCLUDES_CURRENT_HOST_COMMAND_CAUSATION=true
PRECOMMAND_FRAME_PREVIOUS_SESSION_IDENTITY=UNPROVEN
```

### Valutazione del futuro diagnostico zero-OUT

Il solo design metodologicamente distinto giustificato per review separata è:

```text
open/claim -> begin host generation -> exactly one bounded bulk-IN -> ZERO OUT
-> complete full frame OR bounded timeout/no frame -> cleanup -> STOP
```

Un frame completo produrrebbe nuova evidenza perché proverebbe la disponibilità
di dati **prima** della prima causa host-command corrente. Non proverebbe quale
sessione, comando, buffer o emissione device-side li abbia causati. Un timeout
proverebbe soltanto che nessun frame completo è arrivato entro quel singolo
bound: non prova FIFO permanentemente vuota, assenza di frame ritardati,
quiescenza APP12509 o readiness per A8.

Il bulk-IN non è un peek: può consumare dati. Il massimo ammissibile per questo
design è un submit IN e una completion, con al più un frame logico completo e
nessun secondo receive. Frame incompleto, dati extra/concatenati o errore sono
terminali e conservati come classificazione; non autorizzano un loop. Telemetria
minima: contatori open/claim/release/close, OUT=0, IN submit/completion <=1,
timeout/error, byte count, complete/incomplete/extra, outer/control/body length,
cleanup/drain e contatori retry/reopen/reset/persistent-write a zero. Nessun
payload sensibile è necessario.

```text
FUTURE_ZERO_OUT_PRECOMMAND_DIAGNOSTIC=JUSTIFIED_FOR_SEPARATE_REVIEW
```

La classificazione non implementa né autorizza la live. Anche dopo silenzio
precommand restano separati:

```text
ENDPOINT_OR_OBSERVATION_WINDOW_SILENT
!=
APP12509_PROTOCOL_STATE_READY_FOR_NEW_A8
```

Non viene progettato alcun drain di produzione.

## C. Audit recovery OEM/Windows

Il corpus locale prova il normale cold-start Windows APP12509
`A8 -> E4 -> A2 {01,14} -> ...`, ma un cold-start riuscito non è recovery da
failure. D231 ricostruisce `A2 {01,14}` come reset volatile del solo sensore nel
path OEM ordinario; non prova che Windows lo usi dopo un failure A8/E4.

La statica di `gfusb.dll` 1.1.125.14 contiene primitive e branch generali di
recovery: il transport presenta retry bounded su timeout/ACK, `SetDriverState`
ha due tentativi e un ramo descritto come hard reset MCU, esistono handler
D0Entry/D0Exit e `gfresetMCUAndfingerprint`. Questi fatti non sono collegati da
un call-flow locale chiuso al ritorno di failure di A8/E4 o alla specifica
catena pre-D1 APP12509. Le stringhe non provano l'esecuzione dei rami.

D255/D256 osservano una diversa classe, post-D1/FDT: cancel host di un bulk-IN,
re-entry OEM con query/init e nuovo `0x32`, senza reset/clear-stall/re-enumeration
USB osservati. Non è prova di recovery da init failure. Rocky corrobora solo
primitive generali e non è autorità target-specific.

Il corpus non contiene una capture/log OEM di timeout, response inattesa,
failure pre-D1 o init failure seguita dalla decisione di retry/reset/D0/reopen.
Manca inoltre un call graph completo dal failure callback A8/E4 fino alla
policy superiore, inclusi numero di tentativi, timing e traffico effettivo.

```text
OEM_PRE_D1_FAILURE_RECOVERY=UNRESOLVED
```

## D. Sticky `POISONED` nel production-shaped C

### Discrepanza verificata

Il contratto D276 richiede che un terminale non quiescente avveleni il restante
open epoch. Il codice precedente marcava `ctx->poisoned = TRUE`, ma ogni nuova
`goodix_fpimage_device_activate()` azzerava `terminal_fence` e `poisoned`, poi
creava una generation e raggiungeva il backend. Il gate era quindi realmente
aggirabile dopo il completamento framework del terminale.

### Correttivo minimo

`activate()` ora accetta lo stato `POISONED` soltanto per fallire chiuso: prima
di mutare qualsiasi gate, cancellable o generation, restituisce l'errore
terminale preservato (o un errore protocollo redatto). Non azzera più
`poisoned`. Nessun recovery, reset o nuovo stato complesso è stato introdotto.
Activation pulite continuano lungo il path precedente; `img_close` distrugge
il `GoodixDeviceContext` e resta il boundary dell'open epoch.

```text
POISON_AFTER_NONQUIESCENT_TERMINAL_MUST_BE_STICKY=true
AUTOMATIC_REENTRY_FROM_POISONED=false
POISON_LIFETIME=REMAINDER_OF_OPEN_EPOCH_UNTIL_IMG_CLOSE
```

Il test focalizzato prova: activation pulita; terminal poison; seconda
activation rifiutata; zero nuova generation; zero nuovi comandi backend, IN o
OUT submit; fence/poison preservati; callback stale ed evento fake incapaci di
riabilitare il contesto; distruzione del contesto a close. Le regressioni
esistenti continuano a coprire activation pulite, cancellazione e generation
stale.

## E. Modello di re-entry

| Stato | Ingresso | Azioni ammesse | Azioni vietate / uscita |
| --- | --- | --- | --- |
| `CLEAN` | nuovo contesto/open epoch senza poison | normale activation secondo contratti già provati | un terminale non quiescente porta a `POISONED`; close porta a `TERMINAL` |
| `POISONED` | error/cancel con quiescenza device non provata | cleanup/drain host e `img_close` | nessuna activation, generation, command, USB submit, retry, TLS restart o reopen implicito |
| `REENTRY_OBSERVATION_CANDIDATE` | solo futuro design separatamente revisionato, dopo nuovo open/claim e prima di OUT | un solo receive bounded, classificazione e stop | non è uno stato production, non scarta frame e non autorizza A8 |
| `TERMINAL` | stop/close o fine del diagnostico | cleanup e report | nessun resume; un nuovo contesto è una nuova decisione, non prova quiescenza |

`PRECOMMAND_SILENCE` non equivale a `DEVICE_PROTOCOL_QUIESCENT`. D278/05 non
autorizza alcun resume production.

## Riesame metodologico pre-live

1. **Cosa cambierebbe realmente?** Un futuro zero-OUT osserva prima di ogni
   OUT corrente; le due D278/03 precedenti avevano già trasmesso A8 quando
   ricevevano il primo frame. È quindi un metodo causalmente diverso, non una
   variazione di pacing o logging.
2. **Quale nuova ipotesi testerebbe?**
   `PENDING_OR_DELAYED_FRAME_EXISTS_BEFORE_ANY_CURRENT_COMMAND_OUT`.
3. **Se non osservasse frame o fallisse?** Stop dopo quella sola observation;
   nessun A8 nello stesso run e nessun loop equivalente. L'azione successiva è
   offline: chiudere il call graph OEM pre-D1 o cercare un discriminante di
   protocol-state già nel corpus. Un timeout non promuove il device a ready.

Questo riesame non crea un launcher, non seleziona una baseline e non autorizza
hardware.

## Verifiche host-only

```text
FPIMAGE_DEVICE_STRICT_BUILD=PASS
FPIMAGE_DEVICE_NORMAL=16/16_PASS
FPIMAGE_DEVICE_ASAN_UBSAN=16/16_PASS
D276_04_NORMAL=5/5_PASS
D276_04_ASAN_UBSAN=5/5_PASS
D276_03_ROUTER_NORMAL=8/8_PASS
D276_03_ROUTER_ASAN_UBSAN=8/8_PASS
GOODIX_FPIMAGE_DEVICE_FORBIDDEN_SYMBOL_AUDIT=PASS
REAL_USB_TRANSFER_SUBMIT_COUNT=0
REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
GIT_DIFF_CHECK=PASS
```

Il primo avvio della suite `FpImageDevice` nel sandbox è terminato prima della
build perché Flatpak/bwrap non poteva creare `NETLINK_ROUTE`. La stessa suite
host-only è stata eseguita fuori sandbox nel runtime Freedesktop SDK 25.08 ed è
passata; lo stub compile/link abortirebbe se un submit USB reale venisse
raggiunto. Le regressioni D276 sono state eseguite nello stesso runtime con
rete disabilitata.
