# Correttivo Plasma Login: primo accesso dopo logout

> **HISTORICAL_ONLY / REJECTED_ARCHITECTURE — 22 settembre 2026.**
> Questo handoff è superato dalla bonifica R0 e dalla
> [roadmap distro-decoupled](../../ROADMAP_DISTRO_DECOUPLED_RELEASE.md).
> La baseline installata, la console di recovery e il gate citati sotto sono
> lo stato storico del 21 settembre, non istruzioni correnti. Non reinstallare
> questa candidate. Sorgenti, evidenze e rollback restano preservati.

**OUTCOME=HUMAN_REQUIRED — installazione e live esclusivamente umane.**
Baseline attualmente installata: `86d9ebc2cc70aeee43f52c07246e0f24d3e0ef0a`.
La preparazione AI non modifica l'host, la console root tty12 o `/run/gx`.

La nuova candidate corregge la scelta del VT prima dell'autenticazione:
usa un terminale libero fuori dai VT automatici 1–6, verifica i getty sul
terminale scelto e lo mantiene aperto fino al passaggio alla sessione.
Non cambia getty/logind, helper PAM, driver, matcher, impronte o limite tre contatti.
La prova riguarda il **primo handoff fingerprint dopo logout**, non gli altri
consumer già qualificati. Le due precedenti autenticazioni fingerprint erano
riuscite; falliva l'acquisizione del VT dopo l'apertura PAM.

## Prerequisiti e STOP

Salvare il lavoro: **l'attivazione del nuovo daemon riavvia Plasma Login e
chiude KDE**. Non aggiornare pacchetti né avviare console/getty concorrenti
durante questa prova. Fedora 44 KDE, guido uid/gid 1000, Plasma Login
6.7.5-1.fc44 e NAutoVTs/ReserveVT=6 sono verificati; gli altri valori sono STOP.
La shell root già aperta su tty12 deve restare disponibile. Nessuna richiesta
di cambiare password o riconfigurare PAM per ottenere privilegi.

Checkout: `/home/guido/Repository/goodix-27c6-5125_private`, branch development
pulito. La candidate deve avere `MANIFEST:SOURCE_COMMIT` uguale al HEAD completo
riportato nella consegna. I quattro percorsi della consegna sono:

- `/tmp/goodix-combined-migration-ready/candidate`
- `/tmp/goodix-combined-migration-repro/candidate`
- `/tmp/goodix-migration-ready-policy/goodix_fprint_account_delete.pp`
- `/tmp/goodix-migration-ready.SHA256SUMS`

Se manca un percorso, cambia HEAD, compare un drift o un comando fallisce:
**STOP**, conservare console e backup, riportare il messaggio; niente cleanup
manuale o retry. `check` verifica l'intera consegna senza privilegi.

## 1. Recuperare la candidate 86d9 ancora installata

Da KDE/Konsole come guido, senza contatto sul lettore:

```bash
sudo -k /run/gx
```

Digitare la password nel normale percorso sudo già qualificato. È la recovery
salvata della candidate 86d9: non dipende dal nuovo checkout e non arresta
Plasma Login. La console root tty12 resta disponibile come emergenza.
Atteso `RECOVERY=RESTORED_ORIGINALS_DAEMON_INACTIVE_BACKUP_RETAINED`
(o `ALREADY_RESTORED` se già recuperata). Non proseguire su errore.
Restare in Konsole; non chiudere la console root tty12 e non aprirne altre
su tty1.

## 2. Preparare e installare da KDE/Konsole

Come guido, eseguire nell'ordine:

```bash
cd /home/guido/Repository/goodix-27c6-5125_private
development/migration/patched-host-to-combined/operator.sh check
development/migration/patched-host-to-combined/operator.sh preflight
development/migration/patched-host-to-combined/operator.sh rearm
development/migration/patched-host-to-combined/operator.sh run
```

`preflight` è read-only ed è atteso `PREFLIGHT_PASS_REARM_REQUIRED`.
`rearm` verifica la snapshot RESTORED 86d9 (o le precedenti f97/d7), la archivia
integralmente e prepara il nuovo recupero. Non cancella gli originali.
Atteso `REARMED_BASELINE_UNCHANGED_PREVIOUS_BACKUP_ARCHIVED`.
Se è già riarmata, preflight riporta `PREFLIGHT_PASS_NO_CONFIGURATION_CHANGE`
e rearm `ALREADY_REARMED`.

Ogni fase privilegiata usa il normale dialogo **PolicyKit password-only**,
senza retry o agent testuale. `run` verifica di nuovo tutto; **Invio** applica
la migrazione, mantiene fprintd mascherato e prova il normale sudo con password
come guido. Non toccare il lettore. Dopo `PASSWORD=PASS`, un secondo **Invio**
rilascia la maschera e installa la candidate. Ctrl+C prima dell'apply non cambia
nulla; gli errori gestiti dopo l'apply tentano il recupero salvato.

Attesi `GOODIX_MANAGED_INSTALL=PASS`, `GOODIX_MANAGED_STATUS=ACTIVE` e
`PLASMA_VT_ACTIVATION=RESTART_REQUIRED`. Quest'ultimo valore è normale: i file
sono pronti, ma il daemon precedente è ancora in esecuzione. Non fare ancora
logout per il test fingerprint.

## 3. Attivare il nuovo daemon, poi verificare il login-check

