<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D284/01 — decisione di integrazione e pilot `sudo` transiente

## Real Target Compatibility Gate

Il target letto direttamente è Fedora Linux 44 KDE, x86_64. Le versioni
pertinenti sono authselect 1.7.1, PAM 1.7.2, fprintd/fprintd-pam 1.94.5,
libfprint 1.94.100, sudo 1.9.17p2 e Plasma Workspace/Login Manager 6.7.4.
`authselect current --raw` restituisce
`local with-silent-lastlog with-mdns4 with-fingerprint`; `authselect check` è
PASS.

La topologia reale non consente un'attivazione globale prudente:

- `system-auth` contiene `pam_fprintd.so` senza `max-tries`, quindi usa il
  default documentato di tre;
- `sudo`, `kcheckpass` e `kscreensaver` includono `system-auth`;
- `password-auth` non contiene pam_fprintd;
- Plasma Login usa `/usr/lib/pam.d/plasmalogin` → `password-auth`, quindi non
  è già predisposto allo stesso percorso;
- `kde-fingerprint` esiste come stack separata, ma non è il servizio osservato
  di Plasma Login 6.7.4.

```text
REAL_TARGET_COMPATIBILITY=PASS
GLOBAL_DRIVER_ACTIVATION_WITH_CURRENT_PAM=REJECTED_TOO_BROAD
SYSTEM_AUTH_DEFAULT_FPRINT_MAX_TRIES=3
PLASMA_LOGIN_FIRST_TARGET=NO
```

## Decisione

Il primo boundary reale sarà un pilot `sudo -v` transiente e limitato al solo
utente operatore. La scelta di `sudo` non è assunta a priori: deriva dal fatto
che è il consumer reale già cablato sul target, verificabile senza logout o
blocco schermo e recuperabile dal processo root che mantiene il rollback.

Il kit non modifica `system-auth`, `password-auth`, authselect, login o KDE.
Installa temporaneamente due nuovi file con nomi D284:

- `/etc/pam.d/goodix-d284-01-sudo`, con `pam_fprintd.so max-tries=1
  timeout=45`, seguito da `pam_unix.so` come fallback;
- `/etc/sudoers.d/90-goodix-d284-01-pilot`, con un override `pam_service`
  ristretto al solo utente.

Il daemon usa la candidate in `/run` e uno storage isolato D284 sotto
`/var/lib/fprint`; la libreria di sistema non viene sostituita. Gli override
vengono rimossi subito dopo `sudo -v`, prima del delete. Il trap root ripete il
cleanup su ogni uscita e confronta hash di sudo/authselect, unit, libreria e
inventario storage preesistente.

## Scope e limiti probatori

Il pilot può provare una autenticazione PAM reale del consumer `sudo` con
fallback password preservato. Non prova Plasma Login, lock screen, affidabilità
statistica, installazione permanente, packaging RPM o comportamento dopo
reboot/update. Un match SIGFM e return code `sudo -v` zero sono entrambi
necessari; il solo return code non basta perché potrebbe derivare dalla
password.

## Closure offline e review PM

Il launcher è sintatticamente valido e il preflight completo costruisce
realmente la candidate Fedora 44/SIGFM, chiude l'ABI verso il vero fprintd,
valida con `visudo` l'override per-utente, esercita lo staging dei sei oggetti
runtime e prova la rimozione bounded dei due soli file temporanei. Prima dello
staging la live verifica inoltre, come root, che l'utente abbia già una policy
sudo valida. La matrice
D284 è `24/24 PASS`; la matrice combinata D282–D284 è `146/146 PASS` fuori dal
sandbox, necessario soltanto per i test host-only PAM/systemd. Il preflight
termina con return code zero e dichiara esplicitamente zero enumerazione USB,
zero accesso al sensore e zero live.

La review ha individuato e corretto due failure-path prima della closure:

- ogni failure successivo a enrollment o `sudo -v` acquisisce ora phase,
  return code, raw client e journal prima del rollback;
- il cleanup non dichiara più invalidato il timestamp `sudo` se `sudo -K`
  fallisce; in quel caso forza anche il rollback a false;
- qualunque `ROLLBACK_COMPLETE=false` forza ora anche un exit root nonzero,
  affinché un export riuscito non mascheri il fallimento di ripristino.

Un primo preflight ha inoltre scoperto che il trap offline catturava una
variabile locale `work` ormai fuori scope e mascherava il rifiuto del cleanup
regression. Il correttivo usa stato globale dedicato, rifiuta qualunque path
fuori dal prefisso temporaneo D284 e ha regressioni positive e negative. I
quattro workdir temporanei lasciati da quelle prove fallite sono stati rimossi
esplicitamente; la run conclusiva non lascia residui.

Il review PM accetta quindi il kit offline. Non ne consegue autorizzazione per
l'agente a eseguirlo: la prossima azione è la singola Human Gate manuale
descritta in `operator_kit/d284-01-transient-sudo-pilot/README_IT.md`.

```text
OUTCOME=READY_OFFLINE_HUMAN_REQUIRED_OPERATOR_RUN
ADVANCEMENT=MATERIAL_ARCHITECTURAL_DECISION_AND_BOUNDED_REAL_CONSUMER_PATH
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=PRIVILEGED_SENSOR_REACHING_PAM_CONFIGURATION_PILOT
CANONICAL_DOCUMENTATION=GOODIX_TECHNICAL_MANUAL_UPDATED
REVIEW_SET=GIT_NATIVE
```
