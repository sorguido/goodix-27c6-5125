# D278/04 — audit statico/host-only del cross-session protocol re-entry

## Esito esecutivo

L'audit identifica un boundary reale ma non una riproduzione target-specific:
la generation C prova l'ownership e il drain dei transfer host; non codifica la
causalità dei byte consegnati da un transfer nuovo e non prova che endpoint e
protocollo device siano quiescenti dopo una sessione interrotta. Di conseguenza
un callback della generation corrente può, per costruzione, consegnare byte
semanticamente prodotti prima della generation e il parser li attribuisce alla
fase corrente. Che questo sia accaduto sul target APP12509 non è osservato.

La classificazione primaria è quindi:

```text
CROSS_SESSION_REENTRY_GAP=SUPPORTED_BUT_DEVICE_SIDE_UNRESOLVED
```

Non è `PROVEN_HOST_SIDE`: il fencing rifiuta correttamente i callback host
stale, il router ha un solo reader e non è stato trovato un overlap host
deterministico. Non è `DISPROVEN`: né il codice né le API USB generali provano
la quiescenza device/endpoint o la provenance cross-session. Non è
`UNRESOLVED_INSUFFICIENT_EVIDENCE`: l'assenza del contratto di provenance e il
limite host-only del drain sono verificabili staticamente; resta irrisolta la
sola occorrenza device-side sul target.

`CROSS_SESSION_RX_RESIDUAL` è `SUPPORTED` soltanto come scenario di rischio
architetturale. Non è una causa provata della run D278/03: quella run terminò
sul primo IN di E4, non telemetrizzò lo status ACK E4 e possiede già la più
forte spiegazione documentata `CURRENT_NATIVE_C_REJECTED_A_PROVEN_SUCCESS_ACK_CLASS_AT_E4`.

## Baseline, scope e safety

Comandi Git iniziali, eseguiti read-only:

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

Sono stati letti integralmente `AGENTS.md`, le linee guida di progetto e il
prompt D278/04, oltre alle sezioni pertinenti del manuale e agli artefatti
D242–D278 indicati sotto. Non sono stati eseguiti USB reale, launcher live,
`sudo`, accesso allo store protetto, reset, clear-halt, retry, reopen o comandi
sensor-reaching. Non sono stati modificati runtime, sorgenti, test, launcher o
artefatti storici.

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

Il secondo marker nega deliberatamente la garanzia di prevenzione, non osserva
che il caso sia avvenuto: un transfer N+1 che riceve dati prodotti
causalmente prima della generation ha comunque il token N+1 e supera tutti i
check correnti. `goodix_usb_router_begin_generation` e
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

La run D278/03 osservò A8 PASS, E4 OUT sent e terminale sul primo IN E4, con
una open/claim/release/close, `physical_in_completion_count=3`,
`physical_out_completion_count=2`, zero retry/reopen/reset e backend drained.
Non registrò lo status ACK E4. Il report correttivo individua la divergenza
ACK C/D238, corroborata storicamente, come causa primaria con status corrente
non direttamente telemetrizzato. Nulla nella telemetria osserva un frame
cross-session. Evidenza:
`analysis/D278/D278_03_native_secure_session_live_result_20260829.json` e
`analysis/D278/D278_03_e4_ack_policy_corrective.md`.

## Decisione A–G