Questa singola attivazione richiede tty12 perché termina KDE. Passare con
**Ctrl+Alt+F12** alla shell root già aperta ed eseguire:

```bash
systemctl restart plasmalogin.service
```

Non chiudere la shell. Il normale greeter può diventare visibile automaticamente;
altrimenti raggiungerlo con **Ctrl+Alt+F1**. Eseguire un normale accesso
**con password**, senza contatto sul lettore, per rientrare in KDE.
Questo è anche il controllo della regressione password del nuovo daemon.
Se non compare il greeter o la password non porta in KDE: **FAIL → /run/gx**
dalla console tty12, senza tentare fingerprint.

In Konsole come guido:

```bash
/home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/operator.sh login-check
```

Atteso `LOGIN_PREFLIGHT=PASS ... plasma_vt=RUNNING_CORRECTIVE ... PENDING_LIVE`.
Il controllo verifica daemon realmente avviato, digest installato, console root
su tty12, tty1 libera, versione e contratto logind. Non apre VT o sensore.
Un `RESTART_REQUIRED`/errore non si supera con un nuovo tentativo di login.

## 4. Una sola prova fingerprint dopo logout

Fare logout normalmente. Al greeter eseguire **un solo login fingerprint**:
fino a tre contatti fisici indipendenti, fermandosi al primo MATCH; nessun
quarto contatto e nessun secondo login per trasformare un failure in PASS.

- **PASS_IF:** il primo handoff dopo l'autenticazione apre KDE senza ritorno al
  greeter; password iniziale e console di recupero sono rimaste funzionanti.
- **FAIL_IF:** ritorno al greeter, errore VT/sessione, blocco o regressione password.
- **STOP_IF:** tre NO-MATCH, comportamento non previsto, recovery indisponibile,
  errore di installazione/attivazione o richiesta di un ulteriore tentativo.

Un secondo login non è accettazione. Non ripetere la matrice sudo/Polkit/locker.

## 5. Recupero finale obbligatorio anche dopo PASS

Passare a **Ctrl+Alt+F12**, nella shell root ancora aperta:

```bash
/run/gx
```

La nuova recovery rimuove l'integrazione gestita, arresta il daemon corretto,
ripristina i byte originali della migrazione e solo dopo riavvia Plasma Login
vendor. Il percorso è salvato e verificato, indipendente dal checkout e da /tmp.
Ripetere la recovery dopo un'interruzione conserva la richiesta di riavvio
vendor nello stato salvato; non serve ricostruire comandi dalla memoria.

Atteso `RECOVERY=RESTORED_ORIGINALS_PLASMA_BASELINE_RESTORED_BACKUP_RETAINED`
(o `ALREADY_RESTORED`). Plasma Login torna alla baseline attiva.
Eseguire il normale login **password**
post-recovery. In questa prova temporanea non lasciare la candidate installata,
neppure dopo PASS. Conservare la console fino alla verifica del login password.

## Oggetti modificati e inverse

La migrazione conserva il proprio piano storico di undici path e la conversione
reversibile del solo manifest. I quattro materiali associati e i template sono
preservati; la migrazione ne controlla soltanto i metadata. Originali, metadata,
policy e codice di recupero restano nella snapshot root-only
`/var/lib/goodix-27c6-5125-migration`; i tentativi RESTORED sono archiviati.
Il dettaglio storico resta in [INVENTORY-REVIEW.md](INVENTORY-REVIEW.md).

Il delta Plasma aggiunge soltanto:

- `plasmalogin` e `plasma-vt-preflight` nella directory runtime gestita per commit;
- `/etc/systemd/system/plasmalogin.service.d/99-goodix-plasma-vt.conf`, con
  ExecStart del daemon gestito e preflight read-only;
- campi di stato/hash per verificare e rimuovere esattamente questi oggetti.

Non sovrascrive `/usr/bin/plasmalogin` o il helper vendor. Uninstall rimuove il
proprio drop-in e la directory solo se creata dalla transazione e vuota,
ripristina il servizio precedente e rilascia la riserva VT col daemon.
Nessun getty/logind è modificato. Update con daemon/preflight Plasma diversi
è rifiutato: recovery salvata, poi installazione nuova. Gli update che lasciano
questi byte identici mantengono il normale rollback gestito. Dopo aggiornamenti
Fedora il preflight può fermare il daemon locale: eseguire recovery **prima**
di aggiornare. Se l'host è già aggiornato, anche recovery può fermarsi sul drift
vendor: STOP e review, senza forzare avvio o sovrascritture.

## Cosa riportare

Riportare install/status, esito password iniziale, primo login fingerprint,
esito `/run/gx` e password post-recovery; in caso di FAIL, messaggio e punto
preciso, orario e comportamento osservato. Il journal registra bounded:
`AUTH_RESULT`, `SELECTED_SESSION_VT`, `GETTY_STATE_FOR_SELECTED_VT`,
`SESSION_START` e `TIOCSCTTY_RESULT=FAIL` sull’exit 5 del helper. Il solo report
di avvio non è un PASS: il risultato positivo richiede KDE visibile al primo handoff.
Non serve un collector; dopo un failure reale l'AI indicherà la query mirata.

La [review del correttivo](PLASMA-VT-RACE-REVIEW.md) distingue prove osservate,
ricostruzione del sorgente e limiti dei test offline.
