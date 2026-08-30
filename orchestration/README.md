<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix orchestrator deterministic core (O001)

O001 implements only the deterministic, host-only orchestration core described
by `SPEC.md`: explicit state transitions, structured protocols, deny-by-default
capability policy, SQLite persistence, an external-effect ledger model, and
fake-agent flows.

It contains no Codex App Server, Git/GitHub, shell, network, USB, privileged,
protected-material, or live-runner adapter. Effect records are data only and
cannot execute an external action.

The persisted state schema is versioned at v2. Legacy v1 stores are rejected
as incompatible without modification: v1 cannot retain the expected-next task
or immutable replan envelope, so arbitrary operational state cannot be
reconstructed exactly. Engine creation is fresh-store-only; every existing
store must enter through recovery. Task manifests structurally deny `main`,
and persisted next-task/envelope metadata prevents identity or scope drift.

Project-authored content in `orchestration/` is licensed
`GPL-2.0-or-later`. O001 incorporates no external implementation code.

## Test invocation

From `<git-root>/orchestration` run:

```bash
python -W error::ResourceWarning -m unittest discover -s tests -v
```

The command uses only the Python standard library and does not install the
package or any dependency.
