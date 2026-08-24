# Goodix 27c6:5125 — manuale tecnico

## Stato del progetto

Il progetto studia il sensore Goodix USB `27c6:5125` del Huawei MateBook D15 /
BohrD-WDH9D con un vincolo assoluto: preservare firmware, identità,
configurazione factory, stato persistente/secure e compatibilità con Windows.

Non esiste ancora un driver Linux funzionante. La progressione live ha però
chiuso i confini A8, E4 e TLS sul firmware 12509: D239 ha eseguito il cold-start
OEM fino al B0/TLS, D241 ha verificato l'ownership exactly-once e il
ClientHello TLS 1.2, D242–D244 hanno localizzato e controllato i timeout E4 e
D245 ha completato l'intero percorso A8→E4→pre-D1→D1→TLS senza retry. D246 ha
ora completato live anche il solo exchange D4 autorizzato: un tentativo e un
invio, ACK esatto `d4/01`, nessuna response tipizzata, nessun application data
e stop terminale `STOP_AFTER_D4`. Cleanup, zeroizzazione del secret, restore di
fprintd e reseal sono riusciti; le famiglie di scrittura persistente sono
rimaste a zero. La semantica D4 resta quella già provata staticamente,
`VOLATILE_SESSION_INITIALIZATION`, limitata al receiver APP12509 esatto. A8,
E4, TLS e D4 non sono più blocker aperti. D249 ha ora chiuso offline il
framing e parsing AF e, dopo la correzione di review, ha chiuso realmente nel
nuovo core GPL due replay sintetici bounded fino a `FIRST_IMAGE_RECEIVED`:
FDT fresh e cached POV, sopra un transport astratto e senza USB reale. D250 ha
poi eseguito una volta il boundary AF sul target: TLS e D4 sono riusciti, AF è
stato inviato una volta come 13 byte logici in una submission fisica da 64 byte
con tail zero, e il device ha restituito una A0/AE strutturalmente valida con
checksum valido e body da 16 byte. Il percorso fresh-FDT non è ancora
autorizzato live: D256 ne ha chiuso il lifecycle osservabile host/bus, mentre il
corrective D257 ha dimostrato che il replay precedente copriva soltanto una
sottosequenza proiettata. D258 ha trovato nel `gfusb.dll` target
l'orchestratore completo `gf_update_all_base`: `0x50` e `0x20` sono acquisiti
prima del terzo sample ma classificati soltanto dopo, mentre `0x82` fornisce
nel secondo byte la soglia unsigned del confronto assoluto fra i word FDT
grezzi. Il corrective D259 ha ora confermato meccanicamente il riflesso causale
dei classificatori: la matrice è derivata dai compare/jump/call del disassembly
hash-gated e tutti i return osservabili convergono a successo, possono cambiare
soltanto basi RAM e dirty/cache host OEM, ma non tabella FDT, payload o
raggiungibilità del primo `0x32`, né aggiungono comandi/retry/recovery
device-side. La Classe A del classifier è quindi confermata. Il corrective ha
però falsificato la precedente readiness complessiva: il runtime sealed D245
crea il TLS server come locale e lo chiude nel `finally` di `tls_handshake()`,
senza esporre la stessa sessione al futuro consumer B0. L'adapter GPL e la
continuità handshake→B0→secondo record sono provati offline sulla stessa
`SSLObject`, e il replay consuma ora B0 subito dopo `0x20` e prima del terzo
`0x36`; il plumbing nel runtime live resta `UNIMPLEMENTED`. D259 è pertanto
bloccato prima della live-readiness review e non autorizzato live.

D260 chiude ora quel gap **sul solo piano architetturale offline** nel dominio
GPL `core/`, senza modificare il runtime sealed. Un coordinator production-shaped
possiede una sola sessione transport simulata, un solo handoff di secret
sintetico, un solo server TLS e un solo handshake; il lifecycle TLS resta vivo
attraverso D4 plaintext A0, AF/AE e gli A0 FDT, poi consuma il B0 baseline sulla
stessa sessione prima del terzo `0x36`. ACK e IRQ `0x0100` passano da contratti
distinti. Il rehearsal unico `D1/B0 TLS → D4 → AF/AE → 36,50,36,82,20,36,32`
e i 15 failure richiesti passano offline con zero retry, recovery speciale,
cache write e famiglie persistenti. Le policy fisiche D4 e B0 sono chiuse; la
tail fisica dei futuri A0 FDT Linux resta esplicitamente astratta. Ne segue
`READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW=true`, mentre review operativa,
backend USB reale, secret reale, baseline approvata, kit e autorizzazione live
restano separati e tutti i flag live non qualificati restano false.

D261 chiude offline il successivo gap operativo senza eseguire USB reale. Il
raw D255 è stato ricensito per comando: tutti gli A0 FDT hanno submission da
64 byte; i sei byte nonzero fuori frame ricorrono agli stessi offset assoluti
`40..45` su comandi non correlati e cambiano nella capture D254, mentre il
finale `0x32` OEM usa tail interamente zero e riceve ACK. Il candidate Linux
usa quindi fixed-64 e zero-fill deterministico per
`36,50,36,82,20,36,32`, senza replay di residui. L'accettazione target è prova
primaria per `0x32`, ma resta una nuova ipotesi live per gli altri comandi e il
rischio principale della futura singola run. Il nuovo path GPL integra
cold-start APP12509, secret reale protetto con validazione E4 prima del medesimo
handoff TLS, cache hash/CRC/OTP-bound, adapter libusb esatto con un solo reader
EP81, preflight, marker single-use, restore e reporting. La review AI-PM ha poi
rilevato quattro overclaim operativi: parte della matrice failure era
assertion-only, la funzione Python live sostituiva l'intento CLI con una
costante interna, il reader rinnovava il timeout per ogni completion non
corrispondente e la safety della report directory veniva chiusa soltanto in
pubblicazione. Il corrective dello stesso D261 separa ora capability
CLI-intent e Live-I/O, valida il contenuto protetto prima del marker, applica
una deadline monotonic assoluta e anticipa i gate directory pre-side-effect.
Tutti i 24 failure, i 13 casi demux/deadline e il rehearsal transazionale
passano offline. La review successiva ha individuato una bounded import closure
incompleta e una lettura secret anticipata rispetto al failure config90, senza
osservare side effect a import-time. Il corrective finale dello stesso D261
include ora nel set baseline anche `core/__init__.py` e
`poc/goodix5125/tools/binding_reference/__init__.py`: la closure dinamica
bounded comprende 16 file Python, non omette file e rileva drift sintetico di
entrambi gli initializer. Un subprocess nuovo, non privilegiato e senza flag
live importa l'intera closure con zero tentativi USB, accessi al filesystem
protetto, istanziazioni/materializzazioni del real secret loader, mutazioni
fprintd e creazioni marker. Manifest, config90 e cache hash/layout/CRC vengono
ora validati prima di costruire o materializzare il secret reale; i rehearsal
offline iniettano esclusivamente una boundary sintetica via Protocol e non
tentano alcun fallback real→synthetic. La suite completa passa offline; i
contatori reali USB/secret/comandi/marker/fprintd restano zero. Lo stato massimo
è `READY_FOR_BASELINE_APPROVAL_REVIEW=false` e
`OPERATIONAL_REVIEW_PENDING_APPROVED_BASELINE=false`; Utente e AI-PM hanno ora
approvato il full commit SHA `e9073a171697bd68dd2debabb851f23d007bf718` come
baseline live-critical immutabile, promuovendo la readiness a review operativa
(`READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=true`, `READY_FOR_FDT_LIVE_REVIEW=true`),
ma `READY_FOR_FDT_LIVE=false`: approvazione baseline ≠ autorizzazione hardware.

D262 esegue la final execution-readiness review offline del bounded fresh-FDT arm
sulla baseline approvata `e9073a171697bd68dd2debabb851f23d007bf718`, senza modificare
nessun file live-critical (`D262_LIVE_CRITICAL_MODIFICATION_COUNT=0`). Il kit operatore
D261 è riusato in `--dry-run` da cwd realistico (PASS, zero USB/secret/marker/command/
fprintd reali); il verifier conferma che tutti i 17 blob del live-critical set sono
byte-identici alla baseline. La full suite offline (238 test) PASSa; il rehearsal
conferma che il runtime giunge solo a `STOP_AFTER_FDT_ARM_ACK` con traccia FDT
`0x36,0x50,0x36,0x82,0x20,0x36,0x32`, zero retry, zero famiglie persistenti, zero
A2/`0x70` di recovery, `0x22`/post-finger/enrollment/matching irraggiungibili. Rischio
live invariato: l'accettazione della zero-tail per `0x32` è provata
(`PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED`), mentre per `0x36/0x50/0x82/0x20`
resta `EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE` /
`UNPROVEN_LIVE_HYPOTHESIS`. Lo stato era
`READY_FOR_D262_OPERATOR_EXECUTION_REVIEW=true`, `READY_FOR_D262_OPERATOR_EXECUTION=false`,
`READY_FOR_FDT_LIVE=false`: nessuna esecuzione hardware né autorizzazione implicita.

La singola run live autorizzata è poi stata eseguita una sola volta e completata con
successo: `PASS_STOP_AFTER_FDT_ARM_ACK`, nessuna interazione dito (`FINGER_INTERACTION_COUNT=0`),
nessun retry (`RETRY_COUNT=0`), zero famiglie persistenti (`PERSISTENT_DEVICE_WRITE_COUNT=0`),
zero cache write (`CACHE_WRITE_COUNT=0`) e zero recovery A2/`0x70`, un'unica sessione USB
(`USB_TRANSPORT_SESSION_COUNT=1`) e un solo handshake/server TLS, B0 consumato sulla stessa
sessione TLS prima di stage2, secret zeroizzato e non loggato, fprintd e segnale ripristinati,
runtime chiuso. La traccia FDT esatta
`0x36,0x50,0x36,0x82,0x20,0x36,0x32` è ora accettata dal target primario con ACK: il rischio
zero-tail per `0x36/0x50/0x82/0x20` è ritirato per `27c6:5125`/`GF_ST411SEC_APP_12509` sul
bounded FDT arm path (`PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED`). Il marker single-use è
consumato; `SECOND_LIVE_ATTEMPT_ALLOWED=false`: la stessa run non deve essere ripetuta e nessun
nuovo step live è autorizzato in questo step. `0x22` e il post-finger image non sono stati
raggiunti.

D250 aveva chiuso offline il boundary minimo exactly-one AF. L'audit
riproducibile della capture primaria ha isolato `D4/ACK d4-01 → AF → AE`:
request logica 13 byte, submission OEM da 64 byte, risposta AE diretta da 24
byte con 16 byte di stato, nessun ACK AF e 58,365 ms osservati tra ACK D4 e AF
OUT. La tail OEM AF contiene 51 byte fuori dalla lunghezza dichiarata, con sei
byte opachi nonzero identici nelle cinque occorrenze; il candidate non li
replayava e usava una tail deterministica zero. La run D250 ha ora provato sul
target APP12509 che questa zero-tail viene accettata fino a OUT completion e a
una risposta AE strutturalmente valida: `D250_AF_ZERO_TAIL_DEVICE_ACCEPTANCE`
e `D250_AF_ZERO_TAIL_STRUCTURAL_AE_RESPONSE` sono `LIVE_PROVEN`. Non è invece
provata l'equivalenza byte-per-byte o semantica universale con i sei byte opachi
nonzero della tail OEM. La run si è fermata fail-closed perché il validator
promuoveva il byte 0, osservato a `1` nelle cinque capture OEM, a una presunta
versione obbligatoria. Il contatore `af_response_count` veniva incrementato
solo dopo quel controllo: il valore live `0` è quindi un difetto di
osservabilità, non assenza di risposta. Il byte 0 live non è stato persistito ed
è `LOST_BY_OBSERVABILITY_GAP`. Cleanup, reseal, zeroizzazione del secret e
restore fprintd/segnali sono riusciti; retry, write persistenti e application
data sono rimasti a zero. Il marker D250 è consumato.

D251 ha poi eseguito una volta il candidate corretto sulla baseline approvata
`f07352ce085651568a9aedbf04b097df91d7c0bb`. TLS e D4 sono riusciti; AF è stato
inviato una volta con la zero-tail già accettata dal target e ha ricevuto una
sola A0/AE strutturalmente valida. Lo stato live è `byte0=0`, ancora opaco e
non una “versione 0”, con `flags=0x02`: TLS connected vero, POV-valid e locked
falsi, bit ignoti zero. D251 ha terminato a `STOP_AFTER_AF`; retry, famiglie di
scrittura persistente e application data sono rimasti a zero, mentre cleanup,
zeroizzazione secret, restore fprintd/segnali e reseal sono riusciti. Il marker
D251 è consumato. `POV_VALID=false` seleziona il percorso fresh-FDT; D2 non è
selezionato da questo stato.

D252 ha riesaminato offline quel percorso senza hardware. La capture target
prova che la tabella FDT-down è appresa dinamicamente dagli IRQ `0x0100` prodotti
da tre `0x36`, ma non chiude la provenienza/freschezza della tabella seed del
primo `0x36` per il cold-start corrente. Tutti i tre `0x32` usano la tabella
finale nella stessa sessione; dopo l'unico IRQ finger-down catturato il comando
target successivo è wire `0x22 [01 00]`, non il `0x20` del modello Rocky/D249.
Soprattutto, nessun cancel/disarm/restore post-FDT è provato: `0x34` arma
finger-up e `gfOnCancel` cancella una richiesta host, mentre A2/`0x70` non sono
osservati come restore FDT. Perciò `D252_LIVE_BOUNDARY=BLOCKED` e non esiste un
operator kit D252.

D253 ha chiuso offline la distinzione immagine target e ha corretto il modello
corrente: `0x20` e `0x22` sono entrambi SetMode Image con `more=0`, ma usano
rispettivamente `cmd1=0` nei due contesti baseline/no-finger catturati e
`cmd1=1` subito dopo IRQ finger-down `0x0002`. Il core invia ora exact wire
`0x22 [01 00]` dopo IRQ2, valida ACK echo `22` e impedisce un secondo tentativo
post-IRQ in caso di failure. L'audit dataflow ha però delimitato, non chiuso,
il bootstrap: `gfusb.dll` riceve il primo seed tramite un callback host che
copia 12 byte nella globale FDT, ma il chiamante e la sorgente ultima sono
esterni al DLL disponibile. Nessun `goodix.dat` OEM è presente; il path OEM
osservato confronta soltanto il prefisso OTP e non prova una table FDT. Inoltre
non esiste ancora cancel/restore device-side deterministico. D253 resta quindi
`BLOCKED`, richiede evidenza primaria esterna mirata e non crea un kit live.

D254 ha acquisito e parsato offline le fonti pubbliche richieste senza hardware
locale. Il WBDI di `yanxinwu946/goodix-5125-linux` è in realtà `27c6:5110`,
firmware `GF_ST411SEC_APP_12117`: mostra un cache OTP-bound da 13520 byte e tre
stage FDT riusciti con NAV e immagine base intercalati, ma non è prova diretta
APP12509. Lo stesso repository espone una costante claimed-12509
`b3b3...b7b7`, diversa dal seed target `adad...b2b2`, senza capture wire che ne
provi la derivazione. La capture pubblica Issue #63 è `27c6:5125`, firmware
ignoto: in 21 eventi IRQ2 usa sempre `0x22 [01 00]`, corroborando il modello
corrente, e mostra su 22 comandi `0x36` residui fisici agli stessi offset
40–45 del target, con valori diversi. Non contiene cold-start, cancel senza
dito o restore. D254 aveva quindi lasciato bootstrap e restore aperti e aveva
indicato come prossima evidenza una traccia Windows APP12509 da cold-start fino
ad arm, cancel senza dito e re-entry. D255 ha ora acquisito e recuperato quella
traccia. D256 ne ha poi esaurito offline i metadati USBPcap: il bootstrap/seed
è corroborato sul target e il nuovo arm viene accettato senza reset,
re-enumerazione o restore USB esplicito osservato. Il corrective D256 ha inoltre
esaurito la seconda cancellazione della stessa capture: il pending bulk-IN del
nuovo arm termina cancellato al frame finale `218`, seguito da 491,125998
secondi fino al marker host di finalizzazione senza altri packet. Il contratto
terminal-stop host/bus è quindi chiuso, path-bounded, come quiescenza USB; il
disarm, la lifetime e lo stato FDT interno restano non osservati.

D255 ha completato la singola acquisizione richiesta sulla baseline approvata
`f01b81d629ffe8af5eecb92ca93968045d5345ce`. La run canonica
`captures/D255_20260822T205631772Z_85c8c41f/` contiene un pcapng USBPcap da
27.684 byte, SHA-256 `802370d6...cc63337c`, con 218 frame leggibili e primo
frame `1`. Cold attach, UI ready, cancel e re-entry sono stati completati senza
dito. Il launcher ha fallito soltanto dopo `OPERATOR_PHASES_COMPLETE`: Windows
PowerShell 5.1 ha esposto `$null` per `ExitCode` sul `Process` creato con
`Start-Process -PassThru -NoNewWindow` e redirect, pur con processo terminato e
stderr TShark `218 packets captured`. È un failure di finalizzazione host-side,
non un failure di acquisizione.

Il recovery offline ha verificato hash, dimensione, leggibilità, 218 frame e
ordine univoco dei marker senza cambiare hash, size o mtime del raw. Gli
snapshot `run_clock_end`, `guest_topology_after_capture`, cache/log after e il
manifest originale non erano stati prodotti prima del falso failure e sono
`NOT_RECOVERABLE_RETROACTIVELY`; non sono stati ricreati dallo stato corrente.
Il manifest nuovo è esplicitamente `RECOVERED_ARTIFACT`. Il postprocessor reale
accetta questa provenance mantenendo i gate wire: descriptor e primo A8
APP12509 cadono, in quest'ordine, dentro i marker dell'attach manuale. La
capture prova cold attach target-specific, tre `0x36`, match primo seed/cache,
zero IRQ dito/`0x22`/image path nella finestra operatore, re-entry OEM e nuovo
`0x32` accettato. D256 ha chiarito il limite dell'assenza di log/snapshot
`after`: sul bus non compare alcun packet target durante l'intervallo cancel;
dopo l'inizio della re-entry compare una completion bulk-IN cancellata della
richiesta pendente, quindi il medesimo device `1:2` continua sugli endpoint
`01/81` e accetta il nuovo `0x32`. Non compaiono abort/reset, control transfer,
descriptor replay, reconfiguration o re-enumeration. Questo prova re-entry e
re-arm senza restore USB esplicito come prerequisito osservato, ma non prova
`DEVICE_FDT_DISARM_PROVEN` o la lifetime del prior arm. Il secondo cancel chiude
separatamente il comportamento bus: zero packet nell'intervallo operatore, una
sola completion bulk-IN cancellata host-side al frame finale `218`, quindi zero
packet target e totali per il resto della capture fino al duration boundary.
Questo prova la quiescenza USB osservata, non lo stato volatile interno del
sensore. Non è richiesta una nuova capture live equivalente.

Le note successive sulle revisioni del kit e sui precedenti failure sono
provenance storica, superata per lo stato corrente dalla run acquisita e dal
recovery appena descritto.

La terza review AI-PM ha corretto due overclaim residui. Con Goodix assente dal
guest, la UI fingerprint può legittimamente essere nascosta o indisponibile:
pre-attach si verificano perciò soltanto pagina Sign-in options, stato account,
enrollment incompleto, divieto di nuovo PIN e stato PIN esplicito. La
disponibilità sensor-dependent resta `UNKNOWN_BEFORE_ATTACH`; non è un gate di
autorizzazione. Il vero path Settings → Sign-in options → Fingerprint
recognition → Set up/Add a fingerprint viene verificato solo dopo capture
attiva, singolo attach, PnP guest, A8 APP12509 wire-derived e bootstrap passivo.

Il primo preflight nella VM reale ha poi osservato un ulteriore difetto locale
dello stesso D255: self-test `PASS`, zero azioni hardware, autorizzazione non
consumata, una sola `USBPcap1` e cache leggibile in
`C:\ProgramData\Goodix`, ma nessun `goodix*.log`/`wbdi*.log`. L'esistenza di un
log OEM non era mai stata provata come prerequisito e non protegge alcun gate
live-critical. La correzione rende quindi log OEM e cache Goodix fonti
opzionali e indipendenti, classificate `PRESENT|ABSENT`; restano terminali prima
dell'autorizzazione soltanto i path esplicitamente forniti ma illeggibili.

La successiva prima invocazione del ramo live sulla baseline approvata
`74a1ebda24166ac026ef7ed55c15f0d21e4593e3` non ha però superato il setup
pre-autorizzazione: PowerShell ha rifiutato `-Candidates @()` sulla funzione
`Write-OemLogSnapshot` con
`ParameterArgumentValidationErrorEmptyArrayNotAllowed`. Il binding è fallito
prima di entrare nella funzione e prima del confronto con la stringa di
autorizzazione; `$script:AuthorizationConsumed = $true`, il record
`authorization_consumed.json` e `Start-Process` sono tutti successivi nel
control flow. Il tentativo non ha quindi consumato l'autorizzazione, aperto USB,
avviato TShark né raggiunto l'attach host→VM.

La correzione di classe dello stesso D255 marca esplicitamente con
`AllowEmptyCollection` le collezioni di log, cache e setup che possono essere
vuote, e serializza gli snapshot senza righe come JSON letterale `[]`. Le liste
di interfacce restano semanticamente non vuote nel live, ma il binding permette
ora alla funzione di produrre un failure D255 esplicito invece dell'errore
generico del binder. Il nuovo `-PreAuthorizationSimulationOnly` rifiuta
autorizzazione, TShark, selettori e path reali, crea solo fixture sintetiche e
chiama la stessa `Invoke-D255PreAuthorizationEvidenceSetup` del ramo live fino
al boundary immediatamente precedente all'autorizzazione/capture. Copre sia
zero log sia log presente e un audit separato con zero cache root; non usa PnP,
USB o hardware. La suite offline verifica struttura e condivisione del ramo,
ma `pwsh` non è disponibile sull'host Linux: le due modalità sintetiche devono
ancora essere eseguite nativamente in Windows prima di dichiarare il kit pronto
per l'operatore.

La successiva singola run autorizzata sulla baseline
`999483362af23f67790eb6e54f4c02bb48bd6cd5` ha superato quel setup, consumato
l'autorizzazione e avviato TShark su `USBPcap1`, ma si è fermata prima del
prompt di attach perché il launcher pretendeva `wire.pcapng` già creato dopo
un grace period fisso di due secondi. Il processo TShark era ancora vivo;
Goodix non è mai stato collegato al guest e non è avvenuta alcuna azione
sensor-reaching. Una verifica successiva in sola lettura ha osservato il file,
ancora a zero byte, comparso diversi secondi dopo il controllo. È quindi
osservata una race di materializzazione/buffering host-side, non un failure
device-side o una prova di processo TShark non sano.

La correzione corrente elimina soltanto quel requisito pre-attach. Dopo il
breve grace period la readiness significa
`TSHARK_PROCESS_STARTED=true`, `TSHARK_PROCESS_ALIVE=true` e
`GOODIX_PRESENT_IN_GUEST=false`; il nuovo marker
`CAPTURE_PROCESS_STARTED` e il marker compatibile `CAPTURE_STARTED` non
dichiarano file, frame o pcapng valido. Dopo attach e bootstrap passivo il file
deve essere materializzato. Al termine restano obbligatori exit code TShark
zero, pcapng presente e non vuoto e readback TShark di almeno un frame prima di
`CAPTURED_PENDING_OFFLINE_VALIDATION`. I failure TShark includono exit code se
disponibile, command/arguments redatti, stato del path e stdout/stderr redatti.
L'audit locale conserva il timer bounded e il deadline PnP post-attach perché
proteggono rispettivamente durata della capture e vera enumerazione del target;
non esistono altri gate file/processo host-side equivalenti da rimuovere.

Il gate post-attach accetta solo `READY_WAITING_FOR_FINGER`, `UI_UNAVAILABLE`,
`NEW_PIN_REQUIRED` o `UNEXPECTED_PREREQUISITE`. Solo il primo entra nelle due
cancellazioni senza dito; gli altri chiudono la restore phase senza retry,
mutazione account/PIN, UI alternativa, recognition, dito o detach. Il timer
bounded completa comunque la capture: descriptor/A8, cache, primo `0x36` e
bootstrap restano sanitizzabili come
`PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE`, con
`BOOTSTRAP_EVIDENCE_PRESERVED=true` e
`RESTORE_EVIDENCE_ACQUIRED=false`.

La re-entry OEM e perfino un nuovo `0x32` accettato provano soltanto che una
nuova sessione/arm è accettata; non osservano necessariamente la vita del prior
arm né un disarm FDT. Il sanitizer separa quindi cancel host, comandi wire,
close/D0Exit/D0Entry, re-entry, nuovo arm, cancel device-side e lifetime del
prior arm. Senza comando/transizione target-specific semanticamente chiusa,
`DEVICE_FDT_DISARM_PROVEN=false`, `RESTORE_CLOSED=false` e
`RESTORE_CLOSURE_DECISION=AI_PM_REVIEW_REQUIRED`. Ogni IRQ finger-down
`0x0002`, `0x22 [01 00]` o image path nella finestra operatore invalida la
restore evidence. La correzione resta pronta soltanto per review AI-PM, non per
una run operatore; nessuna autorizzazione live è implicita.

D247 cambia inoltre la strategia implementativa, senza modificare il confine
hardware: fino a D246 il codice di progetto è rimasto BSD-2-Clause e clean-room
rispetto a Rockytkg; dalla baseline post-D247 il futuro core userspace e i tool
collegati sono `GPL-2.0-or-later`, con riuso diretto Rocky consentito nel solo
dominio GPL quando licenza e provenance sono verificate. La validazione
factory-preserving sul target 12509 resta indipendente e obbligatoria. Il futuro
driver/glue libfprint è un dominio separato `LGPL-2.1-or-later`. D247 non ha
importato codice funzionale esterno e non ha eseguito AF/FDT/capture o hardware.
La verifica GitHub autenticata fornita dall'AI Supervisor ha poi chiuso il
blocker di provenance sulla baseline Rocky
`227eba219fa9e3fbac5bd59aca79f624f67cd11b` del 2026-08-17; D247 è quindi
`READY`. La verifica è esterna al workspace Codex ed è registrata come tale.
Resta obbligatoria la verifica puntuale di diritti, SPDX e componenti terzi per
ogni file che un futuro step deciderà effettivamente di importare.

D248 ha consolidato esclusivamente l'organizzazione del repository, senza
modificare runtime o confine hardware. Cache Python versionate e due backup
`.orig` generati sono stati rimossi dopo audit; i contenuti dei backup restano
ricostruibili dal commit storico `1c66b43c63e21e2dc4547a903154167233731fdd`
e non avevano riferimenti. `src/`, `tests/` e `poc/` rimangono congelati nelle
posizioni storiche per preservare riproducibilità e import della catena
D232–D246. Il nuovo sviluppo post-D247 continua invece nei domini `core/`,
`tools/` e `libfprint-driver/` definiti dalla mappa licenze.

| Area | Stato | Risultato |
| --- | --- | --- |
| Framing USB A0/B0 | confermato | endpoint, chunk da 64 byte, checksum e correlazione sono noti |
| TLS 1.2 PSK | handshake completo verificato live in D245 | D241 aveva provato il server flight; D245 ha completato il handshake sul target e si è fermato prima di D4 |
| Configurazione `0x80`/`0x90` | confermata per i path studiati | effetti volatili per quelle sole operazioni |
| A2 e `0x70` | convergenza host-side D231 | reset solo sensore e set-mode idle; corpi resident ancora assenti |
| Readback resident arbitrario | esaurito nel corpus locale | nessun path host-side safe trovato da D230 |
| Exact OEM replay | implementato e revisionato offline in D232 | state machine single-shot e oracle sintetico; live compilato fuori e D233 non autorizzato |
| Binding D190 PSK→E4 | reference recuperata e verificata | cinque KAT OEM-attributed non circolari e PE canonico hash-gated |
| Backend/orchestratore D233 | verificato offline, hard-disabled | schema candidate distinto; D234 e rischio operatore non autorizzati |
| Entrypoint production D235 | composto e verificato offline, hard-disabled | path reali deterministici, mapping terminale e restore collegati; D236 non autorizzato |
| Evidenza live D236 | parziale, non è un cold-start riuscito | E4 binding reale `match`; primo A2 trasmesso; ACK reale `B0/A2/07`; zero TLS/retry/persistent-write |
| Consolidamento D238 | verificato offline, source-sealed | policy ACK unica, replay pre-D1 completo con `0x01` e `0x07`, osservabilità redatta e unico kit operatore |
| Evidenza live D239 | pre-D1 integralmente superato su 12509 | 12 comandi, E4 `match`, D1 seguito da B0/TLS diretto di 52 byte; stop host-side `unexpected_data` |
| Transizione TLS D241 | live single-shot consumato, fail-closed | handoff e PSK object binding verificati; timeout dopo server flight; zero D4/app-data/retry |
| Run live D242 | fail-closed al primo E4 | OUT E4 completato, bulk IN in timeout senza frame completo; binding/TLS/pacing non raggiunti; cleanup/restore/reseal riusciti |
| Run live D243 | fail-closed al primo E4 | A0 corto ripristinato; OUT E4 completato e stesso timeout bulk IN; zero binding/TLS/retry; cleanup/restore/reseal riusciti |
| Run live D244 | fail-closed al primo E4 | fresh host boot documentato e controllo valido; OUT E4 completato, bulk IN timeout; nessuna prova di perdita elettrica sensore; zero retry e cleanup/reseal riusciti |
| Run live D245 A8→E4→TLS | successo, consumata | ACK A8 `07`, FW12509 esatto, E4 `match`, pre-D1/D1 e handshake TLS completi; stop prima di D4, zero retry/app-data/persistent-write |
| Run live D246 TLS→D4 | successo, consumata | handshake TLS completo; D4 attempt/send `1/1`, ACK `01`, nessuna response/app-data/retry/write persistente; `STOP_AFTER_D4`, cleanup/restore/reseal riusciti |
| Run live D250 D4→AF | eseguita una volta, marker consumato, fail-closed nel validator | TLS e D4 riusciti; AF logical 13 / physical 64 zero-tail inviato una volta; A0/AE strutturalmente valida con body 16; byte0 perduto dalla telemetria; zero retry/write/app-data; cleanup/restore/reseal riusciti |
| Run live D251 D4→AF | successo, consumata | exactly-one AF/AE; byte0 opaco `0`, flags `0x02`, POV false/TLS true/locked false, zero retry/write/app-data, cleanup/restore/reseal riusciti, `STOP_AFTER_AF` |
| Boundary D252 fresh-FDT | bloccato offline, nessun kit live | tabella appresa via `0x36`/IRQ `0x0100` ma seed/freschezza current-path e restore non provati; target post-IRQ usa `0x22`, non `0x20` |
| Boundary D253 seed/restore/`0x22` | bloccato offline, nessun kit live | current core corretto a IRQ2→`0x22`; seed ultimo, zero-tail `0x36` e restore deterministico non chiusi; richiesta evidenza OEM esterna mirata |
| Audit esterno D254 | bloccato offline, nessun kit live | cache/layout OEM 5110/12117 e capture Issue63 riducono bootstrap e corroborano IRQ2→`0x22`/tail; seed APP12509 e no-finger restore restano non chiusi |
| Acquisizione Windows D255 | capture riuscita e run consumata; finalizzazione host-side recuperata offline | 27.684 byte/218 frame, cold attach APP12509, fasi zero-finger complete, seed/cache match; snapshot after non recuperabili e restore non chiuso; nessuna nuova capture richiesta |
| Contratto lifecycle D256 | audit offline completo dei packet USBPcap D255, incluso corrective terminal-cancel | primo cancel: re-entry e nuovo `0x32` accettato senza restore USB esplicito; secondo cancel: zero packet nell'intervallo, pending bulk-IN cancellato al frame finale `218`, zero packet residui e quiescenza USB host/bus provata; disarm/lifetime/stato FDT interno non osservati |
| Candidate fresh-FDT D257 | BLOCKED exact offline; nessun backend/kit live | replay proiettato storico PASS; sequenza esatta D255 `36,50,36,82,20,36,32`, ma gate host dinamici NAV/delta/baseline non derivabili; first-`0x36` single-shot fail-closed; freshness non è il solo blocker |
| Chiusura gate host D258 | avanzamento offline, candidate ancora BLOCKED | orchestratore target in `gfusb.dll`; gate `0x82` chiuso e implementato; `0x50`/`0x20` corretti come input a classificatori post-stage2 ancora non riproducibili; timeout per comando; zero hardware |
| Corrective contratto minimo D259 | BLOCKED sul plumbing TLS runtime; live non autorizzato | Classe A confermata meccanicamente dal CFG; replay B0 ordinato subito dopo `0x20`, same-`SSLObject` e continuità TLS PASS offline; il runtime sealed D245 chiude e non espone l'engine, quindi `READY_FOR_FDT_LIVE_REVIEW=false` |
| Runtime persistente D260 | architecture readiness PASS offline; operational/live false | nuovo coordinator GPL con un server/sessione/handshake TLS, D4 A0 plaintext, EventSource separato e minimal FDT continuo; 15 failure contenuti, `src/`/launcher storici invariati; physical FDT A0 ancora astratto |
| Corrective readiness D261 | PASS offline per baseline-approval; operational review promosso, live false | closure import 16/16 e import purity PASS; non-secret prima del secret; capability CLI-intent/Live-I/O distinte, 24 failure e 13 casi demux execution-derived; 238 test PASS, full commit SHA `e9073a171697bd68dd2debabb851f23d007bf718` approvato da Utente e AI-PM, zero-tail per comando resta rischio live |
| Codec immagine | confermato offline | record 7684 byte → raster u16 `80x64` |

## Fonti e confini di pubblicazione

Il repository privato è il workspace canonico di sviluppo. Il repository
pubblico è una superficie di pubblicazione congelata: non viene sincronizzato
da D247 e potrà ricevere soltanto un export futuro, separato, sanitizzato e
auditato. Un working tree pulito/equivalente non rende pubblicabile la history
privata; capture, DLL, firmware, secret o dati biometrici transitati nella
storia richiedono clean export, nuova storia o filtro dedicato.

Le evidenze autentiche private hanno sede canonica in `<git-root>/captures/` e
possono essere versionate nel repository privato per renderle disponibili agli
strumenti autorizzati sul remoto privato. Bundle ed export pubblici escludono il
raw; la futura pubblicazione richiede sanitizzazione esplicita di contenuto e
history. Non esiste sincronizzazione automatica privato→pubblico.

La root contiene soltanto fonti canoniche, licenze, linee guida e directory di
progetto. Gli output Dxxx sono step-local e non cumulativi in
`analysis/Dxxx/`, inclusi bundle e checksum; `analysis/README.md` è il solo
indice sintetico e non sostituisce questo manuale. Il manifest
`analysis/D248/D248_binary_relocation_manifest.json` fissa blob Git, SHA-256,
dimensione, destinazione e riferimenti dei bundle storici in root. Le undici
coppie D230–D238 possono essere spostate insieme in una fase meccanica
byte-preserving. La coppia D239 resta invece intenzionalmente in root perché il
controllo offline D245 apre quel path per verificare i launcher storici: la
riproducibilità prevale su una root solo esteticamente perfetta. Rimuovere
l'eccezione richiede uno step futuro che migri esplicitamente la dipendenza
D245 e ne verifichi nuovamente l'executable closure. La relocation di layout
non cambia stato tecnico né autorizzazioni live.

