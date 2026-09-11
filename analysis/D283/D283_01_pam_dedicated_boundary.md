<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D283/01 — servizio PAM dedicato, primo boundary target

```text
OUTCOME=READY_OFFLINE_HUMAN_REQUIRED
ADVANCEMENT=DEDICATED_PAM_CONFDIR_MAX_TRIES_1_OPERATOR_PATH
EXECUTABLE_CLOSURE=PASS_OFFLINE_REAL_LIBPAM_AND_CANDIDATE_BUILD
RESIDUAL_BLOCKER_OR_RISK=SAME_FINGER_FALSE_NON_MATCH_OCCASIONALE
CANONICAL_DOCUMENTATION=GOODIX_TECHNICAL_MANUAL_UPDATED
REVIEW_SET=GIT_NATIVE
```

D282/01 ha provato sul target enrollment, storage SIGFM, restart, match,
different-finger no-match, delete e rollback. D283/01 cambia un solo confine:
la VERIFY positiva viene richiesta tramite il modulo Fedora
`pam_fprintd.so`, non tramite `fprintd-verify`.

Il servizio `goodix-d283-01` vive esclusivamente nella candidate transiente e
contiene una sola regola:

```text
auth required /usr/lib64/security/pam_fprintd.so max-tries=1 timeout=45
```

Il runner usa `pam_start_confdir()`, quindi non scrive `/etc/pam.d`,
`system-auth`, `login` o `sudo`. Chiama soltanto `pam_authenticate()` e
`pam_end()`. La verifica offline reale usa lo stesso runner con un servizio
temporaneo `pam_permit` e passa contro `libpam.so.0`; il simbolo
`pam_start_confdir@@LIBPAM_1.4` è presente sul sistema. Il sorgente esatto
fprintd Fedora 44 interpreta `max-tries=`, inizializza il contatore con tale
valore, lo decrementa dopo un no-match e restituisce `PAM_MAXTRIES` a zero.

La futura run non usa PAM per ottenere privilegi: `sudo` serve soltanto ad
avviare manualmente staging e rollback. Nessun login o comando sudo viene
autenticato biometricamente. Il percorso crea storage fprintd isolato,
esegue un enrollment da otto contatti, riavvia il daemon e chiama una sola
conversazione PAM con l'indice destro. Poi elimina il template host-only e
ripristina servizio, drop-in, runtime e storage.

Il limite per invocazione è di due action biometriche e nove contatti. Il
launcher richiede `max-tries=1`, un solo epoch VERIFY, zero retry/reopen/reset/
clear-halt/persistenza nota, backend drenato e context chiuso. Il profilo
production continua inoltre a respingere una seconda action nello stesso open
epoch prima di generazione, TLS o submit USB.

La candidate e il servizio PAM sono hash-pinned; full SHA, branch
`development`, allineamento a `origin/development`, worktree live-critical,
NEVRA `fprintd-pam-1.94.5-5.fc44.x86_64`, linkage, cardinalità target,
SELinux, libreria e storage vengono verificati prima dello staging. Dopo il
restart il mapping della candidate viene verificato una seconda volta.

La seconda run valida D282/03 ha prodotto 3/3 match same-finger e 3/3 no-match
different-finger su due processi distinti, con audit safety puliti. La review
indipendente chiude quel prerequisito preliminare e sblocca D283/01 senza
attribuirgli significanza statistica.

Prima dello sblocco il percorso è stato ricontrollato contro le failure di
staging già note: ora copia esplicitamente i sei file runtime prima di creare i
symlink SONAME, inizializza `operator.log` e `summary.env` prima dello staging e
verifica l'export pre-action. Enrollment e PAM hanno conferme fisiche separate.
La closure positiva richiede inoltre nove estrazioni SIGFM, un solo outcome
matcher `match`, score osservato almeno pari a threshold e un solo epoch VERIFY.

Un eventuale fallimento PAM con il dito corretto resta ambiguo finché non si
leggono return code PAM e telemetria SIGFM: D282/01 e D282/02 hanno già mostrato
un false non-match same-finger occasionale. Il kit esporta entrambi e non
autorizza retry. La live PAM target, USB e staging privilegiato sono ora il
prossimo Human Gate; l'AI non li esegue.
