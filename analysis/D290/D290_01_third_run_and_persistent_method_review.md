<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D290/01 — terza run e review PM del metodo persistente

## Decisione

```text
PM_DECISION=HUMAN_REQUIRED
D290_CLOSED_SUCCESSFULLY=true
OUTCOME=PASS_LIVE_CLOSED
ADVANCEMENT=REAL_PLASMALOGIN_FINGERPRINT_MATCH_TO_NEW_WAYLAND_SESSION_PROVEN
EXECUTABLE_CLOSURE=PASS_LIVE_OPERATOR_OBSERVATION_PLUS_READ_ONLY_HOST_CORROBORATION
RESIDUAL_BLOCKER_OR_RISK=NO_D290_BLOCKER_PROJECT_LEVEL_PLAN_REQUIRES_USER_REVIEW
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_PLUS_HASH_PINNED_SANITIZED_CAPTURE
AI_PRIVILEGED_OR_SENSOR_REACHING_EXECUTION_PERFORMED=false
```

## Chiusura live D290

La live one-shot sulla baseline `31b0548a5613406b11e7311b8744ec25bca445c5`
ha raggiunto una VERIFY integra ma ha prodotto `SIGFM_RESULT=no_match`, zero
nuove sessioni grafiche e rollback completo PASS. Non prova il login.

L'Utente ha poi applicato direttamente al solo PAM `plasmalogin` la riga
fingerprint sufficient con `max-tries=3 timeout=45 debug`, ha riavviato dal
menu KDE e ha osservato MATCH e ingresso diretto nella nuova sessione grafica
senza password. La raccolta read-only dello stesso boot mostra una sola epoch
VERIFY integra, `result=match`, sessione logind `Service=plasmalogin`,
`Type=wayland`, `Class=user`, e apertura PAM dallo stesso PID leader 1550
subito dopo il MATCH. L'evidenza sanitizzata è hash-pinned in
`captures/D290_01/D290_01_MANUAL_SUCCESS_20260912T193632Z/sanitized/`.

```text
D290_REAL_PLASMALOGIN_FINGERPRINT_LOGIN=PROVEN
D290_REAL_NEW_WAYLAND_SESSION_AFTER_FINGERPRINT=PROVEN
D290_PASSWORDLESS_FINGERPRINT_LOGIN=PROVEN
D290_DIRECT_OPERATOR_OBSERVATION=PASS
D290_FINGERPRINT_SERIES_POLICY=max_3_stop_on_first_match
```

## Chiusura della terza run

La capture
`captures/live_probe/d290-plasmalogin_20260912T155916Z_4d6fb16350bb/sanitized/`
ha manifest integro e baseline completa
`4d6fb16350bb3bbe7a7908b4b611b294825ca00d`. Il pre-audit è PASS con una sola
sessione iniziale Plasma Wayland. Contrariamente all'assunto del prompt di
ripresa, `root-overlay.log` e `payload.log` contengono tutti i marker
`DAEMON_IDENTITY`, `NAMESPACE_MATCH`, `OVERLAY_READ_ONLY`, `OVERLAY_READY` e
`USER_OVERLAY_VISIBLE` a `true`.

L'Utente non ha eseguito logout né contatto. L'interruzione ha dato payload rc
130, poi `OVERLAY_UNMOUNTED`, `HOST_PAM_RESTORED`, `RUNTIME_REMOVED`, cleanup e
post-audit PASS. Il post-audit registra zero azioni sensore; non esistono
telemetria, login-state o outcome e il journal diagnostico non contiene
marker Goodix. Nessun valore di password viene riprodotto o registrato.

Dopo il riavvio la review read-only ha verificato PAM non mountpoint, hash
originale `c6fc4a0bc2d89f88fa15ca7e9a6c5aaeccfbe66897755b5416ce9c5e35b4e40b`,
`root:root:0644`, contesto `system_u:object_r:lib_t:s0`, runtime assente e zero
processi residui. `plasmalogin.service` è `active/running`, ExecStart è
`/usr/bin/plasmalogin`, cgroup `/system.slice/plasmalogin.service`; esiste una
sola sessione utente Wayland tty2 e non risultano marker Goodix/VERIFY dopo il
cursor della run. Non è necessaria recovery del vecchio metodo.
La fotografia macchina è in `D290_01_post_reboot_read_only_assessment.env`.

## Cambio metodo e implementazione

Il boundary non cambia. Il vecchio esperimento è disarmato con
`LIVE_CAPABLE=false` e conservato per audit/test. Il nuovo micro-kit espone un
solo script con ARM, CLOSE e ROLLBACK e non usa TTY3, daemon, service, FIFO,
socket, watchdog, `coproc` o bind mount.

La review byte-level conferma candidato SHA-256
`89d389e6c2ee59dcee374029a5428a81dc9138c4f5e86068159b3d5a2c77ab2d` come
PAM Fedora originale più la sola riga fingerprint `sufficient`, bounded da
`max-tries=1 timeout=45`, prima di `password-auth`. Account/password/session
restano identici; authselect e PAM condivisi non vengono modificati.