Le categorie restano distinte:

- capture Windows, `gfusb.dll`, APP12509 ed evidenza live locale sono evidenza
  privata target-specific e autorità primaria per il comportamento sul target;
- codice esterno Rockytkg verificato GPL può essere una fonte implementativa
  riusabile in `core/`/`tools/`, con attribution e ledger, ma non prova safety;
- materiale OEM/proprietario, secret, capture e dati biometrici non sono
  redistribuibili e non ricevono una licenza open source per collocazione;
- documentazione e codice pubblicabile seguono la mappa file/directory in
  `docs/LICENSING_AND_PROVENANCE.md`.

Il corpus D230 è `GoodixExport.zip`, indicato dall'operatore come corpus privato
recuperato e già provenance-validato, SHA-256
`2b76e294059fcfa2f32a6e75d92d04731b41a01bd3221852b5584ce409a3e45e`.
Contiene `gfusb.dll` SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`
e una capture recuperata SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
La prima capture resta definitivamente perduta e non è sostituita da riepiloghi.

La testimonianza indipendente di `mkl-corbachoh` nella issue GitHub #1 (https://github.com/Rockytkg/goodix-linux-27c6-5125/issues/1) resta
classificata `EXTERNAL_THIRD_PARTY_LIVE_CORROBORATION`. Sul proprio target
riferisce `27c6:5125`, chip `0x2504`, firmware nativo 12509 preservato,
TLS-PSK, enrollment, verifica same/different-finger, autenticazione PAM e
nessun firmware flash. Riferisce però anche `MCU read 0xBB010003 status 0x01`,
quindi assenza di dati PSK preesistenti, e provisioning una tantum di una nuova
PSK; riporta inoltre la coesistenza di eventi FDT plaintext e frame immagine
protetti TLS. È corroborazione esterna utile, ma non prova primaria del nostro
target, non prova la preservazione della PSK Windows/factory preesistente e non
autorizza automaticamente alcuna futura operazione live.

### Rockytkg — snapshot locale implementativo canonico

Il riferimento operativo unico è lo snapshot versionato
`<git-root>/Rockytkg/`; la sua scheda canonica è
`Rockytkg/PROVENANCE.md`. Il repository online
`Rockytkg/goodix-linux-27c6-5125` registra l'origine ma non è una dipendenza del
workflow ordinario. La Issue #1 resta una fonte esterna distinta e non è
incorporata da un normale snapshot Git.

La baseline preservata è il commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`: il `LICENSE` assegna
GPL-2.0-or-later al codice originale, LGPL-2.1-or-later a `src/goodixgf.c`,
lascia `libfprint/` ai termini upstream ed esclude dalla blanket license il
firmware vendor. Gli header campionati confermano GPL per
`goodix_capture.c`, `goodix_init.c`, `goodix_tls.c` e LGPL per `goodixgf.c`;
il copyright repository-level indica `liushicong (Rockytkg)` senza implicare
titolarità su ogni riga o contributo terzo. Il tree upstream preservato è
`6dda93a960ceddb085c59b5382df47ecc5d56a39`; il gitlink upstream originario di
`libfprint` è `7ebe0c809b4d1df3400e84299a4ec4acdea84590`, mentre nello snapshot locale
`Rockytkg/libfprint/` è materializzato come file normali, senza submodule attivo
o `.git` annidata.

Preservazione non equivale a diritto di riuso: ogni import richiede audit
file-specifico e registrazione nel ledger. Il codice originale Rocky è GPL,
`src/goodixgf.c` è LGPL, `libfprint/` conserva i termini third-party e
`firmware/st411sec_app.bin` più i byte firmware in `include/goodix_fw.h` sono
materiale vendor fuori dalla blanket GPL/LGPL. Lo snapshot e il materiale
vendor non confluiscono automaticamente nel repository pubblico.

La issue Rocky #1 verificata chiarisce inoltre che la validazione hardware
diretta dell'autore riguarda un'unità 12508, non un 12509 non modificato. Il
codice Rocky è quindi una fonte implementativa autorizzata, ma resta
corroborazione esterna e non prova primaria della preservazione factory/PSK o
del comportamento APP12509. Questi due ruoli non vanno confusi; ogni futuro
import richiede comunque verifica file-specifica di diritti e SPDX.

## Architettura

```text
Windows Biometric Framework
        |
EngineAdapter.dll / AlgoChicago.dll
        |
gfusb.dll (UMDF NativeUSB, A0/B0, TLS)
        |
Goodix MCU: APP ST411/12509 + resident code non disponibile
```

Il target dichiara `GF_ST411SEC_APP_12509`. L'APP mappata disponibile inizia a
`0x0802c000`; il codice resident necessario per interpretare A2 e `0x70` è sotto
questo indirizzo.

### Architettura software e licensing boundary post-D247

```text
GPL userspace core
  transport
  protocol
  tls
  fdt
  capture
  image
      |
      | licensing boundary
      v
LGPL libfprint driver/glue
```

L'architettura post-D247 è stata adottata precisamente per consentire il riuso diretto, l'adattamento e l'integrazione nel core/ e nei tools/ GPL del codice Rockytkg compatibile GPL, preservandone licenza, attribuzione e provenienza. Analogamente, codice Rockytkg specificamente disponibile sotto licenza LGPL compatibile può essere valutato per libfprint-driver/.

Il licensing boundary non vieta quindi il riuso di Rockytkg: impedisce soltanto che espressione GPL-only venga trasferita dal dominio GPL al driver upstream-facing LGPL. Tale passaggio è possibile solo in presenza di dual licensing o di una licenza alternativa compatibile concessa da tutti i titolari pertinenti; in assenza, l'implementazione LGPL deve essere indipendente e basata su specifiche, fatti di protocollo, test ed evidenza, non sull'espressione GPL-only.


## Trasporto USB

L'interfaccia usa bulk OUT `0x01` e bulk IN `0x81`, max packet 64. Interrupt IN
`0x82` è presente ma non è una superficie host→device del protocollo ricostruito.
EP0 è usato per enumerazione/configurazione USB standard.

Il frame A0 ha magic `0xa0`, lunghezza LE16 e tag esterno additivo. Il payload
interno contiene control, lunghezza e checksum. Alcuni builder 5125 calcolano il
checksum in coordinate pre-OR: il control logico e quello wire vanno conservati
separatamente. Non è corretto dedurre sempre il logico con `wire & 0xfe`.

B0 avvolge direttamente un record TLS completo con header Goodix di quattro
byte; non aggiunge cifratura o compressione.

Le lunghezze dichiarate A0/B0 descrivono soltanto il frame logico. Nella capture
D175 tutte le 56 submission bulk OUT A0/B0 osservate sono staging buffer host
da 64 byte; la tail dell'ultimo blocco è fuori dalla lunghezza dichiarata e,
nei B0 del server flight esaminati, è nonzero. I byte del frame costruito, i
byte USB richiesti e quelli completati sono quindi misure distinte. Questa
osservazione host-side **non** prova che una tail A0 artificialmente zero-filled
sia device-side equivalente: il contenuto semanticamente rilevante della tail
Windows resta non noto. La run D242 ha mostrato che il padding zero generico
coincide temporalmente con la perdita di responsività E4 già superata live in
D239/D241; la run D243 ha poi mostrato che rimuoverlo non è sufficiente a
recuperare quel path.

Lo stato canonico è perciò:

```text
D243_A0_FIXED64_CAUSAL_STATUS=FALSIFIED_AS_SUFFICIENT_EXPLANATION_BY_D243_LIVE
D244_A0_FIXED64_DEVICE_EQUIVALENCE_STATUS=UNRESOLVED
D244_B0_FIXED64_DEVICE_EQUIVALENCE_STATUS=NOT_YET_LIVE_REACHED
```

La claim `OEM_COMMON_A0_B0_TRANSPORT_CONTRACT_VERIFIED` resta ritirata come
claim device-side. D243/D244 invia gli A0 in chunk logici `<=64`, con ultimo OUT
corto e completion richiesta pari alla lunghezza del chunk. Solo B0/TLS usa
staging fisico da 64 byte, tail zero-initialized e completion esattamente 64.
La sola eccezione D246 è il frame D4 byte-exact
`a00600a6d403000000d3`: la capture primaria mostra una submission fisica da 64
byte con tail interamente zero. Questa evidenza non generalizza il fixed-64 ad
altri A0.
Un flag
`server_hello_sent` prova al massimo emissione e wrapping; la trasmissione
completa richiede completion USB full-length per ogni blocco richiesto.

## Sicurezza e TLS

Il profilo noto è TLS 1.2 pure PSK, suite `0x00a8`, identity
`Client_identity`, dispositivo client e host server. Il materiale autentico del
laptop originale ha prodotto una singola E4 read-only `MATCH`, ma questo non
costituisce una procedura generale di provisioning.

D241 ha inoltre verificato il binding di ownership: il medesimo oggetto
`SecretBuffer` validato da E4 è stato consegnato al server TLS, senza copia o
sostituzione intermedia. Questo prova l'identità dell'oggetto e il percorso
runtime, non prova da solo che il dispositivo abbia completato la derivazione
crittografica o accettato il server flight.

D231 conferma nella DLL che il plaintext DPAPI viene copiato nell'area PSK
runtime e passato direttamente al setup TLS senza un secondo KDF OEM. Il
materiale è portabile solo perché recuperato legittimamente dalla macchina
originale; questa conclusione non autorizza PSK zero, sostitutive o cross-device.

`PSK_PORTABILITY_STATUS=PSK_PORTABILITY_PROVEN` con
`PORTABILITY_SCOPE=ORIGINAL_DEVICE_AND_LEGITIMATELY_EXPORTED_MACHINE_BOUND_MATERIAL_ONLY`.
Non è richiesto un challenge Windows-only dopo il recupero legittimo e lo
stesso materiale può essere riusato su Linux senza riprovisionare il sensore.

Nessun secret deve essere stampato, copiato o incluso negli artefatti. Un futuro
test hardware richiede autorizzazione separata, fail-closed e con ripristino del
servizio Windows/Linux previsto.

## Lifecycle osservato

La capture recuperata contiene il cold-start:

```text
E4 → A2 → 82 → A6 → A2 → 70 → 80×4 → 90 → D1 → B0
```

L'ordine è osservato, non dimostrato come insieme causale minimo. D231 chiude la
semantica host-side di A2 e `0x70` per il replay OEM esatto; non trasforma la
sequenza in una ricetta generale né dimostra i body resident istruzione per
istruzione.

### Lifecycle ACK/risposta consolidato in D238

La capture primaria locale `rilevamento.pcapng` (SHA-256
`50071c0f...19c184b`, già classificata storicamente nel filone D175) mostra
status ACK `0x01` in tutte le undici fasi pre-D1 che producono ACK. E4, A2,
`0x82`, A6 e `0x90` hanno poi una risposta A0 distinta con lo stesso control;
`0x70` e le quattro `0x80` sono ACK-only. D1 non ha ACK A0: la risposta attesa è
direttamente B0 con ClientHello TLS.

| Fase | Control | ACK ammessi D238 | Risposta dopo ACK | Evidenza locale primaria |
| --- | --- | --- | --- | --- |
| E4 | `e4` | `01`, `07` | A0/E4 validator tipizzato | capture `01`; live D236 `07` + binding `match` |
| A2 #1 | `a2` | `01`, `07` | A0/A2 IRQ tipizzato | capture `01`; live D236 `07` |
| `0x82` | `82` | `01`, `07` | A0/82, body hash-pinned | capture `01`; `07` ereditato dalla semantica ACK di sessione |
| A6 | `a6` | `01`, `07` | A0/A6, body hash-pinned | capture `01`; `07` ereditato dalla semantica ACK di sessione |
| A2 #2 | `a2` | `01`, `07` | A0/A2 IRQ tipizzato | capture `01`; stesso control del live `07` |
| `0x70` | `70` | `01`, `07` | nessuna | capture `01`; `07` ereditato dalla semantica ACK di sessione |
| `0x80` ×4 | `80` | `01`, `07` | nessuna | capture `01`; `07` ereditato dalla semantica ACK di sessione |
| `0x90` | `90` | `01`, `07` | A0/90 body esatto `0100` | capture `01`; `07` ereditato dalla semantica ACK di sessione |
| D1 | `d1` | nessuno | B0/TLS diretto | capture primaria D175 e live D241: ClientHello TLS 1.2 verificato; D241 ownership exactly-once |

`0x07` non è stato promosso come risposta applicativa specifica di E4 o A2. La
capture mostra `0x01` invariato attraverso control diversi; i run reali D236
mostrano `0x07` invariato attraverso E4 e A2 nello stesso path e nello stesso
firmware. D238 lo modella quindi come secondo valore di successo ACK di
trasporto/sessione, con allowlist esplicita per ogni fase. Ogni altro status,
echo, lunghezza, control, ordine o body resta terminale e fail-closed. Questa è
un'inferenza cross-control corroborata, non una definizione nominale dei bit:
il significato interno di `0x01`/`0x07` resta ignoto.

Nella capture locale ACK e risposta tipizzata sono frame distinti in completion
USB separate. Il trasporto D238 accetta anche due frame logici esatti nella
stessa completion, perché il boundary USB non cambia il framing A0; non accetta
una forma combinata o payload più permissivi. Il report distingue completion
separate, coalesciute e frame frammentati. Gli artefatti storici nominati D43,
D178 e D226 non sono presenti nell'albero D238 corrente e non vengono simulati
o citati come fonti primarie; la prima capture resta definitivamente perduta.

## Configurazione prima di TLS

Le quattro scritture `0x80` e il download `0x90` studiati sono ricondotti a
registri/SRAM/configurazione volatile nell'APP disponibile. `0x90` è un path di
download/write e non deve essere descritto come read.

A2 subtype 2 dispatcha a `0x080272e1` (allineato `0x080272e0`). La DLL target
1.1.125.14 costruisce il body `{01,14}` da
`ResetMCUAndFingerprint(false,true)`: bit 0 reset sensore, bit 1 reset MCU. I
due frame recuperati sono quindi reset del solo sensore.

La famiglia `0x70` usa la tabella callback SRAM con target `0x0802b8f5`
(allineato `0x0802b8f4`). La DLL costruisce `{14,00}` dal ramo
`ChicagoHUSetMode(7,0,0)`, log `setmode: idle`, e lo invoca all'inizio di
`ChicagoHUsetDac`, prima delle write `0220/0236/0238/023a`. Questi risultati
convergono con la ricostruzione riferita per la DLL 1.1.125.13 e con il wire.

I corpi target-specific restano assenti. La lifetime è classificata
operativamente volatile e senza evidenza di mutazione persistente per l'exact
OEM replay; non è una prova assoluta device-side di non-mutazione NVM.

## Convergenza e gate D231

`D231_DECISION=D231_PRE_D1_CLEARED_FOR_EXACT_OEM_REPLAY`

`PRE_D1_PATH_CLEARED_FOR_EXACT_OEM_REPLAY=true` vale esclusivamente per la
sequenza byte-identica, i DAC/config del dispositivo originale e il materiale
PSK autentico già validato. Non è un gate universale e non autorizza hardware.

La roadmap immediata è:

```text
D231 -> decisione statica chiusa
D232 -> implementazione/review OFFLINE chiusa dell'exact OEM replay
     -> live hard-disabled, allowlist byte-pinned, test sintetici pass
D233 -> backend USB/TLS reale + review soltanto OFFLINE, hard-disabled
D233 closure -> reference D190 + binding runtime + orchestratore candidate offline
D234 -> accettazione rischio concessa, ma nessun live: blocker entrypoint
D235 -> entrypoint production-candidate composto e testato soltanto OFFLINE
     -> doppio source seal D235/D233, nessun runtime enablement
D236 -> autorizzato, unseal revisionato, ma bloccato prima del preflight root
     -> zero enumerazione/open/comandi; source resealed
D237 -> evidenza D236 normalizzata e boundary di sicurezza riconfermato
D238 -> policy pre-D1 consolidata e kit operatore source-sealed
     -> tentativo operatore fallito sull'import Python, prima di unseal/USB
D239 -> launcher corretto + dry-run operatore production-shaped fino al pre-USB
     -> gate offline PASS; successiva run autorizzata: pre-D1 completo e B0/TLS
D240 -> SUPERSEDED / DO_NOT_EXECUTE / NOT_EXECUTED
D241 -> run live single-shot consumata: ClientHello verificato e server flight
     -> trasmesso, poi timeout senza ClientKeyExchange; zero retry/D4/app-data
D242 -> run live single-shot: timeout al primo E4 dopo generic fixed-64 A0
     -> binding/TLS/pacing non raggiunti; cleanup/restore/reseal riusciti
D243 -> split A0/B0 chiuso offline, poi run live single-shot consumata
     -> A0 corto D241 ma stesso timeout E4; binding/TLS non raggiunti; zero retry/D4
D244 -> evidenze D242/D243 verificate, timeout localizzato su bulk IN dopo OUT
     -> successiva run fresh-host valida: E4 OUT completato, bulk IN timeout
     -> fresh host boot falsificato come condizione sufficiente; power loss sensore non provata
D245 -> record storico canonico D179 A8→E4 + corroborazione locale D230
     -> D43 ACK01 e D175 ACK07 seguiti dalla stessa response 12509: vecchia policy ACK07 terminale falsificata
     -> A8 read-only una volta; ACK01/07 autorizzano una response bounded; poi E4 solo su FW12509 esatto
     -> closure offline PASS, poi live PASS: ACK07, FW12509, E4 match e TLS completo; stop prima di D4
     -> bundle 9813878a...569f precedente alla correzione ACK07 SUPERSEDED / DO_NOT_USE_FOR_LIVE_AUTHORIZATION
D246 -> evidenza D245 validata; audit primario TLS Finished→D4→ACK→AF
     -> D4 classificato volatile sul receiver APP12509 esatto; host e device persistence escluse per quel path
     -> patch offline D4 exactly-once, ACK d4/01 only, STOP_AFTER_D4; closure PASS
     -> launcher live-capable hard-gated e testato offline; successiva run live single-shot PASS
     -> TLS completo, D4 attempt/send 1/1, ACK d4/01, STOP_AFTER_D4; zero retry/app-data/persistent-write
     -> cleanup/restore/reseal riusciti; AF diventa il prossimo confine non valutato
D250 -> candidate AF exactly-once chiuso offline, poi run live singola consumata
     -> TLS e D4 riusciti; AF zero-tail attempt/send 1/1; A0/AE strutturalmente valida body 16
     -> abort fail-closed sul gate byte0==1; response_count incrementato troppo tardi; byte0 perso
     -> cleanup/restore/reseal riusciti; zero retry/app-data/persistent-write
D251 -> audit byte0: gfusb usa byte1 bit0/1/3 e non confronta byte0; Rocky corrobora
     -> byte0 riclassificato opaco; validator/telemetria corretti, wire D250 invariato
     -> closure offline PASS; successiva run live single-shot PASS e marker consumato
     -> AE unica valida: byte0=0 opaco, flags=0x02, POV false/TLS true/locked false; STOP_AFTER_AF
D252 -> audit offline fresh-FDT: tabella appresa da 0x36/IRQ0100, ma seed/freschezza current-path aperti
     -> target IRQ2 seguito da wire 0x22, non 0x20; nessun cancel/restore post-FDT provato
     -> D252_LIVE_BOUNDARY=BLOCKED; nessun kit live e zero hardware
D253 -> dataflow seed delimitato; core corretto a IRQ2->0x22; restore ancora ignoto
D254 -> audit pubblico hash-gated: WBDI=5110/12117, Issue63=5125/FW ignoto
     -> Issue63 corrobora 21/21 IRQ2->0x22 e residuo tail 0x36 agli stessi offset
     -> bootstrap ridotto ma non chiuso; restore non ridotto; nessun live
D255 -> kit offline per una sola capture Windows APP12509 correlata
     -> USBPcap attivo prima del cold attach VM; wire+WBDI+cache+marker UTC
     -> sanitizer hash-gated, redazione OTP/PSK/biometria; zero hardware in D255
     -> prima review FAIL: API PowerShell 5.1 e timestamp WBDI MMDD non chiusi
     -> corrective: helper PS5.1, self-test, clock start/end, log delta/rotation
     -> seconda review FAIL: recognition non provata e enrollment VM non completato
     -> corrective VM: capture-before-attach, singolo attach GUI, PnP+descriptor+A8
     -> setup/add-fingerprint zero-finger; IRQ2/0x22/image invalidano la run
     -> preflight reale PASS; i failure locali pre-attach sono stati corretti nello stesso step
     -> run finale acquisita: 27.684 byte/218 frame; cold attach, zero finger, cancel e re-entry
     -> recovery/postprocess offline PASS; seed/cache match; nessuna nuova capture richiesta
D256 -> timeline completa dei 206 packet target nel raw D255 hash-gated
     -> cancel interval senza traffico target; una completion bulk-IN cancellata dopo re-entry begin
     -> stesso bus/device ed endpoint; nessun abort/reset/descriptor replay/re-enumeration
     -> nuovo 0x32 accettato senza restore USB esplicito osservato
     -> secondo cancel: pending IN cancellato al frame finale; zero packet residui
     -> terminal-stop host/bus chiuso come quiescenza; stato interno/lifetime non osservati
D257 -> lifecycle FDT e provider seed esplicito implementati offline, senza backend USB
     -> corrective raw D255: bootstrap esatto 36,50,36,82,20,36,32
     -> replay precedente riclassificato sottosequenza proiettata PASS_HISTORICAL
     -> gate host dinamici NAV/delta/baseline non derivabili; candidate esatto BLOCKED
     -> first 0x36 exactly-once, ACK/IRQ/validator obbligatori, zero retry e cleanup fail-closed
     -> IRQ2->0x22 exactly-once e primo record immagine chiusi su fixture sintetica
     -> cache riusata con successo oltre 27 minuti dopo mtime; TTL generale ignota ma non safety blocker
D258 -> orchestratore target gf_update_all_base recuperato nel gfusb.dll hash-gated
     -> 0x50 NAV e 0x20 baseline acquisiti prima di stage2, classificati soltanto dopo stage2
     -> 0x82 chiuso: byte1 unsigned, abs-delta sui word FDT grezzi; predicate implementata
     -> timeout per comando 36/50/82=500, 20=2000, 32=100 ms; zero retry
     -> replay esatto avanza wire-exact fino al terzo 0x36, poi fail-closed sui classificatori NAV/image
     -> B0 D255 non decifrato: input PSK non disponibile nel confine user-readable; nessun privilegio richiesto
D259 -> branch audit dei return NAV/image 0,1,2,3 e altri/negativi sul gfusb.dll hash-gated
     -> return 1 conserva la base; ogni altro return copia la base acquisita e marca cache host dirty
     -> nessun effetto su tabella/payload/reachability 0x32, comandi USB, retry o recovery A2/0x70
     -> B0 resta obbligatoriamente consumato/autenticato/decrittato dalla sessione TLS attiva
     -> replay minimo completo PASS: due delta, zero classifier/raster/cache/retry/persistenza, final 0x32 una volta
     -> Classe A: minimal contract chiuso offline e pronto per review live separata; READY_FOR_FDT_LIVE=false
```

L'accettazione D234 è stata consumata dal suo esito terminale senza alcun live
run. D236 ha ricevuto una nuova accettazione, ma si è chiuso al gate root prima
dell'inizio del live; per qualunque step successivo l'accettazione è nuovamente
`not_granted`,
`D233_AUTOMATIC_RESET_ON_FAILURE=forbidden` e il live resta `NOT_AUTHORIZED`.
E0/A4/F0/F4, erase, IAP, ClearApp, boot change, provisioning e varianti
cross-device restano vietati. Nel caso peggiore credibile il sensore può restare
in stato protocollo ignoto o non enumerato e richiedere recovery manuale.

La prima capture è definitivamente perduta; D231 confronta a livello packet la
sola capture recuperata. I claim 1.1.125.13 sono corroborazione indipendente
fornita, ma il relativo binario non appartiene al corpus locale.

## Implementazione e safety wall D232

`D232_DECISION=D232_READY_FOR_D233_RISK_ACCEPTANCE_REVIEW` significa soltanto
che il contratto/state model sintetico è pin-nato e testato offline.
Il modulo clean-room `src/goodix5125_d232_offline.py` è l'unico seam D232:
contiene codec A0/B0, gate del materiale locale, boundary PSK, preflight come
validazione di dati forniti, state machine e report. Non contiene backend USB,
enumerazione, driver detach, chiamate libusb o entrypoint live.

La macchina autorizza una sola transizione alla volta:

```text
START -> IDENTITY_REVALIDATED -> E4_MATCH -> A2_1_OK -> CHIPID_OK
-> OTP_OK -> A2_2_OK -> MODE_IDLE_OK -> DAC_1_OK -> DAC_2_OK
-> DAC_3_OK -> DAC_4_OK -> CONFIG_OK -> D1_SENT_CLIENT_HELLO_OK
-> TLS_HANDSHAKE_OK -> CLOSE
```

Le richieste sono esattamente `E4/A2/82/A6/A2/70/80x4/90/D1`, poi TLS.
A2 `{01,14}`, `0x70` `{14,00}` e il frame D1
`a00600a6d103000000d7` hanno golden vector. D4, E0, A4, F0, F4, IAP,
ClearApp e provisioning sono irraggiungibili. Non esistono salti, retry o reset
automatici; timeout, completamento ambiguo, ACK/DATA/IRQ inattesi, ChipID o OTP
errati, mismatch E4/config, re-enumeration inattesa, alert TLS e Bad Record MAC
terminano in `STOP` senza autorizzare la fase successiva.

I quattro valori DAC e il payload `0x90` derivano esclusivamente dalla capture
target locale provenance-valid. Il manifest pubblicabile conserva ordine,
offset, lunghezze e SHA-256; il raw `0x90` resta escluso e in un futuro D234
dovrebbe essere installato come file locale regular, root-owned, mode `0600`,
non symlink, con lunghezza 224, hash, finalizer e correlazione DAC tutti validi.
La prima capture resta definitivamente perduta: la provenance è completa per il
replay osservato, ma la coverage packet-level rimane una sola capture.

La PSK non è nel source, fixture, report o bundle. Il boundary production
accetta soltanto il record canonico `G5125POC` da 88 byte, SHA-256
`eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75`,
regular, root-owned `0600` e non symlink. Il loader verifica magic/hash, estrae
i 32 byte di transport secret dall'offset canonico senza stamparli e azzera il
record temporaneo. La stessa istanza `SecretBuffer` validata contro E4 è quella
consegnata al TLS e viene azzerata in cleanup; non esiste fallback
zero/random/sostitutivo. I test offline usano esclusivamente secret sintetici e
non aprono lo store reale.

`D232_LIVE_CAPABILITY=0` è un vincolo source: nessun flag, ambiente o config può
abilitare il live, non esiste un backend/entrypoint hardware e un oggetto backend
diverso dall'oracle sintetico esatto viene respinto. Il backend aggiunto in D233
resta a sua volta sigillato a livello source.

Il report sintetico è JSON redatto, atomico, mode `0600` e pubblicato anche sui
failure; registra fase, abort class, command count, USB open count (sempre zero
in D232), handshake, cleanup e restore. Il cleanup è exactly-once e il secret è
azzerato. La recovery futura resta: R0 stop comandi; R1 preserva report; R2
release USB/ripristina ownership e fprintd; R3 nessun altro traffico nello stesso
run; R4 reboot/power-cycle soltanto dopo review umana; R5 verifica Windows; R6
stop live se enumera male o regredisce; R7 SWD/JTAG fuori dal workflow. D232 non
automatizza R4-R7.

## Backend reale offline e safety wall D233

D233 inserisce deliberatamente uno step tra il modello D232 e qualunque prova
hardware. `src/goodix5125_d233_backend.py` contiene un binding ABI minimo a
libusb-1.0, target esatto `27c6:5125`, interfaccia 0, bulk OUT `0x01`, bulk IN
`0x81`, frame da chunk massimi di 64 byte, revalidazione bus/address/port path,
claim/release/close exactly-once e nessun detach, clear-halt, reset o retry. Il
backend riusa serializer, allowlist, timeout, response validator e core
monotono D232: non esiste una seconda sequenza safety.

Il server TLS usa OpenSSL tramite `ssl.MemoryBIO`: TLS 1.2 soltanto,
`PSK-AES128-GCM-SHA256`/`0x00a8`, identity esatta `Client_identity`, niente
certificati, ticket, resumption, downgrade, seconda PSK o API application-data.
Il bridge accetta payload B0 frammentati, alimenta il BIO, separa più record in
uscita e li reincapsula singolarmente in B0. L'handshake è one-shot e il run si
ferma appena verificati versione e cipher; alert, timeout e Bad Record MAC sono
terminali.

Il boundary secret D232 viene riusato senza fallback. D233 aggiunge
`RuntimePskE4Binder`: deriva un expected validator dal buffer PSK effettivamente
caricato, confronta in constant time i 32 byte E4 e azzera il temporaneo; un
mismatch ferma dopo E4 e prima del primo A2. D189/D190 avevano già chiuso la
teoria, l'oracle OEM e la reference locale byte-exact; la sanitizzazione
successiva della repository pubblica aveva rimosso il source, non quella prova.
Il D233 originario non riuscì a recuperarlo e dichiarò correttamente il blocker.
La closure D233 ha poi recuperato source e KAT dal transcript locale D190,
reintegrato la reference minima e ripetuto i cinque vettori sul PE canonico con
zero mismatch. Non usa un MATCH storico come gate: ogni run deriva nuovamente il
validator dalla PSK caricata e dal PE hash-gated.

## Derivazione OEM e reference D190

La catena target è `secret[32] → producer key[32] → SP800-108 HMAC-SHA-256
out48 → envelope AES-256-GCM/HMAC[102] → SHA-256 → validator[32]`. Il FixedData
SP800-108 contiene le label canoniche e `BE32(384)`; `T1` e `T2` usano counter
BE32 1 e 2. D190 ha corretto due dettagli statici tramite le istruzioni OEM:
il buffer AES è azzerato a ogni iterazione e i quattro blocchi non sono
concatenati; `inner16` è il nonce GCM e la costante target è l'AAD.

