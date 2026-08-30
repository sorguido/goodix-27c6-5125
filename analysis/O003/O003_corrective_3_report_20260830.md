# O003 corrective #3 — true process-restart closure

## OUTCOME

PASS host-only per Findings M/N/O. Nessun accesso Goodix, sudo/root, materiale
protetto, `development` canonico, update di `main`, gate GitHub reale o fallback
pay-as-you-go è stato eseguito.

## ADVANCEMENT

Il recovery è ora provato con store, engine, lifecycle, driver e coordinator
ricreati, oltre che con processi distinti sullo startup path di `service-run`.
I turni strutturati rendono atomici dispatch, risultato validato e
`COMPLETED`; il crash pre-commit qualificato resta fail-closed con zero secondo
turno. Il gate salva il checkpoint pre-binding prima della transizione locale e
recupera una sola issue.

## EXECUTABLE_CLOSURE

PASS locale: compileall e 160 test deterministici con `ResourceWarning` fatale.
La qualifica true-restart raggiunge `DONE`, cleanup `PASS`, massimo un task
branch, `main` invariato e nessuna duplicazione. La qualifica subprocess usa un
processo nuovo per ogni tick e raggiunge lo stesso stato finale. Poiché il
Finding N modifica l'adapter, un singolo smoke reale ChatGPT read-only ha
prodotto un dispatch, un `COMPLETED` e zero risultati strutturati mancanti.

## RESIDUAL_BLOCKER_OR_RISK

Il vero GitHub Human Gate E2E resta Human-controlled e non eseguito. Il crash
tra terminale Codex e commit atomico è qualificato come fail-closed, non come
recupero dell'esatto output remoto. `ORCHESTRATION_READY_FOR_GOODIX` resta
falso; nessun O004, `development` canonico o live runner è autorizzato.

## CANONICAL_DOCUMENTATION

Aggiornati organicamente manuale tecnico, `orchestration/SPEC.md` e
`orchestration/README.md` per restart reale, atomicità del risultato e ordine
pre-binding.

## REVIEW_SET

Baseline: `ddaa4ba7ff116104f1ffd0736c7abbe5f45bd285`; branch:
`ai-executor/o003-human-gate-service-hardening`; review head:
`GIT_REVIEW_HEAD_DYNAMIC`. La CI fresca è risolta dai check sull'esatto review
head finale dopo push.

```text
FINDING_M_TRUE_PROCESS_RESTART=PASS
FINDING_N_STRUCTURED_TURN_DURABILITY=PASS_ATOMIC_OR_FAIL_CLOSED_NO_REDISPATCH
FINDING_O_GATE_PREBINDING_RESTART=PASS

COORDINATOR_REENTRY_TEST=PASS
TRUE_STORE_ENGINE_RESTART_TEST=PASS
SUBPROCESS_SERVICE_RESTART_TEST=PASS

COMPLETED_WITHOUT_STRUCTURED_RESULT_COUNT=0
DUPLICATE_PM_PLAN_DISPATCH_COUNT=0
DUPLICATE_EXECUTOR_DISPATCH_COUNT=0
DUPLICATE_PM_REVIEW_DISPATCH_COUNT=0
DUPLICATE_COMMIT_COUNT=0
DUPLICATE_PUSH_COUNT=0
DUPLICATE_INTEGRATION_FF_COUNT=0
DUPLICATE_GATE_ISSUE_COUNT=0

REAL_PRODUCTION_COORDINATOR_CODEX_QUALIFICATION=PASS_PREVIOUS_DISPOSABLE_NOT_REPEATED
REAL_EXACT_ROUTE_PROBE=PASS_PREVIOUS_GPT_5_6_SOL_MEDIUM
REAL_STRUCTURED_TURN_SMOKE=PASS_CHATGPT_ONE_DISPATCH_ONE_COMPLETED_ZERO_MISSING_RESULT
REAL_GITHUB_GATE_E2E=NOT_EXECUTED

FINAL_HEAD=GIT_REVIEW_HEAD_DYNAMIC
FRESH_ORCHESTRATION_CI=PENDING_FINAL_HEAD_PUSH
FRESH_GOODIX_REGRESSION_CI=PENDING_FINAL_HEAD_PUSH

GOODIX_USB_OPEN_COUNT=0
SUDO_USE_COUNT=0
PROTECTED_MATERIAL_ACCESS_COUNT=0
MAIN_UPDATE_COUNT=0
PAYG_FALLBACK_COUNT=0
UNSANDBOXED_TASK_CODE_EXECUTION_COUNT=0
```
