<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D285/01 Attempt 02 — review indipendente post-installazione persistente

## Decisione

`PASS_LIVE_CLOSED`, con installazione D285 intenzionalmente `ACTIVE`. La run
prova sul target reale l'enrollment persistente, il riavvio del daemon sulla
candidate installata e un'autenticazione `sudo -v` tramite il servizio PAM
dedicato al solo utente operatore. Non prova sopravvivenza a reboot, lock
screen, login grafico o affidabilità statistica.

Il set canonico è
`captures/D285_01/D28501_ATTEMPT_02_20260911T163528Z_a9e234e43d2b/sanitized/`.
L'auditor ripetibile è
`analysis/D285/d285_01_attempt_02_evidence_audit.py`.

## Integrità e provenance

La baseline live è `a9e234e43d2bdf3e81630df143eb7a809a19bff5`.
I digest ricalcolati coincidono con quelli forniti dall'operatore:

- `operator.log`: `aeb42ae93bf2e9ad902031a609162c3e394f135554bba3816386df79d9a93995`;
- `summary.env`: `59577e61a197e855a217192c24fa64ffb213fa16258c624252776ca1bdaf1c33`;
- `terminal-transcript.log`: `e1935aca82a49bafaee33bf8f20bb3b84f67c491acb44a0e8917931884624e3a`.

La directory contiene soltanto i tre file sanitizzati attesi. Template FP3,
state root-only, immagini e materiale protetto non sono esportati.

## Causalità `sudo` persistente

La baseline crea il PAM `goodix-d285-01-sudo` con
`pam_fprintd.so max-tries=1 timeout=45`, fallback `pam_unix.so` e deny finale;
un file sudoers per il solo utente seleziona quel PAM senza sovrascrivere
`/etc/pam.d/sudo`. Il drop-in fprintd seleziona il wrapper persistente, che
prima dell'exec verifica SHA del daemon, manifest runtime, symlink e allowlist
del solo driver Goodix.

Il control-flow riduce authselect prima di avviare fprintd, verifica che
`system-auth` non contenga pam_fprintd, carica la candidate dal path legato al
full SHA, completa l'enrollment e pinna path/hash dell'unico template. Dopo un
restart obbligatorio ricontrolla il mapping della candidate, invalida il
timestamp sudo ed esegue una sola invocazione `sudo -v`. Il successo viene
accettato soltanto con return code zero, una epoch VERIFY e un unico outcome
SIGFM `match` nel journal. Solo dopo questi gate scrive lo state e marca
l'installazione committed.

La capture osserva esattamente questa catena: enrollment a otto stage, restart
dichiarato, VERIFY con 75 submit e match del sample 1 a score 584 rispetto alla
soglia 40, quindi `sudo -v` zero. La causalità biometrica è pertanto
`VERIFIED_BASELINE_AND_LIVE_MATCH`, non inferita dal solo return code.

## Lifecycle e safety

Le due epoch ENROLL e VERIFY consumano due action, due handshake TLS e 203 +
75 = 278 submit reali. Entrambe terminano con outstanding zero, backend
drenato e context chiuso. Retry secure/post, reopen, reset, clear-halt e
famiglie persistenti note sono zero. Lo zero della allowlist persistente non è
una prova assoluta contro effetti NVM sconosciuti, ma non emerge alcun marker
anomalo. Il transcript mostra sette stage intermedi e un completion, nessun
gate refusal e nessun prompt password.

## Stato host corrente osservabile senza privilegi

Dopo la run, probe read-only separati osservano authselect
`local with-silent-lastlog with-mdns4`, configurazione valida,
`system-auth` con zero pam_fprintd e `fingerprint-auth` fail-closed. PAM,
wrapper, drop-in e runtime sono root-owned con i mode previsti; lo state è
`0600 root:root`. Il manifest runtime sul path baseline-pinned verifica tutti
i sei artefatti. `systemctl cat` include il drop-in D285; il daemon è inattivo,
stato compatibile con il servizio D-Bus on-demand dopo idle. `rpm -V libfprint`
non segnala drift del payload e la libreria di sistema ha SHA-256
`d71d98e80eacd49b515ef1999016a540b6e39dc5009a6f84b1924e977d472504`.

Il contenuto dello state, il sudoers e il template root-protected non sono
stati letti dall'AI. La loro creazione e coerenza alla fine della run sono
verificate dal control-flow baseline e dai gate di successo; la coerenza
corrente diretta resta un boundary privilegiato per D286. Nessun accesso
fprintd/USB/sensore è stato eseguito durante questa review.

## Closure

Gli entrypoint di installazione D285 ora rifiutano prima di candidate o
staging; l'uninstall ownership-pinned resta disponibile. Il rischio
`SAME_FINGER_FALSE_NON_MATCH_OCCASIONALE` resta valido e un futuro non-match
isolato non dimostrerà da solo un guasto della persistenza.

```text
OUTCOME=PASS_LIVE_CLOSED_ACTIVE_INSTALLATION
ADVANCEMENT=REAL_PERSISTENT_SUDO_BIOMETRIC_INSTALL_AND_RESTART_COMPLETED
EXECUTABLE_CLOSURE=PASS_LIVE_WITH_HASH_PINNED_REVIEW
RESIDUAL_BLOCKER_OR_RISK=POST_REBOOT_SURVIVAL_AND_CURRENT_PRIVILEGED_STATE_TEMPLATE_ROLLBACK_COHERENCE_NOT_YET_PROVEN
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_PLUS_HASH_PINNED_PRIVATE_CAPTURE
NEXT_BOUNDARY=D286_PERSISTENT_SURVIVAL_AND_ROLLBACK_READINESS
```
