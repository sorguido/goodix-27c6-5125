# D278/04 — audit del cross-session protocol re-entry, riconciliato con la seconda single-shot live

## Esito esecutivo

L'audit statico separa il drain dei transfer host dalla provenance causale dei
byte: la generation C prova l'ownership e il drain dei transfer host; non
codifica la causalità dei byte consegnati da un transfer nuovo e non prova che
endpoint e protocollo device siano quiescenti dopo una sessione interrotta. Un
callback della generation corrente può quindi, per costruzione, consegnare byte
semanticamente prodotti prima della generation e il parser li attribuisce alla
fase corrente. Questo boundary architetturale è dimostrato staticamente.

La seconda single-shot live D278/03, autorizzata ed eseguita una sola volta
dall'Utente sulla baseline post-corrective, aggiunge un fatto nuovo che questo
audit non possedeva: sul target APP12509, in una **nuova** sessione e in fase
`A8`, il primissimo frame IN ricevuto è stato `outer=0xA0`, `control=0xE4`,
`body_length=41`, cioè con control e lunghezza compatibili con la typed response
E4 canonica, ma senza verifica del body completo; non era l'ACK A8 atteso. Il fenomeno descritto dall'audit come rischio
architetturale è pertanto ora **osservato sul target**.

Resta però non provato che quel frame *sia* la typed response E4 rimasta dalla
run precedente: il wire contract non contiene nonce/session ID e il body E4
canonico è funzione del materiale protetto persistente, non di un valore
per-run. La classificazione primaria è quindi tripartita:

```text
CROSS_SESSION_REENTRY_ARCHITECTURAL_GAP=PROVEN
TARGET_UNEXPECTED_PRIOR_PHASE_SHAPE_AT_REENTRY=OBSERVED

OBSERVED_REENTRY_FRAME_OUTER=0xA0
OBSERVED_REENTRY_FRAME_CONTROL=0xE4
OBSERVED_REENTRY_FRAME_BODY_LENGTH=41
OBSERVED_REENTRY_FRAME_MATCHES_CANONICAL_E4_CONTROL_AND_LENGTH=true

CROSS_SESSION_RX_RESIDUAL_TARGET_HYPOTHESIS=STRONGLY_LIVE_CORROBORATED
CROSS_SESSION_RX_RESIDUAL_CAUSAL_IDENTITY=UNPROVEN
```

Il gap architetturale è `PROVEN` perché l'assenza di un contratto di provenance
e il limite host-only del drain sono verificabili staticamente; il fencing
rifiuta correttamente i callback host stale e non esiste un overlap host
deterministico, quindi il difetto non è host-side ma di attribuzione causale.
L'osservazione target è `OBSERVED` come struttura del primo IN al re-entry, non
come catena causale. La causal identity è `UNPROVEN` e non va promossa.

La seconda run ha inoltre trasmesso un solo comando (`command_count=1`, solo
A8) e non ha raggiunto l'E4 della sessione corrente. Il correttivo della policy
ACK D278/03 non è quindi né refutato né ritestato live:

```text
ACK_POLICY_CORRECTIVE_REFUTED=false
ACK_POLICY_CORRECTIVE_LIVE_RETESTED=false
```

## Baseline, scope e safety

Comandi Git iniziali dell'audit statico originario, eseguiti read-only:

```text
REPOSITORY_ROOT=/home/guido/Repository/goodix-27c6-5125_private
BRANCH=main
STATUS=clean; main...origin/main
BASELINE_MAIN=5fbbe3f37d09d2b9f41e4a3906a2a759e8122f21
CURRENT_HEAD=5fbbe3f37d09d2b9f41e4a3906a2a759e8122f21
HEAD_MESSAGE=docs: update post-corrective closure details and enhance launcher verification process
BASELINE_CONTAINED_IN_CURRENT_HISTORY=true
POST_BASELINE_LIVE_CRITICAL_CHANGE_COUNT=0
```

Baseline del presente micro-correttivo documentale, che riconcilia il report con
la seconda single-shot live già eseguita dall'Utente:

```text
CORRECTIVE_BASELINE_MAIN=6544e408e3eb39b2e33f1442ad5407577c05b149
CORRECTIVE_SCOPE=DOCUMENTATION_AND_EVIDENCE_RECONCILIATION_ONLY
CORRECTIVE_CODE_CHANGED=false
CORRECTIVE_TESTS_CHANGED=false
CORRECTIVE_LIVE_EXECUTION_PERFORMED=false
```

Sono stati letti integralmente `AGENTS.md`, le linee guida di progetto e il
prompt D278/04, oltre alle sezioni pertinenti del manuale e agli artefatti
D242–D278 indicati sotto. Né l'audit né questo correttivo hanno eseguito USB
reale, launcher live, `sudo`, accesso allo store protetto, build, test,
self-test, reset, clear-halt, retry, reopen o comandi sensor-reaching. Non sono
stati modificati runtime, sorgenti, test, launcher o artefatti storici: la
seconda single-shot è stata autorizzata ed eseguita esclusivamente dall'Utente
sul proprio host e qui viene soltanto incorporata come evidenza.

## Classificazione dell'evidenza

- `OBSERVED`: telemetria/capture live versionata relativa al target.
- `VERIFIED`: proprietà dimostrabile da codice, test o artefatto locale.
- `INFERRED`: conclusione causale ragionevole ma non direttamente osservata.
- `HYPOTHESIZED`: scenario compatibile con i fatti, senza catena causale
  sufficiente.
