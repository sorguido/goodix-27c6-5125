# D279/47 — assorbimento D279/46 e replan biometrico

## Evidenza autentica

Il summary D279/46 fornito dall'operatore è preservato byte-identico con
SHA-256 `7dfb2feab05a11b01830903c773211d811f5b9a55aac35bd478fd57e4707f90b`.
Il validator digest-pinned verifica schema, baseline approvata, cattura,
operazione, matrice, ruolo `baseline,(primary,auxiliary)*21`, invarianti
statistiche, privacy e riproduzione esatta del blocco `groups` signed D279/44.

Il controllo signed riproduce 10/42 frame fingerprint con minutiae nel tier
NBIS B/A e 2/42 nel tier A. Il complemento scuro-su-bianco della half-wave
`frame > baseline` resta 1/42 e 0/42. Quello di `baseline > frame` resta 9/42
B/A e passa soltanto da 1/42 a 2/42 nel tier A. La polarità d'uscita non produce
quindi un rescue materiale. Il signed resta il miglior candidato NBIS
single-frame osservato, ma non è sufficiente a provare enrollment o matching.

La run era offline: transport verificato, nessun export di PSK/transport,
plaintext, raster o template e zero azioni USB/live. La specifica autorizzazione
D279/46 è consumata e non abilita retry o ulteriori letture protette.

## Decisione PM

La ricerca per trasformazioni semplicemente plausibili si ferma. D279/39–46
mostrano che una quality-map forte non implica minutiae sufficienti e che i
preprocessori signed/half-wave non rendono robusto NBIS sul frammento 80×64.
Questo non dimostra che NBIS sia definitivamente inadatto, né prova che il B0
ATTEMPT02 sia la baseline no-finger usata da Rockytkg.

D279/02 resta valido per la compatibilità strutturale del path NBIS Fedora
44/libfprint 1.94.100. La suitability biometrica non è più una semplice
assenza neutra di dati: è `CHALLENGED_BY_TARGET_EVIDENCE`. Il solo esperimento
successivo giustificato è un confronto controllato sullo stesso input tra
checkpoint Rockytkg R1/R2 e gli extractor NBIS/SIGFM, senza tuning.

```text
OUTCOME=AUTHENTIC_D279_46_ACCEPTED_AND_BIOMETRIC_REPLAN_REQUIRED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_AND_ARCHITECTURAL_COMPARISON_BOUNDARY
EXECUTABLE_CLOSURE=PASS_AGGREGATE_AUDIT_ONLY
D279_46_AUTHORIZATION_CONSUMED=true
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
PRODUCTION_PATH_CHANGED=false
NEXT_PRIMARY_BOUNDARY=CONTROLLED_ROCKY_PREPROCESSING_NBIS_SIGFM_COMPARISON
```
