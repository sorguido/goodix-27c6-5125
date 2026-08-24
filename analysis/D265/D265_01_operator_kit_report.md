# D265/01 — corrective offline del kit operatore one-shot

## Esito

`PASS_OFFLINE_OPERATOR_KIT`; `AI_PM_CORRECTIVE=CLOSED_OFFLINE`. Nessun USB, secret, marker reale, comando sensore, mutazione fprintd o TLS live.

## Correzioni

L'interazione umana è italiana. Il comando canonico è `sudo env D265_APPROVED_LIVE_BASELINE_SHA=<FULL_APPROVED_SHA> ./operator_kit/d265-first-image-once.sh --i-authorize-one-d265-first-image-live-attempt`: sudo gestisce direttamente la password e preserva `SUDO_UID`; il kit non gestisce password. Il prompt dito viene emesso una sola volta immediatamente prima del vero wait IRQ2 15000 ms, dopo l'arm finale.

Tracker host-side e audit reale sostituiscono i default inventati. USB open viene dal backend; sessioni, TLS, retry, persistenza, recovery, cleanup e zeroization dall'audit; IRQ2/ACK/B0 da contatori monotoni nei punti runtime esistenti. L'audit è disponibile anche su failure. Valori non osservati sono `UNKNOWN` o `NOT_REACHED`.

## Stato

Il set live-critical resta 20 file e nessuna baseline è approvata. `READY_FOR_LIVE=false`, `LIVE_AUTHORIZED=false`, `0x22_FIXED64_LIVE_PROVEN=false`, `FIRST_IMAGE_LIVE_PROVEN=false`; stato interno post-image `UNKNOWN`. La precedente autorizzazione non è consumata né trasferita.
