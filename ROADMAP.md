<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# ROADMAP.md — Goodix 27c6:5125 self-contained release

## 0. Scopo e autorità

Questa roadmap è la state machine operativa canonica del progetto per portare
la release attuale, dipendente dal bundle Windows, a un driver autonomo e
convivente con Windows. Il branch operativo non è hard-coded qui: vale il branch
correntemente selezionato dall'Utente secondo `AGENTS.md`.

Goal finale:

```text
git clone / download
        |
        v
./install.sh
        |
        v
KDE / fprintd-enroll
        |
        v
driver inizializza autonomamente il reader
        |
        v
fingerprint stack Fedora operativo
```

Il percorso finale non deve richiedere all'utente Windows Material Builder,
USBPcap, DPAPI recovery, `Goodix_Cache.bin`, `gfusb.dll`, una VM Windows o un
bundle preparato manualmente.

Il target qualificato resta:

```text
USB VID:PID:  27c6:5125
APP:          GF_ST411SEC_APP_12509
Host:         Fedora 44 KDE x86_64
Stack:        libfprint -> stock fprintd -> PAM/KDE
```

`AGENTS.md` possiede la governance permanente. Questo file possiede soltanto
sequenza, gate e criteri di uscita. `PROJECT_STATE.json` è una cache operativa
non autoritativa e deve seguire questa roadmap. `ARTIFACT_INDEX.json` è il
router non autoritativo del contesto: Git resta la fonte della sua struttura
reale e l'indice va riparato quando diventa stale.

## 1. Invarianti di progetto

Restano non negoziabili per tutto il percorso:

- no firmware flash o firmware replacement;
- no IAP;
- no ClearApp;
- no OTP write;
- no factory-data write;
- no cambio persistente di VID:PID o modalità;
- no comando persistente non compreso;
- fail-closed su target, APP, chip/profile, OTP, pairing o risposta ambigui;
- password login, desktop, sudo e PolicyKit devono sopravvivere a failure,
  rollback e normali update Fedora;
- Windows interoperability è requisito di release, non un extra;
- nessun dato biometrico reale, PSK, plaintext DPAPI o protected material entra
  negli artefatti pubblici.

L'unica nuova mutazione persistente prevista sul reader è il pairing host già
qualificato dal PoC: un singolo `E0` per transazione autorizzata, con
`BB010002` reale preservato byte-per-byte, nessun retry automatico e prova
indipendente tramite readback/hash/TLS.

## 2. Evidenza corrente

### PROVEN

- provisioning PSK Linux sul target;
- singolo `E0` end-to-end;
- `BB010002` invariato nel write qualificato;
- `BB020003 == SHA256(BB010003)` per la nuova PSK;
- TLS 1.2 con `PSK-AES128-GCM-SHA256`;
- intervallo di 10 ms tra record B0 TLS consecutivi;
- recovery Windows dopo uno stato persistente originato da Linux;
- `gx_wb_encrypt()` equivalente byte-per-byte alla rappresentazione OEM
  qualificata;
- bootstrap FDT da seed iniziale zero nel production path;
- riutilizzo della stessa PSK Linux `L1` dopo ripetuti ritorni da Windows;
- ciclo stabile `L1 -> W1 -> L1 -> W2 -> L1`.

### INFERRED — non promuovere a PROVEN prima del gate dedicato

- generazione completa di CONFIG90 da template type-12 + OTP;
- parser strutturale generalizzato di `BB010002` per stati Windows legittimi.

### Blocker tecnici iniziali

1. equivalenza esatta della CONFIG90 generata;
2. validazione strutturale generalizzata di `BB010002`.

## 3. Regola di avanzamento

Ogni fase usa:

```text
PHASE
PURPOSE
PRIMARY_ARTIFACT
EXIT_GATE
NEXT
```

Non saltare una fase. Non iniziare il fallback in parallelo finché il primary
path resta tecnicamente plausibile. Una failure richiede prima adattamento
all'interno dell'ipotesi primaria; un cambio di strategia materiale richiede
`HUMAN_REQUIRED`.

---

## P0 — Architecture baseline

**STATUS:** COMPLETE

**PURPOSE**

Adottare come baseline l'architettura emersa da
`development/SELF_CONTAINED_DRIVER_AUDIT.md`:

