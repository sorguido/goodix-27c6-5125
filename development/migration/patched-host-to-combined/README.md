# PC patchato → candidate combinata: handoff operatore

**OUTCOME=HUMAN_REQUIRED — GATE=MIGRATION_AND_CANDIDATE_LIVE**

Preparazione offline autorizzata e completata. **Nessuna migrazione,
installazione o autenticazione reale è stata eseguita dall'AI.** I comandi
seguenti appartengono esclusivamente al prossimo intervento umano. Non sono
un'autorizzazione a farli eseguire all'agente.

L'inventario privilegiato è già riesaminato: non ripetere il vecchio probe.
L'autorizzazione successiva consente la preparazione offline della conversione
reversibile del solo manifest; quattro binari materiali, impronte, firmware e
factory state rimangono invariati. [INVENTORY-REVIEW.md](INVENTORY-REVIEW.md)
contiene ownership, classificazioni, prove e limiti.

## Scopo, baseline e prerequisiti

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
numerati, etichette/modi nel `state.json`, `recovery-policy.pp` e quattro file
di codice/piano (`migration.py`, `manifest.py`, `inventory.py`, `host-plan.json`).
Il backup completo viene verificato prima di disattivare D285.

Oggetti temporanei: directory backup `.pending` durante snapshot;
`<nome>.goodix-migration-new` per scritture atomiche; lock vuoto
`/run/lock/goodix-migration.lock`; maschera runtime
`/run/systemd/system/fprintd.service -> /dev/null`. La maschera blocca
l'attivazione mentre si verifica la password, poi viene rimossa esplicitamente.
Lock e backup sono recupero/concorrenza, non grant o credenziali.

Un errore gestito nell'apply tenta il rollback. Dopo interruzione, lo stesso
rollback accetta soltanto i byte originali o quelli previsti dal piano; su
modifiche estranee si ferma. Se resta soltanto `.pending`, lo switch non è
iniziato: conservare tutto e riportare lo STOP, senza cancellarlo o riprovare.

## 1. Console di recupero e preflight finale

Il precedente `su -` è fallito: non ripeterlo. Prima di qualsiasi rimozione,
ottenere una console root separata dalla sessione KDE, attraverso il normale
agent Polkit e la password di guido. Nel terminale KDE di guido:

```bash
loginctl show-session self -p VTNr --value
/usr/bin/pkexec --disable-internal-agent --user root /usr/bin/systemd-run --unit=goodix-migration-recovery --collect --setenv=TERM=linux -- /usr/bin/openvt -s -w -- /usr/bin/bash --noprofile --norc
```

Annotare il numero VT di KDE. Il secondo comando apre una VT libera con un
servizio **transitorio di sistema**, indipendente dal logout KDE, senza
configurazione permanente. Nella nuova console verificare `id -u` = `0` e
annotare `tty` (`/dev/ttyN`). Se la console non compare, il comando fallisce o
l'identità non è root: **STOP prima della migrazione**. Non usare fingerprint
per ottenerla. Tenerla disponibile, fisicamente presidiata, fino alla fine;
Ctrl+Alt+F(numero) permette di tornare a KDE o alla console di recupero.

Dalla console root, verificare la consegna e poi eseguire il solo preflight:

```bash
sha256sum --check --quiet /tmp/goodix-migration-ready.SHA256SUMS
/usr/bin/python3 -I -B /home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/migration.py --preflight
```

Entrambi devono terminare senza errori; il secondo deve stampare
`MIGRATION=PREFLIGHT_PASS_NO_CONFIGURATION_CHANGE`. Il preflight non crea
lock/backup, non avvia fprintd, non apre USB. Qualifica per la prima volta il
**manifest host effettivo**, senza stamparlo; l'identità storica finora era
un'inferenza. Hash diverso, policy diversa, processo attivo, pacchetto cambiato,
file/attributo/overlay aggiunto o metadata divergenti comportano STOP.

## 2. Migrazione e confine password

Solo dopo il PASS precedente, nella console root:

```bash
/home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/install.sh /tmp/goodix-migration-ready-policy/goodix_fprint_account_delete.pp
```

Atteso: `MIGRATION=APPLIED_RUNTIME_MASKED`. Tornare nel terminale KDE di guido:

```bash
sudo -k /usr/bin/true
```

Inserire la password di guido. Deve funzionare attraverso il PAM password
vendor; non toccare il sensore. Se fallisce, interrompere e usare il rollback
della sezione 5 dalla console root. Non installare la candidate.

