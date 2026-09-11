<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D287/01 — probe PAM dalla sessione utente attiva

## Stato

La closure offline e la review AI PM positiva sono completate. Questo kit è
`READY_FOR_HUMAN_OPERATOR` ed è destinato esclusivamente all’esecuzione manuale
dell’Utente. L’agente AI non deve eseguire
`--operator-run`: il percorso può raggiungere il sensore reale e include due
audit privilegiati espliciti tramite Polkit.

Il precedente kit KScreenLocker è chiuso e non deve essere rilanciato. Questo
probe elimina il launcher `pkexec -> runuser` che aveva lasciato il greeter nel
cgroup/session context root `background-light`; il runner PAM viene eseguito
direttamente dal terminale della sessione Plasma Wayland attiva dell’utente.

## Ipotesi e delta metodologico

1. **Cosa cambia:** il subject che invoca PAM/fprintd è il processo utente
   non privilegiato della sessione grafica attiva, non un discendente della
   sessione logind root creata da `pkexec`.
2. **Ipotesi testata:** un `pkcheck` non interattivo per
   `net.reactivated.fprint.device.verify`, riferito all’esatto
   PID/start-time/UID del runner, deve passare e lo stesso processo deve poi
   superare `ListEnrolledFingers` e raggiungere una sola VERIFY.
3. **Se fallisce ancora prima di VERIFY:** non rilanciare. Conservare la
   capture e riesaminare subject/sessione/policy o il diverso boundary PAM;
   non preparare un tentativo equivalente.

## Limiti hardware e rischio

- una sola chiamata `pam_authenticate()`;
- `pam_fprintd.so max-tries=1 timeout=45`;
- massimo una epoch VERIFY e un contatto dell’indice destro;
- zero retry automatici o impliciti, reopen, reset, clear-halt e famiglie di
  scrittura persistente;
- nessun enroll, delete, flash, IAP, ClearApp, provisioning o modifica PSK;
- nessuna modifica a `/etc/pam.d`, authselect, servizi o file persistenti;
- nessun greeter, fullscreen o blocco reale della sessione.

Il rischio residuo è una singola VERIFY sul sensore reale. Non appoggiare un
secondo dito e non rilanciare il comando dopo qualsiasi esito o anomalia.

## Prerequisiti e gate fail-closed

- terminale aperto direttamente nella sessione Plasma Wayland attiva;
- utente non root, runtime Wayland e bus sessione coerenti con l’UID;
- branch `development`, HEAD uguale a `origin/development`, review set critico
  pulito;
- installazione D285 e dipendenze PAM/Polkit ancora hash-pinned;
- esattamente un target USB `27c6:5125` e nessun processo fprintd già attivo;
- disponibilità della password per le due finestre Polkit degli audit D286.

Gli audit privilegiati pre/post non avviano fprintd e dichiarano zero azioni
sensore. Il loro `pkexec` usa il PAM Polkit/password: il kit verifica prima che
`system-auth` non contenga `pam_fprintd`, evitando ricorsione biometrica.

Il `pkcheck` preventivo del runner non usa `--allow-user-interaction` né un
agent interno. Se il subject esatto non è autorizzato, il runner emette
`PAM_NOT_STARTED=true` e termina prima di `pam_start_confdir()`.

## Preflight offline

Questo comando compila il runner con warning-as-error e prova
`pam_start_confdir()` contro un servizio temporaneo contenente soltanto
`pam_permit`. Non enumera USB, non invoca `pkcheck`, PAM biometrico, fprintd,
`pkexec` o `sudo`:

```bash
operator_kit/d287-01-active-user-pam-probe/run-d287-01-active-user-pam-probe.sh --offline-preflight
```

## Unica esecuzione manuale consentita

Dal terminale della sessione grafica attiva, nella root del repository:

```bash
operator_kit/d287-01-active-user-pam-probe/run-d287-01-active-user-pam-probe.sh --operator-run
```

1. Autorizzare con password il pre-audit Polkit.
2. Leggere i limiti stampati dal kit.
3. Digitare esattamente `INDICE DESTRO`.
4. Appoggiare l’indice destro una sola volta; poi allontanare la mano.
5. Autorizzare con password il post-audit Polkit, se richiesto.
6. Non rilanciare. Consegnare il path `D287_01_PROBE_CAPTURE_DIRECTORY` alla
   review AI PM.

`Ctrl-C` interrompe il runner. Se ricevuto dopo l’avvio dell’azione, il kit
prosegue con export diagnostico e post-audit e classifica l’interruzione; non
appoggiare nuovamente il dito.

## Osservabilità ed esiti

La capture privata viene creata sotto
`captures/D287_01/D28701_ACTIVE_USER_PAM_<UTC>_<SHA>/sanitized/` con permessi
restrittivi e contiene:

- `operator.log`, `context.env` e `pam-runner.log`;
- `pre-root-audit.log` e `post-root-audit.log`;
- `fprintd-journal.log` per l’unità e `diagnostic-journal.log` globale ma
  filtrato a PAM/fprintd/Polkit/telemetria Goodix;
- `classification.env`, `summary.env` e `capture.sha256`.

Lo username è sostituito con `<USER>` nei journal. Non vengono registrate
risposte PAM, password/PIN, PSK, template, pixel o dati biometrici.

`MATCH_REACHED_VERIFY` e `NO_MATCH_REACHED_VERIFY` richiedono una sola epoch,
un solo extract, almeno un confronto, `consumed=1`, `tls=1`, cleanup completo e
tutti i contatori retry/persistent a zero. `POLKIT_PREFLIGHT_FAILED_BEFORE_PAM`
prova che PAM non è partito; `FPRINTD_POLKIT_DENIED_BEFORE_VERIFY`, `PAM_ERROR`,
`SAFETY_VIOLATION`, timeout, journal incompleto o post-audit fallito sono esiti
terminali e vietano il rerun.