- pairing/state coordinator dentro il driver libfprint;
- inizializzazione hardware solo durante una azione biometrica esplicita;
- PSK Linux generata localmente e journaled prima dell'unico `E0`;
- `BB010002` corrente preservato byte-per-byte;
- CONFIG90 da template qualificato + OTP live;
- eliminazione logica di `gfusb.dll`;
- FDT appreso live;
- migrazione utenti esistenti senza reprovisioning se E4/TLS coincidono;
- una PSK Linux stabile come policy candidata, da qualificare in P7.

**PRIMARY_ARTIFACT**

`development/SELF_CONTAINED_DRIVER_AUDIT.md`

**EXIT_GATE**

`SELF_CONTAINED_ARCHITECTURE_APPROVAL=PASS`

**NEXT**

P0A.

---

## P0A — Artifact index baseline reconciliation

**PURPOSE**

Prima di riprendere l'implementazione, riconciliare `ARTIFACT_INDEX.json` con
il delta Git reale introdotto sul branch operativo rispetto a `main`.

Per il bootstrap corrente il riferimento iniziale è il lavoro prodotto su
`development`, quindi il confronto canonico è:

```text
main...development
```

con semantica three-dot/merge-base: deve descrivere ciò che è stato introdotto
sul lato `development` senza confondere i commit presenti solo su `main` con
lavoro del branch di sviluppo.

Per sessioni future, se l'Utente ha selezionato un diverso branch operativo,
AI PM deve usare:

```text
main...CURRENT_CHECKED_OUT_BRANCH
```

senza cambiare branch autonomamente.

**PRIMARY_ARTIFACT**

`ARTIFACT_INDEX.json`

**EXIT_GATE**

`ARTIFACT_INDEX_BASELINE_RECONCILED=PASS` solo se:

- il branch operativo è determinato senza ambiguità;
- il confronto three-dot con `main` è stato osservato realmente;
- ogni file aggiunto/modificato/rinominato dal lato operativo è indicizzato o
  esplicitamente classificato come non utile al routing;
- gli eventuali delta presenti soltanto su `main` sono registrati
  separatamente e non sovrascritti implicitamente;
- i file canonici, state cache, decision artifact, PoC/evidenze e artefatti
  rilevanti per la fase corrente sono instradabili senza scansione completa del
  repository;
- l'indice registra HEAD/merge-base usati per la riconciliazione;
- `PROJECT_STATE.json` viene aggiornato con il gate chiuso e il prossimo passo
  P1.

L'indice non deve ricostruire retroattivamente tutta la storia del progetto e
non deve creare directory/file per completezza.

**STOP_IF**

Il branch è ambiguo, il confronto non è determinabile, oppure un file necessario
al routing non può essere classificato con sufficiente certezza.

**NEXT**

P1.

---

## P1 — Direct pairing crypto / logical DLL removal

**PURPOSE**

Rendere la derivazione WB/`BB010003`/`BB020003` una funzione interna pura,
indipendente dalla DLL OEM, senza cambiare ancora il runtime production.

La soluzione deve derivare da codice/protocol facts con provenance e licensing
espliciti. `gfusb.dll` resta soltanto oracle/provenance finché l'equivalenza non
è chiusa.

**PRIMARY_ARTIFACT**

Implementazione pairing-crypto pura + KAT/differential tests.

**EXIT_GATE**

`PAIRING_CRYPTO_OFFLINE=PASS` solo se:

- tutti i vettori OEM/D190 esistenti coincidono byte-per-byte;
- i vettori `BB010003` e `BB020003` qualificati coincidono;
- negative KAT per key/AAD/header/IV/tag/HMAC falliscono correttamente;
- nessun runtime path è stato ancora reso dipendente dalla nuova implementazione;
- licensing/provenance è chiaro.

**STOP_IF**

Qualunque byte differisce senza spiegazione provata.

**NEXT**

P2.

---

## P2 — CONFIG90 derivation + BB010002 structural boundary

**PURPOSE**

Chiudere due input boundary necessari alla self-initialization.

### CONFIG90

Implementare parsing chip/OTP e generazione della CONFIG90 type-12, con patch
nominate e finalizer ricalcolato.

### BB010002

Definire un parser strutturale stretto per valori OEM legittimi senza
decrittare, sintetizzare o reinterpretare il contenuto Windows.

**PRIMARY_ARTIFACT**

Generator CONFIG90 puro + parser `BB010002` + differential/negative tests.

**EXIT_GATE**

`CONFIG90_AND_BB010002_OFFLINE=PASS` solo se:

- ogni bundle legittimo disponibile produce una CONFIG90 identica byte-per-byte,
  oppure ogni differenza è nominata, spiegata e separatamente qualificata;
