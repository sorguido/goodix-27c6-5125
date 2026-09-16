# D275/02 — Linux second-B0 live one-shot readiness (corrective Git-native, operator UX)

## Esito

```text
OUTCOME=READY
ADVANCEMENT=OPERATOR_UX_POKA_YOKE_QUALIFIED_OFFLINE_NO_NEW_HARDWARE_EVIDENCE
EXECUTABLE_CLOSURE=PASS_OFFLINE_FAKE_LIVE_SAME_PRODUCTION_COORDINATOR
RESIDUAL_BLOCKER_OR_RISK=D275_LIVE_BASELINE_SHA_NOT_YET_APPROVED;AI_PM_PRE_LIVE_REVIEW_REQUIRED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_DIFF_AGAINST_b0c3397a26bbe0dcd5be3eb5a0ac2e4ecab5c83f
```

## Corrective locale D275/02 — operator UX poka-yoke

Il percorso live candidate ora guida esplicitamente l'operatore nei tre momenti
fisici del ciclo, con blocchi in italiano su `stderr` e report macchina JSON su
`stdout`:

1. `D275 — PREPARAZIONE` (dito lontano) prima del primo accesso USB reale.
2. `D275 — AZIONE OPERATORE 1/3` (appoggia) immediatamente prima del primo
   `wait_event(IRQ 0x0002)` dopo l'arm finale.
3. `D275 — AZIONE OPERATORE 2/3` (solleva) immediatamente prima della wait
   `IRQ 0x0200` dopo `0x34/ACK`.
4. `D275 — AZIONE OPERATORE 3/3` (appoggia di nuovo) immediatamente prima del
   secondo `wait_event(IRQ 0x0002)` dopo `0x32/ACK`.
5. `D275 — TEST COMPLETATO` dopo il secondo B0 con risultato
   `PASS_STOP_AFTER_SECOND_IMAGE`.

Ogni blocco è separato da almeno due righe completamente vuote, non usa colori
ANSI, non richiede `input()` né sleep artificiali, ed è emesso con `flush=True`
su `stderr`.  I prompt sono agganciati al contatore monotonico delle vere wait
`FIRST_IMAGE_IRQ2_TIMEOUT_MS` del production path: non ci sono state machine
parallele, lettori extra, retry, modifica timeout o ordine.

In caso di qualsiasi failure dopo l'avvio compare una sola volta
`D275 — TEST INTERROTTO` in italiano, senza nascondere la `failure_class`
macchina conservata nel JSON su `stdout`.

La fake-live attraversa lo stesso `PersistentRuntimeCoordinator` con fixture
sintetica e mostra la stessa sequenza di blocchi, ciascuno con la riga
`SIMULAZIONE — NON TOCCARE IL SENSORE`.  Resta hardware-inert:
`REAL_USB_ACCESS=false`, `REAL_SENSOR_COMMAND_COUNT=0`,
`REAL_SECRET_MATERIALIZATION_COUNT=0`, `LIVE_AUTHORIZED=false`.

## Ownership ricostruita

```text
LIVE_ENTRYPOINT=operator_kit/d275-second-b0-once.sh
LIVE_WRAPPER=tools/d275_live_second_b0_once.py
LIVE_TRANSPORT_OWNER=core.usb_runtime.LibusbRuntimeTransport
TLS_SESSION_OWNER=core.persistent_runtime.PersistentRuntimeCoordinator
PSK_BOUNDARY_OWNER=core.protected_runtime.RealSecretBoundary
FDT_LIFECYCLE_OWNER=core.fdt_lifecycle.FdtLifecycle
CURRENT_LIVE_TERMINAL_BOUNDARY=STOP_AFTER_FIRST_IMAGE (D268 storico, invariato)
D275_PRODUCTION_BOUNDARY_OWNER=core.persistent_runtime.PersistentRuntimeCoordinator
LIVE_CLEANUP_OWNER=PersistentRuntimeCoordinator.run finally + D268 host transaction finally
LIVE_PREFLIGHT_OWNER=tools.d275_live_second_b0_once + D275-overridden D268ProductionDependencies
LIVE_COMMAND_ALLOWLIST_OWNER=core.persistent_runtime._ProductionMultiFrameChannel
D275_REPORT_PATH=/var/lib/goodix-5125-poc/d261-results/d275-second-b0-final.json
D275_MARKER_PATH=/var/lib/goodix-5125-poc/d275-second-b0-single-use.marker
D275_MARKER_SCHEMA=D275_SECOND_B0_SINGLE_USE_MARKER_V1
D275_LIVE_CRITICAL_FILE_COUNT=21
```

