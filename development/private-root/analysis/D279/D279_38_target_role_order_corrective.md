# D279/38 — corrective sull'ordine dei ruoli ATTEMPT02

## Esito

La review PM successiva alla run D279/37 ha individuato un errore di
etichettatura negli evaluator D279/34 e D279/37. Il composer conserva i 43
application record TLS nell'ordine di cattura. L'audit metadata-only D279/10
prova invece questa sequenza wire:

```text
baseline, (primary, auxiliary) × 21
```

Gli evaluator usavano erroneamente:

```text
baseline, primary × 21, auxiliary × 21
```

L'audit riproducibile D279/38 collega la già verificata identità tra i 43 TLS
application record e i 43 B0 fingerprint-shape alle 21 righe primarie D279/10.
Il record 1 è la baseline; per ogni ciclo `n=1..21`, il record `2n` è il B0
primario successivo a `0x22` e il record `2n+1` è il B0 ausiliario successivo a
`0x20`. Tutte le 21 coppie rispettano l'alternanza.

## Impatto sulle evidenze precedenti

Il primo vecchio gruppo da 21 contiene in realtà 11 primari e 10 ausiliari; il
secondo contiene 10 primari e 11 ausiliari. Di conseguenza:

- le statistiche D279/35 e D279/37 attribuite separatamente a primary e
  auxiliary sono invalidate;
- restano validi i fatti invarianti rispetto alla partizione dell'insieme dei
  42 B0 fingerprint: numero complessivo di frame positivi o sopra soglia,
  minimo/massimo complessivo ricavabile dai due gruppi e confronto con la
  baseline;
- non è valida alcuna inferenza precedente secondo cui gli ausiliari sarebbero
  biometricamente migliori dei primari;
- il significato del B0 ausiliario resta ignoto e il percorso production deve
  continuare a trattarlo come opaco.

Per D279/35 rimangono quindi provati, dall'aggregate autentico già preservato,
zero frame fingerprint con almeno 10 minutiae in tutte le 48 varianti e un
massimo complessivo non superiore a 5, raggiunto anche dalla baseline. Non
rimangono provati il “miglior primary” o il vantaggio auxiliary.

Per D279/37 il `summary.json` autentico dichiarato nel riscontro operatore non
è stato materialmente fornito nel workspace né tra gli allegati accessibili.
La matrice testuale è pertanto `USER_ATTESTED`, non un JSON autenticato. Anche
su tale attestazione, le proprietà role-agnostic restano utili: minmax x3 ha
38/42 frame fingerprint positivi, 4/42 con almeno 10 minutiae e massimo 19
contro baseline 1; robust x3 ha 38/42 positivi e 7/42 sopra soglia, ma baseline
8; robust x2 ha baseline 11 mentre nessun frame fingerprint supera la soglia.
Questo sostiene l'effetto della scala e indica minmax x3 come candidato più
pulito, ma non prova ancora struttura biometrica utilizzabile.

Provenance del riscontro operatore:

```text
SOURCE_KIND=USER_ATTESTED_MARKDOWN
SOURCE_SHA256=5a606c593e994254f472e9c46d57d460fccc0c3120566d24277d0272dd2cdc4a
AUTHENTIC_D279_37_SUMMARY_JSON_AVAILABLE=false
D279_37_AUTHORIZATION_CONSUMED=true
```

## Corrective e prossimo confine

Entrambi gli evaluator condivisi assegnano ora i ruoli alternati corretti e i
test verificano esplicitamente inizio e fine della sequenza. I kit D279/35 e
D279/37 e le relative run restano evidenza storica vincolata ai rispettivi SHA
e grant consumati: nessun risultato viene ricostruito o sostituito.

Prima di scegliere fusion o uso production dell'ausiliario, il prossimo
esperimento minimo deve eseguire minmax x3 e controlli artefatto sul ruolo
corretto e misurare, oltre al totale minutiae, il supporto nativo NBIS già
disponibile: istogramma quality-map e conteggi per soglie di reliability. Solo
aggregati per ruolo potranno essere persistiti. Questo testa se il segnale
minmax x3 è sostenuto da blocchi A/B e minutiae affidabili, distinguendolo dai
falsi positivi della baseline robust; non tenta ancora matching o fusion.

## Closure

```text
OUTCOME=ROLE_ORDER_ERROR_CONFIRMED_AND_CORRECTED_OFFLINE
ADVANCEMENT=NEW_PROTOCOL_TO_EVALUATOR_MAPPING_EVIDENCE
EXECUTABLE_CLOSURE=PASS_METADATA_AUDIT_AND_SYNTHETIC_ROLE_TESTS
D279_38_TESTS=10/10_PASS
CORRECT_TARGET_ROLE_ORDER=baseline,(primary,auxiliary)*21
D279_35_ROLE_SPECIFIC_AGGREGATES_VALID=false
D279_37_ROLE_SPECIFIC_ATTESTED_AGGREGATES_VALID=false
D279_37_AUTHENTIC_SUMMARY_JSON_AVAILABLE=false
D279_37_AUTHORIZATION_CONSUMED=true
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
TARGET_PSK_ACCESSED_BY_AI=false
LIVE_OR_USB_ACTION_COUNT_BY_AI=0
NEXT_PRIMARY_BOUNDARY=OFFLINE_CORRECT_ROLE_NBIS_QUALITY_EVALUATOR
CANONICAL_DOCUMENTATION=GOODIX_MANUAL_D279_38
REVIEW_SET=GIT_NATIVE
```
