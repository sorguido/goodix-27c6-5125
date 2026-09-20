# PC patchato → candidate combinata: handoff operatore

**OUTCOME=HUMAN_REQUIRED — GATE=LIVE_RETEST**

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

La candidate `d7de50585d555b1ca676e4fcf6c9ed77cc20d601` ha ottenuto
**PASS umani reali**: install/status; sudo e sudo-i password/fingerprint;
Polkit password/fingerprint; sudo e Polkit NO-MATCH→password e cancel→password;
KScreenLocker password/fingerprint. Questi risultati restano validi come
provenance della candidate precedente, non sono una prova della nuova build.

Il precedente logout/login è **INVALID / PROCEDURE-INDUCED VT CONFLICT**:
la recovery root occupava tty1, richiesta da Plasma Login; il daemon ha
terminato con 23 dopo ripetuti `ttyFailed`. Non è un candidate FAIL.
Dopo rollback e chiusura della vecchia console, l'operatore ha riavviato Plasma
Login e verificato il normale login password. **Plasma Login candidate
PASSWORD e FINGERPRINT restano PENDING LIVE.**

Il primo `/run/gx` si era fermato sul counter Polkit root:1000 0600, regolare,
un link, un byte `0`. Il helper setuid, non setgid, eredita il gruppo utente;
il runtime non lo normalizzava e uninstall pretendeva root:root. L'operatore
ha qualificato il file e corretto solo il GID: recovery completa PASS.
Non ripetere quella correzione manuale. Il nuovo runtime crea il counter
root:root; uninstall verifica l'intero runtime prima delle rimozioni e ripristina
localmente i file su errori I/O gestiti. La compatibilità root:1000 è limitata
al preciso vecchio modulo e all'account locale guido/1000.

Questo retest verifica **solo il delta Polkit/recovery e il login ancora aperto**.
Non valida Windows, FAR/FRR, enrollment, account-delete, provisioning o firmware.
Nessuna patch Polkit separata e nessun uninstall storico. Per questa prova,
**il recupero finale è obbligatorio anche dopo PASS**, come richiesto dall'Utente.

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

La verifica read-only corrente trova KDE su tty2, anche una sessione su tty3,
Plasma Login attivo e vecchia recovery inattiva. La nuova recovery usa
**tty12**, fuori dai VT automatici 1–6 di logind e dal suo ReserveVT=6.
Plasma Login 6.7.5 preferisce tty1 e usa VT_OPENQRY per nuove sessioni:
un processo che mantiene tty12 aperta la esclude dalla ricerca dei VT liberi.
`openvt -c 12 -w` non forza un VT occupato e non cambia il VT visibile.

**Tutte le operazioni ordinarie restano in Konsole; TTY solo emergenza.**
Prima predisporre la console (password nel dialogo KDE):

```bash
/home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/operator.sh console
```

Atteso `RECOVERY_CONSOLE=START_REQUESTED tty12` oppure `ALREADY_ACTIVE`.
Non è necessario passare sulla TTY o digitare comandi lì. Prima di riarmo/run
il launcher verifica processo openvt, shell root figlia realmente su tty12,
logind, assenza di getty su tty12 e assenza di processi/sessioni su tty1.
Una vecchia console con scelta VT automatica è rifiutata, mai terminata in
modo implicito. Qualsiasi collisione: STOP e conservare la recovery.

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

## 1a. Dopo rollback: riarmo da Konsole, senza cleanup manuale

Solo dopo `PREFLIGHT_PASS_REARM_REQUIRED`, con console root ancora aperta:

```bash
/home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/operator.sh rearm
```

È una singola elevazione password-only. Verifica stato `RESTORED`, source hash
correnti o quelli esatti delle run f97de44/d7de505, backup, `/run/gx`, baseline integra,
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
5. Il manager esegue install e status nella sessione privilegiata già
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

## 4. Retest minimo da Konsole e normale login

Non eseguire test simultanei. Per ogni serie fingerprint: **massimo tre
contatti fisici indipendenti, stop al primo MATCH; NO MATCH 1/2 consente il
successivo, NO MATCH 3 termina, mai quarto contatto**. Errore, timeout o cancel
terminano la serie. Non riaprire dialoghi per aggirare il limite tecnico.

1. **Polkit, unico smoke consumer richiesto dal delta**:
   `/usr/bin/pkexec --disable-internal-agent /usr/bin/true`, con password.
   Una nuova invocazione per fingerprint: Invio vuoto seleziona un tentativo,
   poi un contatto; massimo tre scelte esplicite e stop al MATCH. La password
   resta disponibile durante l'attesa (massimo 45 s). Questo esercita creazione,
   riapertura e reset del counter corretto. Non ripetere sudo-i, NO-MATCH,
   cancel o KScreenLocker: codice/PAM relativi sono invariati e già PASS reali.
