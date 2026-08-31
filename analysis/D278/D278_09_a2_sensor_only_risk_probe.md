# D278/09 — exact A2 sensor-only one-shot risk probe, live consumata

## Closure

```text
OUTCOME=READY
ADVANCEMENT=REAL_EXECUTION_COMPLETED_EXACT_A2_ACCEPTED_IN_CURRENT_REENTRY_CONTEXT
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=A8_AFTER_SUCCESSFUL_SAME_SESSION_A2_REMAINS_UNTESTED_AND_ABSOLUTE_DEVICE_NVM_NONMUTATION_PROOF_IS_UNAVAILABLE
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_07eb95c95e955fe915bd0ef8f5c5f3e057e452c4_ON_main_PLUS_WORKTREE_DIFF_PLUS_analysis/D278/D278_09_a2_sensor_only_risk_probe.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_tools/goodix_d278_a2_sensor_only_probe.c_PLUS_tools/goodix_d278_a2_sensor_only_probe.h_PLUS_tools/d278_a2_sensor_only_observe_once.c_PLUS_libfprint-driver/tests/test_goodix_d278_09_a2_sensor_only_probe.c_PLUS_libfprint-driver/tests/run_goodix_d278_09_a2_sensor_only_probe_test.sh_PLUS_libfprint-driver/tests/run_goodix_d278_09_a2_sensor_only_probe_test_inner.sh

D278_09_BASELINE=07eb95c95e955fe915bd0ef8f5c5f3e057e452c4

OEM_PRE_D1_FAILURE_RECOVERY=RESOLVED
OEM_RECOVERY_FACTORY_PRESERVING=false
LINUX_SAFE_OEM_RECOVERY_CANDIDATE=false

CONTROLLED_RISK_EXPLORATORY_RECOVERY_CANDIDATE=A2_SENSOR_ONLY_EXACT_01_14
OEM_RECOVERY_EQUIVALENCE=false

A2_SENSOR_ONLY_EXACT_BODY=01_14
A2_SENSOR_ONLY_HOST_SEMANTICS=CONVERGED_SENSOR_ONLY_RESET
A2_SENSOR_ONLY_ACCEPTED_ON_APP12509_PREVIOUSLY=true
A2_SENSOR_ONLY_PERSISTENT_MUTATION_EVIDENCE=false
A2_SENSOR_ONLY_DEVICE_NVM_NONMUTATION_ABSOLUTELY_PROVEN=false

ROCKY_12513_A2_SENSOR_ONLY_SEMANTICS_CORROBORATES_LOCAL=true
ROCKY_12513_A2_NVM_SAFETY_CLAIM=EXTERNAL_CORROBORATION_ONLY
INDEPENDENT_12509_STACK_SUCCESS=CORROBORATING_CONTEXT
INDEPENDENT_12509_EXACT_A2_EXECUTION=NOT_BYTE_EXACTLY_PROVEN_FROM_COMMENT_ALONE

RESIDUAL_RISK_CLASS=POST_A2_A8_REENTRY_BEHAVIOR_UNPROVEN_WITH_DEVICE_SIDE_NVM_ABSOLUTE_PROOF_MISSING

A2_RISK_PROBE_IMPLEMENTED=true
A2_RISK_PROBE_LIVE_CAPABLE=true
A2_RISK_PROBE_LIVE_EXECUTED=true

GOODIX_COMMAND_SUBMIT_MAX=1
GOODIX_BULK_OUT_SUBMIT_MAX=1
A2_SENSOR_ONLY_SUBMIT_MAX=1
PHYSICAL_BULK_IN_SUBMIT_MAX=2
PHYSICAL_BULK_IN_COMPLETION_MAX=2
A8_SUBMIT_MAX=0
E4_SUBMIT_MAX=0
A2_MCU_ONLY_SUBMIT_MAX=0
TLS_HANDSHAKE_COUNT=0

RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0

FUTURE_SINGLE_SHOT_A2_SENSOR_ONLY_LIVE_READY_FOR_AI_PM_REVIEW=false

REAL_USB_ACCESS=true
LIVE_EXECUTION_PERFORMED=true
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false

D278_09_LIVE_OUTCOME=PASS
D278_09_LIVE_BASELINE=1c40f6b7b7282ca6e0a39a2c3e2d8672d9544dd6
A2_SENSOR_ONLY_ACCEPTED_IN_CURRENT_CONTEXT=true
A2_SENSOR_ONLY_LIVE_ACK_ECHO=0xA2
A2_SENSOR_ONLY_LIVE_ACK_STATUS=0x07
A2_SENSOR_ONLY_LIVE_TYPED_CONTROL=0xA2
A2_SENSOR_ONLY_LIVE_TYPED_BODY_LENGTH=3
A2_SENSOR_ONLY_LIVE_TYPED_TARGET_PIN_MATCH=true
A2_SENSOR_ONLY_LIVE_RETRY_COUNT=0
A2_SENSOR_ONLY_LIVE_PERSISTENT_WRITE_COUNT=0
A2_SENSOR_ONLY_LIVE_CLEANUP_COMPLETE=true
D278_09_ONE_SHOT_CONSUMED=true
D278_09_RERUN_AUTHORIZED=false
```

