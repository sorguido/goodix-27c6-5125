# D279/36 — review dell'aggregate autentico D279/35

> **Corrective D279/38:** l'ordine reale dei raster è
> `baseline,(primary,auxiliary)*21`, non tre blocchi contigui. Le statistiche
> separate primary/auxiliary qui riportate sono quindi superate. Restano valide
> solo le conclusioni invarianti sulla partizione complessiva dei 42 B0
> fingerprint; si veda `D279_38_target_role_order_corrective.md`.

## Decisione PM

Il risultato autentico D279/35 è accettato come evidenza aggregate-only della
singola valutazione protetta autorizzata. L'autorizzazione
`D279_35_ONE_OFFLINE_PROTECTED_EVALUATION` è consumata e non autorizza retry,
una seconda lettura protetta, USB o live.

Il prossimo esperimento discriminante non è uno sweep di `ppmm`: il confine
minimo è il resize spaziale controllato con lo stesso algoritmo bilineare del
tree libfprint 1.94.100 pinned. Prima di un nuovo Human Gate restano da
costruire e verificare sinteticamente helper, matrice minima e operator kit.

## Provenance e recovery

La baseline approvata ed eseguita è
`5b2cb03b04e68225134316fb049712830f7ff9f8`. Il commit manuale corregge il
post-link guard del parent `9a9c88d`: `ldd` non poteva dimostrare la presenza
di NBIS perché le unità NBIS sono collegate staticamente nell'eseguibile e il
linker può eliminare `libfprint-2.so.2` da `DT_NEEDED` con `--as-needed`.

Il guard corretto respinge simboli NBIS irrisolti e richiede nel helper le
definizioni di `get_minutiae`, `free_minutiae` e `g_lfsparms_V2`. Insieme allo
snapshot Git e alla build del target esatto, verifica la closure realmente
necessaria. Il primo preflight fallito non ha letto protected material e non
ha eseguito USB/live; il preflight corretto ha passato 19/19 test Python e le
build normali e ASan/UBSan.

L'operatore ha poi eseguito la singola run autorizzata. Il file autentico
ricevuto è preservato byte-per-byte in
`captures/D279_35/D27935_20260906T072751Z/sanitized/summary.json`:

```text
SOURCE_SUMMARY_SHA256=5010f695f539b60b1f03e63d0bcbd6b60d57c06607f9a6340216cf7518cb7d04
BASELINE_SHA=5b2cb03b04e68225134316fb049712830f7ff9f8
CAPTURE_SHA256=3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab
SOURCE_OUTCOME=AUTHENTIC_AGGREGATE_READY
TRANSPORT_INPUT_VERIFIED=true
TRANSPORT_OR_PSK_EXPORTED=false
PLAINTEXT_OR_RASTER_EXPORTED=false
TEMPLATE_EXPORTED=false
LIVE_OR_USB_ACTION_COUNT=0
```

Il JSON non contiene il lifecycle del grant. Consumo one-shot, nessun retry e
cleanup sono quindi attestati dal transcript operatore fornito dall'Utente,
non inferiti dal solo aggregate. Il JSON prova invece direttamente baseline,
capture, contratto privacy e risultato biometrico aggregato.

## Audit riproducibile del risultato

`d279_36_authentic_aggregate_review.py` accetta esclusivamente il digest
autentico sopra, valida schema e chiavi esatti, matrice completa 3×8×2,
cardinalità 1+21+21, invarianti statistiche e assenza di export. Produce
`D279_36_authentic_aggregate_review.json`, senza introdurre conteggi per-frame
o dati biometrici. Quattro test coprono risultato compatto, fail-closed su
digest, matrice/privacy alterate e divieto di overwrite.

## Evidenza biometrica

Tutte le 48 varianti hanno zero frame con almeno 10 minutiae in ciascun gruppo.
La mediana primaria resta zero per ogni variante.

