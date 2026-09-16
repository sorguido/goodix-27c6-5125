<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D289/01 — review AI PM del payload real locked-session

```text
PM_DECISION=HUMAN_REQUIRED
OUTCOME=READY_FOR_ONE_MANUAL_BOUNDED_REAL_LOCK_SERIES
EXECUTABLE_CLOSURE=PASS_OFFLINE
REAL_TARGET_COMPATIBILITY=PASS_WITH_LIVE_PRIVILEGED_NAMESPACE_GATE
LIVE_EXECUTION_PERFORMED=false
```

La review ha riesaminato direttamente il boundary post-D288, il sorgente
upstream KScreenLocker 6.7.5, lo stato target read-only, common harness, config,
PAM, payload, helper root, audit, cleanup, sanitizer, classifier, istruzioni,
test e manuale. Il common harness non cambia; D289 è un payload compatibile e
limitato al nuovo lifecycle di lock.

Finding chiusi durante la review:

1. il primo cleanup avrebbe potuto smontare un mount preesistente non
   posseduto dopo un rifiuto; ora `umount` è raggiungibile soltanto dopo che lo
   stesso helper ha creato o riconosciuto in recovery l'overlay hash-pinned;
2. il PAM root-only iniziale era mode `0600`, illeggibile dal greeter utente;
   ora è `0644` dentro runtime `0700`, il bind è read-only e il payload verifica
   dalla vista utente sia candidato sia password service invariato;
3. un overlay unico sarebbe rimasto esposto durante recovery e conferme fra
   cicli; ora ogni ciclo crea al massimo un overlay, attende la morte del
   greeter, lo rilascia e soltanto dopo può offrire un nuovo tentativo;
4. lo stato D-Bus unlocked può precedere di poco il reap del greeter; payload e
   post-audit attendono bounded la sua assenza prima di rilasciare/chiudere;
5. un failure di unmount conserva il runtime ed espone una recovery dedicata
   `--recover`, che rifiuta contenuti diversi dal candidato e non rilancia la
   live;
6. owner D-Bus, PID/exe/UID KWin e parent del greeter sono ricontrollati; la
   transizione `false → true → false` non viene dedotta dal solo exit del
   greeter.

La regressione high-risk pertinente passa `176/176`: D286, vecchio greeter
D287, PAM active-user D287, common harness, D288 e D289. `bash -n`,
`git diff --check` e il percorso D289 `--offline-test` da cwd esterna sono
PASS. `shellcheck` non è installato. Le query read-only target confermano
versioni/hash, sessione Wayland attiva e owner KWin del service; non hanno
bloccato la sessione né raggiunto PAM/fprintd/USB.

Il residuo non è riproducibile offline: `pkexec`, uguaglianza del namespace
vista da root, bind mount temporaneo, vero metodo `Lock`, greeter reale e fino
a tre VERIFY/contatti. Sono Human Gate concreti. Il kit è fail-closed e
direttamente eseguibile dall'operatore; l'AI non esegue `--operator-run`.