## Risultato live integrato

L'operatore ha eseguito una sola volta il probe sulla baseline approvata
`1c40f6b7b7282ca6e0a39a2c3e2d8672d9544dd6`. L'autorizzazione è consumata,
non trasferibile e non consente rerun né A8. La telemetria canonica è:

```json
{"approved_baseline":"1c40f6b7b7282ca6e0a39a2c3e2d8672d9544dd6","identity_preflight_result":"EXACT_ONE_27C6_5125_PRIOR_D277_02_APP12509_AND_EXACT_A2_PROOF_NO_CURRENT_A8","usb_open_count":1,"usb_claim_count":1,"usb_release_count":1,"usb_close_count":1,"goodix_command_count":1,"out_submit_count":1,"a2_sensor_only_submit_count":1,"physical_in_submit_count":2,"physical_in_completion_count":2,"ack_count":1,"typed_response_count":1,"ack_echo":162,"ack_status":7,"typed_control":162,"typed_body_length":3,"typed_result_class":"STRICT_MATCH","timeout_count":0,"retry_count":0,"reopen_count":0,"device_reset_count":0,"clear_halt_count":0,"persistent_device_write_count":0,"tls_handshake_count":0,"unexpected_frame_count":0,"stale_callback_count":0,"prohibited_second_command_count":0,"completion_class":"A2_ACCEPTED","error_class":"NONE","current_context_result":"A2_SENSOR_ONLY_ACCEPTED_IN_CURRENT_CONTEXT","backend_drained":true,"cleanup_completed":true}
```

```text
LIVE_RC=0
ONE_SHOT_CONSUMED=true
RETRY_AUTHORIZED=false
A8_AFTER_A2_AUTHORIZED=false
DO_NOT_RERUN=true
```

È quindi osservato sul target che exact A2 `{01 14}` è stato accettato nello
stato reale corrente e ha completato ACK strict più typed target-pinned. Lo
status ACK `0x07` è successo perché appartiene alla allowlist canonica
`0x01|0x07` ed è seguito dal typed strict match; non gli viene attribuita una
semantica bit-level non dimostrata.

La live non prova nonmutazione NVM assoluta, readiness A8, soluzione della
re-entry, endpoint permanentemente quiescente o assenza di emissioni autonome
tardive. `device_reset_count=0` significa soltanto assenza di primitive USB
reset aggiuntive: il comando A2 sensor-only è contato separatamente.

## Baseline, scope e invarianti

Lo step è iniziato su branch `main`, worktree pulito, con `HEAD` e
`origin/main` coincidenti a
`07eb95c95e955fe915bd0ef8f5c5f3e057e452c4`. Sono stati letti integralmente il
prompt, le policy canoniche, le sezioni D278/03–D278/08, gli artefatti D278/06,
D278/07 e D278/08 richiesti, l'audit semantico A2 e la matrice timeout D231, il
contratto backend D233 e i builder/test correnti. La parentesi
O001/O002/O003/orchestration non è stata usata.

Lo sviluppo e la closure originaria sono stati host-only. In quella fase non sono stati
enumerati o aperti dispositivi, non sono stati inviati A2/A8/E4, non sono stati
letti store protetti e non sono stati usati `sudo`, TLS, PSK, reset USB,
clear-halt, retry, reopen o comandi persistenti. I file congelati D278/03 e i
runtime condivisi elencati nel prompt non sono stati modificati.

## Gerarchia delle evidenze e rivalutazione del rischio

### 1. Evidenza locale target-specific

La capture canonica D255/D256 sul target `27c6:5125`, APP
`GF_ST411SEC_APP_12509`, ha già osservato due exact A2 con control `0xA2`, body
`01 14`, ACK e typed response. L'ordine successful cold-start è
`E4 → A2 → 82 → A6 → A2 → 70 → 80×4 → 90 → D1 → TLS`. Questa è l'autorità
primaria per compatibilità generale del comando sul target; non prova il
current re-entry context.

### 2. Reverse engineering locale 1.1.125.14

