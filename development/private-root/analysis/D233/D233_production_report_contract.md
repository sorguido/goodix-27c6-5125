# D233/D234 production-candidate report contract

D232 retains `d232-synthetic-run-report-v1`. The candidate orchestrator passes
an in-memory capture publisher to the unchanged core and translates its result;
the synthetic schema is never written to a candidate durable path.

The D233 candidate schema is `d233-production-candidate-run-report-v1`. In D233
its execution mode is immutably `injected_offline_test`, seal is `sealed`, and
live authorization is `no`. A future D234 may introduce `live_single_shot` and
`explicitly_unsealed_for_reviewed_D234` only by reviewed source modification,
never via CLI/environment/config.

Required fields cover schema/mode/seal/authorization, result/terminal phase and
abort, command/USB/handshake/cleanup/publication counts, initial fprintd state,
fprintd/signal restore, secret zeroization, redaction booleans, runtime binding,
target identity and same-PSK TLS identity.

## Causal publication and restore

The locally established D232/D233 governance requires durable evidence before
OS restoration. The implemented order is:

```text
STOP new traffic
-> backend cleanup and secret zeroization
-> atomic mode-0600 pre-restore checkpoint
-> exactly-once fprintd and signal restore
-> atomic mode-0600 final report with restore outcome
```

Thus `report_publish_count` is 2 on the normal candidate path: one checkpoint
and one final report, each to a distinct path and each exactly once. If checkpoint
publication fails, restore still runs and the final report records an internal
abort with count 1. If restore fails, the checkpoint already survives and the
final report records the failed restore. No report contains secret or raw 0x90.
