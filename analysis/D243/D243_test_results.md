# D243 test results

All commands ran from `/home/guido/Repository/goodix-27c6-5125` without sudo,
real USB, protected-secret reads or live TLS.

## Mandatory executable closure gate

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
....................................................................................................................
----------------------------------------------------------------------
Ran 116 tests

OK
```

```text
./operator_kit/d243-live-tls-once.sh --offline-dry-run
D243_PHASE=EXECUTABLE_CLOSURE
D243_RESULT=PASS
D243_FAILURE_CLASS=none
```

## Direct D243 coverage

- exact core E4 logical frame unchanged and submitted short;
- explicit `len(submitted_E4_chunk) != 64` assertion;
- all twelve pre-D1 A0 requests use D241 chunk/completion semantics;
- B0 ServerHello uses `64|64`, ServerHelloDone uses `64`;
- B0 tail is zero-initialized and short completion is terminal;
- pacing is exactly two 10 ms events and zero for A0;
- first-E4 timeout has durable pre-restore checkpoint and final post-restore
  report, cleanup/release/close/exit exactly once and secret zeroized;
- same SecretBuffer E4→TLS, retry/D4/application-data/persistent-write zero;
- failure observability never collapses a known preflight cause into generic
  `PREFLIGHT_FAILED`;
- unseal/reseal patch applies and reverses byte-exactly without offset.

`D243_REAL_USB_ACCESS_DURING_CODEX=0`

`D243_REAL_TLS_HANDSHAKE_DURING_CODEX=0`