| Boundary | Storico | C corrente | Evidenza | Decisione | Residuo |
| --- | --- | --- | --- | --- | --- |
| A. `HOST_ASYNC_TRANSFER_DRAIN` | Python sincrono: nessun token async; cleanup release/close | cancel/fence e ritorno di tutti i callback matching | `goodix_fpi_usb_backend_cancel`, `complete_receive`, `complete_out`; D276/04 | `VERIFIED: PROVEN_HOST_ONLY` | non dice nulla sulla causalità dei byte o sul device |
| B. `USERSPACE_REASSEMBLY_BUFFER_EMPTY` | D245 verifica `_rx == 0` dopo exact ACK+typed A8; extra byte è failure | `goodix_usb_router_begin_generation/cancel` azzerano `pending`; il parser conserva partial corrente | D245 patch; `goodix_usb_router.c` | `VERIFIED_HOST_SIDE` | non svuota coda kernel/endpoint e non classifica provenance |
| C. `KERNEL/USB_ENDPOINT_PENDING_DATA` | nessuna telemetria o reset endpoint in D242–D245 | nessuna query/asserzione sulla FIFO endpoint | report storici; API USB sotto | `UNKNOWN_TARGET_SPECIFIC` | dipendenza kernel/controller/device non chiusa |
| D. `DEVICE_PROTOCOL_QUIESCENCE` | cleanup non prova protocol close/reset; fresh host boot non prova power-cycle sensore | nessun cancel device-side provato; context diventa poisoned/unknown | D244 initial-state audit; D276/04; `goodix_fpimage_device.c` | `UNRESOLVED` | stato APP12509 dopo cancel arbitrario ignoto |
| E. `SAME_SESSION_SEMANTIC_ROUTING` | D266 prova viste command/event con un solo reader | router C prova A0/B0 framing; secure-session applica phase contract | D266 report; `SharedFrameRouter`; `GoodixUsbRouter`; `goodix_secure_session_handle_a0` | `VERIFIED` | non estende provenance oltre open/processo |
| F. `CROSS_SESSION_FRAME_PROVENANCE` | nessun session ID/epoch nel frame o nel router | generation è submit ownership host, non causalità device | sorgenti Python/C e test stale-generation | `VERIFIED_ABSENT_AS_HOST_GUARANTEE` | occorrenza target `UNKNOWN` |
| G. `PRE_A8_REENTRY_SYNCHRONIZATION` | D245 inizia direttamente con A8; niente pre-read; A8 initializer non provato | D278 arma IN e invia direttamente A8; nessun protocollo di re-entry | D245 patch; `goodix_d278_harness_start` | `UNRESOLVED_NOT_IMPLEMENTED_AS_PROVEN_SYNC` | nessuna regola sicura di discard/resync |

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
| cross-session frame provenance | assente | assente: generation locale al processo/submit | sorgenti e assenza di nonce/session ID nel wire contract | `VERIFIED_ABSENT_AS_GUARANTEE` | manifestazione target non osservata |
| device quiescence | non provata; boot host non equivale a power-cycle sensore | esplicitamente `QUIESCENCE_UNKNOWN`, nessun cancel device-side | D244 e D276/04 | `UNKNOWN/UNRESOLVED` | boundary device-side aperto |

## Valutazione H1–H6

| Ipotesi | Esito | Motivo determinante |
| --- | --- | --- |
| H1 — vecchio generic pre-A8 drain | `DISPROVEN` | D245 scrive A8 prima di qualsiasi read; nessun drain/flush generico esiste nel path. |
| H2 — A8 cross-session synchronizer dimostrato | `UNRESOLVED` | A8 è un precondition discriminator live-proven; il successo prima di E4 non dimostra reset/flush/sincronizzazione, né esiste un esperimento cross-session controllato. |
| H3 — D266 copriva provenance cross-session | `DISPROVEN` | D266 classifica frame intra-sessione in un solo router; nessun epoch/process/open provenance. |
| H4 — multi-image esercitava re-entry | `DISPROVEN` | D275/04 registra una sola sessione USB, un solo oggetto/handshake TLS e zero reopen/retry fino alla seconda immagine. |
| H5 — generation fencing C sufficiente | `DISPROVEN` | blocca `OLD_CALLBACK_FROM_GENERATION_N`, ma un transfer N+1 con byte causali vecchi porta legittimamente il token N+1; nessun controllo può distinguerlo se il frame soddisfa la fase corrente. |
| H6 — residual RX come spiegazione corrente | `SUPPORTED` | supportato come rischio architetturale da assenza di provenance/quiescenza e semantica USB generale; non provato come causa D278/03, che ha una spiegazione ACK più forte e nessun frame residual telemetrizzato. |

```text
H1_HISTORICAL_GENERIC_PRE_A8_DRAIN=DISPROVEN
H2_A8_CROSS_SESSION_SYNCHRONIZER=UNRESOLVED
H3_D266_CROSS_SESSION_PROVENANCE=DISPROVEN
H4_MULTI_IMAGE_CROSS_SESSION_REENTRY=DISPROVEN
H5_NATIVE_GENERATION_FENCING_SUFFICIENT=DISPROVEN
H6_CROSS_SESSION_RX_RESIDUAL_CURRENT_EXPLANATION=SUPPORTED
```

## Nessun resync candidate giustificato

