# D264/02 — First-image OFFLINE operationalization

## Baseline, scope e patch plan

Starting HEAD `fbb39daf80e1ec611b496f300ad480ba60e49b02` discende dalla baseline richiesta `a6d0fbea12a841c7071681b50ee7a82c04a0a33b`; branch osservato `work`, non cambiato. Il commit candidate del live-critical set è `c0463b024f71ed3bb90d228b27f0866660988401`. Non è una baseline live approvata.

Il patch plan minimo è stato: riusare `PersistentRuntimeCoordinator.run()` e le fixture D263; aggiungere un launcher/entrypoint esclusivamente sintetico; irrobustire il cleanup indipendente; aggiungere test e aggiornare il manuale. File implementativi modificati: `core/persistent_runtime.py`, `tools/d264_first_image_offline.py`, `operator_kit/d264-first-image-offline.sh`, `tests/test_d264_02_offline_operator.py`, `tests/test_d263_phase2_public_run.py`; aggiornati anche i due README e il manuale canonico.

## Percorso operatore e comportamento

Senza argomenti il launcher preserva `STOP_AFTER_FDT_ARM_ACK`. Solo `--stop-after-first-image` seleziona esplicitamente `STOP_AFTER_FIRST_IMAGE`; unknown o più argomenti falliscono prima di Python e quindi prima di qualunque backend. L'entrypoint non possiede modalità live e guida il public coordinator su transport/event/TLS sintetici D263.

Il percorso opt-in raggiunge: final ACK `0x32` → una wait IRQ2 con deadline host assoluto/non rinnovabile 15000 ms → un `0x22` con policy operational candidate `FIXED64_ZERO_TAIL` → una validazione ACK → un primo B0 sulla TLS trattenuta → CRC/parser/decode canonico in memoria → cleanup host → stop. Il default non raggiunge IRQ2, `0x22` o immagine.

## Invarianti, failure e assenza hardware

Una rehearsal mantiene una sessione transport, una TLS, un handshake e un handoff secret sintetico; zero retry/reopen/fallback. Nel segmento post-arm non compaiono `0x34`, `0x20` post-image, secondo `0x22`, re-arm, A2, `0x70`, recovery o write persistenti. Nessun payload biometrico è serializzato: il report espone soltanto esito e dimensioni.

I test coprono timeout IRQ2, evento inatteso, ACK `0x22` errato, B0 malformato, CRC/decode failure, seconda esecuzione proibita e cleanup parziale. TLS, secret e transport vengono chiusi in blocchi indipendenti: una cleanup exception porta a `FAILED_CLOSED` senza saltare le fasi residue. I dry-run attestano `REAL_USB_OPEN_COUNT=0`, `REAL_TLS_HANDSHAKE_COUNT=0`, `REAL_SENSOR_COMMAND_COUNT=0` e `REAL_SECRET_MATERIALIZATION_COUNT=0`.

## Test ed executable closure

I 34 test D263/D264 mirati passano. Le regressioni environment-independent D260 passano. L'import di `tests.test_d261_operational_readiness` non è disponibile nel container perché manca il pacchetto Python `cryptography`; il failure avviene durante import nella dipendenza storica `binding_reference`, prima del path D264, ed è classificato ambientale, non mascherato. Launcher default/opt-in da cwd `/tmp`, `bash -n`, JSON validation e diff check passano. Bundle e round-trip sono verificati separatamente.

`D264_02_EXECUTABLE_CLOSURE=PASS_OFFLINE`. Il manifest live-critical deriva dalla reachability combinata del nuovo operatore offline e dell'esistente futuro percorso reale; include launcher, backend USB, TLS/secret/authorization, coordinator, framing/lifecycle/image e dipendenze importate. Ogni file ha SHA-256, ruolo e motivazione.

## Rischi residui e review gate

`0x22` fixed64 e first image non sono live-proven. Lo stato interno device post-image e la lifetime interna dell'arm restano ignoti. Il cleanup host è implementato offline, non dimostra uno stato device sicuro. Servono ancora review AI-PM, commit candidate, verifica manifest, approvazione esplicita baseline, autorizzazione live separata e un eventuale nuovo milestone D265.

```text
OUTCOME=PASS_OFFLINE_OPERATIONALIZATION
ADVANCEMENT=NEW_EXECUTABLE_OFFLINE_CANDIDATE
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=0x22_AND_FIRST_IMAGE_NOT_LIVE_PROVEN;POST_FIRST_IMAGE_DEVICE_INTERNAL_STATE_UNKNOWN
CANONICAL_DOCUMENTATION=UPDATED
D264_02_READY_FOR_AI_PM_REVIEW=true
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED=false
```