La reference sotto `poc/goodix5125/tools/binding_reference/` non esegue la DLL.
Accetta soltanto SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`,
controlla PE, range e pattern univoco, legge i due seed strettamente necessari e
li azzera insieme ai material intermedi mutabili. Nel source e nei bundle non
sono presenti seed raw, producer key o out48. La policy resta
`LOCAL_VOLATILE_DERIVATION_HASH_ONLY`; il limite onesto è che Python non può
garantire la cancellazione di ogni copia immutabile interna alla libreria.

I validator attesi V0–V4 furono prodotti dall'oracle di istruzioni OEM sotto
QEMU prima di entrare nel self-test della reference. Nella closure sono input
storici indipendenti, non output rigenerati dalla funzione sotto test. Il PE
canonico locale riproduce tutti e cinque; hash errato, pattern ambiguo, KAT
alterato, PSK mutata o E4 errato falliscono chiusi. Ne seguono
`D190_REFERENCE_PROVENANCE_VALID=yes`, `D190_KAT_NONCIRCULAR=yes` e
`RUNTIME_PSK_E4_BINDING_PROVEN=yes`.

Il raw `0x90` non è copiato nel source o nel bundle. La capture locale
provenance-valid, SHA-256 `50071c0f...19c184b`, contiene a packet index 103
l'unico body di 224 byte con SHA-256 `e1988b11...d4d82`, finalizer `519a` e
tuple DAC coerenti. La procedura D234 documentata estrae da quella sola fonte,
verifica tutti i pin e materializza atomicamente un file root-owned `0600`,
regular e non symlink; D233 non legge lo store reale.

Il preflight production-shaped usa una facade iniettata: gate euid/SUDO_UID,
marker single-use atomico, processo/thread singolo, holder esterni, stato
fprintd, blocco segnali prima del trasporto, identità target e readiness del
report. Il restore riporta fprintd esattamente allo stato precedente e ripristina
la mask segnali. In D233 sono eseguite soltanto facade mock; nessun servizio o
sistema è mutato.

L'orchestratore candidate unisce preflight, loader protetti, verifica PE,
caricamento PSK, binder D190, backend USB/TLS e core OEM monotono attraverso sole
facade iniettate in D233. Il core D232 conserva lo schema sintetico, ma quel
report è catturato soltanto in memoria: il percorso candidate pubblica
`d233-production-candidate-run-report-v1`, con mode, seal, autorizzazione,
conteggi, restore, zeroizzazione, identità target e stato binding espliciti.
Non esiste alcun valore runtime che possa dichiarare `live_single_shot`.

L'ordine di recovery è causale e testato: stop del nuovo traffico, cleanup e
zeroizzazione exactly-once, checkpoint durable pre-restore, ripristino esatto di
fprintd e signal mask, poi report finale. Il checkpoint rende il risultato
recuperabile anche se il restore fallisce; il finale registra fedelmente
l'esito del restore. Nessun failure autorizza un secondo comando o recovery
invasiva automatica.

Il live è hard-disabled due volte: l'unico entrypoint spedito risponde soltanto
con capability zero e respinge flag, ambiente, config e backend alternativo;
ogni metodo della facade libusb reale chiama un sigillo source che solleva prima
di qualsiasi API USB. D234 richiederebbe una patch esplicita a quel sigillo,
review umana e autorizzazione separata. La suite riproducibile corrente comprende
46 metodi unittest, oltre ai check statici censiti separatamente, e copre
happy/failure path D232, boundary, USB mock, TLS loopback reale, B0, restore,
report, KAT D190 e tentativi di enablement. Nessun test enumera o apre il sensore.

## Esito D234: blocker dell'unseal

L'operatore ha concesso l'accettazione del rischio D234, ma la review dell'unseal
ha stabilito che una patch minima al solo sigillo non rende raggiungibile il live
revisionato. L'entrypoint D233 resta esclusivamente offline e
`run_production_candidate_offline()` richiede ancora facade, loader, factory e
publisher iniettati; inoltre emette lo schema D233 offline e dichiara il live non
autorizzato. Collegare in modo production i path root del PSK/config, l'identità
USB, libusb reale e i report D234 richiederebbe nuova logica e nuovi parametri,
oltre il solo unseal consentito.

La decisione è `D234_BLOCKED_BY_UNSEAL_SCOPE_EXPANSION`. Il gate è avvenuto
prima del preflight operativo e prima di qualunque `libusb_init`: live run, open
USB, E4, comandi e handshake TLS sono tutti zero. Non sono stati caricati secret
o config protetti, non è stato fermato `fprintd`, non è stato necessario alcun
cleanup/restore e non vi sono stati retry. Benché nessun run live sia iniziato,
la decisione terminale consuma l'autorizzazione D234 secondo la regola finale
dello step; resta vietato avviare un altro tentativo nell'ambito di D234.

Il prossimo step è subordinato a review umana separata di un vero entrypoint
live production, dei suoi path operativi e del relativo diff ampliato, seguita
da una nuova autorizzazione esplicita. Nessun secondo tentativo è autorizzato da
D234.

## D235: entrypoint production-candidate offline

D235 chiude il blocker software di D234 senza toccare il sensore. Il nuovo
`src/goodix5125_d235_entrypoint.py` è un thin composition layer: non contiene
serializer, state machine, KDF, TLS o B0 alternativi. Risolve dipendenze,
costruisce i componenti D232/D233 esistenti, mappa i terminali e delega la
pubblicazione atomica e il restore all'orchestratore già revisionato. Per rendere
univoco il mapping, D233 espone ora soltanto due metadati osservativi aggiuntivi,
fase tentata e dominio dell'errore, senza alterare ordine o wire protocol.

I path production sono assoluti e indipendenti da `HOME`: PSK
`/var/lib/goodix-5125-poc/transport-material.bin`, manifest protetto
`/var/lib/goodix-5125-poc/target-material-manifest.json`, config
`/var/lib/goodix-5125-poc/target-config-90.bin`, PE canonico nel corpus D230,
report sotto `/var/lib/goodix-5125-poc/d236-results/` e marker
`/var/lib/goodix-5125-poc/d236-live-single-use.marker`. I tre input protetti
restano regular, root-owned, mode `0600`, non symlink e senza fallback; la
directory report production deve essere preesistente, root-owned, mode `0700`.

Il target selector futuro legge soltanto sysfs dopo il gate EUID/SUDO_UID,
richiede un unico `27c6:5125`, ricava bus/address/port-path e accetta soltanto il
nodo character esatto `/dev/bus/usb/BBB/DDD`. Non apre il device. Tale identità
alimenta sia lo scan holder sia `ProductionUsbTransport`, che la rivalida dopo
l'unico open futuro.

La composizione preflight collega EUID root, `SUDO_UID`, marker O_EXCL,
topologia processo/thread, holder, stato e restore `fprintd`, signal mask e
readiness dei report. Gli input seguono l'ordine manifest/config verificati,
PE canonico regular non-symlink e hash-gated, PSK caricata una volta,
derivazione D190/E4 e la stessa istanza `SecretBuffer` consegnata al TLS. Il
percorso di recovery resta: stop traffico, cleanup/zeroizzazione, checkpoint
durable, restore fprintd/segnali, report finale; failure di checkpoint, restore
o finale sono testati fail-closed.

La suite D235 usa soltanto facade, sysfs e USB sintetici confinati in directory
temporanee. Copre happy path, EUID/operatore/holder, metadata e symlink, PE,
E4, open/claim, ogni fase protocollo, Bad Record MAC, publication/restore,
segnali e tentativi di enablement. La suite integrata D232–D235 esegue 53 test
senza sudo, enumerazione target, lettura degli store reali o cambi a `fprintd`.

L'unico entrypoint spedito chiama `_d235_source_seal()` prima di sysfs, input,
servizi o libusb; inoltre ogni metodo libusb reale conserva il sigillo D233.
Argomenti `--live`/`--force`, argv inatteso, ambiente, config, backend alterno,
import diretto e invocazione `-m` mantengono capability e USB open a zero. Non
esiste un runtime unseal. D236 richiederà una patch source piccola e separatamente
revisionata su sigilli e dichiarazioni compile-time, nuova accettazione umana e
nuova autorizzazione; D235 non concede nessuna di queste.

## Esito D236: blocker del preflight root

D236 ha ricevuto `D236_OPERATOR_RISK_ACCEPTANCE=granted`. La patch di unseal è
rimasta minima: due source seal e le dichiarazioni compile-time D236, schema/mode
production e normalizzazione dell'exit code sulla decisione terminale. Non ha
aggiunto protocollo, builder, backend, retry, recovery o enablement runtime. I
test offline mirati dell'unseal, dell'exit code e della composizione sono passati.

Il comando root previsto era
`sudo -n python3 analysis/D236/d236_preflight.py`. `sudo` ha restituito
`a password is required` prima di avviare lo script. Di conseguenza EUID root e
`SUDO_UID` non sono stati acquisiti e il preflight protetto non è iniziato. Non
sono stati letti PSK/config store reali, non è stato enumerato il target, non è
stato interrogato o fermato `fprintd`, non è cambiata la signal mask e non è
stata chiamata alcuna API libusb.

La decisione è `D236_BLOCKED_BY_PREFLIGHT`: live run, USB init/open/claim, E4,
comandi e TLS sono tutti zero; retry, D4, application data, famiglie di scrittura
persistente e recovery invasiva sono zero. Cleanup e restore non erano necessari.
Poiché il live non è iniziato, l'autorizzazione D236 non è stata consumata, ma
l'esito terminale chiude comunque lo step e non autorizza un altro tentativo.

Dopo il blocker sono stati ripristinati entrambi i source seal e le dichiarazioni
compile-time non autorizzate; resta soltanto la correzione innocua dell'exit code.
Un futuro tentativo richiede un nuovo step, una nuova review, una nuova
autorizzazione e una sessione root già autenticata secondo governance. Non è
consentito rilanciare D236.

## Esito D237: autenticazione sudo non predisposta

D237 ha ricevuto `D237_OPERATOR_RISK_ACCEPTANCE=granted`, ma il gate operativo
iniziale obbligatorio `sudo -n true` ha restituito `a password is required`.
La decisione terminale è quindi
`D237_BLOCKED_BY_SUDO_AUTH_NOT_PRIMED`, distinta da un blocker Goodix e dal
preflight D236: nessun altro comando root è stato eseguito.

Il source unseal e la relativa review non sono stati raggiunti. Non sono stati
avviati il preflight root, la selezione sysfs, libusb, l'apertura o il claim USB,
E4, alcun comando OEM o TLS. Tutti i contatori live e di recovery sono zero;
`fprintd` e la signal mask non sono stati toccati e nessun cleanup era necessario.
La regola udev persistente resta assente. Poiché il live non è iniziato,
l'autorizzazione D237 non è stata consumata; l'esito terminale chiude comunque
lo step e non autorizza un secondo tentativo.

Un eventuale nuovo step live richiede una nuova review e autorizzazione umana e,
prima che Codex inizi, una sessione sudo già autenticata dall'operatore fuori dal
workflow. Codex non deve richiedere, ricevere o gestire credenziali.

## Evidenza live D236 successiva e consolidamento D238

Gli artefatti live aggiunti dopo i report iniziali D236/D237 modificano lo stato
canonico senza trasformare D236 in un cold-start riuscito. Nel primo run reale
E4 è stato trasmesso e il dispositivo ha restituito il validator corretto:
`runtime_psk_e4_binding_status=match`. Sul target reale e nello stesso run,
quindi, il record root autentico, la KDF/reference OEM recuperata e il validator
derivato convergono con E4. Il run si è fermato sull'ACK E4 troppo stretto, con
un solo open e un solo comando.

Dopo la correzione limitata di E4, il secondo run ha raggiunto `E4_MATCH`, ha
trasmesso A2 #1 e si è fermato sul relativo ACK: un open, due comandi e nessun
TLS. Il terzo run, deliberatamente troncato dopo il primo frame IN di A2, ha
registrato in forma redatta `wrapper=A0`, `control=b0`, body length 2,
`ack_echo=a2`, `ack_status=07`: il target reale ha quindi restituito
`B0/A2/07`. La struttura diagnostica rendeva `0x82` irraggiungibile.

Tutti e tre gli esiti hanno mantenuto zero retry, zero famiglie di scrittura
persistente, zero TLS, zero D4/application data, cleanup exactly-once,
zeroizzazione del secret, ripristino di signal mask/fprintd dove necessario e
source resealed. La conclusione corretta è soltanto:

```text
E4 cryptographic binding live proven
A2 #1 transport ACK 0x07 live proven
full pre-D1 path beyond A2 #1 not yet live-executed
```

D238 chiude offline la frammentazione. `PHASE_RESPONSE_POLICIES` è l'unica
policy ACK/risposta del core: ammette soltanto `01`/`07`, conserva restrizioni
per fase, risposte tipizzate, ordine monotono e zero retry. La suite esercita
l'intero path sia con tutti gli ACK `01` sia con tutti gli ACK `07`, oltre a
status non provati, echo errato, frame estranei, ordine invertito, B0 malformato
e ACK+risposta coalesciati. Il report production conserva per ogni fase solo
control/lunghezze/status/classificazione di ordine e completion; esclude secret,
raw config90, payload arbitrari e dati biometrici.

Il config `0x90` resta esattamente 224 byte, SHA-256
`e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82`;
il manifest resta pin-nato a
`1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15`
e `gfusb.dll` a
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.
Il tentativo operatore D238 ha invocato direttamente
`python3 analysis/D236/d236_preflight.py` senza rendere esplicita la root del
repository nel path di import. È quindi terminato con
`ModuleNotFoundError: No module named 'src'` prima di entrare nel `main` del
preflight. L'incidente è classificato
`OPERATOR_KIT_PREFLIGHT_INVOCATION_FAILURE` e `NO_LIVE_USB_EXECUTION`: nessun
unseal, claim del marker, entrypoint production, init libusb, open USB o comando
Goodix è stato raggiunto. Il vecchio report D236 già presente non fu rigenerato
da quel tentativo e non ne costituisce evidenza.

## D239 e D241: dal primo B0 live alla transizione TLS

D239 ha sostituito il launcher operativo con
`operator_kit/d239-live-pre-d1-tls-once.sh`. Ogni entrypoint Python del launcher
riceve esplicitamente
`PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}"`; il preflight
espone inoltre un probe d'import offline che costruisce gli stessi componenti
production senza toccare sistema, USB o secret reali. La patch di unseal resta
byte-identica a D238: non sono cambiati protocollo, allowlist, policy ACK,
retry, recovery, command family o percorso del materiale protetto.

Il percorso `--offline-dry-run-pre-usb` è eseguibile senza root. Usa facade,
materiale protetto e secret sintetici, verifica il PE canonico e compone il
vero entrypoint/backend fino all'esatto seam `libusb.init`. In quel punto un
fence offline termina intenzionalmente il percorso prima di inizializzare
libusb. Il report permanente attesta:

```text
OPERATOR_KIT_DRY_RUN_PRE_USB=PASS
pre_usb_fence_count=1
libusb_init_count=0
usb_open_count=0
goodix_command_count=0
real_secret_read_count=0
live_marker_create_count=0
source_unseal_count=0
fprintd_stop_count=0
live_usb_execution=NOT_PERFORMED
```

Il dry-run non crea marker persistenti; il claim single-use e il caricamento del
secret sono sostituiti soltanto in memoria. La directory marker live D238 è
protetta e non ispezionabile da utente non privilegiato; ciò non altera la
diagnosi, perché il fallimento d'import avvenne testualmente prima del relativo
check. Nessun marker live è stato creato da D239.

La Definition of Done permanente dell'operator kit è:

1. `bash -n` del launcher;
2. probe d'import con contesto esplicito;
3. dry-run reale fino al fence pre-USB;
4. validazione di schema, hash e tutti i contatori negativi del report;
5. sorgenti ancora sealed e patch live applicabile soltanto in dry-run;
6. suite completa senza regressioni.

D239 soddisfece questi punti con 74 test passati. Dopo la correzione manuale
della directory report root, l'operatore eseguì il singolo ramo live autorizzato.
Sul dispositivo reale `27c6:5125`, firmware `GF_ST411SEC_APP_12509`, la sequenza
fu `E4/A2/82/A6/A2/70/80x4/90/D1`, con `command_count=12`, binding E4 `match` e
risposta D1 `direct_b0_tls`. Il B0 aveva body length redatta 52; non vi furono
ACK D1, D4, application data, persistent write o retry. Cleanup, zeroizzazione,
restore e reseal risultarono completati.

La mappa causale chiusa da D241 è:

```text
D1 send
→ ProductionReplayBackend.exchange legge e riassembla il primo B0
→ _validate_responses verifica wrapper e ClientHello
→ il frame resta pending dopo la validazione
→ tls_handshake verifica l'identità del SecretBuffer E4-validato
→ B0TlsBridge riceve quel frame esattamente una volta
→ OpenSSL emette ServerHello e ServerHelloDone
→ due B0 distinti sono sottoposti a bulk OUT
→ una successiva bulk IN non riceve dati e scade il budget bounded
```

D241 ammette per il record layer ClientHello TLS 1.2 le legacy version
`0x0301`, `0x0302` e `0x0303` e una lista offerta che contenga `0x00a8`
anche insieme a SCSV o altre suite. Il server OpenSSL resta ristretto a
`0x00a8`; handshake version TLS 1.2, wrapper/lunghezze e struttura ClientHello
restano obbligatori. Non rende permissivo `unexpected_data` e non ammette B0
in altre fasi. Il pending frame viene rimosso prima del feed, quindi non può
essere riletto o reiniettato.

La singola run live D241 è evidenza reale, non un dry-run:

```text
D241_LIVE_SINGLE_SHOT_COMPLETED=true
D241_CLIENT_HELLO_VERIFIED=true
D241_CLIENT_HELLO_RECORD_LENGTH=47
D241_SERVER_HELLO_SENT=true
D241_SERVER_HELLO_RECORD_LENGTH=81
D241_SERVER_HELLO_DONE_SENT=true
D241_SERVER_HELLO_DONE_RECORD_LENGTH=4
D241_CLIENT_KEY_EXCHANGE_OBSERVED=false
D241_TLS_CRYPTOGRAPHIC_HANDSHAKE_COMPLETED=false
D241_ERROR_CLASS=TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT
D241_D4_COUNT=0
D241_APPLICATION_DATA_COUNT=0
D241_PERSISTENT_WRITE_FAMILY_COUNT=0
D241_RETRY_COUNT=0
D241_SECRET_ZEROIZED=true
D241_FPRINTD_RESTORED=true
D241_SOURCE_RESEALED=true
D241_DO_NOT_RETRY=true
```

Nel JSON ereditato, `decision=D236_ABORTED_USB_TRANSPORT` e
`backend_failure_domain=usb_transport` sono label nominali legacy. Non hanno
precedenza sulla classe causale specifica: l'esito canonico D241 è
`TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT`. Il server flight fu emesso da
OpenSSL, avvolto in due B0 validi, sottoposto e completato integralmente secondo
le lunghezze richieste dal codice D241; una bulk IN post-flight fu realmente
tentata e non restituì dati. Questo sposta la vecchia analisi oltre un semplice
errore locale di submit, ma non rende equivalente il contratto USB all'OEM.

La semantica delle lunghezze è ora chiusa tracciando i produttori dei campi:
`response_body_length=52` in D239 è `len(parse_b0(frame))`, cioè record TLS
completo; `record_length=47` nella trace D241 è il payload dichiarato
dall'header TLS. Quindi `52 = 5 byte di header TLS + 47 byte di payload` e la
classificazione è
`D239_52_EQUALS_TLS_HEADER_PLUS_D241_47_CONFIRMED`. Non riguarda i quattro byte
del wrapper B0.

## D242/D243/D244/D245 live e confine D246

La sola capture primaria locale disponibile è quella storicamente classificata
D175; la capture D43 è assente e resta `NOT_ASSESSABLE`. D175 mostra la stessa
struttura TLS osservata in D241: ClientHello payload 47 con suite offerte
`00a8,00ff`, ServerHello payload 81 che seleziona `00a8`, e
ServerHelloDone payload 4. ServerHello e ServerHelloDone sono in due B0
distinti, un record TLS per B0; wrapper type, declared/actual length e checksum
sono coerenti. Non è una equivalenza byte-per-byte dei valori casuali o del
session ID, che restano intenzionalmente non pubblicati.

Il differenziale primario D242 aveva identificato due divergenze dal send path
Windows osservato:

1. il send callback Windows spezza ogni B0 in segmenti logici `<=64`, ma
   sottopone sempre 64 byte al bulk OUT, con tail nonzero catturata fuori dalla
   lunghezza B0 dichiarata; D241
   sottoponeva finali corti (ServerHello `64+26`, ServerHelloDone `13`), mentre
   D175 osserva completion da `64+64` e `64`;
2. la DLL chiama `Sleep(10)` dopo ciascun record TLS. D175 osserva circa
   21,933 ms fra completion ServerHello e primo OUT ServerHelloDone, mentre
   D241 drenava e inviava i due record back-to-back senza pacing.

Il timeout di 3000 ms non spiega la divergenza temporale osservata: nella
sessione OEM il ClientKeyExchange inizia circa 13,338 ms dopo ServerHelloDone,
molto dentro quel budget. D242 aveva quindi esteso staging da 64 byte con tail
zero-initialized e completion da 64 a ogni OUT A0/B0, oltre al pacing di 10 ms
dopo ogni record TLS. La successiva run live D242 ha però terminato al primo
E4: `command_count=1`, `usb_open_count=1`, nessun frame completo IN e timeout.
Il binding E4 non è stato raggiunto; `tls_handshake_count=0`,
`server_flight_usb_bulk_out_count=0` e `server_flight_pacing_count=0`. Retry,
D4, application data e write persistenti sono rimasti zero; cleanup exactly
once, secret zeroization, restore fprintd/segnali e source reseal sono riusciti.

La copia primaria locale accessibile è
`analysis/D242/D242_operator_live_stdout.json`, SHA-256
`1d9c2c736a2b8939855a184e350ea2ecaa914921536ae2a2d616130a166eb7e7`,
classificata `PRIMARY_LOCAL_EVIDENCE_VERIFIED`.

D243 ha poi eseguito live lo split A0/B0: A0 era tornato alla submission corta
D241, ma il singolo E4 ha prodotto di nuovo `command_count=1`, nessun frame
completo e timeout. Binding E4, server flight, pacing e TLS non sono stati
raggiunti; retry, D4, application data e write persistenti sono rimasti zero;
cleanup, zeroizzazione, restore e reseal sono riusciti. La copia locale
`analysis/D243/D243_operator_live_stdout.json`, SHA-256
`a82c43f4aba5c6f9dcfe072eee7b8b6ab0edc7f621961ea6a322dfe6ac45aa23`,
è anch'essa `PRIMARY_LOCAL_EVIDENCE_VERIFIED`. Non sono state lette directory
root-only né usati privilegi per acquisire queste evidenze.

La classificazione corrente è quindi:

```text
D243_A0_FIXED64_CAUSAL_STATUS=FALSIFIED_AS_SUFFICIENT_EXPLANATION_BY_D243_LIVE
D244_A0_FIXED64_DEVICE_EQUIVALENCE_STATUS=UNRESOLVED
D244_B0_FIXED64_DEVICE_EQUIVALENCE_STATUS=NOT_YET_LIVE_REACHED
```

La tail Windows A0 resta non nota e non è né provata né falsificata come
contratto device-side. È falsificata soltanto la sua sufficienza causale per il
timeout D242. Il server flight B0 fixed-64 con pacing 10 ms non è stato
raggiunto live né da D242 né da D243.

D243 applica lo split minimo nello stesso backend: A0/E4/pre-D1 torna alla
submission D241 live-proven (ultimo chunk corto, nessuna tail aggiunta,
completion pari al chunk), mentre B0/TLS conserva fixed-64 e pacing 10 ms.
Declared length, header/checksum, serializer, policy ACK/risposta, ordine e
timeout restano invariati; wrapper inattesi falliscono chiusi. Fixture offline
verificano l'E4 logico esatto con `len(submitted_E4_chunk) != 64`, l'intera
sequenza A0 pre-D1, ServerHello `64|64`, ServerHelloDone `64`, tail zero,
short completion fail-closed e due pause da 10 ms senza pacing A0.

`PROVEN_DIVERGENCE != PROVEN_DEVICE_ROOT_CAUSE`. D244 ha rieseguito il
differenziale sulle fonti reali archiviate D241/D242/D243. I path E4 D241 e D243
non sono byte-identici come sorgente, perché D243 aggiunge validazione wrapper e
telemetria, ma sono semanticamente equivalenti sul frame E4 canonico valido.
Il generic fixed-64 A0 D242 è completamente rimosso dal path D243. Le otto
differenze D241↔D243 raggiunte prima del timeout comprendono cinque differenze
host-side behavior-relevant intenzionali (namespace, gate e preflight), nessuna
wire/timing regression sul frame valido e zero candidati causali irrisolti.

Il logical E4 D241/D242/D243/D244 è in tutti i casi
`a00c00ace40900030002bb00000000fd`, lunghezza 16, SHA-256
`b6ada1adde00249e4e55f41bbf7c00443409c3752050520bc1a1874b0b63cf1a`.
`ProductionUsbTransport.command_count` aumenta soltanto dopo completion
full-length di tutti i chunk bulk OUT. Poiché E4 era l'unico comando e i due
report live hanno `command_count=1`, entrambi provano OUT completato; il timeout
è `IN_CONFIRMED_AFTER_OUT_COMPLETION`. Un timeout OUT sintetico lascia invece
`command_count=0` e non tenta bulk IN. Non è stata necessaria nuova
strumentazione runtime.

Il kit storico D242 usava esclusivamente
`/var/lib/goodix-5125-poc/d242-operator-invocation.marker`; i marker storici
D236/D238/D239/D241 sono benigni e non vengono cancellati. Prepara
idempotentemente `/var/lib/goodix-5125-poc/d242-results` root `0700`, verifica
hash e sealed baseline, applica l'unseal soltanto per la singola invocazione,
e reseala nel cleanup. Il closure gate esegue con peer USB/TLS sintetici
preflight, lifecycle directory/marker, patch apply/reverse, handoff exactly-once,
successo, timeout post-flight, osservabilità redatta e cleanup. Il suo stato è
`D242_EXECUTABLE_CLOSURE_GATE_PASS`. Quello stato `READY_NOT_EXECUTED` era vero
prima della run; la singola invocazione live D242 è ora consumata e non è il kit
corrente.

La closure finale di observability D242 elimina il terminale generico
`PREFLIGHT_FAILED`: se il preflight reale fallisce, lo stesso launcher legge il
report JSON appena prodotto e mostra immediatamente classe specifica, lista dei
failure, marker path e contatori zero per USB/comandi/secret/marker live. Report
mancante, invalido o renderer fallito hanno classi distinte e fail-closed. Il
path è verificato senza sudo con una fixture sintetica che termina prima di
unseal, USB, secret, fprintd e marker. Questa proprietà storica resta valida;
la run D242 successiva ha consumato il kit ed è terminata al primo E4. Anche il
kit D243 è ora consumato; anche la singola autorizzazione D244 descritta sotto
è consumata. Anche la singola invocazione D245 è ora consumata. La frase
storica che indicava D246 come riferimento soltanto offline descriveva lo stato
prima della run D246: D246 è poi stato eseguito live con successo ed è chiuso a
`STOP_AFTER_D4`. D250 è stato poi eseguito una volta fino alla AE strutturale ed
è consumato. D251 ha poi corretto validator/osservabilità ed è stato eseguito
una volta sulla baseline live approvata, chiudendo AF a `STOP_AFTER_AF`; anche
il suo marker è consumato. D252 non ha prodotto un nuovo kit live.

La provenance D241 è nuovamente byte-exact e read-only:
`d241_operator_dry_run.py` ha SHA-256
`0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f` e
`d241_preflight.py` ha SHA-256
`6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7`.
Sono le sole dipendenze D241 behavior-relevant della closure/preflight D242,
entrambe pin-nate e verificate prima dell'import dal launcher; l'adattamento
alla tail fixed-64 vive esclusivamente in D242. Il bundle D242 precedente
SHA-256 `a112fe2be21a48ff84072194e38cf07bfdb0817b42c44de43bc01e858a56df20`
è `SUPERSEDED_DO_NOT_USE_FOR_LIVE_AUTHORIZATION`: il differenziale tecnico e il
runtime fix restano utili, ma quella revisione fallì i gate di
provenance/closure/manuale e non è più il riferimento operativo.
Anche il bundle intermedio SHA-256
`df0f01b6fe78786eb22adf156f5d0c830d93a475e7a45f349635c5fb2843e60f`
è `SUPERSEDED_BY_FINAL_OPERATOR_OBSERVABILITY_CORRECTION_DO_NOT_USE_FOR_LIVE_AUTHORIZATION`;
il solo riferimento D242 finale è identificato dal sidecar `.zip.sha256`
esterno allo ZIP.

Gli hash sealed D242 verificati prima della modifica D243 erano
`c072db52...e90fcef` per `goodix5125_d233_backend.py` e
`6cd9fd37...908993` per `goodix5125_d235_entrypoint.py`: entrambi `MATCH`.
Gli offset `+1` e `-9` osservati applicando la patch D242 erano coordinate di
hunk non aggiornate rispetto alle linee correnti; il context match e il
round-trip byte-exact, insieme agli hash, escludono un baseline diverso. La
patch D243 è generata contro il baseline sealed D243 verificato e si applica e
si inverte senza offset.

Il launcher D243 usa il marker
`/var/lib/goodix-5125-poc/d243-operator-invocation.marker` e la directory
`/var/lib/goodix-5125-poc/d243-results`. Riusa il modello durevole già
revisionato: runtime abort, cleanup e zeroizzazione, checkpoint atomico
pre-restore, restore e report finale sono distinti. Una fixture timeout al
primo E4 verifica checkpoint con `report_publish_count=1` e segnali ancora
`pending`, quindi report finale con restore registrato e
`report_publish_count=2`. La closure offline era
`D243_EXECUTABLE_CLOSURE_GATE_PASS`; la successiva run live è quella terminata
al timeout E4 descritta sopra.

Il cleanup D241 non eseguì device reset, USB reset, A2 reset, re-enumeration
forzata, power-cycle, protocol close o Goodix state reset: eseguì soltanto stop
del nuovo traffico, release/close/exit USB, zeroizzazione, restore fprintd e
signal mask, publication e source reseal. Quindi
`D244_POST_D241_DEVICE_STATE_RESET_OBSERVED=false`. La cronologia journal
accessibile senza privilegi colloca D241 nel boot host
`704a277d1ed647ec877c90a83b2043d4` e D242/D243 nel boot successivo
`bc1ec5816f8044528be0e1feeafcc4c7`: l'ipotesi carryover è
`WEAKENED_BY_INTERVENING_BOOT`, non falsificata, perché un reboot host non prova
il power-cycle elettrico del sensore.

Il launcher D244 usa il marker
`/var/lib/goodix-5125-poc/d244-operator-invocation.marker` e la directory
`/var/lib/goodix-5125-poc/d244-results`. Conserva il wire D243 e richiede
all'operatore di confermare nell'argomento di autorizzazione un normale shutdown
completo seguito da accensione e avvio Fedora. Confronta read-only boot-id,
uptime e, se accessibile, `journalctl --list-boots` con la baseline D243. La run
è un fresh-state control valido solo con conferma operatore e boot-id diverso;
metadati insufficienti o stesso boot producono
`D244_FRESH_STATE_CONTROL_VALID=false` senza fingere una prova elettrica. La
closure sintetica verifica i casi boot-id presente/assente, uptime-only e
metadati insufficienti, insieme a E4, A0, B0, pacing, durability e safety.
La successiva singola run live è stata eseguita con fresh host boot documentato
e controllo fresh-state valido. E4 OUT ha completato, E4 IN è andato in
timeout, il binding non è stato raggiunto, TLS non è stato raggiunto, retry è
rimasto zero e cleanup, restore e reseal sono terminati. La classificazione
corretta è:

```text
D244_FRESH_STATE_HOST_CONTROL_RESULT=E4_TIMEOUT_PERSISTS
D244_FRESH_HOST_BOOT_SUFFICIENCY=FALSIFIED_AS_SUFFICIENT_RECOVERY_CONDITION
D244_SENSOR_ELECTRICAL_POWER_CYCLE_STATUS=NOT_PROVEN
```

Lo shutdown e la rimozione dell'alimentatore esterno non provano che il sensore
abbia perso alimentazione dal laptop con batteria interna. Quindi il carryover
della sola sessione host non basta a spiegare il fallimento, mentre lo stato
elettrico/protocollare del device resta irrisolto; non si dichiara falsificato
in assoluto il carryover di stato device post-D241.

Lo stato iniziale di `fprintd` non è una spiegazione sufficiente:

```text
D241: active   -> E4 superato
D242: active   -> E4 timeout
D243: active   -> E4 timeout
D244: inactive -> E4 timeout
D245_FPRINTD_INITIAL_STATE_CAUSAL_STATUS=NOT_SUFFICIENT_EXPLANATION
```

Il comportamento production resta invariato: se `fprintd` è inizialmente
active viene fermato e ripristinato; se è inactive non viene avviato.

Il corpus storico canonico conserva una run live D179 sul firmware 12509 con
questo boundary:

```text
A8 OUT      a00600a6a803000000ff
A8 ACK      a00600a6b00300a8014e        status 01
A8 response GF_ST411SEC_APP_12509
A8_COMPLETE
E4 OUT      a00c00ace40900030002bb00000000fd
E4 ACK      a00600a6b00300e40112        status 01
E4 response status 0, selector bb020003, validator 32 byte corretto
```

La policy di response A8 è determinata anche dai record storici D43 e D175:

```text
D43:  A8 -> B0/A8/01 -> A8/17 -> GF_ST411SEC_APP_12509\0
D175: A8 -> B0/A8/07 -> A8/17 -> GF_ST411SEC_APP_12509\0
```

D175 falsifica la policy erroneamente reintrodotta nella prima closure D245,
secondo cui ACK07 sarebbe stato terminale senza response. `0x01` e `0x07` sono
classi ACK empiricamente distinte; entrambe autorizzano esattamente una bounded
A8 response read. La semantica nominale interna di entrambe resta ignota. In
particolare, `0x07` è classificato
`UNKNOWN_STATUS_CLASS_EMPIRICALLY_COMPATIBLE_WITH_RESPONSE`, non failure,
busy, not-ready, terminal o response-not-authorized.

Gli artifact runtime primari D179 sono stati bonificati e non sono più nel
repository corrente: il record è
`CANONICAL_HISTORICAL_LIVE_RECORD_PRIMARY_RUNTIME_ARTIFACTS_PURGED`, non
`PRIMARY_LOCAL_EVIDENCE_VERIFIED`. D230 lo corrobora indipendentemente: la
capture corrente contiene due A8 request byte-exact, ACK `B0/A8/01` e response
tipizzata `GF_ST411SEC_APP_12509\0`; il census DLL identifica `GetEvkVersion` e
l'audit read-boundary classifica A8 come query-only di metadato fisso senza
side effect, distinta da flash/IAP, provisioning, OTP/config write e biometria.

La semantica ammessa resta limitata:

```text
D245_A8_SEMANTIC_CLASS=TARGET_LIVE_PROVEN_READ_ONLY_PRECONDITION_DISCRIMINATOR
D245_A8_INITIALIZER_STATUS=NOT_PROVEN
D245_A8_CAUSAL_ROLE=PRECONDITION_OBSERVED_BEFORE_SUCCESSFUL_E4_NOT_DEVICE_INITIALIZATION_PROVEN
```

A8 non è quindi chiamata initializer, reset o wake. D245 richiede wrapper e
checksum validi; ACK echo A8 status `01` oppure `07` autorizza esattamente una
response read. Per entrambi gli status, `A8_COMPLETE` richiede A0 control A8 e
body esatto `GF_ST411SEC_APP_12509\0`, senza frame trailing/unowned. Timeout,
response malformed, control errato, mismatch 12508/12510 o frame extra fermano
la run con E4 count zero e zero retry. Uno status diverso da `01|07` ferma la
run senza una seconda IN e sempre con E4 count zero.

Solo dopo A8 completo, E4 canonico e binding `match`, lo stesso backend continua
`A2→82→A6→A2→70→80x4→90→D1→TLS`. A0 conserva gli OUT corti D241; il server
flight B0 conserva submission fisiche fixed-64 con tail deterministica a zero,
pacing 10 ms per record e timeout 3000 ms. Nel kit D245 D4, application data,
reset e retry erano irraggiungibili. Il launcher usa il marker
`/var/lib/goodix-5125-poc/d245-operator-invocation.marker`, i risultati
`/var/lib/goodix-5125-poc/d245-results`, risolve la root dal proprio path/git e
verifica gli hash sealed dopo il rename. Gli hash correnti backend/entrypoint
coincidono con D243/D244; la closure applica e inverte la patch senza offset e
prova il dry-run production-shaped senza USB reale.

La run live D245 successiva è evidenza primaria locale verificata in
`analysis/D245/D245_operator_live_stdout.json`, SHA-256
`2992457855197b90dad3f7048bef85a6703079b95452dc07fa8e201a5c294e09`.
Il risultato è `pass`: ACK A8 `07`, response firmware 12509 esatta, binding E4
`match`, tutti i comandi pre-D1, D1 e handshake TLS completati. Il terminale è
`TLS_HANDSHAKE_OK`, con `command_count=13`, un solo open USB, un solo handshake,
zero D4, zero application data, zero retry e zero famiglie di scrittura
persistente. Cleanup, restore di fprintd/segnali e source seal risultano
completati; non è registrata una failure. Questo sostituisce lo stato storico
`READY_NOT_EXECUTED` di D245 senza attribuire ad A8 una semantica initializer.

La correzione governance v2.1 non auto-approva una baseline live. L'eventuale
commit SHA del live-critical set D245 deve essere designato dopo review
dall'Utente/AI PM; lo stato corrente è
`LIVE_BASELINE_APPROVAL_PENDING_USER_REVIEW`, che non blocca la closure offline.
I pin correnti di backend, entrypoint, core, patch unseal e preflight proteggono
ancora il percorso live/source-sealing; i pin di audit, contratto, runtime
matrix, closure runner, report storico e test sono governance/closure. D245 non
estende il pinning e non lo ridisegna opportunisticamente.

I launcher D239–D244 sono stati confrontati con i rispettivi bundle storici e
ripristinati byte-per-byte alla versione canonica, incluse le loro assunzioni
di location storiche. Solo `d245-live-tls-once.sh` resta robusto al rename della
root. I test correnti trattano l'eventuale stop per vecchia location come
comportamento storico atteso, senza mutare i launcher:

```text
D245_HISTORICAL_LAUNCHER_INTEGRITY=RESTORED
D245_HISTORICAL_LAUNCHER_MUTATION_COUNT=0
```

Nel kit D245 D4, application data, FDT, capture, enroll, reset/power-cycle e
recovery invasiva automatica erano irraggiungibili o vietati. D246 ha reso
raggiungibile soltanto D4 nella run separatamente approvata, tramite due patch
temporanee applicate in ordine D245→D246; tutte le azioni successive sono
rimaste irraggiungibili. D246 è stato eseguito live una sola volta e si è
fermato dopo l'ACK D4. D240 è obsoleto e non è stato eseguito.

Storicamente, fino a D246, il riferimento Rocky era soltanto corroborazione
esterna e nessuna implementazione GPL era stata copiata nel repository allora
BSD-2-Clause. Questa frase descrive le revisioni storiche, non la policy futura:
dopo D247 il riuso GPL è consentito in `core/`/`tools/` con provenance; resta
vietato usarlo come prova primaria target-specific o copiarlo nel dominio LGPL.

### D246: dal TLS Finished al solo D4

Il riesame metodologico che ha governato la run live completata era:

1. la run non ripeteva un esperimento precedente: D245 aveva già chiuso TLS e
   D246 aggiungeva esattamente un D4 e stop;
2. testava l'ipotesi che il D4 staticamente/capture-correlato come
   `VOLATILE_SESSION_INITIALIZATION` sia accettato live dal target con ACK
   esatto `d4/01`, senza richiedere alcuna azione successiva;
3. in caso di failure non erano autorizzati retry o patch cosmetiche; la run ha
   invece chiuso D4 al primo tentativo, quindi tale ramo non è stato percorso.

La catena causale stretta nella capture D230 è:

