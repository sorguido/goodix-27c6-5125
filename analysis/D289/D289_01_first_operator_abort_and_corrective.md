<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D289/01 — prima invocazione operatore abortita e correttivo host-side

## Evidenza ricevuta

L'operatore ha avviato manualmente il common harness dalla baseline completa
`0568742e682b1bdb3b427da390a8aa4ed7f9b914`. La capture autentica ma
incompleta è:

```text
captures/live_probe/d289-real-locked-session_20260912T061518Z_0568742e682b/sanitized/
```

Contiene soltanto `context.env`, `cleanup.log` e `pre-audit.log` vuoto. Non
contiene summary o manifest perché il teardown è terminato sotto `set -u`.
Digest calcolati durante la review:

```text
context.env   075f5afea3948371e0c6fa684d9c45b888e0191e8438c1ef38f2bdc1ed67f2fe
cleanup.log   839a4de553dd184121953793b019399afccc097590322aff00e6e06398bac409
pre-audit.log e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

L'errore terminale riferito dall'operatore è
`capture.sh: riga 41: LP_JOURNAL_CURSOR: variabile non assegnata`. Il
control-flow della baseline prova che un pre-audit nonzero impedisce sia
l'acquisizione del cursor sia l'avvio del payload, ma il teardown chiamava
comunque `lp_collect_journal`. L'errore cursor è quindi secondario e ha
mascherato il failure primario del pre-audit.

```text
D289_01_FIRST_OPERATOR_RUN=ABORTED_BEFORE_LIVE
D289_01_FIRST_OPERATOR_BASELINE=0568742e682b1bdb3b427da390a8aa4ed7f9b914
D289_01_FIRST_OPERATOR_PRIMARY_FAILURE=PRE_AUDIT_BEFORE_OUTPUT
D289_01_FIRST_OPERATOR_SECONDARY_FAILURE=UNBOUND_LP_JOURNAL_CURSOR
D289_01_REAL_LOCK_STARTED=false
D289_01_PAM_OVERLAY_STARTED=false
D289_01_VERIFY_STARTED=false
D289_01_SENSOR_ACTION_COUNT=0
D289_01_PHYSICAL_CONTACTS_CONSUMED=0
D289_01_NEW_DEVICE_SIDE_EVIDENCE=false
```

## Correttivo

Il common harness inizializza cursor, validità e stato raccolta. Senza cursor
valido non costruisce né invoca `journalctl --after-cursor`; produce invece
`JOURNAL_COLLECTION=NOT_APPLICABLE_NO_CURSOR`. Summary e hash vengono quindi
chiusi anche dopo un pre-audit fallito, preservando return code, log, stato
`payload_started=false` e causa primaria. Il fallimento cursor dopo un
pre-audit valido è distinto come `FAIL_JOURNAL_CURSOR`.

Il gate D289 non dipende più esclusivamente da `/proc/<pid>/exe`. Richiede la
concordanza fra owner PID D-Bus, UID, `comm=kwin_wayland`, cmdline KWin e cgroup
utente; un exe leggibile deve essere esattamente `/usr/bin/kwin_wayland`,
mentre un exe non leggibile è accettato soltanto con gli altri segnali forti.
Audit utente, payload e helper root riusano lo stesso controllo. Il nuovo
`--read-only-preflight` verifica senza `pkexec` sessione Wayland/logind,
`GetActive=false`, owner e identità KWin, greeter assente, mount/runtime
assenti, mode PAM, versioni/hash e cardinalità sysfs Goodix.

## Verifica e stato

```text
COMMON_HARNESS_TESTS=13/13_PASS
D289_TESTS=23/23_PASS
HIGH_RISK_D286_TO_D289=189/189_PASS
D289_TARGET_READ_ONLY_PREFLIGHT=PASS
D289_TARGET_EXE_READABILITY=UNREADABLE_ACCEPTED_WITH_COMPOSITE
LOCK_OR_PRIVILEGED_ACTION_EXECUTED_BY_AI=false
USB_OR_SENSOR_ACTION_EXECUTED_BY_AI=false
OUTCOME=READY_FOR_HUMAN_GATE
EXECUTABLE_CLOSURE=PASS_OFFLINE_PLUS_TARGET_READ_ONLY_PREFLIGHT
NEXT_BOUNDARY=REAL_KDE_LOCKED_SESSION_UNLOCK_LIVE
```

Il comando operatore resta:

```bash
operator_kit/live_probe/run.sh d289-real-locked-session --operator-run
```
