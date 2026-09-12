<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D289/01 — review PM indipendente del correttivo

## Review set

Baseline riesaminata:
`0568742e682b1bdb3b427da390a8aa4ed7f9b914`. La review ha confrontato il
diff Git, la capture abortita, common harness, audit/payload/helper D289,
contratti, documentazione operatore e manuale canonico. Nessun file di
governance è stato modificato.

## Verifica dei failure-path

Il caso pre-audit fallito conserva ora output e return code dell'hook,
`LIVE_PROBE_PRIMARY_FAILURE=PRE_AUDIT`, `payload_started=false`, cleanup,
post-audit, summary e hash. La raccolta journal non viene invocata senza cursor
e registra `NOT_APPLICABLE_NO_CURSOR`; `set -u` non produce più un exit non
classificato. Il caso pre-audit PASS seguito da cursor failure è distinto come
`FAIL_JOURNAL_CURSOR`. Il percorso cursor valido raccoglie una volta e resta
PASS.

L'identità KWin combina owner PID D-Bus, UID, `comm`, cmdline e cgroup utente.
Exe leggibile e incoerente, UID/processo/cgroup errati e owner ambiguo sono
rifiutati; exe non leggibile è accettato solo col composito coerente. Il seam
synthetic-proc è forzato a `/proc` in audit, payload e helper root. La review
ha trovato e chiuso due difetti prima dell'accettazione: i marker di successo
dell'identità non possono precedere il protocollo readiness sulla pipe root e
un override ambientale del proc-root non può entrare nel percorso operatore.

## Evidenze di closure

```text
BASH_SYNTAX=PASS
COMMON_HARNESS_REGRESSION=13/13_PASS
D289_CONTRACT_AND_IDENTITY=23/23_PASS
HIGH_RISK_D286_TO_D289=189/189_PASS
OFFLINE_REFERENCE_HARNESS=PASS
D288_OFFLINE_HARNESS_COMPATIBILITY=PASS
D289_OFFLINE_HARNESS_COMPATIBILITY=PASS
D289_TARGET_READ_ONLY_PREFLIGHT=PASS
D289_TARGET_PROC_ROOT_OVERRIDE_REJECTED_BY_FORCED_REAL_PROC=PASS
GIT_DIFF_CHECK=PASS
SHELLCHECK=NOT_INSTALLED
```

La prima D288 compatibility run nel sandbox ha restituito PAM code 4 perché
il sandbox impediva allo smoke `pam_start_confdir` di operare normalmente; la
stessa run offline, ripetuta senza quelle restrizioni e senza privilegi/live,
è PASS (`start/auth/end=0/0/0`). Non è stata modificata D288.

Il preflight target ha letto soltanto metadata/versioni/hash, D-Bus/logind,
`/proc` e sysfs. Nessun lock, `pkexec`, mount, PAM fingerprint, fprintd, USB o
comando sensore è stato eseguito dall'AI.

## Decisione

```text
AI_PM_REVIEW=PASS
DECISION=HUMAN_REQUIRED
OUTCOME=READY_FOR_HUMAN_GATE
EXECUTABLE_CLOSURE=PASS_OFFLINE_PLUS_TARGET_READ_ONLY_PREFLIGHT
REAL_LOCK_STARTED_IN_FIRST_OPERATOR_RUN=false
VERIFY_STARTED_IN_FIRST_OPERATOR_RUN=false
PHYSICAL_CONTACTS_CONSUMED_IN_FIRST_OPERATOR_RUN=0
NEXT_BOUNDARY=REAL_KDE_LOCKED_SESSION_UNLOCK_LIVE
```

Il comando resta direttamente eseguibile dall'operatore, senza rerun
automatico:

```bash
operator_kit/live_probe/run.sh d289-real-locked-session --operator-run
```