```text
frame 134  completion host TLS Finished
frame 136  H→D A0/D4, logical 10, physical OUT 64, zero tail
           a00600a6d403000000d3
frame 138  D→H B0 ACK, body d4 01
           a00600a6b00300d40122
frame 140  successivo host A0/AF — fuori scope e irraggiungibile in D246
```

Il submit D4 segue di circa 53,154 ms la completion host Finished; l'ACK segue
D4 di circa 1,043 ms. Il callsite primario DLL a `0x18001f16b` è nello stesso
percorso handshake/init, dopo stato handshake `0x10` e `Sleep(20)`. Chiama il
builder D4 `0x18001c46c`, che serializza major `0xd`, subtype `2`, due byte body
zero e usa il generic A0 con budget caller 200 ms. D4 è quindi plaintext A0
post-handshake, non un record TLS application data. La capture mostra un solo
ACK `d4/01` e nessuna response D4 tipizzata; D246 non autorizza una seconda IN
né interpreta altri status.

Sul firmware APP12509 il dispatcher a `0x08035e3c` instrada la famiglia D al
receiver presente `0x080396b0`. Il branch subtype 2 a `0x0803987c` azzera solo
SRAM `0x20000790`; la coda comune legge un bit volatile tramite `0x0802e144` e
setta o pulisce un bit in SRAM a `0x20006d3c+5`. `0x0802e144` effettua soltanto
un read/test di RAM. Nel percorso esatto non compaiono chiamate o target
flash/IAP, OTP, configurazione persistente, provisioning, enrollment o factory
data. La classificazione ristretta è dunque:

```text
D246_D4_SEMANTIC_CLASS=VOLATILE_SESSION_INITIALIZATION
D246_HOST_SIDE_NO_PERSISTENT_WRITE_OBSERVED=true
D246_DEVICE_SIDE_PERSISTENCE_EXCLUDED_WITH_SUFFICIENT_EVIDENCE=true
D246_SCOPE=EXACT_APP12509_D4_RECEIVER_PATH_ONLY
```

Questo non prova l'assenza assoluta di persistenza per comandi successivi,
receiver resident mancanti o varianti firmware. Prova quanto basta per il solo
D4 esatto: precondizioni TLS completo, identità stabile e buffer RX vuoto;
una pausa host da 20 ms; un OUT fisico fixed-64 zero-tail; un ACK bounded entro
200 ms; accettazione solo del body `d4 01`; quindi `STOP_AFTER_D4`. Timeout,
completion ambigua, ACK diverso o frame trailing terminano senza retry,
rilasciano le risorse e resealano. AF e ogni azione ulteriore sono non
raggiungibili.

La successiva run live D246 è evidenza primaria locale in
`analysis/D246/D246_operator_live_stdout.json`, SHA-256
`055ace08832e2297d1b3687523fd41a410ed80b215207d63c352ea1cee2493e0`.
Il risultato autoritativo è determinato dai contatori e dai campi D246
specifici della run:

```text
D246 live execution                 COMPLETED
execution_mode                      live_single_shot
usb_open_count                      1
TLS cryptographic handshake         COMPLETED (count 1)
D4 attempt/send count               1/1
D4 ACK                              status 0x01
D4 completed                        true
D4 request logical/physical length  10/64
D4 response body length             0
D4 completion                       single_frame_usb_completion
retry/application data count        0/0
persistent write family count       0
terminal boundary                   STOP_AFTER_D4
cleanup                             completed (count 1)
secret/source/fprintd               zeroized/sealed/restored
```

Il raw evidence resta byte-identico. I campi
`LIVE_BASELINE_APPROVAL=PENDING_USER_REVIEW`,
`decision=D236_LIVE_TLS_HANDSHAKE_SUCCESS` e
`reached_phase=TLS_HANDSHAKE_OK` sono metadata legacy del renderer: sono
incoerenti con la closure finale D246 ma non invalidano la run. `result=pass`,
`execution_mode=live_single_shot`, i contatori D4 e l'osservazione protocollo
D4 sono i campi autoritativi. La run produce nuova evidenza tecnica live che il
target accetta l'exchange previsto; non estende la prova semantica oltre
`EXACT_APP12509_D4_RECEIVER_PATH_ONLY`.

Il contratto exactly-once distingue ora `d4_attempt_count`, latched a uno
immediatamente prima della chiamata che può consegnare il frame al transport,
da `d4_send_count`, che indica soltanto il ritorno full-length confermato. La
guardia d'ingresso vieta D4 quando attempt è già diverso da zero. Una
completion ambigua conserva quindi `attempt=1`, `send=0`, failure
`ambiguous_usb_completion`, zero retry; una re-entry intenzionale termina prima
del transport con secondo write zero, senza inferire se il device abbia
ricevuto il frame.

Il delta vive in `analysis/D246/D246_d4_continuation.patch` ed è applicato
soltanto dopo la patch D245. Nella closure offline le patch vivono in una copia
temporanea; nella run approvata il launcher ha creato prima backup byte-exact,
applicato D245→D246 alle due sorgenti canoniche per una sola invocazione
dell'entrypoint e garantito restore/reseal tramite trap anche su uscita anomala.
Le sorgenti D233/D235 a riposo restano source-sealed. La matrice sintetica prova
regressione D245 fino a TLS, happy path D4 exactly-once, timeout D4 senza retry,
ACK inatteso e assenza di qualunque OUT dopo D4. L'estensione di safety prova
anche disconnect e re-enumeration terminali senza reopen/reclaim, secondo D4
irraggiungibile, completion ambigua con re-entry vietata e nessun reset/recovery
automatico. I fixture preflight provano che il marker D245 è benigno, il marker
D246 blocca e path/renderer sono soltanto D246. Un repository Git temporaneo
prova che la modifica di `binding_reference/runtime.py` rende la baseline
`STALE`. Closure, hash pre/post, 135 regressioni e contatori reali provano zero
open USB reale, zero handshake TLS reale, zero D4 reale e zero famiglie di
scrittura persistente.

`operator_kit/d246-live-d4-once.sh` accetta `--offline-dry-run` oppure il solo
argomento live esatto `--i-authorize-one-d246-d4-live-attempt`. Il ramo live
fallisce chiuso se non coesistono EUID root, `SUDO_UID` numerico non-root,
marker D246 assente, preflight PASS, source seal attivo e una baseline approvata.
La governance v2.1 usa come baseline primaria il commit SHA completo designato
esternamente in `D246_APPROVED_LIVE_BASELINE_SHA` dopo review AI PM e confronta
direttamente con i blob Git l'intero set live-critical transitivo: launcher,
patch D245/D246, preflight/renderer/helper D246, D232/D233/D235, il PE canonico
hash-gated e i quattro moduli package/runtime/crypto/parser del binding PSK↔E4.
SHA assente/non valido o
contenuto stale bloccano la run. Manuale, report, status e test non sono oggetto
di pinning generalizzato. Marker, directory risultati e report preflight sono
esclusivamente D246.

Prima della correzione, un tentativo operatore si è fermato nel preflight D245
ereditato sul marker storico consumato. Questo prova soltanto un difetto
host-side: `D246 live attempt=NOT_STARTED`, USB/comandi/secret read/mutazioni
fprintd/D4 attempt tutti zero e stato device invariato. Il marker D245 resta
storico, benigno e intatto. La precedente baseline candidata
`ff4cc3b748dafbce681e6fa38a44936eca794d12` è
`SUPERSEDED_NOT_APPROVED_FOR_LIVE`.

Lo stato finale è
`D246_D4_LIVE_EXECUTION_COMPLETED_STOP_AFTER_D4`, con
`ADVANCEMENT=REAL_EXECUTION_COMPLETED` ed `EXECUTABLE_CLOSURE=PASS`. La run ha
prodotto anche nuova evidenza tecnica live sul D4, mentre la categoria primaria
di avanzamento resta l'esecuzione reale completata. L'autorizzazione single-shot
è consumata: D246 non autorizza un secondo D4, retry o il comando AF.

## D249: core GPL offline AF → FDT → first image

