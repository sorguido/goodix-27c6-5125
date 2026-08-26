# D274/03 parallel offline forward analysis — seam report

```text
SEAM=goodix_capture_aggregation
DOMAIN=libfprint-driver (LGPL-2.1-or-later)
IMPLEMENTATION=IMPLEMENTED_ONE_SAFE_HOST_ONLY_SEAM
LEDGER_ENTRY_REQUIRED=false
```

## Cosa è stato implementato

Un collector host-only di capture **già decodificate**, in `libfprint-driver/`:

- `goodix_capture_aggregation.h` / `.c` — API `goodix_capture_aggregation_new /
  add / count / get_image / get_image_ppmm_state / finalize / free`;
- `tests/test_goodix_capture_aggregation.c` — positivi (3 capture → 3 `FpImage`,
  count, `ppmm` UNKNOWN, free) e negativi (bounds, null/short, over-max,
  below-min, out-of-range index);
- `tests/run_goodix_capture_aggregation_test.sh` — identico all'harness D270
  (flatpak `org.freedesktop.Sdk//25.08`, strict C, forbidden-symbol audit, ASan/UBSan).

## Perché soddisfa il contratto del task

| Criterio | Esito |
| --- | --- |
| chiaramente mancante | sì: nessun aggregatore multi-capture nel dominio libfprint-driver |
| indipendente da D274 | sì: opera su rasters decodificati (fixture), non serve il secondo ciclo |
| non assume semantica target non provata | sì: `flags=0`, `ppmm` UNKNOWN; nessuna orientation/polarity/ppmm |
| no USB reale | sì: nessun backend, solo `glib` + pipeline D270 |
| no persistent write | sì: nessun file/device/retry |
| no nuove dipendenze | sì: solo `glib`/`GObject`/`libfprint` già usati da D270 |
| non tocca D274/03 / live-critical | sì: nuovi file soltanto |
| testabile con fixture sintetiche | sì: test C puramente sintetici |
| avanzamento reale verso la pipeline Linux | sì: è il pezzo collection del loop driver che alimenta l'enrollment libfprint |

## Verifica

- **forbidden-symbol audit** (grep su `libusb_/usb_/fopen/open/read/write/socket/SSL_/mbedtls_/gnutls_`): nessun
  match nel `.c` nuovo → `PASS` per revisione statica.
- **build/run**: bloccato nel sandbox corrente (`gcc`/`pkg-config`/`flatpak`
  assenti). Lo script `run_goodix_capture_aggregation_test.sh` riproduce
  esattamente l'harness D270 e deve essere eseguito nel dev-environment
  (Flatpak Sdk + OpenCV4-dev non richiesto per questo seam). Stesso stato di
  blocco del build SIGFM reale in D272/D273, ma qui il seam non dipende da OpenCV.
- **no reachability USB/persistent-write**: garantito per costruzione (nessun
  simbolo corrispondente) e per assenza di qualsiasi chiamata device nel sorgente.

## Licensing

Nuova implementazione indipendente nel dominio LGPL; non copia né adatta
`Rockytkg/src/goodixgf.c` né altro codice esterno → nessuna riga di ledger
richiesta (coerente con `docs/LICENSING_AND_PROVENANCE.md`).
