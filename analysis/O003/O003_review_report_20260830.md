<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# O003 corrective service-closure report — 30 agosto 2026

Il corrective è stato eseguito sul branch esistente
`ai-executor/o003-human-gate-service-hardening`, da
`b50edcb1f9b12ea183a296a35aba1054e4391f86`, senza nuovo O-number. `main` e
`origin/main` restano a `2e0ccdcd36492f21386896294e96dac61e820b68`; il
`development` canonico non è stato creato. Governance v2.7 e freeze Goodix
restano invariati.

## Closure implementata

Il tick normale usa ora il coordinatore production con contesti separati
PM-plan, Executor e PM-review. Il livello deterministico crea manifest,
`task/<TASK_ID>` e worktree XDG, applica commit/push tipizzati e gestisce
`CORRECTIVE` sul medesimo branch, `ACCEPT` con FF/CAS di `development` e cleanup,
oltre a `REPLAN`, `HUMAN_GATE`, `PAUSE` e `DONE`. I turni Codex hanno un ledger
persistente; quiescenza e resume derivano dai ledger turn/effect e dalla
riconciliazione di gate/Git/worktree, non da flag operatore.

Il probe quota/modello usa telemetry soltanto come preflight e autorizza la
route esclusivamente dopo un turno bounded, read-only e senza tool sull'esatta
coppia modello/effort, con route effettiva riosservata. Il manifest Human Gate
è l'unica sorgente macchina di `action_id/action_digest`. La unit è inclusa nel
wheel e l'installer genera un drop-in dai path Git/XDG verificati; un latch
emergency termina il servizio con exit zero e zero dispatch.

## Evidenza eseguita

- compileall e `git diff --check`: PASS.
- `python -W error::ResourceWarning -m unittest discover -s tests -v`:
  147/147 PASS, inclusi O001/O002.
- test production coordinator su repository/remote bare disposable: plan →
  task/worktree → commit/push → review → `CORRECTIVE` sullo stesso branch →
  secondo commit/push/review → `ACCEPT` → FF → cleanup → `DONE`; `main`
  invariato: PASS.
- wheel non-editable installato in venv disposable e invocato da `/tmp`:
  import, `--help`, `configure`, `install-service`, unit packaged e drop-in:
  PASS.
- `systemd-analyze --user verify` sulla unit installata: PASS.
- vero user manager transiente con `ProtectHome=read-only`,
  `ProtectSystem=strict`, `NoNewPrivileges=yes`, repository read-only e soli
  Git common-dir/state writable: qualification Git completa PASS; evidenza
  conservata in `/tmp/o003-systemd-retained-QKOm4L`, con
  `main_unchanged=true`, stato `DONE`, cleanup e task branch assente.
- start/restart/stop della unit installata in ambiente disposable: PASS.
- drift su resume, turn/effect in-flight, gate-action mismatch, emergency latch
  e exact-route probe sono coperti da test deterministici fail-closed: PASS.

Il drill GitHub reale è deliberatamente non eseguito: richiede numeric ID/login
dell'Autorità Umana configurati esplicitamente e un suo commento esatto
`/approve <GATE_ID>` o `/deny <GATE_ID>`. Anche il probe su una route Codex reale
non è stato consumato: è qualificato il percorso esatto con adapter
deterministico, senza presentare telemetry generica come prova della route.
Nessun servizio è stato installato persistentemente nel profilo operatore.

## Findings richiesti

```text
FINDING_A_NORMAL_SERVICE_LOOP=PASS
FINDING_B_REAL_TASK_CREATION=PASS
FINDING_C_AUTHORITATIVE_QUIESCENCE=PASS
FINDING_D_SYSTEMD_GIT_WRITABILITY=PASS
FINDING_E_EMERGENCY_RESTART_STORM=PASS
FINDING_F_EXACT_ROUTE_REPROBE=PASS_DETERMINISTIC_PATH; REAL_ROUTE_NOT_EXECUTED
FINDING_G_SINGLE_SOURCE_GATE_ACTION=PASS
FINDING_H_INSTALLED_SERVICE_RESOURCE=PASS
FINDING_I_RESUME_RECONCILIATION=PASS
REAL_GITHUB_GATE_E2E=NOT_EXECUTED
```

## Boundary residuo

O004 non è stato creato né avviato. Restano obbligatori la prova negativa
OS-level e il ciclo low-risk sul repository/service Goodix reale prima di
qualunque dichiarazione di readiness. O003 non ha aperto USB, usato sudo/root o
materiale protetto, aggiornato `main`, riscritto history, pubblicato, usato API
a consumo o implementato un live runner.

```text
GOODIX_USB_OPEN_COUNT=0
SUDO_USE_COUNT=0
PROTECTED_MATERIAL_ACCESS_COUNT=0
MAIN_UPDATE_COUNT=0
HISTORY_REWRITE_COUNT=0
PUBLICATION_COUNT=0
PAYG_FALLBACK_COUNT=0
UNSANDBOXED_TASK_CODE_EXECUTION_COUNT=0
ORCHESTRATION_READY_FOR_GOODIX=false
CURRENT_LIVE_AUTHORIZED=false
GOODIX_FUNCTIONAL_ADVANCEMENT=NONE
LIVE_RUNNER_ENABLED=false
```

Il report JSON adiacente è la superficie macchina. `O003_FINAL_HEAD` resta
dinamico per evitare l'impossibile self-hash del commit che contiene il report;
gli identificativi CI vengono registrati dopo il primo push corrective.