2. Salvare il lavoro. **Prima di ogni logout**, incollare:

   ```bash
   /home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/operator.sh login-check
   ```

   Non eleva privilegi e non avvia servizi, autenticazioni, USB o logout.
   Atteso `LOGIN_PREFLIGHT=PASS recovery_root_tty12=READY tty1=UNCLAIMED
   logout_greeter_result=PENDING_LIVE`. Controlla anche `/run/gx` root:root 0700,
   processo root su tty12, logind e Plasma Login attivo. È un controllo istantaneo:
   non cambiare servizi/VT dopo il PASS. Se STOP, **non fare logout**.
3. **Plasma Login PASSWORD**: normale logout KDE, greeter visibile, login con
   password valida. Non deve verificarsi il precedente loop/exit 23.
4. Ripetere `login-check` dalla nuova Konsole. **Plasma Login FINGERPRINT**:
   normale logout/login, serie nel greeter entro tre contatti/8 s per tentativo,
   stop al MATCH. Nessun avvio manuale del daemon o lettore.
5. **Recovery/uninstall reale obbligatorio**, anche se tutti i punti passano:
   seguire la sezione 5. La nuova candidate non resta installata in questo retest.

`PASS_IF`: smoke Polkit password/fingerprint, entrambi i login e recovery finale
funzionano, senza regressioni e con limiti rispettati.
`FAIL_IF`: password valida inutilizzabile, riconoscimento fallito dopo la serie,
credenziali non valide accettate, login rotto, recovery fallita o instabilità.
`STOP_IF`: preflight negativo, recovery non pronta, retry non richiesto, quarto
contatto, attività dopo cancel, possibile effetto persistente. Fermarsi al primo
FAIL/STOP. Un nuovo problema greeter/VT va riportato separatamente da un rifiuto
PAM/impronta: **nessun PASS login viene dedotto dalle sole prove offline**.

## 5. Recovery ordinaria in Konsole; `/run/gx` in emergenza

Chiudere dialoghi e consumer. Se Konsole è disponibile, incollare e scegliere
**password**, senza contatti sul lettore:

```bash
sudo -k /run/gx
```

È anche lo smoke sudo password necessario per rimuovere la candidate. Se il
login/desktop o l'autenticazione non funziona, **Ctrl+Alt+F12** raggiunge la
shell root già aperta; digitare soltanto:

```bash
/run/gx
```

Il comando root-only verifica sorgenti e backup, disinstalla la candidate con
il manager salvato, poi ripristina gli undici originali e la policy storica.
Non dipende dal checkout o dai percorsi in /tmp; non usa uninstall D285/D293.
Un counter foreign, malformato, con altro owner/gruppo/mode/tipo/link o entry
extra causa STOP prima della rimozione. Non correggere metadata a mano.
Gli errori I/O gestiti nella rimozione Polkit ripristinano i suoi file e counter;
non è una garanzia generale contro power loss o modifiche root concorrenti.

Atteso `RECOVERY=RESTORED_ORIGINALS_DAEMON_INACTIVE_BACKUP_RETAINED` (oppure
`ALREADY_RESTORED`). Byte, owner/mode/etichette/mtime e manifest originale sono
ripristinati; fprintd inactive, maschera rimossa, selezioni 90/95/96 ripristinate.
Template e quattro materiali restano intatti. L'uninstall intermedio ripristina
prima la baseline post-migrazione senza D285; poi il rollback storico recupera
D285. Backup e `/run/gx` restano disponibili, inclusi gli archivi dei tentativi.

Se il recupero o il greeter restano in STOP, conservare la console e riportare
messaggio/punto esatto; non forzare, ripetere live o riavviare alla cieca.
Dopo recovery PASS, mantenere la console tty12 e verificare un normale
logout/login password sullo stack ripristinato. Poi, da KDE/Konsole, verificare
fprintd inattivo e chiudere la console con una normale elevazione Polkit, ora
sulla baseline password-only:

```bash
systemctl is-active fprintd.service
/usr/bin/pkexec --disable-internal-agent /usr/bin/systemctl stop goodix-migration-recovery.service
systemctl is-active goodix-migration-recovery.service
```

Entrambi i controlli `is-active` devono stampare `inactive` (exit 3 è atteso).
La recovery su tty12 non richiede il precedente stop della console su tty1 né
un riavvio manuale di Plasma Login. Se si è dovuta usare la TTY e KDE non torna,
riportare il failure prima di ulteriori interventi.

Riportare: Polkit password/fingerprint; preflight VT prima dei due logout;
Plasma password/fingerprint; recovery e login password post-recovery. In caso
di errore: messaggio esatto e passaggio. Niente segreti/impronte/bundle.
Log mirati si richiedono soltanto dopo un nuovo failure reale.
