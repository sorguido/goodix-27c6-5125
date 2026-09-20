# PC patchato → candidate combinata: handoff operatore

**OUTCOME=HUMAN_REQUIRED — GATE=MIGRATION_AND_CANDIDATE_LIVE**

Preparazione offline autorizzata e completata. **Nessuna migrazione,
installazione o autenticazione reale è stata eseguita dall'AI.** I comandi
seguenti appartengono esclusivamente al prossimo intervento umano da KDE/Konsole. Non sono
un'autorizzazione a farli eseguire all'agente.

L'inventario privilegiato è già riesaminato: non ripetere il vecchio probe.
L'autorizzazione successiva consente la preparazione offline della conversione
reversibile del solo manifest; quattro binari materiali, impronte, firmware e
factory state rimangono invariati. [INVENTORY-REVIEW.md](INVENTORY-REVIEW.md)
contiene ownership, classificazioni, prove e limiti.

## Scopo, baseline e prerequisiti

Il precedente preflight umano si è fermato read-only con `fprintd_dropins_drift`:
era omesso il drop-in generale Fedora `service.d/10-timeout-abort.conf`,
verificato conforme al pacchetto systemd. Ora viene preservato e controllato
per percorso, posizione e digest esatti; ogni altro drop-in resta rifiutato.
La run umana successiva da `f97de44e0192f249ccb80fd9b32e1488195f0101` ha
superato preflight, apply e prova password. Install si è fermato su
`plasmalogin_vendor_pam_package_drift`; rollback automatico PASS, nessun workflow
sensore iniziato. Il backup è ora `RESTORED` e `/run/gx` è conservato.

Causa provata offline con il verificatore RPM: la post-image precedente aveva
contenuto/dimensione corretti, ma mtime corrente anziché quello del pacchetto.
La nuova migrazione imposta per entrambi i PAM vendor il contratto RPM completo,
compresa la data `1788825600`, e verifica davvero la compatibilità prima di
release/install. Il managed installer conserva tutti i controlli originali.

La prova verifica la transizione dagli overlay D285/D293/login-early aggiornati
da login-three alla candidate canonica con driver, fprintd, greeter, login,
KScreenLocker, Polkit, sudo/sudo-i e protezione account-delete. Non valida
Windows, FAR/FRR, enrollment, cancellazione account, provisioning o firmware.
Non installare la patch Polkit separata e non usare uninstall storici.

PC qualificato: Fedora 44 KDE, account locale `guido` uid/gid 1000, stack
password authselect `local with-silent-lastlog with-mdns4`, versione pacchetti
e hash esatti nel piano/preflight. Prima della prova: salvare il lavoro,
chiudere dialoghi di autenticazione/impostazioni impronte e gli altri consumer;
non aggiornare pacchetti o cambiare configurazioni durante la transazione.
fprintd deve risultare **inactive**, non fermarlo ad hoc per forzare il preflight.

Checkout operativo:
`/home/guido/Repository/goodix-27c6-5125_private`, branch **development pulito**.
Candidate consegnata: `/tmp/goodix-combined-migration-ready/candidate`.
Il suo `MANIFEST:SOURCE_COMMIT` deve coincidere con `git rev-parse HEAD` e con
il commit completo nel report finale. Il manager lo impone: non spostare HEAD,
non riciclare la candidate preliminare e non aggirare il controllo.
La copia riprodotta è `/tmp/goodix-combined-migration-repro/candidate`.
Policy storica di recupero: `/tmp/goodix-migration-ready-policy/goodix_fprint_account_delete.pp`.
Provenance e integrità della consegna: `/tmp/goodix-migration-ready.SHA256SUMS`.
Questi output sono temporanei: **STOP se mancanti dopo riavvio/pulizia**;
richiedere nuova preparazione offline, senza improvvisare nuovi percorsi.

## Effetti esatti e protezioni

`install.sh` applica esclusivamente gli undici path fissi di `migration.py:ORDER`:

- rimuove selettore sudoers e PAM D285; drop-in fprintd 90/95/96; drop-in greeter
  96; override `/etc/pam.d/plasmalogin`; hook account-delete B5;