- chip/profile sconosciuto e OTP malformata falliscono chiusi;
- `BB010002` legittimi disponibili passano lo stesso parser strutturale;
- assenza, lunghezza, tag o struttura ambigui vengono rifiutati;
- nessun dummy `BB010002` è introdotto.

**STOP_IF**

Template nonpatchato, semantica OTP o struttura `BB010002` restano ambigui.

**NEXT**

P3.

---

## P3 — Seedless FDT model

**PURPOSE**

Eliminare la dipendenza runtime da `fdt-cache.bin` dimostrando offline che il
production lifecycle può rappresentare esplicitamente l'assenza di seed e
apprendere la tabella FDT da campioni no-finger bounded.

**PRIMARY_ARTIFACT**

Lifecycle FDT seedless + test no-finger/finger-present/timeout/drift.

**EXIT_GATE**

`FDT_ZERO_SEED_OFFLINE=PASS` solo se:

- zero seed è codificato senza ambiguità;
- sample count e retry sono bounded;
- finger/touch disturbance non può essere promosso a baseline;
- temperatura, timeout, duplicate e frame malformati falliscono in modo pulito;
- l'unico stato eventualmente persistito è la minima tabella FDT necessaria,
  mai una immagine baseline.

**NEXT**

P4.

---

## P4 — Crash-safe state v2 and legacy migration

**PURPOSE**

Costruire lo stato locale per-reader e la transazione
`PREPARED -> ACTIVE`, con PSK durably journaled prima di qualunque futuro
`E0`.

Migrare il bundle legacy senza modificarlo e senza reprovisioning quando la PSK
importata coincide con il pairing live.

**PRIMARY_ARTIFACT**

State-v2 implementation + old-bundle importer + fault-injection tests.

**EXIT_GATE**

`STATE_V2_AND_MIGRATION_OFFLINE=PASS` solo se:

- state binding usa target/APP/profile/OTP digest e non solo VID:PID;
- PSK/receipt sono root-only, bounded, no-follow e atomicamente aggiornati;
- file e directory `fsync` sono coperti;
- crash/power-loss a ogni boundary sceglie una sola riconciliazione read-only;
- nessun recovery richiede un secondo `E0` speculativo;
- il bundle legacy resta byte-per-byte intatto e rollback-capable;
- secret e WB plaintext non entrano nei log.

**STOP_IF**

Il recovery post-write può richiedere guessing o un secondo `E0`.

**NEXT**

P5.

---

## P5 — Read-only coordinator integration and Fedora VM closure

**PURPOSE**

Integrare nel driver il coordinator di identity/config/state in modalità
read-only rispetto al pairing, senza abilitare ancora il writer production.

Il trigger deve essere una reale attivazione fprintd/libfprint, non enumeration,
installer, boot o login non inizializzato.

**PRIMARY_ARTIFACT**

Integrated coordinator + Fedora 44 VM install/update/uninstall/rollback tests.

**EXIT_GATE**

`COORDINATOR_HOST_VM=PASS` solo se:

- installazione fresca non richiede il bundle;
- installazione con reader assente resta valida;
- discovery/login non possono generare pairing write;
- stock fprintd e SELinux Enforcing restano il confine di servizio;
- update/reinstall/uninstall/rollback preservano password e desktop;
- runtime legacy e state-v2 possono coesistere durante la migration window;
- il writer production resta disabilitato.

**NEXT**

`HUMAN_REQUIRED: LIVE_NO_FINGER_APPROVAL`, poi P6.

---

## P6 — Integrated LIVE_NO_FINGER qualification

**PURPOSE**

Qualificare sul target APP12509, senza biometria reale, il percorso
self-contained integrato.

Il live deve procedere dal meno invasivo al più invasivo:

1. identity/chip/OTP/`BB010002`/E4 read-only;
2. CONFIG90 generata confrontata con la baseline qualificata;
3. solo dopo i gate precedenti: journal `PREPARED`;
4. massimo un `E0`;
5. ACK/completion, `BB010002` invariato, E4 match e TLS;
6. zero-seed FDT no-finger;
7. reopen ordinario con zero `E0`;
8. recovery read-only da crash post-E0/pre-ACTIVE senza secondo write.

**PRIMARY_ARTIFACT**

Qualified live evidence/receipt sanitizzata, senza secret.

**EXIT_GATE**

`SELF_CONTAINED_LIVE_NO_FINGER=PASS`

**STOP_IF**

