# D279/41 — calibrazione sintetica della risposta in scala NBIS

## Ipotesi e metodo

La quality-map forte con poche minutiae può essere spiegata senza nuovi dati
protetti: un campo di creste continuo deve avere ridge flow ma nessuna vera
ending/bifurcation interna. L'evaluator genera sinusoidi analitiche 80×64,
senza dato biometrico, su 16 combinazioni orientamento/fase per periodo e le
misura con lo stesso helper NBIS/resize pinned D279/39.

Il codice pinned usa blocchi 8×8, finestre DFT 24×24 e coefficienti 1,2,3,4;
la prima onda è esclusa dalle statistiche direzionali, quindi i periodi
nominali testati sono 12, 8 e 6 pixel. `NEIGHBOR_DELTA=2` applica inoltre una
penalità edge fissa in blocchi, rendendo le proporzioni A/B dipendenti anche
dalla dimensione della mappa.

## Risultato

Build normale e ASan/UBSan producono JSON byte-identico. Pattern continui
ottengono A/B elevata e zero minutiae su ampie regioni dello sweep: il passaggio
`GOOD QUALITY MAP -> POOR MINUTIAE COUNT` non è contraddittorio.

```text
SYNTHETIC_RESULT_SHA256=21b0108c80ea8fbe5ebd41db5334d0a5ad47fa626b4ef6fb3772829d40e760d9
SPATIAL_X2_NATIVE_PERIODS_WITH_MEDIAN_AB_GE_250_PER_MILLE=2.5..11
SPATIAL_X3_NATIVE_PERIODS_WITH_MEDIAN_AB_GE_250_PER_MILLE=2..7
NORMAL_AND_ASAN_UBSAN=PASS_BYTE_IDENTICAL
PROTECTED_OR_BIOMETRIC_INPUT=false
LIVE_OR_USB_ACTION_COUNT=0
```

Lo sweep è una calibrazione algoritmica, non un phantom fisico: non stima il
ridge spacing target e non prova DPI/ppmm. La risposta ampia mostra che i soli
aggregati D279/39 non identificano una scala fisica univoca. I fattori degli
altri piccoli driver libfprint sono workaround driver-locali; non derivano da
un contratto DPI comune documentato.

```text
OUTCOME=SYNTHETIC_SCALE_RESPONSE_CLOSED_PHYSICAL_SCALE_STILL_UNKNOWN
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_OFFLINE_ONLY
D279_41_UNIT_TESTS=3/3_PASS
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
```
