# Review correttiva — Plasma Login VT/getty

CURRENT_TASK=PLASMA_LOGIN_VT_GETTY_RACE_CORRECTIVE
BASELINE=86d9ebc2cc70aeee43f52c07246e0f24d3e0ef0a

## Recovery e classificazione dell'evidenza

Recovery iniziale: development pulito, HEAD 86d9, storia e manuale consultati.
Task esplicito corrente; nessun lavoro interrotto da sovrascrivere. Il log,
inizialmente assente, è stato ripristinato dall'Utente. Analisi dell'intero
file con estrazione delle sequenze pertinenti: 4004 righe, 827168 byte,
SHA-256 `fed92e23a15becce6a3f404387b14aa461796f8ef16f27b2679da210ed111cf7`.
Originale `/home/guido/goodix-plasma-login-first-attempt-20260921.log` preservato;
nessun raw log, segreto o dato biometrico entra nel review set.

| Sequenza osservata | Esito |
|---|---|
| 20:48:42 → 20:48:50: timeout fingerprint, PAM pam_unix, sessione 5 tty3 | Password e sessione KDE riuscite |
| Logout sessione 5; getty tty3 avviato 20:50:17.106061 | Getty sul VT liberato |
| PAM fingerprint/session_open sessione 8 tty3 riusciti; errore 20:50:23.161306 | TIOCSCTTY EPERM; helper exit 5; ritorno greeter |
| Login seguente sessione 9 tty4 | KDE raggiunto, non accettazione del primo tentativo |
| Logout sessione 9; getty tty4 avviato 20:50:45.520151 | Stessa classe su altro VT |
| Due contatti, MATCH; PAM/session_open sessione 10 tty4 riusciti; errore 20:50:53.332792 | Stesso TIOCSCTTY EPERM |
| Login seguente sessione 11 tty5 | KDE raggiunto |

FINGERPRINT_PATH_TO_PAM=PASS; PAM_SESSION_OPEN=PASS;
WAYLAND_SESSION_START_REQUEST=REACHED; VT_CONTROL_ACQUISITION=FAIL.
Nessun AVC denied nel file. Il testo `root` nell'errore è il proprietario
**dell'inode tty**, non una cattura del PID proprietario della controlling tty.
La prova corrente non riapre il correttivo Polkit/counter né il vecchio conflitto
della recovery tty1. tty12 resta la recovery separata.

## Sorgente corrispondente e meccanismo

Acquisito il SRPM esatto Fedora 6.7.5-1.fc44, verificato tar contro SHA-512
Fedora e conservati sorgenti/spec/quattro patch immutabili con manifest.
Vedi [provenance](../../reference/plasma-login-manager-fedora44-6.7.5/PROVENANCE.md).
L'host ha systemd 259.9-1.fc44, kernel 7.2.5-200.fc44; le unit reali e la
configurazione sono state lette senza cambiarle. `autovt@` risolve `getty@`;
getty è Type=idle, StandardInput=tty, TTYPath=/dev/%I, TTYVHangup/Reset=yes.
Logind espone NAutoVTs=6; ReserveVT è il default 6. Plasma confligge solo con
getty/kmscon tty1 e conserva l'override vendor service.d/10-timeout-abort.conf.

