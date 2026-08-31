# D278/06 — observer precommand zero-OUT, closure host-only e risultato live

## Closure

```text
OUTCOME=READY
ADVANCEMENT=REAL_EXECUTION_COMPLETED_ONE_ZERO_OUT_ONE_IN_BOUNDED_OBSERVATION_WITH_NO_DATA_WITHIN_1000MS
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
HOST_ONLY_CLOSURE=PASS
LIVE_EXECUTION_RESULT=VALID_SINGLE_SHOT_TIMEOUT_NO_DATA
RESIDUAL_BLOCKER_OR_RISK=CURRENT_APP12509_FIRMWARE_IDENTITY_WAS_NOT_REREAD_DUE_TO_CAUSAL_CUT;DEVICE_PROTOCOL_QUIESCENCE_AND_READINESS_FOR_A8_REMAIN_UNPROVEN;EQUIVALENT_OBSERVATION_MUST_NOT_BE_REPEATED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_8ca15e343572676d2ed0de24abda8ebeb3ad0698_ON_main_PLUS_WORKTREE_DIFF_PLUS_analysis/D278/D278_06_zero_out_precommand_observation.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_tools/goodix_d278_precommand_observer.c_PLUS_tools/goodix_d278_precommand_observer.h_PLUS_tools/d278_precommand_observe_once.c_PLUS_libfprint-driver/tests/test_goodix_d278_06_precommand_observer.c_PLUS_libfprint-driver/tests/run_goodix_d278_06_precommand_observer_test.sh_PLUS_libfprint-driver/tests/run_goodix_d278_06_precommand_observer_test_inner.sh

D278_06_BASELINE=8ca15e343572676d2ed0de24abda8ebeb3ad0698
PRECOMMAND_FRAME_EXCLUDES_CURRENT_HOST_COMMAND_CAUSATION=true
PRECOMMAND_FRAME_PREVIOUS_SESSION_IDENTITY=UNPROVEN
POST_A8_WIRE_CAUSAL_PROVENANCE=UNAVAILABLE
ZERO_OUT_OBSERVER_IMPLEMENTED=true
LIVE_CAPABLE_LAUNCHER_IMPLEMENTED=true
LIVE_CAPABLE_LAUNCHER_EXECUTED=true
GOODIX_BULK_OUT_SUBMIT_MAX=0
GOODIX_COMMAND_COUNT=0
SECURE_SESSION_START_COUNT=0
TLS_HANDSHAKE_COUNT=0
PHYSICAL_BULK_IN_SUBMIT_MAX=1
PHYSICAL_BULK_IN_COMPLETION_MAX=1
SECOND_RECEIVE_PATH_PRESENT=false
TIMEOUT_PROVES_DEVICE_QUIESCENCE=false
PRECOMMAND_SILENCE_PROVES_READY_FOR_A8=false
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
REAL_USB_ACCESS=true
LIVE_EXECUTION_PERFORMED=true
FUTURE_SINGLE_SHOT_ZERO_OUT_LIVE_READY_FOR_AI_PM_REVIEW=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

## Risultato live integrato post-review

La AI-PM ha approvato la baseline completa
`1682e01bcc2817f5a0b5028ab6bf4bcac32a61d0` e l'operatore ha consumato una
sola autorizzazione `D278_06_ONE_ZERO_OUT_PRECOMMAND_OBSERVATION_NO_RETRY`.
Questa evidenza è fornita come input canonico a D278/07: non è stata ripetuta
né rieseguita durante l'audit offline. La telemetria esatta è:

```json
{"identity_preflight_result":"EXACT_ONE_27C6_5125_PRIOR_D277_02_APP12509_PROOF_CURRENT_FW_NOT_READ","usb_open_count":1,"usb_claim_count":1,"usb_release_count":1,"usb_close_count":1,"observation_generation":1,"physical_in_submit_count":1,"physical_in_completion_count":1,"received_byte_count":0,"out_submit_count":0,"goodix_command_count":0,"secure_session_start_count":0,"tls_handshake_count":0,"completion_class":"TIMEOUT_NO_COMPLETE_DATA","timeout_count":1,"cancel_count":0,"error_class":"TIMEOUT","frame_class":"NOT_OBSERVED","frame_complete":false,"frame_partial":false,"extra_or_concatenated_data":false,"observed_outer_type":-1,"observed_control":-1,"observed_ack_echo":-1,"observed_ack_status":-1,"observed_body_length":-1,"retry_count":0,"reopen_count":0,"device_reset_count":0,"clear_halt_count":0,"persistent_device_write_count":0,"stale_callback_count":0,"prohibited_out_attempt_count":0,"backend_drained":true,"cleanup_completed":true}
```

```text
D278_06_LIVE_EXECUTION_PERFORMED=true
D278_06_LIVE_EXECUTION_COUNT=1
D278_06_LIVE_BASELINE=1682e01bcc2817f5a0b5028ab6bf4bcac32a61d0
D278_06_LIVE_OUTCOME=VALID_SINGLE_SHOT_TIMEOUT_NO_DATA
D278_06_HYPOTHESIS_RESULT=NO_PRECOMMAND_DATA_OBSERVED_WITHIN_1000MS
D278_06_PHYSICAL_BULK_IN_SUBMIT_COUNT=1
D278_06_PHYSICAL_BULK_IN_COMPLETION_COUNT=1
D278_06_RECEIVED_BYTE_COUNT=0
D278_06_GOODIX_BULK_OUT_SUBMIT_COUNT=0
D278_06_GOODIX_COMMAND_COUNT=0
D278_06_TLS_HANDSHAKE_COUNT=0
D278_06_COMPLETION_CLASS=TIMEOUT_NO_COMPLETE_DATA
D278_06_TIMEOUT_COUNT=1
D278_06_FRAME_CLASS=NOT_OBSERVED
D278_06_USB_OPEN_COUNT=1
D278_06_USB_CLAIM_COUNT=1
D278_06_USB_RELEASE_COUNT=1
D278_06_USB_CLOSE_COUNT=1
D278_06_BACKEND_DRAINED=true
D278_06_CLEANUP_COMPLETED=true
D278_06_RETRY_COUNT=0
D278_06_REOPEN_COUNT=0
D278_06_DEVICE_RESET_COUNT=0
D278_06_CLEAR_HALT_COUNT=0
D278_06_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_06_CURRENT_LIVE_AUTHORIZED=false
D278_06_RETRY_AUTHORIZED=false
D278_06_DO_NOT_RUN_EQUIVALENT_OBSERVATION_AGAIN=true
```

Il risultato è metodologicamente valido e non è un failure del launcher. Prova
che, entro una sola finestra host di 1000 ms dopo open/claim e prima di ogni
Goodix OUT corrente, il singolo IN ha completato per timeout con zero byte;
prova inoltre zero OUT/comandi/TLS/retry/reopen/reset/clear-halt/write
persistente e cleanup completo. Non prova endpoint permanentemente vuoto,
quiescenza del protocollo, assenza di emissioni tardive, identità di una
sessione precedente, revisione firmware corrente o readiness APP12509 per A8.

```text
IMMEDIATE_PRECOMMAND_BACKLOG_WITHIN_1000MS=NOT_OBSERVED
DEVICE_PROTOCOL_QUIESCENCE_PROVEN=false
APP12509_READY_FOR_A8_PROVEN=false
```

## Baseline, scope e safety della closure originaria

Lo step è partito da tree pulito, branch `main`, con `HEAD` e `origin/main`
coincidenti a `8ca15e343572676d2ed0de24abda8ebeb3ad0698` (`feat: enhance
activation process with sticky poison handling and add related tests`). Sono
stati letti il contesto canonico, D277/02, D278/01–D278/05, backend, router,
harness, launcher secure-session e test pertinenti. La parentesi
orchestration/O001/O002/O003 non è stata usata.

Lo sviluppo e tutte le verifiche host-only originarie sono stati sintetici. Non sono stati
enumerati, aperti o reclamati device reali; non sono stati eseguiti launcher in
modalità live, `sudo`, store protetti, PSK, TLS, power-cycle, reset, clear-halt,
reopen, retry o comandi Goodix. Il build live-capable usa deliberatamente la
baseline compile-time `UNAPPROVED_FOR_LIVE`: il test del gate termina prima
della creazione del contesto GUsb. Non viene selezionata né auto-approvata
alcuna baseline live.

I file D278/03 live-critical, inclusi
`tools/d278_native_secure_session_once.c`, `tools/goodix_d278_harness.c`,
`goodix_fpi_usb_backend.*`, `goodix_usb_router.*` e secure session, non sono
stati modificati. Il nuovo codice è GPL-2.0-or-later nel dominio `tools/` e non
importa espressione esterna.

## Architettura eseguibile

Il path è dedicato e non usa `GoodixSecureSession`, TLS, materiali protetti,
il backend D278/03 o il router stream-oriented. Quest'ultimo ricompone frame su
più completion e consegna più frame concatenati, comportamento corretto per il
runtime ordinario ma incompatibile con il boundary D278/06.

`GoodixD278PrecommandObserver` espone un solo start single-shot. Lo start
chiama un seam con direzione fissata a IN e un solo token di generation; il
core non espone alcuna funzione di submit OUT. Una completion matching consuma
il token, classifica l'intero buffer senza conservarne il payload, marca il
backend logico drained e termina. Timeout, cancel ed errore sono terminali.
Callback stale vengono contate ma non possono creare token, comandi o una
seconda observation. Un tentativo sintetico di direzione OUT fallisce
immediatamente nel guard e non incrementa `out_submit_count`.

Il launcher dedicato possiede solo endpoint IN `0x81`. Dopo una futura catena
di autorizzazione valida, la forma è:

```text
exact-one host target gate
→ open/claim exactly once
→ begin generation 1
→ one GUsb bulk-IN submit with finite timeout
→ one completion (data | timeout/cancel | error)
→ structural classification
→ release/close exactly once
→ STOP
```

SIGINT/SIGTERM cancellano il solo `GCancellable`; il callback matching drena
il token prima di release/close. Non esistono pacing, loop di lettura, drain di
protocollo, secondo receive, A8 o continuazione secure-session.

## Classificazione e telemetria

La completion è trattata come unità probatoria indivisibile:

- meno byte della lunghezza dichiarata: `PARTIAL_FRAME`;
- più byte della lunghezza dichiarata: `EXTRA_OR_CONCATENATED_DATA`;
- outer, tag, inner length o checksum A0 inattesi: classe strutturale terminale;
- A0 ACK-shaped: pubblica soltanto control, echo, status e lunghezza;
- A0 typed-shaped o `E4/body41` sintetico: pubblica soltanto control e lunghezza;
- B0: solo outer-complete opaco, senza interpretare o salvare TLS;
- errore/timeout/cancel: terminale, senza tentativo successivo.

Nessuna classe inattesa viene scartata. Il raw buffer appartiene al transfer e
viene liberato dopo la classificazione; JSON e audit non contengono payload,
validator E4, secret TLS o dati biometrici.

## Timeout

Il timeout è configurato una sola volta come
`GOODIX_D278_06_OBSERVATION_TIMEOUT_MS=1000`. La provenance è il bound host
semplice già usato dal probe A8 D277; non viene presentato come conoscenza del
`TARGET_DEVICE_TIMEOUT`, che resta unknown. Esso prova soltanto
`HOST_OBSERVATION_IS_BOUNDED=true`. Un timeout significa esclusivamente
`NO_COMPLETE_OBSERVATION_WITHIN_BOUND=true`.

## Identity gate

La revalidation firmware canonica D277/02 era wire-derived: exact A8 OUT,
ACK e typed response `GF_ST411SEC_APP_12509`. Non è compatibile con zero-OUT e
non è stata riusata o nascosta dietro un preflight.

Il futuro launcher separa quindi esplicitamente:

```text
CURRENT_HOST_DESCRIPTOR_GATE=EXACTLY_ONE_27C6_5125
PRIOR_TARGET_FIRMWARE_PROOF=D277_02_APP12509
CURRENT_APP12509_FIRMWARE_READBACK=NOT_PERFORMED_CAUSAL_CUT
```

Il gate è sufficiente per preparare una review del diagnostico read-only sul
singolo target incorporato già provato, dato che il path non ha alcun OUT o
write device; non prova però da solo la revisione firmware corrente. La
telemetria lo dichiara come
`EXACT_ONE_27C6_5125_PRIOR_D277_02_APP12509_PROOF_CURRENT_FW_NOT_READ`, senza
promuoverlo a revalidation APP12509. La futura AI-PM review deve accettare
esplicitamente questa base probatoria o bloccare la live; D278/06 non la
auto-approva.

## Test host-only e regressioni

Il runner focalizzato è stato eseguito nel Freedesktop SDK 25.08 con rete
disabilitata. La matrice obbligatoria passa:

| Caso | Risultato |
| --- | --- |
| timeout/no data | PASS; 1 IN, 1 completion, zero OUT, cleanup |
| A0 ACK-shaped | PASS; classificato e stop |
| A0 typed-shaped sintetico | PASS; classificato e stop |
| E4/body41 sintetico | PASS; sola shape strutturale |
| frame parziale | PASS; nessuna continuation |
| frame + trailing/concatenazione | PASS; extra preservato come classe |
| errore receive | PASS; terminale, zero retry |
| callback generation stale | PASS; nessun nuovo token/comando |
| tentativo OUT nel seam | PASS; fail immediato |
| riuso single-shot | PASS; rifiutato senza nuovo submit |

```text
D278_06_STRICT_BUILD=PASS
D278_06_NORMAL=10/10_PASS
D278_06_NORMAL_DETERMINISM_RUNS=2
D278_06_ASAN_UBSAN=10/10_PASS
D278_06_LIVE_CAPABLE_LAUNCHER_BUILD=PASS
D278_06_SELF_TEST=PASS
D278_06_UNAPPROVED_LIVE_GATE=PASS_BEFORE_USB_CONTEXT
FORBIDDEN_SYMBOL_AND_CALL_AUDIT=PASS
D276_04_NORMAL_AND_ASAN_UBSAN=5/5_PASS_EACH
D276_03_ROUTER_NORMAL_AND_ASAN_UBSAN=8/8_PASS_EACH
D277_A8_NORMAL_AND_ASAN_UBSAN=15/15_PASS_EACH
D278_SECURE_SESSION_NORMAL_AND_ASAN_UBSAN=11/11_PASS_EACH
REAL_USB_ACCESS=false
REAL_USB_SUBMIT_COUNT=0
```

## Riesame metodologico pre-live

1. **Cosa cambia realmente rispetto alle D278/03?** Il primissimo receive è
   sottomesso e completato prima di qualsiasi Goodix OUT della command stream
   corrente; entrambe le D278/03 avevano già trasmesso A8.
2. **Quale nuova ipotesi viene testata?**
   `PENDING_OR_DELAYED_FRAME_EXISTS_BEFORE_ANY_CURRENT_GOODIX_COMMAND_OUT`.
   Resta un'ipotesi fino a una futura run autorizzata.
3. **Se la futura observation non produce frame o produce un risultato
   inatteso?** Stop dopo quell'unica completion/timeout/error; nessun A8,
   secondo receive o tentativo equivalente. Si torna all'analisi offline del
   recovery OEM pre-D1 o a un discriminante già presente nel corpus.

Un frame futuro escluderebbe soltanto la causalità di un comando Goodix
corrente; non ne proverebbe la sessione precedente. Un timeout non proverebbe
endpoint vuoto permanente, quiescenza APP12509 o readiness per A8.