- target/APP/profile/OTP/`BB010002` differiscono dal boundary qualificato;
- CONFIG90 presenta differenze non spiegate;
- risposta pairing è ambigua;
- viene richiesto un secondo `E0`;
- cambia un persistent field fuori dal pairing previsto;
- compare qualunque firmware/IAP/ClearApp/OTP-write path;
- TLS/readback/hash non coincidono.

**NEXT**

`HUMAN_REQUIRED: WINDOWS_INTEROP_APPROVAL`, poi P7.

---

## P7 — Windows interoperability and stable Linux-key reuse

**PURPOSE**

Dimostrare realmente la convivenza Windows/Linux e qualificare la policy della
PSK Linux stabile.

La sequenza candidata:

```text
Linux L1
  -> Windows W1
  -> Linux restores L1
  -> ordinary Linux reopen: no E0
  -> Windows W2
  -> Linux restores L1
  -> ordinary Linux reopen: no E0
```

Linux deve sempre preservare il `BB010002` Windows corrente byte-per-byte.
Un mismatch E4 può essere classificato solo come external pairing replacement,
mai attribuito automaticamente a Windows.

**PRIMARY_ARTIFACT**

Bounded multi-cycle Windows/Linux interoperability evidence.

**EXIT_GATE**

`WINDOWS_LINUX_PING_PONG=PASS` solo se:

- Windows recupera autonomamente dopo Linux;
- Linux riconosce read-only il pairing sostituito;
- Linux riusa realmente la stessa `L1`;
- ogni transizione OS richiede al massimo un write qualificato;
- ogni reopen nello stesso OS richiede zero write;
- almeno un ciclo ripetuto W2/L1 non crea nuove generazioni Linux o loop;
- VM passthrough/dual-boot ownership loss non può provocare un secondo writer;
- nessuno dei due OS diventa unrecoverable.

Solo questo gate può promuovere il repeated `L1/Wn` reuse da `INFERRED` a
`PROVEN`.

**STOP_IF**

Same-OS reopen scrive, il reader entra in loop, Windows non recupera, Linux
perde L1 o compare qualunque necessità di condividere/esportare la PSK tra OS.

**NEXT**

P8.

---

## P8 — Biometric and desktop integration qualification

**PURPOSE**

Qualificare enrollment/verify/identify e tutti i consumer Fedora con il nuovo
bootstrap self-contained.

**PRIMARY_ARTIFACT**

Stock-stack biometric and desktop qualification evidence.

**EXIT_GATE**

`SELF_CONTAINED_BIOMETRIC_STACK=PASS` solo se:

- KDE/fprintd enrollment funziona;
- verify/identify funzionano nello stock stack;
- login, KScreenLocker, sudo e PolicyKit restano coerenti con il comportamento
  supportato;
- serie fisica bounded: massimo tre tentativi, stop al primo MATCH, nessun quarto
  o hidden retry;
- cancel/release/baseline/temperature paths sono puliti;
- failure fingerprint non compromette password, desktop, sudo o PolicyKit.

**NEXT**

P9.

---

## P9 — Publication cleanup and development-branch sanitization

**PURPOSE**

Primo passaggio della closure pubblica dopo P8. Preparare il contenuto destinato a `main`
separando in modo netto ciò che è pubblico/necessario da ciò che deve restare
solo nel workspace di sviluppo.

Questa fase non deve fare pulizia cosmetica indiscriminata: deve classificare
ogni artefatto in base alla reale funzione.

**PRIMARY_ARTIFACT**

Publication audit + clean main-candidate tree.

**REQUIRED CLASSIFICATION**

```text
PUBLIC_RUNTIME_REQUIRED
PUBLIC_BUILD_TEST_REQUIRED
PUBLIC_DOCUMENTATION
INTERNAL_NONPUBLIC
PRIVATE_OR_NONREDISTRIBUTABLE
OBSOLETE
```

**EXIT_GATE**

`PUBLICATION_CLEANUP=PASS` solo se:

- nessuna parte di codice necessaria a build, installazione, runtime, recovery,
  test pubblici o licensing/provenance resta nascosta dentro la directory
  git-ignored `development/`;
- qualunque codice oggi dentro `development/` ma necessario al driver viene
  promosso in una posizione pubblicabile, ordinata e semanticamente corretta;
- tutto ciò che non è pubblicabile viene invece raccolto con ordine sotto
  `development/`, che resta git-ignored;
- i file non pubblicabili vengono rimossi dal main-candidate tracking senza
  perdere la copia locale necessaria allo sviluppo/provenance;
