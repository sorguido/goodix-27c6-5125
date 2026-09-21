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
- il target fisico può essere usato soltanto per operazioni read-only o per una
  nuova azione esplicitamente autorizzata dall'Utente;
- modifiche Git/documentali al repository non sono considerate mutazioni del
  runtime host, ma nessun artefatto prodotto può essere installato sul target
  fisico senza nuova decisione esplicita.

~~~text
PHYSICAL_HOST_RUNTIME_MUTATION=false
VM_ONLY_RUNTIME_VALIDATION=true
~~~

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

---

## R4 — Consumer di autenticazione: solo percorso stock

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

## R7 — Upstream come obiettivo di lungo periodo

Obiettivo finale:

~~~text
driver Goodix
→ upstream libfprint
→ pacchetto distribuzione
~~~

Valutare separatamente:

- accettabilità/upstreaming del driver Goodix;
- matcher SIGFM e relative dipendenze;
- packaging/provenance/licensing;
- eventuali bug/patch da inviare a fprintd/KDE/Plasma upstream.

R7 non blocca una prima public release distro-decoupled che soddisfi R5/R6.

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
- eseguire ogni runtime/live/update test esclusivamente sulla VM;
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
