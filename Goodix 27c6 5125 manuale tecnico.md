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
checksum valido e body da 16 byte. FDT arming/disarm non è ancora chiuso sul
target. Il repository non auto-approva né
autorizza da solo ulteriori operazioni live.

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
dito o restore. Il bootstrap blocker è ridotto ma non chiuso; il restore
blocker non è ridotto. D254 resta `BLOCKED`, non autorizza live e richiede come
prossima evidenza primaria una singola traccia Windows APP12509 sanitizzata da
cold-start/cache/first-seed fino ad arm, cancel senza dito e re-entry.

D255 ha preparato offline il kit per quella singola acquisizione, senza
eseguirla. La prima versione non è stata approvata dalla review AI-PM: il
launcher dichiarava PowerShell 5.1 ma usava tre API .NET moderne, mentre il
postprocessor ISO-only non ancorava il formato WBDI Goodix
`[MMDD-HH:MM:SS:mmm]`. La revisione correttiva dello stesso D255 sostituisce
quelle API, aggiunge self-test PowerShell, clock anchor start/end, snapshot
before/after del log e correlazione MMDD fail-closed. La procedura recuperabile
dalla storia resta delimitata ma incompleta:
la capture sopravvissuta è un pcapng USBPcap e il corpus la classifica come
cold attach Windows OEM, mentre comando, versione dello strumento, hypervisor,
passthrough e path WBDI originari non sono conservati. Il kit riusa quindi il
formato e il boundary provati: TShark/USBPcap nel guest Windows deve essere già
attivo prima del normale attach GUI della VM. Acquisisce nello stesso run wire,
log OEM, snapshot mirato del cache e marker UTC; il postprocessor hash-gated
correla A8, primo `0x36`, FDT12 host, cancel e re-entry senza esportare OTP,
immagini, PSK, TLS o payload biometrici. I test sintetici e le regressioni
offline passano; il runtime PowerShell nativo resta da verificare tramite il
nuovo `-SelfTestOnly` e poi `-PreflightOnly` in Windows perché non è disponibile
sull'host D255. La correzione è pronta soltanto per una nuova review AI-PM, non
per una run operatore. Bootstrap e restore restano aperti, nessuna
autorizzazione live è implicita e ogni run richiede una nuova autorizzazione
single-shot dopo review positiva.

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
| Kit acquisizione Windows D255 | prima review fallita; corrective pronto per nuova review AI-PM, non eseguito | compatibilità PS5.1/7 statica, self-test, clock anchor e WBDI MMDD/log rotation fail-closed; hardware non autorizzato |
| Codec immagine | confermato offline | record 7684 byte → raster u16 `80x64` |

## Fonti e confini di pubblicazione

Il repository privato è il workspace canonico di sviluppo. Il repository
pubblico è una superficie di pubblicazione congelata: non viene sincronizzato
da D247 e potrà ricevere soltanto un export futuro, separato, sanitizzato e
auditato. Un working tree pulito/equivalente non rende pubblicabile la history
privata; capture, DLL, firmware, secret o dati biometrici transitati nella
storia richiedono clean export, nuova storia o filtro dedicato.

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
     -> READY_FOR_AI_PM_REVIEW; nuova autorizzazione richiesta per ogni run
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
ha confermato l'assenza di restore deterministico;
FDT arming/disarm/restore e ordering mixed-channel completi restano quindi non
chiusi target-side. Un live FDT o first-image non è giustificato né autorizzato.

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

## D255: kit di acquisizione Windows APP12509

La ricostruzione storica distingue fatti e lacune. Il file
`rilevamento.pcapng`, hash `50071c0f...19c184b`, usa linktype USBPcap; manuale
ed evidence index lo classificano come cold attach e citano una seconda
capture indipendente ora perduta. `GoodixExport.zip` ne ha preservato il file
insieme a `gfusb.dll` e componenti OEM. Non sono invece preservati comando di
capture, versione Wireshark/USBPcap, prodotto VM, comando di passthrough o path
del log. Non è quindi provato il locus esatto del vecchio collector.