- `UNKNOWN`: comportamento non stabilito dalle fonti disponibili.
- `EXTERNAL_GENERAL_USB_SEMANTICS`: semantica upstream generale; non è
  `APP12509_TARGET_PROOF`.

## Ricostruzione storica

### D242–D245: A8 non era un generic pre-drain

D242, D243 e D244 aprirono ciascuno una sola sessione USB, inviarono un solo
comando E4 e fallirono sul bulk-IN con timeout prima di un frame completo. I
report registrano `command_count=1`, `usb_open_count=1`, zero retry e nessun
handshake TLS. Il cleanup post-D241/D242/D243 era release/close/reseal host:
non comprendeva device reset, USB reset, A2 reset, re-enumeration, protocol
close o power-cycle. D244 documentò un fresh host boot ma non una rimozione
elettrica dell'alimentazione del sensore
(`D244_SENSOR_POWER_CYCLE_ELECTRICALLY_PROVEN=false`). Evidenza:
`analysis/D242/D242_operator_live_stdout.json`,
`analysis/D243/D243_operator_live_stdout.json`,
`analysis/D244/D244_operator_live_stdout.json` e
`analysis/D244/D244_initial_state_audit.md`.

D245 cambiò la sequenza inserendo l'exact A8 read-only prima dell'E4. In
`analysis/D245/D245_live_unseal.patch::_exchange_a8_precondition` l'ordine è:
open/claim se necessario, identity revalidation, A8 OUT, `read_frame()` per
l'ACK, un secondo `read_frame()` per la risposta tipata APP12509, controllo
del buffer e poi E4. Non esiste alcuna lettura, loop di drain o flush prima
dell'A8.

`src/goodix5125_d233_backend.py::ProductionUsbTransport.read_frame` mantiene
`_rx` per tutta la singola istanza transport, ricompone esattamente un frame e
lascia gli eventuali byte concatenati nel buffer. D245 richiedeva poi
`transport.buffered_rx_bytes == 0`; un residuo diventava
`stale_or_unowned_frame` e bloccava E4. Non veniva scartato né classificato
come appartenente a una sessione precedente. La regola provava solo
`USERSPACE_REASSEMBLY_BUFFER_EMPTY` in quel punto della sessione D245, non la
coda kernel/endpoint prima dell'A8.

Il successo live D245 osservò A8 ACK `0x07`, risposta tipata esatta APP12509,
E4 match e continuazione fino al TLS in una singola run. Gli artefatti canonici
limitano correttamente il ruolo causale:

```text
D245_A8_SEMANTIC_CLASS=TARGET_LIVE_PROVEN_READ_ONLY_PRECONDITION_DISCRIMINATOR
D245_A8_INITIALIZER_STATUS=NOT_PROVEN
D245_A8_CAUSAL_ROLE=PRECONDITION_OBSERVED_BEFORE_SUCCESSFUL_E4_NOT_DEVICE_INITIALIZATION_PROVEN
```

Evidenza: `analysis/D245/D245_A8_E4_primary_evidence_audit.md`,
`analysis/D245/D245_final_report.md` e
`analysis/D245/D245_A8_E4_contract.json`. D245 non prova A8 come reset, wake,
flush, initializer o sincronizzatore cross-session.

### D266: routing semantico intra-sessione

Il difetto D266 era una classificazione troppo stretta degli eventi: il router
Python trattava come evento solo IRQ100 e lasciava IRQ2 nella vista command.
`core/usb_runtime.py::_is_fdt_event` introdusse parsing FDT e allowlist
`0x32/IRQ2`, `0x34/IRQ0200`, `0x36/IRQ0100`.
`core/usb_runtime.py::SharedFrameRouter` mantiene un solo bulk-IN fisico, una
lista ordinata e due viste logiche che estraggono il primo frame semanticamente
compatibile. Un frame dell'altra vista resta accodato; non è scartato.

Questa proprietà risolve interleaving command/event nella stessa istanza
runtime. Non esistono session ID, open epoch, process ID o causal timestamp
wire. Il router non può riconoscere che un A0/B0 valido provenga da un open o
processo precedente. Evidenza:
`analysis/D266/D266_01_router_fix_report.md`,
`core/usb_runtime.py::SharedFrameRouter` e
`core/usb_runtime.py::_is_fdt_event`.

### D268–D275: le due immagini restano nella stessa sessione

D268 osservò la prima immagine nella stessa sessione aperta per cold start,
secure-session, D4, AF/FDT, IRQ2, `0x22` e B0. D275 estese lo stesso
`PersistentRuntimeCoordinator` a release tail, NAV/re-arm e seconda immagine.
La closure live D275/04 registra:

```text
usb_transport_session_count=1
tls_server_session_object_count=1
tls_server_handshake_count=1
secret_boundary_handoff_count=1
retry_count=0
transport_reopen_after_tls=false
second_server_session_created=false
phase_reached=STOP_AFTER_SECOND_IMAGE
```

La traccia `D4 → AF → IRQ2 → 0x22 → first B0 → 0x34 → IRQ0200 →
0x20 → post-up B0 → NAV 0x50 → re-arm 0x32 → IRQ2 → 0x22 → second B0`
non contiene un nuovo processo, open o handshake. Evidenza:
`analysis/D268/D268_02_post_live_first_image_closure_report.md`,
`analysis/D268/D268_02_live_evidence_summary.json`,
`analysis/D275/D275_01_offline_linux_multiframe_bridge_report.md` e
`analysis/D275/D275_04_second_b0_live_closure.{md,json}`.

