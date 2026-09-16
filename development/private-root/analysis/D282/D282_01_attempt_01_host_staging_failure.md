<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/01 — attempt 01, failure host-side normalizzata

## Classificazione

```text
D282_01_ATTEMPT_01=FAIL_HOST_STAGING_CLOSED
D282_01_ATTEMPT_01_SENSOR_PROTOCOL_RESULT=NOT_REACHED
D282_01_ATTEMPT_01_BIOMETRIC_RESULT=NOT_REACHED
D282_01_ATTEMPT_01_HOST_STAGING_RESULT=FAIL
D282_01_ATTEMPT_01_GRANT_CONSUMED=true
D282_01_ATTEMPT_01_RETRY_AUTHORIZED=false
FINGER_CONTACT_COUNT=0
BIOMETRIC_ACTION_COUNT=0
ENROLLMENT_STARTED=false
```

Nessuna proprietà biometrica o sensor-side viene elevata da questa run. La
fonte primaria disponibile alla sessione non privilegiata è la trascrizione
autentica fornita dall'operatore. Il result originale è
`/var/tmp/goodix-d282-01-results/20260910T124005Z-54b6eb3002d1`, ma
`summary.env` è `root:root 0600` e `private/` è `root:root 0700`: il divieto
esplicito di sudo/root impedisce di leggerli o attribuire loro hash non
verificati. Questo documento normalizza soltanto i valori trascritti e li
separa dalle verifiche indipendenti su codice e stato host corrente.

## Failure trascritta e diagnosi verificata nel codice

Il journal fornito riporta:

```text
launch-fprintd: /usr/libexec/fprintd: Permesso negato
fprintd.service: Main process exited, status=126
```

Il summary trascritto riporta `FPRINTD_START_RESULT=FAIL`,
`EXEC_MAIN_STATUS=126` e `ERROR=/usr/libexec/fprintd: Permission denied`.
Alla baseline `54b6eb3002d1afacbb5331e0dbd33761f8865bca` il launcher creava
`/run/goodix-d282-01/.../launch-fprintd`, ne copiava la label
`fprintd_exec_t`, faceva avviare quel wrapper a systemd e il wrapper eseguiva
un secondo `exec /usr/libexec/fprintd`. Le label host lette dopo il recovery
sono `fprintd_exec_t` per `/usr/libexec/fprintd`, `lib_t` per la libfprint di
sistema e `var_run_t` per `/run`, con SELinux `Enforcing`. Codice, label e
failure status confermano quindi la root cause primaria:

```text
ROOT_CAUSE_PRIMARY=SELINUX_WRAPPER_EXEC_DENIED
```

Il cleanup trascritto falliva con
`service_touched: variabile non assegnata`. Il codice della stessa baseline
definiva `cleanup_live()` dentro `run_authorized_live()`, installandolo però
come trap `EXIT`, e leggeva `service_touched`, `staging_started`, path e hash
definiti `local` nella funzione esterna. All'uscita sotto `set -e` quegli
identificatori non erano più nello scope dinamico Bash. La root cause
secondaria è pertanto confermata indipendentemente:

```text
ROOT_CAUSE_SECONDARY=EXIT_TRAP_SCOPE_FAILURE
```

## Unit/drop-in attempt 01 e recovery

La unit vendor verificata dopo il recovery conserva
`ExecStart=/usr/libexec/fprintd`. Il drop-in della attempt 01, ricostruibile
esattamente dal launcher alla baseline, sostituiva invece `ExecStart` con il
wrapper sotto `/run`:

```ini
[Service]
ExecStart=
ExecStart=/run/goodix-d282-01/<RUN>/launch-fprintd
```

Il recovery manuale trascritto aveva riportato servizio `active/running`,
`Result=success`, `ExecMainStatus=0` e zero residui runtime, drop-in e storage.
La verifica read-only successiva osserva la sola unit vendor, nessun drop-in
D282, `Result=success` ed `ExecMainStatus=0`; il servizio è nel frattempo
`inactive/dead`, stato coerente con l'uscita idle del daemon D-Bus e non con
una nuova failure. I residui storage restano attestati dall'operatore perché
`/var/lib/fprint` non è leggibile dalla sessione non privilegiata.

```text
D282_01_ATTEMPT_01_MANUAL_RECOVERY=PASS_USER_ATTESTED
D282_01_ATTEMPT_01_RUNTIME_RESIDUES=0_USER_ATTESTED
D282_01_ATTEMPT_01_DROPIN_RESIDUES=0_USER_ATTESTED
D282_01_ATTEMPT_01_STORAGE_RESIDUES=0_USER_ATTESTED
```

Il grant originale resta consumato. Nessun retry e nessuna nuova Human Gate
sono impliciti in questa closure documentale.