Il wrapper D268 invoca già il coordinator production, ma fissa
`STOP_AFTER_FIRST_IMAGE`. D275/02 aggiunge wiring e authority operatore: non
duplica FDT, parser B0, D273 runner, NAV, TLS o PSK ownership. Fake e real
transport entrano nello stesso `PersistentRuntimeCoordinator.run()`. Il
`finally` del coordinator chiude TLS, secret e transport anche fra i due B0; il
finally host ripristina segnali/fprintd. La publish D268 è differita; D275
finalizza `PASS_STOP_AFTER_SECOND_IMAGE` e pubblica una sola volta sul proprio
path.

## Corrective host gates

L'authority live D275 è il commit SHA completo approvato dall'AI-PM/Utente.
`verify_d275_authoritative_baseline` verifica SHA lowercase da 40 caratteri,
`HEAD ==` SHA, worktree pulito, path set esatto e byte-identity rispetto al
blob Git. Nessuno SHA è auto-approvato. Non esiste un manifesto SHA-256
per-file D275.

Il live-critical set copre launcher, wrapper, operator D275/D268, capability,
runtime persistente, `multiframe_validation`, lifecycle FDT, transport USB/TLS,
cold-start/seed/post-D4, protected runtime, cleanroom, helper D261 e i moduli
`binding_reference` raggiunti da `protected_runtime`. Manuale, report e test
restano fuori dal pin live.

Il full suite D268 sul current HEAD produce 12 PASS / 1 FAIL / 1 ERROR. FAIL ed
ERROR confrontano il manifest frozen `analysis/D268/D268_01_live_critical_manifest.json`
con file condivisi evoluti (`identita_byte_non_valida` su
`core/fdt_lifecycle.py`, `core/live_capability.py`,
`core/persistent_runtime.py`, `core/runtime_transport.py`). Classificazione:

```text
D268_CURRENT_FULL_SUITE_CLASSIFICATION=EXPECTED_HISTORICAL_MANIFEST_GUARD
D268_CURRENT_SHARED_SEMANTIC_SUBSET=12_PASS
```

Alla baseline storica `c03d32e8647444495e6615e41c2839cbddd62143` (worktree
detached) la suite D268 è riproducibile: manifest e dry-run passano; il test
dirty-tree fallisce solo su tree pulito e passa se il worktree storico è
deliberatamente sporcato. Gli artefatti D268 storici non sono stati riscritti.

## Safety e qualifica

L'allowlist post-image è esattamente `0x34,0x20,0x50,0x32,0x22`. Il secondo B0
completa il runner e porta immediatamente a cancel/terminal stop; non esiste
transizione di terzo ciclo. Report e fake output contengono solo metadata e
contatori.

Il gate live richiede la stringa esatta
`27c6:5125_ONE_SHOT_STOP_AFTER_SECOND_IMAGE_NO_RETRY_FACTORY_PRESERVING_NO_ENROLLMENT_NO_THIRD_CYCLE`,
oltre al flag D275, boundary esplicito e SHA completo approvato. Marker
single-use D275, O_CREAT|O_EXCL, O_NOFOLLOW, mode 0600, fsync prima della
capability. Le capability D268 e D275 non si mintano a vicenda.

La UX operatore è testata offline con:

- ordine esatto `PREPARAZIONE → 1/3 → 2/3 → 3/3 → COMPLETATO` senza duplicazioni;
- spaziatura di almeno due righe vuote fra blocchi adiacenti;
- separazione `stderr` (operator UX) / `stdout` (JSON parseabile);
- timing: ogni azione precede la wait `FIRST_IMAGE_IRQ2_TIMEOUT_MS` corretta;
- failure single-shot `TEST INTERROTTO` che blocca azioni successive;
- fake-live con zero accesso USB/secret reale.

## Riesame metodologico pre-live

1. Cambia realmente il metodo: D268 si fermava alla prima immagine; il candidate
   usa ora il lifecycle production-shaped D275/01 fino allo stop al secondo B0,
   con authority/report/marker D275 realmente distinti.
2. L'ipotesi futura è che il target Linux accetti l'intero edge APP12509 già
   osservato Windows e chiuso offline, nella stessa sessione TLS/USB.
3. Se fallisce allo stesso confine, non si ripete: si classifica la failure
   semantica e si torna ad analisi offline/evidenza sanitizzata.

Nessun hardware è stato aperto. Il comando live resta
`CANDIDATE_ONLY_PENDING_AI_PM_REVIEW`.
