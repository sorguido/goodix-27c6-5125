# D263/03 — terminal stop dopo la first image e gate Phase 1

## Esito

`FIRST_IMAGE_TERMINAL_STOP = EVIDENCE_SUPPORTED_BUT_DEVICE_INTERNAL_STATE_UNKNOWN`
`D263_PHASE1_READY_FOR_PHASE2_OFFLINE_RUNTIME_INTEGRATION = true`

## Confronto con il ciclo positivo

Ciclo positivo documentato (PRIMARY `rilevamento.pcapng`, in `workflow_state.observed_order`):

```
0x32 -> IRQ 0x0002 -> 0x22 -> first image
     -> 0x34 -> IRQ 0x0200 -> 0x20 -> 2nd image -> 0x32 (re-arm)
```

Candidato terminale D263/03:

```
0x32 -> IRQ 0x0002 -> 0x22 -> first image -> HOST/TLS/USB CLEANUP -> STOP
```

Lo stack Windows usa `0x34` (= **arm finger-up**, manuale righe 170-171) per
abilitare il rilevamento del dito successivo e poi `0x20` per la seconda
immagine, infine re-arm. Questo è multi-enrollment: **non dimostra** che
`0x34`/`0x20`/re-arm siano richiesti per uno stop host dopo la *prima* immagine.

## Host cleanup semantics — VERIFICATO fattibile/implementato

| Azione | Stato | Evidenza |
|---|---|---|
| cancel pending receive | VERIFIED | D255/D256: pending IN cancellato a frame 218, zero packet residui (manuale 749-752) |
| TLS close | VERIFIED | `core/persistent_runtime.py` finally `tls_session.close()`; audit D263/02 |
| USB release/close | VERIFIED | cleanup/restore/reseal riusciti in D232-D262 (manuale 378-389, 1377-1387) |
| restore fprintd | VERIFIED exactly-once | manuale 912-928, 1377-1387 |
| nessun comando Goodix extra | VERIFIED | D255/D256: intervallo cancel senza packet target |

## Device internal state — UNKNOWN (taxonomy)

- `fdt/finger post-image`: **UNKNOWN** (D252 BLOCKED, nessun live post-first-image).
- `necessità di 0x34`: osservato solo come *arm finger-up*; necessità NON provata;
  INFERITO non richiesto per disconnect host-side (D255/D256 quiescono senza restore device).
- `tolleranza disconnect USB/TLS` (device): **UNKNOWN**; quiescenza host/bus **VERIFIED**.
- `recovery cold start`: **INFERRED OK** (D256: nuovo `0x32` accettato senza restore USB).
- `restore command device-side`: **UNKNOWN**; A2/`0x70` NON osservati come restore FDT.

## Classificazione e gate

Una sola: `EVIDENCE_SUPPORTED_BUT_DEVICE_INTERNAL_STATE_UNKNOWN`.

Lo stop è **supportato lato host** (evidenza primaria + D255/D256 + audit TLS
retainita). Lo stato interno device resta sconosciuto ma **non contraddice**
l'evidenza. Nessun blocco per l'integrazione OFFLINE.

`D263_PHASE1_READY_FOR_PHASE2_OFFLINE_RUNTIME_INTEGRATION = true`: autorizza
solo design/implementazione OFFLINE del candidato bounded (cablare path
post-arm first-image + cleanup host esattamente-once + STOP), **NON** live
review né live execution.

## Artefatti

`analysis/D263/`: `D263_03_terminal_boundary_evidence.json`,
`D263_03_terminal_boundary_decision.json`, `D263_03_phase1_decision.json`,
`D263_03_report.md`, `D263_workflow_state.json` (aggiornato con gate Phase 2).

Nessun ZIP.
