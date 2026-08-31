# D278/10 — discriminante same-session A2→A8, closure host-only

## Closure

```text
OUTCOME=READY
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_HOST_ONLY_SAME_SESSION_A2_A8_CAUSAL_GATE_AND_FAILURE_BOUNDARY
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=DEVICE_SIDE_POST_A2_A8_BEHAVIOR_AND_ABSOLUTE_WIRE_CAUSAL_PROVENANCE_REMAIN_UNPROVEN
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_1c40f6b7b7282ca6e0a39a2c3e2d8672d9544dd6_ON_main_PLUS_WORKTREE_DIFF_PLUS_analysis/D278/D278_09_a2_sensor_only_risk_probe.md_PLUS_analysis/D278/D278_10_same_session_a2_a8_reentry_discriminator.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_tools/goodix_d278_a2_a8_reentry_probe.c_PLUS_tools/goodix_d278_a2_a8_reentry_probe.h_PLUS_tools/d278_a2_a8_reentry_observe_once.c_PLUS_libfprint-driver/tests/test_goodix_d278_10_a2_a8_reentry_probe.c_PLUS_libfprint-driver/tests/run_goodix_d278_10_a2_a8_reentry_probe_test.sh_PLUS_libfprint-driver/tests/run_goodix_d278_10_a2_a8_reentry_probe_test_inner.sh

D278_10_BASELINE=1c40f6b7b7282ca6e0a39a2c3e2d8672d9544dd6

D278_09_LIVE_OUTCOME=PASS
A2_SENSOR_ONLY_ACCEPTED_IN_CURRENT_CONTEXT=true
A2_SENSOR_ONLY_LIVE_ACK_STATUS=0x07
A2_SENSOR_ONLY_LIVE_TYPED_TARGET_PIN_MATCH=true
D278_09_ONE_SHOT_CONSUMED=true
D278_09_RERUN_AUTHORIZED=false

SAME_SESSION_A2_COMPLETION_PROVIDES_STRONGER_CAUSAL_ANCHOR_BEFORE_A8=true
POST_A2_A8_RESPONSE_CAUSAL_PROVENANCE_ABSOLUTE=false

A2_A8_REENTRY_PROBE_IMPLEMENTED=true
A2_A8_REENTRY_PROBE_LIVE_CAPABLE=true
A2_A8_REENTRY_PROBE_LIVE_EXECUTED=false

GOODIX_COMMAND_SUBMIT_MAX=2
GOODIX_BULK_OUT_SUBMIT_MAX=2
A2_SENSOR_ONLY_SUBMIT_MAX=1
A8_SUBMIT_MAX=1
PHYSICAL_BULK_IN_SUBMIT_MAX=4
PHYSICAL_BULK_IN_COMPLETION_MAX=4
E4_SUBMIT_MAX=0
A2_MCU_ONLY_SUBMIT_MAX=0
TLS_HANDSHAKE_COUNT=0
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0

FUTURE_SINGLE_SHOT_A2_A8_LIVE_READY_FOR_AI_PM_REVIEW=true

REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

`FUTURE_SINGLE_SHOT_A2_A8_LIVE_READY_FOR_AI_PM_REVIEW=true` indica soltanto
che il candidato host-only è disponibile per review. D278/10 non seleziona o
approva una baseline live e non trasferisce l'autorizzazione D278/09.

## Input live D278/09

La singola live D278/09 sulla baseline
`1c40f6b7b7282ca6e0a39a2c3e2d8672d9544dd6` è `PASS` ed è consumata. Exact
A2 `{01 14}` ha prodotto ACK echo `0xA2`, status `0x07` nella allowlist
canonica, e typed A2 control `0xA2`, body length 3, target pin strict match.
Open/claim/release/close sono 1/1/1/1; command e OUT 1/1; IN
submit/completion 2/2; timeout/retry/reopen/reset/clear-halt/persistent-write/
TLS/unexpected/stale sono zero; backend e cleanup sono completi.

Questo prova l'accettazione A2 nel contesto reale corrente. Non prova
nonmutazione NVM assoluta, readiness A8, soluzione della re-entry, quiescenza
permanente o impossibilità di emissioni tardive. Il valore `0x07` non viene
interpretato bit-per-bit.

## Boundary e causalità

Il nuovo path è dedicato e non modifica i percorsi D278/09 e D278/03. Nella
stessa open epoch ammette soltanto:

```text
exact A2 OUT
→ strict A2 ACK
→ strict typed A2 target pin
→ exact A8 OUT
→ strict A8 ACK
→ strict typed APP12509 exact pin
→ cleanup
→ STOP
```

A8 è sottomesso soltanto dalla transizione che ha appena validato l'intero
contratto A2. Un frame inatteso, timeout, mismatch o errore A2 è terminale e
mantiene `a8_submit_count=0`. Qualunque failure A8 è terminale senza E4,
reset, reopen o retry. Ogni callback deve possedere direzione e generation
outstanding; una completion duplicata/stale non può riattivare la fase
precedente né creare un secondo A8.

Il completamento A2 causalmente osservabile prima dell'A8 restringe molto il
backlog compatibile rispetto a D278/03, dove A8 era il primo comando della
nuova open epoch. Non rende assoluta la provenance: A0 non contiene nonce,
session ID o epoch wire.

## Autorità wire

A2 riusa il codec A0 canonico e l'exact body D278/09:

```text
a0 06 00 a6 a2 03 00 01 14 f0
```

A8 riusa il vettore target-proven D277/D278, non una ricostruzione mnemonica:

```text
a0 06 00 a6 a8 03 00 00 00 ff
```

Il successo A8 richiede ACK `B0`, body esattamente due byte, echo `A8`, status
`0x01|0x07`, poi typed control `A8` con body byte-identical a
`GF_ST411SEC_APP_12509` incluso il terminatore NUL. Una sottostringa `12509`
non è sufficiente.

Ogni IN fisico deve contenere un solo frame A0 completo validato dal codec.
Non esistono accumulation, drain, discard-until-expected, precommand receive o
parser permissivo. I quattro submit/completion IN massimi derivano esattamente
dai due contratti ACK+typed.

## Authorization gate e launcher

La build ordinaria incorpora `UNAPPROVED_FOR_LIVE`. Prima della creazione del
contesto GUsb o dell'enumerazione, una futura build deve soddisfare insieme:

1. full SHA compile-time approvata e non-default;
2. identica full SHA runtime;
3. token `D278_10_ONE_SAME_SESSION_A2_THEN_A8_NO_RETRY`;
4. operation name `D278_10_SAME_SESSION_A2_A8_REENTRY_PROBE`.

Solo dopo il gate, il launcher richiede exactly-one `27c6:5125`, quindi una
sola open/claim e, al terminale, release/close. Il path contiene solo bulk OUT
`0x01` e IN `0x81`; non collega secure session, TLS, PSK, control transfer,
reset o clear-halt.

## Test host-only

Il runner è stato eseguito nel Freedesktop SDK 25.08 con rete disabilitata.
Il primo avvio nel sandbox si è fermato prima della compilazione sul limite
Flatpak/bwrap `NETLINK_ROUTE`; lo stesso runner host-only è poi passato fuori
da quel limite. Nessuno dei due avvii ha creato un contesto USB reale.

```text
D278_10_STRICT_BUILD=PASS
D278_10_NORMAL=14/14_PASS
D278_10_NORMAL_DETERMINISM_RUNS=2
D278_10_ASAN_UBSAN=14/14_PASS
D278_10_SELF_TEST=PASS
D278_10_LIVE_CAPABLE_LAUNCHER_BUILD=PASS
D278_10_UNAPPROVED_LIVE_GATE=PASS_BEFORE_USB_CONTEXT
FORBIDDEN_SYMBOL_AND_CALL_AUDIT=PASS
REAL_USB_ACCESS=false
```

La matrice copre happy path; timeout/mismatch ACK e typed A2; E4 inatteso
durante A2; timeout/mismatch ACK A8; timeout typed A8; APP pin e control A8
errati; callback stale; secondo A2; completion A2 duplicata incapace di
sottomettere un secondo A8. Il self-test verifica 2 command/OUT, un solo A2,
un solo A8, quattro IN, entrambi gli ACK+typed strict e APP12509 exact match.
L'audit statico e dei simboli non risolti conferma l'assenza di E4, 70, 80,
90, D1, E0, A4, F0, F4, TLS, secure-session, USB reset, clear-halt e control
transfer dal path runtime.

## Riesame metodologico pre-live

1. **Cosa cambia realmente?** A differenza di D278/03, A8 non è il primo
   comando della open epoch: è causalmente gated dal completamento strict di
   un exact A2 appena osservato nella stessa sessione. A differenza di D278/09,
   il path non si ferma dopo A2, ma pone una sola domanda aggiuntiva con A8.
2. **Quale nuova ipotesi viene testata?** Dopo exact A2 completato con
   ACK+typed nella stessa open epoch, APP12509 accetta un singolo A8 e produce
   il normale contratto A8 target-pinned senza l'anomalia cross-session.
3. **Se fallisce nello stesso punto?** Stop al primo failure, cleanup e ritorno
   all'analisi offline. Nessun secondo A2/A8, retry, E4, reset o nuova run
   equivalente viene proposto automaticamente.

D278/10 non esegue questa ipotesi sul device. Una eventuale live richiede
review AI-PM, full SHA esplicitamente approvata e autorizzazione single-shot
nuova e specifica dell'Utente.
