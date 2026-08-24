# D265/01 — offline one-shot first-image operator kit

## Esito

`OUTCOME = PASS_OFFLINE_OPERATOR_KIT` e `EXECUTABLE_CLOSURE = PASS_OFFLINE`. Il launcher cwd-independent espone soltanto `--dry-run` e l'esatto flag futuro `--i-authorize-one-d265-first-image-live-attempt`; ogni altra combinazione è hard-disabled. Nessun accesso USB, secret, marker reale, fprintd o TLS live è avvenuto.

## Control flow reviewabile

Il tool esegue prima il gate `D265_APPROVED_LIVE_BASELINE_SHA`: full SHA lowercase, risoluzione commit esatta, HEAD esatto, worktree pulito, path-set interno di 20 file e byte identity contro il commit. Solo dopo crea l'intento interno già reviewato, costruisce `FutureProductionDependencies` e chiama `run_future_first_image_candidate`, che trasferisce ownership al `PersistentRuntimeCoordinator` con `TerminalBoundary.STOP_AFTER_FIRST_IMAGE`. Il marker D265 dedicato è durable/O_EXCL/O_NOFOLLOW/0600 e non riusa D261.

## Limiti probatori

Tutte le prove sono offline, synthetic o fixture. `0x22_FIXED64_LIVE_PROVEN=false`, `FIRST_IMAGE_LIVE_PROVEN=false`, stato interno post-image `UNKNOWN`. La precedente autorizzazione non è stata consumata e non è trasferita. Review AI-PM, merge, approvazione esplicita del nuovo full SHA e nuova autorizzazione sono ancora obbligatori.
