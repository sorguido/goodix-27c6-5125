<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# O003 review report — 30 agosto 2026

O003 è stato implementato host-only sul branch
`ai-executor/o003-human-gate-service-hardening`, baseline esatta
`2e0ccdcd36492f21386896294e96dac61e820b68`. Il fetch iniziale ha confermato
`origin/main` allo stesso SHA, `development` assente e nessun task branch remoto.
Il ref canonico `development` non è stato creato: attende ACCEPT O003 e merge
Human-gated in `main`.

La governance passa strettamente da v2.6 a v2.7. Il codice aggiunge schema
SQLite v4, binding GitHub issue/identità numerica+login/gate/commit/azione,
parser exact-command, recovery delle due crash boundary gate, servizio
local-first/CLI XDG, single-instance, maintenance epoch, emergency latch,
re-probe della route Codex esatta, backup consistente e lifecycle
`development`/`task/<TASK_ID>` con FF/CAS, reachability e cleanup post-verifica.

## Evidenza eseguita

- `python -m compileall -q goodix_orchestrator tests`: PASS.
- `python -W error::ResourceWarning -m unittest discover -s tests -v`: 137/137 PASS.
- CLI `--help`, `configure`, `status`, `pause`, `resume`, maintenance-enter,
  backup e service-run con XDG temporaneo: PASS.
- `systemd-analyze verify systemd/goodix-orchestrator.service`: PASS; il sandbox
  ha emesso warning sui socket user lookup, non errori di unità.
- unità transiente reale `systemd --user` con `NoNewPrivileges`,
  `PrivateDevices`, `RestrictSUIDSGID`, `KillMode=control-group`: start active,
  restart active, stop inactive: PASS.
- Git lifecycle con repository e remote bare disposable: init SHA esatto,
  expected-old/FF, mismatch refusal, crash after FF, cleanup e crash cleanup:
  PASS; `main` invariato.

Il drill GitHub reale non è stato eseguito perché l'Autorità Human numeric
ID/login non può essere inferita dall'account `gh` corrente: serve configurazione
locale esplicita e commento `/approve <GATE_ID>` dell'Autorità. La coverage fake
completa è PASS e non viene presentata come E2E reale. La unit persistente non è
stata installata nel profilo utente; l'install/rollback sono documentati e la
qualifica transiente reale è PASS.

## Boundary residuo

O004 resta obbligatorio per la prova negativa OS-level e il ciclo low-risk sul
repository/service Goodix reale. O003 non ha aperto USB, usato sudo/root o
materiale protetto, aggiornato `main`, riscritto history, pubblicato, usato API
a consumo, implementato live runner o avanzato funzionalmente Goodix.

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

Il report JSON adiacente è la superficie macchina; `O003_FINAL_HEAD` indica
dinamicamente l'head Git sottoposto a review, evitando un impossibile self-hash
del commit che contiene il report.