Non esiste evidenza sufficiente per una regola sicura “discard until A8”. Un
frame inatteso può essere evidenza valida di fase, errore corrente, risposta
tardiva o stato device non quiescente. Senza un discriminante wire provato,
scartarlo confonderebbe dati validi inattesi con “spazzatura”. Non vengono
quindi proposti pre-A8 blind read, timeout-drain, clear-halt, reset, reopen,
retry, pacing o parser permissivo.

```text
SAFE_READ_ONLY_RESYNC_DESIGN=NOT_YET_JUSTIFIED
```

La stop condition è raggiunta: per stabilire se APP12509 preservi o produca
tardi un frame attraverso cancel/release/close e nuovo open serve osservazione
del device reale. Prima di una futura run, AI-PM e Utente dovrebbero approvare
separatamente una specifica diagnostica. Il minimo diagnostico non deve creare
comandi o read aggiuntivi: deve soltanto, in una run già altrimenti giustificata
e non equivalente, conservare fail-closed la struttura del primissimo IN
(generation del transfer, fase, timestamp relativo ad arm e OUT, outer class,
control, ACK echo/status, body length e failure class), senza payload sensibili.
Un frame non coerente con la nuova A8 sarebbe nuova evidenza; una A8 valida non
proverebbe da sola la causalità corrente. Un esperimento controllato a due
sessioni, necessario per provare la causalità, non è ancora safety-justified da
questo audit e non è autorizzato.

## Riesame metodologico pre-live

1. **Cosa cambierebbe realmente rispetto all'ultimo tentativo?** Questo audit
   non ha definito un cambiamento metodologico sufficiente per una nuova run.
   Il correttivo ACK D278/03 cambia una regola di protocollo, ma una sua
   riesecuzione non decide il cross-session re-entry. La sola telemetria in più
   non costituisce un nuovo metodo; un vero test richiederebbe un protocollo
   controllato a due sessioni, ancora non safety-justified.
2. **Quale nuova ipotesi tecnica verrebbe testata?** Soltanto un futuro
   esperimento separato potrebbe testare
   `NEW_CALLBACK_GENERATION_N_PLUS_1_RECEIVING_OLD_DEVICE_CAUSAL_DATA`, distinta
   da `OLD_CALLBACK_FROM_GENERATION_N`, già coperta offline.
3. **Se fallisse di nuovo nello stesso punto?** Nessuna run equivalente
   ulteriore. Si conserva la prima failure strutturale, si confronta con la
   policy ACK e con la fase attesa e si torna ad audit offline. Se la provenance
   resta indeterminabile, il boundary resta unresolved finché non esiste un
   diagnostico controllato, revisionato e autorizzato; non si aggiungono
   drain/retry/reset empirici.

Questo riesame non autorizza una run futura.

## Closure

```text
OUTCOME=READY
ADVANCEMENT=ARCHITECTURAL_BOUNDARY_CLARIFIED
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=NO_TARGET_SPECIFIC_PROOF_OF_ENDPOINT_OR_DEVICE_QUIESCENCE_AFTER_INTERRUPTED_SESSION;CROSS_SESSION_FRAME_PROVENANCE_ABSENT;SAFE_PRE_A8_RESYNC_RULE_NOT_JUSTIFIED;D278_03_E4_STATUS_NOT_TELEMETRIZED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_5fbbe3f37d09d2b9f41e4a3906a2a759e8122f21_PLUS_CURRENT_HEAD_5fbbe3f37d09d2b9f41e4a3906a2a759e8122f21_PLUS_analysis/D278/D278_04_cross_session_protocol_reentry_audit.md_PLUS_MANUAL
H1_HISTORICAL_GENERIC_PRE_A8_DRAIN=DISPROVEN
H2_A8_CROSS_SESSION_SYNCHRONIZER=UNRESOLVED
H3_D266_CROSS_SESSION_PROVENANCE=DISPROVEN
H4_MULTI_IMAGE_CROSS_SESSION_REENTRY=DISPROVEN
H5_NATIVE_GENERATION_FENCING_SUFFICIENT=DISPROVEN
H6_CROSS_SESSION_RX_RESIDUAL_CURRENT_EXPLANATION=SUPPORTED
CROSS_SESSION_REENTRY_GAP=SUPPORTED_BUT_DEVICE_SIDE_UNRESOLVED
SAFE_READ_ONLY_RESYNC_DESIGN=NOT_YET_JUSTIFIED
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
```