D231 lega `gfresetMCUAndfingerprint(false, true, ...)` al flag bit 0, al body
`{01 14}` e al control A2. La semantica host converge quindi su reset del solo
sensore. Non esiste evidenza di mutazione persistente, ma il receiver resident
APP12509 non è nel corpus e resta corretto mantenere:

```text
A2_SENSOR_ONLY_PERSISTENT_MUTATION_EVIDENCE=false
A2_SENSOR_ONLY_DEVICE_NVM_NONMUTATION_ABSOLUTELY_PROVEN=false
```

### 3. Corroborazione Rocky cross-version

Il claim esterno della Issue #1 per `gfusb.dll` 1.1.125.13 ricostruisce gli
stessi bit e classifica `{01 14}` come sensor reset/SetIdle. Lo snapshot locale
Rocky preservato al commit `227eba219fa9e3fbac5bd59aca79f624f67cd11b`
contiene inoltre `gx_dev_reset()` con `uint8_t data[2] = { 1, 20 }`; il path
`init_fpsensor()` lo usa come SetIdle. Questi fatti corroborano
indipendentemente l'identità e la semantica host, non la safety assoluta sul
receiver APP12509 locale. Nessun codice Rocky è stato copiato o adattato in
D278/09.

### 4. Corroborazione indipendente native 12509

Il report terza parte già classificato nel manuale riferisce uno stack Linux
funzionante su `27c6:5125`, chip `0x2504` e firmware nativo 12509 mantenuto,
con TLS, enrollment, verify-match/no-match e PAM. La macchina riportava però
PSK assente (`status 0x01`) e ne ha provisionata una nuova: non prova
preservazione PSK/factory. Il commento non prova byte-per-byte che quella
singola esecuzione abbia inviato exact A2; la plausibilità deriva dal path del
driver e resta `INFERRED_FROM_DRIVER_PATH`.

Prima della live, la classificazione del rischio era più precisa di un
generico comando ignoto:

```text
KNOWN_VOLATILE_SENSOR_RESET
+ KNOWN_PROJECT_TARGET_COMPATIBILITY
+ CROSS_VERSION_INDEPENDENT_SEMANTIC_CORROBORATION
+ INDEPENDENT_NATIVE_12509_STACK_CORROBORATION
+ UNPROVEN_CURRENT_REENTRY_CONTEXT  # chiuso dalla successiva live D278/09
```

La live documentata sopra ha poi sostituito quella componente con
`A2_ACCEPTED_IN_CURRENT_REENTRY_CONTEXT`. Restano non provati la nonmutazione
NVM assoluta, la readiness A8 e la quiescenza permanente; non viene quindi
promossa l'accettazione osservata a una safety assoluta del receiver.

## Implementazione dedicata

`GoodixD278A2SensorOnlyProbe` non istanzia `GoodixSecureSession`, non usa il
router, non apre materiale protetto e non contiene TLS. Il comando è costruito
tramite l'autorità esistente `goodix_a0_build_frame()` con coordinate costanti
`0xA2, 0xA2` e body costante `{0x01, 0x14}`. Il vettore risultante, verificato
dai test, è:

```text
a0 06 00 a6 a2 03 00 01 14 f0
```

La state machine è:

```text
READY
  → exact A2 OUT once
  → exact-length OUT completion
  → one bounded IN for strict ACK
  → one bounded IN for strict typed A2
  → TERMINAL
```

L'ACK deve avere control `B0`, body di due byte, echo `A2` e status nella
allowlist canonica D278/03 `0x01|0x07`. La typed response deve avere control
`A2`, body di tre byte e SHA-256 target-pinned
`39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5`.
Ogni physical IN deve contenere esattamente un frame A0 completo; lunghezza,
tag e checksum sono verificati dal codec canonico. Non esistono accumulation,
discard-until-expected o drain generico.

Il massimo fisico è esattamente quello necessario al contratto A2 già
osservato: due IN, uno per ACK e uno per typed response. Un timeout ACK, typed
missing dopo ACK, mismatch, errore di trasporto, frame E4/A8, callback stale o
secondo start termina senza altro OUT. Il successo classifica soltanto
`A2_SENSOR_ONLY_ACCEPTED_IN_CURRENT_CONTEXT`; non implica readiness A8 o
risoluzione della re-entry.

## Launcher e authorization gate

Il launcher `d278_a2_sensor_only_observe_once.c` usa, solo nella build
live-capable, exact-one descriptor gate `27c6:5125`, open/claim una volta,
endpoint OUT `0x01`, endpoint IN `0x81`, release/close una volta. Non esegue A8
per rileggere la revisione firmware: la telemetria separa descriptor corrente,
prova APP12509 D277/02 pregressa e precedente successo exact A2 sul target.

