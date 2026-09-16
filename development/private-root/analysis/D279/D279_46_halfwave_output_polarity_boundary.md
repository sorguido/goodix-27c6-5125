# D279/46 — completamento della matrice half-wave supporto×polarità

## Audit offline

D279/44 non isola il solo supporto di segno: entrambe le half-wave sono state
consegnate a NBIS come deviazione chiara su fondo nero. Nel libfprint pinned,
`fp-image.c` applica `FPI_IMAGE_COLORS_INVERTED` prima di `get_minutiae()`,
quindi la polarità è parte effettiva del preprocessing NBIS. Egis0570 usa
`max(frame-background,0)` e poi richiede l'inversione colori; Elan usa lo stesso
supporto senza inversione, mentre VFS7552 usa `max(background-frame,0)` senza
inversione. Sono convenzioni sensor-specifiche, non prove APP12509, ma mostrano
che supporto e polarità non possono essere confusi.

Rockytkg preserva invece un delta signed con offset/clamp e successive
trasformazioni; è corroborazione GPL matcher-specifica e non è stato copiato
codice. Non fornisce una ragione target-specific per scegliere pesi, dead-zone,
flat-field, percentile clipping o sharpening prima di chiudere la matrice più
piccola.

## Esperimento minimo

L'evaluator mantiene il controllo signed D279/42 e aggiunge esclusivamente i
complementi non misurati delle due half-wave D279/44:

- deviazioni `frame > baseline`, scure su fondo bianco;
- deviazioni `baseline > frame`, scure su fondo bianco.

I test provano che sono complementi byte-esatti delle varianti precedenti, che
non le duplicano su delta non costanti e che i 43 raster sintetici seguono i
ruoli `baseline,(primary,auxiliary)*21`. Min/max, identity, resize x2 e NBIS
pinned restano invariati. Il baseline auto-sottratto bianco è ancora una
conseguenza matematica e non un discriminatore.

La preflight passa 43 test Python, build normale e ASan/UBSan del helper,
build da snapshot, source/symbol seam checks e un passaggio end-to-end su 43
raster sintetici non protetti. Il runner confronta l'intero blocco `groups`
del controllo signed con il summary D279/44 digest-pinned: un drift impedisce
l'output. Il kit consuma il grant prima della lettura protetta e valida
fail-closed il solo JSON aggregate. Nessun helper espone entry point USB;
production, sender e allowlist restano invariati. I timeout della pipe sono
esclusivamente safety bound del processo host offline.

La singola domanda è se il vantaggio attribuito provvisoriamente al supporto
negativo sopravviva quando la polarità d'uscita viene separata. Il controllo
signed deve inoltre riprodurre esattamente D279/44; ogni drift rende la nuova
run non confrontabile. Nessun risultato autorizza ancora pesi asimmetrici o
integrazione production.

```text
OUTCOME=READY_FOR_HUMAN_GATE_ONE_OFFLINE_PROTECTED_HALFWAVE_POLARITY_COMPLETION_EVALUATION
ADVANCEMENT=NEW_BIOMETRIC_DISCRIMINATOR_AND_OPERATOR_BOUNDARY_REACHED
EXECUTABLE_CLOSURE=PASS_OFFLINE_ONLY
D279_46_PREFLIGHT_TESTS=43/43_PASS
D279_46_NORMAL_AND_ASAN_UBSAN=PASS
D279_46_SYNTHETIC_END_TO_END=PASS
D279_46_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
PROTECTED_OR_BIOMETRIC_INPUT=false
LIVE_OR_USB_ACTION_COUNT=0
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
PRODUCTION_PATH_CHANGED=false
```
