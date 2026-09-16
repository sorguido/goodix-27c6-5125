# Esperimento di riferimento offline

Fixture `TEST-ONLY` del Live Probe Harness. Non apre USB, non avvia fprintd,
non richiede privilegi e non è abilitata per `--operator-run`.

Serve a provare il passaggio dei budget al payload, una sola invocazione,
pre/post audit, capture, cleanup e handoff ai classificatori common e locale.