- build/test/install della candidate esportata non dipendono in alcun modo da
  `development/`;
- vengono auditati secret, PSK, DPAPI plaintext, biometric data, raw capture,
  OEM/proprietary binary, cache, temp, evidence private e machine-specific path;
- vengono auditati source manifests, license notices, attribution, provenance,
  import, script, test e packaging;
- si controlla esplicitamente se materiale git-ignored oggi contiene invece
  codice o documentazione che deve essere pubblicata;
- il diff `development -> main candidate` non contiene materiale estraneo;
- i soli file canonici di gestione/orchestrazione root elencati qui sotto
  (`AGENTS.md`, `START.md`, `ROADMAP.md`, `PROJECT_STATE.json`,
  `ARTIFACT_INDEX.json`) restano nella root locale, sono coperti da `.gitignore`
  e non risultano più tracked nella main-candidate;
- se materiale sensibile/nonredistribuibile è già presente nella storia Git,
  non si riscrive la history autonomamente: si termina con un Human Gate
  specifico per la bonifica della history.

I file canonici di gestione/orchestrazione root da trattare in questo modo sono
**esclusivamente**:

```text
AGENTS.md
START.md
ROADMAP.md
PROJECT_STATE.json
ARTIFACT_INDEX.json
```

P9 deve lasciare tutti e cinque fisicamente nella root del workspace, aggiungerli
a `.gitignore` e rimuoverli dal main-candidate tracking senza spostarli,
cancellarli o raccoglierli sotto `development/`. Devono restare disponibili
nella root locale per la governance, l'orchestrazione, la state cache e il routing
degli artefatti nelle fasi successive, ma non devono essere pubblicati nel futuro
`main`.

Non estendere questo elenco per analogia o interpretazione ad altri file della root.
Qualunque ulteriore file candidato a essere trattato come governance/orchestrazione
richiede una decisione esplicita dell'Utente.

**STOP_IF**

La candidate pubblica dipende ancora da un file ignorato/privato oppure non è
possibile dimostrare l'assenza di protected/nonredistributable material.

**NEXT**

P10.

---

## P10 — Final technical documentation reconciliation

**PURPOSE**

Secondo passaggio della closure pubblica. Aggiornare la documentazione pubblica per
descrivere con coerenza narrativa e stilistica il driver self-contained ormai
qualificato.

Il riferimento editoriale è la documentazione esistente nel ramo `main`.
Non riscrivere per gusto personale e non mutilare contenuto ancora corretto.

**PRIMARY_ARTIFACT**

Public documentation set candidata, destinata a essere verificata end-to-end da P11.

**RULES**

- osservare la documentazione del ramo `main` prima di modificare;
- rimuovere soltanto contenuto realmente divenuto obsoleto;
- lasciare invariato ciò che resta tecnicamente corretto;
- riscrivere le sezioni che descrivono il vecchio bundle/Windows prerequisite
  quando il nuovo comportamento le rende false;
- aggiungere le nuove parti necessarie su self-initialization, state-v2,
  pairing, Windows coexistence, migration, rollback, security e validation;
- mantenere tono, struttura, cross-linking e livello tecnico della
  documentazione esistente;
- aggiornare `TECHNICAL_MANUAL.md` solo con conoscenza tecnica stabile e
  provata, mai con cronaca dei tentativi;
- aggiornare gli altri documenti pubblici solo dove il nuovo comportamento li
  rende incompleti o obsoleti;
- vietate riduzioni massive o riscritture non necessarie.

**EXIT_GATE**

`FINAL_DOCUMENTATION_AND_RELEASE_READINESS=PASS` solo se:

- README, installation, uninstall/recovery, security, validation, licensing,
  device-material/migration references, learning docs e technical manual sono
  reciprocamente coerenti;
- nessun documento pubblico richiede ancora Windows Material Builder per un
  fresh install;
- le limitazioni ancora reali sono dichiarate;
- i claim `PROVEN`, `INFERRED` e support scope coincidono con le evidenze;
- link e document index sono validi;
- nessun contenuto tecnico attuale è stato perso senza ragione.

**NEXT**

P11.

---

## P11 — Clean-VM user lifecycle and release-candidate closure

**PURPOSE**

Qualificare come ultimo passaggio la release candidate dal punto di vista di un normale
utente Fedora, usando una VM Fedora 44 KDE pulita e il reader fisico presente
per l'intera sequenza.

