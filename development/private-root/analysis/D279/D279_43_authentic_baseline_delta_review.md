# D279/43 — review autentica D279/42 e scelta del prossimo discriminante

## Assorbimento e risultato

La singola run D279/42 è accettata come evidenza aggregate-only autentica. Il
summary è preservato byte-per-byte con SHA-256
`0fc29eb7ece380e548b3cdc2caa995564a15c4e062bce4e83677c6367ee6ffb3`.
Il validator digest-pinned verifica schema, chiavi, matrice, ruolo canonico
`baseline,(primary,auxiliary)*21`, cardinalità, invarianti statistiche e privacy.

Sui 42 fingerprint, i frame con almeno una minutia nel tier NBIS B/A passano da
5 nel controllo a 10 dopo sottrazione; quelli con almeno una minutia nel tier A
passano da 0 a 2 per `frame_minus_baseline` e a 1 per la polarità opposta. È un
segnale positivo, ma ancora insufficiente per enrollment, matching o production.

## Correzioni interpretative

Le due sottrazioni signed seguite da min/max generano immagini complementari,
a meno dell'arrotondamento. Non sono quindi due repliche indipendenti della
rimozione del fixed field: isolano soprattutto la sensibilità di NBIS alla
polarità. Anche il baseline auto-sottratto nullo è una conseguenza matematica,
non un discriminatore indipendente. La lieve preferenza per
`frame_minus_baseline` resta solo sperimentale.

Il B0 iniziale è utilizzabile come riferimento sperimentale in questa cattura,
ma la sua funzione OEM come calibration/background frame non è provata.

## Audit del metodo

Nel libfprint pinned esistono entrambe le convenzioni sensor-specifiche:

- Elan e Egis0570 applicano `max(frame-background, 0)` prima della
  normalizzazione; Egis marca poi l'immagine come color-inverted;
- VFS7552 applica `max(background-frame, 0)` e guadagno fisso;
- tutti scartano la deviazione del segno opposto anziché rimapparla nell'intero
  range come fa il signed min/max D279/42.

Rockytkg usa invece delta signed con offset/clamp, flat-field, stretch robusto e
enhancement; è corroborazione terza matcher-specifica, non prova APP12509 e non
ne è stato copiato codice. Flat-field, sharpening e robust stretch introdurrebbero
ulteriori variabili prima di aver chiuso la rettifica più semplice.

Il prossimo esperimento minimo confronta pertanto il controllo signed D279/42
con entrambe le rettifiche half-wave, sempre min/max x2. Chiude una sola domanda:
se rifiutare le deviazioni del segno opposto aumenta le minutiae nei tier B/A e
A e, incidentalmente, quale segno è coerente col target. Non decide production.

```text
OUTCOME=AUTHENTIC_D279_42_ACCEPTED_AND_HALFWAVE_BOUNDARY_SELECTED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_AND_CORRECTED_INTERPRETATION
EXECUTABLE_CLOSURE=PASS_AGGREGATE_AUDIT_ONLY
D279_42_AUTHORIZATION_CONSUMED=true
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
PRODUCTION_PATH_CHANGED=false
```
