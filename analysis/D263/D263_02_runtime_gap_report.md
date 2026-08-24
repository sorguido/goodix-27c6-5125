# D263/02 — retained TLS e pipeline first-image

**AI esecutrice:** Hy3 Free / Code Cloud
**Reasoning:** HIGH
**Milestone:** D263 (unico)
**Gate iniziale:** `D263_workflow_state.json` contiene `completed_substeps: ["01"]` e
`outcome_01: PASS_PRIMARY_EVIDENCE_CLOSED` → coerente. Procedo con 02.
**Esecuzione:** OFFLINE, strictly no-USB/no-sudo/no-secret/no-runtime-patch. Solo audit.

## Obiettivo

Auditare l'architettura esistente per:

`encrypted first-image B0 -> retained TLS -> Goodix payload -> image record -> CRC -> packed12 -> 80x64`

senza modificare runtime live-critical.

## Retained TLS (mappa delle 6 domande)

Vedi `D263_02_retained_tls_map.json` (citazioni file:line). Sintesi:

1. **Stessa sessione TLS da handshake → baseline B0 → 0x32 → IRQ2 → 0x22 → first-image B0?**
   Sì *per progetto*, ma **non cablata nel coordinator**. `Tls12PskServerSession`
   (`core/tls_b0.py:152`) è creata una sola volta
   (`core/persistent_runtime.py:207`), con `server_session_object_count=1`,
   `psk_context_provisioning_count=1`, `handshake_count→1`. L'adapter
   `MemoryBioApplicationSessionAdapter.consume_application_record`
   (`core/tls_b0.py:109`) incrementa `application_record_count` e può essere
   chiamato più volte sulla **stessa** sessione/SSLObject/BIO: il baseline B0 è
   già consumato come application record #1
   (`core/persistent_runtime.py:226-227`). Il primo B0 immagine sarebbe il
   record #2 sulla stessa sessione — **ma** `PersistentRuntimeCoordinator.run()`
   termina a `machine.arm(ts16)` (`core/persistent_runtime.py:232`) e il
   `finally` chiude TLS subito dopo (`core/persistent_runtime.py:261-263`),
   prima di qualsiasi IRQ2/0x22/immagine.

2. **Proprietario dell'application session:** `Tls12PskServerSession` possiede
   l'adapter; `PersistentRuntimeCoordinator` ne detiene il riferimento.

3. **Chi consuma/decripta B0:** `B0ApplicationConsumer.consume`
   (`core/tls_b0.py:287`) → `session.consume_application_record`.

4. **Chi valida/parse la prima immagine:** `parse_image_payload`
   (`core/post_d4.py:347`) → `decode_image_record` →
   `src/goodix5125_cleanroom.decode_record`. Richiede i byte **decriptati**
   (quindi prima il consumo B0 su TLS). Nel path coordinator il primo B0
   immagine non è mai passato al consumer → `parse_image_payload` non viene
   mai invocato su di esso.

5. **Glue mancante in `PersistentRuntimeCoordinator`:** la fase post-arm è
   assente. `ExactFreshFdtBootstrapMachine` non espone alcun metodo
   post-IRQ2/receive-first-image (finisce a `arm()`, `core/fdt_lifecycle.py:673`).
   Mancano: wait IRQ finger-down via `event_source`, submit di `build_finger_image()`
   (0x22), consumo del primo B0 su `self.tls_session.application_session`,
   chiamate a `lifecycle.post_irq2_image_command()` e `lifecycle.first_image_received()`,
   e rinvio di `tls_session.close()` nel `finally`. `FdtLifecycle` ha già gli
   stati/metodi (`FDT_ARMED_WAIT`, `FIRST_IMAGE_RECEIVED`, `post_irq2_image_command`,
   `first_image_received`) — manca solo l'orchestrazione.

6. **Seconda TLS session/server/handshake/provisioning/reopen?** **NO.**
   Una sola sessione retainita basta (baseline + prima immagine sullo stesso
   oggetto). L'audit del coordinator riporta già
   `second_server_session_created=False`, `second_psk_provisioning`=
   `(psk_context_provisioning_count != 1)`, `tls_uses_same_secret_boundary_object=True`,
   `transport_reopen_after_tls = (session_count != 1)`.

