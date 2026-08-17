# Goodix 27c6:5125 — manuale tecnico

## Stato del progetto

Il progetto studia il sensore Goodix USB `27c6:5125` del Huawei MateBook D15 /
BohrD-WDH9D con un vincolo assoluto: preservare firmware, identità,
configurazione factory, stato persistente/secure e compatibilità con Windows.

Non esiste ancora un driver Linux funzionante. D239 ha eseguito sul firmware
12509 l'intero cold-start OEM fino a D1 e ricevuto il B0/TLS diretto; D241 ha
poi verificato live l'ownership exactly-once e un ClientHello TLS 1.2 valido.
Il server OpenSSL ha emesso ServerHello e ServerHelloDone, ma il dispositivo
non ha inviato ClientKeyExchange entro il timeout bounded. D242 ha isolato e
corretto offline due divergenze primarie dal send path Windows: ultimi OUT corti
anziché blocchi fissi da 64 byte e assenza del pacing TLS `Sleep(10)`. Il nuovo
kit è `READY_NOT_EXECUTED`: il repository non autorizza da solo operazioni live.
D242 ha provato e corretto offline due divergenze rispetto al contratto OEM
osservato in D175/Windows; la loro sufficienza causale sul firmware 12509 non è
ancora verificata live.

| Area | Stato | Risultato |
| --- | --- | --- |
| Framing USB A0/B0 | confermato | endpoint, chunk da 64 byte, checksum e correlazione sono noti |
| TLS 1.2 PSK | server flight verificato live in D241 | ClientHello 47, ServerHello 81, ServerHelloDone 4; nessun ClientKeyExchange |
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
| Correzione D242 | PASS offline, source-sealed | contratto A0/B0 OUT fissi da 64 byte + pacing TLS 10 ms; closure gate PASS; kit non eseguito, sufficienza causale live non verificata |
| Codec immagine | confermato offline | record 7684 byte → raster u16 `80x64` |

## Fonti e confini di pubblicazione

Lo stato pubblico è composto dal repository, da `README.md`, dall'indice
`docs/EVIDENCE.md`, dai riferimenti e dal codice clean-room. Le fonti primarie
private/locali comprendono DLL OEM, capture e APP embedded, identificati per hash
ma non redistribuiti. Materiale proprietario, payload TLS privati, secret,
immagini e template biometrici non devono entrare nel repository o nei bundle.