- ripristina i byte vendor dei PAM `/usr/lib/pam.d/plasmalogin` e
  `/etc/pam.d/kde-fingerprint`, verificando i digest RPM ricostruiti;
- converte solo `/var/lib/goodix-5125-poc/target-material-manifest.json`:
  accetta esclusivamente il manifest storico di 2305 byte con hash qualificato,
  produce i dieci campi canonici deterministici, conserva owner/mode/SELinux;
- rimuove il solo modulo SELinux B5 `goodix_fprint_account_delete` a priorità
  400, dopo verifica di unicità, abilitazione e hash CIL effettivo.

Conserva integralmente runtime, wrapper, state e backup storici inattivi,
authselect, sudo/sudo-i/Polkit vendor, archivi e staging. I quattro binari
materiali e il template vengono controllati **solo tramite metadata**, mai
letti, hashati, copiati o modificati. Il manifest originale è copiato byte per
byte in `/var/lib/goodix-27c6-5125-migration/original-manifest.json` root:root
0600; la directory root-only 0700 conserva anche gli altri dieci originali
numerati, etichette/modi/mtime nanosecondi nel `state.json` schema 2,
`recovery-policy.pp` e otto file di codice/piano (`migration.py`, `manifest.py`,
`inventory.py`, `host-plan.json`, `recovery.py`, `package_baseline.py`, `rearm.py`,
`legacy-recovery.json`). Conserva anche il manager di rimozione e i suoi moduli
`production/polkit/deploy.py` e `production/sudo/rules.py`, con hash verificati.
La copia del manager conserva tutti i controlli e ammette solo uninstall di
guido; viene rimossa soltanto la ricerca Git inutilizzata da uninstall.
La recovery non dipende dal checkout o dalla candidate in /tmp.
Il backup completo viene verificato prima di disattivare D285.

Oggetti temporanei: directory backup `.pending` durante snapshot;
`<nome>.goodix-migration-new` per scritture atomiche; comando di emergenza
root-only `/run/gx` (0700), che esegue il codice salvato; maschera runtime
`/run/systemd/system/fprintd.service -> /dev/null`. La maschera blocca
l'attivazione mentre si verifica la password, poi viene rimossa esplicitamente.
Il lock concorrente è sul descrittore della directory `/run`, senza creare
un file. Backup e hash sono recupero/integrità, non grant o credenziali.
`/run/gx` resta disponibile anche dopo rollback, fino al riavvio.

Un errore gestito nell'apply tenta il rollback. Dopo interruzione, lo stesso
rollback accetta soltanto i byte originali o quelli previsti dal piano; su
modifiche estranee si ferma. Se resta soltanto `.pending` della prima snapshot, lo switch non è
iniziato: conservare tutto e riportare lo STOP, senza cancellarlo o riprovare.
Per la `.pending` del riarmo valgono le condizioni della sezione 1a.

## 1. Preflight da KDE/Konsole: un comando copia-incolla

La sessione osservata è KDE su **tty2**, con console root di recupero già
aperta su **tty1** e servizio `goodix-migration-recovery.service` attivo.
**Tutte le operazioni ordinarie restano in Konsole.** Non trascrivere path o
sequenze sulla TTY e non chiudere la console di emergenza. Il launcher ne
verifica servizio e comando prima dello switch. Non ripetere `su -`.

In Konsole come guido, incollare:

```bash
/home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/operator.sh preflight
```

Il launcher controlla branch, HEAD pulito, candidate, receipt e tutti i digest;
verifica che il PAM Polkit sia ancora la baseline password-only qualificata,
poi usa **un solo pkexec senza retry o agent testuale di fallback**. Inserire
la password nel normale dialogo KDE. Non viene proposta/scelta l'impronta per
ottenere questi privilegi. In caso di annullamento, errore o PAM diverso,
STOP prima delle operazioni. Le prove fingerprint avvengono solo nella sezione 4.