P11 non è una matrice esaustiva di combinazioni artificiali: deve verificare in
ordine il lifecycle realmente documentato e utilizzabile dall'utente, senza
ripetere P8 e senza introdurre scenari non necessari.

La prova deve seguire alla lettera le istruzioni pubbliche della release candidate
come risultano dopo P9 e P10. Non sostituire i comandi documentati con scorciatoie,
comandi di sviluppo o procedure ad hoc: eventuali failure di istruzioni, riferimenti,
sequenza o aspettative documentate sono failure reali della candidate e vanno corrette
prima di riprendere P11.

**PRIMARY_ARTIFACT**

Bounded clean-VM user-lifecycle evidence per installazione, uso, update,
rimozione normale, reinstallazione e rimozione di emergenza.

**TEST ENVIRONMENT**

- VM Fedora 44 KDE x86_64 pulita;
- SELinux Enforcing e stack Fedora stock;
- nessuna precedente installazione del progetto;
- nessun legacy five-file Windows material bundle;
- reader Goodix 27c6:5125 presente tramite USB passthrough dall'inizio alla
  fine della sequenza;
- test eseguiti sulla release candidate del branch operativo corrente;
- installazione, update, uso e rimozione eseguiti seguendo le istruzioni ufficiali
  del repository così come risultano dopo P9 e P10.

**TEST SEQUENCE**

Eseguire in questo ordine e fermarsi alla prima failure non spiegata:

1. **Installazione canonica**
   - seguire alla lettera la procedura di installazione pubblicata nel repository
     sulla VM pulita con reader presente;
   - la fresh install deve completarsi senza Windows Material Builder e senza
     legacy material bundle.

2. **Uso reale**
   - usare il lettore tramite lo stock stack Fedora/KDE per confermare che la
     fresh install produce un sistema biometrico realmente operativo;
   - non ripetere l'intera qualificazione P8: basta un uso ordinario
     rappresentativo e conclusivo.

3. **Update canonico**
   - seguire alla lettera la procedura di update pubblicata nel repository sulla installazione
     funzionante, sempre con reader presente;
   - l'update deve completarsi senza compromettere lo stato operativo,
     password o desktop.

4. **Disinstallazione canonica normale**
   - seguire alla lettera la procedura di disinstallazione normale pubblicata nel
     repository, incluso `goodix-uninstall` da una normale sessione desktop;
   - la rimozione deve togliere il progetto dal critical authentication path
     preservando state-v2 e fingerprint templates e senza scrivere sul reader.

5. **Reinstallazione canonica**
   - seguire alla lettera la procedura pubblicata per reinstallare dopo la rimozione precedente,
     sempre con reader presente;
   - la reinstallazione deve riutilizzare correttamente lo stato preservato e
     non deve richiedere il legacy material bundle.

6. **Disinstallazione di emergenza da TTY**
   - seguire alla lettera il percorso TTY documentato nel repository ed eseguire
     `goodix-force-remove`;
   - la rimozione deve completarsi con il reader presente, preservare
     state-v2 e fingerprint templates, non scrivere sul reader e lasciare
     password/desktop recuperabili secondo il normale percorso Fedora.

Non aggiungere a P11 una matrice reader-presente/reader-assente, rollback verso
uno schema precedente, migration matrix separata o prove artificiali
preserve/purge: non fanno parte di questa qualificazione lineare salvo che una
failure reale renda necessaria un'analisi specifica.

**EXIT_GATE**

`SELF_CONTAINED_RELEASE_CANDIDATE=PASS` solo se l'intera sequenza precedente
è PASS e:

- la fresh install su VM pulita funziona senza Windows Material Builder,
  USBPcap, DPAPI recovery o five-file material bundle;
- il normale uso biometrico funziona dopo la fresh install;
- il percorso update funziona con reader presente;
- `goodix-uninstall` funziona con reader presente e non provoca writer sul
  reader;
- la reinstallazione dopo rimozione normale funziona usando lo stato
  preservato;
- `goodix-force-remove` da TTY funziona con reader presente e non provoca
  writer sul reader;
- state-v2 e fingerprint templates restano preservati attraverso entrambe le
  rimozioni;
- password e desktop restano disponibili e recuperabili lungo l'intero
  lifecycle;
- nessun lifecycle operation introduce firmware/IAP/ClearApp/OTP/factory-data
  write o altra mutazione persistente inattesa del reader;
- la documentazione ufficiale risultante da P10 è sufficiente e corretta per
  completare l'intero lifecycle senza conoscenza privata o istruzioni aggiuntive.

