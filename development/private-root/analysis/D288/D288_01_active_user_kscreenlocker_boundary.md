<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D288/01 — KScreenLocker active-user, closure offline e Human Gate

## Decisione

```text
OUTCOME=READY_FOR_HUMAN_GATE
ADVANCEMENT=ACTIVE_USER_KSCREENLOCKER_PRIVATE_PAM_PAYLOAD_IMPLEMENTED
EXECUTABLE_CLOSURE=PASS_OFFLINE_REAL_TARGET_PREFLIGHT
REAL_TARGET_COMPATIBILITY=PASS
RESIDUAL_BLOCKER_OR_RISK=ONE_MANUAL_FACTORY_PRESERVING_KSCREENLOCKER_VERIFY_SERIES
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
PM_DECISION=HUMAN_REQUIRED
LIVE_EXECUTION_PERFORMED=false
```

## Nuovo boundary

D287/01 prova che PAM/fprintd/Goodix raggiunge VERIFY e MATCH quando il client
appartiene alla sessione grafica attiva. Non prova ancora che il consumer
KScreenLocker propaghi quel MATCH non-interattivo al proprio stato `Unlocked`.
La vecchia run greeter non è riutilizzabile: il figlio UID 1000 conservava il
cgroup logind root/background creato da `pkexec`, e il mount namespace PAM
privato costringeva a mantenere proprio quella discendenza.

D288 separa le due esigenze. Il common harness e il payload girano nella
sessione utente attiva; una libreria preload di 50 righe intercetta soltanto il
simbolo versionato `pam_start@LIBPAM_1.0` per il service esatto
`kde-fingerprint` e chiama `pam_start_confdir()` sul PAM privato. Ogni altro
service, incluso `kde`/password, passa al vero `pam_start()`. Il greeter è un
figlio diretto user-session: non usa `runuser`, root namespace, bind mount o
scritture `/etc/pam.d`. I soli privilegi sono gli audit D286 pre/post separati.

## Riesame metodologico pre-live

1. **Cosa cambia realmente?** Il greeter non discende più da `pkexec` e non usa
   un namespace root; resta nella sessione attiva già causalmente validata da
   D287. Il PAM privato è selezionato in-process con interposizione esatta,
   senza modifica host.
2. **Quale nuova ipotesi viene testata?** Che KScreenLocker 6.7.5, con
   autorizzazione Polkit risolta, propaghi un MATCH del proprio autenticatore
   `kde-fingerprint` fino a marker `Unlocked` ed exit zero.
3. **Se fallisce nello stesso punto?** Nessun rerun equivalente. Marker preload,
   journal PAM/fprintd/Polkit, epoch e return del greeter distinguono redirect
   non raggiunto, nuova negazione pre-VERIFY, failure PAM, MATCH non propagato o
   problema cleanup. Il metodo successivo dipenderà da quella classe.

## Safety e UX

Il config impone massimo tre action e tre contatti, zero retry automatico e
timeout complessivo 240 s. Il payload riceve e verifica gli stessi limiti,
avvia massimo tre nuovi processi `--testing`, ognuno con
`pam_fprintd.so max-tries=1 timeout=45`, e richiede `TENTATIVO 2/3` dopo ogni
NO_MATCH. MATCH arresta subito. Ogni outcome accettato richiede esattamente una
epoch/action/TLS/first-image per processo, zero retry/reopen/reset/clear-halt/
famiglie persistenti note, outstanding zero e context drenato/chiuso.

Il greeter `--testing` resta una UI lock-like fullscreen con focus esclusivo.
L'operatore non deve digitare password o PIN. Il successo richiede insieme
SIGFM MATCH, marker preload fingerprint, `Unlocked` ed exit zero; così un
eventuale successo interattivo non può essere scambiato per fingerprint.
Signal/timeout attivano cleanup sia nel payload sia nel common harness; il
post-audit viene comunque tentato. Capture e journal sono sanitizzati e non
includono risposte PAM, template, pixel o protected material.

## Executable closure e target gate

Il preflight host-only ha verificato gli RPM Fedora correnti, gli hash di
greeter/PAM/QML, il riferimento dinamico `pam_start@LIBPAM_1.0` e l'assenza di
header pam-devel come dipendenza. Shim e smoke runner compilano warning-as-error
contro `/lib64/libpam.so.0`; il simbolo esportato è
`pam_start@@LIBPAM_1.0`. La prova reale con `pam_permit` in confdir privato
ritorna start/auth/end `0/0/0` e osserva il marker del redirect. Non esegue
`pkcheck`, pam_fprintd, fprintd, greeter, USB, sensore o privilegi.

La full harness regression aggiornata è `9/9`; i test specifici D288 sono
`9/9`; l'insieme pertinente D286 + vecchio greeter D287 + active-user PAM +
harness + D288 è `162/162 PASS`. `bash -n` e `git diff --check` sono PASS.

## Operator path

Il payload è in
`operator_kit/live_probe/experiments/d288-active-user-kscreenlocker/` e usa il
common harness stabile. Dopo commit/push su `development`, l'unico comando
manuale è:

```bash
operator_kit/live_probe/run.sh d288-active-user-kscreenlocker --operator-run
```

Il gate Git richiede HEAD uguale a `origin/development` e critical set pulito;
la capture registra lo SHA completo effettivamente eseguito. Non esiste
autorizzazione a un rerun implicito.
