<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D287/01 — review post-live PAM/fprintd del greeter reale

## Esito

```text
OUTCOME=FAIL_HOST_POLKIT_CONTEXT_BEFORE_VERIFY
ADVANCEMENT=REAL_GREETER_AND_PAM_FPRINTD_PREVERIFY_POLKIT_BOUNDARY_REACHED
EXECUTABLE_CLOSURE=FAIL_OBSERVABILITY_AND_LAUNCH_CONTEXT
RESIDUAL_BLOCKER_OR_RISK=ACTIVE_USER_SESSION_PAM_PROBE_REQUIRES_HUMAN_LIVE
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_PLUS_HASH_PINNED_PRIVATE_CAPTURE_AND_RECOVERED_JOURNAL
PM_DECISION=REPLAN
```

Non è un `FINGERPRINT_FAILED`: il modulo fingerprint non ha iniziato alcuna
VERIFY. La run ha invece raggiunto il greeter reale, `pam_fprintd.so` e il
daemon fprintd, poi si è arrestata sul controllo Polkit di
`ListEnrolledFingers`, prima di `Claim` e `VerifyStart`.

## Integrità e classificazione della capture

La baseline è `d0679cf9a725bf0f23a60f53eff0eafac9b0ed29`; il boot ID è
`af986ce0-5fea-4aae-bd5e-4d483b0a5c4f`. Gli hash ricalcolati coincidono con
quelli consegnati:

```text
0147fc61bece845a8fcb39be0cab249186f4149f8a07b05fcb675da664563019  root-series.log
46ef541179a979c38231cbb37224b08bf0d85b352b67a7d420f882c5bf33d938  summary.env
```

Pre-audit e post-audit D285 sono integralmente PASS e contano zero azioni
sensore. Il greeter ha emesso readiness, poi è uscito con RC 0 e marker
`Unlocked`; il classificatore ha correttamente rifiutato MATCH perché journal,
epoch VERIFY, extract, confronti, match e no-match erano tutti a zero. L'esito
canonico è quindi `FAIL_HOST_POLKIT_CONTEXT_BEFORE_VERIFY`, non `MATCH`,
`NO_MATCH` o failure biometrico.

## Timeline causale

| Momento | Stato | Evidenza e classificazione |
|---|---|---|
| conferma operatore | accettata | **OBSERVED** in `root-series.log` |
| cursor | globale del boot, poi filtro unit | **VERIFIED** dal control flow della baseline e dal journal recuperato |
| namespace/PAM overlay | greeter reale raggiunto con service dedicato | **VERIFIED** da readiness, processo reale e successiva chiamata fprintd; dettagli mount non esportati singolarmente |
| greeter | PID 50633, UID 1000, `--testing` | **VERIFIED** dal journal |
| contesto logind | cgroup `/user.slice/user-0.slice/session-c3.scope`; sessione `c3` di root `background-light` | **VERIFIED** dal journal; `runuser` ha cambiato UID, non il cgroup/session context |
| QML/auth | il movimento rende visibile la UI e chiama `startAuthenticating()` | **VERIFIED** dal QML 6.7.5; **INFERRED** per la run dalla successiva attività PAM |
| fan-out PAM | `kde` interattivo + `kde-fingerprint` e `kde-smartcard` non interattivi | **VERIFIED** dal sorgente upstream 6.7.5 |
| fingerprint PAM | `pam_fprintd.so` ha aperto il system bus e interrogato fprintd | **VERIFIED**: l'overlay contiene solo quel modulo e fprintd registra `ListEnrolledFingers` |
| fprintd | start 23:34:06.942, ready 23:34:07.099 | **OBSERVED** nel journal |
| authorization | `ListEnrolledFingers` negata per `net.reactivated.fprint.device.verify` | **OBSERVED** alle 23:34:07.113 |
| Claim/VerifyStart/runtime | non raggiunti | **VERIFIED** dal flow di `pam_fprintd.c`, dall'assenza di `VerifyStart` e dalla telemetria zero |
| input credenziale | almeno un `pam_unix(kde:auth)` fallisce alle 23:34:53 | **OBSERVED**; l'operatore riferisce di aver poi usato la credenziale per uscire |
| `Unlocked`/exit 0 | aggregato OR di tutti gli autenticatori | **VERIFIED** dal sorgente; il fingerprint è escluso perché fallito prima di VERIFY. Il successo interattivo è la spiegazione causale più forte in base all'osservazione dell'operatore, ma il log perso non identifica direttamente il backend vincente |
| cleanup/post-audit | greeter chiuso, fprintd idle-exit, post-audit PASS | **OBSERVED**; nessun drift noto |

