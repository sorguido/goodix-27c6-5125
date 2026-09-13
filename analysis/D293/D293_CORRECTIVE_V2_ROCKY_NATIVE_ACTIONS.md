<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D293 corrective v2 — Rocky, action native e gate KDE

Questo report sintetizza il corrective integrato D293/02–04. La matrice
architetturale completa e le regressioni del driver sono in
`D293_02_MULTI_FINGER_IDENTIFY_ENROLL_AND_STORAGE_MODEL.md`; il dettaglio
R1–R8 e la recovery sono in
`D293_04_KDE_NEW_USER_HUMAN_GATE_KIT.md` e nel README dell'experiment.

```text
HEAD=091846914d02f461d4af659ad5de17c0ba4c5363
CURRENT_PHASE=B
WORK_CLASS=D293_LOCAL_REPLAN_AND_CORRECTIVE
ROCKY_COMPARISON=LOCAL_IMPORT_STATE_0b03b3a_PLUS_RECORDED_IMMUTABLE_IDENTITIES_227eba2_AND_7ebe0c8
STANDARD_MECHANISMS_REUSED=FPRINTD_CLAIM_OPEN_PLUS_FPIMAGEDEVICE_ACTIVATE_DEACTIVATE_CLOSE_AND_HOST_SIGFM_MATCHING
LOCAL_DIFFERENCES_RETAINED=APP12509_FRESH_RESOURCE_ROLLOVER_STOP_DRAIN_RELEASE_STICKY_POISON_BASELINE_CONTINUITY_ZERO_UNSAFE_RETRY
R9_SAME_OPEN_IDENTIFY=CONFIRMED_AND_CORRECTED_BY_REAL_ADAPTER_TEST
IDENTIFY_RESULT_CALLBACK=MAINTAINED_MINIMAL_FOR_ASYNC_HOST_OUTCOME_BEFORE_RELEASE
R1_TO_R8=R1_DISTINCT_FINGER_AND_DUPLICATE_STOP_PASS_R2_STANDARD_USER_SANITIZED_ROOT_SUPERVISOR_PASS_R3_SELF_CONTAINED_NORMALIZED_CAPTURE_PASS_R4_STREAMING_PROMPTS_AND_ERRORS_PASS_R5_KCM_CLOSE_VERIFY_REOPEN_DELETE_PASS_R6_SERIALIZED_ATTRIBUTED_IDEMPOTENT_RECOVERY_PASS_R7_STRICT_ACCOUNTING_PASS_BUT_PREACTION_GUI_BUDGET_BLOCKED_R8_PROVENANCE_PASS
EXECUTABLE_CLOSURE=PASS_OFFLINE_LIVE_ENTRYPOINTS_BLOCKED
TESTS=ADAPTER_34_OF_34_AND_32_OF_32_NORMAL_AND_SANITIZER_VIRTUAL_FPRINTD_PASS_KIT_24_OF_24_COMMON_14_OF_14
REAL_TARGET_COMPATIBILITY=FEDORA44_KDE_X86_64_PACKAGE_ABI_SONAME_AND_BUILD_COMPATIBLE_READ_ONLY
REMAINING_TARGET_UNCERTAINTY=KCM_POLICYKIT_ACL_ACCOUNT_MOUNT_STORAGE_AND_USB_LIVE_NOT_EXECUTED
LIVE_EXECUTED_BY_AI=false
PROTECTED_MATERIAL_READ_BY_AI=false
PHASE_B_CLOSED=false
PM_DECISION=HUMAN_REQUIRED
GATE_STATUS=BLOCKED_R7_GUI_SESSION_BUDGET_PREACTION
```

## Decisione architetturale

Il confronto usa anzitutto lo snapshot locale e la storia Git. Gli OID Rocky
esterni non sono oggetti del repository outer materializzato: le identità
`227eba…`, tree `6dda93…` e gitlink `7ebe0c…` restano quelle registrate in
provenance, mentre stato all'import, blob e delta locale sono verificati
direttamente. `Rockytkg/src/goodixgf.c` è invariato dall'import e non contiene
i callback outcome locali.

Rocky e il framework confermano il contratto standard: un open logico, una
activate per action, deactivate e close; fprintd conserva il Claim e ripete
`VerifyStart`/`VerifyStop`. Non vengono importati worker, USB, provisioning,
PSK, retry o percorsi persistenti Rocky. L'adattatore continua invece a
rilasciare e riacquisire le risorse APP12509 per ogni capture pulita, con STOP,
drain, fence e poison già giustificati dalle evidenze locali.

R9 era reale: con gallery multi-dito il secondo `VerifyStart("any")` nello
stesso Claim richiede un secondo IDENTIFY, ma il vecchio ramo lo rifiutava
dopo il primo NO_MATCH. Il test sul vero adattatore ha riprodotto il failure;
il delta `c540d676ef619e3e1f1667778fd902c59566b917` consente una nuova
IDENTIFY soltanto dopo outcome host pulito e non crea azioni da solo. Serie
NO_MATCH→MATCH e tre NO_MATCH producono rispettivamente due e tre capture,
senza quarta acquisizione; retry/fatal/cancel/non-drain/poison non riacquisiscono.
Il caso fatal attraversa il matcher reale via seam test-only, verifica
`FP_DEVICE_ERROR_DATA_INVALID`, poison e rifiuto della successiva IDENTIFY con
zero nuova epoch/claim/materiale/input.

I callback privati `identify_result` e `verify_result` trasportano solo
successo/match fra il confronto host asincrono e l'adattatore. Sono necessari
perché STOP/drain può precedere il matcher, mentre fprintd rilancia
automaticamente su `FP_DEVICE_RETRY`. Non sono API pubbliche o un session
manager. Fedora pristine e Rocky originale non li contengono; la copia Rocky
corrente è parità di test.

## Gate operativo

R1–R6 e i parser/contatori R7 sono chiusi da test comportamentali dei veri
script. Il solo blocker è preventivo: il KCM standard non permette al kit di
intercettare prima dell'esecuzione una seconda enrollment UI nella stessa
sessione. Il controllo journal può soltanto rilevarla dopo. Per non presentare
accounting retrospettivo come guardrail hardware, l'experiment resta
`LIVE_CAPABLE=false`; `prepare.sh`, `--operator-run` e `--deploy` falliscono
prima di build/deployment/privilegio.

Il README corrente è
`operator_kit/live_probe/experiments/d293-kde-new-user/README_IT.md`. Descrive
la sequenza progettata, gli effetti transitori sulla sessione originale e la
recovery, ma avverte esplicitamente di non avviare il gate. La recovery resta
disponibile soltanto per una precedente predisposizione interrotta.

Nessuna live, USB, enumerazione Goodix, root/`sudo`/`pkexec`, account o mount
reale è stata eseguita dall'AI; nessun template o materiale protetto è stato
letto.
