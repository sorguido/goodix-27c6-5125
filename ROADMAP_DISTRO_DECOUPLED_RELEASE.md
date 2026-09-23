# Roadmap — Distro-Decoupled Goodix 27c6:5125 Release

> **Status:** ACTIVE
>
> **Scope:** guida vincolante per l'architettura production/release e per
> l'orchestrazione AI PM / AI Executor sul branch **development**.
>
> **Decisione Utente:** un normale aggiornamento Fedora/libfprint può rendere
> temporaneamente indisponibile il fingerprint e richiedere la reinstallazione
> del driver. Non è accettabile che possa compromettere login con password,
> desktop, sudo, PolicyKit o richiedere TTY/recovery per rendere di nuovo
> accessibile il PC.

---

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

## 3. Baseline corrente — R0 completata

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

## 4. Regola VM-only da questo punto in avanti

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
VM_REPOSITORY_SYNC=USER_PULL_DEVELOPMENT
~~~

La VM non è un ambiente al quale l'AI deve accedere direttamente. Quando il
lavoro richiede build, installazione, runtime, live o update-validation in VM:

1. l'AI prepara, verifica nello scope offline consentito e committa su
   `development` tutto il necessario per la prova;
2. termina con `HUMAN_REQUIRED`, consegnando comandi ed evidenze attese;
3. l'Utente esegue manualmente il pull di `development` nella VM;
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
- recovery TTY come parte del normale lifecycle.

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

**Stato: ATTIVA / REPLAN_REQUIRED; KScreenLocker, sudo ordinario e PolicyKit SUPPORTED sulla baseline provata (23 settembre 2026). Plasma Login fingerprint è un requisito di release ancora aperto.**

**Decisione Utente (23 settembre 2026):** il fingerprint al login grafico Plasma
è una funzione richiesta della release. L'assenza del percorso biometrico stock
non è una `KNOWN_LIMITATION` accettabile per chiudere R4 e non autorizza il
passaggio a R5. Il vincolo distro-decoupled resta però invariato: la soluzione
non può compromettere password, desktop o recovery ordinaria e non può congelare
componenti Fedora.

~~~text
PLASMA_LOGIN_FINGERPRINT_REQUIRED=true
PLASMA_LOGIN_KNOWN_LIMITATION_ACCEPTABLE=false
R4_CLOSED=false
R5_BLOCKED_UNTIL_LOGIN_RESOLVED=true
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

Exit criteria aggiuntivi di R4 per Plasma Login:

~~~text
PASSWORD_LOGIN=PASS
PASSWORD_LOGIN_NO_FORCED_FINGERPRINT_WAIT=true
PLASMA_LOGIN_FINGERPRINT=PASS
MAX_PHYSICAL_CONTACTS_PER_SERIES=3
FEDORA_VENDOR_PAM_MODIFIED=false
FEDORA_VENDOR_PAM_FROZEN=false
NORMAL_UPDATE_MAX_FAILURE=FINGERPRINT_ONLY
UNINSTALL_RETURNS_TO_STOCK=true
TTY_RECOVERY_REQUIRED=false
~~~

Il prossimo lavoro è quindi offline/repository: disegno e review della minima
integrazione compatibile con questi criteri. Qualunque installazione, modifica
PAM live, logout/reboot o prova login in VM resta **HUMAN_REQUIRED**. R5 resta
bloccata finché questi exit criteria non sono chiusi.

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

## R5 — Update Survivability Test su VM

**Entry condition:** R4 formalmente chiusa, incluso `PLASMA_LOGIN_FINGERPRINT=PASS`
e relativo password path sicuro. Finché il login Plasma resta aperto, R5 non
parte.

Testare una candidate funzionante attraverso aggiornamenti reali della VM.

Matrice minima:

1. baseline candidate installata;
2. update libfprint;
3. update fprintd;
4. update PAM/auth stack;
5. update sudo/PolicyKit;
6. update Plasma/KDE;
7. update systemd;
8. update kernel;
9. full dnf upgrade disponibile per la release target.

Dopo ogni step sono obbligatori:

~~~text
PASSWORD_LOGIN=PASS
DESKTOP=PASS
SUDO_PASSWORD=PASS
POLKIT_PASSWORD=PASS
~~~

È consentito:

~~~text
FINGERPRINT=FAIL_TEMPORARY
RECOVERY=REINSTALL_OR_UPDATE_DRIVER
~~~

Se uno step rompe il fingerprint, la prova non termina al semplice fatto che la
password resti sicura: deve essere dimostrato che il recovery supportato
(reinstall/update del driver e della propria eventuale integrazione login)
ripristini il percorso biometrico richiesto senza riparare Fedora.

~~~text
AFTER_FINGERPRINT_FAILURE:
PASSWORD_LOGIN=PASS
DESKTOP=PASS
REINSTALL_OR_UPDATE_DRIVER=PASS
PLASMA_LOGIN_FINGERPRINT=PASS
~~~

Se il recovery richiede modifiche manuali a PAM/Fedora o non ripristina il
fingerprint login richiesto, lo step è **RELEASE_BLOCKER** fino a nuovo update
del progetto compatibile con la baseline Fedora aggiornata.

È vietato:

~~~text
TTY_RECOVERY_REQUIRED=true
FEDORA_COMPONENT_REPAIR_REQUIRED=true
PASSWORD_PATH_BROKEN=true
~~~

Qualunque failure A/B dell'Update Survivability Audit è **RELEASE_BLOCKER**.

---

## R6 — Installer finale semplice e reversibile

L'installer finale deve possedere soltanto i file del driver/runtime Goodix e,
se R4 dimostra che è indispensabile, **un solo artefatto di integrazione Plasma
Login strettamente project-owned**. Tale artefatto non può essere una copia
congelata di un PAM vendor né può modificare direttamente file package-owned.

Target ideale:

~~~text
/usr/local/lib64/goodix-27c6-5125/...
/etc/systemd/system/fprintd.service.d/<unico-dropin-se-necessario>
<eventuale integrazione login minima scelta e qualificata in R4>
~~~

Più i materiali già separati e preservati:

~~~text
/var/lib/goodix-5125-poc/
~~~

Uninstall ideale:

~~~text
remove runtime
remove own drop-in
remove own login-integration artifact if present
systemctl daemon-reload
~~~

Non deve ripristinare file Fedora byte-per-byte perché non deve modificarli.
L'eventuale integrazione login deve essere rimovibile eliminando soltanto
l'artefatto project-owned e facendo riemergere immediatamente il comportamento
stock corrente della distribuzione.

L'installer deve essere re-runnable dopo un update che abbia reso
indisponibile il fingerprint.

---

## R7 — Release autonoma, sicura e sostenibile per l'utente finale

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
  ripristino del sistema;
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
   invariante di questa roadmap.

## AI Executor

Deve:

- implementare soltanto il task assegnato;
- non modificare componenti sopra il confine fprintd salvo il boundary ristretto
  R4 già autorizzato dall'Utente per il fingerprint login Plasma; anche lì sono
  vietate mutazioni live autonome e modifiche dirette ai file package-owned;
- non trasformare una limitation di Fedora/KDE in un nuovo sottosistema privato;
- non usare il fatto che una patch “funziona” come prova di release-safety;
- produrre test offline prima del Human Gate;
- demandare all'Utente, dopo il gate, ogni build/install/runtime/live/update
  test in VM secondo §4;
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
- Update Survivability Test R5 è PASS;
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