**NEXT**

`MILESTONE_COMPLETE: SELF_CONTAINED_GOODIX_27C6_5125`

La modifica/merge del ramo `main` e la pubblicazione della release restano una
decisione umana separata; non costituiscono una fase tecnica successiva della
roadmap.


---

## P12 — Enrollment robustness v2 and adaptive coverage qualification

**STATUS:** ACTIVE — REOPENED DEVELOPMENT

**WHY THIS PHASE EXISTS**

Real use has exposed a material biometric-quality defect in the current
enrollment policy: a formally successful template can still produce legitimate
`score=0` results when the same enrolled finger is presented at a position not
sufficiently represented by the stored samples. The effect is especially visible
with a small finger, but it has also been observed on an adult enrolled finger.

This is not accepted as an operator-placement limitation. The enrollment policy
must teach a sufficiently rich representation of the finger before declaring
success.

**EVIDENCE BASIS**

- On the qualified Linux target, the current template has eight stored SIGFM
  samples and legitimate verification attempts have produced `score=0` against
  every sample even with a real image and substantial keypoint count.
- On the same target and same software stack, correctly positioned contacts can
  score hundreds or thousands, so lowering the verification threshold is not an
  appropriate response to a true zero-overlap result.
- The current project diversity selector is explicitly derived from Rockytkg's
  enrollment selector and preserves its `3/8` accepted-stage bounds, raster
  MAD<8 duplicate test and two-duplicate early-convergence rule.
- Rockytkg's current 27c6:5125/5135 driver likewise uses
  `GF_ENROLL_MIN_STAGES=3`, `GF_ENROLL_MAX_STAGES=8` and
  `GF_ENROLL_DUP_STOP=2`. These values are a host-side policy choice; they are
  not evidence of an APP12509 hardware limit.
- Microsoft Windows Biometric Framework enrollment is adaptive:
  `WinBioEnrollCapture()` may return `WINBIO_I_MORE_DATA` and request further
  samples until the engine can build a satisfactory template; WBF also exposes
  capture rejection reasons for position, skew, size and quality. There is no
  project evidence supporting a universal fixed Windows enrollment count.
- User observation on this exact reader under Windows Hello is consistent with
  that adaptive model: enrollment commonly requests substantially more than
  eight contacts and may continue beyond twenty when the engine is not
  satisfied.
- The Fedora/libfprint Goodix MOC reference itself uses device-dependent enroll
  counts, including 12 stages for numerous Goodix product IDs. Eight is therefore
  not a universal Goodix constant.
- Existing target-local project evidence records 21 successful primary stages
  for this APP/profile. That observation must be re-examined as protocol
  evidence instead of being overridden by the Rockytkg-derived eight-stage
  host policy.

Useful corroboration:

- Microsoft `WinBioEnrollCapture`:
  https://learn.microsoft.com/en-us/windows/win32/api/winbio/nf-winbio-winbioenrollcapture
- Microsoft biometric reject-detail constants:
  https://learn.microsoft.com/en-us/windows/win32/secbiomet/winbio-reject-detail-constants
- Rockytkg 27c6:5125/5135 enrollment policy:
  https://github.com/Rockytkg/goodix-linux-27c6-5125/blob/227eba219fa9e3fbac5bd59aca79f624f67cd11b/src/goodixgf.c
- Local Goodix MOC reference:
  `reference/libfprint-fedora44-1.94.100/source/libfprint/drivers/goodixmoc/goodix.c`

**PRIMARY_ARTIFACT**

Enrollment-policy implementation, offline qualification evidence and a bounded
live requalification plan.

### P12.1 — Preserve verification strictness

Do not lower the verification/matching threshold to mask `score=0` outcomes.
A zero score means the current probe did not establish useful SIGFM overlap with
the enrolled samples. Fix enrollment coverage first.

**EXIT:** current verification threshold and wrong-finger rejection behavior are
preserved while enrollment work proceeds.

### P12.2 — Remove premature Rockytkg-style convergence

Retire the rule that can finish enrollment after only three distinct samples
followed by two duplicate-like contacts.

A repeated placement is not evidence that the finger has been sufficiently
covered. Duplicate or near-duplicate contacts must not advance useful coverage
and must never cause early success merely because the user repeated the same
pose.

**EXIT:** no enrollment can complete because repeated placement is interpreted
as convergence.

### P12.3 — Enrollment Diversity v2

Replace raster-MAD-only diversity with an evidence-led host policy. Evaluate at
minimum:

- SIGFM extraction quality and keypoint count;
- spatial distribution of keypoints across the 80×64 image;
- incremental spatial/feature coverage relative to already accepted samples;
- duplicate and near-duplicate detection;
- rejection/retry of captures that add insufficient new information;
- explicit accounting of accepted samples versus physical contacts.

The design must remain bounded, observable and free of hidden sensor-reaching
retries.

**EXIT:** offline tests prove that repeated near-identical captures do not
artificially increase coverage while meaningfully displaced captures do.

### P12.4 — Adaptive template richness, not a fixed eight-frame target

Do not replace `8` with another arbitrary universal constant.

Enrollment completion must be driven by demonstrated sample quality and
coverage, with a defensible minimum floor and a bounded safety ceiling selected
from evidence. Qualification must explicitly evaluate richer templates around
12, 16, 20 and, if required, beyond 20 accepted contacts.

The current SIGFM/libfprint container boundary of up to 21 sample envelopes is
an implementation constraint to inspect, not a biometric target. If evidence
shows that robust enrollment needs more than the current container permits,
that structural boundary must be analyzed explicitly rather than silently
treating 21 as sufficient.

**EXIT:** the chosen completion policy is justified by measured recognition
robustness and false-accept safety, not by inheritance from Rockytkg.

### P12.5 — Determine the real APP12509 single-action boundary

Do not assume an eight-stage APP12509 limit.

First qualify, on the exact `27c6:5125 / GF_ST411SEC_APP_12509` target, how
many clean enrollment contacts the existing protocol graph can execute in one
libfprint enrollment action. Reconcile this with the historical target-local
21-primary-stage observation.

No firmware, IAP, ClearApp, OTP, factory-data or unrelated persistent write is
permitted during this investigation.

**HUMAN GATE:** any sensor-reaching experiment required by this item is prepared
offline first and then stopped at `HUMAN_REQUIRED` for operator execution.

**EXIT:** the actual target boundary is OBSERVED/PROVEN, not inferred from
Rockytkg.

### P12.6 — Multi-epoch enrollment only if target evidence requires it

A multi-epoch design is a fallback, not the starting assumption.

Only if P12.5 proves a real per-epoch device/protocol ceiling below the desired
host-template richness may one logical fprintd enrollment span multiple clean
Goodix acquisition epochs:

1. collect a bounded acquisition epoch;
2. complete release/STOP/drain;
3. begin a fresh clean acquisition epoch;
4. continue accumulating host-side SIGFM coverage;
5. serialize one final host template.

Pairing/state material must be reused normally; the fallback must not introduce
additional persistent writes.

**EXIT:** either single-action enrollment is sufficient, or the need and safety
of multi-epoch enrollment are demonstrated explicitly.

### P12.7 — Real-user biometric requalification

After the implementation is offline-clean, perform bounded live qualification
with deliberately varied placement.

At minimum include:

- adult index finger;
- small/child finger where practical;
- thumb as a larger-area reference;
- center, left, right, high, low and moderately rotated placements;
- deliberately repeated near-identical contacts during enrollment;
- correct-finger first-touch recognition rate;
- legitimate `score=0` incidence;
- wrong-finger rejection and false-accept safety;
- verify and identify;
- Plasma Login, KScreenLocker, sudo and PolicyKit regression checks;
- Windows coexistence and pairing/TLS invariants;
- zero unintended persistent writes.

The live comparison must retain the old eight-sample behavior as a measurable
baseline wherever practical, rather than relying only on subjective impressions.

**EXIT_GATE**

`ENROLLMENT_ROBUSTNESS_V2=PASS` only if:

- the Rockytkg-derived premature-convergence policy is gone;
- enrollment collects demonstrably broader useful coverage;
- legitimate first-touch `score=0` / NO_MATCH incidence is materially reduced;
- wrong-finger rejection is not weakened;
- verify/identify and Fedora authentication consumers remain correct;
- no new firmware/OTP/factory/persistent-state risk is introduced;
- the target's true enrollment-stage boundary is documented from evidence;
- Windows interoperability remains intact.

**STOP_IF**

- a proposed change weakens matching safety merely to increase acceptance;
- a hidden or unbounded retry/acquisition loop is introduced;
- live work would cross a persistent-write or hardware boundary without the
  required Human Gate;
- APP12509 behavior is asserted from Rockytkg or Windows analogy instead of
  target evidence.

**NEXT**

`MILESTONE_COMPLETE: ENROLLMENT_ROBUSTNESS_V2`