**Valutazione redesign:** il layer TLS già supporta una singola sessione retainita
che attraversa handshake→baseline→0x32→IRQ2→0x22→first-image. Il gap è
orchestration glue (una fase post-arm + un metodo macchina), **non** un redesign
TLS/transport. Pertanto **NON BLOCKED** su redesign: è un gap di estensione,
registrato per lo step 03.

## Pipeline immagine (conferma)

Vedi `D263_02_first_image_pipeline.json`.

- **Parser canonico:** `core/post_d4.decode_image_record` →
  `src/goodix5125_cleanroom.decode_record` (unico codec).
- **Codec canonico:** `src/goodix5125_cleanroom.py`; packed12, 4 campioni/6 byte
  (`decode_group`), `raster_index` column-major.
- **Record 7684 byte:** `RECORD_BYTES=7684` = 7680 packed + 4-byte CRC-32/MPEG-2.
  `parse_image_payload` richiede `len(data)==5+7684`.
- **Numero campioni:** 5120 (= 80×64).
- **Raster 80×64:** `WIDTH=80`, `HEIGHT=64`.
- **CRC:** CRC-32/MPEG-2 (`crc32_mpeg2`), trailer 4 byte; fallimento →
  `ValueError('CRC mismatch')` → `ImageCrcError` → **fail-closed** (nessun accept,
  nessun retry, nessuna cache write).
- **Test esistenti:** `tests/test_cleanroom.py` (round-trip + CRC mismatch),
  `tests/test_d249_post_d4.py` (`FIRST_IMAGE_RECEIVED` via `FirstImageMachine`),
  `tests/test_d257_fdt_candidate.py` (`test_target_irq2_0x22_exactly_once_and_first_image`).
  Tutti con fixture sintetiche, nessun dato biometrico.
- **Assenza decoder duplicati:** un solo codec packed12+CRC in
  `src/goodix5125_cleanroom.py`; `core/post_d4.decode_image_record` è solo un
  wrapper. Nessun secondo decoder nel piano futuro.

## Lifecycle gap (stato di `FIRST_IMAGE_RECEIVED`)

- `FdtLifecycleState.FIRST_IMAGE_RECEIVED` esiste (`core/fdt_lifecycle.py:52`) ed
  è raggiungibile via `FdtLifecycle.first_image_received()`
  (`core/fdt_lifecycle.py:230`) e via `FirstImageMachine`
  (`core/post_d4.py:419`, fase `FIRST_IMAGE_RECEIVED`).
- **Nel path coordinator di produzione** `FIRST_IMAGE_RECEIVED` **non è mai
  raggiunto**: `ExactFreshFdtBootstrapMachine` (quello usato dal coordinator)
  non invoca mai `post_irq2_image_command()` né `first_image_received()`;
  `PersistentRuntimeCoordinator.run()` si ferma a `machine.arm(ts16)` e chiude
  TLS nel `finally`.
- **Transizione terminale assente:** `FDT_ARMED_WAIT → FIRST_IMAGE_RECEIVED`
  (via IRQ2 → 0x22 → immagine) non è cablata nel coordinator. La chiusura
  corrente è `STOP_AFTER_FDT_ARM_ACK` (coerente con D262). Non si decide ora se
  sia safe: quello è lo step 03.

## Esiti machine-readable

- `D263_02_retained_tls_map.json` → `redesign_assessment.outcome = PASS_AUDIT_NOT_BLOCKED`
- `D263_02_first_image_pipeline.json` → codec canonico unico confermato, CRC fail-closed.
- Nessun runtime modificato; nessun patch; nessun ZIP (intermedio D263).

## Artefatti prodotti

- `analysis/D263/D263_02_retained_tls_map.json`
- `analysis/D263/D263_02_first_image_pipeline.json`
- `analysis/D263/D263_02_runtime_gap_report.md`
- `analysis/D263/D263_workflow_state.json` (aggiornato: `"02"` in `completed_substeps`)
