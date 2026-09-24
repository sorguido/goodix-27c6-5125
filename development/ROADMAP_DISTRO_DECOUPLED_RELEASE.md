# Roadmap — Distro-Decoupled Goodix 27c6:5125 Release

> **Status:** ACTIVE
>
> **Scope:** guida vincolante per l'architettura production/release e per
> l'orchestrazione AI PM / AI Executor sul branch **main**.
>
> **Decisione Utente:** un normale aggiornamento Fedora/libfprint può rendere
> temporaneamente indisponibile il fingerprint e richiedere la reinstallazione
> del driver. Non è accettabile che possa compromettere login con password,
> desktop, sudo, PolicyKit o richiedere TTY/recovery per rendere di nuovo
> accessibile il PC.

---

## Stato corrente — R6/R7 autorizzata (23 settembre 2026)

Il prompt Utente `CODEX_R6_R7_FINAL_PUBLIC_RELEASE.md` ha autorizzato la
preparazione finale R6/R7, ora consolidata su `main`, che è l'unico branch
operativo. R4 resta funzionalmente PASS;
normal uninstall e reinstallazione sono PASS riferiti. L'Utente riferisce ora
anche reinstallazione corretta con lettore UP/presente. Il force-remove TTY è
riferito funzionante; output e inventario finale completi restano incompleti.
Non si inventano altre osservazioni e non si ripete la precedente procedura VM.

Il deliverable corrente è un albero interamente pubblico eccetto la directory
`development/`, con un solo installer root `install.sh`. Governance, evidenze,
manuale interno e materiale non pubblico sono sotto `development/`. La precedente
allowlist è eliminata. La history privata resta intatta, non pubblicata e non
necessaria a build, test o installazione. La normale modifica/commit/push
autonoma avviene su `main` secondo `development/AGENTS.md`; operazioni sul
repository pubblico restano soggette ad autorizzazione esplicita dell'Utente.

Il nuovo percorso compila da sorgente pubblica, importa i cinque materiali da
`$HOME/goodix-5125-materials` e installa runtime, selector Plasma e comandi
standalone di rimozione. Il sensore resta presente. L'AI completa implementazione,
test sintetici e simulazione senza directory interna/history, poi si ferma prima
della **installazione fisica eseguita dall'Utente** con la procedura pubblica.
Questa è la deroga circoscritta alla precedente regola VM-only; non autorizza
sudo, accesso USB, materiali reali protetti o live autonomi dell'AI.

Lo stato implementativo e le evidenze correnti sono nel
[manuale canonico](<Goodix 27c6 5125 manuale tecnico.md>). Il loader C ha accettato
due bundle sintetici distinti; la compilazione nativa completa libfprint/payload
non è stata eseguita nell'ambiente corrente per dipendenze Fedora mancanti.
Closure offline consolidata il 24 settembre: 338 file pubblici, 112 test PASS,
18 documenti/59 link verificati e review indipendente accettata. Il dettaglio
è in [PUBLIC_TREE_AUDIT.md](PUBLIC_TREE_AUDIT.md).
La qualifica fisica del nuovo percorso è pendente, non implicita nei test.

L'URL pubblico corrente non contiene ancora il nuovo installer. L'Utente deve
pubblicare la copia dell'albero pronto prima che il blocco clone/install possa
scaricarlo. L'AI non pubblica e non sostituisce tale prerequisito con path,
branch o artefatti privati. La preparazione offline non equivale a disponibilità
online o release fisicamente qualificata.

## 1. Principio architetturale

Il driver possiede il sensore. Fedora possiede Fedora.

Target:

~~~text
Goodix 27c6:5125
        ↓
driver/libfprint Goodix
        ↓
libfprint privata o integrata
        ↓
fprintd FEDORA STOCK
        ↓
PAM / KDE / sudo / PolicyKit FEDORA STOCK
~~~

L'esito massimo accettabile di un normale aggiornamento di un componente
biometrico è:

~~~text
fingerprint non disponibile
→ password/login/desktop/sudo/PolicyKit restano normali
→ reinstallazione o aggiornamento del driver
~~~

Non è accettabile:

~~~text
aggiornamento Fedora/KDE/PAM/systemd
→ login grafico o password compromessi
→ sudo/PolicyKit compromessi
→ TTY/recovery necessaria
→ ricompilazione privata di componenti desktop/login necessaria
~~~

---

## 2. Invarianti permanenti di release

Salvo nuova decisione esplicita dell'Utente:

- niente build privata/distribuita di plasmalogin;
- niente sostituzione del Plasma greeter;
- niente copia congelata del PAM vendor mascherata da override persistenti del progetto;
- un'eventuale integrazione PAM necessaria al fingerprint di Plasma Login deve
  essere minima, reversibile, vendor-aware e fail-safe: non può modificare file
  package-owned, non può congelare una copia del vendor e un update Fedora non
  può trasformare il failure in qualcosa di più grave del solo fingerprint;
- niente moduli/override custom per sudo o PolicyKit come requisito di release;
- niente fprintd custom se il fprintd Fedora stock può essere usato;
- niente pin di versione/hash Fedora come requisito runtime per l'accessibilità
  del sistema;
- niente sostituzione di ExecStart di servizi critici se un normale update
  può trasformare il failure in qualcosa di più grave del solo fingerprint;
- niente correzione privata permanente di bug KDE/Plasma/systemd/PAM: preferire
  limitazione documentata o fix/upstreaming;
- nessun file package-owned Fedora viene modificato direttamente;
- nessun uninstall/update del driver deve richiedere la cancellazione dei
  template biometrici salvo esplicita incompatibilità del formato template;
- i materiali device/factory-preserving restano separati dal runtime software.

Qualunque componente che possa trasformare un update Fedora in un failure di
login/password/desktop/sudo/PolicyKit è un **RELEASE_BLOCKER**.

---

## 3. Baseline di sicurezza — R0 completata

La bonifica del target fisico ha riportato il percorso critico a componenti
Fedora/KDE stock:

~~~text
plasmalogin        = Fedora stock
Plasma greeter     = Fedora stock
plasmalogin PAM    = Fedora stock
KScreenLocker PAM  = Fedora stock
sudo password      = PASS post-reboot
PolicyKit          = Fedora stock
fprintd ExecStart  = /usr/libexec/fprintd
Goodix processes   = none
~~~

I residui software storici sono stati rimossi.

Materiale da preservare:

~~~text
/var/lib/goodix-5125-poc/
~~~

I template sotto /var/lib/fprint/ non vengono cancellati per ragioni di
bonifica host.

Lo stato authselect corrente è valido e non abilita fingerprint nello stack
globale. La sua provenance pre-progetto può essere ricostruita separatamente;
non costituisce motivo per reintrodurre automaticamente with-fingerprint.

