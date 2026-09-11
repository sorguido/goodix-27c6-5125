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
`28544d4910d5ea9be6708eb343804fa0018cb8e4`. Non è stato copiato o adattato nel
progetto. Hash dei file sorgente consultati:

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

**VERIFIED target-side:** Fedora installa `kscreenlocker-6.7.4-1.fc44` e
`plasma-workspace-6.7.4-2.fc44`. Il binario installato contiene la stringa
esatta `kde-fingerprint`. I pin correnti sono:

```text
b9d7ad5798b549c9f9e8c991911f74cb75b4a3b298cbc88b12249151d0726e7c  /usr/libexec/kscreenlocker_greet
7d91b3ad73a998e8b10f9edccd74ba04179a778c4a5e61d9176872f43c7bbac3  /etc/pam.d/kde
8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437  /etc/pam.d/kde-fingerprint
328501780ab06cc0497a25ff48c6f027a1abed8506f0969f39a5f8bc6696181c  LockScreenUi.qml
```

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
2. **Quale nuova ipotesi viene testata?** Che KScreenLocker 6.7.4 selezioni
   davvero `kde-fingerprint`, propaghi un MATCH dal modulo PAM non-interattivo
   all’uscita positiva del greeter `--testing` e lasci invariati host e D285.
3. **Se fallisce nello stesso punto?** Nessun quarto contatto e nessun passaggio
   al lock reale. Si revisionano cursor journal, exit del greeter, namespace e
   segnale PAM/KScreenLocker; si cambia il metodo prima di ogni nuova live.

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
La matrice D287 passa `32/32`. La prima regressione cumulativa D282–D287 nel
sandbox ha contato 242 successi e quattro failure host-only dovuti alle
restrizioni socket PAM/systemd del confinamento; la stessa suite, rieseguita
fuori dal sandbox senza `sudo`, USB o sensore, passa `246/246`. `shellcheck`
non è disponibile; `bash -n` e il preflight host reale passano.

```text
OUTCOME=READY_FOR_HUMAN_GATE
ADVANCEMENT=KSCREENLOCKER_TARGET_CONSUMER_PATH_DESIGNED_AND_OFFLINE_CLOSED
EXECUTABLE_CLOSURE=PASS_OFFLINE_REAL_HOST_HASHES_PLUS_SYNTHETIC_TELEMETRY
RESIDUAL_BLOCKER_OR_RISK=REAL_KSCREENLOCKER_TESTING_MODE_PAM_MATCH_NOT_YET_EXECUTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
```
