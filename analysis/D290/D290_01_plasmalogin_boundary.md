<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D290/01 — boundary Plasma Login Manager reale

## Decisione

```text
SELECTED_NEXT_BOUNDARY=PLASMALOGIN_FINGERPRINT_TO_NEW_WAYLAND_SESSION
OUTCOME=READY_FOR_HUMAN_GATE_PERSISTENT_REVERSIBLE_METHOD
ADVANCEMENT=MINIMAL_SINGLE_SERVICE_PAM_ARM_CLOSE_ROLLBACK_CLOSED_OFFLINE
EXECUTABLE_CLOSURE=PASS_OFFLINE_PLUS_POST_REBOOT_READ_ONLY_ASSESSMENT
REAL_TARGET_COMPATIBILITY=PASS_READ_ONLY
RESIDUAL_BLOCKER_OR_RISK=ONE_REAL_REBOOT_AND_PLASMALOGIN_FACTORY_PRESERVING_VERIFY
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
SENSOR_REACHING_LIVE_EXECUTION_PERFORMED=false
```

## Target e sorgente

Il nome storico del boundary era “SDDM”, ma il target Fedora 44 non installa
il pacchetto SDDM classico. `display-manager.service` è
`plasmalogin.service`, attivo col daemon root `/usr/bin/plasmalogin` nel cgroup
`/system.slice/plasmalogin.service`; il pacchetto è
`plasma-login-manager-6.7.5-1.fc44.x86_64`.

Il PAM reale è `/usr/lib/pam.d/plasmalogin`, non un file sotto `/etc/pam.d`.
Include `password-auth`, che sul target non contiene pam_fprintd. File PAM,
daemon, helper e greeter sono hash-pinned dal pre/post audit.

L'audit del sorgente upstream KDE tag `v6.7.5`, commit
`e63894e7923db053413915ea582db2757303ca8f`, conferma che il greeter invia
username/password soltanto dopo un submit esplicito. Il daemon avvia
`plasmalogin-helper`; per un utente normale il backend seleziona il service PAM
esatto `plasmalogin`, il helper verifica con effective UID 0 e, dopo
`pam_authenticate()` e `pam_acct_mgmt()`, apre e avvia la nuova sessione. Il
solo MATCH fprintd non prova quindi il login: serve osservare anche una nuova
sessione logind Wayland `Service=plasmalogin`.

## Metodo corrente

Il boundary resta `PLASMALOGIN_FINGERPRINT_TO_NEW_WAYLAND_SESSION`, ma per
decisione metodologica dell'Utente il metodo TTY3/FIFO/`coproc`/helper root
long-lived/overlay non è più una via live D290. L'esperimento storico è
preservato con `LIVE_CAPABLE=false`; il common harness non viene ulteriormente
esteso per questo test.

Il micro-kit `operator_kit/d290-01-plasmalogin-persistent-test/` ha un solo
script e tre modalità. ARM verifica host, provenance, D286/fallback, target,
package e contesto SELinux; crea backup/stato root-only e installa direttamente
il solo candidato `plasmalogin`. Nessun processo operatore sopravvive al
reboot. CLOSE raccoglie evidenza del boot e tenta sempre il ripristino.
ROLLBACK è il recovery indipendente, anche da TTY e anche se il test non è
stato eseguito.

Il file originale è rimosso dallo stato solo dopo SHA-256, owner/mode, contesto
SELinux, `rpm -V` pertinente e audit D286/fallback PASS. Drift di package o PAM
non attribuibile viene rifiutato senza cancellare il backup. `password-auth`
resta dopo il modulo `sufficient`, quindi NO_MATCH conserva il login con
password. Authselect e gli stack PAM condivisi non sono modificati.

La procedura live è: ARM dalla sessione grafica, reboot manuale, un solo submit
con campo password vuoto, un solo contatto dell'indice destro, login con
password in caso di failure, quindi CLOSE. PASS richiede una sola epoch VERIFY
valida, SIGFM MATCH e una sessione corrente `Service=plasmalogin`,
`Type=wayland`, `Class=user`, seguiti dal rollback verificato.

## Metodo storico chiuso — audit soltanto

Il common harness resta utilizzabile con una minima estensione opt-in per la
TTY foreground. Il delta principale è un piccolo payload avviato manualmente dalla TTY 3, separata dalla sessione
grafica iniziale su tty2. Il processo harness e il helper root sopravvivono al
logout; questo risolve il lifecycle senza daemonizzare nuovi componenti o
creare un secondo framework.

La seconda invocazione ha mostrato che il payload, eseguito sotto il process
group separato del timeout, non poteva offrire a `pkexec` una controlling TTY
foreground mentre il `coproc` usava stdin per il protocollo helper. Il common
harness ha quindi ricevuto il solo supporto opt-in
`PAYLOAD_REQUIRES_FOREGROUND_TTY`; D290 separa `/dev/tty` interattiva dalla
FIFO 0600 di controllo e lega il helper a PID/start-time del payload con
watchdog. Questa modifica non cambia boundary, budget o protocollo sensore.