Il corpus D230 è `GoodixExport.zip`, indicato dall'operatore come corpus privato
recuperato e già provenance-validato, SHA-256
`2b76e294059fcfa2f32a6e75d92d04731b41a01bd3221852b5584ce409a3e45e`.
Contiene `gfusb.dll` SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`
e una capture recuperata SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.

La prima capture indicata dall'operatore è definitivamente perduta. Nessun
riepilogo storico la sostituisce come evidenza packet-level; D230 censisce una
sola capture. Questo limite è parte della coverage proof.

Una testimonianza indipendente nel commento di `mkl-corbachoh` alla
[issue GitHub #1](https://github.com/Rockytkg/goodix-linux-27c6-5125/issues/1)
è registrata come `EXTERNAL_THIRD_PARTY_LIVE_CORROBORATION`, non come evidenza
primaria del target. Il contributor dichiara successo TLS-PSK, enrollment,
same/different-finger verify e autenticazione PAM su `27c6:5125`, chip
`0x2504`, firmware nativo 12509 preservato e senza flash, usando una build
localmente auditata e isolata sotto `/opt/goodixgf`. La stessa testimonianza
riporta però `MCU read 0xBB010003 status 0x01`, cioè assenza di dati PSK, e una
nuova provisioning PSK once: dimostra al più
`EXTERNALLY_REPORTED_12509_NATIVE_FW_FULL_STACK_SUCCESS` e
`EXTERNALLY_REPORTED_12509_NO_FIRMWARE_FLASH`, non preservazione di una PSK
Windows/factory preesistente. La coesistenza riportata di eventi FDT plaintext
con frame immagine protetti TLS è una corroborazione esterna utile per fasi
post-handshake future; non riapre lo scope D242 e non autorizza D4, FDT,
capture, enroll o matching in questo step.

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
D175 tutte le 56 submission bulk OUT A0/B0 osservate sono staging buffer fissi
da 64 byte; la tail dell'ultimo blocco è fuori dalla lunghezza dichiarata e,
nei B0 del server flight esaminati, è nonzero. I byte del frame costruito, i
byte USB richiesti e quelli completati sono quindi misure distinte. D242 copia
prima i byte significativi e inizializza deterministicamente a zero la tail
non semantica per non propagare contenuto di staging irrilevante. L'equivalenza
rivendicata riguarda dimensione di submit e semantica della lunghezza
dichiarata, non identità byte-per-byte della tail Windows. Un flag
`server_hello_sent` prova al massimo emissione e wrapping; la trasmissione
completa richiede completion USB full-length per ogni blocco.

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
D242 -> contratto OEM corretto offline: OUT fissi 64 byte + pacing 10 ms/record
     -> closure PASS e nuovo kit source-sealed READY_NOT_EXECUTED, senza D4
     -> bundle precedente a112fe2b...56df20 SUPERSEDED / DO_NOT_USE_FOR_LIVE_AUTHORIZATION
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

## D242: correzione delle divergenze del contratto OEM

La sola capture primaria locale disponibile è quella storicamente classificata
D175; la capture D43 è assente e resta `NOT_ASSESSABLE`. D175 mostra la stessa
struttura TLS osservata in D241: ClientHello payload 47 con suite offerte
`00a8,00ff`, ServerHello payload 81 che seleziona `00a8`, e
ServerHelloDone payload 4. ServerHello e ServerHelloDone sono in due B0
distinti, un record TLS per B0; wrapper type, declared/actual length e checksum
sono coerenti. Non è una equivalenza byte-per-byte dei valori casuali o del
session ID, che restano intenzionalmente non pubblicati.

Il differenziale primario ha invece provato due divergenze dal contratto OEM:

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
molto dentro quel budget. D242 ha quindi implementato il fix di contratto:
staging di ogni OUT A0/B0 a 64 byte con tail D242 zero-initialized, requisito di
completion esattamente 64, e pacing di 10 ms dopo ogni record TLS. La portata
comune A0/B0 è classificata `OEM_COMMON_A0_B0_TRANSPORT_CONTRACT_VERIFIED`:
tutte le 56 submission OUT D175 sono da 64 byte e le call-site command-send
note passano `r8b=0x40` al helper che usa la lunghezza del caller. Declared
length, checksum/header, ACK/response e parsing A0 restano invariati; un test
sintetico verifica che la tail resti fuori dal frame dichiarato. Ciò preserva
il pre-D1 già superato live in D239/D241 senza riaprirne la semantica.
First-record ownership, binding PSK, zero retry e stop prima di D4 restano
invariati. Fixture offline verificano tre OUT da 64 byte, due B0 distinti, due
pause da 10 ms, ricezione post-flight, short completion fail-closed,
cleanup/zeroizzazione e redazione.

`PROVEN_DIVERGENCE != PROVEN_DEVICE_ROOT_CAUSE`. H4 e H5 sono `PROVEN` come
divergenze e il runtime corretto ne riproduce offline le proprietà; non è ancora
provato che una o entrambe siano causalmente sufficienti a far rispondere il
firmware con ClientKeyExchange. Il nuovo confine è la validazione device-side futura
del server flight corretto, in un solo tentativo umano separatamente
autorizzato. D242 non ha eseguito USB reale né handshake TLS reale.

Il kit D242 usa esclusivamente
`/var/lib/goodix-5125-poc/d242-operator-invocation.marker`; i marker storici
D236/D238/D239/D241 sono benigni e non vengono cancellati. Prepara
idempotentemente `/var/lib/goodix-5125-poc/d242-results` root `0700`, verifica
hash e sealed baseline, applica l'unseal soltanto per la singola invocazione,
e reseala nel cleanup. Il closure gate esegue con peer USB/TLS sintetici
preflight, lifecycle directory/marker, patch apply/reverse, handoff exactly-once,
successo, timeout post-flight, osservabilità redatta e cleanup. Il suo stato è
`D242_EXECUTABLE_CLOSURE_GATE_PASS`; il kit resta `READY_NOT_EXECUTED`.

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

D4, application data, FDT, capture, enroll, reset/power-cycle e recovery
invasiva automatica restano irraggiungibili o vietati. D240 è obsoleto e non è
stato eseguito.

Il riferimento Rocky indipendente è
<https://github.com/Rockytkg/goodix-linux-27c6-5125/issues/1>. È corroborazione
esterna, distinta dalla capture/DLL primaria locale; nessuna implementazione GPL
è stata copiata nel repository BSD-2-Clause.

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
l'orchestratore e il vero entrypoint production non sono più blocker offline.
Il confine immediato non è più pre-D1: D239 ha provato live su 12509 l'intera
sequenza fino a D1 e il successivo B0/TLS diretto. D241 ha poi verificato live
ClientHello, ownership e binding, ha trasmesso il server flight ed è terminato
senza ClientKeyExchange. D242 ha provato e corretto offline le divergenze di
segmentazione e pacing rispetto a D175/Windows; non ha provato una root cause
device-side. Il confine corrente è la sola
risposta device-side al server flight corretto: non è stata ancora osservata.
Il repository resta source-sealed; soltanto il kit D242 con closure PASS può
applicare temporaneamente l'unseal per un singolo tentativo umano separatamente
autorizzato. Quel tentativo deve fermarsi subito dopo il successo crittografico
TLS, prima di D4. Nessun esito storico autorizza retry o seconda invocazione.
L'assenza di prova device-side assoluta dei receiver resident resta esplicita.

Separatamente, la riproducibilità generale resta limitata dal materiale di
trasporto machine-bound; il motore TLS Linux è verificato soltanto in loopback,
non con il dispositivo.

## Hard Wall

```text
APP mapped start          0x0802c000
A2 target                 0x080272e1
0x70 target               0x0802b8f5
minimum missing interval  0x080272e0..0x0802b8f4
PRE_D1_PATH_CLEARED_FOR_EXACT_OEM_REPLAY  true
DEVICE_RESIDENT_NO_NVM_SIDE_EFFECT_PROVEN false
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
transizione command→TLS D241, più la correzione di trasporto/pacing D242.
Questi includono ABI libusb esatta e TLS OpenSSL, ma il live resta doppiamente
source-sealed e non
costituisce un driver libfprint pronto. Il record immagine noto è di 7684 byte:
7680 byte packed-12 più CRC-32/MPEG-2, convertito in raster u16 `80x64` con
transpose.

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
D230–D242 sono sotto `analysis/`; nessuna fonte proprietaria raw è redistribuita.