D249 usa la baseline Rocky immutabile
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`. Le sole parti adattate nel dominio
GPL provengono da `src/goodix_cmd.c`, `src/goodix_frame.c` e
`src/goodix_capture.c`, con SPDX GPL-2.0-or-later e attribution registrati nel
ledger. Rocky resta fonte implementativa e corroborativa, non prova
APP12509. Lifecycle USB, retry/reconnect, PSK/MCU write, persistenza baseline,
firmware/IAP/ClearApp e le famiglie E0/A4/F0/F4 non sono importati né
raggiungibili.

La prima revisione D249 conteneva un decoder immagine non equivalente alla
closure locale. La correzione lo ha rimosso: `core/post_d4.py` delega ora
esattamente a `src/goodix5125_cleanroom.py`. Restano quindi canonici record da
7684 byte, 7680 packed, gruppi 6-byte/4-sample, 5120 sample, trailer CRC nel
reale ordine `crc>>8, crc, crc>>24, crc>>16` e transpose wire-index → raster
80×64. I test costruiscono il record con il codec locale, confrontano tutti i
pixel dei due output, verificano un KAT non banale e corruzione CRC; non usano
un encoder duplicato D249.

La capture locale osserva AF e comandi FDT plaintext nella sessione post-TLS;
la DLL conferma serializer AF, timestamp, risposta AE da 16 byte e bit di stato.
Il modello offline D249 storico sceglieva separatamente due percorsi: AF senza
POV → invio asincrono FDT down 32 → IRQ 2 → invio asincrono SetMode Image 20 → immagine;
AF con POV valido → invio asincrono D2 → immagine cached. D252 ha poi stabilito
che questo tratto, mutuato da Rocky, non è wire-exact per l'unica occorrenza
target con IRQ 2: il successivo OUT è `0x22 [01 00]`, mentre `0x20` compare
separatamente nei path di immagine base/no-finger. D253 ha quindi corretto
organicamente il core corrente: `build_finger_image()` serializza `0x22`, la
allowlist e la policy ACK includono echo `22`, e la state machine usa quel
comando dopo IRQ2 con latch di tentativo pre-submit. `build_set_image()` resta
il builder `0x20` separato. D249 resta la provenance storica della closure
sintetica; la correzione current-path D253 non prova che il percorso sia
live-safe.
Gli ACK osservati
localmente dopo 32, 20 e 22 vengono validati se presenti, ma non sono una
precondizione causale obbligatoria; per D2 la presenza target resta non nota. Entrambi validano framing, checksum, record, CRC,
unpack/transpose e terminano esplicitamente in `FIRST_IMAGE_RECEIVED`. Questa è
closure eseguibile delle fixture sintetiche, non prova che il sequencing sia il
minimo causale o live-safe sul 12509.

La matrice ACK D249 classifica AF come `FORBIDDEN`: le occorrenze locali hanno
risposta AE diretta senza ACK. Per 32, 20, 36 e 34 la capture osserva un ACK
successivo, ma non prova che sia necessario prima dell'evento/payload push;
questi comandi sono quindi `OPTIONAL_IF_PRESENT`. D2 non è osservato nella
capture target; Rocky lo invia asincrono e consuma eventuali ACK nel receive
loop, perciò il parser D249 usa ancora `OPTIONAL_IF_PRESENT` come policy di
accettazione senza trasformarla in evidenza target. Zero o un ACK esatto sono
accettati; ACK errato o duplicato fallisce chiuso.

La policy checksum è strict: `parse_payload()` calcola sempre il checksum. Il
valore 0x88 è accettato soltanto quando coincide matematicamente con il checksum
del payload specifico; non è un bypass. Il NOP locale osservato con marker
no-check è fuori dall'allowlist D249. Test distinti rifiutano un 0x88 errato e
accettano un checksum genuino che vale 0x88.

La closure avversariale copre ACK inattesi/duplicati, eventi fuori ordine,
immagine anticipata, control e framing errati, EOF parziale, lunghezze immagine,
CRC e transizioni duplicate/regressive. Non esistono backend USB/TLS concreti,
secret, persistenza, retry o loop non bounded. D251 ha raggiunto live AF/AE e
si è fermato prima di FDT o dito. D252 ha provato la derivazione dinamica della
tabella FDT ma non la sua freschezza current-path né un restore post-arming;
D253 ha delimitato il setter host del seed senza trovarne la sorgente ultima e
ha confermato l'assenza di restore deterministico. D255/D256 hanno poi provato
la re-entry/re-arm e il terminal-stop host/bus senza restore USB esplicito;
D257 integra tali fatti nel lifecycle offline e riclassifica disarm/lifetime
interni come unknown epistemici non bloccanti. Il live resta non autorizzato
per la distinta freschezza/provenance current-attempt del seed.

## D250: canonicalizzazione Rocky, closure exactly-one AF e operator path

Lo snapshot operativo canonico è `Rockytkg/`, con provenance in
`Rockytkg/PROVENANCE.md`; struttura e licenze sono quelle descritte nella
sezione fonti. D250 non importa nuovo codice Rocky: riusa il serializer e il
validator GPL già registrati da D249 in `core/post_d4.py`.

L'audit primario riproducibile è
`analysis/D250/D250_af_capture_audit.json`. Nella sola sequenza locale
post-D4 esatta, il frame 136 è D4 logico 10 / OUT 64 zero-tail, il frame 138 è
l'ACK `d4/01`, il frame 140 è AF logico 13 / submission 64 e il frame 142 è AE
logico e fisico 24. La numerazione è umana 1-based; il JSON conserva gli indici
zero-based 135/137/139/141. Non esiste un frame IN non vuoto tra AF e AE. Tutte
le cinque occorrenze AF della capture hanno risposta AE diretta e submission
64; la tail AF fuori dalla lunghezza A0 dichiarata è sempre la stessa sequenza
opaca di 51 byte, con sei byte nonzero agli offset tail 27–32. Non è trattata
come payload protocollo né replayata. Il candidate invia 13 byte logici in un
buffer fisico 64 zero-initialized. D250 ha provato live l'accettazione
device-side di questa zero-tail fino a una AE strutturalmente valida; resta
`NOT_PROVEN` soltanto l'equivalenza byte-per-byte/universale con la tail OEM.
Presenza dell'ACK AF, lunghezza tail, conteggio e offset dei byte
nonzero e identità delle cinque tail sono ora derivati programmaticamente dalla
capture anziché descritti da costanti; il JSON resta redatto e l'audit fallisce
se questo profilo canonico cambia.

La DLL locale classifica `GetMcuState` come read tipizzata: control wire AF
(`AE` logico con `more=1`), body `55,ts16le,00,00`, ACK timeout zero, data
timeout 500 ms ed evento/risposta AE. Il call path OEM mostra anche `Sleep(20)`
prima della query; la capture osserva 58,365 ms da ACK D4 ad AF OUT. Il
candidate usa 20 ms host-side, timeout complessivo AF 500 ms e massimo una sola
lettura di frame. La AE strutturalmente valida deve essere A0, control `0xAE`,
checksum valido e body esattamente 16 byte. Le cinque capture OEM osservavano
byte 0 uguale a `1`, ma l'audit D251 non trova una semantica positiva né un
confronto OEM: chiamarlo “versione” e imporre `== 1` era una promozione di
un'osservazione a invariante. Byte 0 è quindi opaco. Byte 1: bit0 POV-valid,
bit1 TLS-connected e bit3 locked sono gli usi semantici verificati; ogni altro
bit è preservato come ignoto e non governa azioni ulteriori. La telemetria
D251 espone `af_state_byte0`, `af_state_flags`, `af_unknown_flag_bits`,
`af_pov_valid`, `af_tls_connected` e `af_locked`.

`ExactlyOneAfMachine` e la patch continuation mettono il latch attempt prima
della submission. Completion corta/ambigua conserva `attempt=1`, non marca
`send=1` e impedisce re-entry. Timeout, ACK AF, AE corta/lunga, control o
checksum errato, risposta duplicata coalesced e frame trailing falliscono
chiusi; un frame separato successivo resta unowned e non viene consumato perché
il budget autorizza una sola IN. Dopo AE valida il terminale è sempre
`STOP_AFTER_AF`; non esiste transizione verso FDT `32`, SetMode `20`, cached
`D2`, finger o image. Cleanup/release/secret zeroization/restore/reseal restano
quelli della catena D246 e sono verificati nel tree temporaneo.
Il modello core intercetta `Exception`, non `KeyboardInterrupt`, `SystemExit`
o le altre eccezioni di controllo processo.

La classificazione safety è corpus-bounded: AF è una query di stato fissa,
osservata nel workflow OEM e distinta dalle famiglie di write/provisioning/
firmware; non serializza address, blob o selector persistenti. Il receiver
resident APP12509 resta non disponibile, quindi non si afferma una proprietà
universale di ogni AF possibile. Rocky e Issue #1 corroborano serializer e
semantica, ma non sono la prova target-specific.

La run D250, eseguita una volta sulla baseline approvata
`44b22f21178c0083d4628ca9bbdb4ee895df40bd`, ha completato TLS e D4, inviato
AF una volta e ricevuto una A0/AE strutturalmente valida. È terminata
fail-closed nel controllo `byte0 == 1`; questo safety behavior era corretto
rispetto al contratto allora approvato, mentre il modello semantico era
sovravincolato e l'osservabilità insufficiente perché byte 0 e response count
non venivano persistiti prima del controllo. Il valore live non è recuperabile
dagli artefatti leggibili; i due report `/var/lib/.../d250-results/` non sono
leggibili senza privilegi e non è stato usato `sudo`.

```text
D250_AF_LIVE_BOUNDARY=CONSUMED
D250_CANDIDATE=EXECUTED_ONCE_TLS->D4_ONCE->ACK_D4_01->AF_ONCE->STRUCTURAL_AE->VALIDATOR_ABORT
D250_MAX_AF_IN_FRAME_COUNT=1
D250_AF_ACK_POLICY=FORBIDDEN
D250_RETRY_COUNT=0
D250_PERSISTENT_WRITE_FAMILY_COUNT=0
D250_USB_OPEN_COUNT=1
D250_AF_ZERO_TAIL_DEVICE_ACCEPTANCE=LIVE_PROVEN
D250_AF_ZERO_TAIL_STRUCTURAL_AE_RESPONSE=LIVE_PROVEN
D250_AF_ZERO_TAIL_OEM_BYTEWISE_EQUIVALENCE=NOT_PROVEN
D250_AF_LIVE_STATE_BYTE0_VALUE=LOST_BY_OBSERVABILITY_GAP
D250_AF_RESPONSE_COUNTER_DIAGNOSIS=INCREMENTED_TOO_LATE_AFTER_SEMANTIC_CHECK
D250_LIVE_EXECUTION=PERFORMED_ONCE_MARKER_CONSUMED
```

Il marker D250 non deve essere cancellato o riutilizzato. D251 ha usato
namespace e marker propri; anche il marker D251 è ora storico e consumato.

## D251: post-mortem semantica AF e candidate one-shot corretto

L'audit primario di `gfusb.dll` copre `GetMcuState` e i tre call site diretti
nel disassembly locale. La funzione acquisisce 16 byte; il codice OEM usa
byte 1 bit0 nel percorso POV, byte 1 bit1 per conferma TLS e byte 1 bit3 per lo
stato locked. Un call site usa solo l'esito della query. Nessun call site
confronta byte 0 con `1` né lo usa per una decisione. Le cinque capture OEM
restano una semplice osservazione `byte0=1`. Rocky legge/logga byte 0 ma governa
POV/TLS/locked con byte 1; è solo corroborazione.

Il parser canonico restituisce ora ogni A0/AE strutturalmente valida con body
da 16 byte e conserva byte 0 come `McuState.byte0`. Il continuation D251
incrementa `af_response_count` subito dopo questa validazione strutturale,
prima di classificare campi inusuali, e persiste byte0/flags/bit semantici. Il
report distingue `no_response`, `malformed_response`, `unexpected_ack`,
`valid_ae_with_unusual_state_fields` e `valid_ae_accepted`. Un byte0 diverso da
1 è osservabile ma non causa failure; ogni esito resta terminale. Serializer,
tail zero, pacing 20 ms, timeout 500 ms, endpoint e massimo una IN restano
invariati rispetto a D250.

Riesame metodologico pre-live D251:

1. cambia il solo validator/observability, eliminando l'invariante non provata;
2. testa l'ipotesi nuova che la AE D250 fosse protocollo valido con byte0 opaco;
3. se il D251 autorizzato fosse fallito ancora allo stesso punto, non si sarebbe
   ripetuto il probe: la telemetria completa avrebbe riportato all'audit del
   receiver/protocollo prima di qualsiasi nuovo live.

La run autorizzata sulla baseline
`f07352ce085651568a9aedbf04b097df91d7c0bb` ha validato esattamente l'ipotesi:
una sola AE strutturale con `byte0=0` è stata accettata e classificata senza
promuoverla a versione. `flags=0x02` significa TLS connected vero, POV-valid e
locked falsi, con bit ignoti zero. La run ha chiuso AF e si è arrestata prima
di qualsiasi FDT, D2, dito o immagine.

```text
D251_LIVE_RESULT=PASS
D251_AF_BOUNDARY=LIVE_PROVEN
D251_AF_ZERO_TAIL_DEVICE_ACCEPTANCE=LIVE_PROVEN
D251_AF_STRUCTURAL_AE=LIVE_PROVEN
D251_AF_STATE_BYTE0=0
D251_AF_STATE_BYTE0_SEMANTIC_CLASS=OPAQUE
D251_AF_STATE_FLAGS=0x02
D251_AF_POV_VALID=false
D251_AF_TLS_CONNECTED=true
D251_AF_LOCKED=false
D251_AF_UNKNOWN_FLAG_BITS=0
D251_RETRY_COUNT=0
D251_PERSISTENT_WRITE_FAMILY_COUNT=0
D251_APPLICATION_DATA_COUNT=0
D251_CLEANUP_RESEAL_RESTORE=PASS
D251_MARKER=CONSUMED
```

## D252: audit fresh-FDT, tabella dinamica e restore mancante

L'audit riproducibile `analysis/D252/d252_fdt_capture_audit.py` verifica la
capture target hash-gated. Le tre richieste `0x36` hanno data
`09 01 || table12`, frame logico 22 e submission fisica 64; la tail esterna al
frame conserva sei byte OEM opachi nonzero agli offset 40–45. Ognuna riceve
ACK echo `36`/status `01` e un evento IRQ `0x0100`, touch flag zero. La routine
DLL `0x180029210` valida i sei raw word e calcola ciascun word di tabella come
`((v >> 1) << 8) | 0x80`: nella capture le prime due tabelle apprese diventano
esattamente l'input del `0x36` successivo, e la terza diventa
`80ac80bd80a380b180a680b2`.

Le tre richieste `0x32` hanno data
`08 01 || 80ac80bd80a380b180a680b2 || ts16le`, frame logico 24, submission 64
con tail zero e ACK echo `32`/status `01`. Il timestamp DLL è
`wSecond*1000+wMilliseconds` troncato a 16 bit. La tabella è riusata per circa
117,45 secondi nella stessa sessione; la validità cross-session, termica o per
il cold-start D251 non è provata. Il primo seed `0x36` non è un literal in DLL,
APP o config90 e la sua provenienza/freschezza resta aperta, sebbene il DLL
abbia un possibile percorso cache host `goodix.dat` legato alla OTP.

Dopo l'unico IRQ 2 target, il successivo OUT è wire `0x22 [01 00]`, non il
`0x20` modellato in D249/Rocky. `0x34` arma invece finger-up. La routine OEM
`gfOnCancel` cancella la richiesta WDF host senza inviare direttamente un
comando A0; A2 reset-sensor e `0x70` idle non sono osservati come cleanup dopo
FDT. La capture termina dopo il terzo `0x32` senza un restore esplicito. Il
receiver APP family-3 risiede inoltre nel tratto mancante: non si osservano
write persistenti, ma non è possibile promuovere l'inferenza di modalità
volatile a prova assoluta di nonmutazione NVM.

```text
FDT_DOWN_TABLE_SOURCE=DYNAMIC_IRQ_0x100_TRANSFORM_AFTER_0x36; FIRST_0x36_SEED_PROVENANCE_UNRESOLVED
FDT_DOWN_TABLE_LIFETIME=OBSERVED_REUSED_WITHIN_ONE_CAPTURE_SESSION; CROSS_SESSION_AND_ENVIRONMENTAL_VALIDITY_NOT_PROVEN
FDT_DOWN_TABLE_TARGET_VALIDITY=TARGET_CAPTURE_SESSION_ONLY; NOT_VALIDATED_FOR_CURRENT_D251_COLD_START
FDT_DOWN_TABLE_LIVE_READY=false
FDT32_SEMANTIC_CLASS=FINGER_DOWN_DETECTION_ARMING_SENSOR_MODE
FDT32_PERSISTENCE_CLASS=NO_PERSISTENT_WRITE_PATH_OBSERVED; DEVICE_NVM_NONMUTATION_NOT_ABSOLUTELY_PROVEN
FDT36_REQUIRED_BEFORE_FDT32=YES_FOR_CURRENT_PATH_TO_OBTAIN_FRESH_TARGET_BASELINE; SAFE_LIVE_0x36_PRECONDITIONS_NOT_CLOSED
FDT36_SEMANTIC_CLASS=MANUAL_NO_FINGER_FDT_BASELINE_SAMPLING_WITH_IRQ_0x100
FDT36_PERSISTENCE_CLASS=DYNAMIC_SENSOR_BASELINE_AND_HOST_LEARNED_TABLE; NO_DEVICE_PERSISTENT_WRITE_PATH_OBSERVED; DEVICE_NVM_NONMUTATION_NOT_ABSOLUTELY_PROVEN
FDT_CANCEL_COMMAND=NOT_FOUND_OR_PROVEN
FDT_CANCEL_PRIMARY_EVIDENCE=NONE; gfOnCancel_IS_HOST_ONLY; 0x34_ARMS_FINGER_UP
FDT_RESTORE_STATE=NOT_PROVEN
FDT_RESTORE_LIVE_PROVEN_PREDECESSOR=NONE
FDT_ARM_AND_STOP_SAFE=false
NEXT_MINIMUM_LIVE_BOUNDARY=NONE
D252_LIVE_BOUNDARY=BLOCKED
D252_LIVE_EXECUTION=NOT_PERFORMED
```

Il prossimo avanzamento utile richiede nuova evidenza primaria sul seed del
primo `0x36`, sul restore device-side post-FDT e sulla distinzione `0x22/0x20`;
non una ripetizione live del percorso già noto.

## D253: dataflow seed, lifecycle post-FDT e correzione `0x22`

L'audit riproducibile `analysis/D253/d253_offline_audit.py` censisce tutte le
occorrenze prima di applicare gli invarianti attesi. Conferma esattamente tre
`0x36`, tutti logici 22 / fisici 64, con un'unica tail profile e nessuna
zero-tail target. I soli byte nonzero fuori frame sono sempre
`cb f2 e2 be fb 7f` agli offset fisici 40–45. Lo stesso residuo compare nei
tre comandi immagine `0x20`/`0x22`, mentre il buffer locale SetMode è azzerato
esplicitamente: la classificazione più forte è staging/transport residue fuori
dalla lunghezza A0, non payload. Rocky offre solo corroborazione zero-init;
l'equivalenza zero-tail `0x36` sul target non è provata e il contratto fisico
non è live-ready.

Il dataflow della globale FDT-down `0x180580818` separa due fasi. Il callback
registrato in `context+0x13d68` punta a `0x180028480` e copia 12 byte forniti
dal chiamante; è l'unico initializer pre-manual delimitato. Dopo ogni IRQ100,
`0x180029210` valida i raw word e sostituisce la globale con la trasformazione
già provata. Il chiamante del callback, la costruzione dei suoi 12 byte e il
criterio esterno che produce esattamente tre sample non sono presenti in
`gfusb.dll`. Non sono provati un default type-12, una derivazione da sei
scalari, una validazione pre-copy o la necessità fisica di un seed nonzero.

Nel corpus non è presente un file OEM `goodix.dat`. Il path DLL osservato
legge una quantità pari alla OTP, confronta quel prefisso con la OTP live e
sceglie i calibration bytes; non raggiunge direttamente la globale FDT.
Il layout Rocky con OTP/FDT/image/CRC resta fonte implementativa
corroborativa, non prova target del formato o della freschezza. Host persistence
Linux non è quindi autorizzata né classificabile come riuso sicuro.

L'audit differenziale target trova `0x20` ai pacchetti zero-based 167 e 238,
in contesti baseline/no-finger, e `0x22` al 227 immediatamente dopo IRQ2.
Tutti hanno data `01 00`, lunghezza logica 10/fisica 64, ACK con echo uguale al
control e un frame immagine B0/TLS da 7726 byte successivo. Il builder DLL
prova la decomposizione: `0x20 = cmd0 2, cmd1 0, more 0`; `0x22 = cmd0 2,
cmd1 1, more 0`. Il core corrente usa perciò `0x22` post-IRQ2; la semantica
non viene estesa oltre “variante immagine post-finger-down”.

Il lifecycle positivo catturato è
`0x32→IRQ2→0x22→image→0x34→IRQ0x0200→0x20→image→0x32`, ma non è un cancel.
Un `0x32` successivo è accettato senza restore osservato, mentre l'ultimo
`0x32` termina con la capture. Timeout, errori, close USB/TLS, deinit e service
stop non sono esposti. `gfOnCancel` resta host-only, `0x34` arma finger-up e
A2/`0x70` non compaiono come restore. La durata dell'arm, la sopravvivenza ai
close e il safe stop senza dito restano ignoti/non provati.

```text
INITIAL_FDT36_SEED_SOURCE=HOST_SUPPLIED_VIA_GFUSB_CALLBACK; ULTIMATE_SOURCE_UNRESOLVED
FRESH_BASELINE_BOOTSTRAP_CLOSED=false
GOODIX_DAT_AVAILABLE_FOR_AUDIT=false
FDT36_TARGET_OCCURRENCE_COUNT=3
FDT36_ZERO_TAIL_OBSERVED_ON_TARGET=false
FDT36_ZERO_TAIL_TARGET_EQUIVALENCE=NOT_PROVEN
FDT36_PHYSICAL_CONTRACT_LIVE_READY=false
POST_FDT_RESTORE_MODEL=NO_EXPLICIT_RESTORE; SUCCESS_CYCLE_EVENT_CONSUMPTION; STOP_FAILURE_MODEL_UNKNOWN
DEVICE_SIDE_CANCEL_COMMAND=NOT_FOUND_OR_PROVEN
FDT_ARM_SURVIVES_USB_CLOSE=UNKNOWN
SAFE_STOP_AFTER_FDT_ARM=false
CMD20_22_RELATION=CMD1_SELECTOR_0_VERSUS_1; MORE_0_FOR_BOTH
POST_IRQ2_IMAGE_COMMAND=0x22_DATA_0100
D249_FIRST_IMAGE_MODEL_STATUS=HISTORICAL_0x20_MODEL_CORRECTED_IN_CURRENT_CORE; OFFLINE_ONLY
NEXT_MINIMUM_LIVE_BOUNDARY=NONE
D253_OUTCOME=BLOCKED
D253_LIVE_BOUNDARY=BLOCKED
D253_LIVE_EXECUTION=NOT_PERFORMED
REQUIRES_EXTERNAL_EVIDENCE=true
```

Per riaprire il confine servono insieme: una traccia OEM sanitizzata da
cold-start che mostri input/chiamante del callback seed, cache e criterio del
loop; e una traccia OEM di cancel/timeout/service-stop/close subito dopo FDT
arm con verifica deterministica dello stato successivo. Un receiver/lifecycle
APP12509 provenance-valid può sostituire le parti che prova. Ripetere il live
esistente non produce questa evidenza.

## D254: audit esterno FDT, cache OEM e lifecycle

L'audit riproducibile `analysis/D254/d254_external_audit.py` pinna la fonte A
al commit `d39e34f240270bb13c3977a7fa99973c346fa81f`, verifica gli hash prima
del parsing e genera soltanto metadati sanitizzati. Il WBDI associato al
repository non appartiene a un 5125/12509: dichiara `27c6:5110`, chipid
`0x2504`, sensor type 12 e firmware `GF_ST411SEC_APP_12117`. È quindi evidenza
OEM cross-family.

Nel suo init riuscito, il file da 13520 byte viene letto, verificato CRC,
legato alla OTP e usato per NAV/image; segue la sequenza osservata
`FDT0 -> NAV -> FDT1 -> read-reg/delta -> 0x20 base image -> FDT2 -> save ->
FDT-down`. I tre seed sono `afaf...b7b7`, il learned table del passo 0 e quello
del passo 1; il learned table finale alimenta FDT-down. Il layout
`OTP64+FDT12+NAV3200+IMAGE10240+CRC4` spiega esattamente 13520 byte e rende
forte l'inferenza che il primo seed provenga dal campo FDT12 del cache, ma il
log non mostra la copia. Non è osservato un retry loop o un criterio di
convergenza: l'orchestratore completa esplicitamente gli stage 0/1/2. Il
singolo init non prova che il file sia sempre rigenerato né che il seed vari
fra sessioni. Nello stesso log, un controllo runtime `base_is_valid=0`
aggiorna image/NAV e salva di nuovo, mentre un successivo `base_is_valid=1`
termina senza altro save: il modello osservato è validate-and-refresh, non
rigenerazione incondizionata ad ogni controllo.

Il codice claimed-12509 della stessa fonte usa invece la costante
`b3b3c3c3a8a8b5b5a8a8b7b7`, fa due manual step separati da NAV, quindi
read-reg/DAC e `0x20`. Non implementa `0x32`, `0x34`, il current-target `0x22`
o un cancel device-side. Il commento “empirically verified” è una assertion
terza, non una capture. La costante non coincide col target; ciò è compatibile
con dipendenza device/config/session, ma non ne distingue la causa. README e
codice dipendono inoltre dalla plaintext PSK specifica del device, quindi le
claim di funzionamento non chiudono un percorso factory-PSK-preserving.

La capture Issue #63, hash
`5b2e9649b8acdbf93bbb19275feb32203dacc50d727ef2222d58162fbd1b63d0`,
include un descrittore `27c6:5125` ma nessun A8: firmware `UNKNOWN`. Comincia a
sessione già armata e contiene 22 `0x36`, 21 IRQ2, 22 IRQ100 e 13 IRQ200.
Tutti i 21 IRQ2 sono seguiti da `0x22 [01 00]`. I `0x36` sono A0 logici da 22
byte in OUT fisici da 64, con nonzero fuori frame solo agli offset 40–45:
`cb f2 ca 66 f8 7f`, diverso dal target `cb f2 e2 be fb 7f`. Questo corrobora
la natura di staging residue, non l'equivalenza zero-tail. La capture mostra
solo cicli positivi; termina su IRQ200 dopo `0x34` e non prova cancel, timeout,
close o restore.

Rocky rimane l'asse APP12508: il suo campionatore accetta il primo IRQ100
valido entro al massimo tre tentativi, usa seed zero/cache, `0x20` post-IRQ2 e
un flag di cancel host-side. Non equivale ai tre stage OEM WBDI né al target.
La matrice D254 completa classifica ogni cella come target capture, OEM cross-
family, third-party code/capture o unknown.

```text
EXTERNAL_A_WBDI_EVIDENCE_CLASS=CROSS_FAMILY_OEM_LIFECYCLE_EVIDENCE_5110_APP12117
EXTERNAL_12509_FDT_SEED=b3b3c3c3a8a8b5b5a8a8b7b7
EXTERNAL_12509_SEED_MATCH_LOCAL_TARGET=false
ISSUE63_FIRMWARE=UNKNOWN
ISSUE63_FDT36_COUNT=22
ISSUE63_POST_IRQ2_IMAGE_COMMAND=0x22_DATA_0100_FOR_ALL_21_OBSERVED_IRQ2_EVENTS
EXTERNAL_OEM_FDT_PASS_MODEL=FIXED_THREE_SUCCESSFUL_NAMED_STAGES_IN_OBSERVED_INIT
EXTERNAL_OEM_INITIAL_SEED_SOURCE=BASEFILE_FDT12_STRONGLY_INFERRED; DIRECT_COPY_NOT_LOGGED
BOOTSTRAP_BLOCKER_REDUCED=true
BOOTSTRAP_CLOSED=false
RESTORE_BLOCKER_REDUCED=false
RESTORE_CLOSED=false
D254_OUTCOME=BLOCKED
NEXT_MINIMUM_LIVE_BOUNDARY=NONE
D254_LIVE_BOUNDARY=BLOCKED
D254_LIVE_EXECUTION=NOT_PERFORMED
```

La singola acquisizione con massimo valore è una capture Windows APP12509
sanitizzata che inizi dal cold-start e mostri validazione cache e sorgente del
primo seed, poi prosegua fino a `0x32`, cancel operatore senza dito e re-entry
deterministica. Non è una sequenza Linux live proposta.

## D255: acquisizione Windows APP12509 e recovery offline

La ricostruzione storica distingue fatti e lacune. Il file
`rilevamento.pcapng`, hash `50071c0f...19c184b`, usa linktype USBPcap; manuale
ed evidence index lo classificano come cold attach e citano una seconda
capture indipendente ora perduta. `GoodixExport.zip` ne ha preservato il file
insieme a `gfusb.dll` e componenti OEM. Non sono invece preservati comando di
capture, versione Wireshark/USBPcap, prodotto VM, comando di passthrough o path
del log. Non è quindi provato il locus esatto del vecchio collector.

Il metodo poi eseguito avvia TShark sull'interfaccia USBPcap esplicita nel
guest Windows mentre il target è ancora assente; solo dopo i marker
`CAPTURE_PROCESS_STARTED` e `CAPTURE_STARTED` l'operatore usa il normale attach
GUI già revisionato. Entrambi significano processo TShark attivo e target
ancora assente, non file già creato/non vuoto o frame acquisiti. È
preferito al restart di Windows Biometric Service, che non è dimostrato come
trigger dell'intero init, e al disable/enable PnP, meno conservativo. Nessun
wrapper host è stato inventato in assenza di un hypervisor canonico. Il cold
attach è un normale lifecycle OEM con rischio Windows basso ma non nullo; le
capture storiche e l'assenza di azioni maintenance sostengono il confine
factory-preserving, senza costituire prova assoluta di nonmutazione NVM interna.

La prima review AI-PM ha respinto il kit iniziale come non eseguibile/correlabile:
`SHA256.HashData`, `Convert.ToHexString` e `Path.GetRelativePath` non possono
essere assunte su Windows PowerShell 5.1/.NET Framework, e `_oem_timestamp()`
accettava solo ISO-8601 nonostante il corpus D254 esponga timestamp Goodix
`[MMDD-HH:MM:SS:mmm]`. Quella baseline non è autorizzabile per hardware.

La revisione correttiva di
`operator_kit/d255-windows-evidence-capture.ps1` usa ora
`SHA256.Create()`/`ComputeHash()`/`BitConverter` e un helper relativo basato su
`Path.GetFullPath`, separatore normalizzato e confronto
`OrdinalIgnoreCase`; `C:\run2` non può essere accettato come figlio di
`C:\run`. Il nuovo `-SelfTestOnly`, distinto da `-PreflightOnly`, non richiede
target, autorizzazione o TShark e controlla runtime, SHA-256 KAT, path relativo,
sibling rejection, clock/JSON e collisioni con hardware action count zero.

La seconda review AI-PM ha individuato un difetto ulteriore nello stesso
boundary: il launcher assumeva recognition, mentre
`CURRENT_WINDOWS_VM_FINGERPRINT_ENROLLMENT=NOT_COMPLETED` e la disponibilità di
quel prompt non è provata. La storia nativa/operativa precedente non viene
promossa a stato della VM corrente. D175 viene usato soltanto come evidenza di
cold attach passivo e init OEM automatico senza Hello o dito; l'UI esatta della
capture sopravvissuta `rilevamento.pcapng` non è canonicamente preservata.

La terza review AI-PM ha respinto anche il requisito del vero wizard fingerprint
pre-attach e l'equivalenza implicita re-entry→restore. Windows Hello Fingerprint
è sensor-dependent: con Goodix assente dal guest il relativo controllo può
essere nascosto, indisponibile o non configurabile anche se funzionerebbe dopo
l'attach. Inoltre A8 o nuovo `0x32` accettato nella seconda sessione non
osservano necessariamente il disarm del prior arm. Questa è la decisione
canonica corrente, non un limite cosmetico del launcher.

Nel ramo one-shot eseguito, la VM Windows era già avviata e il Goodix restava visibile
sull'host Linux ma assente dal guest. Il preflight verifica soltanto
Sign-in-options/account-level: enrollment `NOT_COMPLETED`, nessuna creazione o
modifica PIN, e `WINDOWS_HELLO_PIN_STATE` in
`ALREADY_CONFIGURED|NOT_CONFIGURED|UNKNOWN|NOT_REQUIRED_BY_CURRENT_ACCOUNT_POLICY`.
Se policy setup=`REQUIRED` e PIN=`NOT_CONFIGURED`, il run fallisce prima
dell'autorizzazione. La disponibilità UI fingerprint resta
`UNKNOWN_BEFORE_ATTACH`. Se TShark vede una sola interfaccia USBPcap la selezione
è univoca; se ne vede più di una, il launcher richiede la capture simultanea di
tutte o fallisce `USBPCAP_INTERFACE_SELECTION=AMBIGUOUS`.

Solo dopo questi gate si scrive `authorization_consumed.json` e si tenta
TShark. Il launcher prova il processo attivo e di nuovo l'assenza del target,
senza usare la materializzazione del pcapng come gate pre-attach, poi presenta
una sola azione
`OPERATOR_ACTION_VM_USB_ATTACH`; non contiene attach/detach automatico. Un
failure di start dopo il record consuma il run. Il postprocessor richiede che
il descriptor `27c6:5125` compaia dopo `CAPTURE_STARTED`, entro i marker
`VM_USB_ATTACH_BEGIN/END`, su un solo bus/device, e che l'A8 byte-exact
`GF_ST411SEC_APP_12509` preceda `PASSIVE_BOOTSTRAP_SETTLED` e il successivo gate
UI. Descriptor pre-capture,
assenza di enumerazione, secondo device/attach o topology change invalidano la
provenance bootstrap. Lo script non invoca service restart, PnP mutation, VM,
provisioning, flash o comandi Goodix. Il cache discovery resta ristretto a root
Goodix e a size/naming pertinenti.

`analysis/D255/d255_postprocess_windows_evidence.py` opera solo su path privati
hash-gated, canonicamente sotto `captures/`. Seleziona il device tramite A8 esatto, ricostruisce A0/B0 senza
esportare payload, misura il contratto fisico `0x36`, valida l'ipotesi
`OTP64+FDT12+NAV3200+IMAGE10240+CRC4`, confronta solo FDT12 e hash di regioni,
e censisce la finestra ultimo `0x32` → cancel → re-entry. La UI sensor-dependent
è verificata soltanto post-attach/A8/bootstrap con una scelta strutturata:
`READY_WAITING_FOR_FINGER`, `UI_UNAVAILABLE`, `NEW_PIN_REQUIRED` o
`UNEXPECTED_PREREQUISITE`. Solo READY prosegue con due attese e due
cancellazioni, sempre senza dito, enrollment o modifica PIN. Nella finestra
`OEM_WAITING_NO_FINGER` → `REENTRY_CANCEL_END`, il sanitizer censisce IRQ
finger-down `0x0002`, exact `0x22 [01 00]` e image-sized B0; qualunque occorrenza
produce `INVALID_FINGER_INTERACTION` e forza `RESTORE_CLOSED=false`.
Il launcher conserva
local-only snapshot OEM before/after con path, size, hash e mtime; il parser usa
come nuova finestra soltanto un append byte-prefix verificato e distingue
`UNCHANGED`, `GREW`, `TRUNCATED` e `REPLACED_OR_ROTATED`.

Il preflight reale della VM ha dimostrato che questa raccolta non può assumere
l'esistenza del log: `C:\ProgramData\Goodix` contiene cache Goodix leggibili,
ma nessun `goodix*.log` o `wbdi*.log` nelle directory candidate. Il vecchio
`no readable OEM/WBDI log source was identified` bloccava quindi un caso reale
senza ridurre rischio device-side. `D255_WINDOWS_PREFLIGHT_V4` accetta zero
candidate log e riporta separatamente `OEM_LOG_STATUS`,
`OEM_LOG_SOURCE_COUNT`, `GOODIX_CACHE_STATUS` e
`GOODIX_CACHE_SOURCE_COUNT`. Quando presenti, log e cache continuano a essere
snapshot before/after; un path esplicito illeggibile resta fail-closed. Gli
snapshot vuoti sono array JSON validi. Il postprocessor accetta l'assenza di
log, conserva l'analisi wire/cache e marca la correlazione temporale
`UNAVAILABLE_NO_OEM_LOG`, senza promuovere restore o causalità.

La prima invocazione live successiva, pur autorizzata dall'operatore sulla
baseline `74a1ebda24166ac026ef7ed55c15f0d21e4593e3`, ha esposto una distinzione
PowerShell non coperta dal solo preflight: il parametro mandatory
`Write-OemLogSnapshot.Candidates` non accettava l'array vuoto e il binder ha
generato `ParameterArgumentValidationErrorEmptyArrayNotAllowed` prima di
entrare nella funzione. Il ramo aveva già creato directory e marker locali, ma
non aveva ancora raggiunto il confronto di autorizzazione, l'assegnazione
`$script:AuthorizationConsumed = $true`, `authorization_consumed.json` o
`Start-Process`; risultano quindi autorizzazione non consumata, capture non
avviata, zero attach, zero USB open e zero azioni hardware.

Una run seguente sulla baseline approvata
`999483362af23f67790eb6e54f4c02bb48bd6cd5` ha invece consumato
l'autorizzazione e avviato TShark, poi ha prodotto
`D255_FAIL_CLOSED: capture process is alive but output file was not created`
al controllo fisso dei due secondi. Il Goodix non è stato collegato alla VM e
non è avvenuta alcuna azione sul sensore. Il successivo pcapng zero-byte con
timestamp di diversi secondi posteriore prova la race host-side del gate. La
futura run richiede review AI-PM, approvazione di un nuovo SHA live-critical e
una nuova autorizzazione esplicita; quella consumata non è riutilizzabile.

La run successiva sulla baseline approvata
`f01b81d629ffe8af5eecb92ca93968045d5345ce` ha invece completato l'intero
percorso operatore senza dito. La capture canonica è
`captures/D255_20260822T205631772Z_85c8c41f/raw/wire.pcapng`: 27.684 byte,
218 frame leggibili, `FIRST_FRAME=1`, SHA-256
`802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`.
Tutti i marker da `CAPTURE_PROCESS_STARTED` a `OPERATOR_PHASES_COMPLETE` sono
presenti una volta e ordinati. Il failure finale
`HOST_SIDE_TSHARK_EXITCODE_NULL_OR_UNAVAILABLE` è il bug noto di Windows
PowerShell 5.1 per processi `Start-Process -PassThru` con `-NoNewWindow` e
stream rediretti: dopo `Wait-Process`, il wrapper può non esporre l'ExitCode
anche se `HasExited=true`. Il launcher conserva ora anticipatamente l'handle e
tratta l'ExitCode come nullable. Zero numerico più pcap valido produce `PASS`;
null più processo terminato, file presente/non vuoto e almeno un frame
leggibile produce `PASS_WITH_EXIT_CODE_UNAVAILABLE`; non-zero, processo ancora
attivo o pcap invalido restano `FAIL_CLOSED`. Stdout/stderr rimangono soltanto
diagnostica e non sostituiscono la prova di leggibilità.

`analysis/D255/d255_recover_existing_run.py` ha finalizzato la run interamente
offline con `REAL_USB_OPEN_COUNT=0`, `REAL_CAPTURE_COUNT=0`,
`REAL_HARDWARE_ACTION_COUNT=0` e `RAW_PCAP_MODIFIED=false`. Il recovery
manifest SHA-256 è `deb08f42...dcedaa`. Gli snapshot after e il manifest
originale mai creati restano `NOT_RECOVERABLE`; il postprocessor distingue
`ORIGINAL_ARTIFACT`, `RECOVERED_ARTIFACT` e `NOT_RECOVERABLE`. L'esecuzione
reale del postprocessor passa: target APP12509, cold attach valido,
`VALID_ZERO_FINGER`, tre `0x36`, primo seed
`aeaebfbfa4a4b2b2a7a7b3b3` uguale all'FDT12 del cache before, re-entry e nuovo
arm accettato. Non prova causalità del seed né disarm del prior arm; senza log
OEM e snapshot after la closure restore resta inconclusiva e soggetta a review
AI-PM. `NEW_LIVE_CAPTURE_REQUIRED=false`.

Il riesame metodologico che precedette quella run era:

1. cambia la semantica della readiness, da file creato entro due secondi a
   processo TShark vivo più target ancora assente, con materializzazione
   post-attach e validazione finale forte;
2. testa l'ipotesi nuova che il failure osservato fosse soltanto ritardo
   host-side di creazione/buffering del pcapng con processo sano;
3. se il failure ricorre nello stesso punto, non si ripete il live: si conserva
   la diagnostica redatta e si studia TShark/USBPcap nativo con un riproduttore
   Windows senza hardware prima di proporre un metodo diverso.

L'audit orizzontale delle collezioni separa i casi semanticamente vuoti da
quelli non vuoti. `OemLogPath`, candidate OEM, `CacheRoot`, roots/file cache e
le corrispondenti collezioni del setup condiviso possono legittimamente essere
vuoti e ora espongono un contratto `AllowEmptyCollection`; un helper dedicato
scrive `[]` senza affidarsi a un secondo binding vuoto di `ConvertTo-Json`.
`CaptureInterface`, candidate USBPcap e match dei selettori non possono invece
essere vuoti nel percorso live: mantengono failure espliciti, univocità o
capture-all. Le collezioni UI/marker sono enumerazioni interne fisse o output
naturalmente vuoti e non espongono un parametro mandatory problematico.

Il setup log/cache/runtime/preflight/argomenti di cattura è ora una funzione
unica chiamata sia dal live sia da `-PreAuthorizationSimulationOnly`. La
simulazione vieta autorizzazione, TShark, interfacce e path reali, usa fixture
sintetiche ABSENT/PRESENT e si arresta prima del consumo/autorizzazione e di
`Start-Process`, con contratto atteso:

```text
EMPTY_OEM_LOG_CANDIDATES_BINDING=PASS
EMPTY_CACHE_ROOTS_BINDING=PASS
AUTHORIZATION_CONSUMED=false
REAL_CAPTURE_STARTED=false
REAL_USB_OPEN_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
```

Non sono stati rimossi altri gate pre-autorizzazione: assenza/topologia guest,
chiusura selezione USBPcap, prerequisiti account/PIN, leggibilità dei path
espliciti, runtime, collisione/spazio output, autorizzazione esatta e prova di
processo TShark attivo riducono rischio device-side, perdita di provenance o
failure operativi reali. Il requisito obbligatorio del log OEM e quello del
pcapng già creato entro due secondi erano gate host-side non probanti e restano
eliminati. Il deadline PnP post-attach e la durata bounded restano perché
proteggono rispettivamente enumerazione reale e contenimento della capture.

Ogni evento OEM sanitizzato espone sorgente timestamp, UTC e qualità, mai la
linea raw. ISO-8601 con offset/Z è diretto; Goodix MMDD viene convertito solo se
anno del run, offset locale, Windows timezone, anchor start/end e marker UTC
selezionano un istante unico. Stesso giorno, mezzanotte e fine anno non ambigua
sono supportati; cambio offset/DST, data malformata o fuori finestra e rotazione
non ricostruibile restano `AMBIGUOUS`. Eventi critici cancel/restore non
correlabili impongono `RESTORE_MODEL=INCONCLUSIVE_OEM_TIME_CORRELATION` e non
promuovono `CANCEL_IS_HOST_ONLY` o `USB_CLOSE_AFTER_CANCEL`.

Se la UI non è ready, il run consumato termina senza cancel/re-entry e lascia
scadere il timer bounded; processo terminato, ExitCode zero oppure non
disponibile, file non vuoto e readback di un frame validano il pcapng prima
degli snapshot after e del manifest. Un ExitCode numerico non-zero resta
terminale. Il postprocessor
accetta `PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE` senza marker cancel ma conserva
descriptor/A8, cache, primo `0x36` e profilo fisico. Produce
`BOOTSTRAP_EVIDENCE_PRESERVED=true`, `RESTORE_EVIDENCE_ACQUIRED=false` e
`RESTORE_CLOSED=false`.

Nel ramo full occorre distinguere quattro fatti: la fase cancel operatore è
completata; la cancellazione della richiesta host è osservata in D256 tramite
una completion bulk-IN cancellata; il disarm device-side non è provato; la
re-entry e il nuovo `0x32` accettato sono provati. La vecchia scorciatoia
`OEM_CANCEL_REENTRY_PROVEN` non va usata come sinonimo di questi quattro
concetti. `PRIOR_ARM_LIFETIME_AFTER_CANCEL=UNOBSERVED` e la sola re-entry non
promuove `RESTORE_CLOSED`; prova invece che un restore USB esplicito non è un
prerequisito osservato per la continuazione/re-arm. L'uguaglianza wire/cache/log
resta correlazione, mai automaticamente causalità. Un A8 assente/diverso rende
l'evidenza non target-specific e terminale; marker/formati inattesi e collisioni
falliscono chiusi senza retry.

I 56 test D255 passano. Oltre alle coperture storiche includono i quattro casi
di finalizzazione TShark — ExitCode 0, ExitCode nullo con pcap valido, ExitCode
nullo con pcap assente/vuoto/illeggibile e ExitCode non-zero — e il recovery
end-to-end su fixture incompleta con hash e mtime raw invariati. La run reale è
stata recuperata e postprocessata offline con successo. `pwsh` non è installato
sull'host Linux: il nuovo handle-caching non è stato rieseguito su Windows
PowerShell 5.1 dopo la patch, ma l'osservazione nativa della run e il bug runtime
documentato chiudono la causa; la semantica nullable è coperta offline e non
richiede una nuova capture.

```text
D255_INITIAL_AI_PM_REVIEW=FAIL_EXECUTABILITY_AND_TIME_CORRELATION
D255_SECOND_AI_PM_REVIEW=FAIL_CURRENT_VM_RECOGNITION_PATH_ASSUMPTION
D255_THIRD_AI_PM_REVIEW=FAIL_PREATTACH_SENSOR_UI_GATE_AND_RESTORE_OVERCLAIM
D255_REAL_PREFLIGHT_OBSERVATION=FAIL_UNPROVEN_OEM_LOG_REQUIREMENT
D255_PRIOR_LIVE_PATH_OBSERVATION=FAIL_PARAMETER_ARGUMENT_VALIDATION_EMPTY_ARRAY_BEFORE_AUTHORIZATION
D255_LATEST_LIVE_PATH_OBSERVATION=CAPTURE_ACQUIRED_FINALIZATION_FAILED_EXITCODE_UNAVAILABLE
D255_LATEST_RUN_AUTHORIZATION_CONSUMED=true
D255_LATEST_RUN_TSHARK_STARTED=true
D255_LATEST_RUN_GOODIX_ATTACHED_TO_VM=true
D255_LATEST_RUN_OPERATOR_PHASES=COMPLETED_ZERO_FINGER
D255_CORRECTIVE_STATUS=RECOVERED_READY_FOR_AI_PM_REVIEW
D255_OUTCOME=CAPTURE_ACQUIRED_RECOVERED_AND_POSTPROCESSED_OFFLINE
D255_OEM_LOG_REQUIREMENT=OPTIONAL_REPORTED_PRESENT_OR_ABSENT
D255_GOODIX_CACHE_REQUIREMENT=OPTIONAL_REPORTED_PRESENT_OR_ABSENT
D255_WINDOWS_EXECUTION_ENVIRONMENT=VIRTUAL_MACHINE
D255_VM_USB_ATTACH_METHOD=OPERATOR_GUI_MANUAL_ATTACH
D255_CURRENT_WINDOWS_VM_FINGERPRINT_ENROLLMENT=NOT_COMPLETED
D255_SELECTED_WINDOWS_UI_PATH=WINDOWS_HELLO_SETUP_NO_FINGER
D255_SENSOR_DEPENDENT_UI_AVAILABILITY_BEFORE_ATTACH=UNKNOWN_BEFORE_ATTACH
D255_PARTIAL_BOOTSTRAP_RESULT_SUPPORTED=true
D255_REENTRY_ALONE_CAN_CLOSE_RESTORE=false
D255_FINGER_INTERACTION_ALLOWED=false
D255_LIVE_PATH_ATTEMPT=COMPLETED_OPERATOR_PHASES_FINALIZATION_FALSE_FAILURE
D255_LIVE_CAPTURE=SUCCEEDED
D255_CAPTURE_BYTES=27684
D255_CAPTURE_FRAME_COUNT=218
D255_FIRST_FRAME=1
D255_CAPTURE_SHA256=802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c
D255_NEW_RUN_REQUIRED=false
FUTURE_LIVE_OPERATOR_AUTHORIZATION_REQUIRED=true
D255_AUTHORIZATION_CONSUMED_AFTER_PRE_HARDWARE_SETUP=true
D255_TSHARK_PREATTACH_READINESS=PROCESS_STARTED_AND_ALIVE_TARGET_ABSENT
D255_PREATTACH_PCAP_FILE_REQUIRED=false
D255_FINAL_PCAP_VALIDATION=PROCESS_EXITED_AND_EXIT_ZERO_OR_UNAVAILABLE_AND_EXISTS_NONEMPTY_READABLE_FRAME
D255_RECOVERY_RESULT=PASS_RECOVERED_READY_FOR_OFFLINE_POSTPROCESSING
D255_POSTPROCESS_RESULT=PASS
D255_POST_CAPTURE_STATE_SNAPSHOT=NOT_RECOVERABLE_RETROACTIVELY
D255_PRIVATE_EVIDENCE_CANONICAL_LOCATION=captures/
D255_NEW_LIVE_CAPTURE_REQUIRED=false
D255_EMPTY_OEM_LOG_CANDIDATES_SUPPORTED=true
D255_EMPTY_ARRAY_CLASS_AUDIT=PASS
D255_SHARED_PREAUTHORIZATION_SIMULATION=HISTORICAL_NOT_REQUIRED_FOR_RECOVERY
D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true
READY_FOR_AI_PM_REVIEW=true
READY_FOR_OPERATOR_RUN=false
BOOTSTRAP_CLOSED=false
RESTORE_CLOSED=false
```

## D256: contratto USB lifecycle osservato nella capture D255

L'audit riproducibile
`analysis/D256/d256_usb_lifecycle_contract_audit.py` riusa il parser pcapng
D255, verifica prima del parsing path, SHA-256, 27.684 byte, 218 frame e primo
frame `1`, quindi produce una timeline sanitizzata di tutti i 206 packet
USBPcap del target `bus 1 / device 2`. Hash, size e mtime del raw restano
invariati; nessun payload USB, OTP, PSK, cache raw o materiale biometrico entra
nei derivati.

La finestra critica inizia dal `0x32` frame 198, ACKato prima del marker cancel.
Tra `CANCEL_NO_FINGER_BEGIN` e `CANCEL_NO_FINGER_END` non compare alcun packet
target. Dopo `REENTRY_BEGIN` il frame 202 completa con
`USBD_STATUS_CANCELED` una bulk-IN pendente: è prova di cancellazione della
richiesta host, non un comando device-side. Fino al nuovo `0x32` frame 214 e al
suo ACK frame 216 compaiono soltanto URB function `0x0009`; non si osservano
abort/reset pipe, clear-stall, control transfer, select configuration/interface,
descriptor replay o re-enumeration. Il target resta `1:2` sugli endpoint bulk
`0x01/0x81`.

Il corrective dello stesso D256 separa la seconda cancellazione terminale.
Il nuovo arm/ACK e la bulk-IN pendente sono rispettivamente ai frame
`214/216/217`. Fra `REENTRY_CANCEL_BEGIN` e `REENTRY_CANCEL_END` non compare
alcun packet, target o totale. Dopo `REENTRY_CANCEL_END` non passa traffico
prima del frame `218`, unica completion bulk-IN `0x81` con
`USBD_STATUS_CANCELED`; il frame `218` è anche l'ultimo del raw. Non esistono
quindi packet target o totali successivi. TShark dichiara `218 packets
captured`, la durata configurata è 600 secondi e il marker host finale cade
602,543790 secondi dopo `CAPTURE_PROCESS_STARTED`: la capture è rimasta bounded
fino al duration boundary senza ricevere altro traffico. La distanza
frame-218→marker `RUN_FAILED` è 491,125998 secondi; l'exact process-exit
timestamp non è disponibile e `RUN_FAILED` non è trattato come evento USB.

```text
USBPCAP_LIFECYCLE_AUDIT=PASS_COMPLETE_TARGET_PACKET_TIMELINE
CANCEL_TO_REENTRY_DEVICE_CONTINUITY=SAME_BUS_DEVICE_AND_BULK_ENDPOINTS
HOST_SIDE_PENDING_BULK_IN_CANCELLATION_OBSERVED=true
EXPLICIT_USB_RESTORE_OBSERVED=false
ABORT_OR_RESET_OBSERVED=false
REENUMERATION_OBSERVED=false
REENTRY_WITHOUT_EXPLICIT_USB_RESTORE_PROVEN=true
NEW_FDT_ARM_ACCEPTED_ON_REENTRY=true
RESTORE_REQUIRED_FOR_REENTRY=false
PRIOR_ARM_DISARM_PROVEN=false
PRIOR_ARM_LIFETIME_AFTER_CANCEL=UNOBSERVED
TERMINAL_CANCEL_PENDING_BULK_IN_CANCELED=true
EXPLICIT_USB_TERMINAL_RESTORE_OBSERVED=false
TERMINAL_CANCEL_ABORT_OR_RESET_OBSERVED=false
TERMINAL_CANCEL_REENUMERATION_OBSERVED=false
POST_TERMINAL_CANCEL_CAPTURE_WINDOW_SECONDS=491.125998
POST_TERMINAL_CANCEL_TARGET_USB_PACKET_COUNT=0
POST_TERMINAL_CANCEL_TOTAL_PACKET_COUNT=0
OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN=true
DEVICE_INTERNAL_FDT_STATE_AFTER_CANCEL=UNOBSERVED
```

`RESTORE_REQUIRED_FOR_REENTRY=false` è rigorosamente path-bounded: il nuovo arm
è stato accettato senza restore USB esplicito osservato. Non implica che il
prior arm sia stato disarmato o che ogni restore sia inutile. Separatamente,
`OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN=true` chiude il contratto host/bus
del secondo cancel sul path osservato: la richiesta pendente è cancellata e il
bus resta silente fino alla chiusura della capture. Non prova disarm, expiry o
clear del mode FDT interno.

Il vecchio `SAFE_STOP_AFTER_FDT_ARM=UNRESOLVED` è superato dalla scomposizione:
contratto host/bus terminal-stop chiuso, quiescenza USB provata, stato interno
e lifetime non osservati, nessuna nuova implicazione factory-persistence
device-side derivata dal silenzio USB. Le classi URB di audit comprendono ora
anche `0x0002` abort pipe, `0x001e` sync reset-and-clear-stall, `0x0030` sync
reset pipe e `0x0031` sync clear-stall. Nessuna compare nella finestra reale,
quindi la robustezza del parser non cambia l'esito empirico. Sul corrente host
offline non sono installati header WDK, sorgenti Wireshark o TShark: il check
locale indipendente della nomenclatura resta dichiarato indisponibile e non è
stata usata la rete.

I control D255 `0x50` e `0x97` non sono nuovi: il census D230 classificava già
`0x50` come famiglia sensor/mode a semantica esatta irrisolta e mappava wire
`0x97` al builder `SetDriverState` logico `0x96`. D255 contiene un solo `0x50`,
frame 150, A0 logico 10/fisico 64, ACK `B0/50/01` e una A0/50 lunga seguente;
è nel bootstrap fra primo e secondo `0x36`. Contiene un solo `0x97`, frame 40,
A0 logico 10/fisico 64 senza ACK/response prima del successivo OUT, nella
sequenza iniziale pre-TLS. Nessuno compare nella finestra cancel/re-entry o
fornisce evidenza di restore. La lista `unknown_controls` D255 rifletteva
quindi una allowlist locale incompleta, non una nuova semantica protocollo.

La verifica statica severamente bounded conferma nel solo slice già noto che
`gfOnCancel` non chiama direttamente i builder A0. Le stringhe D0 già censite
non provano che D0Exit/D0Entry siano avvenuti nella run; non emerge un nuovo
dataflow USB e
`STATIC_LIFECYCLE_CORROBORATION=EXHAUSTED_NO_NEW_DATAFLOW`.

Il claim bootstrap massimo resta separato: il cache `goodix.dat` da 13.520
byte ha layout/CRC validi, è OTP-bound al target e il suo FDT12 uguaglia il
primo seed wire nella cold attach D255. La correlazione host/cache/wire è
provata, ma non il dataflow causale della callback né freschezza/lifetime
generali.

```text
BOOTSTRAP_CACHE_LAYOUT_TARGET_VALID=true
BOOTSTRAP_CACHE_OTP_BOUND=true
BOOTSTRAP_CACHE_FDT12_EQUALS_FIRST_WIRE_SEED=true
BOOTSTRAP_SEED_SOURCE_CORRELATED=true
BOOTSTRAP_SEED_DATAFLOW_CAUSALITY_PROVEN=false
BOOTSTRAP_SEED_FRESHNESS_SCOPE=FIRST_0x36_IN_THIS_D255_COLD_ATTACH_ONLY; GENERAL_LIFETIME_UNPROVEN
CURRENT_CORPUS_EXHAUSTED_FOR_REENTRY_RESTORE_QUESTION=true
CURRENT_CORPUS_EXHAUSTED_FOR_INTERNAL_ARM_LIFETIME_QUESTION=true
```

Il risultato strategico è il Caso A: non manca più una componente osservabile
del terminal stop host/bus nel corpus corrente; restano non osservabili lo stato
volatile FDT e la lifetime del prior arm. Una review futura può separare i
requisiti factory-preserving/compatibilità Windows, internal disarm e
live-readiness FDT. D256 è interamente offline, non autorizza FDT live, non
richiede una capture equivalente e non crea un operator kit. Il bundle D256
precedente è `SUPERSEDED_BY_D256_TERMINAL_CANCEL_CORRECTIVE`; il blob storico
resta preservato dalla history Git.

## D257: corrective exact fresh-bootstrap

D257 resta esclusivamente offline e conserva il provider cache esplicito
GPL-2.0-or-later: path fornito dal chiamante, lettura stabile e read-only,
layout OTP64 + FDT12 + NAV3200 + IMAGE10240 + CRC4 = 13.520 byte, CRC-32/MPEG-2
little-endian e binding constant-time all'identità OTP64. Assenza, layout, CRC,
binding o FDT12 non validi falliscono chiusi; non esistono fallback, derivazione
da PSK o scrittura della cache.

Il corrective ricalcola dal raw D255 hash
`802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`
l'intero segmento logico dalla coppia fresh AF/AE fino all'ACK del primo
successivo `0x32`, senza preselezionare soltanto i frame FDT:

```text
0x36/ACK/IRQ100
0x50/ACK/NAV dinamico
0x36/ACK/IRQ100
0x82/ACK/risposta a due byte
0x20/ACK/baseline B0 cifrata
0x36/ACK/IRQ100
0x32/ACK
```

Il replay pre-corrective dei tre `0x36` e del contratto cancel/re-entry D256
resta `PROJECTED_FDT_SUBSEQUENCE_REPLAY=PASS_HISTORICAL`, ma non costituisce
`EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY`. Il `0x50 [01 00]` produce una risposta
NAV A0/`0x50` dinamica da 2.417 byte; l'interstage `0x82
[00 82 00 02 00]` legge due byte dal registro `0x0082`; `0x20 [01 00]`
produce la baseline/image B0 cifrata da 7.726 byte prima del terzo `0x36`.
D254 corrobora cross-family un lifecycle NAV/read-reg/baseline, ma non prova i
predicati APP12509. La necessità causale non è esclusa: tutti e tre gli stage
sono obbligatori nel candidate esatto e i gate host su NAV, delta e baseline
decifrata sono input dinamici, non blob D255 hardcoded. Poiché i predicati
target non sono derivabili dal raw, il replay esatto fallisce chiuso al primo
gate assente.

`core/fdt_lifecycle.py` distingue ora il modello storico proiettato dal
candidate esatto con ordine `36,50,36,82,20,36,32`. Sul primo `0x36` il latch
precede la submission, il massimo è un tentativo, il timeout contrattuale è
100 ms e avanzano solo ACK `36/01`, IRQ `0x0100` con touch zero e transform/
validator della tabella. Ogni errore ferma nuovo traffico, cancella una receive
pendente se presente e completa il cleanup host terminale. Non esistono retry,
A2, `0x70` o famiglie persistenti. Un test negativo prova che ACK errato lascia
un solo request/attempt e impedisce una seconda submission; un test sintetico
positivo prova l'ordine completo soltanto come proprietà implementativa.

La provenance temporale D255 è anch'essa ricalcolata programmaticamente:

```text
CACHE_MTIME_UTC=2026-08-22T20:29:28.5244390Z
VM_ATTACH_BEGIN_UTC=2026-08-22T20:56:34.7220147Z
FIRST_0x36_UTC=2026-08-22T20:56:44.146639Z
CACHE_MTIME_TO_ATTACH_BEGIN_SECONDS=1626.1975757
CACHE_MTIME_TO_FIRST_0x36_SECONDS=1635.6222000
SAME_ATTACH_SEED_GENERATION_REQUIRED=false
PERSISTED_PRE_ATTACH_CACHE_REUSE_PROVEN=true
GENERAL_CACHE_TTL_PROVEN=false
```

I delta dal mtime non sono chiamati “seed age”, perché mtime e generation time
non sono provati equivalenti. D255 prova però il riuso riuscito di un cache
persistente OTP-bound e CRC-valid che precedeva l'attach di oltre 27 minuti e
il cui FDT12 coincide con il primo seed wire. La correlazione post-hoc dello
stesso tentativo sarebbe un gate pre-run circolare e non è richiesta per la
factory-preservation: nessuna famiglia persistente è raggiungibile e un input
invalido fallisce al primo ACK/evento/gate. La TTL generale resta ignota come
rischio di successo funzionale, non come blocker factory-preservation.

```text
PROJECTED_FDT_SUBSEQUENCE_REPLAY=PASS_HISTORICAL
EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY=BLOCKED_DYNAMIC_HOST_GATES_NOT_DERIVABLE_FROM_D255_RAW
FDT_OFFLINE_CANDIDATE_CLOSED=false
HOST_BUS_LIFECYCLE_READY=true
INTERNAL_PRIOR_ARM_STATE=NON_BLOCKING_EPISTEMIC_UNKNOWN
SEED_PROVIDER_IMPLEMENTED=true
SEED_FRESHNESS_GENERALIZATION=UNPROVEN
SEED_FRESHNESS_IS_SOLE_LIVE_BLOCKER=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
```

D256 resta canonico per cancel/re-entry e quiescenza terminale host/bus;
disarm/lifetime/stato interno restano ignoti epistemici non bloccanti. La
chiusura separata IRQ2→`0x22`→prima immagine sintetica resta valida, ma non
colma i gate bootstrap. Il bundle D257 precedente è preservato come provenance
e classificato `SUPERSEDED_BY_D257_EXACT_BOOTSTRAP_CORRECTIVE`. D257 non
apre USB, non usa hardware o dati biometrici, non crea launcher/operator kit,
non approva una baseline e non autorizza una run live.

## D258: proprietario e semantica dei gate host FDT

D258 è esclusivamente offline. L'audit statico mirato sul `gfusb.dll` target
SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`
ha recuperato l'orchestratore `gf_update_all_base` a
`0x180068adc..0x18006987d` e il caller che, su successo, invoca il final FDT
down a `0x180068abe`. Questo corregge l'inferenza D257 che collocava tutti i
gate dinamici prima del terzo sample.