Esistono sessioni storiche separate fra D241 e D245, ma con tentativi e boot
intervenuti e senza osservazione della coda endpoint o del primo frame
cross-session. Non costituiscono un esperimento controllato di abort a metà
secure-session seguito immediatamente da nuovo open/A8.

### D276: generation e drain sono host-only

`libfprint-driver/goodix_fpi_usb_backend.c::pending_new` cattura la generation
al submit. `goodix_fpi_usb_backend_complete_receive` consuma il token IN solo
se `submit_generation == in_generation` e consegna al router solo se il
terminal fence non è chiuso e la generation coincide con quella corrente.
OUT segue la stessa regola. `goodix_fpi_usb_backend_begin_generation` rifiuta
una generation nuova finché i contatori IN/OUT host non sono zero.

`goodix_fpi_usb_backend_cancel` chiude il fence, cancella il `GCancellable` e
notifica drained solo quando tutti i callback matching hanno restituito i
token. Questo prova:

```text
OLD_CALLBACK_FROM_GENERATION_N_CANNOT_CONSUME_GENERATION_N_PLUS_1_TOKEN=true
HOST_ASYNC_IO_DRAIN=PROVEN_HOST_ONLY
```

Non prova invece:

```text
NEW_CALLBACK_GENERATION_N_PLUS_1_RECEIVING_OLD_DEVICE_CAUSAL_DATA_PREVENTED=false
```

Il secondo marker nega deliberatamente la garanzia di prevenzione: un transfer
N+1 che riceve dati prodotti causalmente prima della generation ha comunque il
token N+1 e supera tutti i check correnti. È un fatto statico sul boundary, non
un'osservazione; l'osservazione target del fenomeno arriva soltanto dalla
seconda single-shot documentata sotto, che però non ne prova la provenance.
`goodix_usb_router_begin_generation` e
`goodix_usb_router_cancel` azzerano soltanto il `GByteArray pending` userspace.

Gli artefatti D276 dichiarano già
`DEVICE_PROTOCOL_QUIESCENCE=UNRESOLVED` e nessun comando cancel device-side
provato. I test `async-in-cancel-drain`, router `stale-generation` e
`stale-callback-generation-guard` modellano callback host con generation
vecchia; non modellano un callback nuovo che riceve dati causalmente vecchi.
Evidenza: `analysis/D276/D276_04_native_tls_fpi_usb_host_only.{md,json}`,
`libfprint-driver/goodix_fpi_usb_backend.c`,
`libfprint-driver/goodix_usb_router.c`,
`libfprint-driver/goodix_fpimage_device.c` e i rispettivi test.

### D277/D278: ownership del primo RX nativo corrente

D277/02 provò sul target una sessione pulita e bounded: una open/claim, exact
A8, due receive sequenziali per ACK e risposta tipata, una release/close, zero
retry/reopen. Non partiva da un abort a metà secure-session e quindi non prova
il re-entry. Evidenza: `analysis/D277/D277_02_native_a8_real_usb.{md,json}`.

Nel vero entrypoint D278,
`tools/d278_native_secure_session_once.c::run_live_once`, una sola
open/claim crea il harness. `tools/goodix_d278_harness.c::goodix_d278_harness_start`
esegue nell'ordine:

```text
goodix_usb_router_begin_generation
goodix_fpi_usb_backend_begin_generation
goodix_secure_session_new
goodix_fpi_usb_backend_arm_receive
goodix_secure_session_start  # submit A8 OUT
```

Il primo IN è quindi armato prima del submit A8. Inoltre
`tools/goodix_d278_harness.c::D278_GENERATION` vale `1` per ogni nuovo processo:
non è un epoch globale cross-processo. Anche un contatore globalmente univoco,
comunque, identificherebbe il submit host e non la causalità dei byte. Il path
production più generale
`libfprint-driver/goodix_fpimage_device.c::goodix_device_context_start_secure_session`
ha un ordine locale diverso (start session, poi arm receive), ma non è
l'entrypoint live D278/03 e neppure quell'ordine attribuirebbe provenance
causale ai byte.

`libfprint-driver/goodix_secure_session.c::goodix_secure_session_handle_a0`
parsa ogni A0 valido nella fase corrente. Un ACK deve avere body di due byte,
echo della control attesa e status ammesso; la risposta tipata deve rispettare
control e shape/hash della fase. Un frame valido ma semanticamente di un'altra
fase termina fail-closed per echo/control/shape inattesi; non viene ignorato.
Un vecchio ACK A8 seguito dalla vecchia risposta APP12509, ricevuti da un
transfer della generation corrente mentre la nuova sessione è in A8, sono
indistinguibili da una coppia corrente perché il wire contract non contiene un
nonce/session ID. Questo è il controesempio statico che rende H5 falsa come
garanzia universale.

La prima run D278/03 osservò A8 PASS, E4 OUT sent e terminale sul primo IN E4,
con una open/claim/release/close, `physical_in_completion_count=3`,
`physical_out_completion_count=2`, zero retry/reopen/reset e backend drained.
Non registrò lo status ACK E4. Il report correttivo individua la divergenza
ACK C/D238, corroborata storicamente, come causa primaria con status corrente
non direttamente telemetrizzato. La telemetria di *quella* run non osservava
alcun frame cross-session. Evidenza:
`analysis/D278/D278_03_native_secure_session_live_result_20260829.json` e
`analysis/D278/D278_03_e4_ack_policy_corrective.md`.