Il primo tentativo password fallito visibile alle 23:34:53 non contraddice il
successivo successo: `pam_unix` non registra normalmente la riga equivalente
per un successo e KScreenLocker consente un nuovo invio dopo il delay. Non è
possibile ricostruire il numero esatto di input dal materiale sanitizzato. Il
PIN/password interattivo spiega quindi fortemente, ma non prova da solo, il
backend che ha prodotto `Unlocked`; non esiste evidenza di successo smartcard.

## Causa del mancato VERIFY

La policy installata di `net.reactivated.fprint.device.verify` dichiara
`allow_active=yes`, `allow_inactive=no`, `allow_any=no`. `pkexec` ha creato alle
23:33:56 la sessione logind `c3` di root, classe `background-light`. Il greeter
lanciato più tardi con `runuser -u <USER>` aveva UID 1000, ma journal e cgroup
lo collocano ancora in `session-c3.scope`, sotto `user-0.slice`, non nella
sessione grafica attiva `2` dell'utente.

Il daemon ha pertanto negato il diritto VERIFY. Nel sorgente Fedora fprintd
1.94.5, `ListEnrolledFingers` richiede proprio tale diritto. Nel modulo
`pam_fprintd`, `open_device()` invoca prima `GetDevices`, poi
`ListEnrolledFingers`; se quest'ultima fallisce, registra zero print e restituisce
nessun device. `do_auth()` ritorna quindi `PAM_AUTHINFO_UNAVAIL` senza `Claim` o
`VerifyStart`. Questo spiega direttamente `VERIFY_EPOCH_COUNT=0` e tutti i
contatori sensor-reaching a zero.

Il wrapper D285 è stato avviato come `ExecStart` effettivo del daemon e ha
superato i gate di integrità, ma il percorso Goodix di VERIFY non è stato
raggiunto. Non risultano AVC SELinux nella finestra.

## Semantica upstream e UX reale

Il tag upstream `v6.7.5` (`057b3774...`) costruisce tre autenticatori con lo
stesso utente: `kde` interattivo, `kde-fingerprint` e `kde-smartcard`
non-interattivi. `startAuthenticating()` li avvia insieme; `isUnlocked()` è
l'OR dei tre. Il marker stdout `Unlocked` non identifica quindi il backend.

`--testing` imposta sia `setTesting(true)` sia `setImmediateLock(true)`. Su
Wayland la view usa layer-shell, layer top, ancoraggio fullscreen implicito e
`KeyboardInteractivityExclusive`. L'opzione evita il vero lock orchestrato
della sessione, ma non una UX di lockscreen fullscreen con focus esclusivo.
La precedente frase “la sessione non viene bloccata” era tecnicamente troppo
stretta e operativamente fuorviante.

## Gap di osservabilità

`greeter.log` e `journal.log` vivevano nel tmpfs privato e il cleanup li ha
distrutti prima dell'export. `inner_log` conservava soltanto marker derivati ed
è stato copiato indirettamente in `root-series.log`. Il journal persistente ha
permesso di recuperare l'evento Polkit, ma non il log stdout/stderr completo del
greeter, il motivo interno dell'exit, i marker `pam_start`/`pam_authenticate` o
i messaggi QML debug. È un difetto di executable observability.

Un eventuale percorso futuro può esportare in sicurezza, sostituendo username,
PID e path temporanei: stdout/stderr del greeter; return code di
`pam_start`/`pam_authenticate`/`pam_end`; sole righe journal per KScreenLocker,
PAM, fprintd, logind e Polkit nella finestra; boot ID/cursor; causa di exit e
telemetria safety. Non deve esportare risposte PAM, PIN/password, PSK, template,
pixel o dati biometrici.