Nel corrente stato post-rollback è atteso
`OPERATOR=PREFLIGHT_PASS_REARM_REQUIRED`: baseline qualificata, nessuna modifica,
recovery propria riconosciuta; proseguire con la sezione 1a.
Dopo riarmo è atteso `OPERATOR=PREFLIGHT_PASS_NO_CONFIGURATION_CHANGE`.
Il preflight non crea lock/backup, non avvia fprintd né apre USB; qualifica
anche manifest host effettivo, policy B5 e contratto package dei due PAM:
è il probe host read-only di compatibilità prima della nuova migrazione.
La verifica RPM della post-image effettiva viene poi imposta prima di release.
Qualsiasi differenza interrompe
senza modifiche. Per i drop-in vengono mostrati elenco atteso ed effettivo,
così lo STOP è direttamente diagnosticabile. Non forzare collisioni/permessi.

**Solo se la console di recupero non è più aperta**, da Konsole:

```bash
/home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/operator.sh console
```

Lo stesso preflight precede qualsiasi creazione del servizio transitorio.
Se la console qualificata esiste, viene preservata. Se va creata, il normale
agent password KDE avvia systemd-run/openvt; sulla nuova TTY sono ammessi solo
`id -u` (atteso 0) e `tty`, poi ritorno a KDE con Ctrl+Alt+F2. Nessun comando
ordinario sulla TTY. Se il servizio esistente è diverso/inattivo anomalo: STOP.

## 1a. Dopo rollback: riarmo da Konsole, senza cleanup manuale

Solo dopo `PREFLIGHT_PASS_REARM_REQUIRED`, con console root ancora aperta:

```bash
/home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/operator.sh rearm
```

È una singola elevazione password-only. Verifica stato `RESTORED`, source hash
correnti o quelli esatti della run f97de44, backup, `/run/gx`, baseline integra,
assenza candidate/residui/maschera, policy storica, PAM/overlay e fprintd inattivo.
Una collisione estranea o recovery modificata resta STOP. Non cancella nulla.

Prepara e verifica una nuova snapshot della baseline corrente, poi scambia
atomicamente le directory e archivia integralmente il tentativo precedente in
`/var/lib/goodix-27c6-5125-migration.restored-<SHA256-del-vecchio-state.json>`.
La nuova snapshot riferisce l'archivio e conserva il proprio codice di recupero.
`/run/gx` continua a puntare alla directory attiva, sempre presente; il riarmo
non cambia PAM, policy, servizi o materiali. Non avvia apply né il lettore.

Atteso: `OPERATOR=REARMED_BASELINE_UNCHANGED_PREVIOUS_BACKUP_ARCHIVED`.
Una ripetizione verificata restituisce `OPERATOR=ALREADY_REARMED`.
Ora eseguire `run` nella sezione 2: ricontrolla preflight e compatibilità.
`run` senza il riarmo richiesto si ferma prima di apply.

Interruzione **prima** dello scambio: vecchia recovery intatta, STOP esplicito
`rearm_pending_before_exchange_keep_recovery`; riportarlo, senza cleanup.
Interruzione **dopo** lo scambio: nuova recovery valida; ripetere soltanto
`rearm` completa l'archiviazione se tutti i controlli passano. Qualsiasi altro
STOP richiede di preservare console e file. Il riarmo può essere annullato con
`/run/gx`: torna `RESTORED`, senza eliminare l'archivio o eseguire una live.

## 2. Migrazione, password, candidate e status: un launcher in Konsole

Dopo il PASS del preflight, sempre da Konsole come guido:

```bash
/home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/operator.sh run
```

Un'unica elevazione password-only avvia fasi esplicite nello stesso terminale:

1. Verifica nuovamente consegna, preflight e console di recupero attiva.
   **Invio** applica la migrazione; **Ctrl+C prima di Invio** esce senza modifiche.
2. Conserva backup e tool di recupero, prepara `/run/gx`, applica il piano e
   mantiene fprintd mascherato. Atteso `MIGRATION=APPLIED_RUNTIME_MASKED`.