Il metodo futuro selezionato avvia TShark sull'interfaccia USBPcap esplicita nel
guest Windows mentre il target è ancora assente; solo dopo il marker
`CAPTURE_STARTED` l'operatore usa il normale attach GUI già revisionato. È
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

Nel ramo futuro one-shot, tool/interface/path/disk/log gate e target absence
precedono la creazione del run. `run_clock.json`, marker `CLOCK_ANCHOR`, copie e
metadati before di log/cache, runtime self-check e setup non hardware vengono
completati prima del confronto dell'autorizzazione esatta. Solo allora si
scrive `authorization_consumed.json` e si tenta TShark. Un failure precedente
riporta `D255_AUTHORIZATION_CONSUMED=false`; un failure di start TShark dopo il
record consuma il run. Attach VM, Windows Hello, cancel e re-entry restano
azioni GUI separate da marker UTC. Lo script non invoca service restart, PnP,
VM, provisioning, flash o comandi Goodix. Il cache discovery resta ristretto a
root Goodix e a size/naming pertinenti.

`analysis/D255/d255_postprocess_windows_evidence.py` opera solo su path esterni
hash-gated. Seleziona il device tramite A8 esatto, ricostruisce A0/B0 senza
esportare payload, misura il contratto fisico `0x36`, valida l'ipotesi
`OTP64+FDT12+NAV3200+IMAGE10240+CRC4`, confronta solo FDT12 e hash di regioni,
e censisce la finestra ultimo `0x32` → cancel → re-entry. Il launcher conserva
local-only snapshot OEM before/after con path, size, hash e mtime; il parser usa
come nuova finestra soltanto un append byte-prefix verificato e distingue
`UNCHANGED`, `GREW`, `TRUNCATED` e `REPLACED_OR_ROTATED`.

Ogni evento OEM sanitizzato espone sorgente timestamp, UTC e qualità, mai la
linea raw. ISO-8601 con offset/Z è diretto; Goodix MMDD viene convertito solo se
anno del run, offset locale, Windows timezone, anchor start/end e marker UTC
selezionano un istante unico. Stesso giorno, mezzanotte e fine anno non ambigua
sono supportati; cambio offset/DST, data malformata o fuori finestra e rotazione
non ricostruibile restano `AMBIGUOUS`. Eventi critici cancel/restore non
correlabili impongono `RESTORE_MODEL=INCONCLUSIVE_OEM_TIME_CORRELATION` e non
promuovono `CANCEL_IS_HOST_ONLY` o `USB_CLOSE_AFTER_CANCEL`.

L'uguaglianza wire/cache/log viene classificata come correlazione, mai
automaticamente come causalità. Un A8 assente/diverso rende l'evidenza non
target-specific e terminale; marker mancanti, cancel prima di arm, formato
inatteso e collisioni falliscono chiusi senza retry.

I 27 test D255 passano, inclusi ISO, MMDD realistico, mezzanotte, fine anno,
ambiguità/cambio offset e quattro stati del log, insieme alle regressioni
D252–D254 e ai 172 test della suite supportata. `pwsh` non è installato
sull'host Linux D255: sintassi, API vietate e contratti PowerShell sono coperti
staticamente, mentre il vero `-SelfTestOnly` e poi `-PreflightOnly` Windows
restano una verifica futura. Nessun dato raw D255 è stato acquisito.

