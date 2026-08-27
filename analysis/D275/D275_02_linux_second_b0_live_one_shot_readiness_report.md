# D275/02 — Linux second-B0 live one-shot readiness

## Esito

```text
OUTCOME=BLOCKED
ADVANCEMENT=NEW_OPERATOR_PATH_QUALIFIED_OFFLINE_NO_NEW_HARDWARE_EVIDENCE
EXECUTABLE_CLOSURE=PASS_OFFLINE_BUT_RELEASE_GATE_BLOCKED
RESIDUAL_BLOCKER_OR_RISK=D268_AFFECTED_REGRESSION_SUITE_FAILS_ON_PREEXISTING_LIVE_MANIFEST_HASH_DRIFT;AI_PM_REVIEW_REQUIRED
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=BASE64_TRANSPORT_VERIFIED
```

## Ownership ricostruita

```text
LIVE_ENTRYPOINT=operator_kit/d275-second-b0-once.sh
LIVE_WRAPPER=tools/d275_live_second_b0_once.py
LIVE_TRANSPORT_OWNER=core.usb_runtime.LibusbRuntimeTransport
TLS_SESSION_OWNER=core.persistent_runtime.PersistentRuntimeCoordinator
PSK_BOUNDARY_OWNER=core.protected_runtime.RealSecretBoundary
FDT_LIFECYCLE_OWNER=core.fdt_lifecycle.FdtLifecycle
CURRENT_LIVE_TERMINAL_BOUNDARY=STOP_AFTER_FIRST_IMAGE (D268 storico)
D275_PRODUCTION_BOUNDARY_OWNER=core.persistent_runtime.PersistentRuntimeCoordinator
LIVE_CLEANUP_OWNER=PersistentRuntimeCoordinator.run finally + D268 host transaction finally
LIVE_PREFLIGHT_OWNER=tools.d275_live_second_b0_once + reused D268ProductionDependencies
LIVE_COMMAND_ALLOWLIST_OWNER=core.persistent_runtime._ProductionMultiFrameChannel
```

Il wrapper D268 invoca già il coordinator production, ma fissava esplicitamente
`STOP_AFTER_FIRST_IMAGE`. D275/02 aggiunge solo wiring e authority operatore:
non duplica FDT, parser B0, D273 runner, NAV, TLS o PSK ownership. Fake e real
transport entrano nello stesso `PersistentRuntimeCoordinator.run()`; non
esistono retry/fallback. Il `finally` del coordinator chiude TLS, secret e
transport anche fra i due B0; il finally host ripristina segnali/fprintd.

## Safety e qualifica

L'allowlist post-image è esattamente `0x34,0x20,0x50,0x32,0x22`; ogni altro
controllo fallisce chiuso. Nessuna famiglia flash/IAP/OTP/provisioning/ClearApp,
configurazione persistente, enrollment, reset o VID/boot è chiamabile. Il
secondo B0 completa il runner e porta immediatamente a cancel/terminal stop;
non esiste transizione di terzo ciclo. Report e fake output contengono solo
metadata e contatori, mai plaintext/raster/hash biometrico.

Il gate live richiede la stringa esatta
`27c6:5125_ONE_SHOT_STOP_AFTER_SECOND_IMAGE_NO_RETRY_FACTORY_PRESERVING_NO_ENROLLMENT_NO_THIRD_CYCLE`,
oltre al flag D275, boundary esplicito e SHA completo approvato. Il preflight
riusa selezione cardinalità-one, accesso transport, protected metadata, PSK
boundary senza stampa, cache/materiale, holder check, output sicuro, marker
single-use e byte identity Git. Nessuna baseline è auto-approvata.

## Riesame metodologico pre-live

1. Cambia realmente il metodo: D268 si fermava alla prima immagine; il candidate
   usa ora il lifecycle production-shaped D275/01 fino allo stop al secondo B0.
2. L'ipotesi futura è che il target Linux accetti l'intero edge APP12509 già
   osservato Windows e chiuso offline, nella stessa sessione TLS/USB.
3. Se fallisce allo stesso confine, non si ripete: si classifica la failure
   semantica e si torna ad analisi offline/evidenza sanitizzata.

Nessun hardware è stato aperto. Il comando live resta
`CANDIDATE_ONLY_PENDING_AI_PM_REVIEW`.
