<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D290/01 — terza run e review PM del metodo persistente

## Decisione

```text
PM_DECISION=ACCEPT_AND_CONTINUE_TO_HUMAN_GATE
OUTCOME=READY_FOR_HUMAN_GATE_PERSISTENT_REVERSIBLE_METHOD
ADVANCEMENT=OLD_HOST_ORCHESTRATION_CLOSED_AND_MINIMAL_REVERSIBLE_PATH_READY
EXECUTABLE_CLOSURE=PASS_OFFLINE_PLUS_POST_REBOOT_READ_ONLY_ASSESSMENT
RESIDUAL_BLOCKER_OR_RISK=REAL_REBOOT_GREETER_PAM_FPRINTD_USB_AND_ONE_CONTACT
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
AI_PRIVILEGED_OR_SENSOR_REACHING_EXECUTION_PERFORMED=false
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
- contratto del micro-kit: `17/17 PASS`;
- cattura terza run e manifest: PASS;
- vecchio D290 disarmato, ma test storico offline preservato: PASS;
- regressione common harness + D286–D290: `248/248 PASS`;
- nessuna invocazione reale di `pkexec`, PAM, reboot, USB o sensore da parte
  dell'AI.

```text
D290_01_EPHEMERAL_OVERLAY_METHOD=ABANDONED_DO_NOT_RERUN
D290_01_REASON=HOST_ORCHESTRATION_COMPLEXITY_EXCEEDED_BOUNDARY_VALUE
D290_01_NEW_METHOD=PERSISTENT_REVERSIBLE_SINGLE_SERVICE_PAM_TEST
D290_01_GLOBAL_AUTHSELECT_FINGERPRINT_REENABLE=false
D290_01_PASSWORD_FALLBACK_PRESERVED=true
D290_01_REBOOT_SAFETY=PINNED_PACKAGE_STATE_AND_TTY_ROLLBACK
D290_01_PM_REVIEW=PASS
D290_01_NEXT_STATE=HUMAN_REQUIRED
```