La build di closure incorpora `UNAPPROVED_FOR_LIVE`. Prima di creare il
contesto GUsb, il gate richiede congiuntamente:

1. una SHA compile-time esadecimale completa di 40 caratteri, diversa dal
   default;
2. la stessa SHA completa a runtime;
3. token operatore esatto
   `D278_09_ONE_A2_SENSOR_ONLY_EXACT_01_14_NO_RETRY`;
4. operation name esatto `D278_09_A2_SENSOR_ONLY_RISK_PROBE`.

Nessuna baseline è stata scelta o auto-approvata. L'invocazione sintetica
`--live-a2-sensor-only-observe-once` sulla build corrente termina con codice 3
e `LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED` prima del contesto USB.

## Telemetria

Il JSON redatto espone baseline/gate, open/claim/release/close, command e OUT,
A2 sensor-only, submit/completion IN, ACK/typed, echo/status/control/lunghezza e
classe typed. Espone inoltre timeout, retry, reopen, reset, clear-halt, TLS,
write persistenti, frame inattesi, callback stale, secondo command attempt,
drain e cleanup. Non salva il body A2 typed né altri payload raw.

## Test host-only

Il runner focalizzato ha passato strict build, due run normali deterministiche
da 9/9 e una run ASAN/UBSAN da 9/9:

| Caso | Esito |
| --- | --- |
| exact `{01 14}`, ACK, typed | PASS; 1 command/OUT, 2 IN, stop |
| ACK timeout | PASS; terminale, nessun resend |
| ACK status mismatch | PASS; terminale |
| typed timeout dopo ACK | PASS; terminale |
| typed body/hash mismatch | PASS; terminale |
| E4-shaped frame | PASS; inatteso, non scartato |
| A8-shaped frame | PASS; inatteso, non scartato |
| callback stale | PASS; nessun nuovo submit |
| secondo command attempt | PASS; fail-closed, count resta 1 |

La stessa esecuzione ha costruito il launcher live-capable, eseguito il
self-test, verificato il gate pre-USB e passato l'audit di simboli, call e
control proibiti. La regressione del secure-session che riusa lo stesso codec
A0 ha passato 11/11 normal e 11/11 ASAN/UBSAN, con zero USB reale.

Il primo avvio del runner nel sandbox si è fermato prima della build per il
limite Flatpak/bwrap `NETLINK_ROUTE`; il tentativo host si è fermato prima
della build perché i file `pkg-config` GLib development non sono installati.
La successiva esecuzione offline nel Freedesktop SDK 25.08 locale, con rete
disabilitata, ha prodotto tutti i PASS sopra. Nessuno dei due failure
ambientali ha creato un contesto USB.

```text
D278_09_STRICT_BUILD=PASS
D278_09_NORMAL=9/9_PASS
D278_09_NORMAL_DETERMINISM_RUNS=2
D278_09_ASAN_UBSAN=9/9_PASS
D278_09_SELF_TEST=PASS
D278_09_UNAPPROVED_LIVE_GATE=PASS_BEFORE_USB_CONTEXT
FORBIDDEN_SYMBOL_AND_CALL_AUDIT=PASS
D278_SECURE_SESSION_REGRESSION_NORMAL=11/11_PASS
D278_SECURE_SESSION_REGRESSION_ASAN_UBSAN=11/11_PASS
HOST_ONLY_CLOSURE_REAL_USB_ACCESS=false
```

## Riesame metodologico pre-live

1. **Cosa cambia realmente rispetto agli ultimi tentativi?** Non viene
   ripetuto A8 né il secure-session D278/03 e non viene ripetuta l'observation
   zero-OUT D278/06. Il nuovo discriminante invia soltanto il noto exact A2
   sensor-only e si ferma dopo le sole risposte causalmente attribuibili.
2. **Quale nuova ipotesi tecnica viene testata?** Che il target, nell'attuale
   stato di re-entry/non-quiescenza, accetti e completi exact A2 `{01 14}` una
   sola volta. Identità del comando, semantica host e compatibilità APP12509
   generale sono già corroborate; la variabile è il contesto corrente.
3. **Se fallisce di nuovo nello stesso punto?** Timeout, mismatch o errore
   causano cleanup e stop. Nessun A2 retry, A8 o comando successivo; nessuna
   observation equivalente viene proposta automaticamente. Si torna
   all'analisi offline del device state e a un discriminante metodologicamente
   diverso, previa nuova review.

Questa procedura è stata poi eseguita una sola volta come documentato sopra.
L'autorizzazione è consumata e nessuna nuova esecuzione D278/09 è ammessa.
