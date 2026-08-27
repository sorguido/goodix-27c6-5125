# D275/04 — Closure della seconda acquisizione Linux live

> **Reasoning**: medio/alto, correttivo/documentale  
> **Natura**: closure Git-native + consolidamento evidenza + aggiornamento manuale  
> **Nuovo live hardware**: VIETATO  
> **Baseline live post-corrective**: `6eb60856fee7eed2c1765e5b1a11b492e99e42b0`

## 1. Obiettivo

Chiudere formalmente D275 dopo la prima esecuzione Linux live PASS fino al
secondo B0, consolidando nel repository e nel manuale tecnico canonico la nuova
evidenza target-specific.

Questo step NON modifica il protocollo, NON prepara una nuova live e NON espande
il lifecycle oltre `STOP_AFTER_SECOND_IMAGE`.

## 2. Esito live

```text
result=PASS_STOP_AFTER_SECOND_IMAGE
phase_reached=STOP_AFTER_SECOND_IMAGE
failure_reason=null
runtime_state=CLOSED
```

Trace live osservata:

```text
0x36
0x50
0x36
0x82
0x20
0x36
0x32
0x22
0x34
0x20
0x50
0x32
0x22
```

Il percorso live ha superato con successo:

```text
cold start
→ TLS 1.2 PSK
→ D4
→ AF
→ fresh FDT
→ first IRQ 0x0002
→ first 0x22
→ first B0 / first image
→ 0x34 con FDT-up derivata OEM
→ IRQ 0x0200
→ post-up 0x20
→ post-up B0 / NAV 0x50
→ re-arm 0x32 con down-table derivata
→ second IRQ 0x0002
→ second 0x22
→ second B0
→ STOP_AFTER_SECOND_IMAGE
→ cleanup
```

## 3. Audit live

```text
first_image_irq2_observed_count=1
first_image_ack_validation_count=1
first_image_b0_count=1
first_image_raster_decode_count=1
first_image_received=true
image_command_attempt_count=2

persistent_device_write_count=0
host_cache_write_count=0
retry_count=0
transport_reopen_after_tls=false

usb_transport_session_count=1
transport_cleanup_count=1

tls_server_session_object_count=1
tls_server_handshake_count=1
tls_close_count=1

second_server_session_created=false
second_psk_provisioning=false
secret_boundary_handoff_count=1
secret_boundary_zeroized=true
tls_uses_same_secret_boundary_object=true

cleanup_failures=[]
terminal_cleanup_completed=true
target_firmware=GF_ST411SEC_APP_12509
operational_fdt_physical_policy=true
```

Il runner ha mostrato correttamente all'operatore:

```text
1/3 APPOGGIA
2/3 SOLLEVA
3/3 APPOGGIA
TEST COMPLETATO
SECONDO B0 RICEVUTO
```

## 4. Safety invariants

Tutti gli invarianti factory-preserving sono stati rispettati:

- `persistent_device_write_count=0`
- `host_cache_write_count=0`
- `retry_count=0`
- `transport_reopen_after_tls=false`
- nessun flash / IAP / provisioning / OTP / factory write
- nessuna modifica PSK
- nessun enrollment, terzo ciclo, retry/reopen, timeout widening
- cleanup e zeroizzazione secret completati

## 5. Promozione del boundary

D275/04 promuove i seguenti confini a **osservati live sul target APP12509**:

```text
LINUX_FIRST_IMAGE_LIVE_OBSERVED=true
LINUX_IRQ0200_AFTER_0X34=OBSERVED
LINUX_SECOND_IRQ0002=OBSERVED
LINUX_SECOND_0X22=OBSERVED
LINUX_SECOND_B0_LIVE_OBSERVED=true
STOP_AFTER_SECOND_IMAGE_LIVE=PASS
```

Il secondo B0 Linux non è più classificato come non osservato.

## 6. Causalità FDT — da `STRONG_CAUSAL_INFERENCE` a `LIVE_VALIDATED`

Prima del corrective D275/03, due live sulla baseline
`3443154184e138ba0b104669076132c27ace8255` fallivano entrambe così:

```text
first cycle → 0x22 → first B0 → 0x34 / ACK → wait IRQ 0x0200
→ TimeoutError:libusb_bulk_timeout:0x81 → FAIL_CLOSED
```

Nel secondo tentativo il timing operatore era controllato, eliminando il
confound umano.

D275/03 ha verificato che la vecchia baseline Linux passava erroneamente:

```text
IRQ 0x0002 event.raw_base → direttamente a build_fdt_up()
```

mentre APP12509 OEM usa la FDT-up derivata:

```text
IRQ 0x0002 + touch_flags=0x003f → 80 || ((raw_word >> 1) + 0x1d)
```

e per `IRQ 0x0200`:

```text
IRQ 0x0200 + touch_flags=0 → 80 || (raw_word >> 1)
```

D275/03 aveva classificato:

```text
FDT_TABLE_MISMATCH_CAUSALITY=STRONG_CAUSAL_INFERENCE
```

Dopo il PASS live post-corrective, la classificazione è promossa a:

```text
FDT_TABLE_MISMATCH_CAUSALITY=LIVE_VALIDATED
```

Motivazione:

1. prima del corrective: due failure identiche dopo `0x34/ACK`, nessun
   `IRQ 0x0200`;
2. operator timing confound eliminato;
3. timeout widening escluso dall'evidenza OEM;
4. lost-event race non trovata;
5. vecchia tabella `0x34` verificata come errata rispetto all'OEM;
6. dopo il solo corrective protocollo FDT derivation + telemetry, il medesimo
   percorso supera `IRQ 0x0200` e raggiunge il secondo B0;
7. la modifica telemetry non altera traffico o sequencing device-side.

Questa promozione è validata live sul target APP12509 per questo boundary e
questo percorso; non è una pretesa assoluta oltre il corpus disponibile.

## 7. Cosa resta UNKNOWN

```text
TARGET_DEVICE_TIMEOUT=UNKNOWN
```

Il PASS non misura né chiude il timeout semantico del device. Rimangono inoltre
non affrontati in questo step:

- enrollment / matcher / fprintd integration
- terzo ciclo di acquisizione
- qualità biometrica target-specific
- orientation / polarity dell'immagine
- `ppmm`/`DPI` fisico target-specific

## 8. Nessuna nuova live autorizzata

```text
LIVE_AUTHORIZED=false
NEW_LIVE_AUTHORIZED=false
```

D275/04 è una closure; non autorizza alcuna nuova run live, enrollment, terzo
ciclo, persistenza, retry/reopen o marker rearm.

## 9. Review set Git-native

- **Baseline live post-corrective**: `6eb60856fee7eed2c1765e5b1a11b492e99e42b0`
- **HEAD corrente**: `6eb60856fee7eed2c1765e5b1a11b492e99e42b0` (main)
- **Branch**: `main`
- **File modificati / artefatti**:
  - `Goodix 27c6 5125 manuale tecnico.md`
  - `analysis/D275/D275_04_second_b0_live_closure.md`
  - `analysis/D275/D275_04_second_b0_live_closure.json`
- **Evidenze raw private**: `captures/` (non duplicate; futuri export pubblici
  le escludono)

Nessun ZIP, `.zip.b64`, bundle manifest o review archive è stato creato.
