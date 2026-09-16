# D278/11 — prefisso A2 re-entry recovery nel secure-session nativo (host-only)

## Closure

```text
OUTCOME=READY
ADVANCEMENT=NEW_HOST_ONLY_EXECUTABLE_INTEGRATION_OF_TARGET_PROVEN_A2_REENTRY_RECOVERY_INTO_COMPLETE_NATIVE_SECURE_SESSION
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=A2_RECOVERY_CAUSAL_MECHANISM_AND_UNIVERSAL_SAFETY_AND_ABSOLUTE_DEVICE_NVM_NONMUTATION_REMAIN_UNPROVEN;NO_D278_11_LIVE_AUTHORIZATION
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_529e98626421b3f3fc1e85f9a25c5e938b357482_ON_main_PLUS_WORKTREE_DIFF_PLUS_analysis/D278/D278_10_same_session_a2_a8_reentry_discriminator.md_PLUS_analysis/D278/D278_11_reentry_prefixed_native_secure_session_host_only.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_libfprint-driver/goodix_secure_session.c_PLUS_libfprint-driver/goodix_secure_session.h_PLUS_tools/goodix_d278_harness.c_PLUS_tools/goodix_d278_harness.h_PLUS_tools/d278_native_secure_session_once.c_PLUS_libfprint-driver/tests/test_goodix_d278_secure_session.c_PLUS_libfprint-driver/tests/test_goodix_d278_02.c_PLUS_libfprint-driver/tests/run_goodix_d278_02_test_inner.sh

D278_11_BASELINE=529e98626421b3f3fc1e85f9a25c5e938b357482
D278_10_LIVE_OUTCOME=PASS
D278_10_ONE_SHOT_CONSUMED=true
D278_10_RERUN_AUTHORIZED=false

A2_SENSOR_ONLY_ACCEPTED_IN_CURRENT_CONTEXT=true
SAME_SESSION_A2_THEN_A8_APP12509_TARGET_PROVEN=true
A2_SENSOR_ONLY_REENTRY_RECOVERY_EFFECTIVE_FOR_A8_ON_CURRENT_TARGET_CONTEXT=true
A2_REENTRY_RECOVERY_CAUSAL_MECHANISM=UNKNOWN
A2_REENTRY_RECOVERY_UNIVERSALLY_REQUIRED=false
A2_REENTRY_RECOVERY_UNIVERSALLY_SAFE_ALL_FIRMWARE=false
A2_DEVICE_NVM_NONMUTATION_ABSOLUTELY_PROVEN=false
WIRE_CAUSAL_PROVENANCE_ABSOLUTE=false

REENTRY_RECOVERY_A2_OEM_EQUIVALENCE=false
REENTRY_RECOVERY_A2_PROJECT_POLICY=true
NATIVE_SECURE_SESSION_REENTRY_PREFIX_IMPLEMENTED=true
NATIVE_SECURE_SESSION_REENTRY_PREFIX_HOST_ONLY_PROVEN=true

REENTRY_RECOVERY_A2_SUBMIT_MAX=1
A8_SUBMIT_MAX=1
E4_SUBMIT_MAX=1
A2_MCU_ONLY_SUBMIT_MAX=0
HOST_ONLY_FULL_PATH_GOODIX_COMMAND_SUBMIT_MAX=14
HOST_ONLY_FULL_PATH_PHYSICAL_IN_SUBMIT_COUNT=18
HOST_ONLY_FULL_PATH_PHYSICAL_OUT_SUBMIT_COUNT=19
MAX_PHYSICAL_IN_OUTSTANDING=1
MAX_PHYSICAL_OUT_OUTSTANDING=1

RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0

FUTURE_REENTRY_PREFIXED_NATIVE_SECURE_SESSION_LIVE_READY_FOR_AI_PM_REVIEW=true
REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

`FUTURE_REENTRY_PREFIXED_NATIVE_SECURE_SESSION_LIVE_READY_FOR_AI_PM_REVIEW`
significa soltanto che l'implementazione host-only è disponibile per review.
D278/11 non seleziona né approva una baseline live e non materializza un kit
operatore autorizzato.

## Baseline e scope

Lo step è iniziato su `main` con HEAD e `origin/main` coincidenti a
`529e98626421b3f3fc1e85f9a25c5e938b357482` e worktree pulito. Sono state
lette le policy canoniche, il prompt, le sezioni e gli artefatti D278/01–10
pertinenti, D231/D233 e i sorgenti live-critical del path nativo. O001/O002/O003
e orchestration non sono stati usati.

L'implementazione e tutta la verifica D278/11 sono host-only. Non sono stati
enumerati, aperti o contattati device USB; non sono stati letti materiali
protetti autentici; non sono stati eseguiti launcher live, `sudo`, reset,
clear-halt, retry, reopen o write persistenti.

## Input target-specific D278/10

La singola live D278/10 sulla baseline approvata dello step è `PASS` ed è
consumata. Una open/claim/release/close, due comandi e due OUT hanno completato:

```text
A2 {01 14} → ACK 0x07 → typed A2 STRICT_MATCH
A8 {00 00} → ACK 0x07 → typed GF_ST411SEC_APP_12509 STRICT_MATCH
```

I quattro IN sono stati completati; timeout, frame inattesi, callback stale,
retry, reopen, reset, clear-halt, write persistenti e TLS sono zero. Backend e
cleanup sono completi. Il precedente frame E4-shaped osservato in fase A8 non
si è ripetuto dopo il completamento strict A2 nella stessa open epoch.

Ciò prova l'efficacia pratica di A2 per ristabilire A8 nel target/context
corrente. Non prova il meccanismo causale, la necessità universale, la safety
su tutti i firmware, la nonmutazione NVM assoluta o la provenance wire
assoluta.

## Architettura implementata

La stessa `GoodixSecureSession` ora inizia con una policy esplicita e riusa le
primitive e i gate esistenti:

```text
REENTRY_RECOVERY_A2 {01 14}
→ A8 → E4 → OEM_COLD_START_A2_1 → CHIP_82 → OTP_A6
→ OEM_COLD_START_A2_2 → MODE_70 → DAC_220 → DAC_236
→ DAC_238 → DAC_23A → CONFIG_90 → D1 → TLS → STOP
```

Non esiste un secondo secure-session stack. Il recovery usa
`goodix_a0_build_frame()`, l'exact body `{01,14}`, la allowlist ACK
`0x01|0x07` e il pin SHA-256 A2 canonico. Le due A2 successive sono rinominate
come OEM cold-start per impedire equivalenze semantiche improprie. A8 resta
byte-pinned a APP12509; validator E4, ChipID 82, OTP A6, CONFIG90, D1/B0 e TLS
mantengono i gate preesistenti.

## Failure boundary e telemetria

Recovery ACK timeout/mismatch, typed timeout/mismatch ed E4 inatteso sono
terminali con `a8_submit_count=0`. Un failure A8 è terminale con nessun E4. Le
fasi successive conservano il fail-closed esistente. Secondo start,
completion duplicata e callback stale non possono riemettere recovery/A8 o
avanzare due volte.

Il JSON redatto aggiunge:

```text
reentry_recovery_a2_submit_count
reentry_recovery_a2_ack_count
reentry_recovery_a2_typed_count
reentry_recovery_a2_result_class
a8_submit_count
a8_ack_count
a8_typed_count
a8_app12509_pin_match
e4_submit_count
oem_cold_start_a2_1_submit_count
oem_cold_start_a2_2_submit_count
retry_count
reopen_count
device_reset_count
clear_halt_count
persistent_device_write_count
```

I marker JSON rendono inoltre espliciti
`reentry_recovery_a2_oem_equivalence=false` e
`reentry_recovery_a2_project_policy=true`. I conteggi TLS, cleanup, drain e
backend restano preservati.

## Budget deterministico host-only

Il massimo di command submission A0 è 14 e non esiste duplicazione o retry.
Nel peer OpenSSL deterministico usato dalla composizione completa, due
invocazioni normali e due sanitizer hanno riprodotto esattamente:

```text
command_count=14
ack_count=13
typed_response_count=8
tls_handshake_count=1
physical_in_submit_count=18
physical_in_completion_count=18
physical_out_submit_count=19
physical_out_completion_count=19
b0_physical_submit_count=5
max_outstanding_bulk_in=1
max_outstanding_bulk_out=1
```

I 19 OUT sono 14 frame A0 più 5 chunk fisici B0. I conteggi fisici sono il
budget del riferimento host-only deterministico; nessuna misura live D278/11
è stata eseguita.

## Test R1–R12

Il runner focalizzato `run_goodix_d278_secure_session_test.sh` passa 12/12
normal e 12/12 ASAN/UBSAN. Copre il full path TLS, exact recovery body,
timeout/mismatch ACK e typed, E4 inatteso, A8 failure, duplicate completion,
secondo start, generation fencing, failure nelle fasi esistenti e regressione
TLS.

Il runner di composizione `run_goodix_d278_02_test.sh`, eseguito due volte
consecutive nel Freedesktop SDK 25.08 senza rete, passa per invocazione 62/62
normal e 62/62 ASAN/UBSAN. Prova il full path attraverso harness/router/backend,
watchdog recovery, drain, cleanup, telemetria, budget fisico, materiali
sintetici, D190/loader e build live-capable non eseguita.

La regressione del discriminatore D278/10 passa 14/14 per due run normali
deterministiche e 14/14 ASAN/UBSAN, inclusi build strict, self-test, gate
unapproved e audit host-only, sempre senza accesso USB reale.

L'audit source/symbol del live-critical set esclude primitive raggiungibili
E0, A4, ClearApp, IAP, firmware update, `production_write_key`, A2 MCU-only
`{02 14}`, USB reset e clear-halt. Il launcher ordinary-build passa il gate
`UNAPPROVED_FOR_LIVE` prima di materiali protetti, contesto GUsb o
enumerazione.

```text
D278_11_FOCUSED_NORMAL=12/12_PASS
D278_11_FOCUSED_ASAN_UBSAN=12/12_PASS
D278_11_FULL_NORMAL=62/62_PASS
D278_11_FULL_ASAN_UBSAN=62/62_PASS
D278_11_FULL_DETERMINISM_RUNS=2
D278_10_REGRESSION_NORMAL=14/14_PASS_TWO_RUNS
D278_10_REGRESSION_ASAN_UBSAN=14/14_PASS
D278_11_FORBIDDEN_PERSISTENT_RECOVERY_SOURCE_AUDIT=PASS
D278_11_FORBIDDEN_PERSISTENT_RECOVERY_SYMBOL_AUDIT=PASS
D278_11_UNAPPROVED_LIVE_GATE=PASS_BEFORE_MATERIAL_AND_USB_CONTEXT
HOST_ONLY_CLOSURE_REAL_USB_ACCESS=false
```

## Live authorization

Il launcher live-capable conserva default `UNAPPROVED_FOR_LIVE`. Prima di ogni
materiale autentico e prima della creazione del contesto GUsb richiede una
full SHA compile-time non-default, la stessa full SHA runtime, token
`D278_11_ONE_REENTRY_PREFIXED_NATIVE_SECURE_SESSION_NO_RETRY` e operation
`D278_11_REENTRY_PREFIXED_NATIVE_SECURE_SESSION` esatti. Non è incorporata
alcuna SHA approvata. `CURRENT_LIVE_AUTHORIZED=false`.
