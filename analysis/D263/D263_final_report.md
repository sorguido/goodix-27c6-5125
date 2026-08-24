# D263 — Final report (sottostep 08, ultimo)

**Outcome:** `OFFLINE_IMPLEMENTATION_READY_FOR_AI_PM_REVIEW` (non live-ready).
**Reasoning:** HIGH · **Offline:** yes · **Live execution:** not performed.

## Cosa D263 ha provato offline
- **D263/01** — ordine post-arm target-specific, con evidenza primaria APP12509
  (`rilevamento.pcapng`, hash-gated): `0x32(arm,ACK) → IRQ0x0002 → 0x22[01 00](ACK)
  → first image (TLS B0 17 03 03, 7726)`. Policy fisica `0x22`:
  `ABSTRACT_LOGICAL_ONLY`. Taxonomy `0x22 = PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY`.
- **D263/02** — audit retained TLS + pipeline first-image: una sola sessione
  TLS retainita, codec canonico unico (`decode_image_record` 7684B → 80×64, CRC
  fail-closed). Gap: il coordinator si fermava a `arm()`; post-arm non cablato.
- **D263/03** — terminal-stop candidato dopo la prima immagine (host/TLS/USB
  cleanup → STOP, senza `0x34`/`0x20`/re-arm/A2/`0x70`); gate Phase1
  `READY_FOR_PHASE2_OFFLINE_RUNTIME_INTEGRATION=true`.
- **D263/04** — contratto Phase 2 + patch plan (design-only), baseline
  live-critical prechange hashes.
- **D263/05** — support primitives: `0x22` allowlist in `runtime_transport.py`;
  `post_irq2_image_command()` one-shot + `cancel_pending_receive` accetta
  `FIRST_IMAGE_RECEIVED` in `fdt_lifecycle.py`. 12 test PASS.
- **D263/06** — integrazione runtime: `_run_first_image_terminal()` nel
  coordinator di produzione, riuso codec canonico + TLS retained. 8 test PASS.
- **D263/07** — executable closure + regression audit; micro-correctiva
  (shape raster derivata dal decode, non hardcoded). 20/20 test D263 PASS; full
  discovery 248 (38 ambientali, 0 regressioni D263).
- **D263/08** — consolidamento finale, closure canonica, UNICO bundle.

## Coerenza tra sottostep
Nessuna contraddizione: taxonomy `0x22` costante; gate Phase1 coerente; step05/06/07
implementano esattamente il contratto `D263_04`; hash live-critical coerenti con
`D263_07`. D262 (`PASS_STOP_AFTER_FDT_ARM_ACK`, baseline `e9073a17…`) non regredito.

## File live-critical cambiati (vs `D263_04`)
- `core/persistent_runtime.py` (`8e448caa…` → `c266ef8a…` → `1a731cda…`)
- `core/runtime_transport.py` (`cbbb0b68…` → `2930aa57…`)
- `core/fdt_lifecycle.py` (`2edbec9e…` → `2aac7422…`)
Tutti gli altri backend/guardrail/launcher live-critical: byte-identici.

## Invarianti preservati
One USB/TLS session+handshake; zero second secret/USB reopen/retry/re-arm; exactly
one `0x22`; no `0x34`/`0x20`-post/`A2`/`0x70`/persistent-write; first-image bytes
non persistiti (plaintext azzerato); fail-closed; cleanup su ogni path.

## Residual blocker / risk
Causalità IRQ2→0x22 non provata; `0x22` non live-proven; device-side
restore/cancel/arm-lifetime aperti (D252/D253/D255); `0x22` physical policy
astratta (nessun padding Linux-safe inventato).

## Artefatti (analysis/D263/)
`D263_01_*` … `D263_07_*`, `D263_workflow_state.json`, `d263_01_0x22_evidence_audit.py`,
`D263_final_decision.json`, `D263_final_report.md`, e bundle
`D263_post_arm_first_image_offline_bundle.zip` (+ `.sha256`).

## Bundle
Unico, step-local, non cumulativo. Include artefatti D263 (Phase1+Phase2),
manuale canonico aggiornato, e i file source/test modificati da D263. Esclude
raw capture / secret / biometric / temp / unrelated. Manifest con path+SHA-256.
Verificato: CRC OK, nessun path traversal/symlink, nessun forbidden-material.

## Prossima review necessaria prima di qualunque live
Baseline live esplicitamente approvata dall'AI PM; autorizzazione live separata;
verifica del live-critical set contro questo bundle; evidenza OEM mirata per
chiudere D252/D253/D255. `0x22` resta `OBSERVED_ONLY` finché un live dedicato non
lo accetta.

---

## Correttivo post-review AI-PM (D263/09)

Esecuzione OFFLINE, strictly no-USB/no-sudo/no-secret. Branch
`session/agent_16ceb075-09cc-4bef-9575-02c7f6528892`, HEAD `320dbf3c…`, stato
clean. Nessun live test/autorizzazione; nessun comando USB/PSK/OTP/flash.

**Defect A (CHIUSO):** `run()` promuoveva implicitamente ogni consumer al
boundary D263 (first-image dopo arm). Aggiunto `TerminalBoundary`
(`STOP_AFTER_FDT_ARM_ACK` default = preserva D260/D262; `STOP_AFTER_FIRST_IMAGE`
opt-in); trace check dipendente dal boundary.

**Defect B (CHIUSO):** `0x22` ora seleziona `operational_fdt_a0_policy`
(`FIXED64_ZERO_TAIL`) se `operational_physical_policy=true`, altrimenti
`fdt_a0_policy` (`ABSTRACT_LOGICAL_ONLY`).

**Normalizzazione:** `0x22` = `PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY`;
`ABSTRACT_LOGICAL_ONLY` (logical) vs `FIXED64_ZERO_TAIL`
(`EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE`, non live-accepted); ACK `0x22` =
`EXACTLY_ONE_REQUIRED_AND_VALIDATED`; `FIRST_IMAGE_TERMINAL_STOP` =
`EVIDENCE_SUPPORTED_BUT_DEVICE_INTERNAL_STATE_UNKNOWN` (host cleanup
supported/implemented offline; device internal UNKNOWN; device stop NOT
live-proven).

**Test:** aggiunti 7 test environment-independent su `run()` pubblico (arm-only x3,
first-image success x1, first-image failure x1, `0x22` policy x2). Totale D263
27 PASS. D260 pertinenti falliscono solo per limite ambientale Cloud
(OpenSSL-PSK assente), non per regressione D263.

**File live-critical modificati dal correttivo:** solo `core/persistent_runtime.py`
(`1a731cda…`→`36963ce7…`); `core/runtime_transport.py` e `core/fdt_lifecycle.py`
invariati. Nessun launcher/operator-kit modificato.

**Esito:** `D263_CORRECTIVE = PASS`; `D263_HARDWARE_ACTION_COUNT = 0`;
`D263_READY_FOR_LIVE_REVIEW = false`; `D263_READY_FOR_LIVE = false`;
`D263_LIVE_EXECUTION = NOT_PERFORMED`. Nessuna autorizzazione live concessa né
consumata.