Quella run terminò però proprio sul primo IN di E4: la typed response E4 attesa
subito dopo l'ACK non fu mai letta, e la sessione fu chiusa con cancel/fence,
release e close host-side, senza alcun protocol close, reset o power-cycle
device provato. È esattamente la condizione di partenza che l'audit descrive
come re-entry non protetto.

### Seconda single-shot D278/03: il fenomeno è osservato sul target

Dopo la review AI-PM del correttivo ACK, l'Utente ha autorizzato ed eseguito
esattamente una seconda single-shot live sulla baseline live-critical
post-corrective, con il nuovo launcher candidate. La provenance è:

```text
REPOSITORY_HEAD_AT_AUTHORIZATION=5fbbe3f37d09d2b9f41e4a3906a2a759e8122f21
LIVE_CRITICAL_BASELINE=4e5d74770bce6e0a9de929b19279038827abff8c
LAUNCHER_SHA256=bf7a1b0dae42d1c17b613c3f03338d10c3448be622e8bc46383f1923f56f192d
LIVE_RC=1
LIVE_LOG=/tmp/d278_03_native_secure_session_second_single_shot_20260829.log
LIVE_LOG_SHA256=647b3c21f6954440fa29e54d6d31c29647d4d8434d08bc46f73dae1d8c553c5a
LIVE_AUTHORIZATION_CONSUMED=true
RETRY_AUTHORIZED=false
DO_NOT_RUN_AGAIN=true
CURRENT_LIVE_AUTHORIZED=false
```

Terminal JSON osservato:

```text
result=fail
failure_class=SECURE_SESSION_TERMINAL
reached_phase=TERMINAL
phase_trace=A8,TERMINAL
current_live_authorized=false
live_authorization_consumed=true

usb_open_attempt_count=1
usb_open_count=1
usb_claim_count=1
usb_release_count=1
usb_close_count=1

real_usb_submit_count=2
physical_in_submit_count=1
physical_in_completion_count=1
physical_out_submit_count=1
physical_out_completion_count=1
max_outstanding_bulk_in=1
max_outstanding_bulk_out=1

command_count=1
ack_count=0
typed_response_count=0

protocol_failure_phase=A8
protocol_failure_kind=TYPED_SHAPE_MISMATCH
observed_outer_type=160
observed_a0_control=228
observed_ack_echo=-1
observed_ack_status=-1
observed_body_length=41

D278_03_SECOND_SINGLE_SHOT_LOCAL_E4_BINDING_MATCH=true
D278_03_SECOND_SINGLE_SHOT_LIVE_E4_TYPED_MATCH=NOT_REACHED
tls_handshake_count=0
tls_established=false
secret_handoff_count=0
project_secret_zeroized=true

retry_count=0
transport_reopen_count=0
device_reset_count=0
persistent_device_write_count=0

d4_reachable=false
application_data_count=0
finger_wait_count=0
image_count=0

backend_drained=true
terminal_cleanup_completed=true
real_usb_access=1
synthetic_in_submit_count=0
synthetic_out_submit_count=0
```

Lettura strutturale. La sessione era nuova: una sola open/claim, una sola
release/close, un solo OUT (`command_count=1`, cioè soltanto A8) e un solo IN.
Quel singolo IN, atteso come ACK A8 (`echo=0xA8`, body di due byte), è stato
invece `outer=0xA0` (160), `control=0xE4` (228), `body_length=41`, senza campi
ACK (`observed_ack_echo=-1`, `observed_ack_status=-1`, `ack_count=0`,
`typed_response_count=0`). Il parser ha fallito chiuso con
`protocol_failure_kind=TYPED_SHAPE_MISMATCH` in `protocol_failure_phase=A8` e la
run è terminata a `phase_trace=A8,TERMINAL`, con cleanup completo, zero retry,
zero reopen, zero reset, zero scritture persistenti e secret azzerato.

Compatibilità di control e lunghezza, verificabile staticamente. In
`libfprint-driver/goodix_secure_session.c::validate_typed` la typed response E4
canonica ha `control=0xE4` e body di `9 + 32 = 41` byte (prefisso
`00 03 00 02 bb 20 00 00 00` più i 32 byte del validator). Al re-entry sono
stati osservati lo stesso control e la stessa lunghezza; il body completo non è
stato telemetrizzato e quindi non è stato verificato byte-exact:

```text
OBSERVED_REENTRY_FRAME_OUTER=0xA0
OBSERVED_REENTRY_FRAME_CONTROL=0xE4
OBSERVED_REENTRY_FRAME_BODY_LENGTH=41
OBSERVED_REENTRY_FRAME_MATCHES_CANONICAL_E4_CONTROL_AND_LENGTH=true
CANONICAL_E4_TYPED_BODY_LENGTH_SOURCE=libfprint-driver/goodix_secure_session.c::validate_typed
```

Perché la causal identity resta `UNPROVEN`. Il frame è stato rifiutato in fase
A8 per control inatteso, quindi i 41 byte non sono stati confrontati con il
validator della sessione corrente; e anche un confronto byte-esatto non
deciderebbe nulla, perché il validator E4 è `material->e4_validator`, derivato
dal materiale protetto persistente e pinnato per SHA-256, identico fra le run e
privo di qualsiasi componente per-run. Il wire contract A0 non contiene nonce,
session ID, epoch o timestamp causale. Restano quindi compatibili con
l'osservazione almeno queste spiegazioni, non discriminabili con la telemetria
disponibile:

