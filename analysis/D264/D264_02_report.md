# D264/02 — First-image OFFLINE operationalization (AI-PM corrective)

## Provenance canonica e scope

La baseline iniziale locale discende da `a6d0fbea12a841c7071681b50ee7a82c04a0a33b`. Per la tree eseguibile D264/02 sottoposta a review, il riferimento canonico remoto è `REMOTE_REVIEW_HEAD=a4b2eec79071b3b2682962be63c583bad0fae03b`, head osservato dall'AI-PM sulla PR #7 prima del corrective. È un review anchor, non una baseline approvata. Gli SHA `c0463b024f71ed3bb90d228b27f0866660988401` e `7dfa7f85b8630811c82383864217f8cadce2f15e` sono registrati esclusivamente come `EXECUTOR_LOCAL_IMPLEMENTATION_SHA` e `EXECUTOR_LOCAL_DELIVERABLE_SHA`: `LOCAL_EXECUTOR_PROVENANCE_ONLY_NOT_REMOTE_BASELINE_AUTHORITY`.

Il corrective cambia soltanto manuale, report/manifest D264/02 e trasporto bundle. Nessun file sotto `core/`, `tools/`, `operator_kit/` o `tests/` cambia rispetto al remote review anchor: `NO_EXECUTABLE_FILE_CHANGED=true`.

## Closure offline e distinzione di reachability

`PASS_OFFLINE_OPERATIONALIZATION` resta valido. Il launcher D264/02 e il relativo entrypoint costituiscono una rehearsal/operator path **synthetic-only**, non un launcher reale: selezione esplicita → public coordinator → `STOP_AFTER_FIRST_IMAGE` → deadline IRQ2 assoluta/non rinnovabile 15000 ms → candidate fixed64 `0x22` → primo B0 sulla TLS trattenuta → decode in memoria → cleanup host indipendente. Il default resta `STOP_AFTER_FDT_ARM_ACK`; unknown o selezioni multiple falliscono prima dell'entrypoint. I contatori reali USB/TLS/comandi/secret restano zero e nessun payload biometrico viene persistito.

Il percorso reale esistente è distinto. `tools/d261_live_fdt_arm_once.py` continua a invocare `coordinator.run(ts16=ts16)` senza selezionare `STOP_AFTER_FIRST_IMAGE`: sotto i guard esistenti può raggiungere USB reale, ma termina ancora a `STOP_AFTER_FDT_ARM_ACK`. Pertanto `FIRST_IMAGE_LIVE_OPERATOR_WIRING=NOT_IMPLEMENTED`. Prima di chiedere una baseline live serve un successivo step OFFLINE, separato, che cabli il boundary first-image nel percorso reale protetto e ne riesegua review, hash e closure. Questo corrective non implementa tale wiring.

Il manifest v2 separa per-file `reachable_from_d264_offline_operator_path` da `included_for_future_live_review`. Le dipendenze D261 USB/protected/secret sono correttamente non raggiungibili dal launcher D264 synthetic; restano elencate soltanto perché un futuro wiring live le renderebbe pertinenti, con `future_first_image_live_reachability=ARM_ONLY_CURRENTLY`. I file condivisi sono raggiunti dalla rehearsal, ma nel real entrypoint corrente partecipano soltanto al boundary arm-only. Qualunque futura modifica al set richiederà nuovi hash e una nuova approvazione esplicita.

## Verifiche e rischio residuo

JSON validation, diff check, audit dello scope, ZIP test e round-trip Base64 byte-exact passano. Il corrective non riesegue hardware. La closure offline non è promossa a closure live. `0x22` fixed64 e first image restano non live-proven; lo stato interno device post-image e la lifetime interna dell'arm restano ignoti; host cleanup offline non dimostra uno stato device safe.

```text
OUTCOME=PASS_OFFLINE_OPERATIONALIZATION
ADVANCEMENT=DOCUMENTATION_AND_PROVENANCE_CORRECTIVE
EXECUTABLE_CLOSURE=PASS_OFFLINE
AI_PM_CORRECTIVE=PASS
REMOTE_REVIEW_HEAD=a4b2eec79071b3b2682962be63c583bad0fae03b
EXECUTOR_LOCAL_IMPLEMENTATION_SHA=c0463b024f71ed3bb90d228b27f0866660988401
EXECUTOR_LOCAL_DELIVERABLE_SHA=7dfa7f85b8630811c82383864217f8cadce2f15e
FIRST_IMAGE_LIVE_OPERATOR_WIRING=NOT_IMPLEMENTED
D264_02_READY_FOR_BASELINE_APPROVAL=false
RESIDUAL_BLOCKER_OR_RISK=PRELIVE_FIRST_IMAGE_WIRING_NOT_IMPLEMENTED;0x22_AND_FIRST_IMAGE_NOT_LIVE_PROVEN;POST_FIRST_IMAGE_DEVICE_INTERNAL_STATE_UNKNOWN
CANONICAL_DOCUMENTATION=UPDATED
NO_EXECUTABLE_FILE_CHANGED=true
D264_02_READY_FOR_AI_PM_REVIEW=true
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED=false
```