ARM è fail-closed su branch/provenance/critical set, hash e delta, package,
owner/mode, contesto SELinux reale e policy `matchpathcon`, D286/fallback,
cardinalità target, vecchi residui e stato preesistente. Backup e stato sono
root-only; una failure prima di ARMED ripristina immediatamente bytes,
owner/mode/context. Lo script non esegue reboot.

CLOSE registra boot/sessione/journal correnti, impone un'unica epoch e tenta
sempre rollback anche su failure di raccolta o setup capture. Il rollback
accetta soltanto candidato o originale attesi, ripristina e verifica SHA,
metadata, contesto SELinux, package-owned target e D286/fallback prima di
rimuovere lo stato. ROLLBACK usa lo stesso percorso e resta disponibile da
TTY; drift inatteso conserva backup e stato.

## Micro-corrective finale: metadata e causalità

Il backup conserva ora la `mtime` originale e lo stato ARM ne vincola il
valore. Ogni percorso di ripristino applica la `mtime` del backup prima delle
verifiche finali. ARM registra inoltre return code e hash dell'output completo
di `rpm -V plasma-login-manager`; dopo il rollback la verifica deve coincidere
esattamente con quel baseline. È quindi ammesso soltanto l'eventuale drift di
package già presente prima di ARM, mentre qualunque nuovo drift, sul PAM target
o su un altro file del package, fallisce chiuso e conserva stato e backup. Il
target PAM non può avere drift già al baseline.

La classificazione `PASS_MATCH_NEW_SESSION` richiede ora, oltre alla singola
epoch valida e al SIGFM MATCH, una sessione logind dell'UID operatore con
`Service=plasmalogin`, `Type=wayland`, `Class=user`, leader numerico e
timestamp monotono. Nel journal dello stesso boot deve comparire esattamente
una apertura PAM `plasmalogin:session` attribuita a quel leader, dopo il MATCH
ed entro due secondi; non deve comparire la continuazione auth password
`pam_kwallet5(plasmalogin:auth)`. Un MATCH con sessione successiva di recovery
password o privo di questa correlazione è `AMBIGUOUS_REVIEW_REQUIRED`, mai
PASS.

La scelta dei marker è corroborata sul target da osservazione read-only:
logind espone `TimestampMonotonic` e `Leader` per la sessione Wayland corrente;
il journal `plasmalogin` lega l'apertura sessione al PID leader e, nel percorso
password osservato, emette prima il marker `pam_kwallet5(plasmalogin:auth)`.
L'operatore non deve comunque usare la password grafica prima di CLOSE: se il
fingerprint non entra direttamente nel desktop, passa a TTY3, esegue CLOSE,
attende il rollback PASS e soltanto dopo torna al greeter.

## Review e verifiche

La review PM ha corretto due gap prima dell'accettazione: ARM confronta ora il
contesto corrente con la policy SELinux attesa, e il rollback di emergenza
pre-ARMED verifica anche owner/mode/context. La race di uscita CLOSE riconosce
un rollback concorrente completato solo con file originale e metadata/context
attesi. Poiché le modalità reali girano dopo `pkexec`, la root Git viene
derivata dalla posizione dello script e ogni lettura Git usa un
`safe.directory` one-shot limitato a quella root; nessuna configurazione Git
globale viene scritta.

- `bash -n` del nuovo script: PASS;
- contratto del micro-kit: `18/18 PASS`;
- cattura terza run e manifest: PASS;
- vecchio D290 disarmato, ma test storico offline preservato: PASS;
- regressione common harness + D286–D290: `249/249 PASS`;
- nessuna invocazione reale di `pkexec`, PAM, reboot, USB o sensore da parte
  dell'AI.

```text
D290_01_EPHEMERAL_OVERLAY_METHOD=ABANDONED_DO_NOT_RERUN
D290_01_REASON=HOST_ORCHESTRATION_COMPLEXITY_EXCEEDED_BOUNDARY_VALUE
D290_01_NEW_METHOD=PERSISTENT_REVERSIBLE_SINGLE_SERVICE_PAM_TEST
D290_01_GLOBAL_AUTHSELECT_FINGERPRINT_REENABLE=false
D290_01_PASSWORD_FALLBACK_PRESERVED=true
D290_01_REBOOT_SAFETY=PINNED_PACKAGE_STATE_AND_TTY_ROLLBACK
D290_01_ROLLBACK_MTIME_AND_PACKAGE_BASELINE=PASS
D290_01_DIRECT_LOGIN_CAUSALITY=PASS_LIVE_CORROBORATED
D290_01_PERSISTENT_KIT=HISTORICAL_ONLY_DO_NOT_RERUN
D290_01_REAL_LOGIN=PROVEN
D290_01_PM_REVIEW=PASS
D290_01_NEXT_STATE=CLOSED_SUCCESSFULLY
```
