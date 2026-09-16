# D279/45 — review autentica D279/44 e confondimento di polarità

## Assorbimento e risultato

La singola run D279/44 è accettata come evidenza aggregate-only autentica. Il
summary è preservato byte-per-byte con SHA-256
`86a98984949b483a8c8887e3f3cfb8742cd6eff5ec1c32943af66cdb7374a331`.
Il validator digest-pinned verifica schema, chiavi, matrice, ruolo canonico
`baseline,(primary,auxiliary)*21`, cardinalità, invarianti statistiche e
privacy.

Sui 42 fingerprint, i frame con almeno una minutia nel tier NBIS B/A sono
10 per il controllo signed, 1 per `max(frame-baseline,0)` e 9 per
`max(baseline-frame,0)`. Nel tier A sono rispettivamente 2, 0 e 1. La
half-wave baseline-positive conserva quindi quasi tutto il risultato signed,
mentre la coppia frame-positive osservata è fortemente sfavorita. Il controllo
signed resta il miglior candidato single-frame osservato, senza essere pronto
per enrollment, matching o production.

## Correzione interpretativa

D279/44 ha variato insieme il supporto di segno conservato e la polarità
dell'immagine risultante: ciascuna half-wave è stata misurata soltanto come
segnale positivo su fondo nero. NBIS è sensibile alla polarità, come mostrava
già la coppia signed complementare D279/42. Il collasso della half-wave
frame-positive non prova quindi che la componente `frame > baseline` sia
intrinsecamente priva di struttura; prova il fallimento della specifica coppia
supporto+polarità misurata.

Analogamente, il vantaggio 10/42 contro 9/42 del signed non dimostra che una
componente opposta contribuisca indipendentemente: min/max e combinazione dei
segni cambiano insieme il remapping e il summary aggregate-only non espone
overlap per-frame. Resta supportata soltanto la formulazione prudente che, in
ATTEMPT02 e nelle polarità provate, le deviazioni negative di
`frame-baseline` conservano la parte dominante del segnale NBIS osservato.

Il baseline auto-sottratto resta nullo per costruzione e il ruolo OEM del B0
non è provato.

## Prossimo discriminante minimo

Prima di introdurre pesi, clipping robusto, dead-zone o fusion, va separato il
supporto di segno dalla polarità d'uscita. Il minimo spazio mancante contiene
le immagini complementari delle due half-wave D279/44, con controllo signed
immutato. Una calibrazione sintetica/non protetta deve prima confermare che la
matrice distingue realmente le due variabili e che non duplica varianti già
misurate.

```text
OUTCOME=AUTHENTIC_D279_44_ACCEPTED_WITH_OUTPUT_POLARITY_CONFOUNDING_CORRECTION
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_AND_CORRECTED_EXPERIMENTAL_BOUNDARY
EXECUTABLE_CLOSURE=PASS_AGGREGATE_AUDIT_ONLY
D279_44_AUTHORIZATION_CONSUMED=true
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
PRODUCTION_PATH_CHANGED=false
```