Il percorso target statico è:

```text
stage0 0x36 -> acquisizione/store NAV 0x50 -> stage1 0x36
-> ChipRegRead 0x0082 -> confronto base0/base1
-> acquisizione baseline 0x20 -> stage2 0x36 -> confronto base1/base2
-> classificatore NAV mode1 -> classificatore immagine mode0 -> final 0x32
```

L'helper NAV `0x180067874` copia la risposta dinamica nel buffer di lavoro e
ritorna successo senza valutarne semanticamente il contenuto; stage1 segue
dunque la sola acquisizione strutturalmente valida. Il NAV viene consumato
dopo stage2 dal wrapper `0x180023fdc`, che imposta mode 1 e chiama il
classificatore comune `0x180022654`. La baseline acquisita da `0x180067914`
viene analogamente consumata dopo stage2 da `0x180023fa8`, mode 0, verso lo
stesso classificatore. Gli enum `0..3` selezionano riuso o aggiornamento delle
basi; non autorizzano il terzo sample, già completato.

La read `ChipRegRead(register=0x0082, quantity=2)` è invece chiusa: il byte 0
della risposta non viene usato su questo path, il byte 1 è zero-extended come
soglia unsigned e ogni elemento delle due basi FDT grezze è confrontato come
word unsigned:

```text
forall i: abs(uint16(base0[i]) - uint16(base1[i])) <= uint8(response[1])
```

Una violazione sceglie il fallback alla base file quando disponibile o il loop
di rebuild; il pass prosegue verso la baseline. Lo stesso confronto è ripetuto
fra base1 e base2. Nel raw D255 la massima differenza base0/base1 è `1` e la
soglia osservata è `29`, quindi il pass deriva dalla formula e non dal blob
hardcoded `80 1d`.

Il core GPL conserva ora NAV e B0 baseline come stato runtime, applica il gate
`0x82` nativo nel punto corretto, completa stage2 e sposta i classificatori
NAV/image nel boundary post-stage2. La decryption e i classificatori mancanti
restano obbligatori prima del final `0x32`: in loro assenza il candidate fallisce
chiuso. Il replay D255 esatto è wire-exact attraverso
`36,50,36,82,20,36`, poi si arresta prima di `0x32` sul primo classificatore
post-stage2 non riproducibile. Il replay proiettato D256/D257 resta distinto e
`PASS_HISTORICAL`.

Il classifier comune è presente nel corpus, ma la sua configurazione/stato
runtime target e un modello ABI esatto validabile non sono materializzati.
Per la baseline manca inoltre il plaintext application del B0 D255: la PSK
factory approvata vive fuori dal confine user-readable del repository, quindi
`D255_B0_DECRYPTION_STATUS=INPUT_UNAVAILABLE_WITHOUT_PRIVILEGE`. D258 non ha
letto path root-only, chiesto privilegi o copiato secret. Il corpus statico
locale è esaurito per queste domande: un ulteriore census dello stesso DLL
senza runtime state o plaintext non testerebbe una nuova ipotesi.

La policy temporale non riusa più accidentalmente un unico valore:

```text
COMMAND_TIMEOUT_POLICY=PER_COMMAND_EVIDENCE_BOUNDED
TIMEOUT_0x36_MS=500
TIMEOUT_0x50_MS=500
TIMEOUT_0x82_MS=500
TIMEOUT_0x20_MS=2000
TIMEOUT_0x32_MS=100
```

I valori derivano dai callsite OEM e sono compatibili con le latenze D255
osservate (`11.025`, `17.934`, `2.198`, `81.293`, `0.957` ms rispettivamente).
Timeout significa stop fail-closed e non retry.

```text
TARGET_BOOTSTRAP_SEQUENCE_HASH_GATED=true
GATE_0x50_STATUS=PARTIAL_STORE_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED
GATE_0x82_STATUS=CLOSED_NATIVE_PREDICATE_IMPLEMENTED
GATE_0x20_STATUS=PARTIAL_ACQUISITION_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED
CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x50_GATE=true
CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x82_GATE=true
CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x20_GATE=true
PROJECTED_FDT_SUBSEQUENCE_REPLAY=PASS_HISTORICAL
EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY=BLOCKED
DYNAMIC_HOST_GATES_CLOSED=false
FDT_OFFLINE_CANDIDATE_CLOSED=false
HOST_BUS_LIFECYCLE_READY=true
SEED_FRESHNESS_FACTORY_PRESERVATION_BLOCKER=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
```

D258 non modifica il backend USB reale, non crea launcher o operator kit, non
accede all'hardware e non autorizza una run live.

## D259: contratto minimo device-visible e consumo TLS B0

D259 è esclusivamente offline e supera il blocker D258 per separazione causale,
non ricostruendo artificialmente l'intero algoritmo OEM. L'audit riproducibile
è gated sul `gfusb.dll` SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`
e sul raw D255 SHA-256
`802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`.
Nel caller `0x180068940`, `gf_update_all_base` è chiamato a `0x18006898a` e
il final `ChicagoHUSetMode(3,1,1)` segue a `0x180068abe` per ogni return nonzero
dell'orchestratore.

La conclusione Class A preliminare era sostenuta da anchor corretti ma da una
matrice semantica codificata nel Python. Il corrective la sostituisce con
`D259_post_classifier_disasm_excerpt.txt` e
`D259_post_classifier_cfg.json`: un parser bounded estrae programmaticamente
le sole istruzioni pertinenti, deriva target condizionali/incondizionati,
case/default, merge, call, copy e dirty flag e genera da quel CFG la matrice
finale. Un campo non derivabile farebbe fallire l'audit invece di essere
promosso. La Classe A seguente è pertanto `PASS_MECHANICALLY_DERIVED`, non più
una riaffermazione dell'assertion harness preliminare.

I wrapper classifier NAV `0x180023fdc` e image `0x180023fa8` alimentano il
classificatore comune `0x180022654`. I rispettivi return sono salvati a
`[rsp+0x54]` e `[rsp+0x58]`; gli switch `0x1800693d8..0x1800694fa` e
`0x180069592..0x1800696b4` trattano esplicitamente `0`, `1`, `2`, `3` e fanno
convergere anche ogni altro valore. Soltanto il valore esatto `1` conserva la
base esistente. Tutti gli altri valori, inclusi negativi/altri, copiano la base
acquisita nelle globali host `0x18059fa88`/`0x18059fa78` e marcano il flag
dirty. Nessuno di questi rami modifica il risultato successo inizializzato in
`[rsp+0x44]`, né la globale tabella FDT `0x180580818`, letta separatamente dal
builder del final `0x32`.

La conseguenza delimitata è:

```text
CLASSIFIER_FIRST_ARM_ROLE=NON_BLOCKING
CLASSIFIER_FULL_DRIVER_ROLE=FUTURE_HOST_ALGORITHM_OR_CACHE_FIDELITY
CLASSIFIER_FDT_TABLE_EFFECT=NONE
CLASSIFIER_FINAL_0x32_PAYLOAD_EFFECT=NONE
CLASSIFIER_ADDITIONAL_DEVICE_COMMANDS=NONE
CLASSIFIER_RETRY_OR_REBUILD_EFFECT=NONE
CLASSIFIER_ERROR_RECOVERY_COMMANDS=NONE
```

Questa non è l'affermazione che il sensore accetti ciecamente `0x32`, né che il
classifier sia inutile per sempre. È la conclusione più stretta che, nel
contratto del primo arm, l'esecuzione e il return del classifier non cambiano
alcun comando, payload, tabella, requisito temporale o stato device-visible e
sono perciò causalmente non osservabili dal MCU. Qualità, discriminazione dito,
temperatura, refresh delle basi e fedeltà cache/OEM restano possibili ruoli
futuri del classifier.

Il flag dirty porta, prima del ritorno di `gf_update_all_base`, alla chiamata
condizionale `0x180067f44` (`gf_savebaseTofile`, stringa `goodix.dat`) a
`0x1800697e1`. Il return del salvataggio non governa il final `0x32`, che il
caller invia dopo. Non è osservato alcun cache write dopo quel final nello
stesso path. La cache è persistenza host e fedeltà OEM, non factory state del
sensore; il first-live Linux la tiene disabilitata e non introduce una nuova
persistenza host:

```text
OEM_CACHE_WRITE_BEFORE_FINAL_0x32=CONDITIONAL
OEM_CACHE_WRITE_AFTER_FINAL_0x32=false
OEM_CACHE_WRITE_REQUIRED_FOR_FINAL_0x32=false
OEM_CACHE_WRITE_REQUIRED_FOR_DEVICE_PROGRESS=false
LINUX_FIRST_LIVE_CACHE_WRITE_POLICY=DISABLED
HOST_CACHE_WRITE_COUNT=0
```

Il B0 baseline `0x20` segue una regola diversa: può essere ignorato
semanticamente solo dopo il consumo da parte dello stack TLS che possiede la
sessione. Rimuovere il ciphertext dal transport senza TLS consumption è
fail-closed perché desincronizzerebbe sequence/state. Il corrective sposta il
consumo nel punto corretto: risposta B0 a `0x20` → autenticazione/decryption
tramite la sessione attiva → discard e zeroizzazione best-effort del solo
buffer mutabile → terzo `0x36`. Il finalizer post-stage2 non riceve più il B0 e
non può ritardarne il consumo.

Il core GPL espone un adapter che usa l'esatta `SSLObject` e la stessa input
MemoryBIO già handshaked, senza creare un secondo contesto/server, handshake,
transport o provisioning PSK. La fixture sintetica non biometrica prova una
sessione server, un client, un handshake, il consumo B0 e un secondo record
applicativo sulla medesima sessione, quindi anche la continuità di sequence
numbers/cipher state. La prova resta esclusivamente offline/architectural.

D245 resta evidenza live target-specific che Linux completa il TLS nel ruolo
server con lo stesso secret validato da E4. L'audit del runtime sealed mostra
però che `ProductionReplayBackend.tls_handshake()` conserva l'engine soltanto
in una variabile locale e lo chiude incondizionatamente nel `finally`; non
esiste un oggetto post-handshake esposto al consumer B0. Poiché D259 non può
modificare `src/` o i launcher live, il plumbing reale non è chiuso. Il
plaintext B0 storico D255 resta indisponibile e non è stato richiesto o
decrittato:

```text
BASELINE_B0_TLS_CONSUMPTION_REQUIRED=true
BASELINE_B0_IMAGE_CLASSIFICATION_REQUIRED=false
BASELINE_B0_RASTER_DECODE_REQUIRED=false
HISTORICAL_D255_B0_PLAINTEXT_AVAILABLE=false
FUTURE_LINUX_RUNTIME_TLS_SESSION_PROVEN=true
LIVE_TLS_ROLE=SERVER
LIVE_TLS_TO_B0_ADAPTER_STATUS=UNIMPLEMENTED
SAME_TLS_SESSION_B0_CONSUMPTION=PASS_OFFLINE_ARCHITECTURAL
POST_B0_TLS_SESSION_CONTINUITY=PASS_OFFLINE_ARCHITECTURAL
FUTURE_LINUX_RUNTIME_B0_CONSUMPTION_CAPABILITY=false
```

La zeroizzazione non è promossa oltre quanto Python/OpenSSL consentono:

```text
PLAINTEXT_MUTABLE_BUFFER_BEST_EFFORT_ZEROIZED=true
OPENSSL_INTERNAL_COPY_ZEROIZATION=NOT_PROVEN
PYTHON_IMMUTABLE_TEMP_COPY_ZEROIZATION=NOT_PROVEN
```

Il replay D259 usa per riferimento seed/cache, request e risposte non-B0 D255;
sostituisce soltanto la risposta B0 con un record TLS sintetico della stessa
lunghezza esterna `7726`, perché non pretende il plaintext storico. Il percorso
completo è wire-exact nelle request target:

```text
validated OTP-bound seed
-> 0x36 -> IRQ100 -> 0x50 structurally valid
-> 0x36 -> IRQ100 -> 0x82 native delta PASS
-> 0x20 -> B0 TLS authenticate/decrypt/best-effort mutable-buffer zeroize/discard
-> 0x36 -> IRQ100 -> second native delta PASS
-> no classifier, raster decode or cache write
-> final 0x32 exactly once
```

I timeout restano `36/50/82=500`, `20=2000`, `32=100` ms. Retry, A2/`0x70`,
famiglie device persistenti e cache write sono zero. Un failure resta
`no retry → no recovery speciale → cleanup terminale host-side`; D256 rimane
l'autorità sul terminal stop osservato.

La knowledge boundary distingue ora permanentemente tre domande. Il corpus
locale è esaurito per la fedeltà host OEM esatta, perché mancano ABI/stato
runtime completo del classifier; non è esaurito/bloccante per il contratto
minimo device-visible del classifier, ora confermato meccanicamente. Resta però
un gap software concreto fra il TLS live-proven D245 e il consumer B0: la prova
same-session sintetica non sostituisce il plumbing runtime. Analogamente, cache
fidelity non equivale a factory-preservation, e readiness review non equivale
ad autorizzazione.

```text
OUTCOME=BLOCKED_LIVE_TLS_RUNTIME_ADAPTER_GAP
POST_CLASSIFIER_BRANCH_PROOF=PASS_MECHANICALLY_DERIVED
BRANCH_MATRIX_DERIVATION_MODE=PARSED_DISASSEMBLY_CFG
POST_STAGE2_CLASSIFIER_DEVICE_PROGRESS_REQUIRED=false
POST_STAGE2_CLASSIFIER_FACTORY_PRESERVATION_REQUIRED=false
POST_STAGE2_CLASSIFIER_FIRST_ARM_REQUIRED=false
POST_STAGE2_CLASSIFIER_OEM_HOST_FIDELITY_REQUIRED=true
POST_STAGE2_CLASSIFIER_HOST_PERSISTENCE_REQUIRED=false
CORPUS_EXHAUSTED_FOR_EXACT_OEM_HOST_FIDELITY=true
CORPUS_EXHAUSTED_FOR_MINIMAL_DEVICE_LIVE_CONTRACT=false
MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED=false
FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED=false
FDT_OFFLINE_CANDIDATE_CLOSED=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
```

Il precedente bundle D259 è preservato per provenance ma marcato
`SUPERSEDED_BY_D259_MECHANICAL_PROOF_CORRECTIVE`. Il corrective lascia `src/`
e i launcher D245/D246/D251 byte-identici, non aggiunge backend USB, launcher o
operator kit, non auto-approva una baseline e non autorizza hardware.

## D260: runtime GPL persistente e architecture readiness offline

D260 implementa in `core/` la convergenza architetturale che D259 aveva
lasciato aperta. `core/persistent_runtime.py` possiede per l'intera esecuzione
una sessione transport logica, un `ValidatedSecretBoundary`, un server TLS 1.2
PSK, un bridge B0, il demux misto A0/B0, un `EventSource` separato e la state
machine FDT D259. `core/tls_b0.py` espone ora il lifecycle esplicito:

```text
CREATED -> HANDSHAKING -> ESTABLISHED -> APPLICATION_ACTIVE -> CLOSED
```

Il rehearsal usa esclusivamente un client OpenSSL e un secret sintetici. Il
medesimo boundary object effettua un solo handoff; il server crea un solo
`SSLObject`, registra un solo handshake e non esegue secondo provisioning,
fallback, PSK random o PSK null. La sessione rimane stabilita mentre D4 passa
come A0 plaintext canonico `a00600a6d403000000d3`, una sola volta, con policy
fixed-64 zero-tail, pacing post-TLS 20 ms e timeout 200 ms. D4 non incrementa
il contatore TLS application data. AF/AE e gli A0 FDT restano plaintext; solo
la risposta B0 a `0x20` viene autenticata/decrittata dal medesimo engine e il
buffer mutabile del plaintext sintetico viene scartato e zeroizzato
best-effort. Copie interne OpenSSL e temporanei Python immutabili restano
`NOT_PROVEN` rispetto alla zeroizzazione.

Il bridge handshake prova offline il passaggio `D1 → B0 ClientHello → server
flight B0 → client Finished B0 → ESTABLISHED`. I record B0 host→device
conservano staging fisico fixed-64 e pacing 10 ms D242/D245. D4 conserva il
contratto fisico D246 e AF quello D251. Per `0x36/0x50/0x82/0x20/0x32`, D260
modella framing e timeout logici esatti ma non inventa la tail fisica futura
del backend Linux:

```text
PHYSICAL_SUBMISSION_CONTRACT_STATUS=
  ABSTRACT_OFFLINE_FOR_FDT_A0_WITH_EXACT_D4_AND_B0_TLS_POLICIES
```

Questa incompletezza è compatibile con architecture readiness ma impedisce
operational readiness. ACK sincrono ed evento asincrono non sono collassati:
`RuntimeTransport.receive()` consegna l'ACK e solo dopo
`EventSource.wait_event()` consegna ciascuno dei tre IRQ `0x0100`, touch zero e
raw-base da 12 byte, exactly once.

Il percorso production-shaped continuo passa come singolo runtime object:

```text
D1/B0 TLS handshake
-> retained TLS engine
-> D4 A0 plaintext exactly once
-> AF/AE A0
-> 0x36 ACK -> separate IRQ100 stage0
-> 0x50 NAV
-> 0x36 ACK -> separate IRQ100 stage1
-> 0x82 first native delta PASS
-> 0x20 -> B0 consumed by same TLS engine
-> 0x36 ACK -> separate IRQ100 stage2
-> second native delta PASS
-> classifier/raster/cache zero
-> final 0x32 exactly once
-> one TLS close and one transport cleanup
```

La traccia FDT è esattamente `36,50,36,82,20,36,32`; B0 viene consumato prima
dello stage2. La matrice copre malformed B0 handshake, bad MAC handshake,
timeout TLS, ACK D4 errato, AE malformed, seed invalido, timeout primo `0x36`,
IRQ100 mancante/errato, NAV malformed, primo delta reject, B0 auth failure, B0
ritardato oltre il boundary stage2, secondo delta reject e ACK finale `0x32`
errato. Ogni scenario termina con retry/cache/device-write/A2/`0x70` a zero,
una chiusura TLS e un cleanup transport.

Il runtime D245/D246/D251 e i launcher storici restano byte-identici e
continuano a essere l'autorità dell'evidenza live pregressa. Il nuovo runtime
non è collegato a USB reale, non usa il secret E4 reale, non implementa
privilege/fprintd/marker/baseline/operator kit e non è live-proven. Lo stato
canonico D260 è:

```text
PERSISTENT_TLS_RUNTIME_IMPLEMENTED=true
LEGACY_TLS_ONE_SHOT_LIMITATION_ARCHITECTURALLY_BYPASSED_IN_CORE=true
END_TO_END_OFFLINE_RUNTIME_REHEARSAL=PASS
FAILURE_CONTAINMENT_MATRIX=PASS
MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED=true
FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED=true
FDT_OFFLINE_CANDIDATE_CLOSED=true
READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW=true
READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
NEW_RUNTIME_LIVE_PROVEN=false
```

La successiva review operativa, se autorizzata come step distinto, dovrà
ancora chiudere backend USB del nuovo runtime, physical policy A0 FDT,
privilege model, loading/binding del secret reale, stop/restore fprintd,
single-use marker, baseline live approvata e operator kit. D260 non autorizza
hardware e non prepara quel percorso.

## D261: operational live-readiness candidate offline

D261 implementa il percorso operativo che D260 lasciava intenzionalmente
astratto, ma lo valida soltanto con backend, OS, secret e target sintetici. Il
censimento riproducibile della capture canonica D255 separa per ciascun
controllo lunghezza logica, lunghezza fisica, tail e provenienza. Le submission
OEM FDT sono tutte da 64 byte. Nei comandi `0x36`, `0x50`, `0x82` e `0x20` i
soli byte extra nonzero occupano sempre gli offset fisici `40..45`; la capture
D254 mostra gli stessi offset con valori diversi. Il finale `0x32` D255 ha
invece tail zero e ACK valido. La decisione bounded è:

```text
FDT_A0_PHYSICAL_LENGTH=64
FDT_A0_TAIL_POLICY=ZERO_FILL_OUTSIDE_DECLARED_LOGICAL_FRAME
FDT_A0_RESIDUE_REPLAY=false
0x32_ZERO_TAIL_EVIDENCE=PRIMARY_TARGET_OEM_ACCEPTED
0x36/0x50/0x82/0x20_ZERO_TAIL_EVIDENCE=DETERMINISTIC_CANDIDATE_NOT_LIVE_PROVEN
PRIMARY_FUTURE_LIVE_RISK=FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND
```

`core/cold_start.py` reimplementa nel dominio GPL i fatti comportamentali già
provati da D245/D246 senza importare o modificare il runtime sealed: firmware
A8 esatto, E4 tipizzato e validato, due A2 soltanto nelle posizioni canoniche,
chip `0x82`, OTP A6, `0x70`, quattro DAC `0x80` correlati alla config e config
`0x90` hash-gated. L'OTP ottenuto nella stessa sessione è l'unica identità
accettata da `provide_hash_gated_fdt12()`; mismatch, layout, CRC o hash fermano
prima del primo `0x36`, senza fallback, randomizzazione o write cache.

`core/protected_runtime.py` definisce path root-owned `0600` deterministici.
Il dry-run effettua soltanto `lstat`, distingue `ABSENT` da
`INACCESSIBLE_UNPRIVILEGED`/errore errno e non legge il secret. Il supported
path crea una capability CLI-intent soltanto dopo il parsing dell'esatto flag;
questa abilita preflight e validazione del contenuto protetto ma non USB. Dopo
i gate holder, il manifest e config90 sono letti e validati, quindi la fonte
cache è verificata per hash, layout e CRC; soltanto dopo il PASS di tutto il
materiale non-secret viene costruita e materializzata la boundary secret
reale. Il secret è così l'ultimo contenuto protetto materializzato prima del
marker. Solo dopo tali controlli viene acquisito e fsyncato il marker, che
restituisce una prova opaca usata immediatamente per emettere la distinta
capability Live-I/O accettata dal backend libusb. Lo stesso buffer valida E4
mediante la reference D190 canonica e, solo dopo il match, passa al server TLS;
il cleanup lo azzera best-effort. Funzione Python interna senza capability,
ambiente da solo e backend da solo falliscono prima di marker, secret e libusb.
È un fence contro uso accidentale/path non supportati, non un confine di
sicurezza contro codice arbitrario nel medesimo interprete Python.

La bounded import closure del supported path è derivata in un processo nuovo
dal delta dei moduli repository-local effettivamente caricati e comprende 16
source Python. Oltre a entrypoint e moduli transitivi include i due package
initializer realmente eseguiti, `core/__init__.py` e
`poc/goodix5125/tools/binding_reference/__init__.py`; entrambi appartengono ora
alla tuple hardcoded e il verifier ne rileva il drift rispetto a una baseline
sintetica. Le directory namespace prive di `__init__.py` non sono incluse. Un
harness separato, senza mock che intercettino gli import, usa audit/profile
solo per osservare il subprocess e prova zero accessi USB/protected filesystem,
zero istanziazione o materializzazione secret reale, zero mutazioni fprintd e
zero marker a import-time. Definire e importare il concrete loader è consentito;
il rehearsal offline lo sostituisce esplicitamente tramite Protocol con una
fixture sintetica e non implementa fallback dopo un tentativo reale.

`core/usb_runtime.py` è un adapter libusb lazy e production-shaped per un solo
target `27c6:5125`, interfaccia `0`, OUT `0x01`, IN `0x81`. Richiede cardinalità
esatta e rivalida bus/address/port path prima e dopo ogni OUT. Non espone
detach, reset, clear-halt, reopen, retry o recovery. Un solo
`SharedFrameRouter` possiede fisicamente EP81 e conserva in code separate ACK,
risposte, IRQ `0x0100` e B0 anche quando sono frammentati o coalesciuti. Ogni
phase read usa una sola deadline monotonic assoluta: le completion valide ma
non corrispondenti ricevono solo il tempo residuo e non rinnovano il timeout.
Tredici harness eseguono split/coalescing, buffering incrociato, NAV/B0 grandi,
interleaving, ordine, starvation, deadline e tentativo di secondo reader. Il
transport applica inoltre pacing pre/post della policy fisica e rifiuta frame
buffered inattesi dopo l'ACK terminale `0x32`.

Il launcher `operator_kit/d261-live-fdt-arm-once.sh` accetta soltanto
`--dry-run` oppure l'esatta autorizzazione live. Il default è hard-disabled.
Il ramo live, non eseguito in D261, richiede root derivato da un operatore non
root, full SHA approvato e confronto Git blob-per-blob dell'insieme hardcoded.
La tuple immutabile nel verifier è l'autorità; il JSON fileset è un report
derivato e il verifier include se stesso nel set. Protected root e report
directory reali, non symlink, root-owned e `0700`, più destinazione report
sicura, sono verificati o creati secondo policy prima di fprintd, marker,
secret e USB. Seguono metadata/target, stop fprintd, signal mask e holder
check; manifest, config90 e cache non-secret vengono quindi validati prima del
secret reale. Soltanto dopo la sua materializzazione il marker `O_EXCL` `0600`
viene consumato e abilita la capability Live-I/O. La pubblicazione usa
temporary `0600`, fsync file, replace nella stessa directory e fsync directory;
collisioni/symlink falliscono chiuso e un failure del report finale non può
essere rappresentato come run PASS.

Il rehearsal offline completo attraversa capability CLI-intent, gate
pre-side-effect, validazione protetta, marker, capability Live-I/O e, in una
sola sessione fake,
`cold-start → D1/TLS → D4 → AF/AE → 36,50,36,82,20/B0,36,32` e termina solo
dopo l'ACK arm. Copre split/coalescing, payload grandi, identità USB mutata,
claim failure, mismatch OTP/cache, mismatch E4 e frame extra terminale. La
matrice operativa comprende inoltre baseline errata o modificata, marker stale,
holder esterno, metadati protetti invalidi, failure fprintd/report/cleanup/
restore e mismatch della policy fisica. Tutti i 24 scenari invocano realmente
il gate o il runtime, inclusi due repository Git temporanei reali;
`ASSERTION_ONLY_FAILURE_ROWS=0`. Tutti i failure sono fail-closed con retry,
famiglie persistenti e cache write a zero. I failure config90, manifest e cache
hash/layout/CRC hanno inoltre secret materialization, marker e USB a zero; il
failure di metadata secret ha materializzazione, marker e USB a zero. La suite
repository completa passa `238/238`; nessun raw, OTP, secret o dato biometrico entra nel
bundle.

Riesame metodologico pre-live:

1. rispetto all'ultimo percorso live, cambia il metodo: il nuovo runtime GPL
   conserva cold-start, TLS e FDT nella stessa sessione reale, usa un solo
   reader fisico e sostituisce la tail astratta con una policy per comando
   derivata dal raw;
2. la nuova ipotesi tecnica è che APP12509 accetti la tail zero fixed-64 anche
   per `0x36`, `0x50`, `0x82` e `0x20`, come già osservato direttamente per
   `0x32` e per altri boundary A0;
3. se una futura singola run fallisce nello stesso punto, non si ripete: si
   analizza il comando/tail preciso e si acquisisce nuova evidenza o si cambia
   metodo tecnico, senza creare una replica basata soltanto su pacing,
   packaging o preflight.

Lo stato canonico D261 è:

```text
D261_OUTCOME=READY
D261_OPERATIONAL_EVIDENCE_HARDENING=PASS
D261_END_TO_END_OFFLINE_OPERATIONAL_REHEARSAL=PASS
D261_FAILURE_CONTAINMENT_MATRIX=PASS_EXECUTION_DERIVED
D261_FAILURE_SCENARIO_COUNT=24
D261_FAILURE_SCENARIO_EXECUTED_COUNT=24
D261_ASSERTION_ONLY_FAILURE_ROWS=0
D261_LIVE_CAPABILITY_DEFAULT=0
D261_LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG=false
D261_DIRECT_PYTHON_LIVE_CALL_WITHOUT_CAPABILITY_FAILS_CLOSED=true
D261_SHARED_READER_PHASE_DEADLINE_ENFORCED=true
D261_LIVE_IMPORT_CLOSURE_STATUS=PASS
D261_LIVE_IMPORT_CLOSURE_PATH_COUNT=16
D261_LIVE_IMPORT_CLOSURE_MISSING_PATH_COUNT=0
D261_PACKAGE_INITIALIZERS_EXECUTED_AND_BASELINE_GATED=true
D261_NO_IMPORT_TIME_SIDE_EFFECTS=true
D261_IMPORT_SAFETY_TEST=PASS
D261_NON_SECRET_CONTENT_VALIDATED_BEFORE_SECRET_MATERIALIZATION=true
D261_SECRET_MATERIALIZATION_LAST_PRE_MARKER_PROTECTED_READ=true
D261_OFFLINE_REAL_SECRET_LOADER_INSTANTIATION_COUNT=0
D261_OFFLINE_REAL_SECRET_MATERIALIZATION_COUNT=0
D261_OFFLINE_SECRET_FALLBACK_FROM_REAL_TO_SYNTHETIC=false
D261_APPROVED_LIVE_BASELINE_SHA=e9073a171697bd68dd2debabb851f23d007bf718
D261_OPERATIONAL_LIVE_CRITICAL_FILESET=APPROVED_USER_AI_PM_FULL_SHA
D261_EXACT_APPROVED_LIVE_BASELINE_PRESENT=true
D261_READY_FOR_BASELINE_APPROVAL_REVIEW=false
D261_OPERATIONAL_REVIEW_PENDING_APPROVED_BASELINE=false
D261_READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=true
D261_READY_FOR_FDT_LIVE_REVIEW=true
D261_READY_FOR_FDT_LIVE=false
D261_LIVE_EXECUTION=NOT_PERFORMED
```

## Operazioni read note e limiti

| Operazione | Dominio | Limite |
| --- | --- | --- |
| E4 | selector service di produzione MCU | nessun serializer address+length a 32 bit |
| `0x82` | registri chip/sensore | address LE16 e quantità LE16; non MCU flash |
| A6 | OTP/factory tipizzato | risposta fixed/selective |
| A8 | versione firmware | metadato fisso |
| AE / wire AF | stato MCU | struttura fissa |
| ProductionOperateKey | enum key/state | selector tipizzato, non puntatore |
| F0/F4 | update/check | status; erase/program/reset possibili, nessun raw readback |

Nessuna di queste operazioni può codificare e leggere
`0x080272e0..0x0802b8f4` attraverso un path provato.

## Audit definitivo del readback resident (D230)

`D230_DECISION=D230_NO_SAFE_MEMORY_READ_PATH_EXISTS_IN_CORPUS`

D230 ha censito tutti i 52 request frame della capture disponibile, 20 control
wire A0 distinti, 65 call-site verso i tre builder di trasporto in `gfusb.dll`,
sette classi di superficie USB e tutte le 16 famiglie del dispatcher APP. Non è
stato trovato alcun dataflow:

```text
address MCU host-controlled a 32 bit + length
→ request USB
→ dereference flash device-side
→ byte raw proporzionali nella risposta
```

Le primitive interne di load/copy non sono esposte con source pointer
host-controlled. I path A4/F0/F4 sono maintenance mutante e non forniscono
readback grezzo.

La conclusione è rigorosamente corpus-bounded: non afferma che il dispositivo
non possa mai contenere un comando non documentato. I corpi resident sono
assenti e la prima capture è perduta. Tuttavia nessun builder o request nel
corpus trasporta un indirizzo arbitrario verso quei corpi.

`SAFE_RESIDENT_READBACK_ROUTE_STATUS=EXHAUSTED_IN_LOCAL_CORPUS`

Non creare o raccomandare D231/D232 per altre ricerche statiche della stessa
interfaccia senza nuova evidenza primaria target-specific.

## Current critical boundary

La semantica host-side A2/0x70, il backend USB/TLS, il binding runtime PSK↔E4,
l'orchestratore e l'entrypoint production non sono più blocker offline. D245 ha
provato live su 12509 l'intera catena A8→E4→pre-D1→D1→TLS e ha completato
l'handshake senza retry. D246 ha poi chiuso live il primo confine
post-handshake: il target ha accettato una sola inizializzazione volatile D4
per il receiver APP12509 esatto con ACK `0x01`, e la run si è fermata a
`STOP_AFTER_D4`. A8, E4, TLS e D4 non sono più blocker aperti.

Il boundary A0/AF è stato raggiunto una volta in D250. Il target ha accettato
la submission AF zero-tail e restituito direttamente una A0/AE con checksum
valido e body da 16 byte. La run è terminata nel validator host-side, non per
assenza o malformazione della risposta. Byte 0 non ha semantica positiva
provata; byte 1 bit0 POV valido, bit1 TLS connesso e bit3 locked sono gli usi
OEM verificati, e gli altri bit restano ignoti. Il valore byte0 della run D250
è perduto per gap di osservabilità.

D251 ha chiuso live AF sulla baseline approvata: la singola AE valida con
`byte0=0` ha confermato che il byte è opaco, e `flags=0x02` ha selezionato
fresh-FDT, non D2. Anche il marker D251 è consumato; l'esito non autorizza
retry, secondo D4, secondo AF, FDT o una nuova invocazione.

Il current critical boundary resta offline, ma D255/D256 lo hanno ristretto.
La capture APP12509 prova nella stessa cold attach il cache OTP-bound da 13.520
byte, l'uguaglianza FDT12→primo seed wire, tre `0x36`, cancel senza dito,
re-entry e nuovo `0x32` accettato. D256 prova inoltre che nell'intervallo cancel
non passa traffico target e che, dopo una completion bulk-IN cancellata
host-side, il medesimo device `1:2` continua sugli stessi endpoint senza
abort/reset, descriptor replay, reconfiguration, re-enumeration o restore USB
esplicito. Un restore USB esplicito non è quindi un prerequisito osservato per
la re-entry/re-arm OEM.

Il secondo cancel della stessa capture chiude inoltre il terminal stop
osservabile sul bus. Il nuovo arm frame `214`, ACK `216` e pending IN `217` sono
seguiti da zero packet durante il cancel, poi dalla sola completion cancellata
frame `218`, ultimo frame; per i successivi 491,125998 secondi fino al marker
host finale non viene registrato alcun altro packet. Nessun restore, abort,
reset, reconfiguration o re-enumeration è osservato: il contratto terminal-stop
host/bus è chiuso come quiescenza USB path-bounded.

D257 mantiene chiusi il lifecycle host e il provider cache fail-closed e
riclassifica il vecchio replay come sottosequenza proiettata. D258 chiude la
semantica `0x82` e corregge `0x50`/`0x20` come acquisizioni prima di stage2 con
classificazione soltanto dopo stage2. Il corrective D259 prova meccanicamente
che i return dei due classifier hanno effetto solo su basi/cache host OEM e
nessun riflesso sul contratto device-visible del primo arm; il loro modello
esatto e il plaintext B0 storico D255 non sono blocker del classifier. Il B0
resta obbligatoriamente TLS-consumed subito dopo `0x20`. Questa proprietà e la
continuità del record successivo sono provate offline sulla stessa `SSLObject`,
ma il runtime sealed D245 chiude l'engine a fine handshake e non lo espone.
D260 lascia quel runtime storico invariato e implementa invece nel nuovo core
GPL un coordinator persistente: lo stesso server TLS attraversa D4/AF/FDT A0 e
consuma il B0 baseline prima di stage2. Il rehearsal end-to-end e la matrice
failure passano offline, quindi il gap one-shot è architetturalmente superato,
non live-proven. Il disarm del prior arm, la sua lifetime e lo stato interno
FDT dopo cancel rimangono ignoti
epistemici non bloccanti rispetto al contratto host/bus D256. La TTL generale
del cache resta un'incertezza di successo funzionale, non il solo blocker né
un requisito di factory-preservation.

Il current critical boundary non è più l'implementazione operativa: D261
collega ora adapter USB reale, physical policy FDT zero-tail, privilege model,
binding del secret E4, stop/restore fprintd, marker, verifier della baseline
Git, operator kit e autorizzazione esplicita. Il corrective chiude offline le
prove operative che la prima versione aveva overclaimed: supported entrypoint
unico, capability distinte, gate pre-side-effect, marker post-validazione,
matrice failure execution-derived, deadline reader assoluta e report durable.
La review successiva è chiusa dallo stesso D261: la tuple baseline copre ora
l'intera bounded import closure inclusi i due initializer, l'import è provato
side-effect-free in subprocess pulito e il materiale non-secret viene validato
prima della materializzazione secret. Il full commit SHA
`e9073a171697bd68dd2debabb851f23d007bf718` è ora approvato da Utente e AI-PM
come baseline live-critical immutabile: la governance di readiness è promossa
a review operativa/live. Il boundary immediato era una **AI-PM final risk review**
del bounded fresh-FDT arm sulla baseline approvata; solo dopo tale review, su
nuova autorizzazione hardware esplicita dell'Utente, potrà proseguire un nuovo
step live. L'accettazione target della zero-tail per `0x36/0x50/0x82/0x20`
era il rischio live primario dichiarato, non un fatto già provato; `0x32`
restava provato sul target.

Questa AI-PM final risk review è stata completata e la singola run live
autorizzata è stata eseguita con successo (`PASS_STOP_AFTER_FDT_ARM_ACK`). Sul
target primario `27c6:5125` / firmware `GF_ST411SEC_APP_12509`, lungo il
bounded FDT arm path `0x36,0x50,0x36,0x82,0x20,0x36,0x32`, l'accettazione
zero-tail è ora **live-proven con ACK**, con la seguente tassonomia esplicita
per comando:

```text
0x32 = PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED

