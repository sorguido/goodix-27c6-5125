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
- niente PAM vendor congelato o mascherato da override persistenti del progetto;
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
- PAM plasmalogin custom;
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

## R4 — Consumer di autenticazione: solo percorso stock

**Stato: ATTIVA; KScreenLocker e sudo ordinario SUPPORTED sulla baseline provata (23 settembre 2026).**
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
PolicyKit. Ultimo fprintd active/running/PID 6749 dopo vero prompt sudo senza
lettore: compatibile con attivazione stock, non failure da ripulire.

**Closure policy incompleta:** il riepilogo non fornisce tutti i corpi delle
regole; pkla-compat consulta input legacy esclusi dalla query iniziale, che
possono precedere la scelta wheel o cambiare autorizzazione/retention. Inoltre
pkexec può selezionare un'altra azione tramite annotazioni del programma.
Il default exec auth_admin non prova da solo identità o assenza di autorizzazione
automatica. Prossimo gate: il blocco integrativo nella stessa
`deployment/minimal-runtime/R4_POLKIT_PREFLIGHT_VM.md`, a sensore assente, legge
quegli input e le azioni registrate. Nessuna nuova query PAM/agente, patch,
cache clear o live; `/usr/bin/true` resta candidata da confermare dopo review.
Runtime/template preservati. PolicyKit/login e R5 restano aperti.

Una volta ottenuti:

~~~text
fprintd-enroll = PASS
fprintd-verify = PASS
~~~

il lavoro del driver è considerato completato al confine biometrico.

KDE, KScreenLocker, sudo, PolicyKit e Plasma Login vengono testati usando
esclusivamente i meccanismi stock della distribuzione.

Per ogni consumer:

~~~text
funziona stock      → SUPPORTED
non funziona stock  → KNOWN_LIMITATION / UPSTREAM_BUG
~~~

Un consumer che non funziona non autorizza patch private al consumer.

Se il bug VT di Plasma Login Manager resta presente, può essere documentato e
portato upstream. Non blocca la release del driver se password e desktop
restano sicuri.

---

## R5 — Update Survivability Test su VM

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
FINGERPRINT=FAIL
RECOVERY=REINSTALL_OR_UPDATE_DRIVER
~~~

È vietato:

~~~text
TTY_RECOVERY_REQUIRED=true
FEDORA_COMPONENT_REPAIR_REQUIRED=true
PASSWORD_PATH_BROKEN=true
~~~

Qualunque failure A/B dell'Update Survivability Audit è **RELEASE_BLOCKER**.

---

## R6 — Installer finale semplice e reversibile

L'installer finale deve possedere soltanto i file del driver/runtime Goodix.

Target ideale:

~~~text
/usr/local/lib64/goodix-27c6-5125/...
/etc/systemd/system/fprintd.service.d/<unico-dropin-se-necessario>
~~~

Più i materiali già separati e preservati:

~~~text
/var/lib/goodix-5125-poc/
~~~

Uninstall ideale:

~~~text
remove runtime
remove own drop-in
systemctl daemon-reload
~~~

Non deve ripristinare file Fedora byte-per-byte perché non deve modificarli.

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
  trasformarle in dipendenze private permanenti del progetto.

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
5. rifiutare scope creep verso KDE/PAM/sudo/PolicyKit/systemd;
6. richiedere HUMAN_REQUIRED se per avanzare sembra necessario violare una
   invariante di questa roadmap.

## AI Executor

Deve:

- implementare soltanto il task assegnato;
- non modificare componenti sopra il confine fprintd senza nuova decisione
  esplicita dell'Utente;
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
CAN_A_NORMAL_UPDATE_BREAK_MORE_THAN_FINGERPRINT?
DOES_IT_TOUCH_A_FEDORA_OWNED_AUTH_COMPONENT?
IS_REINSTALL_DRIVER_SUFFICIENT_RECOVERY?
~~~

Se la risposta alle prime tre è sì oppure all'ultima è no, il task non è
accettabile come production architecture.

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
- password login, desktop, sudo e PolicyKit restano indipendenti dal driver;
- installer/uninstaller sono piccoli, leggibili e reversibili;
- eventuali limitazioni consumer sono documentate senza patch invasive.

~~~text
RELEASE_SAFETY_BOUNDARY:
FINGERPRINT_MAY_FAIL
THE_PC_MUST_NOT
~~~