```text
D255_INITIAL_AI_PM_REVIEW=FAIL_EXECUTABILITY_AND_TIME_CORRELATION
D255_CORRECTIVE_STATUS=READY_FOR_AI_PM_REVIEW
D255_OUTCOME=CORRECTIVE_WINDOWS_EVIDENCE_ACQUISITION_KIT_PREPARED
D255_LIVE_EXECUTION=NOT_PERFORMED
D255_HARDWARE_BOUNDARY=NOT_AUTHORIZED
D255_OPERATOR_AUTHORIZATION_REQUIRED=true
D255_AUTHORIZATION_CONSUMED_AFTER_PRE_HARDWARE_SETUP=true
D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true
READY_FOR_AI_PM_REVIEW=true
READY_FOR_OPERATOR_RUN=false
BOOTSTRAP_CLOSED=false
RESTORE_CLOSED=false
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

Il current critical boundary è offline: chiudere la precondizione target
fresh per `0x36`/tabella FDT e il cancel/restore device-side dopo arming. D253
ha chiuso la distinzione wire corrente `0x22`/`0x20` e corretto il core, ma non
ha reso il path live-safe. D254 ha corroborato dall'esterno il cache OTP-bound
cross-family e `IRQ2→0x22` su una capture 5125 a firmware ignoto, senza però
ottenere la derivazione del seed APP12509 o un no-finger restore. La tabella
finale della capture locale è
dinamicamente appresa da IRQ `0x0100`, ma vale soltanto come prova della
sessione catturata; il cold-start D251 non possiede una baseline validata. Non
esiste un restore OEM post-FDT provato. D255 ha preparato e verificato offline
il kit per la capture Windows APP12509 mirata, ma non l'ha eseguita: il confine
resta bloccato e nessun path FDT Linux è diventato live-capable.

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
FDT_RESTORE_STATE NOT_PROVEN
FDT_ARM_AND_STOP_SAFE false
D252_LIVE_BOUNDARY BLOCKED
D252_LIVE_EXECUTION NOT_PERFORMED
D253_POST_IRQ2_IMAGE_COMMAND 0x22_DATA_0100
D253_FRESH_BASELINE_BOOTSTRAP_CLOSED false
D253_FDT36_PHYSICAL_CONTRACT_LIVE_READY false
D253_SAFE_STOP_AFTER_FDT_ARM false
D253_LIVE_BOUNDARY BLOCKED
D253_LIVE_EXECUTION NOT_PERFORMED
D253_REQUIRES_EXTERNAL_EVIDENCE true
D254_BOOTSTRAP_BLOCKER_REDUCED true
D254_BOOTSTRAP_CLOSED false
D254_RESTORE_BLOCKER_REDUCED false
D254_RESTORE_CLOSED false
D254_LIVE_BOUNDARY BLOCKED
D254_LIVE_EXECUTION NOT_PERFORMED
D254_REQUIRES_MORE_PRIMARY_EVIDENCE true
D255_KIT_PREPARED true
D255_INITIAL_AI_PM_REVIEW FAIL_EXECUTABILITY_AND_TIME_CORRELATION
D255_CORRECTIVE_STATUS READY_FOR_AI_PM_REVIEW
D255_READY_FOR_AI_PM_REVIEW true
D255_READY_FOR_OPERATOR_RUN false
D255_LIVE_EXECUTION NOT_PERFORMED
D255_HARDWARE_BOUNDARY NOT_AUTHORIZED
D255_BOOTSTRAP_CLOSED false
D255_RESTORE_CLOSED false
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
hardware. Seed APP12509 iniziale e restore no-finger restano bloccanti.

D255 aggiunge un kit PowerShell GPL per la futura raccolta OEM e un
postprocessor GPL offline con fixture. La prima versione è stata respinta in
review; la correzione chiude staticamente API PS5.1 e correlazione MMDD, ma non
ha avviato Windows, VM, TShark, USB, TLS o comandi Goodix reali. Ha usato solo
fixture sintetiche e audit offline. Il bundle non contiene raw USB, WBDI,
cache, OTP, PSK, firmware, DLL o biometria. Una review positiva del kit non
consuma né sostituisce la futura autorizzazione operatore.

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
D230–D255 sono sotto `analysis/`; nessuna fonte proprietaria raw, WBDI esterna
o capture Issue #63 raw è redistribuita.
