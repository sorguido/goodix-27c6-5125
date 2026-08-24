# D267/01 — record sanitizzato del live first-image

## Esito e autorità

La singola run D267/01 è stata eseguita manualmente dall'operatore sulla
baseline esplicitamente approvata
`219c038600deb87da1cd93340b9bd07c14e1f5fe`. Questo report materializza
soltanto l'output sanitizzato fornito dall'operatore; non contiene raw USB,
TLS, B0, secret, pixel, raster, hash immagine o dati biometrici.

```text
D267_BASELINE_APPROVED=true
D267_APPROVED_BASELINE_SHA=219c038600deb87da1cd93340b9bd07c14e1f5fe
D267_01_LIVE_AUTHORIZATION_GRANTED=true
D267_01_LIVE_AUTHORIZATION_CONSUMED=true
D267_01_LIVE_ATTEMPT_COUNT=1
D267_01_SECOND_LIVE_ATTEMPT_AUTHORIZED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

## Evidenza primaria fornita dall'operatore

```text
OUTCOME=FAIL_CLOSED
FAILURE_CLASS=RuntimeFailure:first_image_decode_failed
D267_01_LIVE_RESULT=FAIL_CLOSED
D267_01_FAILURE_CLASS=RuntimeFailure:first_image_decode_failed
USB_OPEN_COUNT=1
TRANSPORT_SESSION_COUNT=1
TLS_OBJECT_COUNT=1
TLS_HANDSHAKE_COUNT=1
SECRET_MATERIALIZATION_COUNT=1
FINAL_FDT_ARM_COUNT=1
IRQ2_FINGER_DOWN_COUNT=1
COMMAND_22_ATTEMPT_COUNT=1
COMMAND_22_ACK_VALIDATION_COUNT=1
FIRST_B0_COUNT=1
FIRST_IMAGE_DECODE_STATUS=FAIL_OR_NOT_REACHED
FIRST_IMAGE_RASTER_SHAPE=NOT_REACHED
RETRY_COUNT=0
RECOVERY_COUNT=0
REOPEN_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
FORBIDDEN_POST_IMAGE_COMMAND_COUNT=0
TERMINAL_BOUNDARY=STOP_AFTER_FIRST_IMAGE
HOST_CLEANUP_STATUS=COMPLETED
SECRET_ZEROIZED=true
```

La review AI-PM incorpora quindi come provati live sul percorso eseguito:

```text
IRQ2_HOST_DELIVERY_LIVE_PROVEN=true
0x22_FIXED64_LIVE_SENT=true
0x22_FIXED64_ACK_LIVE_PROVEN=true
FIRST_B0_LIVE_RECEIVED=true
```

Non segue invece alcuna prova dell'immagine:

```text
FIRST_IMAGE_DECODE_LIVE_PROVEN=false
FIRST_IMAGE_LIVE_PROVEN=false
```

## Safety state

La run ha mantenuto retry, recovery, reopen, write persistenti e comandi
post-image vietati tutti a zero. Cleanup host completato e zeroizzazione del
secret sono osservati nell'output operatore. Il report protetto canonico non è
leggibile dall'utente corrente:

```text
PROTECTED_D267_REPORT_READ_STATUS=UNAVAILABLE_WITH_CURRENT_PERMISSIONS
FPRINTD_RESTORE_STATUS=UNVERIFIED_FROM_AVAILABLE_SANITIZED_EVIDENCE
```

Non sono stati usati `sudo`, password, cambio permessi o copie del report raw
durante D267/02. L'autorizzazione one-shot resta consumata e non esiste
autorizzazione per un secondo tentativo.
