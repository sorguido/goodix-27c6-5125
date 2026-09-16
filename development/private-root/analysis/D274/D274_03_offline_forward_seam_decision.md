# D274/03 parallel offline forward analysis — seam decision (post AI-PM review)

```text
SEAM=goodix_capture_aggregation
DOMAIN=libfprint-driver (LGPL-2.1-or-later)
IMPLEMENTATION=SKIPPED_NO_INDEPENDENT_SAFE_SEAM
REMOVED_AFTER_AI_PM_REVIEW=true
LEDGER_ENTRY_REQUIRED=false
```

## Cosa era stato aggiunto (step precedente)

Quattro file in `libfprint-driver/`:

- `goodix_capture_aggregation.h` / `.c` — collector bounded di capture già decodificate;
- `tests/test_goodix_capture_aggregation.c` — test C sintetici;
- `tests/run_goodix_capture_aggregation_test.sh` — harness flatpak.

## Perché la review AI-PM lo ha scartato (BLOCKER 2)

Il seam era descritto come il "pezzo mancante di enrollment aggregation". La
verifica diretta nel repository contraddice la premessa:

1. **`Rockytkg/libfprint/libfprint/fpi-image-device.c:302-306`** — il framework
   libfprint esegue già l'enrollment/template aggregation multi-stage:
   `fpi_print_add_print(enroll_print, print)` → `priv->enroll_stage += 1` →
   `fpi_device_enroll_progress(...)`. L'aggregazione è *framework-owned*.
2. **`Rockytkg/src/goodixgf.c`** — la glue Rockytkg consegna ogni `FpImage`
   singolarmente via `fpi_image_device_image_captured()` e conserva copie 8-bit
   di frame già accettati solo per una propria euristica di diversità/duplicate
   detection (`gf_enroll_frame_dup`), policy target-quality-dependent e diversa
   dall'aggregazione di framework. Non costruisce un enroll-set di `FpImage`.
3. **`libfprint-driver/goodix_fpimage_pipeline.c`** — il pipeline mantiene
   l'ownership del proprio `FpImage`; un `get_image()` restituirebbe un puntatore
   borrowed. La glue futura deve invece consegnare l'immagine al framework
   secondo il suo lifecycle/ownership.

Il collector quindi: non implementava l'enrollment aggregation reale di libfprint;
non era necessario per consegnare una capture al framework; introduceva retention
multi-image non motivata; non aveva un consumer reale; non soddisfaceva il
criterio originario "chiaramente mancante".

## Azione

I 4 file sono stati rimossi. Nessun altro seam è stato aggiunto.

```text
LIBFPRINT_ENROLLMENT_AGGREGATION=FRAMEWORK_OWNED_VERIFIED
PROJECT_EXTRA_FPIMAGE_AGGREGATOR_REQUIRED=false
LOCAL_LIBFPRINT_DEVICE_GLUE=NOT_YET_IMPLEMENTED
```

## Licensing

Nessun codice esterno copiato/adattato in questo corrective → nessuna nuova riga
di ledger richiesta (coerente con `docs/LICENSING_AND_PROVENANCE.md`).
`src/goodixgf.c` resta `LGPL-2.1-or-later` e riusabile/adaptabile dopo audit
per-file; le porzioni firmware/PSK/GPL-only restano escluse.