1. residuo cross-session: la typed response E4 prodotta durante la prima run,
   mai letta, consegnata al primo transfer della nuova sessione;
2. emissione tardiva / stato di protocollo APP12509 non quiescente lato device
   (un frame della fase precedente emesso in risposta alla nuova A8, senza che
   sia stato inviato alcun E4 nella seconda run: solo A8, `command_count=1`);
3. dato bufferizzato lungo la catena kernel/host-controller attraverso
   release/close/open/claim;
4. altra origine device-side non discriminabile con la telemetria disponibile.

L'ipotesi (1) è la più naturale e ora fortemente corroborata dai fatti live —
la run precedente aveva lasciato pendente esattamente una typed response E4 e
la nuova sessione ha ricevuto per primo esattamente quella shape — ma nessuna
delle quattro è esclusa. Di conseguenza:

```text
CROSS_SESSION_REENTRY_ARCHITECTURAL_GAP=PROVEN
TARGET_UNEXPECTED_PRIOR_PHASE_SHAPE_AT_REENTRY=OBSERVED
CROSS_SESSION_RX_RESIDUAL_TARGET_HYPOTHESIS=STRONGLY_LIVE_CORROBORATED
CROSS_SESSION_RX_RESIDUAL_CAUSAL_IDENTITY=UNPROVEN
THAT_FRAME_WAS_DEFINITELY_THE_PREVIOUS_RUN_E4_TYPED_RESPONSE=UNPROVEN
```

Effetto sul correttivo ACK. La run ha inviato un solo comando e non ha raggiunto
l'E4 della sessione corrente: nessun ACK è stato ricevuto (`ack_count=0`),
quindi la tabella per fase `0x01|0x07` non è stata esercitata sul target. Il
correttivo non è contraddetto da questa run e non è stato ritestato live:

```text
ACK_POLICY_CORRECTIVE_REFUTED=false
ACK_POLICY_CORRECTIVE_LIVE_RETESTED=false
CURRENT_RUN_E4_ACK_07_NOT_DIRECTLY_TELEMETRIZED=true
```

Effetto sulle chiusure target. La seconda run non prova E4, TLS, D4, finger o
image: `d4_reachable=false`, `tls_established=false`, `application_data_count=0`,
`image_count=0`. L'autorizzazione live è consumata e nessun retry equivalente è
autorizzato.

## Decisione A–G

| Boundary | Storico | C corrente | Evidenza | Decisione | Residuo |
| --- | --- | --- | --- | --- | --- |
| A. `HOST_ASYNC_TRANSFER_DRAIN` | Python sincrono: nessun token async; cleanup release/close | cancel/fence e ritorno di tutti i callback matching | `goodix_fpi_usb_backend_cancel`, `complete_receive`, `complete_out`; D276/04 | `VERIFIED: PROVEN_HOST_ONLY` | non dice nulla sulla causalità dei byte o sul device |
| B. `USERSPACE_REASSEMBLY_BUFFER_EMPTY` | D245 verifica `_rx == 0` dopo exact ACK+typed A8; extra byte è failure | `goodix_usb_router_begin_generation/cancel` azzerano `pending`; il parser conserva partial corrente | D245 patch; `goodix_usb_router.c` | `VERIFIED_HOST_SIDE` | non svuota coda kernel/endpoint e non classifica provenance |
| C. `KERNEL/USB_ENDPOINT_PENDING_DATA` | nessuna telemetria o reset endpoint in D242–D245 | nessuna query/asserzione sulla FIFO endpoint | report storici; API USB sotto; seconda single-shot | `UNKNOWN_TARGET_SPECIFIC` | il primo IN al re-entry è ora osservato inatteso, ma la catena kernel/controller/device non è discriminata |
| D. `DEVICE_PROTOCOL_QUIESCENCE` | cleanup non prova protocol close/reset; fresh host boot non prova power-cycle sensore | nessun cancel device-side provato; context diventa poisoned/unknown | D244 initial-state audit; D276/04; `goodix_fpimage_device.c`; seconda single-shot | `UNRESOLVED_WITH_ADVERSE_LIVE_INDICATION` | dopo un abort a metà secure-session la nuova sessione ha ricevuto una shape della fase precedente; stato APP12509 comunque non provato |
| E. `SAME_SESSION_SEMANTIC_ROUTING` | D266 prova viste command/event con un solo reader | router C prova A0/B0 framing; secure-session applica phase contract | D266 report; `SharedFrameRouter`; `GoodixUsbRouter`; `goodix_secure_session_handle_a0` | `VERIFIED` | non estende provenance oltre open/processo |
| F. `CROSS_SESSION_FRAME_PROVENANCE` | nessun session ID/epoch nel frame o nel router | generation è submit ownership host, non causalità device | sorgenti Python/C e test stale-generation; seconda single-shot | `VERIFIED_ABSENT_AS_HOST_GUARANTEE` | fenomeno ora `OBSERVED` sul target (A0/E4/41 in fase A8); provenance causale `UNPROVEN` e non deducibile dal wire |
| G. `PRE_A8_REENTRY_SYNCHRONIZATION` | D245 inizia direttamente con A8; niente pre-read; A8 initializer non provato | D278 arma IN e invia direttamente A8; nessun protocollo di re-entry | D245 patch; `goodix_d278_harness_start`; seconda single-shot | `UNRESOLVED_NOT_IMPLEMENTED_AS_PROVEN_SYNC` | l'assenza di sincronizzazione è ora anche live-visibile; nessuna regola sicura di discard/resync resta comunque giustificata qui |

