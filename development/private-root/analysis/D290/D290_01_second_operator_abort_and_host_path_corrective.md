<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D290/01 — seconda invocazione abortita e closure del percorso host

> **STORICO.** Il correttivo descritto qui appartiene al metodo
> TTY3/FIFO/overlay, ora abbandonato e disarmato. L'evidenza della run resta
> valida; non usare questo documento come procedura operatore corrente.

## Evidenza della seconda invocazione

La seconda invocazione operatore è partita dalla baseline completa
`603a47cdf1c1b6672c6d26c589648aab973aeeaf`. La capture sanitizzata e il
manifest integro sono in:

```text
captures/live_probe/d290-plasmalogin_20260912T144942Z_603a47cdf1c1/sanitized/
```

Il pre-audit è PASS e osserva una sola sessione iniziale `2`, tty2,
`plasmalogin`, Wayland, class user, state online; la TTY operatore è `4`.
Dopo `PREPARA LOGIN D290`, il payload è entrato nel vecchio `coproc pkexec`.
L'autenticazione interattiva è rimasta bloccata e l'input digitato sulla TTY è
stato mostrato in chiaro. Nessun valore è copiato qui né presente nella
capture: `payload.log` è byte-empty.

Il teardown successivo registra `INTERRUPTED`, payload rc 130, cleanup PASS e
post-audit fallito soltanto perché la sessione TTY operatore non era più nello
stato atteso. Il journal diagnostico contiene due errori generici
`plasmalogin ... Process crashed`, ma nessun marker `GOODIX_`; non esistono
telemetria, payload details, login-state o root-overlay log.

Controlli read-only eseguiti prima del riavvio hanno verificato PAM host non
montato, hash originale, runtime assente e zero eventi Goodix/fprintd dopo il
cursor. Dopo il riavvio sono nuovamente verificati: nessun processo residuo,
nessun mount/runtime, hash PAM e binari attesi, daemon attivo e sessione
grafica originaria coerente. `OVERLAY_STARTED=false` è quindi verificato, non
dedotto dalla sola assenza dei marker.

```text
D290_01_SECOND_OPERATOR_RUN=ABORTED_PRE_LOGIN
D290_01_SECOND_OPERATOR_BASELINE=603a47cdf1c1b6672c6d26c589648aab973aeeaf
D290_01_SECOND_OPERATOR_FAILURE_CLASS=PRIVILEGED_HELPER_INTERACTIVE_TTY_DEADLOCK
D290_01_SECOND_OPERATOR_LOGOUT_PERFORMED=false
D290_01_SECOND_OPERATOR_OVERLAY_STARTED=false
D290_01_SECOND_OPERATOR_VERIFY_STARTED=false
D290_01_SECOND_OPERATOR_SENSOR_ACTION_COUNT=0
D290_01_SECOND_OPERATOR_PHYSICAL_CONTACTS_CONSUMED=0
D290_01_SECOND_OPERATOR_NEW_DEVICE_SIDE_EVIDENCE=false
D290_01_INTERACTIVE_AUTH_ECHO_SAFETY_FAILURE=OBSERVED
D290_01_PASSWORD_VALUE_RECORDED=false
```

## Root cause e design corretto

Il vecchio design usava lo stdin del `coproc` come protocollo `RELEASE`, mentre
`pkexec` doveva autenticare interattivamente. Inoltre GNU `timeout`, senza
`--foreground`, collocava il payload in un process group diverso dal foreground
della TTY. Il polkit agent non poteva quindi leggere correttamente la TTY e il
medesimo lifecycle mescolava autenticazione e controllo.

Il common harness aggiunge un'opzione config strettamente booleana:
`PAYLOAD_REQUIRES_FOREGROUND_TTY=true`. Solo in `--operator-run` questa produce
`timeout --foreground`; gli altri esperimenti conservano la semantica
precedente. Il payload verifica anche `pgid == tpgid` prima di `pkexec`.

L'autenticazione usa esplicitamente `/dev/tty`. Il controllo usa invece la FIFO
privata `d290-root-control.fifo`, mode 0600, in workdir 0700: il root helper
verifica tipo, assenza di symlink, path canonico e ownership. Il figlio chiude
la copia ereditata del writer ed esegue direttamente `pkexec`, senza una shell
intermedia che nasconda il PID da cancellare; soltanto il payload può inviare
`RELEASE`. Lo status viene drenato con timeout e cardinalità limitata.
L'helper riceve inoltre PID e start-time del payload e usa un watchdog bounded:
EOF, morte/reuse del parent, segnale, comando inatteso o release conducono al
medesimo cleanup. Nessuna password/PIN attraversa FIFO, stdout/stderr, log,
capture, telemetria o fixture e il percorso non dipende dalla cache Polkit.

Il root lifecycle resta long-lived perché l'EOF/watchdog garantisce cleanup
automatico durante il periodo fra mount e ritorno dell'operatore. Due helper
brevi PREPARE/RELEASE avrebbero richiesto un secondo prompt e lasciato
l'overlay senza owner in caso di crash fra le fasi.

## Audit orizzontale

La separazione in `privileged-channel.sh` e `root-overlay-lib.sh` rende
esercitabili le stesse primitive production. I test coprono:

- pseudo-TTY reale, stdin TTY, no echo di un token runtime non versionato,
  regressione del vecchio stdin-coproc, FIFO distinta, READY/RELEASE ed exit;
- signal prima dell'overlay, durante l'attesa autenticazione, durante setup,
  con overlay ready e dopo outcome; EOF e morte del parent con PID/start-time
  watchdog;
- prepare/release, cleanup idempotente, failure prima/dopo runtime, bind e
  remount failure, mount preesistente, host inatteso, FIFO mode/parent/symlink,
  recovery candidato corretto e rifiuto candidato errato;
- modello sessioni iniziale/nuovo, pre-audit failure senza rumore e capture
  autentica della seconda invocazione;
- payload production completo con host simulato, per MATCH e NO_MATCH:
  logout boundary, greeter, un'unica epoch, nuova sessione/assenza sessione,
  release, `CHIUDI D290`, telemetria e classifier.

L'audit ha trovato e corretto anche due gate Bash della stessa classe:
`! mountpoint` e `! loginctl` usati come asserzioni isolate non sono protetti da
`set -e`. Sono ora `if ...; then exit/return 1`, così mount preesistente e
sessione iniziale ancora viva fermano realmente il percorso.

Restano non simulati soltanto logout grafico reale, interazione col greeter
Plasma reale, PAM/fprintd/USB VERIFY reale e creazione della nuova sessione
Wayland reale.