---

## 4. Regola VM-only e deroga finale esplicita R6/R7

**Deroga corrente:** la decisione Utente del 23 settembre 2026 autorizza il
prossimo gate sul Fedora fisico, eseguito dall'Utente tramite la sola procedura
pubblica dopo closure offline. L'AI può eseguire build e test offline sintetici
non privilegiati nello scope autorizzato; non installa dipendenze/runtime e
non avvia USB, sudo o live. Non si prepara un ulteriore giro VM come prerequisito
non richiesto. Tutte le invarianti factory e gli altri gate restano immutati.

La regola generale precedente, riportata sotto per gli altri task, continua ad
applicarsi fuori da questa deroga. I valori VM-only seguenti descrivono tale
regola generale, non annullano l'eccezione esplicita corrente.

Dopo la bonifica R0, il target fisico Fedora è una baseline di sicurezza e non
è più il banco di prova del progetto.

Da questo punto in avanti:

- nessuna nuova installazione, patch runtime, modifica PAM/systemd, test di
  update-survivability o live validation sul Fedora fisico;
- build/install/test/runtime/update-survivability si eseguono sulla VM;
- l'eventuale pass-through USB del sensore reale alla VM resta soggetto ai
  normali Human Gate e alle invarianti factory-preserving;
- il Fedora fisico resta il workspace dell'AI per sviluppo sul repository,
  audit, documentazione e verifiche offline consentite che non mutino il
  runtime host;
- modifiche Git/documentali al repository non sono considerate mutazioni del
  runtime host, ma nessun artefatto prodotto può essere installato sul target
  fisico senza nuova decisione esplicita.

~~~text
PHYSICAL_HOST_RUNTIME_MUTATION=false
VM_ONLY_RUNTIME_VALIDATION=true
AI_SOURCE_WORKSPACE=PHYSICAL_FEDORA
AI_VM_ACCESS_REQUIRED=false
VM_EXECUTION=HUMAN_ONLY_AFTER_GATE
VM_REPOSITORY_SYNC=USER_PULL_MAIN
~~~

La VM non è un ambiente al quale l'AI deve accedere direttamente. Quando il
lavoro richiede build, installazione, runtime, live o update-validation in VM:

1. l'AI prepara, verifica nello scope offline consentito e committa su
   `main` tutto il necessario per la prova;
2. termina con `HUMAN_REQUIRED`, consegnando comandi ed evidenze attese;
3. l'Utente esegue manualmente il pull di `main` nella VM;
4. l'Utente esegue la prova e restituisce evidenze/output;
5. l'AI riprende dal repository e dagli output forniti.

La mancanza di accesso diretto dell'AI alla VM non è un blocker. Non si cerca
un accesso alternativo e non si ripete una prova già chiusa solo perché l'AI
non l'ha eseguita direttamente. Restano invariati i gate su privilegi, USB,
materiali protetti e factory state.

---

## 5. Architettura precedente — REJECTED / HISTORICAL ONLY

La precedente candidate managed e le sue integrazioni host sono preservate come
evidenza e sorgente di apprendimento, ma non sono più una base production.

Sono escluse dalla nuova architettura release le soluzioni che includono o
richiedono:

- daemon plasmalogin ricompilato;
- greeter custom;
- PAM plasmalogin custom che replica/congela il vendor o costruisce uno stack
  parallelo permanente; resta ammissibile soltanto l'eventuale integrazione
  minima e safety-bounded esplicitamente autorizzata da R4 per ottenere il
  fingerprint login richiesto;
- PAM KScreenLocker custom;
- bridge/moduli custom sudo;
- bridge/moduli custom PolicyKit;
- fprintd custom quando non strettamente necessario;
- snapshot/pinning esatti di componenti Fedora per mantenere funzionante il PC;
- recovery TTY come parte del normale lifecycle; è invece ammesso un solo
  percorso **emergency-only**, documentato e a comando singolo, che rimuove gli
  artefatti project-owned quando il login grafico non è più raggiungibile.

Codice, test e documentazione storici non vanno cancellati soltanto perché
l'architettura è stata respinta. Devono però essere marcati e trattati come
**HISTORICAL_ONLY / REJECTED_ARCHITECTURE** e non possono essere selezionati
dall'AI PM come base della nuova candidate.

---

# Roadmap operativa

## R1 — Congelare la vecchia architettura nel repository

**Obiettivo:** impedire che l'orchestrazione AI riprenda accidentalmente la
candidate respinta.

Attività:

- marcare la managed candidate e i percorsi Plasma/PAM/sudo/PolicyKit custom
  come architettura respinta/storica;
- rimuoverli dalla roadmap production attiva;
- preservare evidenze, test e provenance utili;
- aggiornare documentazione canonica dove necessario;
- non cancellare storia utile.

**Exit criteria:**

~~~text
OLD_MANAGED_ARCHITECTURE=HISTORICAL_ONLY
PLASMA_PRIVATE_RUNTIME=OUT_OF_PRODUCTION_SCOPE
CUSTOM_AUTH_CONSUMERS=OUT_OF_PRODUCTION_SCOPE
~~~

Nessuna live richiesta.

---

## R2 — Estrarre il runtime minimo già dimostrato

**Obiettivo:** recuperare dal lavoro D282/D293 e dal production tree soltanto
ciò che serve a far funzionare il sensore attraverso libfprint.

Auditare e separare:

- driver Goodix 27c6:5125;
- libfprint Goodix/SIGFM;
- librerie runtime strettamente necessarie;
- accesso read-only/controllato ai materiali preservati in
  /var/lib/goodix-5125-poc/;
- eventuali regole udev realmente necessarie.

Escludere per default:

- fprintd custom;
- pam_fprintd custom;
- greeter;
- plasmalogin;
- sudo;
- PolicyKit;
- KScreenLocker;
- account lifecycle hook non indispensabili al driver.

**Deliverable obbligatorio prima di qualunque live:**

~~~text
MINIMAL_RUNTIME_CONTENTS
HOST_FILES_TOUCHED
WHY_EACH_FILE_IS_NECESSARY
FEDORA_COMPONENTS_REPLACED=NONE
EXPECTED_UPDATE_FAILURE=FINGERPRINT_ONLY
~~~

Nessuna live richiesta.

---

## R3 — Integrazione minima con fprintd Fedora stock

**Stato: COMPLETATA al confine biometrico (22 settembre 2026).** Enrollment
stock PASS e verify stock MATCH al primo tentativo, con cleanup completo,
riportati dall'Utente e riesaminati nel manuale tecnico. Runtime/template
conservati; indice DESTRO nello slot left-index-finger resta mismatch noto di
laboratorio mantenuto nella fase R4 per decisione Utente. Nessuna qualifica
R4/R5 o release è implicata; non ripetere le live R3 già chiuse.

