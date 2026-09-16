# D277/02 — confine nativo A8/A0 su USB reale (target proof)

## Build host-only immediatamente prima della live

L'harness D277 esistente è stato ricompilato e validato dalla baseline canonica
`2a6c19a7e8a6199178fe7ac16e63d4cec495e22b`.

```text
D277_HOST_TESTS=15/15 PASS
D277_SANITIZER_TESTS=15/15 PASS
LIVE_HARNESS_BUILD=PASS
LIVE_HARNESS_PATH=/tmp/goodix-d277-a8.ZGmnuA/d277_native_a8_once
HARNESS_SHA256=8f0b089ea897862f53b6bd274fa266ffa6d3a69591d9f8a5a2bd0860b0e41a2b
```

Il path `/tmp/...` è effimero e non è un artefatto canonico. Lo SHA-256 è
registrato solo come evidenza di integrità del binario costruito. Durante questa
fase non è avvenuto alcun accesso USB reale.

## Prerequisito temporaneo di permesso host

Il target corrente era:

```text
VID:PID=27c6:5125
BUS=001
DEVICE=004
PORT=7
DEVICE_NODE=/dev/bus/usb/001/004
```

Stato iniziale del nodo:

```text
owner=root
group=root
mode=0664
```

L'operatore ha applicato manualmente una named-user ACL **temporanea e solo al
nodo corrente**:

```text
user:guido:rw-
```

Nessuna regola udev persistente è stata creata; non è stato modificato owner,
group o mode globali; l'esecutore non ha eseguito `sudo` né alcuna mutazione host.

Il permission-only preflight ha poi riportato:

```text
DEVICE_NODE=/dev/bus/usb/001/004
DEVICE_NODE_EXISTS=true
DEVICE_NODE_TYPE=character_device
DEVICE_NODE_UID=0
DEVICE_NODE_GID=0
DEVICE_NODE_MODE=0664
EXECUTOR_UID=1000
EXECUTOR_GID=1000
EXECUTOR_GROUPS=10,1000
DEVICE_NODE_READABLE=true
DEVICE_NODE_WRITABLE=true
USB_OPEN_ATTEMPT_COUNT=0
LIVE_AUTHORIZED=false
```

Il preflight stesso non ha aperto o reclamato il dispositivo e non ha consumato
l'autorizzazione live.

## Cambiamento metodologico pre-live

La precedente run live D277/01 si era arrestata al primo `g_usb_device_open()`
perché il contesto operatore non privilegiato non poteva scrivere il device node.

Il cambiamento metodologico materiale di D277/02 è stato quindi limitato ed
esplicito:

```text
temporary per-node ACL -> host permission preflight PASS
```

Questo ha rimosso il blocco ambientale identificato prima di qualsiasi nuovo
tentativo di apertura del target. Non è stato introdotto alcun allargamento di
protocollo.

## Autorizzazione live single-shot esplicita

L'Utente ha autorizzato esattamente una esecuzione live D277/02 limitata a:

```text
open/claim
-> exactly one A8 command
-> receive A8 ACK / typed A8 response
-> cleanup
```

Con vincoli:

```text
zero retry
zero reopen
no other command
no persistent modification
```

L'autorizzazione è stata consumata dalla singola run e non è più attiva.

## Risultato live D277/02 — telemetria autoritativa

La singola invocazione live si è conclusa con:

```text
EXIT_CODE=0
result=pass
failure_class=none
```

Identità del target:

```text
target_vid=27c6
target_pid=5125
target_bus=1
target_address=4
target_port=7
```

Request A8 esatta:

```text
a8_tx_hex=a00600a6a803000000ff
```

USB/open/claim:

```text
usb_open_attempt_count=1
usb_open_count=1
usb_claim_count=1
```

Percorso A8 e ricezione:

```text
a8_command_submit_count=1
bulk_in_submit_count=2
bulk_in_completion_or_cancel_callback_count=2
a8_logical_ack_count=1
a8_typed_response_count=1
a8_firmware_match=true
a8_firmware=GF_ST411SEC_APP_12509
max_outstanding_bulk_in=1
second_reader_api_path=ABSENT
```

I due bulk-IN sottomessi sono validi e attesi per il design bounded implementato:
ACK e risposta tipata A8 sono stati ricevuti tramite receive sequenziali, con al
massimo un IN outstanding alla volta.

Telemetria di sicurezza / negativa:

```text
retry_count=0
transport_reopen_count=0
device_reset_count=0
device_side_cancel_command_count=0
secret_materialization_count=0
tls_handshake_count=0
finger_wait_count=0
image_count=0
persistent_device_write_count=0
host_cache_write_count=0
```