1. In [logind session_start](https://github.com/systemd/systemd/blob/v259.9/src/login/logind-session.c)
   la nuova sessione provoca una rilettura del VT attivo. Nel percorso
   [seat_active_vt_changed](https://github.com/systemd/systemd/blob/v259.9/src/login/logind-seat.c)
   viene valutato l'avvio auto-getty. Dopo logout il vecchio VT può essere ancora
   visibile e libero prima che il nuovo greeter passi a tty1.
2. [manager_spawn_autovt](https://github.com/systemd/systemd/blob/v259.9/src/login/logind-core.c)
   controlla occupazione e intervallo automatico, poi richiede StartUnit.
   [Type=idle](https://github.com/systemd/systemd/blob/v259.9/src/core/exec-invoke.c)
   può differire l'apertura della tty: attesa iniziale 5 secondi, ulteriore
   attesa limitata 1 secondo. `Started getty` non prova che agetty avesse già
   aperto la tty al momento della selezione Plasma.
3. Fedora Display::startAuth seleziona prima di PAM; setUpNewVt usa VT_OPENQRY
   e restituisce il numero. **Contrariamente a un dettaglio del prompt, non
   apre né mantiene /dev/ttyN.** La patch Fedora 170 modifica jumpToVt, non
   questa selezione. Un job getty non ancora arrivato all'apertura resta
   invisibile alla query kernel dei VT in uso.
4. Dopo PAM, UserSession apre O_RDWR|O_NOCTTY, duplica stdin, verifica setsid,
   quindi tenta TIOCSCTTY. La condizione di [Linux tiocsctty](https://github.com/gregkh/linux/blob/v7.2.5/drivers/tty/tty_jobctrl.c)
   rifiuta con EPERM una tty controllata da un'altra sessione senza takeover.
   Sul target il percorso arriva a quel ramo, non al fallimento setsid.
   La successiva query vede ormai occupato il primo VT e può scegliere quello
   seguente, coerentemente con entrambi i successi successivi del log.
5. Non è dimostrato che “fingerprint più lento” sia da solo la causa: il login
   password precedente impiega circa otto secondi e riesce. La differenza
   rilevante è il VT appena liberato e il getty pendente dopo il logout.

**Noto:** selezione non riservata, apertura differita consentita, ordine dei
failure e confine kernel. **Inferito:** l'esatto interleaving tra apertura agetty
e helper in quelle due run; manca un trace del PID/sessione controlling tty.
Non lo trasformiamo in misura kernel osservata. Il difetto di classe è nel
percorso Plasma/Fedora/logind; Goodix può modificarne il timing ma il failure
osservato non è nel matcher o in pam_fprintd. Il correttivo evita quel dominio
di contesa e la nuova live deve verificarne l'effetto reale.

## Alternative confrontate

| Famiglia | Race e console | Lifecycle/compatibilità/footprint | Decisione |
|---|---|---|---|
| A: solo fd aperto dopo VT_OPENQRY | Non neutralizza un getty già accodato; un fd O_NOCTTY non possiede la controlling tty | Piccola patch, ma prova insufficiente | Scartata da sola |
| A+C: VT fuori dall'intervallo auto-getty, libero e qualificato, fd mantenuto | Evita job automatici di tty3/4 e ogni altro VT 1–6; controlla getty/autovt/kmscon sul candidato; preserva console e tty12 | Un daemon locale GPL, nessun nuovo servizio/getty o libreria runtime; target pin, inverse completa | Scelta |
| B: stop/mask/conflict del getty scelto | Stop tardivo potrebbe interrompere console già usata; serve coordinamento per nuove richieste | Più stato systemd e ripristino, possibile impatto su utenti console | Scartata |
| C: TIOCSCTTY forzato o retry del helper | Può sottrarre una console; retry nasconde il primo fallimento | Tocca helper/PAM e semantica sessione | Scartata |
| D: Type=simple, delay o modifica globale logind/getty | Riduce una finestra senza qualificare ownership, oppure modifica tutte le console | Override apparentemente piccolo ma race residua o scope maggiore | Scartata |

La selezione usa la maschera kernel VT_GETSTATE (bit 1–15): NAutoVTs effettivo
qualificato 6, scansione dei VT liberi superiori a 6, nessun tty3/4/5 prefissato.
ReserveVT=6 è verificato dal preflight. Se non c'è un terminale qualificato o
una query fallisce, non parte PAM. Nessun fallback al VT attivo. Sono esclusi
unit attive/failed e job pendenti; controllo ripetuto dopo open. Il fd O_NOCTTY,
CLOEXEC appartiene a Display e si chiude su cancellazione, errore, distruzione
o report di avvio del helper. Nessun ioctl di takeover aggiunto.
Una modifica root concorrente a configurazione/console resta fuori dal
contratto: non promettiamo esclusione atomica contro un altro amministratore.

Password e fingerprint condividono la stessa assegnazione prima di PAM.
Nessun getty è fermato o disabilitato. tty12 già aperta compare occupata nella
maschera e non viene scelta. La patch include solo Display e il nuovo selettore;
helper/UserSession, PAM, driver, matcher, USB/TLS/FDT, Polkit/sudo/locker,
timeout e tre contatti restano invariati.

## Verifica offline ed executable closure

- 14 casi del **SessionVt C++ di produzione**, con syscall VT simulate e D-Bus
  privato: tty3/tty4, terminale libero, fixture della stessa scelta pre-PAM
  condivisa da password/fingerprint (nessuna autenticazione eseguita),
  tty12 presente, VT occupato, getty attivo/job pendente anche fuori intervallo,
  contesa durante open, risposta malformata, configurazione errata, bus indisponibile,
  esaurimento e rilascio/distruzione. SIMULATED_CONTRACT_TEST, non live kernel VT.
- Test kernel locale uid 1000 su PTY nuove: altra sessione proprietaria → EPERM;
  PTY libera → TIOCSCTTY riuscito con argomento zero. Nessun /dev/ttyN reale.
- Managed 35, migrazione 27, launcher 23, metadata/riarmo 15: PASS, inclusi
  candidate preliminare con ELF reale, rollback, collisioni, directory preesistente,
  update Plasma diverso rifiutato e recovery salvata da cwd estranea.
- Riarmo della snapshot 86d9 autentica per hash del codice; originali simulati
  conservati integralmente. Non legge la snapshot root reale. Le fixture PAM
  vendor sono ora stabili, perché l'host mantiene intenzionalmente la candidate
  installata e non può fungere da fixture della baseline storica.
- Preflight read-only eseguito come guido sul target: PASS; no root, install,
  restart, logout o sensore. Compilazione SDK senza rete, link Fedora, nessun
  RPATH/RUNPATH né dipendenza runtime irrisolta; daemon mai eseguito dall'AI.
- La consegna finale è prodotta due volte dal HEAD pulito, confrontata per
  intero e sigillata con receipt prima del gate. Manifest/receipt della consegna
  e risposta finale identificano lo SHA effettivo; non esiste un grant separato.

I test hanno corretto un vero errore di lettura QDBusArgument (accesso di lettura
const), e la fixture dipendente dal PAM host. Non è stato aggiunto un harness
live. Il report SESSION_START del helper non è trattato come un ACK positivo di
TIOCSCTTY: un exit prematuro del child non deve diventare un falso PASS. Il
risultato negativo è esplicito (errore helper e HELPER_EXIT=5); il positivo
richiede il normale desktop osservato al primo handoff.
Il test compila un eseguibile separato con wrapper dei soli syscall VT;
il daemon production non contiene questi wrapper o API di test.
REAL_KERNEL_VT_TEST_STATUS=REAL_TARGET_LIVE_PENDING.
PASSWORD_LOGIN_REGRESSION=offline comune PASS, normale password live obbligatoria.
RECOVERY_TTY12_REGRESSION=offline PASS, console reale preservata, live pending.

## Lifecycle e metodo del prossimo test

Installazione: binario e preflight nel runtime già gestito + un drop-in del
servizio Plasma. Nessun binario vendor sovrascritto. Stato, layout, digest e
provenance verificati; attivazione separata ed esplicita, perché il daemon
precedente sopravvive al normale logout. Il login-check rifiuta quel daemon
precedente e verifica i byte della candidate attiva. L'unica attivazione umana
riavvia Plasma dalla console tty12; poi password per rientrare in KDE.

Uninstall arresta il daemon sostitutivo (o un restart pendente), preserva il
vendor ancora in esecuzione se la patch non era stata attivata, elimina
soltanto il proprio override/runtime e
ripristina lo stato servizio. La recovery /run/gx differisce il riavvio fino al
ripristino della baseline completa; lo stato originale attivo/inattivo è salvato
prima della migrazione, anche per ripresa dopo interruzione. Usa copie salvate
e verificate di manager/Polkit/sudo, nessuna dipendenza dal checkout corrente.
Update con byte Plasma diversi è fail-closed; update con byte identici mantiene
l'inverse gestita. Upgrade Fedora non qualificato fa fallire il preflight: questa consegna
temporanea richiede recovery prima degli aggiornamenti. Se l'host è già
aggiornato, anche la recovery può fermarsi sui nuovi file vendor e richiede
review; non li sovrascrive implicitamente.

WHAT_CHANGED_FROM_LAST_LIVE=assegnazione strutturale del VT prima di PAM,
fuori dal dominio auto-getty, con qualificazione e fd mantenuto.
NEW_TECHNICAL_HYPOTHESIS=il VT assegnato non può essere reclamato dal getty
automatico del terminale appena liberato durante l'autenticazione.
IF_SAME_FAILURE_RECURS_NEXT_ACTION=STOP e recovery; correlare il VT effettivamente
scelto, stato getty/job e proprietario della sessione al failure con diagnostica
mirata; riesaminare il percorso helper/ownership. Nessun secondo login di
accettazione e nessun terzo tentativo equivalente basato sul solo timing.

Review PM eseguita in una fase separata dall'implementazione, senza seconda
istanza agente e senza modifiche durante il riesame. Esaminati direttamente
diff Git-native, source list rispetto a CMake Fedora, costanti/configurazione,
provenance/licenze, inverse e recovery, risultati e assenza di delta nei
componenti fingerprint. Corrette la falsa equivalenza tra report di avvio e
TIOCSCTTY riuscito, la chiusura non necessaria del daemon vendor nella recovery
di un'installazione non attivata e il claim finale fprintd inattivo dopo riavvio
del greeter. Test pertinenti rieseguiti dopo questi correttivi. Review software
accettata; closure della consegna subordinata alle due build finali, al confronto
integrale e al controllo del launcher da cwd estranea prima del Human Gate.
Il README contiene i comandi umani, STOP e rollback. Stato canonico aggiornato
nel manuale, nessun nuovo D-number per questo correttivo locale.

OUTCOME=HUMAN_REQUIRED dopo review e sigillo della consegna.
NEXT_HUMAN_GATE=recovery 86d9 → install/attivazione nuova → password e login-check
→ logout → un solo login fingerprint → recovery anche dopo PASS → password.
