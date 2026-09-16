# D279/40 — review dell'aggregate autentico D279/39

## Decisione PM

La singola run D279/39 è accettata come evidenza aggregate-only autentica. Il
file ricevuto è preservato byte-per-byte in
`captures/D279_39/D27939_20260906T084055Z/sanitized/summary.json`:

```text
SOURCE_SUMMARY_SHA256=861bc73e743a444b4894598c34c11b20c31b5152a0f5410e6deb7febba8b677c
BASELINE_SHA=4001bf07413ec09afb29db39d78fb65aa7c6f904
CAPTURE_SHA256=3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab
OPERATION=D279_39_ONE_OFFLINE_PROTECTED_NBIS_QUALITY_EVALUATION
LIVE_OR_USB_ACTION_COUNT=0
```

Il validator digest-pinned verifica schema e chiavi esatti, matrice 3×3,
ordine `baseline,(primary,auxiliary)*21`, cardinalità, invarianti statistiche e
privacy. Quattro test coprono digest, role order, matrice e statistiche.

## Evidenza e interpretazione corretta

`frame_minmax x2` separa la baseline dai fingerprint nella quality-map della
cattura: A/B è zero sulla baseline, presente su 21/21 primary e 20/21
auxiliary, con mediana 366‰ in entrambi. Resta il candidato sperimentale più
pulito tra le nove varianti, non una scelta production.

Nel NBIS pinned, con `ppmm=0`, `radius_pix=0` rende zero la componente
grayscale. Reliability ≥0,25 significa quindi esattamente che la minutia cade
in un blocco quality B/A; ≥0,50 significa A. Non è una seconda misura fisica.
La quality-map misura contrasto e ridge flow direzionale su blocchi 8×8 con
finestra 24×24; non misura densità di endings/bifurcations né matchabilità.

Per `frame_minmax x2` i massimi finali sono 3 minutiae primary e 4 auxiliary,
sempre sotto le 10 richieste da Bozorth per calcolare un match. Libfprint
accetta però un'immagine con qualunque numero positivo di minutiae nel print:
“sotto 10” è quindi un blocker di match computabile per quella singola
immagine, non la stessa condizione del live failure a zero minutiae.

`frame_minmax x3` produce più punti grezzi ma quasi nessuna A/B e resta
declassato. `robust x2` produce 11 punti e 144‰ A/B anche sulla baseline, quindi
è meno pulito come discriminatore.

L'autorizzazione D279/39 è consumata; il JSON non autorizza retry, seconda
lettura, production, USB o live.

```text
OUTCOME=AUTHENTIC_D279_39_ACCEPTED_WITH_CORRECTED_INTERPRETATION
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_AGGREGATE_AUDIT_ONLY
D279_40_TESTS=4/4_PASS
D279_39_AUTHORIZATION_CONSUMED=true
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
```
