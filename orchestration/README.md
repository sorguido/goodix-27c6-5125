<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix host-only orchestrator (O001 + O002)

`orchestration/` now contains the deterministic O001 engine and the bounded
O002 adapters that prove a real PM → Executor → PM loop on a disposable
synthetic Git repository. It remains completely separate from Goodix USB,
protected material, `sudo`, `main`, live execution and publication.

The O001 engine remains authoritative for transitions, capability policy,
idempotency and fail-closed recovery. O002 adds:

- a JSONL Codex App Server client with initialize/initialized handshake,
  explicit request correlation, server-request denial, ChatGPT-only auth,
  model discovery, one bounded schema-repair turn and error classification;
- three independent contexts: PM planning (read-only), PM review (read-only)
  and Executor (synthetic-worktree write only), implemented with named Codex
  permission profiles and command network disabled;
- strict typed planning, work-report and review contracts, with
  App-Server-compatible Structured Outputs schemas and stronger local
  validation before any state or Git effect;
- a trusted data-only verifier that reads only fixed, bounded synthetic files;
  deterministic acceptance never imports or executes task-controlled project
  code outside the Codex sandbox;
- a deterministic Git Manager for synthetic repositories only: task branch
  and worktree creation, scoped diff validation, task-derived commits and an
  exact expected-old fast-forward of the integration ref after PM `ACCEPT`;
- SQLite schema v3 for contexts, dispatch routing evidence and Git state, with
  freshness accounting across every operational table. v1 and v2 stores are
  rejected as incompatible without modification.

## Closed model routing

| Context/class | Exact route |
| --- | --- |
| PM plan `STANDARD` | `gpt-5.6-sol` / `medium` |
| PM plan `ESCALATED` | `gpt-5.6-sol` / `high` |
| PM review | `gpt-5.6-sol` / `high` |
| Executor `MECHANICAL` | `gpt-5.6-luna` / `medium` |
| Executor `LOCAL_CORRECTIVE` | `gpt-5.6-terra` / `medium` |
| Executor `BOUNDED_IMPLEMENTATION` | `gpt-5.6-terra` / `high` |
| Executor `ARCHITECTURAL_OR_HIGH_RISK` | `gpt-5.6-sol` / `high` |

Unknown routes, raw model/effort overrides, unavailable exact pairs, hidden
downgrades and autonomous `xhigh`/`max` use fail closed. API-key auth and paid
API fallback are denied.

## Deterministic tests

From `<git-root>/orchestration`:

```bash
python -m compileall -q goodix_orchestrator tests
python -W error::ResourceWarning -m unittest discover -s tests -v
```

The suite uses only the Python standard library. It includes the 63 O001
regressions plus fake App Server, routing, persistence, synthetic Git-manager
and full fake corrective/accept/next-task/DONE coverage. It also proves that
malicious-looking synthetic bytes remain inert, every route is reverified after
every dispatch, and schema repair does not echo invalid content. CI runs only
these 105 deterministic host-only checks; it never runs the real model
qualification.

## Real local synthetic qualification

Use an existing ChatGPT-authenticated Codex installation. Choose new paths
outside the Goodix Git root for every run:

```bash
cd <git-root>/orchestration
python -m goodix_orchestrator.qualification \
  --real-codex \
  --state-dir /tmp/o002-qualification-state \
  --report /tmp/o002-qualification-report.json
```

The command creates its own synthetic repository and requires no install,
`sudo`, USB, protected material or GitHub credentials. It exits nonzero on
failure, never silently falls back to pay-as-you-go, and emits a redacted JSON
report. Default paths use `XDG_STATE_HOME` or
`~/.local/state/goodix-orchestrator/` and do not dirty this repository.

A successful run prints `O002_REAL_CODEX_SYNTHETIC_CYCLE=PASS`. Its report
must also show `AUTH_MODE=CHATGPT`, pinned/effective routing PASS, observed
independent CORRECTIVE/ACCEPT/second-task DONE from disposition-neutral review
prompts, persisted verified dispatch routing, real task
branch/worktree/commits and integration fast-forward PASS, and
`MAIN_UNCHANGED=true`. Zero qualification-path counters for human relay, paid
fallback, Goodix USB, `sudo` and protected material are observations of this
path, not proof of OS-level negative isolation; that proof remains future work.

O002 does not make the orchestration ready for Goodix. GitHub Human-Gate
identity binding, persistent-service isolation and any live runner remain
future O003/O004 work requiring their own scope and gates.

Project-authored content in this domain is `GPL-2.0-or-later`; no external,
Rockytkg, OEM, capture, biometric or protected implementation material is
incorporated.