3. Esegue la normale verifica `sudo -k /usr/bin/true` dopo aver ridotto i
   privilegi a guido. **Digitare la password in Konsole**, senza contatto.
   La maschera resta attiva. Password fallita/interruzione: tenta il rollback,
   non installa la candidate. Nessuna password viene raccolta dal launcher.
4. Dopo `PASSWORD=PASS`, **Invio** verifica nuovamente i due PAM vendor
   (contenuto, size, mode/owner, mtime, attributi/label e metadata RPM), esegue
   il controllo RPM reale del PAM Plasma e richiede
   `MANAGED_INSTALLER_BASELINE_COMPATIBLE=PASS` prima di rimuovere la maschera
   e installare la candidate;
   **Ctrl+C** ripristina. Il launcher ricontrolla la consegna prima di procedere.
5. Il manager invariato esegue install e status nella sessione privilegiata già
   aperta, senza nuova autenticazione attraverso il PAM appena installato.
   Attesi `GOODIX_MANAGED_INSTALL=PASS`, `GOODIX_MANAGED_STATUS=ACTIVE`, SHA
   consegnato e le due integrazioni `INTERRUPTIBLE_SERVICE_LOCAL_V1` /
   `PASSWORD_FIRST_SERVICE_LOCAL_V1`.
6. `OPERATOR=PASS_INSTALL_AND_STATUS` conclude il launcher **prima** dei workflow
   biometrici. La console root di emergenza rimane aperta. Passare alla sezione 4.

Non rilanciare `run` dopo install: il launcher rifiuta correttamente il PAM
Polkit cambiato e una baseline già migrata. Nessun material import, enrollment,
riavvio Plasma o workflow fingerprint viene automatizzato.

## 3. Effetti candidate e failure

La candidate installa runtime/driver/daemon/PAM/greeter sotto
`/usr/lib64/goodix-27c6-5125/<commit>` con `current`, wrapper, drop-in 99,
integrazioni locali login/unlock/sudo/Polkit, leaf fingerprint, stato managed e
Polkit, tmpfiles/helper Polkit e hook/policy account-delete. Elenco completo in
`docs/INSTALLATION.md`. Il manager non modifica sudoers o authselect.
`PROTECTED_MATERIAL_READY=true` resta un controllo metadata, non un MATCH.

Su errore dopo apply il launcher tenta lo stesso recupero salvato: uninstall
candidate quando il suo state è presente, quindi rollback storico. Su residui
parziali, drift o `RECOVERY=STOP` non forza rimozioni: tenere la console root,
interrompere e usare la sezione 5. Non ripetere install o test in loop.

## 4. Workflow reale, una serie per volta

Non eseguire test simultanei. Per ogni serie fingerprint: **massimo tre
contatti fisici indipendenti, stop al primo MATCH; NO MATCH 1/2 consente il
successivo, NO MATCH 3 termina, mai quarto contatto**. Errore, timeout o cancel
terminano la serie. Non riaprire dialoghi per aggirare il limite. I limiti
sono implementati nei bridge/daemon/driver; non dipendono da un harness.

1. **sudo**: `sudo -k /usr/bin/true` prima con password. Nuova invocazione per
   fingerprint: Invio vuoto seleziona un tentativo, poi un contatto. Dopo
   NO MATCH scegliere esplicitamente il successivo Invio, entro tre. Ogni
   selezione ha limite totale 8 s; attendere il nuovo prompt per la password.
2. **sudo-i**: `sudo -k -i`, prima con password, poi `exit`; una seconda
   invocazione per la serie fingerprint, poi `exit`. Non fare altro da root.
3. **Polkit KDE**: `/usr/bin/pkexec --disable-internal-agent /usr/bin/true`,
   prima password; nuova invocazione per fingerprint con invio vuoto. Fino a
   tre scelte esplicite; la password resta utilizzabile durante l'attesa
   (massimo 45 s). Si prova il dialogo KDE senza aggiornare pacchetti tramite
   Discover; nessun PASS specifico di un'operazione Discover viene inferito.