Valutare le opzioni in questo ordine e passare alla successiva soltanto se la
precedente è esclusa da evidenza tecnica.

### R3-A — Private libfprint + environment drop-in

Prima scelta.

Concetto:

~~~ini
[Service]
Environment=LD_LIBRARY_PATH=/path/runtime-goodix
~~~

Fedora continua a possedere ExecStart e il proprio /usr/libexec/fprintd.

### R3-B — Wrapper minimale attorno al fprintd Fedora

Consentito soltanto se R3-A non è sufficiente.

Il wrapper può impostare environment/runtime e poi deve eseguire il fprintd
Fedora. Non può sostituire il daemon con una build privata.

### R3-C — Installazione/sostituzione libfprint di sistema

Ultima scelta pragmatica.

È accettabile soltanto con questo failure model:

~~~text
update libfprint
→ driver Goodix sovrascritto/non disponibile
→ fingerprint FAIL
→ password e desktop PASS
→ reinstall driver
~~~

Non è accettabile alcun effetto ulteriore.

**Gate R3:** review offline dell'architettura prima della prima installazione in
VM.

**Decisione Utente sui tentativi stock:** Fedora stock determina il numero di
tentativi espliciti. Il driver non impone un limite cumulativo di capture per
logical open/Claim: dopo clean NO_MATCH e cleanup completo, una nuova action
VERIFY/IDENTIFY esplicita può acquisire normalmente una volta. Il contatore,
se presente, è soltanto telemetria. MATCH resta terminale per il Claim dopo
il cleanup necessario; processing error/`FP_DEVICE_RETRY` non deve consentire
nuova acquisizione di materiali, USB claim o transport submission alla
risottomissione automatica. Un nuovo Claim/open riparte da stato fresco.
Nessuna modifica a fprintd/PAM/CLI stock. Il gate iniziale era limitato ai test
sintetici VM senza sensore; la successiva qualifica R3 è ora completata come
riportato sopra. La semantica dei tentativi resta invariata.

---

## R4 — Consumer di autenticazione: stock-first, login Plasma richiesto

**Stato: CHIUSA sulla baseline VM provata (23 settembre 2026). KScreenLocker,
sudo ordinario, PolicyKit e Plasma Login opt-in = SUPPORTED_ON_TESTED_BASELINE.**
Lo stop dell'handoff `CODEX_CLOSE_R4_PLASMA_LOGIN_PASS_STOP_BEFORE_R5.md` è
storico, superato dalla decisione R5 del 23 settembre riportata sotto.

**Decisione Utente (23 settembre 2026):** il fingerprint al login grafico Plasma
è una funzione richiesta della release. L'assenza del percorso biometrico stock
non è una `KNOWN_LIMITATION` accettabile per chiudere R4 e non autorizza il
passaggio a R5. Il vincolo distro-decoupled resta però invariato: la soluzione
non può compromettere password, desktop o recovery ordinaria e non può congelare
componenti Fedora.

~~~text
PLASMA_LOGIN_FINGERPRINT_REQUIRED=true
PLASMA_LOGIN_KNOWN_LIMITATION_ACCEPTABLE=false
R4_CLOSED=true
R5_LOGIN_ENTRY_CONDITION=SATISFIED
R5=AUTHORIZED_CURRENT_PHASE
STOP_BEFORE_R5=false
NEXT_STATE=R5_REMOVAL_QUALIFICATION
~~~
Per KScreenLocker, password unlock a lettore assente e fingerprint unlock al primo contatto senza password,
cleanup drained/closed, servizio inactive/MainPID 0 e lettore scollegato sono
riportati dall'Utente e accettati. Nessuna modifica PAM/authselect necessaria;
runtime/template mantenuti e test completato da non ripetere.
Review SELinux chiusa nello scope provato: dopo lookup viewer NOT_FOUND, la
query mirata riporta tre AVC fprintd/read su nr_hugepages, sysctl_vm_t,
permissive=0, alle 09:04:02, 09:04:32 e 09:06:14 CEST. L'ultimo coincide con
lo sblocco riuscito: diniego non fatale per questo percorso, documentato senza
modifiche SELinux o attribuzione a un callsite non provato. Non è innocuità
universale né qualifica R5. Query audit e live sono completate, da non ripetere.
**Preflight sudo PASS** a `168469b79565cf401f2cb256448c184f3a803d8c`:
sudo Fedora → system-auth con pam_fprintd sufficient e fallback pam_unix;
profilo valido con fingerprint già attivo, nessun selettore custom/NOPASSWD
emerso e verifica RPM sudo exit 0. Password/query completata a lettore assente.
Lo snapshot storico del preflight active/running/PID 3802 era
compatibile con attivazione stock e idle timeout; non è cleanup live fallito.
Raw AVC nr_hugepages, stesso PID alle 09:55:15 CEST, non fatale per la
query; nessuna modifica SELinux o ripetizione diagnostica.

**Live sudo ordinaria PASS** dalla guida `deployment/minimal-runtime/R4_SUDO_VM.md`,
guest riportato `f5a4430` (risolto localmente a
`f5a4430b50a24dc7247b455701ba35ffc582713c`): password reale con lettore assente,
poi `sudo -k -- /usr/bin/true` exit 0, MATCH al primo contatto dell'indice DESTRO,
nessuna password durante B. Una VERIFY/epoch, cleanup drained/closed, zero
retry/reopen/reset/persistent; ultimo stato inactive/MainPID 0, lettore detached.
release_tail=0/single_terminal=0 compatibili con ritorno anticipato PAM al MATCH.
Nessuna patch PAM/sudoers/runtime, rollback o ripetizione del test riuscito.
Avviso SELinux dello stesso tipo riferito anche durante il PASS; nessun nuovo
raw AVC/timestamp allegato, i metadata precedenti restano riferiti al preflight.

**Decisione sudo -i:** auth CONFIGURATION_COVERED tramite include sudo osservato
e PASS ordinario; login shell/session UNTESTED, nessun SUPPORTED esteso a quella
variante. Non serve una live aggiuntiva per il confine biometrico R4 senza nuova
evidenza di una differenza pertinente.

**Preflight PolicyKit configurazione PASS** a
`b674dd8842cf336e6d74ec81070498879b856330`: polkit-1 stock include system-auth,
pam_fprintd sufficient e successivo fallback pam_unix, agente KDE attivo,
authority/helper stock e RPM polkit/polkit-kde exit 0. Nessuna autenticazione
PolicyKit. Il supplemento successivo è completato al checkout riportato
`d5e890b`: POLICY_FILES=0 nelle tre sedi PKLA, verifica pkla-compat exit 0,
raccolta dei corpi delle regole confermata dall'Utente (riepilogo nell'handoff).
Nessun override legacy emerso; default wheel corroborato. Lo snapshot fprintd
active/running/PID 8053 del supplemento dopo sudo senza lettore è storico e
compatibile con attivazione stock, non failure da ripulire. PID 6749 resta lo
snapshot del preflight iniziale; entrambi superati dal cleanup live sotto.