La prima invocazione operatore sulla baseline `1a8c5528a0b9f9d12c395f1a9804ee82fd076b94`
si è fermata correttamente nel pre-audit, prima di conferma e payload. Il
predicato iniziale richiedeva erroneamente `State=active`: logind può invece
marcare `online` il desktop tty2 ancora loggato mentre la TTY 3 è foreground.
Il modello corretto identifica il desktop iniziale con UID, ID distinto dalla
TTY operatore, `Class=user`, `Type=wayland`, `Service=plasmalogin`, `TTY=tty2`
e stato loggato `active|online`. Manager e TTY 3 non sono candidati.

Il helper `pkexec` verifica daemon root, exe, cmdline, cgroup e uguaglianza del
mount namespace. Monta read-only il PAM candidato sul solo file
`/usr/lib/pam.d/plasmalogin` e resta control-channel-bounded. `RELEASE`, EOF,
segnale o
errore smontano, verificano l'hash host e rimuovono il runtime root-only.

Il candidato è byte-identico allo stack Fedora salvo una sola riga prima di
`password-auth`:

```text
auth sufficient /usr/lib64/security/pam_fprintd.so max-tries=1 timeout=45 debug
```

L'operatore esegue manualmente logout, seleziona l'utente, lascia vuoto il
campo password, preme Invio una sola volta e fa un solo contatto. Il payload
richiede un greeter reale nella sessione logind `plasmalogin-greeter`, una sola
epoch VERIFY e poi:

- su MATCH, una nuova sessione Wayland loggata `Service=plasmalogin`, con ID
  diverso dalla sessione iniziale già scomparsa dopo il logout;
- su NO_MATCH, nessuna nuova sessione e recovery password soltanto dopo
  unmount/ripristino/runtime removal e post-audit.

Il ritorno manuale alla TTY dopo MATCH o `Login Failed` rende visibili cleanup,
conferma conclusiva e possibile prompt del post-audit. Il payload non esegue
logout, terminate-session, unlock o recovery password autonomi.

### Safety e non-claim del metodo storico

Budget tecnico: una action, un contatto, `max-tries=1`, zero retry. Ogni epoch
deve avere attempted/rejected/consumed `1/0/1`, TLS/first-image `1/1`, zero
retry/reopen/reset/clear-halt/famiglie persistenti/outstanding e
drained/context-closed uno. PAM/authselect non sono modificati persistentemente.

La capture non può telemetrare eventi tastiera: l'assenza di password/PIN
durante il fingerprint resta una procedura operatore e non un claim macchina.
Il risultato non proverà affidabilità statistica, login dopo reboot multipli,
integrazione PAM permanente o assenza assoluta di side effect NVM sconosciuti.

### Riesame metodologico del metodo storico

1. Cambia il consumer: vero Plasma Login Manager e creazione sessione, non
   lock/unlock della sessione esistente. Cambia anche il punto di avvio in una
   TTY sopravvivente al logout.
2. La nuova ipotesi è che il MATCH Goodix nel service `plasmalogin` produca una
   nuova sessione Wayland logind.
3. Se fallisce nello stesso punto, non esiste terzo tentativo equivalente:
   l'overlay viene rilasciato, si usa la password solo per recuperare e la
   capture viene riesaminata prima di qualunque nuovo metodo.

Nessuna live, logout, `pkexec`, mount, USB o azione sensore è stata eseguita
dall'AI. La prima invocazione operatore non ha eseguito logout, overlay,
`pam_fprintd` o VERIFY e non ha prodotto evidenza device-side.

Anche la seconda invocazione operatore si è fermata prima di logout, overlay e
VERIFY, con zero contatti. Il testo immesso al prompt inefficace è apparso in
chiaro sulla TTY, ma non è presente in capture o repository. L'intero percorso
host simulabile è ora esercitato per MATCH e NO_MATCH; restano live soltanto
logout/greeter/PAM-fprintd/USB e creazione reale della sessione.

La terza invocazione sulla baseline `4d6fb16350bb3bbe7a7908b4b611b294825ca00d`
ha invece raggiunto tutti i marker READY dell'overlay; il resoconto preliminare
che li dava assenti era inesatto. L'Utente non ha eseguito logout o contatto.
L'interruzione ha chiuso overlay/runtime e ripristinato il PAM; cleanup e
post-audit sono PASS, azioni sensore e marker Goodix sono zero. Il riavvio
successivo conferma read-only PAM originale, nessun mount/runtime/processo
residuo, daemon attivo e zero VERIFY successivi al cursor.

## Stato corrente

```text
D290_01_EPHEMERAL_OVERLAY_METHOD=ABANDONED_DO_NOT_RERUN
D290_01_REASON=HOST_ORCHESTRATION_COMPLEXITY_EXCEEDED_BOUNDARY_VALUE
D290_01_NEW_METHOD=PERSISTENT_REVERSIBLE_SINGLE_SERVICE_PAM_TEST
D290_01_GLOBAL_AUTHSELECT_FINGERPRINT_REENABLE=false
D290_01_PASSWORD_FALLBACK_PRESERVED=true
D290_01_PERSISTENT_KIT_TESTS=17_PASS
D290_01_COMBINED_REGRESSION=248_PASS
D290_01_NEXT_STATE=HUMAN_REQUIRED
```
