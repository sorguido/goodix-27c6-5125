# D279/34 — evaluator varianti NBIS esatto, closure sintetica

## Obiettivo

Chiudere offline il percorso tra i raster D279/33 e lo stesso NBIS usato da
Fedora 44/libfprint 1.94.100, senza introdurre accesso a capture, PSK, USB o
file immagine e senza esportare raster, template o conteggi per singolo frame.

## Superficie valutata

La matrice deterministica contiene 48 varianti:

- scale: mapping production fisso 12-bit, min/max frame-local, percentile
  robusto p01/p99;
- geometria: le otto trasformazioni diedrali, con dimensione 80×64 oppure
  64×80 esplicita;
- polarità: normale e invertita.

L'output contiene per ciascuna variante soltanto aggregati separati per il
baseline, i 21 frame primari e i 21 ausiliari: numero frame, quanti hanno
minutiae, quanti ne hanno almeno 10, minimo, mediana e massimo. I conteggi
per-frame non sono esportati.

## NBIS pinned e isolamento

`test_goodix_nbis_count_pipe.c` è costruito esclusivamente come target test
non installato dal tree pinned. Chiama direttamente `get_minutiae()` con
`g_lfsparms_V2`, `ppmm=0`, profondità 8 e `remove_perimeter_pts=FALSE`, cioè il
profilo del percorso production corrente con `flags=0` e nessun PPMM assegnato.
Riceve solo frame raw su stdin e restituisce un conteggio su stdout; non
accetta path e non contiene entry point USB o driver production.

Build normale e ASan/UBSan passano nel Freedesktop SDK 25.08 senza rete. Un
frame uniforme sintetico 80×64 produce zero minutiae. La suite Python passa
4/4 e verifica coordinate diedrali, clipping robusto, matrice 48, profilo
target 1+21+21, aggregazione e azzeramento dei buffer trasformati borrowed.

Le copie interne o gli oggetti numerici transitori del runtime Python/NBIS non
sono dichiarati provabilmente azzerati. Questo limite dovrà restare esplicito
nel percorso operatore short-lived.

```text
OUTCOME=READY_OFFLINE_EXACT_NBIS_VARIANT_EVALUATOR
ADVANCEMENT=MATERIAL_EXECUTABLE_BIOMETRIC_EVALUATION_BOUNDARY
EXECUTABLE_CLOSURE=PASS_SYNTHETIC_PINNED_NBIS_NORMAL_ASAN_UBSAN
PYTHON_TESTS=4/4_PASS
VARIANT_COUNT=48
TARGET_FRAME_PROFILE=1_BASELINE_PLUS_21_PRIMARY_PLUS_21_AUXILIARY
NBIS_PROFILE=FEDORA44_LIBFPRINT_1_94_100_G_LFSPARMS_V2_PPMM_0_FLAGS_0
PER_FRAME_COUNT_EXPORTED=false
RASTER_OR_TEMPLATE_EXPORTED=false
TARGET_PSK_ACCESSED=false
REAL_RASTER_EVALUATED=0
LIVE_OR_USB_ACTION_COUNT=0
PRODUCTION_USB_ENTRYPOINT_PRESENT=false
RUNTIME_INTERNAL_COPY_ZEROIZATION_PROVEN=false
RESIDUAL_BLOCKER_OR_RISK=PROTECTED_PSK_OPERATOR_BOUNDARY_NOT_YET_PREPARED_OR_AUTHORIZED
CANONICAL_DOCUMENTATION=GOODIX_MANUAL_D279_34
REVIEW_SET=GIT_NATIVE
```

## Confine successivo

Preparare e revisionare offline un operator kit separato, hash-pinned e
fail-closed, che componga D279/33 e D279/34 in un processo short-lived. Il kit
deve fermarsi prima della lettura della PSK finché l'Utente non autorizza
specificamente quella singola analisi protetta. Non è necessaria né consentita
una nuova run sul sensore.

