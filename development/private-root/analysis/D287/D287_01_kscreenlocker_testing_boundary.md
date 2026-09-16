<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D287/01 — boundary KScreenLocker standalone `--testing`

## Decisione AI-PM

D286 chiude la persistenza e la ripetibilità del consumer sudo. Il successivo
incremento minimo verso l’integrazione end-user è KScreenLocker, ma una prova
del blocco sessione reale introdurrebbe subito rischio di lockout e renderebbe
più difficile separare consumer, PAM e comportamento grafico. D287 seleziona
prima il percorso ufficiale standalone `kscreenlocker_greet --testing`.

Il pilot non riabilita `with-fingerprint` e non altera la configurazione PAM
host. Un tmpfs dentro un mount namespace per tentativo sovrappone read-only il
solo `kde-fingerprint` per il greeter figlio. Il file password `kde`, il sistema
host e l’installazione D285 restano invariati e vengono hash-auditati.

## Evidenza primaria e target locale

Il sorgente upstream è stato ispezionato read-only dal repository ufficiale
`https://invent.kde.org/plasma/kscreenlocker.git`, tag `v6.7.4`, commit
`28544d4910d5ea9be6708eb343804fa0018cb8e4`, e tag `v6.7.5`, commit
`057b3774d9ad322cfccc2683ea057aed87e0f878`. Non è stato copiato o adattato nel
progetto. La firma presente sull'oggetto tag 6.7.5 non è stata dichiarata
verificata perché la chiave pubblica non era disponibile localmente. Gli hash
dei file sorgente pertinenti sono identici nei due tag:

```text
70a973806f47306f4d348b04d110c100ee344da21340dfa08a229fafd360c0d8  greeter/main.cpp
5f6239fc1ec8f88f46f770402781355edf02374e9623692b2fdd8067c6abd00a  greeter/greeterapp.cpp
4fa76a0a575ba3e09fab7b06f3393a07dddd0ec3dc1de5b4ca44e6c63c3eca1f  greeter/pamauthenticator.cpp
1a6f24e49d50a1debb0246f95fb5d78f0d825cd5032f12c7940cc59e8a4c6d7c  greeter/pamauthenticators.cpp
950d0c418521b5bdc96eff7ad4a03ae532fc7c0bd80b93faf939b39800d9236e  greeter/CMakeLists.txt
```

**VERIFIED source-side:** `main.cpp` accetta `--testing`, imposta
`setTesting(true)` e non riceve un fd `ksld`; `greeterapp.cpp` evita input grab
quando `m_testing` ed istanzia autenticatore password `kde` e autenticatore
non-interattivo `kde-fingerprint`; `PamWorker::authenticate()` invoca una sola
`pam_authenticate()` per `tryUnlock()`; `PamAuthenticators` avvia entrambi ma
non riporta lo stato aggregato a `Idle` sul solo fallimento non-interattivo.
Il diff completo `v6.7.4..v6.7.5` tocca dodici file di versione, metadata,
notifiche e traduzioni, ma nessuno dei cinque file greeter sopra elencati:

```text
RELEVANT_GREETER_SOURCE_DIFF=EMPTY
```

**VERIFIED target-side dopo l'aggiornamento Fedora:** sono installati
`kscreenlocker-6.7.5-1.fc44.x86_64`,
`plasma-workspace-6.7.5-1.fc44.x86_64`, `pam-1.7.2-2.fc44.x86_64` e
`fprintd-pam-1.94.5-5.fc44.x86_64`. Il binario installato contiene ancora le
stringhe esatte `kde-fingerprint` e `kde-smartcard`. I PAM Fedora restano
separati (`kde` include `password-auth`; `kde-fingerprint` usa il substack
`fingerprint-auth`). Gli hash PAM e QML sono invariati rispetto alla prima
closure; è cambiato soltanto il binario greeter tra gli elementi hash-pinned:

```text
45d5a60737ff966b93f60639a662396956b28d50122741261f4351fef941be48  /usr/libexec/kscreenlocker_greet
7d91b3ad73a998e8b10f9edccd74ba04179a778c4a5e61d9176872f43c7bbac3  /etc/pam.d/kde
8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437  /etc/pam.d/kde-fingerprint
328501780ab06cc0497a25ff48c6f027a1abed8506f0969f39a5f8bc6696181c  LockScreenUi.qml
```