Le categorie più precise sono osservabili solo con tali segnali. Per questa
run è provata `FPRINTD_NOT_AUTHORIZED_BEFORE_VERIFY`; il generico
`GREETER_EXITED_BEFORE_OUTCOME` resta corretto ma insufficiente. Non è lecito
retro-classificare categorie come `FINGERPRINT_AUTHENTICATOR_UNAVAILABLE` dal
solo marker `Unlocked`; l'indisponibilità è invece dimostrata dal journal e dal
flow del modulo.

## Alternative e prossimo esperimento minimo

| Percorso | Cosa dimostra | Sensore/root/gate | Valutazione |
|---|---|---|---|
| rerun greeter invariato | ripete la stessa negazione Polkit | sensore no, root sì | rifiutato: nessuna ipotesi nuova |
| solo più logging sullo stesso launcher | rende visibile la stessa failure | sensore no, root sì | utile solo come diagnostica, non come nuovo esperimento |
| introspezione D-Bus/fprintd | disponibilità statica | può attivare daemon; niente VERIFY se strettamente limitata | non separa l'autorizzazione del caller reale |
| probe Polkit del caller | active/inactive del processo senza fingerprint | sensore no, root no | preflight necessario del percorso successivo |
| PAM `pam_start_confdir()` eseguito direttamente dalla sessione utente attiva | separa launcher/session context da PAM/fprintd/runtime e prova il superamento di `ListEnrolledFingers` | una VERIFY, niente root per PAM; Human Gate live | **prossimo esperimento minimo** |
| nuovo greeter con overlay in diverso namespace | consumer finale completo | root + UI esclusiva + VERIFY | prematuro finché il probe stretto non chiude Polkit/PAM |

Il runner `pam_start_confdir()` esiste già ed è stato validato in D283, ma la
run D283 avveniva nel processo root di staging. Il delta probante è eseguirlo
direttamente dal terminale della sessione grafica attiva, dopo un `pkcheck`
non interattivo sul subject completo PID/start-time/UID, contro il runtime D285
già installato. Una sola `pam_authenticate`, `max-tries=1`, una sola conferma e
una sola epoch distinguono nettamente l'ipotesi rimasta senza UI fullscreen.
È sensor-reaching e quindi non viene eseguito dall'AI.

## Riesame safety/UX

Un futuro greeter deve avere un escape path esplicito e provato; una credenziale
interattiva può restare disponibile per safety, ma il suo successo deve avere
un marker distinto e non può soddisfare il criterio fingerprint. La modalità
Wayland corrente prende focus esclusivo e non è accettabile descriverla come
facilmente dismissibile. Il probe PAM stretto evita del tutto questa UI. Una
nuova run del greeter sarà giustificabile solo dopo una soluzione al launch
context che preservi contemporaneamente sessione attiva e isolamento PAM.

```text
D287_01_REAL_GREETER_REACHED=true
D287_01_GREETER_TESTING_MODE_READY=true
D287_01_VERIFY_STARTED=false
D287_01_SENSOR_ACTION_COUNT=0
D287_01_NEW_DEVICE_SIDE_EVIDENCE=false
D287_01_GREETER_UNLOCK_MARKER_SOURCE=INTERACTIVE_OR_NONINTERACTIVE_PAM
D287_01_FINGERPRINT_SUCCESS_NOT_PROVEN=true
D287_01_ROOT_CAUSE=GREETER_RETAINED_PKEXEC_ROOT_BACKGROUND_LOGIND_CONTEXT
D287_01_NEXT_EXPERIMENT=ACTIVE_USER_SESSION_PAM_CONFDIR_SINGLE_VERIFY_PROBE
D287_01_PM_DECISION=REPLAN
D287_01_POST_LIVE_OFFLINE_CONTRACT_MATRIX=68/68_PASS
D287_01_POST_LIVE_COMBINED_REGRESSION_MATRIX=282/282_PASS_HOST_ENV
```