Se la password funziona, nella console root rimuovere la maschera:

```bash
/usr/bin/python3 -I -B /var/lib/goodix-27c6-5125-migration/migration.py --release-mask
```

Atteso: `MIGRATION=RELEASED_FOR_CANDIDATE_INSTALL`. La baseline ora è Fedora
password-only, materiali esistenti con solo manifest convertito e nessuna
selezione degli overlay storici. La pausa fra release e install deve essere
breve, senza avviare consumer fingerprint.

## 3. Installazione e stato della candidate

Dal terminale KDE **come guido**, password al normale sudo quando richiesta:

```bash
cd /home/guido/Repository/goodix-27c6-5125_private
deployment/managed-install/manage.sh install /tmp/goodix-combined-migration-ready/candidate
deployment/managed-install/manage.sh status
```

Install deve dare `GOODIX_MANAGED_INSTALL=PASS`; status deve mostrare il commit
consegnato, `POLKIT_INTEGRATION=INTERRUPTIBLE_SERVICE_LOCAL_V1` e
`SUDO_INTEGRATION=PASSWORD_FIRST_SERVICE_LOCAL_V1`, integrazioni login/unlock
attive. `PROTECTED_MATERIAL_READY=true` prova soltanto metadata, non contenuti
né riconoscimento. Nessun import dei materiali è necessario.

Il manager installa `/usr/lib64/goodix-27c6-5125/<commit>` e `current`, wrapper
`/usr/libexec/goodix-27c6-5125/fprintd-wrapper`, drop-in fprintd/greeter 99,
PAM locali login/unlock/sudo/Polkit e leaf fingerprint, stato managed/Polkit,
tmpfiles e drop-in helper Polkit, hook/policy account-delete. Lista completa e
contratto invariato in `docs/INSTALLATION.md` e
`deployment/managed-install/README.md`. Non cambia sudoers o authselect;
non riavvia Plasma. FAIL: se cleanup completo, rollback storico; se
`RECOVERY_REQUIRED`/`POLKIT_ROLLBACK_FAILED`, preservare console e file,
riportare errore senza forzare rimozioni.

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

## 5. Rollback e stato finale

Dopo FAIL/instabilità/regressione il rollback è obbligatorio. Chiudere i
consumer. Se la candidate è installata, dalla **console root** usare il suo
uninstall corrente (le variabili identificano l'installer, non autenticano):

```bash
SUDO_USER=guido SUDO_UID=1000 SUDO_GID=1000 /home/guido/Repository/goodix-27c6-5125_private/deployment/managed-install/root-transaction.sh --root-uninstall guido
```

Atteso `GOODIX_MANAGED_UNINSTALL=PASS`: ripristina la baseline post-migrazione,
**non D285**. Se install non era iniziato o cleanup è completo, saltare questo
comando. Su uninstall fallito fermarsi; non eliminare a mano lo stato managed.
Il rollback storico rifiuta comunque qualsiasi residuo della candidate.

Sempre dalla console root, ripristinare poi gli originali:

```bash
/usr/bin/python3 -I -B /var/lib/goodix-27c6-5125-migration/migration.py --rollback
```

Equivalentemente usare `development/migration/patched-host-to-combined/uninstall.sh`.
Il codice salvato funziona anche se il checkout cambia. Atteso
`MIGRATION=RESTORED_ORIGINALS_DAEMON_INACTIVE_BACKUP_RETAINED` (oppure
`ALREADY_RESTORED` a una seconda verifica). Ripristina esattamente byte,
owner/mode/etichette dei file toccati, originale manifest e policy B5;
riporta la selezione D285/95/96, lascia fprintd inactive come all'inizio e
toglie la maschera. Timestamp non necessari non vengono ripristinati.
Il backup rimane root-only. Nel normale accesso successivo usare la password;
nessuna nuova serie fingerprint automatica per dimostrare il rollback.

Su drift il rollback **non sovrascrive lavoro estraneo**: mantenere la console
e riportare l'errore. Il recupero dopo spegnimento/power-loss non è stato
provato fisicamente; non pianificare un riavvio durante questa prova.

Su **PASS mantenere la candidate installata** e il backup recuperabile.
Chiudere la console root con `exit` solo dopo le verifiche: il servizio
transitorio termina e viene raccolto. Tornare al VT grafico.
Riportare PASS/FAIL per i consumer, comportamento osservato, testo esatto
dell'errore e passaggio; niente secret, impronte o bundle. Log mirati soltanto
se un failure reale li rende necessari.
