# D263/05 — Phase 2 support primitives: lifecycle + transport

## Risultato

`PASS_SUPPORT_PRIMITIVES_IMPLEMENTED`. Gate (Phase1 READY + step04 contract) superato.
Implementati SOLO i support primitives; il coordinator (`PersistentRuntimeCoordinator`)
**non** è stato esteso (rimandato a step 06). Nessuna patch runtime oltre agli import
indispensabili (zero import aggiunti nel coordinator).

## Modifiche (prima/dopo hash)

### `core/fdt_lifecycle.py`
- `before`: `2edbec9e…75e1c8`
- `after`:  `2aac7422…93a33a`
- `COMMAND_TIMEOUT_MS`: aggiunto `0x22: 2000`.
- `FdtLifecycle.__init__`: aggiunto `self.image_command_attempt_count = 0`.
- `post_irq2_image_command`: guard one-shot (secondo tentativo → `fail_closed` +
  `InvalidTransition`); niente re-arm retry.
- `cancel_pending_receive`: `_require` accetta ora anche `FIRST_IMAGE_RECEIVED`
  (cleanup host terminale post-first-image per la decisione step 03).

### `core/runtime_transport.py`
- `before`: `cbbb0b68…be91ea`
- `after`:  `2930aa57…3e38d`
- `fdt_a0_policy`: `0x22` aggiunto all'allowlist → `ABSTRACT_LOGICAL_ONLY`
  (**non** etichettato live-proven; nessun tail inventato).
- `operational_fdt_a0_policy`: `0x22` aggiunto → `FIXED64_ZERO_TAIL_D261_CANDIDATE`
  (candidato deterministico, zero-fill; non provato live). Fail-closed su
  logical length/body/padding inatteso via `materialize`.

### `tests/test_d263_phase2_support_primitives.py` (nuovo)
12 test deterministici, dati sintetici, tutti OK. Coprono: valid transition,
one-shot `0x22`, second attempt rejected, wrong-order/state rejected, terminal
transition semantics, prohibited commands unreachable, physical frame
construction, deterministic tail, `0x34`/`0xA2`/`0x70` rejected.

## Invarianti preservate
zero `0x34`, zero `0x20` post-image, zero re-arm, zero `A2`/`0x70`, zero retry,
zero persistent-write, nessun device cleanup command inventato, coordinator
invariato (`8e448caa…0df12c`).

## Artefatti
`analysis/D263/`: `D263_05_change_summary.json`, `D263_05_test_results.json`,
`D263_05_report.md`, `D263_workflow_state.json` aggiornato. Nessun ZIP.