Cleanup:

```text
usb_release_count=1
usb_close_count=1
terminal_cleanup_completed=true
```

Errori host:

```text
usb_open_error=NOT_AVAILABLE
usb_claim_error=NOT_AVAILABLE
usb_release_error=NOT_AVAILABLE
usb_close_error=NOT_AVAILABLE
```

Stato autorizzazione/telemetria dopo il tentativo:

```text
device_contact_or_real_submit_occurred=true
live_authorization_consumed=true
live_authorized=false
current_live_authorized=false
new_user_authorization_required_for_any_new_open_claim_or_submit=true
```

## Cleanup host post-run

Dopo la run live di successo l'operatore ha rimosso manualmente la ACL
temporanea. Il `getfacl` finale non conteneva più `user:guido:rw-`; il check
effettivo ha prodotto:

```text
WRITE_ACCESS_REMOVED
```

Il prerequisito temporaneo di permesso host è quindi stato revocato con successo.

## Conclusioni tecniche

Le seguenti affermazioni sono evidenza target-proven, non speculazione:

```text
D277_02_LIVE_RESULT=PASS
NATIVE_FPI_USB_A8_PATH_TARGET_PROVEN=true
NATIVE_FPI_USB_A0_ROUTER_TARGET_PROVEN=true
APP12509_NATIVE_IDENTITY_REVALIDATED=true
```

Il percorso nativo target-proven da questo step è delimitato a:

```text
real Goodix 27c6:5125
-> GUsb/libfprint-owned USB device
-> FpiUsbTransfer / GoodixFpiUsbBackend
-> GoodixUsbRouter A0 path
-> exact A8 request
-> logical A8 ACK
-> typed A8 firmware response
```

Con identità firmware esatta:

```text
GF_ST411SEC_APP_12509
```

Limiti espliciti:

```text
TLS_NOT_EXERCISED=true
E4_NOT_EXERCISED=true
FINGER_PATH_NOT_EXERCISED=true
IMAGE_PATH_NOT_EXERCISED=true
PERSISTENT_DEVICE_WRITE_COUNT=0
CURRENT_LIVE_AUTHORIZED=false
```

Non si estende l'equivalenza hardware oltre ciò che questa prova A8/A0 target
stabilisce. Non si afferma che la quiescenza del dispositivo dopo cancel
arbitrario sia risolta. Non si afferma che l'integrazione production fprintd/
libfprint sia completa. Non si afferma che il lifetime TLS tra attivazioni sia
risolto.

## Chiusura

```text
D277_02_LIVE_RESULT=PASS
D277_02_DEVICE_SIDE_ADVANCEMENT=NATIVE_A8_A0_TARGET_PROOF
NATIVE_FPI_USB_A8_PATH_TARGET_PROVEN=true
NATIVE_FPI_USB_A0_ROUTER_TARGET_PROVEN=true
APP12509_NATIVE_IDENTITY_REVALIDATED=true
CURRENT_LIVE_AUTHORIZED=false
NEW_USER_AUTHORIZATION_REQUIRED_FOR_ANY_NEW_OPEN_CLAIM_OR_SUBMIT=true
CANONICAL_DOCUMENTATION=UPDATED
NEXT_PRIMARY_BOUNDARY=AI_PM_NEXT_STEP_SELECTION_AFTER_D277_02_CLOSURE

OUTCOME=READY
ADVANCEMENT=NATIVE_A8_A0_TARGET_PROVEN_ON_REAL_APP12509
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=GLOBAL_HARDWARE_EQUIVALENCE_UNPROVEN;PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED;TLS_LIFETIME_ACROSS_ACTIVATIONS_UNRESOLVED;ENROLLMENT_STAGE_POLICY_UNRESOLVED;ORIENTATION_POLARITY_PPMM_UNRESOLVED;PRODUCTION_LIBFPRINT_FPRINTD_INTEGRATION_NOT_YET_PROVEN;FUTURE_LIVE_RUNS_REQUIRE_FRESH_HOST_PERMISSION_PREFLIGHT_AND_NEW_EXPLICIT_AUTHORIZATION
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_2a6c19a7e8a6199178fe7ac16e63d4cec495e22b_PLUS_HEAD_87209c9b20b7b708ebc607724209be69733297c8_PLUS_analysis/D277/D277_02_native_a8_real_usb.md_PLUS_analysis/D277/D277_02_native_a8_real_usb.json_PLUS_Goodix_27c6_5125_manuale_tecnico.md
```
