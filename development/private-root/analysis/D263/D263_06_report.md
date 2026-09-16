# D263/06 — Phase 2 PersistentRuntime first-image integration

## Risultato

`PASS_RUNTIME_INTEGRATION`. Gate (Phase1 READY + step05 PASS) superato. Esteso
il production-shaped `PersistentRuntimeCoordinator` con il minimo percorso
offline candidato:

`D262 arm complete -> bounded IRQ2 wait -> exactly-one 0x22 -> retained TLS
first-image B0 -> canonical parser/codec -> FIRST_IMAGE_RECEIVED -> bounded
host/TLS/USB cleanup -> stop`.

## Modifica (`core/persistent_runtime.py`)
- `before`: `8e448caa…0df12c` — `after`: `c266ef8a…3963af`
- Nuovo metodo `_run_first_image_terminal()` riusa `build_finger_image`,
  `parse_image_payload`/`decode_image_record` (codec canonico), e la retained
  TLS B0 application session (`consume_application_record`). Nessun parser/codec
  duplicato.
- `run()` chiama il nuovo metodo dopo `arm(ts16)`; il check del trace esatto è
  rilassato a: prefisso `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE` + extra esattamente
  `(0x22)` + audit comandi proibiti post-arm (`0x34`/`0x20`/`A2`/`0x70`).
- `RuntimeResult`/`audit()` arricchiti di `irq2_observed`, `image_command_attempt_count`,
  `image_ack`, `first_image_received/validation/raster_shape`,
  `first_image_bytes_persisted`, `terminal_cleanup_completed`.
- Il `finally` esistente (TLS close + secret zeroize + USB release) resta
  exactly-once su ogni failure → cleanup garantito.

## Test (8, tutti OK, dati sintetici)
`tests/test_d263_phase2_first_image_terminal.py` (TLS sintetico: l'env Cloud
non ha OpenSSL PSK; il path di produzione `Tls12PskServerSession` è validato da
`test_d259` in un env con OpenSSL-PSK). Copertura: happy-path completo; wrong
IRQ; timeout; wrong ACK; malformed B0; CRC/image failure (plaintext azzerato);
prevenzione second command (one-shot 0x22); nessun pixel sensibile persistito;
one-session/one-handshake/no-reopen.

## Invarianti preservate
one USB/TLS session+handshake, zero second secret/USB reopen/retry, same
retained TLS session, esattamente un `0x22`, no `0x34`/`0x20`-post/re-arm/
`A2`/`0x70`/persistent-write, first-image bytes non persistiti (plaintext
azzerato, raster solo in memoria, mai in report/bundle), fail-closed su
IRQ/ACK/B0/image mismatch, cleanup eseguito anche su failure.

## Artefatti
`analysis/D263/`: `D263_06_runtime_integration_summary.json`,
`D263_06_test_results.json`, `D263_06_report.md`, `D263_workflow_state.json`
aggiornato. Nessun ZIP.
