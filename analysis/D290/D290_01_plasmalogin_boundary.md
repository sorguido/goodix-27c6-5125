<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D290/01 — boundary Plasma Login Manager reale

## Decisione

```text
SELECTED_NEXT_BOUNDARY=PLASMALOGIN_FINGERPRINT_TO_NEW_WAYLAND_SESSION
OUTCOME=READY_FOR_HUMAN_GATE_AFTER_FULL_HOST_PATH_CORRECTIVE
ADVANCEMENT=REAL_LOGIN_MANAGER_ONE_SHOT_PAYLOAD_IMPLEMENTED_ON_REUSABLE_HARNESS
EXECUTABLE_CLOSURE=PASS_OFFLINE
REAL_TARGET_COMPATIBILITY=PASS_READ_ONLY_PLUS_PRIVILEGED_NAMESPACE_GATE_AT_LIVE
RESIDUAL_BLOCKER_OR_RISK=ONE_MANUAL_LOGOUT_AND_REAL_LOGIN_FACTORY_PRESERVING_VERIFY
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

## Metodo e compatibilità col common harness

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

## Safety e non-claim

Budget tecnico: una action, un contatto, `max-tries=1`, zero retry. Ogni epoch
deve avere attempted/rejected/consumed `1/0/1`, TLS/first-image `1/1`, zero
retry/reopen/reset/clear-halt/famiglie persistenti/outstanding e
drained/context-closed uno. PAM/authselect non sono modificati persistentemente.

La capture non può telemetrare eventi tastiera: l'assenza di password/PIN
durante il fingerprint resta una procedura operatore e non un claim macchina.
Il risultato non proverà affidabilità statistica, login dopo reboot multipli,
integrazione PAM permanente o assenza assoluta di side effect NVM sconosciuti.

## Riesame metodologico pre-live

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