**Query azione PASS** a `0d8ccb7482fb10d7520f8830f59fb2e979c04380`:
`/usr/bin/true` risolve a sé stesso, nessuna azione annotata concorrente,
selezione `org.freedesktop.policykit.exec`, default auth_admin in tutti i casi.
Sensore assente, nessun sudo/autenticazione/modifica; nessuna nuova misura
fprintd. Preflight completato: non ripetere query, supplemento o catalogo.
Non sono emersi grant automatici di questa azione dalle regole riportate;
la successiva prova nativa ha confermato una richiesta reale per guido.

**Live PolicyKit stock PASS**, handoff `CODEX_HANDOFF_R4_POLKIT_PASS.md`, guida
`deployment/minimal-runtime/R4_POLKIT_VM.md` al commit riportato `8ed5218`
(risolto localmente a `8ed52181897c4078dfb2be26fe67481e7a7b6961`; nessuno SHA
checkout guest stampato nell'handoff). Per la stessa azione exec su /usr/bin/true:
password reale nel dialogo KDE per guido con lettore assente ed exit 0; poi
indice DESTRO, MATCH al primo contatto senza password/input ed exit 0.
Autorizzazioni temporanee revocate e lista vuota prima di A/B; nessun cambio
identità/restart/seconda serie. Una VERIFY/epoch, nessun retry/reopen/reset o
famiglia persistente rilevata, cleanup drained/closed, fprintd inactive/MainPID 0,
sensore detached. release_tail=0/single_terminal=0 compatibili con ritorno
anticipato PAM al MATCH. Nessuna regressione desktop riportata. **PolicyKit =
SUPPORTED_ON_TESTED_BASELINE**; non ripetere. Runtime/template e inversa
mantenuti, nessuna patch/PAM/policy/SELinux change o rollback. L'handoff non
conferma una nuova ricorrenza SELinux PolicyKit: nessun nuovo evento dedotto.

**Preflight Plasma Login PASS come raccolta configurazione** al checkout guest
`725b3c1f8bf879b9e56632b4f15da494968cead7`: sessione KDE Wayland con
`Service=plasmalogin`; display manager stock `plasmalogin.service`; authselect
valido con `with-fingerprint`. Il PAM stock `/usr/lib/pam.d/plasmalogin`
entra in `password-auth`, che non contiene `pam_fprintd.so`; `fingerprint-auth`
e `system-auth` contengono invece il modulo biometrico. Review sorgenti/package
successiva: sulla baseline stock non emerge un servizio PAM biometrico alternativo
per il normale login né un accesso diretto a fprintd. La live biometrica stock
che non raggiungerebbe il sensore non va eseguita soltanto per confermare questa
assenza.

Questa evidenza **non chiude Plasma Login come limitation**. È il trigger per
riesaminare il boundary di integrazione mantenendo il requisito funzionale.
D295/02 resta una prova tecnica storica utile: dimostra che il gap può essere
colmato con un delta PAM minimo senza ricompilare plasmalogin, ma la sua copia
vendor persistente non è automaticamente accettabile come soluzione finale.

Ordine di progettazione obbligatorio:

1. cercare prima un meccanismo Fedora/PAM supportato che esponga il fingerprint
   a Plasma Login senza congelare file vendor;
2. se non esiste, progettare il più piccolo adapter/integrazione project-owned
   che deleghi al percorso vendor corrente e fallisca in modo fingerprint-only;
3. usare D295/02 soltanto come reference/proof-of-feasibility, non come scelta
   automatica;
4. ricorrere a modifiche più profonde di Plasma Login soltanto dopo esclusione
   documentata delle opzioni precedenti e nuova review.

Exit criteria funzionali/architetturali di R4 per Plasma Login:

~~~text
PASSWORD_LOGIN=PASS
PASSWORD_LOGIN_NO_FORCED_FINGERPRINT_WAIT=true
PLASMA_LOGIN_FINGERPRINT=PASS
MAX_PHYSICAL_CONTACTS_PER_SERIES=3
FEDORA_VENDOR_PAM_MODIFIED=false
FEDORA_VENDOR_PAM_FROZEN=false
UNINSTALL_RETURNS_TO_STOCK=true
TTY_RECOVERY_REQUIRED=false
~~~

La closure R4 accetta funzionalità sulla baseline osservata, composizione del
vendor corrente e modello di rimozione verificato nei test sintetici. Il limite
di tre contatti è imposto dal percorso stock; la live sotto ha usato un contatto,
non ha esercitato l'esaurimento/fallback né l'uninstall, che non va ripetuto su PASS.

Resta invariato il requisito di sicurezza della release:

~~~text
NORMAL_UPDATE_MAX_FAILURE=FINGERPRINT_ONLY
~~~

La closure R4 non prova compatibilità con aggiornamenti futuri. Il successivo
replan Utente sotto sostituisce la matrice update R5 con la qualifica di rimozione
e recovery; non attribuisce PASS empirici agli aggiornamenti.
Il rischio del contratto/path vendor resta visibile nell'audit: qualunque failure
A/B da normale update è RELEASE_BLOCKER; non è una limitation accettabile.

**Avanzamento del replan:** composizione supportata Linux-PAM tramite include
assoluti del vendor corrente, ma nessun selettore stock completo per la UX
richiesta nella baseline auditata. Preparata B minima in
`deployment/plasma-login-opt-in/`: un ingresso PAM del servizio login e piccolo
supporto project-owned esplicitamente inventariato, separato dal runtime R3.
Nessun file vendor copiato/congelato, daemon o greeter privato.
La decisione UX Utente accetta Invio vuoto come scelta esplicita fingerprint,
campo temporaneamente disabilitato durante la serie bounded e fallback al termine;
una password non vuota va subito al vendor senza attesa fingerprint.
La candidata disabilita solo l'opzione fingerprint su auth policy incompatibile
e include sempre il vendor corrente per password/account/session. Il reset del
prefisso è necessario anche per gli errori di modulo durante pam_setcred.

Dettagli e limiti in `docs/R4_PLASMA_LOGIN_INTEGRATION.md`. Il contratto del path
vendor corrente è una dipendenza di packaging: rimozione/relocation incompatibile
può rompere password e sarebbe un blocker classe A, mai una qualifica implicita
fingerprint-only. Nessuna prova R5 anticipata; il PASS login deriva dalla live sotto.

**Build/test VM PASS accettato** al source commit
`6fc6e640710885954d9e6fd603b3bc47b45d2ac6`: marker finale riportato
`PLASMA_LOGIN_VM_BUILD_TESTS=PASS`, 11 test Python OK; lo script completa prima
anche unità C e dispatcher libpam sintetico. Nessuna installazione/login.
Il primo STOP per pam-devel assente era pre-build, risolto dall'Utente nella VM.
Output conservato in
`development/build-artifacts/plasma-login-opt-in/goodix-login-build.OeCmF8Ja`,
escluso solo localmente tramite `.git/info/exclude`. Riutilizzare output e
manifest originali; nessuna rebuild o ripetizione dei test riusciti.

**Installazione VM PASS accettata**, guida checkout
`24c3018071e8d120687ff8fbd2f344cde620692d`, stesso source/output preservato:
manifest/source, installazione, bytes/metadata/receipt, cinque default-label
check, hash vendor invariato e worktree pulito riportati dall'Utente. Desktop
aperto, sensore assente, nessun logout/reboot/login; R3 runtime/template mantenuti.
Nessuna rebuild/reinstallazione o rollback su PASS. I default label da soli non
provavano il caricamento nel dominio helper; segue ora la prova funzionale reale.

**Live Plasma Login PASS accettata** da guida/checkout guest
`7d0e2d3bcd33dc1311f70cc26b0a72b6889acfbe`, preparazione PASS:
logout normale, password reale a sensore assente, desktop PASS senza richiesta
fingerprint o attesa forzata (ritardo circa zero riferito dall'Utente). Poi
secondo logout, un solo Invio vuoto e un contatto dell'indice DESTRO; desktop
raggiunto senza password, seconda serie o retry osservato. Una VERIFY/MATCH
terminale, epoch drained/closed, zero retry/reopen/reset/persistent e outstanding;
fprintd finale inactive/MainPID 0, sensore detached. release_tail=0/single_terminal=0
sono compatibili con ritorno PAM anticipato al MATCH, non failure automatico
né prova di quiescenza device. Telemetria completa nel manuale canonico.

Fallback B dopo failure **NOT_EXERCISED**, nessuna nuova live per provocarlo.
Integrazione, runtime R3/template e inverse mantenuti; nessun rollback, rebuild
o reinstallazione. Plasma Login **SUPPORTED_ON_TESTED_BASELINE**, R4 formalmente
chiusa. La guida `deployment/plasma-login-opt-in/R4_PLASMA_LOGIN_VM.md` è ora
evidenza completata, da non rieseguire. Il nuovo gate R5 riguarda soltanto
il lifecycle di rimozione/reinstallazione/recovery.

Una volta ottenuti:

~~~text
fprintd-enroll = PASS
fprintd-verify = PASS
~~~

il lavoro del driver è considerato completato al confine biometrico.

KDE, KScreenLocker, sudo e PolicyKit vengono qualificati sul percorso stock.
Plasma Login è **stock-first**, ma il fingerprint login è un requisito esplicito
della release: se il percorso stock non lo espone, si apre un replan della minima
integrazione sicura invece di chiudere il consumer come limitation.

Regola consumer:

~~~text
KSCREENLOCKER/SUDO/POLKIT stock PASS  → SUPPORTED
KSCREENLOCKER/SUDO/POLKIT stock FAIL  → KNOWN_LIMITATION / UPSTREAM_BUG
PLASMA_LOGIN stock fingerprint absent → REPLAN_REQUIRED
PLASMA_LOGIN fingerprint PASS safely  → SUPPORTED
~~~

Un consumer che non funziona non autorizza patch private indiscriminate. Per
Plasma Login è autorizzata soltanto la progettazione di un'integrazione minima,
reversibile e update-safe entro il boundary definito sopra.

Un eventuale bug VT di Plasma Login Manager può essere documentato/upstreamed
senza bloccare la release **solo se non impedisce gli exit criteria richiesti di
login password + fingerprint**. Se impedisce il fingerprint login, R4 resta
aperta finché non esiste una soluzione conforme al failure model.

---

## R5 — Removal & Emergency Recovery Qualification su VM

**Stato: precedente qualifica lifecycle, fase operativa superata dalla nuova
autorizzazione R6/R7.** R4 è formalmente chiusa e
`PLASMA_LOGIN=SUPPORTED_ON_TESTED_BASELINE`. Rimozione normale e reinstallazione
reader-present sono PASS riferiti; il force-remove TTY è riferito funzionante
con limite di evidenza finale ancora esplicito. I contratti di rimozione sotto
restano vincolanti, ma le vecchie guide VM non sono la procedura pubblica né il
prossimo gate. La precedente matrice obbligatoria di Update Survivability non
è un release gate reintrodotto da R6/R7.

**Decisione Utente (23 settembre 2026):** il target realistico è una release
installabile da un utente tecnico o assistito da AI, che possiede già il bundle
dei cinque materiali device-specific. Non si tenta di dimostrare in anticipo
ogni futura combinazione di aggiornamenti Fedora. Il requisito di sicurezza è
che il progetto possa essere **rimosso completamente e facilmente** quando crea
problemi, lasciando nuovamente Fedora corrente responsabile dei propri stack.

La distinzione è vincolante:

~~~text
NORMAL_UNINSTALL
= percorso prudente da sessione grafica funzionante

EMERGENCY_FORCE_REMOVE
= pulsante rosso da TTY quando il login grafico non è raggiungibile
~~~

Il percorso TTY non diventa recovery ordinaria:

~~~text
NORMAL_LIFECYCLE_TTY_REQUIRED=false
EMERGENCY_TTY_RECOVERY_ALLOWED=true
~~~

**Stato aggiornato dal correttivo Utente (23 settembre 2026):** il prompt
`CODEX_CORRECTIVE_SENSOR_PRESENT_AND_PUBLIC_DOCS.md` impone il lettore integrato
continuamente presente in install/update/uninstall/recovery. Vietato sostituire
il detach con unbind, disable o occultamento. La sicurezza del lifecycle viene
dal controllo software del servizio; presenza in sysfs non è un errore.

A `4f244fa2946da94406f03991332f8a70e9a8b401` l'Utente riferisce PASS di tooling,
rimozione normale, password/desktop, assenza path progetto, fprintd stock e
metadata invariati dei cinque materiali/template. Reinstallazione allora con
lettore scollegato e un login Plasma con un contatto MATCH PASS. Emergency in
TTY con lettore presente riferita riuscita, ma output/stato finale esatti
incompleti. La successiva reinstallazione reader-present è stata fermata dal
gate USB del tool, prima del runtime. Quella è la classe di failure corretta.

Tutti gli entrypoint attivi ammettono ora il lettore presente. Tooling senza
azioni fprintd/USB; runtime protetto da inibizione temporanea dell'attivazione,
stop e verifica inactive/MainPID 0/LoadState masked; nessun riavvio automatico.
Login usa il manager corrente con gli output originali verificati. Le operazioni
concorrenti sono serializzate. Qualifica sintetica e review nel manuale corrente;
classificazione dei percorsi in `development/READER_PRESENT_LIFECYCLE_REVIEW.md`.

**Procedura precedente ora storica:** `development/deployment/recovery/R5_VM.md`
e `development/docs/R5_INSTALL.md` conservano la qualifica componente su VM e
il precedente riuso degli output. Non devono essere presentate o rieseguite come
installazione finale. La decisione R6/R7 autorizza invece build/import/install
pubblici da sorgente e sostituisce l'allowlist con l'unica area interna
`development/`. Il prossimo gate è la procedura pubblica sul Fedora fisico
eseguita dall'Utente; la qualifica di quel nuovo percorso resta pendente.

### R5-A — Uninstall normale unificato

Creare un comando utente semplice, preferibilmente:

~~~text
goodix-uninstall
~~~

eseguibile da terminale nella normale sessione grafica e capace di chiedere
autonomamente i privilegi necessari.

Deve rimuovere l'intero software Goodix installato e i suoi effetti
project-owned, inclusi almeno:

- integrazione Plasma Login project-owned;
- runtime/libfprint Goodix project-owned;
- drop-in/service integration project-owned;
- eventuali policy/label/support software project-owned che l'installazione ha
  aggiunto e che devono essere rimossi per tornare allo stack Fedora corrente.

Deve invece preservare per default:

~~~text
/var/lib/goodix-5125-poc/
fingerprint templates
factory/device-specific material
~~~

Il normale uninstall può restare fail-closed e verificare receipt/hash/ownership
**dei file del progetto**, ma non può subordinare la rimozione del progetto alla
salute, esistenza, posizione, versione o hash di file Fedora.

In particolare, l'attuale precondizione Plasma:

~~~text
vendor_ready()
→ richiede /usr/lib/pam.d/plasmalogin
~~~

deve cessare di essere un requisito per poter rimuovere l'override project-owned.
Se Fedora ha cambiato o spostato il proprio PAM, questo è un motivo in più per
uscire di scena, non un motivo per bloccare l'uninstall.

### R5-B — Emergency red button: `goodix-force-remove`

Creare e installare un comando stabile e facile da digitare:

~~~text
goodix-force-remove
~~~

disponibile direttamente nel `PATH` dell'utente anche da TTY, senza repository,
build output, `cd`, pipe, hash, commit o argomenti tecnici. Se eseguito come
utente normale deve poter richiedere esso stesso la normale autenticazione
`sudo`; l'utente deve digitare **un solo comando**.

Semantica obbligatoria:

~~~text
GOODIX_FORCE_REMOVE_GOAL=
REMOVE_PROJECT_INFLUENCE_FROM_CRITICAL_AUTH_PATH
RETURN_CONTROL_TO_CURRENT_FEDORA
~~~

Il force-remove è deliberatamente diverso dal normale uninstall:

- non controlla se il PAM vendor esiste ancora;
- non controlla versione/hash/layout Fedora;
- non richiede receipt valida;
- non richiede repository o candidate;
- non richiede che l'installazione sia completa;
- non prova a diagnosticare o riparare Fedora;
- non ripristina snapshot/copie storiche di file Fedora;
- non cancella materiali protetti o template biometrici;
- rimuove soltanto i **path e gli artefatti noti come project-owned**, in ordine
  fail-safe, privilegiando prima il disinnesco del percorso di autenticazione;
- tollera artefatti project-owned già assenti e installazioni parziali;
- rimuove il proprio comando/tool di recovery per ultimo, se tecnicamente
  sicuro, così che una rimozione completa non lasci software Goodix attivo.

L'obiettivo non è promettere di riparare una Fedora già rotta per cause esterne.
L'obiettivo è poter affermare, salvo imponderabili failure del sistema:

~~~text
GOODIX_PROJECT_IN_CRITICAL_AUTH_PATH=false
FEDORA_CURRENT_STATE_EXPOSED=true
~~~

Il force-remove non deve fare verifiche incrociate o "ragionare" sulla distro nel
momento di emergenza. Le verifiche di sicurezza devono essere concentrate nella
scelta **statica e limitata** dei path project-owned che il comando è autorizzato
a rimuovere.

### R5-C — Documentazione canonica a prova di emergenza

Il repository pubblico/canonico deve rendere immediatamente trovabili:

- uninstall normale;
- emergency recovery / force remove;
- cosa viene rimosso;
- cosa viene preservato;
- cosa il force-remove **non** può garantire se Fedora stessa è corrotta.

Il `README.md` principale deve collegare in modo evidente una pagina dedicata,
preferibilmente:

~~~text
docs/UNINSTALL.md
~~~

La sezione emergency deve iniziare con istruzioni non tecniche e brevi, adatte a
essere lette da smartphone quando il desktop non è accessibile. Target UX:

~~~text
1. premi Ctrl+Alt+F3
2. login con username/password
3. esegui: goodix-force-remove
4. segui l'unica eventuale istruzione finale mostrata
~~~

La spiegazione tecnica può seguire, ma non deve precedere la procedura di
emergenza.

### R5-D — Test offline obbligatori prima della live

Prima del prossimo Human Gate, testare sinteticamente almeno:

~~~text
NORMAL_UNINSTALL_COMPLETE_INSTALL
NORMAL_UNINSTALL_VENDOR_PATH_MISSING
NORMAL_UNINSTALL_PROJECT_DRIFT_FAILS_CLOSED

FORCE_REMOVE_COMPLETE_INSTALL
FORCE_REMOVE_VENDOR_PATH_MISSING
FORCE_REMOVE_RECEIPT_MISSING
FORCE_REMOVE_PARTIAL_RUNTIME
FORCE_REMOVE_PARTIAL_LOGIN_INTEGRATION
FORCE_REMOVE_FPRINTD_ACTIVE
FORCE_REMOVE_FPRINTD_INACTIVE
FORCE_REMOVE_REPOSITORY_MISSING
FORCE_REMOVE_BUILD_OUTPUT_MISSING
FORCE_REMOVE_IDEMPOTENT_REPEAT
MATERIALS_PRESERVED
TEMPLATES_PRESERVED
FEDORA_FILES_NOT_RESTORED_OR_OVERWRITTEN
~~~

Il force-remove deve essere testato specificamente contro il caso che ha motivato
questa fase:

~~~text
/usr/lib/pam.d/plasmalogin = MISSING
/etc/pam.d/plasmalogin     = PROJECT_OVERRIDE_PRESENT

EXPECTED:
project override removed
force-remove continues
no dependency on vendor_ready()
~~~

### R5-E — Sequenza live VM storica, non corrente

Quando il lavoro offline e la documentazione sono pronti, **HUMAN_REQUIRED**.
La live R5 deve essere preparata ma non eseguita autonomamente dall'AI.

La sequenza inizialmente concordata sotto è conservata come provenance.
Il nuovo correttivo la sostituisce operativamente con: verifica dello stato
rimosso riferito → install reader-present → normal uninstall e password/desktop
→ stessa reinstallazione reader-present → un comando emergency TTY → verifica
TTY/password e desktop con runtime assente. Lettore sempre presente; nessun
nuovo MATCH, enrollment o rebuild. Blocchi esatti in
`deployment/recovery/R5_VM.md`. Il packaging finale non è inventato né anticipato.

Sequenza originale (parzialmente eseguita, non ripetere integralmente):

1. creare snapshot della VM nello stato R4 PASS corrente;
2. eseguire `goodix-uninstall` dalla sessione grafica;
3. verificare rimozione software Goodix, preservazione materiali/template e
   normale accessibilità Fedora;
4. reinstallare il driver usando **esattamente la procedura destinata
   all'utente finale**, così da qualificare anche quel percorso;
5. eseguire solo la verifica funzionale minima necessaria a dimostrare che
   l'installazione ha ripristinato la candidate qualificata;
6. entrare in TTY secondo documentazione;
7. digitare soltanto:
   ~~~text
   goodix-force-remove
   ~~~
8. verificare che gli artefatti project-owned siano disinnescati/rimossi e che
   Fedora corrente torni responsabile del login/password.

La live non deve provocare deliberatamente corruzione Fedora o spostamenti reali
dei file vendor: questi scenari appartengono ai test sintetici.

### Scope escluso da R5

La precedente matrice obbligatoria:

~~~text
update libfprint
update fprintd
update PAM
update sudo/PolicyKit
update Plasma/KDE
update systemd
update kernel
full dnf upgrade
~~~

non è più un release gate R5.

Questi eventi restano sorgenti reali di compatibilità da osservare nell'uso
quotidiano e nella manutenzione del progetto. Regressioni future vengono
tracciate tramite issue GitHub, corrette quando riproducibili e possono generare
nuove release. Non si interpreta questa scelta come garanzia che ogni update
Fedora futuro sarà compatibile.

**Exit criteria R5:**

~~~text
GOODIX_NORMAL_UNINSTALL=QUALIFIED
GOODIX_FORCE_REMOVE=QUALIFIED
EMERGENCY_TTY_RECOVERY=ONE_COMMAND
PROJECT_AUTH_INFLUENCE_REMOVABLE_WITHOUT_VENDOR_PRECONDITION=true
MATERIALS_PRESERVED=true
TEMPLATES_PRESERVED=true
END_USER_INSTALL_PATH=QUALIFIED
FEDORA_SNAPSHOT_RESTORE_USED_BY_UNINSTALL=false
R5=CLOSED
~~~

**Boundary storico:** R5 non autorizzava automaticamente R6. La necessaria
nuova autorizzazione esplicita è ora stata ricevuta con il prompt R6/R7;
l'orchestrazione corrente segue quel task e resta soggetta ai gate hardware,
privilegi e pubblicazione.

---
## R6 — Installer finale semplice e reversibile

**Stato: PUBLIC_INSTALLER_OFFLINE_PASS; PHYSICAL_INSTALL_PENDING.** L'Utente ha autorizzato
esplicitamente R6/R7. Il nuovo root `install.sh` costruisce il payload dai sorgenti
pubblici, valida il bundle dell'Utente e richiede sudo per la transazione host.
Il clone documentato è `$HOME/goodix-27c6-5125`; l'implementazione accetta altri
path e non usa branch, history o output privati. Le dipendenze Fedora sono
dichiarate nel blocco unico di `docs/INSTALLATION.md`.

Staging materiali default: `$HOME/goodix-5125-materials/`, esattamente cinque
file, esterno al clone. L'importatore valida lo schema/identità e i digest del
bundle fornito, non quelli del lettore di sviluppo. Conserva il pin globale
compatibile della DLL OEM e richiede il checker C offline per il binding E4.
Pubblica il set validato nella destinazione root con mode `0700`/`0600` e label
corrette. Un set valido esistente e i template restano preservati. Nessuna
lettura USB o provisioning è necessaria all'installazione.

Runtime, login e removal sono indipendenti dal clone dopo installazione.
L'update usa il medesimo entrypoint, controlla proprietà del software corrente
e sostituisce sotto quiescenza con rollback dello stato software progetto in
caso di errore. Le suite sintetiche e la simulazione dei 338 file pubblici senza
`development/` o storia Git sono PASS: 112 test e due checker C compilati;
la build nativa completa non è stata eseguita nell'ambiente privo delle dipendenze.
Non è una qualifica installativa fisica. L'AI non installa pacchetti o runtime.

L'installer possiede il runtime Goodix e la sola integrazione minima Plasma
Login già scelta in R4. Nessun file vendor è copiato/congelato o modificato.
I path operativi correnti sono:

~~~text
/usr/local/lib64/goodix-27c6-5125/
/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf
/usr/local/lib64/goodix-plasma-login/
/etc/pam.d/plasmalogin
/usr/local/bin/goodix-uninstall
/usr/local/bin/goodix-force-remove
/usr/local/share/goodix-recovery/
~~~

I materiali sono separati e preservati in `/var/lib/goodix-5125-poc/`; i template
restano sotto `/var/lib/fprint/`. La rimozione disarma prima il PAM/drop-in
progetto, verifica la quiescenza, rimuove runtime/support e restituisce le label
ai default correnti quando il mapping era proprio. Gli strumenti di recovery
si eliminano per ultimi soltanto a cleanup riuscito.

Non deve ripristinare file Fedora byte-per-byte perché non deve modificarli.
L'eventuale integrazione login deve essere rimovibile eliminando soltanto
l'artefatto project-owned e facendo riemergere immediatamente il comportamento
stock corrente della distribuzione.

L'installer deve essere re-runnable dopo un update che abbia reso
indisponibile il fingerprint.

---

## R7 — Release autonoma, sicura e sostenibile per l'utente finale

**Stato: PUBLICABILITY_OFFLINE_PASS; PHYSICAL_INSTALL_PENDING.**
L'albero pubblico è tutto ciò che è versionato eccetto `development/`. Devono
passare audit strutturale, link/documentazione, build/test/installazione senza
storia privata e verifica offline del root entrypoint da clone alternativo.
Materiali del lettore, byte OEM non redistribuibili, capture e dati biometrici
non possono comparire nel tree pubblico. Un elenco di eccezioni non è ammesso.

L'URL pubblico deve ricevere dall'Utente la versione preparata prima della
prova fisica con il blocco canonico. L'AI non esegue tale pubblicazione.
La closure offline non consente di dichiarare la release completamente
qualificata/pubblica prima della review dell'installazione fisica e dei minimi
risultati lifecycle. Nessuna ulteriore procedura privata/VM sostituisce il
percorso che dovrà utilizzare un utente esterno.

L'obiettivo finale del progetto **non è l'upstream ufficiale**. L'obiettivo è
una release pubblica sufficientemente autonoma, stabile e sicura da poter
essere installata e mantenuta da un utente finale senza esporre il sistema
operativo a rischi sproporzionati.

La release deve essere progettata affinché il suo failure model resti
strettamente confinato al sottosistema fingerprint.

Obiettivo finale:

~~~text
installazione semplice
→ fingerprint funzionante
→ normali aggiornamenti del sistema operativo
→ nessun rischio ragionevole di lockout o rottura del desktop
→ se il driver diventa incompatibile: fingerprint FAIL soltanto
→ reinstallazione/aggiornamento del driver sufficiente al recupero
~~~

La release deve quindi soddisfare contemporaneamente:

- nessuna necessità ordinaria di TTY, recovery console o procedure manuali di
  ripristino del sistema; è ammesso un percorso emergency-only documentato,
  consistente in login TTY + un solo comando `goodix-force-remove`, come ultimo
  airbag quando il login grafico non è raggiungibile;
- nessuna modifica privata di componenti critici Fedora/KDE necessaria per
  mantenere accessibili password, desktop, sudo o PolicyKit;
- comportamento prevedibile anche quando futuri aggiornamenti cambiano
  libfprint, fprintd, PAM, KDE/Plasma, systemd o kernel;
- aggiornamenti incompatibili possono rendere temporaneamente indisponibile
  l'impronta, ma non devono rendere il PC meno accessibile o meno sicuro;
- installazione, aggiornamento e rimozione del driver devono essere comprensibili,
  reversibili e proporzionati;
- la recovery ordinaria deve essere reinstallare/aggiornare/rimuovere il driver,
  non riparare Fedora;
- eventuali limitazioni dei consumer stock vengono documentate senza
  trasformarle in dipendenze private permanenti del progetto, **salvo il login
  fingerprint Plasma che è requisito funzionale esplicito e deve essere risolto
  entro il boundary R4 prima della release**.

L'eventuale contributo upstream di singole correzioni o componenti resta una
possibilità tecnica facoltativa, non un requisito, non una milestone e non il
criterio di successo del progetto.

R7 è raggiunta quando la release soddisfa R5/R6 e dimostra che il suo normale
lifecycle non richiede all'utente finale acrobazie di recupero del sistema né
lo espone inutilmente a regressioni causate da futuri aggiornamenti del sistema
operativo.

~~~text
FINAL_PROJECT_GOAL=SAFE_STANDALONE_END_USER_RELEASE
UPSTREAM_REQUIRED=false
NORMAL_RECOVERY=REINSTALL_UPDATE_OR_REMOVE_DRIVER
MAX_ACCEPTABLE_UPDATE_FAILURE=FINGERPRINT_ONLY
SYSTEM_RECOVERY_GYMNASTICS_ALLOWED=false
~~~

---

# Regole di orchestrazione AI PM / AI Executor

Questa roadmap è un boundary operativo, non un suggerimento.

## AI PM

Prima di assegnare un task deve:

1. identificare la fase R1-R7 corrente;
2. scegliere il più piccolo task che avanza quella fase;
3. verificare che il task non reintroduca componenti dichiarati
   REJECTED_ARCHITECTURE;
4. verificare che il failure model resti FINGERPRINT_ONLY per normali update;
5. rifiutare scope creep verso KDE/PAM/sudo/PolicyKit/systemd, salvo il boundary
   ristretto e già autorizzato di R4 per l'integrazione fingerprint di Plasma Login;
6. richiedere HUMAN_REQUIRED se per avanzare sembra necessario violare una
   invariante di questa roadmap;
7. applicare la nuova autorizzazione R6/R7 e completare il lavoro offline
   consentito, fermandosi prima della pubblicazione e dell'installazione fisica
   riservate all'Utente.

## AI Executor

Deve:

- implementare soltanto il task assegnato;
- non modificare componenti sopra il confine fprintd salvo il boundary ristretto
  R4 già autorizzato dall'Utente per il fingerprint login Plasma; anche lì sono
  vietate mutazioni live autonome e modifiche dirette ai file package-owned;
- non trasformare una limitation di Fedora/KDE in un nuovo sottosistema privato;
- non usare il fatto che una patch “funziona” come prova di release-safety;
- produrre test offline prima del Human Gate;
- demandare all'Utente ogni installazione/runtime/live/update; per il gate
  finale R6/R7 il target è il Fedora fisico secondo la deroga esplicita §4;
- preservare le invarianti factory-preserving esistenti.

## Review

La review deve chiedere esplicitamente:

~~~text
DOES_THIS_CHANGE_INCREASE_DISTRO_COUPLING?
DOES_IT_MODIFY_OR_FREEZE_A_FEDORA_OWNED_AUTH_COMPONENT?
CAN_A_NORMAL_UPDATE_BREAK_MORE_THAN_FINGERPRINT?
IS_REINSTALL_UPDATE_OR_REMOVE_DRIVER_SUFFICIENT_RECOVERY?
~~~

Una risposta sì alla prima domanda richiede minimizzazione, motivazione e prova
R5: non è da sola un veto se serve al requisito Plasma Login. Una risposta sì
alla seconda o terza, oppure no all'ultima, rende invece il task non accettabile
come production architecture.

---

# Criteri di release

Una candidate può avanzare verso public release soltanto se:

- driver/device path funziona;
- enrollment/verify funzionano;
- factory/Windows compatibility resta preservata;
- nessun componente critico Fedora/KDE viene sostituito;
- Removal & Emergency Recovery Qualification R5 è PASS;
- un normale update può al massimo rompere il fingerprint;
- la recovery prevista è reinstall/update del driver;
- password login, desktop, sudo e PolicyKit restano sicuri e indipendenti dal
  successo biometrico del driver;
- Plasma Login fingerprint è PASS sulla baseline qualificata senza attese
  biometriche forzate sul percorso password;
- installer/uninstaller sono piccoli, leggibili e reversibili;
- eventuali limitazioni consumer sono documentate senza patch invasive.

~~~text
RELEASE_SAFETY_BOUNDARY:
FINGERPRINT_MAY_FAIL
THE_PC_MUST_NOT
~~~
