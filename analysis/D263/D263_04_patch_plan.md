# D263/04 — Phase 2 design contract e patch plan

## Stato gate

`D263_PHASE1_READY_FOR_PHASE2_OFFLINE_RUNTIME_INTEGRATION = true` → patch
plan definito, **NESSUNA patch runtime applicata in questo substep**.

## Contratto minimo (riassunto)

`existing D262 path -> final FDT arm 0x32 ACK -> bounded wait IRQ 0x0002 ->
exactly one 0x22 [01 00] -> retained TLS receives first B0 -> parser/codec
canonico valida+decodifica -> FIRST_IMAGE_RECEIVED -> bounded host-only
terminal cleanup -> stop`.

Invarianti: one USB session; one TLS server/session + one handshake; zero
second secret provisioning; zero USB reopen; zero retry; zero A2/`0x70`;
zero `0x34`; zero `0x20` post-image; zero re-arm; zero persistent-write;
first-image bytes non persistiti; fail-closed su mismatch.

## Blocchi già esistenti (riuso, nessun duplicato)

- `core/post_d4.py`: `build_finger_image()` (0x22 [01 00], riga 257),
  `parse_fdt_event()` (irq==2, riga 273), `parse_image_payload()`/`decode_image_record()`
  (codec canonico, righe 336/347), `FirstImageMachine` (test/offline, riga 419).
- `core/fdt_lifecycle.py`: `post_irq2_image_command()` (222), `first_image_received()`
  (230), `cancel_pending_receive()` (234), `terminal_stop()` (251).
- `core/tls_b0.py`: `Tls12PskServerSession.consume_application_record` /
  `B0ApplicationConsumer` (252/287) — sessione retainita unica, multi-application-record supportato (audit D263/02).

Il gap (D263/02) è solo nel `PersistentRuntimeCoordinator.run()`, che si ferma
a `machine.arm(ts16)` (riga 232) e poi chiude TLS nel `finally`.

## Patch plan (mappa file/metodi)

### File A — `core/runtime_transport.py` (step 05, <15 min)
- **pre-state**: `fdt_a0_policy`/`operational_fdt_a0_policy` allowlist
  `{0x20,0x32,0x36,0x50,0x82}`; `0x22` non ammesso → submit 0x22 fallirebbe.
- **modifica minima**: aggiungere `0x22` a entrambi gli allowlist (è già in
  `SAFE_DEVICE_COMMANDS` e `ALLOWED_COMMANDS`). Opzionale: costante
  `IMAGE_FINGER_0x22_A0_POLICY`.
- **invarianti**: `0x34`/`0xA2`/`0x70` restano NON ammessi; nessun segreto/USB.
- **test**: `fdt_a0_policy(0x22, t)` non solleva; `fdt_a0_policy(0x34, t)` solleva ancora.
- **rischio**: basso.

### File B — `core/fdt_lifecycle.py` (step 05, <15 min)
- **pre-state**: `COMMAND_TIMEOUT_MS` senza `0x22`; `cancel_pending_receive()`
  richiede `FDT_ARMED_WAIT` (fallirebbe dopo `first_image_received`).
- **modifica minima**:
  1. aggiungere `0x22: 2000` a `COMMAND_TIMEOUT_MS`;
  2. `cancel_pending_receive()` → `_require(FDT_ARMED_WAIT, FIRST_IMAGE_RECEIVED)`.
- **invarianti**: nessun `0x34`/persistente/recovery raggiungibile (già in
  `_record`); niente re-arm (arm_fdt blocca retry implicito; non entriamo in
  `SESSION_REENTRY`).
- **test**: dopo `first_image_received()`, `cancel_pending_receive()` non solleva;
  `0x22` presente in `COMMAND_TIMEOUT_MS`.
- **rischio**: basso.

### File C — `core/persistent_runtime.py` (step 06, <15 min) — principale
- **pre-state**: `run()` termina a `machine.arm(ts16)` (232) + check
  `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE` (236) + `return result`; `finally`
  chiude TLS/transport/secret. `event_source` già cablato alla macchina.
- **modifica minima** (inserire dopo `machine.arm(ts16)`, prima del check):
  1. `event_frame = self.event_source.wait_event(IRQ2_TIMEOUT); parse_fdt_event→irq==2` (fail-closed);
  2. `self.lifecycle.post_irq2_image_command(); self.transport.submit(build_finger_image(), fdt_a0_policy(0x22, T0x22)); ack=self.transport.receive(T0x22); parse_ack(ack,0x22)` (ACK-optional, fail-closed);
  3. `image_frame=self.transport.receive(TB0); kind,body=parse_outer(image_frame)` (kind==TLS); `plaintext=self.tls_session.application_session.consume_application_record(body)`; `raster=parse_image_payload(bytes(plaintext))`; poi **zeroizza plaintext**;
  4. `self.lifecycle.first_image_received()`;
  5. `self.lifecycle.cancel_pending_receive(); self.lifecycle.terminal_stop()`;
  6. rilassare il check a **prefisso** `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE` +
     audit comandi proibiti (nessun `0x34`/`0x20`/re-arm/`A2`/`0x70`/persistente;
     unico comando aggiuntivo permesso = `0x22`);
  7. `RuntimeResult` arricchito: `first_image_received=True`, `first_image_raster_shape=(80,64)`, `post_arm_trace_suffix=[0x22]`.
  - import aggiuntivi: `build_finger_image`, `parse_fdt_event`, `parse_image_payload` da `core.post_d4` (gli altri già importati).
- **invarianti**: una sola `arm` + un solo `0x22`; nessun `0x34`/`0x20`/re-arm/`A2`/`0x70`; bytes prima immagine non persistiti (plaintext azzerato, raster solo in memoria); fail-closed su qualsiasi mismatch → `finally` esegue cleanup exactly-once + `lifecycle.fail_closed`.
- **test**: nuovo `tests/test_d263_phase2_first_image_terminal.py` con
  `ScriptedTransport`/`EventSource` mock: assert esattamente un `0x22`, raster
  80x64 decodificato, lifecycle `TERMINAL_STOPPED`, `device_command_trace ==
  EXACT...+(0x22)`, `tls.handshake_count==1`, `tls_close_count==1`, secret
  zeroized, zero persistent-write; e fail-closed su IRQ/ACK/TLS/immagine errati
  (cleanup comunque eseguito).
- **rischio**: medio (tocca coordinator live-critical) — mitigato da riuso di
  primitive già auditate, single-use runtime, fail-closed, cleanup exactly-once.

## Ordine di patch (step 05/06, ciascuno <15 min)
- **Step 05**: File A + File B + relativi unit test; `pytest` solo su questi.
- **Step 06**: File C (coordinator) + nuovo integration test
  `tests/test_d263_phase2_first_image_terminal.py`; `pytest` su quest'ultimo.

## File riusati NON patchati (hash in D263_04_live_critical_prechange_hashes.json)
`core/post_d4.py`, `core/tls_b0.py`, `src/goodix5125_cleanroom.py` (codec),
`core/usb_runtime.py` (backend USB reale), `core/protected_runtime.py`
(guardrail), `tools/d261_live_fdt_arm_once.py` (launcher live),
`src/goodix5125_d235_entrypoint.py` (entrypoint).