0x36 / 0x50 / 0x82 / 0x20 = PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
```

Lo scope resta `27c6:5125` / `GF_ST411SEC_APP_12509` sul bounded FDT arm path.
Il rischio primario D262
`FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND` è pertanto ritirato
per questo target/firmware/path. Non si generalizza ad altri device, firmware,
comandi di controllo, flusso post-finger, `0x22`, enrollment/matching o
operazioni di scrittura persistente; `0x22` e il post-finger image non sono
stati raggiunti. Il marker single-use è consumato (`SECOND_LIVE_ATTEMPT_ALLOWED=false`)
e la stessa run non deve essere ripetuta: il prossimo confine live richiede una
nuova AI-PM review e autorizzazione hardware esplicita dell'Utente. Perciò
`READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW=true`,
`READY_FOR_BASELINE_APPROVAL_REVIEW=false`,
`OPERATIONAL_REVIEW_PENDING_APPROVED_BASELINE=false`,
`READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=false`,
`READY_FOR_FDT_LIVE_REVIEW=false` e `READY_FOR_FDT_LIVE=false`: D262 ha aperto
hardware una sola volta in single-shot e si è chiuso, non autorizzando alcun
passo successivo; tutti i gate READY_FOR_* a qualificazione non avvenuta restano
false. D261 non aveva aperto hardware e non auto-approva una run.

Separatamente, la riproducibilità generale resta limitata dal materiale di
trasporto machine-bound. Il motore TLS Linux è ora verificato anche sul target
D245, ma questa evidenza non rende portabile il materiale né autorizza un nuovo
live.

## Hard Wall

```text
APP mapped start          0x0802c000
A2 target                 0x080272e1
0x70 target               0x0802b8f5
minimum missing interval  0x080272e0..0x0802b8f4
PRE_D1_PATH_CLEARED_FOR_EXACT_OEM_REPLAY  true
DEVICE_RESIDENT_NO_NVM_SIDE_EFFECT_PROVEN false
D246_EXACT_APP12509_D4_NO_NVM_SIDE_EFFECT_PROVEN true
D250_AF_LIVE_BOUNDARY CONSUMED
D250_AF_ZERO_TAIL_DEVICE_ACCEPTANCE LIVE_PROVEN
D250_AF_ZERO_TAIL_STRUCTURAL_AE_RESPONSE LIVE_PROVEN
D250_AF_ZERO_TAIL_OEM_BYTEWISE_EQUIVALENCE NOT_PROVEN
D250_AF_LIVE_STATE_BYTE0_VALUE LOST_BY_OBSERVABILITY_GAP
D250_LIVE_EXECUTION PERFORMED_ONCE
D251_LIVE_RESULT PASS
D251_AF_BOUNDARY LIVE_PROVEN
D251_AF_STATE_BYTE0 0_OPAQUE
D251_AF_STATE_FLAGS 0x02
D251_AF_POV_VALID false
D251_MARKER CONSUMED
FDT_DOWN_TABLE_LIVE_READY false
D253_POST_IRQ2_IMAGE_COMMAND 0x22_DATA_0100
D255_LIVE_CAPTURE SUCCEEDED
D255_CAPTURE_BYTES 27684
D255_CAPTURE_FRAME_COUNT 218
D255_CAPTURE_SHA256 802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c
D255_RECOVERY_RESULT PASS
D255_POSTPROCESS_RESULT PASS
D255_NEW_LIVE_CAPTURE_REQUIRED false
D255_NEW_RUN_REQUIRED false
FUTURE_LIVE_OPERATOR_AUTHORIZATION_REQUIRED true
D256_USBPCAP_LIFECYCLE_AUDIT PASS_COMPLETE_TARGET_PACKET_TIMELINE
D256_CANCEL_TO_REENTRY_DEVICE_CONTINUITY SAME_BUS_DEVICE_AND_BULK_ENDPOINTS
D256_HOST_SIDE_PENDING_BULK_IN_CANCELLATION_OBSERVED true
D256_EXPLICIT_USB_RESTORE_OBSERVED false
D256_ABORT_OR_RESET_OBSERVED false
D256_REENUMERATION_OBSERVED false
D256_REENTRY_WITHOUT_EXPLICIT_USB_RESTORE_PROVEN true
D256_NEW_FDT_ARM_ACCEPTED_ON_REENTRY true
D256_RESTORE_REQUIRED_FOR_REENTRY false
D256_PRIOR_ARM_DISARM_PROVEN false
D256_PRIOR_ARM_LIFETIME_AFTER_CANCEL UNOBSERVED
D256_DEVICE_INTERNAL_FDT_STATE_AFTER_CANCEL UNOBSERVED
D256_TERMINAL_CANCEL_PENDING_BULK_IN_CANCELED true
D256_EXPLICIT_USB_TERMINAL_RESTORE_OBSERVED false
D256_TERMINAL_CANCEL_ABORT_OR_RESET_OBSERVED false
D256_TERMINAL_CANCEL_REENUMERATION_OBSERVED false
D256_POST_TERMINAL_CANCEL_CAPTURE_WINDOW_SECONDS 491.125998
D256_POST_TERMINAL_CANCEL_TARGET_USB_PACKET_COUNT 0
D256_POST_TERMINAL_CANCEL_TOTAL_PACKET_COUNT 0
D256_OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN true
D256_HOST_BUS_TERMINAL_STOP_CONTRACT CLOSED_OBSERVED_PATH_BOUNDED_USB_QUIESCENCE
D256_FACTORY_PERSISTENCE_IMPLICATION NO_NEW_DEVICE_SIDE_CLAIM_FROM_USB_SILENCE
D256_CURRENT_CORPUS_EXHAUSTED_FOR_REENTRY_RESTORE_QUESTION true
D256_CURRENT_CORPUS_EXHAUSTED_FOR_INTERNAL_ARM_LIFETIME_QUESTION true
D256_LIVE_EXECUTION NOT_PERFORMED
D257_SEED_PROVIDER_IMPLEMENTED true
D257_SEED_CACHE_LAYOUT_VALIDATION PASS
D257_SEED_OTP_BINDING_VALIDATION PASS
D257_SEED_CRC_VALIDATION PASS
D257_PROJECTED_FDT_SUBSEQUENCE_REPLAY PASS_HISTORICAL
D257_EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY BLOCKED_DYNAMIC_HOST_GATES_NOT_DERIVABLE_FROM_D255_RAW
D257_EXACT_BOOTSTRAP_OUT_TRACE 36,50,36,82,20,36,32
D257_INTERSTAGE_0x50_OBSERVED true
D257_INTERSTAGE_0x82_OBSERVED true
D257_INTERSTAGE_0x20_OBSERVED true
D257_FIRST_0x36_MAX_ATTEMPTS_PER_AUTHORIZATION 1
D257_FIRST_0x36_COMMAND_TIMEOUT_MS 100
D257_FIRST_0x36_AUTOMATIC_RETRY_COUNT 0
D257_IRQ2_0x22_PATH PASS_EXACTLY_ONCE
D257_FIRST_IMAGE_OFFLINE_CLOSURE PASS_SYNTHETIC_NON_BIOMETRIC_CODEC_FIXTURE
D257_INTERNAL_PRIOR_ARM_STATE NON_BLOCKING_EPISTEMIC_UNKNOWN
D257_NO_SPECIAL_FDT_RECOVERY_COMMAND_POLICY DEFAULT
D257_SEED_FRESHNESS_GENERALIZATION UNPROVEN
D257_CURRENT_CORPUS_EXHAUSTED_FOR_SEED_FRESHNESS_GENERALIZATION true
D257_SAME_ATTACH_SEED_GENERATION_REQUIRED false
D257_PERSISTED_PRE_ATTACH_CACHE_REUSE_PROVEN true
D257_CACHE_MTIME_TO_ATTACH_BEGIN_SECONDS 1626.1975757
D257_CACHE_MTIME_TO_FIRST_0x36_SECONDS 1635.6222000
D257_GENERAL_CACHE_TTL_PROVEN false
D257_SEED_FRESHNESS_FACTORY_PRESERVATION_BLOCKER false
D257_SEED_FRESHNESS_FUNCTIONAL_SUCCESS_RISK true
D257_FDT_OFFLINE_CANDIDATE_CLOSED false
D257_HOST_BUS_LIFECYCLE_READY true
D257_SEED_FRESHNESS_IS_SOLE_LIVE_BLOCKER false
D257_READY_FOR_FDT_LIVE_REVIEW false
D257_READY_FOR_FDT_LIVE false
D257_LIVE_EXECUTION NOT_PERFORMED
D258_TARGET_BOOTSTRAP_SEQUENCE_HASH_GATED true
D258_GATE_0x50_STATUS PARTIAL_STORE_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED
D258_GATE_0x82_STATUS CLOSED_NATIVE_PREDICATE_IMPLEMENTED
D258_GATE_0x20_STATUS PARTIAL_ACQUISITION_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED
D258_D255_B0_DECRYPTION_STATUS INPUT_UNAVAILABLE_WITHOUT_PRIVILEGE
D258_COMMAND_TIMEOUT_POLICY PER_COMMAND_EVIDENCE_BOUNDED
D258_TIMEOUT_0x36_MS 500
D258_TIMEOUT_0x50_MS 500
D258_TIMEOUT_0x82_MS 500
D258_TIMEOUT_0x20_MS 2000
D258_TIMEOUT_0x32_MS 100
D258_CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x50_GATE true
D258_CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x82_GATE true
D258_CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x20_GATE true
D258_PROJECTED_FDT_SUBSEQUENCE_REPLAY PASS_HISTORICAL
D258_EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY BLOCKED
D258_DYNAMIC_HOST_GATES_CLOSED false
D258_FDT_OFFLINE_CANDIDATE_CLOSED false
D258_HOST_BUS_LIFECYCLE_READY true
D258_SEED_FRESHNESS_FACTORY_PRESERVATION_BLOCKER false
D258_READY_FOR_FDT_LIVE_REVIEW false
D258_READY_FOR_FDT_LIVE false
D258_LIVE_EXECUTION NOT_PERFORMED
D259_OUTCOME BLOCKED_LIVE_TLS_RUNTIME_ADAPTER_GAP
D259_POST_CLASSIFIER_BRANCH_PROOF PASS_MECHANICALLY_DERIVED
D259_BRANCH_MATRIX_DERIVATION_MODE PARSED_DISASSEMBLY_CFG
D259_NAV_RETURN_CFG_PROVEN true
D259_IMAGE_RETURN_CFG_PROVEN true
D259_CLASS_A_CLASSIFIER_HOST_ONLY_FOR_FIRST_ARM true
D259_POST_STAGE2_CLASSIFIER_DEVICE_PROGRESS_REQUIRED false
D259_POST_STAGE2_CLASSIFIER_FACTORY_PRESERVATION_REQUIRED false
D259_POST_STAGE2_CLASSIFIER_FIRST_ARM_REQUIRED false
D259_POST_STAGE2_CLASSIFIER_OEM_HOST_FIDELITY_REQUIRED true
D259_POST_STAGE2_CLASSIFIER_HOST_PERSISTENCE_REQUIRED false
D259_NAV_CLASSIFIER_FINAL_0x32_EFFECT NONE
D259_IMAGE_CLASSIFIER_FINAL_0x32_EFFECT NONE
D259_CLASSIFIER_FDT_TABLE_EFFECT NONE
D259_CLASSIFIER_FINAL_0x32_PAYLOAD_EFFECT NONE
D259_CLASSIFIER_ADDITIONAL_DEVICE_COMMANDS NONE
D259_CLASSIFIER_RETRY_OR_REBUILD_EFFECT NONE
D259_CLASSIFIER_ERROR_RECOVERY_COMMANDS NONE
D259_BASELINE_B0_TLS_CONSUMPTION_REQUIRED true
D259_BASELINE_B0_IMAGE_CLASSIFICATION_REQUIRED false
D259_BASELINE_B0_RASTER_DECODE_REQUIRED false
D259_HISTORICAL_D255_B0_PLAINTEXT_AVAILABLE false
D259_FUTURE_LINUX_RUNTIME_TLS_SESSION_PROVEN true
D259_LIVE_TLS_ROLE SERVER
D259_LIVE_TLS_TO_B0_ADAPTER_STATUS UNIMPLEMENTED
D259_B0_CONSUMED_BEFORE_STAGE2 true
D259_TLS_SERVER_SESSION_OBJECT_COUNT 1
D259_TLS_CLIENT_SESSION_OBJECT_COUNT 1
D259_TLS_SERVER_HANDSHAKE_COUNT 1
D259_TLS_APPLICATION_RECORD_CONSUMPTION_COUNT 1
D259_SECOND_SERVER_SESSION_CREATED false
D259_SECOND_PSK_PROVISIONING false
D259_SAME_TLS_SESSION_B0_CONSUMPTION PASS_OFFLINE_ARCHITECTURAL
D259_POST_B0_TLS_SESSION_CONTINUITY PASS_OFFLINE_ARCHITECTURAL
D259_FUTURE_LINUX_RUNTIME_B0_CONSUMPTION_CAPABILITY false
D259_PLAINTEXT_MUTABLE_BUFFER_BEST_EFFORT_ZEROIZED true
D259_OPENSSL_INTERNAL_COPY_ZEROIZATION NOT_PROVEN
D259_PYTHON_IMMUTABLE_TEMP_COPY_ZEROIZATION NOT_PROVEN
D259_SRC_SEALED_UNCHANGED true
D259_LIVE_LAUNCHERS_UNCHANGED true
D259_OEM_CACHE_WRITE_BEFORE_FINAL_0x32 CONDITIONAL
D259_OEM_CACHE_WRITE_AFTER_FINAL_0x32 false
D259_OEM_CACHE_WRITE_REQUIRED_FOR_FINAL_0x32 false
D259_LINUX_FIRST_LIVE_CACHE_WRITE_POLICY DISABLED
D259_CORPUS_EXHAUSTED_FOR_EXACT_OEM_HOST_FIDELITY true
D259_CORPUS_EXHAUSTED_FOR_MINIMAL_DEVICE_LIVE_CONTRACT false
D259_MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED false
D259_FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED false
D259_FDT_OFFLINE_CANDIDATE_CLOSED false
D259_READY_FOR_FDT_LIVE_REVIEW false
D259_READY_FOR_FDT_LIVE false
D259_NO_SPECIAL_FDT_RECOVERY_COMMAND_POLICY DEFAULT
D259_A2_REENTRY_INJECTION 0
D259_0x70_REENTRY_INJECTION 0
D259_HOST_CACHE_WRITE_COUNT 0
D259_REAL_USB_OPEN_COUNT 0
D259_REAL_CAPTURE_COUNT 0
D259_REAL_HARDWARE_ACTION_COUNT 0
D259_REAL_COMMAND_SEND_COUNT 0
D259_PERSISTENT_WRITE_FAMILY_COUNT 0
D259_LIVE_EXECUTION NOT_PERFORMED
D260_PERSISTENT_TLS_RUNTIME_IMPLEMENTED true
D260_TLS_SERVER_SESSION_OBJECT_COUNT 1
D260_TLS_SERVER_HANDSHAKE_COUNT 1
D260_SECOND_SERVER_SESSION_CREATED false
D260_SECOND_PSK_PROVISIONING false
D260_D4_POST_TLS_A0_PLAINTEXT_EXACTLY_ONCE true
D260_D4_TLS_APPLICATION_RECORD_COUNT 0
D260_POST_D4_TLS_ENGINE_RETAINED true
D260_EVENT_SOURCE_CONTRACT_REQUIRED true
D260_IRQ100_EVENT_SEPARATE_FROM_ACK_REQUIRED true
D260_EXACT_FDT_COMMAND_TRACE 36,50,36,82,20,36,32
D260_BASELINE_B0_CONSUMED_BEFORE_STAGE2 true
D260_SAME_TLS_SESSION_B0_CONSUMPTION PASS_OFFLINE_ARCHITECTURAL
D260_SECOND_NATIVE_DELTA_REQUIRED true
D260_CLASSIFIER_CALL_COUNT 0
D260_RASTER_DECODE_COUNT 0
D260_HOST_CACHE_WRITE_COUNT 0
D260_RETRY_COUNT 0
D260_PERSISTENT_WRITE_FAMILY_COUNT 0
D260_PHYSICAL_SUBMISSION_CONTRACT_STATUS ABSTRACT_OFFLINE_FOR_FDT_A0_WITH_EXACT_D4_AND_B0_TLS_POLICIES
D260_END_TO_END_OFFLINE_RUNTIME_REHEARSAL PASS
D260_FAILURE_CONTAINMENT_MATRIX PASS
D260_MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED true
D260_FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED true
D260_FDT_OFFLINE_CANDIDATE_CLOSED true
D260_READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW true
D260_READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW false
D260_READY_FOR_FDT_LIVE_REVIEW false
D260_READY_FOR_FDT_LIVE false
D260_NEW_RUNTIME_LIVE_PROVEN false
D260_REAL_USB_OPEN_COUNT 0
D260_REAL_TLS_TARGET_HANDSHAKE_COUNT 0
D260_REAL_HARDWARE_ACTION_COUNT 0
D261_OUTCOME READY
D261_OPERATIONAL_EVIDENCE_HARDENING PASS
D261_FDT_A0_PHYSICAL_LENGTH 64
D261_FDT_A0_TAIL_POLICY ZERO_FILL_OUTSIDE_DECLARED_LOGICAL_FRAME
D261_FDT_A0_RESIDUE_REPLAY false
D261_FDT_ZERO_TAIL_0x32 PRIMARY_TARGET_OEM_ACCEPTED
D261_FDT_ZERO_TAIL_0x36_0x50_0x82_0x20 UNPROVEN_LIVE_HYPOTHESIS
D261_COLD_START_GPL_RUNTIME_IMPLEMENTED true
D261_REAL_USB_ADAPTER_IMPLEMENTED true
D261_ONE_PHYSICAL_EP81_READER true
D261_REAL_SECRET_BOUNDARY_IMPLEMENTED true
D261_SEED_LIVE_OTP_BINDING_REQUIRED true
D261_LIVE_CAPABILITY_DEFAULT 0
D261_LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG false
D261_SUPPORTED_LIVE_ENTRYPOINT_COUNT 1
D261_DIRECT_PYTHON_LIVE_CALL_WITHOUT_CAPABILITY_FAILS_CLOSED true
D261_CLI_INTENT_CAPABILITY_REQUIRED true
D261_LIVE_IO_CAPABILITY_REQUIRES_MARKER true
D261_MARKER_AFTER_PROTECTED_CONTENT_VALIDATION true
D261_MARKER_IMMEDIATELY_PRECEDES_LIVE_IO_CAPABILITY true
D261_REPORT_DIRECTORY_SAFETY_CHECKED_PRE_SIDE_EFFECT true
D261_PROTECTED_ROOT_SAFETY_CHECKED_PRE_SIDE_EFFECT true
D261_END_TO_END_OFFLINE_OPERATIONAL_REHEARSAL PASS
D261_FAILURE_CONTAINMENT_MATRIX PASS_EXECUTION_DERIVED
D261_FAILURE_SCENARIO_COUNT 24
D261_FAILURE_SCENARIO_EXECUTED_COUNT 24
D261_ASSERTION_ONLY_FAILURE_ROWS 0
D261_SHARED_READER_PHASE_DEADLINE_ENFORCED true
D261_TIMEOUT_RENEWAL_PER_UNMATCHED_FRAME false
D261_SINGLE_READER_DEMUX_EXECUTABLE_EVIDENCE PASS
D261_LIVE_IMPORT_CLOSURE_STATUS PASS
D261_LIVE_IMPORT_CLOSURE_PATH_COUNT 16
D261_LIVE_IMPORT_CLOSURE_MISSING_PATH_COUNT 0
D261_PACKAGE_INITIALIZERS_EXECUTED_AND_BASELINE_GATED true
D261_CORE_INIT_DRIFT_DETECTED true
D261_BINDING_REFERENCE_INIT_DRIFT_DETECTED true
D261_NO_IMPORT_TIME_SIDE_EFFECTS true
D261_IMPORT_SAFETY_TEST PASS
D261_IMPORT_TIME_USB_ATTEMPT_COUNT 0
D261_IMPORT_TIME_PROTECTED_FS_ACCESS_COUNT 0
D261_IMPORT_TIME_SECRET_INSTANTIATION_COUNT 0
D261_IMPORT_TIME_SECRET_MATERIALIZATION_COUNT 0
D261_IMPORT_TIME_FPRINTD_MUTATION_COUNT 0
D261_IMPORT_TIME_MARKER_CREATE_COUNT 0
D261_NON_SECRET_CONTENT_VALIDATED_BEFORE_SECRET_MATERIALIZATION true
D261_SECRET_MATERIALIZATION_LAST_PRE_MARKER_PROTECTED_READ true
D261_OFFLINE_REAL_SECRET_LOADER_INSTANTIATION_COUNT 0
D261_OFFLINE_REAL_SECRET_MATERIALIZATION_COUNT 0
D261_OFFLINE_SECRET_FALLBACK_FROM_REAL_TO_SYNTHETIC false
D261_FULL_TEST_SUITE 238_PASS
D261_LIVE_CRITICAL_PATH_SOURCE HARDCODED_REVIEWED_TUPLE_IN_VERIFIER
D261_LIVE_CRITICAL_FILESET_JSON_ROLE DERIVED_REPORT_NOT_AUTHORITY
D261_APPROVED_LIVE_BASELINE_SHA e9073a171697bd68dd2debabb851f23d007bf718
D261_OPERATIONAL_LIVE_CRITICAL_FILESET APPROVED_USER_AI_PM_FULL_SHA
D261_EXACT_APPROVED_LIVE_BASELINE_PRESENT true
D261_READY_FOR_BASELINE_APPROVAL_REVIEW false
D261_OPERATIONAL_REVIEW_PENDING_APPROVED_BASELINE false
D261_READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW true
D261_READY_FOR_FDT_LIVE_REVIEW true
D261_READY_FOR_FDT_LIVE false
D261_REAL_USB_OPEN_COUNT 0
D261_REAL_SECRET_READ_COUNT 0
D261_REAL_COMMAND_SEND_COUNT 0
D261_FPRINTD_MUTATION_COUNT 0
D261_REAL_SINGLE_USE_MARKER_CREATE_COUNT 0
D261_REAL_HARDWARE_ACTION_COUNT 0
D261_LIVE_EXECUTION NOT_PERFORMED
D262_PRELIVE_OUTCOME READY
D262_PRELIVE_ADVANCEMENT LIVE_EXECUTION_READINESS_REVIEW
D262_PRELIVE_EXECUTION_TARGET STOP_AFTER_FDT_ARM_ACK
D262_PRELIVE_LIVE_CRITICAL_MODIFICATION_COUNT 0
D262_PRELIVE_LIVE_CRITICAL_WORKTREE_MATCH PASS
D262_PRELIVE_D261_OPERATOR_KIT_REUSED true
D262_PRELIVE_DRY_RUN PASS
D262_PRELIVE_DRY_RUN_REAL_USB_OPEN_COUNT 0
D262_PRELIVE_DRY_RUN_REAL_SECRET_READ_COUNT 0
D262_PRELIVE_DRY_RUN_REAL_COMMAND_SEND_COUNT 0
D262_PRELIVE_DRY_RUN_REAL_MARKER_CREATE_COUNT 0
D262_PRELIVE_DRY_RUN_FPRINTD_MUTATION_COUNT 0
D262_PRELIVE_FULL_TEST_SUITE 238_PASS
D262_PRELIVE_READY_FOR_D262_OPERATOR_EXECUTION_REVIEW true
D262_PRELIVE_READY_FOR_D262_OPERATOR_EXECUTION false
D262_PRELIVE_READY_FOR_FDT_LIVE_REVIEW true
D262_PRELIVE_READY_FOR_FDT_LIVE false
D262_PRELIVE_LIVE_EXECUTION NOT_PERFORMED
D262_LIVE_EXECUTION_PERFORMED_ONCE true
D262_LIVE_OUTCOME PASS
D262_LIVE_RESULT PASS_STOP_AFTER_FDT_ARM_ACK
D262_LIVE_PHASE_REACHED STOP_AFTER_FDT_ARM_ACK
D262_LIVE_TARGET_IDENTITY 27c6:5125
D262_LIVE_TARGET_FIRMWARE GF_ST411SEC_APP_12509
D262_APPROVED_BASELINE_SHA e9073a171697bd68dd2debabb851f23d007bf718
D262_LIVE_CRITICAL_FILESET_DIGEST 39d162077156b2af5fdb4b43d4382923006aa44f75e1e44c0fff741709761418
D262_EXACT_FDT_COMMAND_TRACE 0x36,0x50,0x36,0x82,0x20,0x36,0x32
D262_FDT_ARM_BOUNDARY_LIVE_PROVEN true
D262_FDT_ZERO_TAIL_0x32 PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED
D262_FDT_ZERO_TAIL_0x36 PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
D262_FDT_ZERO_TAIL_0x50 PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
D262_FDT_ZERO_TAIL_0x82 PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
D262_FDT_ZERO_TAIL_0x20 PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
D262_PRIMARY_ZERO_TAIL_RISK_RETIRED true
D262_ZERO_TAIL_PROOF_SCOPE PRIMARY_TARGET_27C6_5125_APP_12509_BOUNDED_FDT_ARM_PATH
D262_FINGER_INTERACTION_COUNT 0
D262_RASTER_DECODE_COUNT 0
D262_RETRY_COUNT 0
D262_PERSISTENT_DEVICE_WRITE_COUNT 0
D262_CACHE_WRITE_COUNT 0
D262_HOST_CACHE_WRITE_COUNT 0
D262_A2_SPECIAL_RECOVERY_COUNT 0
D262_0X70_SPECIAL_RECOVERY_COUNT 0
D262_USB_TRANSPORT_SESSION_COUNT 1
D262_TLS_SERVER_SESSION_OBJECT_COUNT 1
D262_TLS_SERVER_HANDSHAKE_COUNT 1
D262_TRANSPORT_REOPEN_AFTER_TLS false
D262_TRANSPORT_CLEANUP_COUNT 1
D262_TLS_CLOSE_COUNT 1
D262_SECOND_SERVER_SESSION_CREATED false
D262_SECOND_PSK_PROVISIONING false
D262_SECRET_BOUNDARY_HANDOFF_COUNT 1
D262_SECRET_BOUNDARY_ZEROIZED true
D262_SECRET_ZEROIZED true
D262_SECRET_LOG_COUNT 0
D262_BASELINE_B0_TLS_CONSUMED true
D262_BASELINE_B0_CONSUMED_BEFORE_STAGE2 true
D262_SECOND_NATIVE_DELTA_PASSED true
D262_FPRINTD_RESTORE_STATUS restored_to_initial_state
D262_SIGNAL_RESTORE_STATUS restored
D262_RUNTIME_STATE CLOSED
D262_SINGLE_USE_MARKER_STATUS claimed_single_use
D262_SECOND_LIVE_ATTEMPT_ALLOWED false
D262_NEXT_LIVE_BOUNDARY_REQUIRES_NEW_AI_PM_REVIEW_AND_EXPLICIT_USER_AUTHORIZATION true
D262_OUTCOME PASS
D262_ADVANCEMENT LIVE_FDT_ARM_BOUNDARY_PROVEN
D262_EXECUTABLE_CLOSURE PASS
D262_READY_FOR_D262_OPERATOR_EXECUTION_REVIEW false
D262_READY_FOR_D262_OPERATOR_EXECUTION false
D262_READY_FOR_FDT_LIVE_REVIEW false
D262_READY_FOR_FDT_LIVE false
D262_CANONICAL_MANUAL_UPDATED true
```

Il corpus sa dove si trovano i receiver ma non contiene i loro corpi. La safety
ristretta D231 deriva dalla convergenza di control flow, dataflow, due versioni
host e wire OEM; non dall'ordine della capture o dalla sola raggiungibilità.

## Evidenza primaria richiesta per riaprire

La via readback si riapre esclusivamente con almeno una delle seguenti fonti:

1. firmware resident/combined 12509 provenance-valid;
2. capture target recuperata/nuova che usa un opcode assente dal census D230;
3. artefatto OEM target-specific che documenta una readback interface;
4. evidenza primaria indipendente equivalente.

La capture definitivamente perduta, se recuperata e contenente un nuovo opcode,
rientrerebbe nel punto 2. “Cercare ancora” nello stesso corpus non è una
condizione di riapertura.

## Implicazione strategica

`NO_NOT_WITH_CURRENT_LOCAL_CORPUS_AND_CONSTRAINTS`

Non esiste oggi una strada tecnicamente concreta e factory-preserving per
estrarre autonomamente dal sensore il resident code mancante. Questo resta vero
anche se D231 consente di implementare e revisionare offline in D232 l'exact OEM
replay senza tale estrazione.

## Stato implementazione Linux

Il repository implementa il codec immagine clean-room, il seam D232, la
reference D190 recuperata, il backend/orchestratore D233, l'entrypoint
production-candidate D235, il consolidamento D238, l'evidenza D239 e la
transizione command→TLS D241, le evidenze E4 D242/D243/D244 e il kit D245 per
la precondizione read-only A8→E4 con continuazione TLS. D245 è ora anche una
run live TLS riuscita; D246 ha aggiunto ed eseguito live il solo D4 volatile con
stop immediato, completando il percorso implementato fino a quel boundary. Le
sorgenti sono state ripristinate e sealed dopo la run. L'implementazione storica include ABI libusb esatta e TLS OpenSSL, ma non
costituisce ancora un driver libfprint pronto. D249 aggiunge
`core/post_d4.py`, GPL-2.0-or-later e privo di backend USB: framing/parsing
fail-closed, AF, demux A0 + byte-stream applicativo B0 già decifrato, builder/eventi
FDT, due state path bounded fino a `FIRST_IMAGE_RECEIVED` e delega diretta al
codec immagine locale canonico. L'allowlist
rende E0/A4/F0/F4 e le famiglie provisioning/firmware irraggiungibili per
costruzione. Il record immagine noto è di 7684 byte:
7680 byte packed-12 più CRC-32/MPEG-2, convertito in raster u16 `80x64` con
transpose.

D250 aggiunge il terminale AF-only, la patch continuation sopra la catena
D245→D246 e la matrice avversaria. Il primo bundle aveva un launcher invocabile
soltanto in dry-run; la correzione same-step aggiunge il ramo live hard-gated,
il namespace/marker D250, il preflight specifico e il verifier Git del
live-critical set. Il set include launcher, patch chain, preflight/helper, core
AF, sorgenti backend/entrypoint, PE canonico e dipendenze transitive che possono
influire sul path sensor-reaching; manuale, report, bundle e test offline non
sono pin-nati. Una fixture Git prova `APPROVED` pulito e `STALE` mutando ciascun
file del set senza consultare lo staging index. Il codice sorgente USB storico
resta sealed nel repository; patch apply/reverse e hash dimostrano ripristino
byte-identico. Il dry-run reale passa dalla root e da cwd esterno. Questa è
executable closure offline del percorso operatore live-capable, non esecuzione
hardware né approvazione del commit live.

D251 mantiene invariato quel wire path e aggiunge una patch continuation
successiva che rimuove esclusivamente il gate `byte0 == 1`, rinomina il campo
opaco e corregge response count/classificazione/telemetria. Il launcher usa il
nuovo marker `d251-operator-invocation.marker` e la directory `d251-results`,
tratta il marker D250 come storico benigno ma consumato, applica
D245→D246→D250→D251 e ripristina le sorgenti sealed byte-exact. La matrice
offline copre byte0 `1`, `0` e `2`, failure strutturali, timeout, ACK inatteso,
completion ambigua, duplicati e fence post-AF. Quel launcher è stato poi
eseguito una volta sulla baseline approvata e ha chiuso AF con `byte0=0`,
`flags=0x02`, stop terminale e restore completo; il marker è consumato.

D252 non aggiunge runtime USB né operator kit. Aggiunge soltanto un audit
offline GPL hash-gated della capture, la decisione strutturata e il report
step-local. Il modello D249 `IRQ2→0x20` resta storico e viene esplicitamente
marcato non wire-exact rispetto al target `IRQ2→0x22`; non è stato promosso un
nuovo percorso perché tabella fresh e restore non sono entrambi chiusi.

D253 corregge soltanto il core GPL offline corrente e i test: la state machine
usa `IRQ2→0x22`, conserva `0x20` come builder baseline distinto e applica un
fence single-shot prima del secondo comando. L'audit/report/decisione sono
step-local; non esistono backend USB aggiunti, persistenza host, live kit o
autorizzazione hardware. Bootstrap seed, contratto fisico `0x36` e restore
restano bloccanti.

D254 aggiunge soltanto parser e derivati sanitizzati hash-gated. Clone, WBDI,
ZIP e PCAP esterni restano fuori dal repository; non sono stati importati
codice runtime, secret, OTP, immagini o payload biometrici. La corroborazione
esterna non modifica guardrail, non crea un backend/launcher e non autorizza
hardware. D254 lasciava seed APP12509 iniziale e restore no-finger bloccanti;
D255/D256 hanno poi provato la correlazione target cache→seed e la re-entry
senza restore USB esplicito, restringendo ma non chiudendo causalità/freschezza,
disarm e lifetime interna. Il corrective D256 chiude invece il distinto
terminal-stop host/bus come quiescenza USB path-bounded.

D255 ha aggiunto il kit PowerShell GPL e il postprocessor GPL offline, poi ha
acquisito la capture APP12509 definitiva e ne ha recuperato offline la
finalizzazione. Il raw canonico da 27.684 byte/218 frame prova cold attach,
bootstrap, zero finger, cancel e re-entry; non è richiesta una nuova run D255.
Le revisioni e i failure pre-attach precedenti restano provenance storica nella
sezione D255, non stato corrente dell'implementazione.

D256 aggiunge soltanto l'audit GPL offline e derivati sanitizzati: timeline
CSV/MD completa dei packet target, decisione lifecycle, test minimi e report.
Non modifica il runtime live-critical, il core FDT, fprintd o un operator kit.
Il nuovo modello corrente ammette re-entry e re-arm senza restore USB esplicito
osservato e chiude separatamente il terminal-stop host/bus come cancellazione
della bulk-IN pendente più quiescenza USB fino alla fine della capture. Il
bundle D256 corrective sostituisce il precedente artefatto D256 ed esclude raw
USB, cache, DLL, firmware, OTP, PSK e biometria.

D257 aggiunge `core/fdt_lifecycle.py`, `core/fdt_seed.py`, l'integrazione
observer opzionale in `core/post_d4.py`, test e replay offline. Il corrective
aggiunge l'audit esatto del raw e il candidate ordinato
`36,50,36,82,20,36,32`, con gate dinamici espliciti e failure containment
single-shot sul primo `0x36`. Il provider accetta solo cache esplicita valida,
OTP-bound e read-only; cancel/re-entry/terminal-stop restano host-only e
recovery speciali/famiglie persistenti restano vietate per costruzione. Il
vecchio replay è una sottosequenza proiettata storica; l'esatto resta bloccato
sui predicati NAV/delta/baseline non derivabili. La chiusura separata
IRQ2→`0x22`→prima immagine usa una fixture sintetica non biometrica. Non sono
stati aggiunti backend USB, launcher, baseline approvata o operator kit, e il
live resta non autorizzato.

D258 estende soltanto il core e gli audit offline: preserva NAV/B0 come input
runtime, implementa il predicate target `0x82`, sposta correttamente i
classificatori dopo stage2 e introduce timeout per comando. L'audit statico e
il replay sono hash-gated e non esportano raw, OTP, cache, DLL, secret o raster.
Storicamente D258 lasciava il final `0x32` irraggiungibile finché entrambi i
classificatori post-stage2 non fossero riproducibili; D259 supera precisamente
questa conclusione per branch audit causale, senza retro-modificare gli
artefatti D258.

D259 aggiunge il consumer B0 TLS post-handshake riutilizzabile in `core/`, il
finalizer del contratto minimo, matrici branch/wire/recovery/cache hash-gated,
replay D255-by-reference e test OpenSSL con secret/plaintext sintetici non
biometrici. La compatibilità D258 del finalizer host-semantico storico resta
testata, mentre il nuovo path minimo conserva B0 TLS consumption e due delta
native ma ha contatori classifier, raster e cache a zero. Nessun dato storico
B0 è decrittato o esportato. Non sono stati aggiunti backend USB, launcher,
operator kit, baseline live approvata o autorizzazione hardware.

D260 aggiunge `core/runtime_transport.py` e `core/persistent_runtime.py` ed
estende il TLS e lifecycle FDT esistenti senza toccare `src/`. Il nuovo core
separa framing logico, policy fisica ed eventi asincroni; conserva un solo
server TLS oltre l'handshake, lascia D4/AF/FDT come A0 plaintext e inoltra il
solo B0 baseline allo stesso engine. Il rehearsal sintetico production-shaped
copre l'intera sessione e 15 failure terminali. D4 e B0 hanno policy fisiche
evidence-backed; gli A0 FDT restano `ABSTRACT_LOGICAL_ONLY`. Questa è
executable closure del runtime offline e architecture readiness, non un
backend USB, un path operatore o una readiness live.

D261 aggiunge `core/cold_start.py`, `core/protected_runtime.py` e
`core/usb_runtime.py`, rende operativa la policy FDT fixed-64 zero-tail nel
coordinator e aggiunge entrypoint e launcher D261. Il live-critical set è
hardcoded e verificato sia contro la working tree sia contro ogni blob di un
full commit SHA esternamente approvato; il riferimento architetturale D260 è
letto dal commit storico, non da report rigenerabili nella working tree. Il
corrective mantiene la tuple hardcoded come autorità e riclassifica il JSON
fileset come report derivato; il verifier include se stesso. Separa capability
CLI-intent e Live-I/O, sposta materiale protetto prima del marker, anticipa i
gate delle directory, rende assoluta la deadline del shared reader e rende
execution-derived matrici failure/demux e safety del report durable. Il
corrective finale completa inoltre la tuple con i due package initializer,
prova import purity in un subprocess nuovo e impone manifest/config/cache
non-secret prima del secret. Il dry-run reale è cwd-independent, non legge il
secret e non apre USB; il rehearsal usa soltanto fixture sintetiche iniettate e
non istanzia il real loader. La baseline live-critical
`e9073a171697bd68dd2debabb851f23d007bf718` è ora approvata da Utente e AI-PM
(EXACT_APPROVED_LIVE_BASELINE_PRESENT=true), promuovendo la readiness a review
operativa/live senza autorizzare hardware (READY_FOR_FDT_LIVE=false). Il
precedente bundle D261 resta preservato ma è
`SUPERSEDED_BY_D261_OPERATIONAL_EVIDENCE_HARDENING_CORRECTIVE`.

## D262: fresh-FDT arm execution-readiness review offline

D262 esegue una **final execution-readiness review offline** del bounded fresh-FDT arm
usando il candidate D261 già approvato, senza modificare alcun file live-critical e
senza hardware. La baseline live-critical immutabile rimane
`e9073a171697bd68dd2debabb851f23d007bf718` (sha completo approvato da Utente e AI-PM).

Il live path futuro validato è:

```text
A8
→ E4
→ exact cold-start pre-D1
→ D1
→ TLS 1.2 PSK handshake
→ D4 plaintext A0
→ AF / AE
→ fresh FDT:
   0x36 stage0 → ACK → IRQ 0x0100 → 0x50 → ACK + response
   → 0x36 stage1 → ACK → IRQ 0x0100 → 0x82 → ACK + response
   → 0x20 → ACK → B0 baseline on SAME retained TLS session
   → authenticate/decrypt/consume B0
   → 0x36 stage2 → ACK → IRQ 0x0100 → 0x32 → ACK
