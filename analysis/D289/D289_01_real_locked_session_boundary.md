<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D289/01 — boundary unlock della sessione KDE realmente bloccata

## Decisione del boundary

```text
SELECTED_NEXT_BOUNDARY=REAL_KDE_LOCKED_SESSION_UNLOCK
OUTCOME=READY_FOR_HUMAN_GATE
ADVANCEMENT=REAL_LOCK_PAYLOAD_IMPLEMENTED_ON_REUSABLE_HARNESS
EXECUTABLE_CLOSURE=PASS_OFFLINE
REAL_TARGET_COMPATIBILITY=PASS_WITH_PRIVILEGED_NAMESPACE_PREFLIGHT_AT_LIVE
RESIDUAL_BLOCKER_OR_RISK=ONE_MANUAL_REAL_LOCK_FACTORY_PRESERVING_VERIFY_SERIES
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
LIVE_EXECUTION_PERFORMED=false
```

D288 ha già chiuso consumer, PAM, Polkit, fprintd, Goodix VERIFY, SIGFM MATCH
e propagazione a `Unlocked` nel greeter `--testing`. Il delta più piccolo e
probante è ora la proprietà mancante dello stesso percorso: lock orchestrato
da KWin e transizione reale della sessione. SDDM è più distante perché usa
`plasmalogin → password-auth`, oggi privo di pam_fprintd, e introduce creazione
di sessione. Packaging e integrazione generale esporrebbero più consumer prima
che i due boundary desktop siano provati.

## Audit architetturale e target

Il sorgente upstream KScreenLocker `v6.7.5`, commit
`057b3774d9ad322cfccc2683ea057aed87e0f878`, mostra che `KSldApp` conserva un
`QProcessEnvironment`, crea il greeter con `QProcess`, legge il marker esatto
`Unlocked\n` dal suo stdout e chiama `doUnlock()`. Il service D-Bus installato
espone `Lock` e `GetActive`, ma non un setter dell'environment del greeter.
Poiché KWin è già in esecuzione, il preload D288 non può essere ereditato dal
nuovo figlio senza riavviare o mutare il processo KWin.

Le query target read-only osservano Fedora 44, KWin/KScreenLocker/Plasma
6.7.5, sessione Wayland logind attiva e non bloccata, e
`org.freedesktop.ScreenSaver` posseduto da `/usr/bin/kwin_wayland`. Hash di
KWin, `libKScreenLocker`, greeter, QML e PAM sono pin nel pre/post audit. Il
PAM di sistema `kde-fingerprint` include `fingerprint-auth`, che D285 mantiene
fail-closed mentre `with-fingerprint` è disabilitato; `kde` password resta una
stack separata e integra.

## Metodo minimo

Il payload `d289-real-locked-session` riusa senza modifiche il common Live
Probe Harness. Dopo la conferma operatore, un helper `pkexec` verifica il PID
KWin, UID e uguaglianza del mount namespace, copia il PAM a un path root-only
sotto `/run` e crea un bind mount read-only sul solo
`/etc/pam.d/kde-fingerprint`. L'helper rimane collegato al payload tramite
pipe: `RELEASE`, EOF, segnale o errore portano sempre a unmount, verifica
dell'hash host originale e rimozione del runtime. Un mount preesistente viene
rifiutato e non viene mai smontato dall'helper.

Il payload chiama `org.freedesktop.ScreenSaver.Lock`, richiede
`GetActive false → true`, un solo greeter con parent KWin e cgroup utente, una
sola epoch Goodix e poi `GetActive false`. Solo la congiunzione MATCH e
transizione a unlocked classifica il boundary. Dopo NO_MATCH l'operatore usa
la password esclusivamente per recuperare il vero lock; un nuovo ciclo richiede
`TENTATIVO 2/3`. Nessun comando forza l'unlock nel payload.

## Safety e stop conditions

Massimo tre cicli/action/contatti, ogni PAM con `max-tries=1`, zero retry
automatico o implicito e timeout harness 900 s. Ogni epoch richiede
attempted/rejected/consumed `1/0/1`, TLS e first-image uno, zero
secure/post retry, reopen, reset, clear-halt, famiglie persistenti e
outstanding, con drained/context-closed uno. Il servizio password `kde` non è
montato né scritto. Pre/post root audit D286, stato D-Bus unlocked e assenza di
greeter/mount/runtime residui sono gate.

La finestra breve dell'overlay resta una modifica runtime host: un altro
processo che invocasse proprio `kde-fingerprint` la vedrebbe. Per questo il
gate rifiuta greeter preesistenti e chiude l'overlay dopo ogni singolo ciclo,
prima di offrire il successivo. Un reboot elimina comunque il bind mount;
istruzioni TTY e password recovery sono
esplicite. Nessuna live, lock, USB, PAM fingerprint o operazione privilegiata
è stata eseguita dall'AI.

## Verifiche offline e comando

`bash -n`, il percorso harness `--offline-test` e i 14 contratti D289 sono
PASS; la regressione high-risk pertinente D286–D289 è `176/176 PASS`.
L'offline path non invoca D-Bus Lock, `pkexec`, mount, pam_fprintd,
fprintd, USB o sensore. La verifica residua di namespace/mount e il vero lock
sono intrinsecamente privilegiati/live e costituiscono il prossimo Human Gate.

```bash
operator_kit/live_probe/run.sh d289-real-locked-session --operator-run
```