## Semantica GUsb/libusb/USB generale

Ambiente locale ispezionato: Fedora espone `libgusb 0.4.9` e `libusb 1.0.30`;
il runtime Flatpak 25.08 usato nelle verifiche D278 esponeva libusb `1.0.29`.
Il progetto usa l'API async GUsb/FpiUsbTransfer con `GCancellable`; il limite
semantico rilevante è quello del transfer libusb sottostante.

Le seguenti sono tutte `EXTERNAL_GENERAL_USB_SEMANTICS`, mai
`APP12509_TARGET_PROOF`:

1. L'header upstream GUsb espone open/close, claim/release e bulk transfer
   asincroni con `GCancellable`/finish; non espone un identificatore di
   provenance cross-session né una primitiva “discard protocol frames”. È
   un'osservazione della superficie API, non una garanzia sulla coda endpoint.
   Fonte: <https://github.com/hughsie/libgusb/blob/0.4.9/gusb/gusb-device.h>.
2. La documentazione ufficiale libusb 1.0.30 descrive
   `libusb_cancel_transfer()` come asincrona: il ritorno non completa la
   cancellazione; il callback arriva successivamente. Avverte inoltre che al
   momento della cancellazione alcuni dati possono già essere stati trasferiti
   e non si deve assumere il contrario.
   Fonte: <https://libusb.sourceforge.io/api-1.0/group__libusb__asyncio.html>.
3. Il callback chiude il lifetime del transfer host e rende disponibili status
   e quantità trasferita. La documentazione non lo definisce come flush della
   FIFO endpoint né come protocol close del dispositivo. Questa è una
   delimitazione della garanzia API, non la prova che una FIFO APP12509
   contenga dati.
4. `libusb_release_interface()` invia un `SET_INTERFACE` che riporta
   l'interfaccia al primo alternate setting. La documentazione non promette che
   ciò resetti la state machine applicativa Goodix o classifichi/scarti tutte
   le risposte già generate. Fonte:
   <https://libusb.sourceforge.io/api-1.0/group__libusb__dev.html>.
5. `libusb_close()` è non bloccante e non invia richieste sul bus. Chiude il
   device handle, ma non è documentato come reset, protocol synchronizer o
   garanzia di coda bulk-IN vuota. Stessa fonte ufficiale.
6. Claim di una nuova interfaccia è una ownership logica host e non invia
   richieste sul bus. Nuovo open/claim non porta quindi, per contratto API, una
   provenance dei byte della prima completion.

La sorte esatta di dati unread dopo cancel → release → close → open/claim non
è specificata in modo portabile dalle API come “sempre preservati” o “sempre
scartati”. Può dipendere da backend kernel, host controller, timing e
comportamento del device. L'unica conclusione lecita è:

```text
HOST_TRANSFER_LIFETIME_AFTER_CANCEL_CALLBACK=KNOWN
UNREAD_ENDPOINT_DATA_AFTER_CLOSE_REOPEN=UNKNOWN_TARGET_SPECIFIC
DEVICE_PROTOCOL_STATE_AFTER_RELEASE_CLOSE=UNKNOWN_TARGET_SPECIFIC
```

## Confronto OLD vs CURRENT

| Aspetto | Runtime storico Python | Runtime C nativo | Evidenza | Classificazione | Gap |
| --- | --- | --- | --- | --- | --- |
| first RX ownership | dopo A8 OUT, `ProductionUsbTransport.read_frame` esegue il primo bulk-IN | D278 arma un transfer generation 1 prima di A8 OUT | D245 patch `::_exchange_a8_precondition`; `goodix_d278_harness_start` | `VERIFIED` | ownership host nota; causalità byte ignota |
| pre-A8 behavior | open/revalidate → A8; nessun pre-read/drain | begin generation → arm IN → A8; nessun pre-read/resync | stessi simboli | `VERIFIED` | `PRE_A8_REENTRY_SYNCHRONIZATION` assente |
| reassembly buffer | `_rx` persistente nell'istanza; exact-frame pop; remainder preservato e dopo A8 rifiutato | `GoodixUsbRouter.pending`; svuotato a begin/cancel; parser incrementale | `read_frame`, `buffered_rx_bytes`; `goodix_usb_router_begin_generation/parse_pending/cancel` | `VERIFIED` | entrambi descrivono solo userspace |
| single-reader model | D266 `SharedFrameRouter._read_once` con lock non reentrante | un solo IN outstanding in backend/router | `core/usb_runtime.py`; `goodix_fpi_usb_backend_arm_receive`; `goodix_usb_router_request_receive` | `VERIFIED` | nessun secondo reader host trovato |
| same-session routing | viste command/event su lista ordinata | A0/B0 demux + parser di fase secure-session | D266 report; `parse_pending`; `goodix_secure_session_handle_a0` | `VERIFIED` | nessun routing cross-session |
| cancel semantics | path D241–D245 sincrono; cleanup release/close, nessun cancel device | terminal fence + `GCancellable`; token fino al callback | D244 audit; `goodix_fpi_usb_backend_cancel/complete_*` | `VERIFIED_HOST_ONLY` | device quiescence ignota |
| close/reopen semantics | ogni kit single-shot chiude; nessun contratto di endpoint empty | D278 single-shot release/close; nessun reopen nella run | report D242–D245, D278/03; `run_live_once` | `OBSERVED` per i contatori, `UNKNOWN` per lo stato device | nessuna prova cross-open |
| stale callback fencing | non applicabile al transport sincrono | callback generation N non consuma il token N+1 | backend/router e test stale-generation | `VERIFIED` | non copre callback N+1 con dati causali vecchi |
| cross-session frame provenance | assente | assente: generation locale al processo/submit | sorgenti e assenza di nonce/session ID nel wire contract; seconda single-shot | `VERIFIED_ABSENT_AS_GUARANTEE` | manifestazione target `OBSERVED`, identità causale `UNPROVEN` |
| device quiescence | non provata; boot host non equivale a power-cycle sensore | esplicitamente `QUIESCENCE_UNKNOWN`, nessun cancel device-side | D244, D276/04 e seconda single-shot | `UNKNOWN/UNRESOLVED_WITH_ADVERSE_LIVE_INDICATION` | boundary device-side aperto; il re-entry ha però mostrato una shape della fase precedente |