→ STOP_AFTER_FDT_ARM_ACK
```

Il candidate riutilizza il kit operatore D261
(`operator_kit/d261-live-fdt-arm-once.sh` + `tools/d261_live_fdt_arm_once.py`) con il
ramo `--dry-run` e con cwd realistico (repo root). `D262_LIVE_CRITICAL_MODIFICATION_COUNT=0`:
nessun file del live-critical set D261 è stato toccato. Il verifier D261 conferma che
TUTTI i 17 blob del set sono byte-identici ai blob del commit di baseline. Nessun nuovo
runtime/launcher D262 è stato creato.

Verifiche eseguite in D262 (tutte offline, zero hardware):

```text
D261_APPROVED_LIVE_BASELINE_SHA = e9073a171697bd68dd2debabb851f23d007bf718
D261_APPROVED_BASELINE_RESOLVES = true
D261_LIVE_CRITICAL_WORKTREE_MATCH = PASS
D261_LIVE_CRITICAL_MISMATCH_COUNT = 0
D262_LIVE_CRITICAL_MODIFICATION_COUNT = 0
D262_D261_OPERATOR_KIT_REUSED = true
D262_DRY_RUN = PASS
D262_DRY_RUN_REAL_USB_OPEN_COUNT = 0
D262_DRY_RUN_REAL_SECRET_READ_COUNT = 0
D262_DRY_RUN_REAL_COMMAND_SEND_COUNT = 0
D262_DRY_RUN_REAL_MARKER_CREATE_COUNT = 0
D262_DRY_RUN_FPRINTD_MUTATION_COUNT = 0
D262_EXECUTION_TARGET = STOP_AFTER_FDT_ARM_ACK
D262_EXACT_FDT_COMMAND_TRACE = 0x36,0x50,0x36,0x82,0x20,0x36,0x32
D262_RETRY_COUNT = 0
D262_AUTOMATIC_RETRY_COUNT = 0
D262_AUTOMATIC_RECOVERY_COMMAND_COUNT = 0
D262_PERSISTENT_WRITE_FAMILY_COUNT = 0
COMMAND_0X22_REACHABLE = false
POST_FINGER_IMAGE_REACHABLE = false
ENROLLMENT_REACHABLE = false
MATCHING_REACHABLE = false
FINGER_INTERACTION_REQUIRED = false
FINGER_INTERACTION_ALLOWED = false
IRQ_FINGER_DOWN_REQUIRED = false
A2_0X70_RECOVERY_AFTER_FDT_FAILURE = forbidden
PHYSICAL_USB_OUT_LENGTH = 64
FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND = 0x36/0x50/0x82/0x20
PRIMARY_FUTURE_LIVE_RISK = FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND
```

Questo blocco descrive lo stato offline pre-live della readiness review. Dopo
l'esecuzione live una tantum, il rischio `FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND`
è **ritirato** per `27c6:5125` / `GF_ST411SEC_APP_12509` sul bounded FDT arm path:
`0x36/0x50/0x82/0x20` sono ora `PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED`;
`0x32` resta `PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED`
(v. sezione "D262: esecuzione live una tantum e closure" e Hard Wall).

Il rehearsal end-to-end offline (238 test suite PASS) conferma che il runtime
giunge solo a `STOP_AFTER_FDT_ARM_ACK` dopo il terzo `0x36`/IRQ `0x0100` e l'ACK finale
`0x32`, con una sola sessione TLS, un solo server, un solo handshake, zero retry,
zero famiglie persistenti, zero A2/`0x70` di recovery, secret zeroizzato e fprintd
ripristinato. Il dry-run è cwd-independent, non legge il secret e non apre USB;
l'import safety dimostra zero side-effect a import-time in un subprocess non
privilegiato (16 moduli Python, closure 16/16). Il live-critical set è verificato
blob-per-blob contro la baseline approvata.

La decisione corrente restava invariata: `READY_FOR_D262_OPERATOR_EXECUTION_REVIEW=true`,
`READY_FOR_D262_OPERATOR_EXECUTION=false`, `READY_FOR_FDT_LIVE=false`. D262 non aveva
ancora aperto hardware, non aveva letto secret reale, non aveva aperto USB reale, non
aveva creato marker reale e non aveva tolto fprintd. La prossima azione era esclusivamente
la review AI-PM del bundle D262 e la decisione/autorizzazione live esplicita dell'Utente,
con esecuzione terminale da eseguire manualmente dall'operatore su base single-shot.

### D262: esecuzione live una tantum e closure del confine fresh-FDT arm

La review AI-PM è stata completata e la run è stata eseguita una sola volta (single-shot)
e si è chiusa con `PASS_STOP_AFTER_FDT_ARM_ACK`. La prova primaria del rapporto operatore
(recuperato read-only da `/var/lib/goodix-5125-poc/d261-results/d261-final.json`) è
riprodotta fedelmente negli artefatti `analysis/D262/D262_live_fdt_arm_result.json`,
`D262_post_live_closure_report.md` e `D262_post_live_decision.json`.

Risultato live (target `27c6:5125`, firmware `GF_ST411SEC_APP_12509`, baseline immutabile
`e9073a171697bd68dd2debabb851f23d007bf718`, live-critical fileset digest
`39d162077156b2af5fdb4b43d4382923006aa44f75e1e44c0fff741709761418`):

```text
D262_LIVE_ATTEMPT = PASS
D262_LIVE_RESULT = PASS_STOP_AFTER_FDT_ARM_ACK
PHASE_REACHED = STOP_AFTER_FDT_ARM_ACK
EXACT_FDT_COMMAND_TRACE = 0x36,0x50,0x36,0x82,0x20,0x36,0x32
FDT_ARM_BOUNDARY_LIVE_PROVEN = true

FINGER_INTERACTION_COUNT = 0
RASTER_DECODE_COUNT = 0
RETRY_COUNT = 0
PERSISTENT_DEVICE_WRITE_COUNT = 0
CACHE_WRITE_COUNT = 0
HOST_CACHE_WRITE_COUNT = 0
A2_SPECIAL_RECOVERY_COUNT = 0
0X70_SPECIAL_RECOVERY_COUNT = 0

USB_TRANSPORT_SESSION_COUNT = 1
TLS_SERVER_SESSION_OBJECT_COUNT = 1
TLS_SERVER_HANDSHAKE_COUNT = 1
TRANSPORT_REOPEN_AFTER_TLS = false
TRANSPORT_CLEANUP_COUNT = 1
TLS_CLOSE_COUNT = 1

SECOND_SERVER_SESSION_CREATED = false
SECOND_PSK_PROVISIONING = false
SECRET_BOUNDARY_HANDOFF_COUNT = 1
SECRET_BOUNDARY_ZEROIZED = true
SECRET_ZEROIZED = true
SECRET_LOG_COUNT = 0

BASELINE_B0_TLS_CONSUMED = true
BASELINE_B0_CONSUMED_BEFORE_STAGE2 = true
SECOND_NATIVE_DELTA_PASSED = true

FPRINTD_RESTORE_STATUS = restored_to_initial_state
SIGNAL_RESTORE_STATUS = restored
RUNTIME_STATE = CLOSED

SINGLE_USE_MARKER_STATUS = claimed_single_use
SECOND_LIVE_ATTEMPT_ALLOWED = false
```

La traccia FDT esatta è stata accettata dal target primario con ACK. Il rischio zero-tail
per `0x36/0x50/0x82/0x20` passa da `UNPROVEN_LIVE_HYPOTHESIS` a
`PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED`; `0x32` resta `PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED`.
Lo scope della prova è limitato a `27c6:5125` / `GF_ST411SEC_APP_12509` sul bounded FDT arm
path. Non si generalizza ad altri device, firmware, comandi di controllo, flusso post-finger,
`0x22`, enrollment/matching o scritture persistenti. Nessuna interazione dito, nessun retry,
nessuna scrittura persistente/cache, nessun recovery A2/`0x70`, un'unica sessione USB e un
solo handshake/server TLS, B0 consumato sulla stessa sessione TLS prima di stage2, secret
zeroizzato e non loggato, fprintd e segnale ripristinati, runtime chiuso.

`D262_PRIMARY_ZERO_TAIL_RISK_RETIRED=true`; `D262_ZERO_TAIL_PROOF_SCOPE=
PRIMARY_TARGET_27C6_5125_APP_12509_BOUNDED_FDT_ARM_PATH`. Il marker single-use è consumato e
la stessa run non deve essere ripetuta: il prossimo confine live richiede nuova AI-PM review
e autorizzazione hardware esplicita dell'Utente. I vincoli factory-preserving e di
compatibilità Windows restano integrali. Lo stato massimo è `OUTCOME=PASS`,
`ADVANCEMENT=LIVE_FDT_ARM_BOUNDARY_PROVEN`, `EXECUTABLE_CLOSURE=PASS`; i flag `READY_FOR_*`
restano false perché D262 è già eseguito e chiuso, non perché D262 sia fallito.

## D263: post-arm order e policy fisica `0x22` (sottostep 01)

D263/01 ricostruisce e chiude, con evidenza primaria target-specific, il tratto
`final 0x32 → IRQ 0x0002 → 0x22 [01 00] → first image` e ne classifica la
policy fisica USB di `0x22`. Esecuzione OFFLINE, strictly no-USB/no-sudo/no-secret.

La capture primaria è `analysis/D230/work/GoodixExport/rilevamento.pcapng`
(`GF_ST411SEC_APP_12509`, SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`), hash-gated.
La capture D255 (`VALID_ZERO_FINGER`) **non** contiene il sottoalbero
post-arm (`FINGER_DOWN_IRQ_COUNT=0`, `POST_IRQ2_0x22_COUNT=0`); pertanto il
tratto è derivato da `rilevamento.pcapng`, non da D255. Issue #63 (21/21 IRQ2→
`0x22`) resta solo corroborazione esterna, non autorità primaria APP12509.

Ordine osservato (indici pacchetto zero-based):

```text
0x32 arm  OUT@220 / ACK@223 echo 0x32 status 0x01
IRQ finger-down  IN@225  value 0x0002  wrapper 3f00d500ee00c800ba00c500d200
0x22  OUT@227  body 01 00  logical A0=10  physical OUT=64
0x22  ACK@229  echo 0x22 status 0x01
first image  IN@231  outer 0xB0  TLS(17 03 03)  size 7726
subtree: 0x34@233 → IRQ 0x0200@237 → 0x20[01 00]@238 → 2a immagine B0/TLS@243
         → 0x50@244 → … → final 0x32@251 / ACK@253
```

Derivazioni meccaniche `0x22`: body `01 00`; lunghezza logica A0 = **10**;
lunghezza fisica OUT = **64**; 54 byte fuori frame; unici 6 non-zero a offset
fisici **40–45** = `cb f2 e2 be fb 7f` (staging residue, identica a `0x36`/`0x20`,
non payload). ACK echo `0x22`/status `0x01`, subito dopo l'OUT e prima della
prima immagine. Prima immagine: outer `0xB0`, **TLS** (`17 03 03`), 7726 byte;
nessun frame A0 "immagine" la precede. Occorrenze `0x22` nel primary corpus:
**1** OUT (`rilevamento.pcapng`@227), 0 IN; D255 = 0; Issue#63 = 21 (esterno).

`MINIMUM_CAUSAL_REQUIREMENT`: la capture prova l'**ordine**
`0x32(arm,ACK) → IRQ0x0002 → 0x22[01 00](ACK) → first image`; **non** prova
che `0x22` sia l'unico comando necessario né che l'IRQ finger-down lo richieda
causalmente (osservato ≠ causale).

**Taxonomy `0x22` = `PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY`.** Il post-arm order,
ACK/echo/status e la policy fisica fixed-64 sono direttamente osservati nella
capture primaria APP12509. Il live proof D262 copre **solo** il bounded FDT arm
(`0x36,0x50,0x36,0x82,0x20,0x36,0x32`, `STOP_AFTER_FDT_ARM_ACK`) e **non**
raggiunge il sottoalbero finger-down/`0x22`/immagine; dunque `0x22` NON è
live-proven/accepted. Il modello Phase 2
`logical exact A0 → physical fixed64 → deterministic zero-fill outside declared length`
è **confermato** sul primary (`rilevamento.pcapng`, già hash-gated).

Artefatti `analysis/D263/`: `d263_01_0x22_evidence_audit.py`,
`D263_01_post_arm_order.json`, `D263_01_0x22_physical_policy.json`,
`D263_01_report.md`, `D263_workflow_state.json`. Nessun ZIP in 01.

### D263/02: retained TLS e pipeline first-image (sottostep 02)

Audit OFFLINE dell'architettura esistente per
`encrypted first-image B0 -> retained TLS -> Goodix payload -> image record -> CRC -> packed12 -> 80x64`,
senza modifiche runtime. Esito `PASS_AUDIT_NOT_BLOCKED`.

Retained TLS: `PersistentRuntimeCoordinator` crea **una** sola
`Tls12PskServerSession` (`server_session_object_count=1`,
`psk_context_provisioning_count=1`, `handshake_count=1`); l'adapter
`MemoryBioApplicationSessionAdapter` può consumare più application
record sulla stessa sessione retainita (baseline B0 = record #1). La stessa
sessione può quindi teoricamente trasportare anche il primo B0 immagine
(IRQ2 → 0x22 → first-image). Tuttavia `run()` si ferma a `machine.arm(ts16)` e
il `finally` chiude TLS prima di qualsiasi post-arm: la fase post-arm non è
cablata. Chi decripta B0: `B0ApplicationConsumer.consume`
(`core/tls_b0.py:287`); chi parse l'immagine:
`parse_image_payload`→`decode_image_record`→`src/goodix5125_cleanroom.decode_record`
(servono i byte decriptati). `FdtLifecycle` ha già gli stati/metodi
`FDT_ARMED_WAIT`, `FIRST_IMAGE_RECEIVED`, `post_irq2_image_command`,
`first_image_received`, ma il coordinator/macchina di produzione non li
invoca: la transizione terminale `FDT_ARMED_WAIT → FIRST_IMAGE_RECEIVED` è assente.
Nessun redesign TLS/transport richiesto (target: ONE USB/TLS session, ONE
handshake, ONE secret boundary, ZERO second PSK/reopen è già soddisfatto).

Pipeline immagine: codec canonico **unico** in `src/goodix5125_cleanroom.py`
(packed12, `RECORD_BYTES=7684`, `SAMPLE_COUNT=5120`, raster 80×64, CRC-32/MPEG-2
fail-closed). `decode_image_record` è solo wrapper. Nessun decoder duplicato.
Test esistenti: `test_cleanroom.py`, `test_d249_post_d4.py`,
`test_d257_fdt_candidate.py` (tutti fixture sintetiche). `FIRST_IMAGE_RECEIVED`
è raggiunto solo da `FirstImageMachine` (offline/test), non dal coordinator.

Artefatti `analysis/D263/`: `D263_02_retained_tls_map.json`,
`D263_02_first_image_pipeline.json`, `D263_02_runtime_gap_report.md`. Nessun ZIP.

### D263/03: terminal stop dopo la first image e gate Phase 1 (sottostep 03)

OFFLINE, no live, no patch runtime. Confronto con il ciclo positivo primario
(`rilevamento.pcapng`, in `D263_workflow_state.observed_order`): lo stack
Windows dopo la prima immagine invia `0x34` (arm finger-up, manuale 170-171) →
`IRQ 0x0200` → `0x20` (seconda immagine) → `0x32` re-arm. Questo è
multi-enrollment e **non** prova che `0x34`/`0x20`/re-arm siano richiesti per
uno stop host dopo la prima immagine.

Candidato terminale D263/03:
`0x32 → IRQ 0x0002 → 0x22 → first image → HOST/TLS/USB CLEANUP → STOP`,
senza `0x34`, `0x20`, re-arm, A2, `0x70`, reset, retry, comandi persistenti.

Host cleanup (VERIFICATO fattibile/implementato): cancel pending receive
(D255/D256 quiescenza bus: pending IN cancellato a frame 218, zero packet
residui), TLS close (`core/persistent_runtime.py` finally), USB release/close,
restore `fprintd` exactly-once (manuale 912-928, 1377-1387), nessun comando
Goodix extra (D255/D256: intervallo cancel senza packet target).

Device internal state (UNKNOWN per taxonomy): FDT/finger post-image non noto
(D252 BLOCKED); `0x34` osservato solo come arm finger-up, necessità non provata;
tolleranza disconnect device-side non osservata; recovery cold start INFERITO OK
(D256: nuovo `0x32` accettato senza restore USB); restore device-side non
osservato, A2/`0x70` NON sono restore FDT.

Classificazione: `FIRST_IMAGE_TERMINAL_STOP=EVIDENCE_SUPPORTED_BUT_DEVICE_INTERNAL_STATE_UNKNOWN`.
`D263_PHASE1_READY_FOR_PHASE2_OFFLINE_RUNTIME_INTEGRATION=true`: autorizza solo
design/implementazione **OFFLINE** del candidato bounded (cablare path post-arm
first-image su TLS retainita + cleanup host esattamente-once + STOP), NON live
review né live execution. Baseline D262 `e9073a17...` rispettata, non regredita.

Artefatti `analysis/D263/`: `D263_03_terminal_boundary_evidence.json`,
`D263_03_terminal_boundary_decision.json`, `D263_03_phase1_decision.json`,
`D263_03_report.md`. Nessun ZIP.

### D263/04: Phase 2 design contract e patch plan (sottostep 04, design-only)

Gate Phase 2 `READY` (`D263_PHASE1_READY…=true`). Nessuna patch runtime in
04. Contratto minimo: `D262 path → arm 0x32 ACK → bounded wait IRQ 0x0002 →
exactly one 0x22 [01 00] → retained TLS receives first B0 → parser/codec
canonico valida+decodifica → FIRST_IMAGE_RECEIVED → bounded host-only terminal
cleanup → STOP`. Invarianti: one USB/TLS session+handshake, zero second
secret/USB reopen/retry/A2/`0x70`/`0x34`/`0x20`-post/re-arm/persistent-write,
first-image bytes non persistiti (plaintext azzerato, raster solo in memoria),
fail-closed su mismatch.

Primitive riusate (nessun duplicato): `build_finger_image` (post_d4.py:257),
`parse_fdt_event` (irq==2, post_d4.py:273),
`application_session.consume_application_record` (tls_b0.py:252),
`parse_image_payload`/`decode_image_record` (post_d4.py:336/347 → codec
canonico), `lifecycle.post_irq2_image_command`/`first_image_received`/
`cancel_pending_receive`/`terminal_stop` (fdt_lifecycle.py:222/230/234/251).
Il gap era solo in `PersistentRuntimeCoordinator.run()` che si ferma a
`machine.arm(ts16)` (persistent_runtime.py:232).

Patch plan (step 05/06, ciascuno <15 min):
- **Step 05**: `core/runtime_transport.py` (aggiungere `0x22` agli allowlist
  `fdt_a0_policy`/`operational_fdt_a0_policy`); `core/fdt_lifecycle.py`
  (aggiungere `0x22` a `COMMAND_TIMEOUT_MS`; `cancel_pending_receive` accetta
  anche `FIRST_IMAGE_RECEIVED`). Rischio basso.
- **Step 06**: `core/persistent_runtime.py` (orchestrazione post-arm: wait
  IRQ2 → un `0x22` → receive B0 TLS → decode → `first_image_received` →
  `cancel_pending_receive`+`terminal_stop`; rilassare il check
  `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE` a prefisso + audit comandi proibiti;
  arricchire `RuntimeResult`); nuovo `tests/test_d263_phase2_first_image_terminal.py`.
  Rischio medio, mitigato da riuso primitive auditate, single-use, fail-closed,
  cleanup exactly-once.

Hash pre-change dei file live-critical in
`D263_04_live_critical_prechange_hashes.json` (baseline per step 05/06).

Artefatti `analysis/D263/`: `D263_04_phase2_contract.json`,
`D263_04_patch_plan.md`, `D263_04_live_critical_prechange_hashes.json`. Nessun ZIP.

### D263/05: Phase 2 support primitives lifecycle + transport (sottostep 05)

Gate READY + contract step 04 valido. Implementati SOLO i support primitives;
il coordinator NON è stato esteso (rimandato a step 06).

`core/fdt_lifecycle.py` (`2aac7422…93a33a`): `COMMAND_TIMEOUT_MS` +`0x22:2000`;
`post_irq2_image_command` con guard one-shot (secondo tentativo →
`fail_closed`+`InvalidTransition`, niente re-arm retry); `cancel_pending_receive`
ora accetta anche `FIRST_IMAGE_RECEIVED` (cleanup host terminale post-first-image
per la decisione step 03). `core/runtime_transport.py` (`2930aa57…3e38d`):
`0x22` aggiunto a `fdt_a0_policy` (ABSTRACT_LOGICAL_ONLY, **non** live-proven,
nessun tail inventato) e a `operational_fdt_a0_policy`
(FIXED64_ZERO_TAIL_D261_CANDIDATE, deterministico zero-fill). `0x34`/`0xA2`/`0x70`
restano rifiutati da entrambe. Nuovo `tests/test_d263_phase2_support_primitives.py`
(12 test sintetici, tutti OK): valid transition (trace termina `0x32,0x22`, nessun
`0x34`/`0x20`), one-shot `0x22`, second attempt rejected, wrong-order rejected,
terminal transition, prohibited unreachable, physical frame construction,
deterministic tail. Coordinator invariato (`8e448caa…0df12c`).

Artefatti `analysis/D263/`: `D263_05_change_summary.json`,
`D263_05_test_results.json`, `D263_05_report.md`. Nessun ZIP.

### D263/06: Phase 2 PersistentRuntime first-image integration (sottostep 06)

Gate READY + step05 PASS. Esteso il production-shaped
`PersistentRuntimeCoordinator` (`persistent_runtime.py`
`c266ef8a…3963af`) con il minimo percorso offline candidato:
`D262 arm complete -> bounded IRQ2 wait -> exactly-one 0x22 -> retained TLS
first-image B0 -> canonical parser/codec -> FIRST_IMAGE_RECEIVED -> bounded
host/TLS/USB cleanup -> stop`. Nuovo metodo `_run_first_image_terminal()`
riusa `build_finger_image`, `parse_image_payload`/`decode_image_record` (codec
canonico) e la retained TLS B0 application session; nessun parser/codec
duplicato. `run()` chiama il metodo dopo `arm(ts16)` e rilassa il check del
trace esatto a prefisso `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE` + extra esattamente
`(0x22)` + audit comandi proibiti; `RuntimeResult`/`audit()` arricchiti. Il
`finally` esistente (TLS close + secret zeroize + USB release) resta
exactly-once su ogni failure. `tests/test_d263_phase2_first_image_terminal.py`
(8 test sintetici TLS, tutti OK) copre happy-path completo, wrong IRQ, timeout,
wrong ACK, malformed B0, CRC/image failure (plaintext azzerato), prevenzione
second 0x22 (one-shot), nessun pixel persistito, one-session/one-handshake/no-
reopen. Invarianti: one USB/TLS session+handshake, zero second secret/USB
reopen/retry, same retained session, esattamente un `0x22`, no
`0x34`/`0x20`-post/re-arm/`A2`/`0x70`/persistent-write, first-image bytes non
persistiti, fail-closed su mismatch, cleanup su failure. Nota: l'env Cloud non
ha OpenSSL PSK; i test usano TLS sintetico, il path `Tls12PskServerSession` di
produzione è validato da `test_d259` in env con OpenSSL-PSK.

Artefatti `analysis/D263/`: `D263_06_runtime_integration_summary.json`,
`D263_06_test_results.json`, `D263_06_report.md`. Nessun ZIP.

### D263/07: executable closure, regression audit, micro-corrective (sottostep 07)

Sottostep conclusivo di review offline end-to-end del change-set D263 (Phase 2
attiva: gate Phase1 READY + step05/06 completati). Closure eseguibile
verificata: coordinator importato da cwd repo-root, path resolution ok,
invocazione offline via double iniettati (nessun USB/live), failure reporting
fail-closed (`run()` -> `FAILED_CLOSED` + `lifecycle.fail_closed()` + re-raise;
`audit()` espone `failure_reason`), single-use (`runtime_single_use`),
cleanup garantito nel `finally` (TLS zeroize + secret boundary + transport).

Regression audit (checklist prompt): sequence state machine esatta (trace
prefisso `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE` + solo `(0x22)`); one-shot
(`post_irq2_image_command` incrementa `image_command_attempt_count` e fail-closed
al secondo tentativo; coordinator single-use); no forbidden reachability
(`run()` rifiuta `{0x34,0xA2,0x70,0x20}` post-arm e impone `extra==(0x22,)`;
lifecycle `_record` rifiuta non-allowlist/persistent/recovery); physical `0x22`
policy coerente con evidence (`fdt_a0_policy(0x22,…)` = `ABSTRACT_LOGICAL_ONLY`;
arm `0x32` (trace provata D255/D261) può usare FIXED64, ma `0x22` post-arm NON è
nella trace provata, quindi astrazione è la scelta fedele all'evidence, nessun
padding inventato); retained TLS single-session (`handshake_count==1`,
`second_server_session_created=False`, stesso secret-boundary); no second
handshake/provision/reopen (`session_count==1`, `psk_context_provisioning_count==1`);
first-image non persistita (plaintext azzerato dopo decode, azzerato anche su
fallimento decode; solo shape `(…,64)` in report, mai pixel; `host_cache_write_count=0`);
cleanup in success/failure; lifecycle terminale
(`FIRST_IMAGE_RECEIVED`->`HOST_WAIT_CANCELED`->`TERMINAL_STOPPED`); exception
fail-closed; no log di payload sensibile; nessun path operator/live preparato.

Micro-corrective (unico step con correzione permessa): difetto locale —
`_run_first_image_terminal` hardcodava `first_image_raster_shape=(80,64)`
invece di derivarlo dal decode canonico. Corretto:
`raster = parse_image_payload(bytes(plaintext)); outcome["first_image_raster_shape"] = (len(raster)//64, 64)`
(`core/persistent_runtime.py` `c266ef8a…` -> `1a731cda…`); decode canonico
inalterato, nessun pixel persistito, scope/invarianti invariati. Retest: 8+12 D263
test PASS.

Test: D263-targeted 20/20 PASS; full discovery 248 (5 fail + 33 err + 3 skip)
tutti ambientali (no OpenSSL PSK / `patch` / libusb / synthetic-TLS client nel
Cloud), pre-esistenti a D263, nessuno importa/esercita i tre moduli patch-ati.
Nessuna regressione D263. Integrity: vs `D263_04`, cambiano esattamente i tre
file patch-ati (persistent_runtime, runtime_transport, fdt_lifecycle); tutti gli
altri live-critical (backend/guardrail/launcher) byte-identici.

Artefatti `analysis/D263/`: `D263_07_executable_closure.json`,
`D263_07_regression_results.json`, `D263_07_live_critical_diff_manifest.json`,
`D263_07_report.md`. Nessun ZIP.

## Regole operative

- niente erase, IAP, ClearApp, F0/F4, cambio boot-mode o provisioning sostitutivo;
- niente payload privati, secret o materiale biometrico nei log/bundle;
- nessun comando live senza autorizzazione esplicita e step separato;
- fonti di modelli Goodix correlati sono atlanti strutturali, non prova target;
- ogni promozione di safety richiede sorgente, control flow, dataflow, lifetime
  ed effetto persistente chiusi sul target.

## Riferimenti

L'indice pubblico delle claim è `docs/EVIDENCE.md`; le fonti OEM/private e i
riferimenti community sono elencati in `docs/REFERENCES.md`. Gli artefatti
D230–D262 sono sotto `analysis/`; nessuna fonte proprietaria raw, WBDI esterna
o capture Issue #63 raw è redistribuita.
