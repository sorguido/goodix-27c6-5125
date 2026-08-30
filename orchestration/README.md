# Goodix orchestrator deterministic core (O001)

O001 implements only the deterministic, host-only orchestration core described
by `SPEC.md`: explicit state transitions, structured protocols, deny-by-default
capability policy, SQLite persistence, an external-effect ledger model, and
fake-agent flows.

It contains no Codex App Server, Git/GitHub, shell, network, USB, privileged,
protected-material, or live-runner adapter. Effect records are data only and
cannot execute an external action.

## Test invocation

From `<git-root>/orchestration` run:

```bash
python -m unittest discover -s tests -v
```

The command uses only the Python standard library and does not install the
package or any dependency.