Queste verifiche chiudono il drift come aggiornamento point-release
compatibile per il boundary D287: modalità `--testing`, mancato input grab in
testing, selezione dei service PAM, singola `pam_authenticate()` per
`tryUnlock()`, semantica del failure non-interattivo e marker `Unlocked`/exit
zero non cambiano nel sorgente pertinente; QML e configurazione PAM installati
sono byte-identici. Non si tratta quindi di un repin basato sulla sola NEVRA.

Il QML installato chiama `startAuthenticating()` quando il form diventa
visibile, ignora nel proprio handler il failure non-interattivo e riavvia gli
autenticatori soltanto dopo un failure interattivo/password. È quindi scorretto
assumere due retry biometrici automatici del greeter. D287 usa tre processi
standalone distinti, ciascuno con `pam_fprintd max-tries=1` e conferma fisica
separata, rispettando la policy target-specific derivata da D286.

## Riesame metodologico pre-live

1. **Cosa cambia realmente rispetto a D286?** Cambia il consumer causale da
   `sudo -v` al binario KScreenLocker reale. Il PAM viene presentato solo nel
   mount namespace del greeter; non si riusa il percorso sudo e non si blocca
   la sessione.
2. **Quale nuova ipotesi viene testata?** Che KScreenLocker 6.7.5 selezioni
   davvero `kde-fingerprint`, propaghi un MATCH dal modulo PAM non-interattivo
   all’uscita positiva del greeter `--testing` e lasci invariati host e D285.
3. **Se fallisce nello stesso punto?** Nessun quarto contatto e nessun passaggio
   al lock reale. Si revisionano cursor journal, exit del greeter, namespace e
   segnale PAM/KScreenLocker; si cambia il metodo prima di ogni nuova live.

## Prima invocazione operatore e correttivo pre-live

L'Utente ha avviato manualmente `--operator-run` sul commit
`69b81c3f6fc4bdbfb86044581324637fd86df9ee`. Il launcher ha stampato
`analysis/D285: È una directory` e ha poi rifiutato la run con
`KSCREENLOCKER_NEVRA_DRIFT`. L'arresto è avvenuto prima di `pkexec`, greeter,
USB e sensore:

```text
D287_01_PRELIVE_OPERATOR_RUN=ABORTED_BEFORE_PRIVILEGE_AND_SENSOR
D287_01_SENSOR_CONTACTS_CONSUMED=0
D287_01_NEW_DEVICE_SIDE_EVIDENCE=false
D287_01_CORRECTIVE_REQUIRED=true
```

La review ha identificato due cause host-side indipendenti. Primo, mancava la
continuazione shell dopo `git status ... --`: l'array dei pathspec diventava
un nuovo comando e il controllo dirty poteva risultare inefficace. La
continuazione è stata corretta e tre fixture Git reali dimostrano ora: critical
set pulito accettato, file tracked modificato rifiutato, file untracked
rifiutato; un pathspec eseguibile-sentinella non viene eseguito. Secondo,
l'host era passato dalle build Plasma 6.7.4 alle 6.7.5. L'audit source/target
sopra documentato ne ha dimostrato la compatibilità pertinente prima di
aggiornare NEVRA e hash.

## Seconda invocazione e corrective orizzontale host-path

La seconda invocazione manuale usa la baseline
`dc09bad49913fd51529ad5d4cbe399bf2f04f04c` e produce la capture hash-pinned
`captures/D287_01/D28701_ATTEMPT_20260911T210420Z_dc09bad49913/sanitized/`.
Supera repository/host gate, `pkexec`, root-series e pre-audit D285; quest'ultimo
prova zero azioni sensore. Dopo la conferma testuale iniziale si arresta nella
creazione del cursor, prima di inner log, `unshare`, namespace, greeter e
VERIFY:

```text
D287_01_SECOND_OPERATOR_RUN=ABORTED_AFTER_PKEXEC_BEFORE_GREETER_AND_VERIFY
D287_01_SECOND_OPERATOR_BASELINE=dc09bad49913fd51529ad5d4cbe399bf2f04f04c
D287_01_SECOND_REFUSAL_REASON=JOURNAL_CURSOR_AMBIGUOUS
D287_01_SENSOR_CONTACTS_CONSUMED=0
D287_01_NEW_DEVICE_SIDE_EVIDENCE=false
D287_01_GREETER_STARTED=false
D287_01_VERIFY_STARTED=false
```

La riproduzione read-only su systemd 259 determina la causa precisa: il comando
filtrato `journalctl -b -u fprintd.service -n 0 --show-cursor --no-pager`
restituisce RC 0 e `-- No entries --`, ma nessun cursor perché l'unit non ha
entry pregresse nel boot. Il nuovo boundary ottiene il cursor dalla coda
globale del boot con `journalctl -b -n 0 --show-cursor --no-pager`; sul target
restituisce esattamente un cursor valido. La collection successiva conserva
sia `-u fprintd.service` sia `--after-cursor`, quindi non include eventi fprintd
precedenti e non usa timestamp o `--since`. Missing, multiple, malformed e
read failure hanno rifiuti distinti.

Due abort host-side consecutivi impongono un cambio da correzione sintomatica a
fix di classe. L'audit completo è in
`analysis/D287/D287_01_HOST_PATH_AUDIT.md`: il vero control flow di
`d287_operator_run`, `d287_root_series` e il supervisore inner viene esercitato
con fixture soltanto ai boundary esterni. La matrice copre happy MATCH,
NO_MATCH con conferma separata, repo dirty, host drift, tutte le classi cursor,
greeter non pronto/exit inattesa, journal senza outcome, safety violation,
cleanup failure e propagazione coerente di inner/root/`tee`/summary. Ha inoltre
chiuso errori di lettura `git status`, risultati outcome/result multipli,
perdita di `PIPESTATUS` e EOF silenzioso nelle conferme.

Il residuo non simulabile è limitato a namespace mount e greeter reali, chiamata
PAM reale a fprintd, VERIFY/contatto sensore e relativa telemetry autentica.
L'enumerazione sysfs read-only ha contato un target `27c6:5125`, senza aprire
USB. Nessun greeter, PAM, mount, VERIFY o sensore è stato avviato dal
corrective.

## Guardrail ed executable closure offline

Il launcher rifiuta versioni/hash/configurazioni diverse, un greeter già
attivo, cardinalità target diversa da uno, ambiente non Wayland o drift D285.
Ogni tentativo crea un namespace mount privato, bind-mount read-only e un nuovo
process group del solo greeter `--testing`. Il supervisore termina quel gruppo
dopo `NO_MATCH` o timeout. Il journal per-cursor deve provare esattamente una
epoch VERIFY, una extract, almeno un confronto, un TLS, cleanup drenato e zero
retry/reopen/reset/clear-halt/persistenza nota. Solo `NO_MATCH` consente una
nuova conferma; `MATCH` richiede anche il marker stdout `Unlocked` e l'exit
code zero del greeter.

La prova reale resta un Human Gate perché usa Polkit/root, interfaccia grafica,
USB e sensore. Il preflight e i test offline non invocano il greeter, non
eseguono `pkexec`, `unshare`, mount o comandi fprintd e non enumerano USB.
La matrice D287 corretta passa `65/65`. La regressione cumulativa D282–D287,
nel sandbox conta 275 successi e le quattro failure host-only già note dovute
alle restrizioni socket PAM/systemd; rieseguita nell'ambiente host consentito
senza `sudo`, USB o sensore, passa `279/279`. `shellcheck` non è disponibile;
`bash -n` e il preflight host reale passano. Il corrective non ha invocato
greeter, Polkit, mount, USB o sensore.

```text
OUTCOME=READY_FOR_HUMAN_GATE
ADVANCEMENT=KSCREENLOCKER_TARGET_CONSUMER_PATH_DESIGNED_AND_OFFLINE_CLOSED
EXECUTABLE_CLOSURE=PASS_OFFLINE_HORIZONTAL
RESIDUAL_BLOCKER_OR_RISK=REAL_KSCREENLOCKER_TESTING_MODE_PAM_MATCH_NOT_YET_EXECUTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
```