```text
BEST_PRIMARY_VARIANT=robust_p01_p99/hflip/inverted
BEST_PRIMARY_FRAMES_WITH_MINUTIAE=9/21
BEST_PRIMARY_MAXIMUM=5
BEST_AUXILIARY_FRAMES_WITH_MINUTIAE=17/21
BEST_AUXILIARY_MAXIMUM=3
BASELINE_NONZERO_VARIANT_COUNT=26/48
BASELINE_BEST_MAXIMUM=5
```

Il mapping fisso produce al massimo 2 minutiae primarie e mantiene la baseline
a zero; min/max e p01/p99 alzano il massimo primario a 4 e 5, ma producono
anche minutiae spurie sulla baseline fino a 3 e 5. La sola comparsa di qualche
minutia non discrimina quindi qualità biometrica da artefatto di preprocessing.

Nessuna geometria o polarità domina: tutte le geometrie raggiungono 8–9 frame
primari nonzero a seconda del mapping, entrambe le polarità arrivano a 9/21 e
la baseline raggiunge 5 con entrambe. I frame ausiliari sono più spesso
nonzero, ma con massimo inferiore; l'aggregate non consente correlazioni
per-stage né giustifica fusion o accumulo multi-frame.

Il successo dell'enrollment OEM dimostra che il percorso OEM sa usare
l'acquisizione complessiva, non che Windows usi NBIS, una singola immagine,
fusion host-side o la stessa rappresentazione Linux. Queste restano ipotesi.

## Perché `ppmm` non è il prossimo esperimento

Nel NBIS pinned, `get_minutiae()` completa detection e rimozione delle false
minutiae prima di chiamare `combined_minutia_quality()`. `ppmm` entra soltanto
in quest'ultima funzione come `radius_pix = sround(RADIUS_MM * ppmm)`; il ciclo
itera la lista già rilevata e assegna `minutia->reliability`. Non modifica
`minutiae->num`. Il helper D279/34 esporta proprio quel numero, non reliability
o qualità. Cambiare soltanto `ppmm` non può quindi cambiare i conteggi D279/35
e non chiude una nuova incertezza reale.

## Prossimo confine metodologico

Il tree pinned implementa `fpi_image_resize()` con pixman e filtro bilineare.
Il driver comune AES3k dichiara esplicitamente il resize un workaround per
rendere l'immagine abbastanza grande da essere elaborata affidabilmente da
NBIS; AES3500 usa fattore 2, AES4000 fattore 3. Anche VFS7552 replica ogni
pixel su 2×2 prima della consegna.

La prossima matrice deve pertanto isolare la scala spaziale, mantenendo un
controllo fattore 1 e fattori interi 2 e 3, con budget minimo e un output ancora
aggregate-only. Va usato l'algoritmo del tree pinned, non una reimplementazione
approssimata. Il fattore 1 deve riprodurre il sottoinsieme D279/35 equivalente.
Solo dopo closure sintetica e review si potrà preparare un nuovo Human Gate per
una distinta lettura protetta one-shot. Primary/aux fusion, accumulo
multi-frame e ulteriore preprocessing restano differiti finché questa ipotesi
più piccola non è misurata.

## Closure

```text
OUTCOME=AUTHENTIC_AGGREGATE_ACCEPTED_NEXT_HYPOTHESIS_SELECTED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_AGGREGATE_AUDIT_ONLY
D279_36_TESTS=4/4_PASS
SOURCE_SUMMARY_SHA256=5010f695f539b60b1f03e63d0bcbd6b60d57c06607f9a6340216cf7518cb7d04
ALL_VARIANTS_ZERO_FRAMES_AT_OR_ABOVE_10=true
PPMM_ONLY_COUNT_EXPERIMENT=REJECTED_NON_DISCRIMINATING
NEXT_PRIMARY_BOUNDARY=OFFLINE_PINNED_LIBFPRINT_SPATIAL_RESIZE_EVALUATOR_AND_SYNTHETIC_CLOSURE
D279_35_AUTHORIZATION_CONSUMED=true
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
TARGET_PSK_ACCESSED_BY_AI=false
LIVE_OR_USB_ACTION_COUNT_BY_AI=0
CANONICAL_DOCUMENTATION=GOODIX_MANUAL_D279_36
REVIEW_SET=GIT_NATIVE
```
