# D233 runtime-binding and orchestrator closure

D190 reference source and KAT provenance were recovered from bounded local
session history after A1/current-tree and A2/Git recovery failed. The minimum
reference was restored, hardened, and verified 5/5 against pre-existing
OEM-attributed validators using the exact canonical PE as data only.

The recovered reference is now the only canonical constructor for
`RuntimePskE4Binder`. It derives from the loaded PSK during E4, gates A2 by
constant-time match, zeroizes temporaries and passes the same secret object to
the one-shot TLS engine.

A production-shaped injected orchestrator now joins preflight, protected input
seams, PE/reference, binder, USB/TLS backend, shared OEM replay, durable report
and exactly-once restore. Candidate reports cannot use the D232 synthetic schema
and explicitly declare offline injected mode, sealed source and no authorization.

Regression result: 46 unittest methods passed. Supplemental static checks and
ad-hoc provenance verification are enumerated separately. No hardware, target
enumeration, system mutation, protected real input or live TLS was used.
Fresh bundle extraction ran 40 methods: 29 passed and 11 were explicit skips
because the canonical proprietary PE is intentionally excluded.

```text
D233_DECISION=D233_REAL_BACKEND_OFFLINE_VERIFIED_READY_FOR_D234_HUMAN_RISK_REVIEW
D233_LIVE_HARD_DISABLED=yes
D234_OPERATOR_RISK_ACCEPTANCE=not_granted
LIVE_AUTHORIZATION=no
```