## Valutazione H1–H6

| Ipotesi | Esito | Motivo determinante |
| --- | --- | --- |
| H1 — vecchio generic pre-A8 drain | `DISPROVEN` | D245 scrive A8 prima di qualsiasi read; nessun drain/flush generico esiste nel path. |
| H2 — A8 cross-session synchronizer dimostrato | `UNRESOLVED` | A8 è un precondition discriminator live-proven; il successo prima di E4 non dimostra reset/flush/sincronizzazione, né esiste un esperimento cross-session controllato. |
| H3 — D266 copriva provenance cross-session | `DISPROVEN` | D266 classifica frame intra-sessione in un solo router; nessun epoch/process/open provenance. |
| H4 — multi-image esercitava re-entry | `DISPROVEN` | D275/04 registra una sola sessione USB, un solo oggetto/handshake TLS e zero reopen/retry fino alla seconda immagine. |
| H5 — generation fencing C sufficiente | `DISPROVEN` | blocca `OLD_CALLBACK_FROM_GENERATION_N`, ma un transfer N+1 con byte causali vecchi porta legittimamente il token N+1; nessun controllo può distinguerlo se il frame soddisfa la fase corrente. |
| H6 — residual RX come fenomeno target | `STRONGLY_LIVE_CORROBORATED_IDENTITY_UNPROVEN` | la seconda single-shot ha osservato, in una nuova sessione in fase A8, `A0/E4/body41`, cioè la shape canonica della typed response E4: il fenomeno non è più solo un rischio architetturale. L'identità causale con la typed response E4 della run precedente resta però indimostrata, perché il wire non porta provenance e il body E4 dipende dal solo materiale persistente. |

```text
H1_HISTORICAL_GENERIC_PRE_A8_DRAIN=DISPROVEN
H2_A8_CROSS_SESSION_SYNCHRONIZER=UNRESOLVED
H3_D266_CROSS_SESSION_PROVENANCE=DISPROVEN
H4_MULTI_IMAGE_CROSS_SESSION_REENTRY=DISPROVEN
H5_NATIVE_GENERATION_FENCING_SUFFICIENT=DISPROVEN
H6_CROSS_SESSION_RX_RESIDUAL_CURRENT_EXPLANATION=STRONGLY_LIVE_CORROBORATED_CAUSAL_IDENTITY_UNPROVEN
```

Il confine fra i tre livelli epistemici va mantenuto anche nella lettura futura:

```text
ARCHITECTURAL_GAP=PROVEN_STATICALLY  # generation protegge OLD_CALLBACK_FROM_GENERATION_N, non la provenance dei byte di un NEW_CALLBACK_N_PLUS_1
TARGET_OBSERVATION=OBSERVED_LIVE     # phase=A8, received=A0/E4/body41
CAUSAL_IDENTITY=UNPROVEN             # THAT_FRAME_WAS_DEFINITELY_THE_PREVIOUS_RUN_E4_TYPED_RESPONSE non è provato
```

## Nessun resync candidate implementato qui

Non esiste ancora evidenza sufficiente per una regola sicura “discard until A8”.
Un frame inatteso può essere evidenza valida di fase, errore corrente, risposta
tardiva o stato device non quiescente. Senza un discriminante wire provato,
scartarlo confonderebbe dati validi inattesi con “spazzatura”. Non vengono
quindi proposti né implementati pre-A8 blind read, discard-until-A8,
timeout-drain, clear-halt, reset, reopen, retry, pacing o parser permissivo.

```text
SAFE_READ_ONLY_RESYNC_DESIGN=NOT_IMPLEMENTED_DESIGN_REVIEW_REQUIRED
RESYNC_IMPLEMENTED_IN_THIS_TASK=false
```