4. **NO MATCH → password**: una serie separata sudo e una Polkit con un dito
   non registrato, al massimo tre NO MATCH, poi password valida. Non iscrivere
   o cancellare dita. Se quel dito dà MATCH, interrompere e riportare FAIL.
5. **Cancel**: una richiesta sudo e una Polkit, scegliere fingerprint senza
   contatti, poi Ctrl+C/Annulla. Verificare che la richiesta si chiuda e la
   successiva operazione normale con password funzioni. Non ripetere in loop.
6. **KScreenLocker**: normale blocco schermo, sblocco password; nuovo blocco
   per una serie fingerprint entro tre contatti. Password deve recuperare
   dopo NO MATCH/errore. Non creare altri account o template per questa prova.
7. **Plasma login, ultimo**: salvare il lavoro, mantenere la console root di
   sistema. Logout/login normale con password; un secondo logout/login per
   la serie fingerprint preparata dal greeter, entro tre contatti/8 s per
   tentativo e stop al MATCH. Nessun lancio manuale del daemon/lettore.

`PASS_IF`: tutti i workflow richiesti funzionano, password/cancel rimangono
utilizzabili e i limiti sono rispettati, senza regressioni osservabili.
`FAIL_IF`: password valida inutilizzabile, mancato riconoscimento al termine
della serie, credenziali non valide accettate, login/unlock rotto, nuovo blocco
sudo o altra instabilità. `STOP_IF`: drift/preflight negativo, recovery non
pronta, retry non richiesto, quarto tentativo, attività che prosegue dopo
cancel, possibile effetto persistente. Interrompere al primo FAIL/STOP.

## 5. Recovery: un solo comando breve sulla TTY

Dopo FAIL/instabilità/regressione il rollback è obbligatorio. Chiudere i
consumer, passare alla console root già aperta (Ctrl+Alt+F1 nello scenario
osservato) e digitare soltanto:

```bash
/run/gx
```

È un comando root-only predisposto **prima** dello switch. Verifica hash e
backup, disinstalla la candidate col suo manager salvato quando presente,
poi ripristina esattamente gli originali e la policy storica. Non richiede
checkout, percorsi lunghi, variabili o una nuova autenticazione. Funziona
anche se il checkout cambia. Non usa vecchi uninstall D285/D293/D297.

Atteso `RECOVERY=RESTORED_ORIGINALS_DAEMON_INACTIVE_BACKUP_RETAINED` (oppure
`ALREADY_RESTORED` alla verifica ripetuta). Byte, owner/mode/etichette e manifest
originale sono ripristinati; fprintd resta inactive, maschera rimossa, selezioni
90/95/96 ripristinate. Template e quattro binari materiali restano intatti.
L'uninstall candidate intermedio ripristina la baseline post-migrazione senza
D285; soltanto il successivo rollback ripristina lo stack storico. Backup e
comando breve rimangono recuperabili. Le nuove snapshot ripristinano anche gli mtime originali.
La snapshot f97de44 non registrava questi timestamp: il riarmo fotografa la
baseline successiva al suo rollback, senza inventare date storiche perdute.

Su drift/partial install non qualificato il comando si ferma senza sovrascrivere
file estranei: mantenere la console e riportare lo STOP, senza cancellare stato
a mano. Se apply non è iniziato, non serve rollback e `/run/gx` non esiste.
Se è rimasta solo la snapshot `.pending`, lo switch non è iniziato: conservare
file e riportare l'errore. Non pianificare reboot/power-loss durante la prova.

Dopo ripristino usare il normale accesso password da KDE; nessuna serie
fingerprint aggiuntiva automatica. Su **PASS mantenere la candidate installata**
e il backup. Chiudere infine la console root con `exit`: il servizio transitorio
termina. L'unica digitazione ordinaria è in Konsole; la TTY resta il paracadute.

Riportare PASS/FAIL per i consumer, messaggio esatto e passaggio del failure.
Niente password, segreti, impronte o bundle. Log aggiuntivi soltanto dopo un
failure reale. La UX è verificata offline; il suo comportamento reale resta
parte del prossimo Human Gate.
