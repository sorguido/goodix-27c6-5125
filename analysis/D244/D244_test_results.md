# D244 — risultati dei test offline

Data: 2026-08-17 (Europe/Rome)

## Executable Closure Gate

```text
$ PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
Ran 124 tests in 1.847s
OK

$ ./operator_kit/d244-live-tls-once.sh --offline-dry-run
D244_PHASE=EXECUTABLE_CLOSURE
D244_RESULT=PASS
D244_FAILURE_CLASS=none
```

## Copertura D244

- T1 E4 D241/D242/D243/D244: lunghezza 16, SHA-256 canonico, match.
- T2 A0: E4 OUT corto, zero tail artificiale, completion full-length.
- T3 B0: ServerHello `64|64`, ServerHelloDone `64`, tail zero.
- T4 pacing: due pause sintetiche da 10 ms, solo sui record TLS server-side.
- T5: non richiesto perché la direzione è già determinabile; fixture separate
  provano comunque OUT-timeout `command_count=0`/nessun IN e IN-timeout dopo
  OUT `command_count=1`/IN tentato.
- T6 durability: cleanup/zeroizzazione, checkpoint, restore e report finale.
- T7 boot-id presente/assente, uptime-only e metadati insufficienti.
- T8 zero retry/D4/application-data/persistent-write.
- T9 entrambi i comandi obbligatori eseguiti con esito PASS.

```text
D244_EXECUTABLE_CLOSURE_GATE=PASS
D244_REAL_USB_ACCESS_DURING_CODEX=0
D244_REAL_TLS_HANDSHAKE_DURING_CODEX=0
```