La nuova evidenza live sposta però il lavoro successivo dalla domanda “il
fenomeno esiste sul target?” alla domanda di design “esiste una discriminazione
read-only, bounded e fail-closed?”. Quella discriminazione dovrà essere prima
progettata e revisionata: dovrà stabilire se il primissimo IN di una nuova
sessione possa essere classificato senza emettere comandi aggiuntivi, senza
reset/clear-halt/reopen/retry, senza allentare il parser e senza scartare
evidenza valida; e dovrà dichiarare esplicitamente che una A8 valida non prova
da sola la causalità corrente, come la seconda single-shot ha mostrato al
contrario per una shape della fase precedente. Il minimo osservativo già
disponibile — fase, outer class, control, ACK echo/status, body length e failure
class conservati fail-closed senza payload sensibili — si è dimostrato
sufficiente a rendere visibile il fenomeno e non deve essere ampliato con read o
comandi aggiuntivi. Un esperimento controllato a due sessioni non è
safety-justified da questo audit e non è autorizzato.

## Riesame metodologico pre-live

1. **Cosa cambierebbe realmente rispetto all'ultimo tentativo?** Nulla è ancora
   cambiato in modo sufficiente. La seconda single-shot ha consumato la propria
   autorizzazione e ha spostato l'evidenza, non il metodo: nessuna terza run
   equivalente è ammessa. Il correttivo ACK D278/03 resta non ritestato live,
   ma una sua riesecuzione non deciderebbe il cross-session re-entry, che ora
   precede E4 nella catena di failure osservata.
2. **Quale nuova ipotesi tecnica verrebbe testata?** Soltanto un futuro
   esperimento separato potrebbe testare
   `NEW_CALLBACK_GENERATION_N_PLUS_1_RECEIVING_OLD_DEVICE_CAUSAL_DATA`, distinta
   da `OLD_CALLBACK_FROM_GENERATION_N`, già coperta offline; e solo un design
   revisionato potrebbe stabilire se la discriminazione read-only sia possibile.
3. **Se fallisse di nuovo nello stesso punto?** Nessuna run equivalente
   ulteriore. Si conserva la prima failure strutturale, si confronta con la
   policy ACK e con la fase attesa e si torna ad audit offline. Se la provenance
   resta indeterminabile, il boundary resta unresolved finché non esiste un
   diagnostico controllato, revisionato e autorizzato; non si aggiungono
   drain/retry/reset empirici.

Questo riesame non autorizza una run futura.

## Closure

```text
OUTCOME=READY_FOR_AI_PM_REVIEW
ADVANCEMENT=ARCHITECTURAL_BOUNDARY_PROVEN_AND_TARGET_REENTRY_PHENOMENON_OBSERVED
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=CROSS_SESSION_RX_RESIDUAL_CAUSAL_IDENTITY_UNPROVEN;NO_TARGET_SPECIFIC_PROOF_OF_ENDPOINT_OR_DEVICE_QUIESCENCE_AFTER_INTERRUPTED_SESSION;CROSS_SESSION_FRAME_PROVENANCE_ABSENT;BOUNDED_READ_ONLY_REENTRY_DISCRIMINATION_NOT_DESIGNED;ACK_POLICY_CORRECTIVE_NOT_LIVE_RETESTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_6544e408e3eb39b2e33f1442ad5407577c05b149_PLUS_CURRENT_HEAD_PLUS_analysis/D278/D278_04_cross_session_protocol_reentry_audit.md_PLUS_MANUAL
H1_HISTORICAL_GENERIC_PRE_A8_DRAIN=DISPROVEN
H2_A8_CROSS_SESSION_SYNCHRONIZER=UNRESOLVED
H3_D266_CROSS_SESSION_PROVENANCE=DISPROVEN
H4_MULTI_IMAGE_CROSS_SESSION_REENTRY=DISPROVEN
H5_NATIVE_GENERATION_FENCING_SUFFICIENT=DISPROVEN
H6_CROSS_SESSION_RX_RESIDUAL_CURRENT_EXPLANATION=STRONGLY_LIVE_CORROBORATED_CAUSAL_IDENTITY_UNPROVEN
CROSS_SESSION_REENTRY_ARCHITECTURAL_GAP=PROVEN
TARGET_UNEXPECTED_PRIOR_PHASE_SHAPE_AT_REENTRY=OBSERVED
OBSERVED_REENTRY_FRAME_OUTER=0xA0
OBSERVED_REENTRY_FRAME_CONTROL=0xE4
OBSERVED_REENTRY_FRAME_BODY_LENGTH=41
OBSERVED_REENTRY_FRAME_MATCHES_CANONICAL_E4_CONTROL_AND_LENGTH=true
CROSS_SESSION_RX_RESIDUAL_TARGET_HYPOTHESIS=STRONGLY_LIVE_CORROBORATED
CROSS_SESSION_RX_RESIDUAL_CAUSAL_IDENTITY=UNPROVEN
ACK_POLICY_CORRECTIVE_REFUTED=false
ACK_POLICY_CORRECTIVE_LIVE_RETESTED=false
SAFE_READ_ONLY_RESYNC_DESIGN=NOT_IMPLEMENTED_DESIGN_REVIEW_REQUIRED
SECOND_SINGLE_SHOT_LIVE_EXECUTED=true
SECOND_SINGLE_SHOT_LIVE_RUN_COUNT=1
LIVE_AUTHORIZATION_CONSUMED=true
RETRY_AUTHORIZED=false
DO_NOT_RUN_AGAIN=true
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_OF_D278_04_POST_SECOND_LIVE_EVIDENCE_THEN_DESIGN_REVIEW_OF_BOUNDED_READ_ONLY_CROSS_SESSION_REENTRY_DISCRIMINATION
```
