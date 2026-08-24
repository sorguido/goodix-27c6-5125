# D263/01 — bootstrap, post-arm order e policy fisica `0x22`

**AI esecutrice:** Hy3 Free / Code Cloud
**Reasoning:** HIGH
**Milestone:** D263 (unico)
**Esecuzione:** OFFLINE, STRICTLY NO-USB, NO-sudo, NO-PSK/OTP/secret, NO-flash, NO-live.
**Risultato:** `PASS_PRIMARY_EVIDENCE_CLOSED` (trace ricostruito da evidenza primaria target-specific).

## Fonti primarie (hash-gated)

| Artefatto | Hash SHA-256 | Ruolo |
|---|---|---|
| `analysis/D230/work/GoodixExport/rilevamento.pcapng` | `50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b` | Capture APP12509 cold-attach, unica lifecycle con finger-down catturata |
| `analysis/D230/tools/offline_census.py` | — (decoder riusato) | Decodifica USBPcap + A0 inner-frame |
| `analysis/D252/d252_fdt_capture_audit.py` | — | Validazione primaria del capture e degli anchor di pacchetto |
| `Goodix 27c6 5125 manuale tecnico.md` | canonico | Stato tecnico |

La capture D255 (`captures/D255_…`, `VALID_ZERO_FINGER`) **non** contiene il
sottoalbero post-arm: `FINGER_DOWN_IRQ_COUNT_IN_OPERATOR_WINDOWS=0`,
`POST_IRQ2_0x22_COUNT_IN_OPERATOR_WINDOWS=0`. Pertanto il tratto
`final 0x32 → IRQ 0x0002 → 0x22 [01 00] → first image` è ricostruito dalla
capture primaria `rilevamento.pcapng`, non da D255.

## TARGET_OBSERVED_ORDER

Sequenza osservata (indici pacchetto zero-based, capture `rilevamento.pcapng`):

1. **FDT arm `0x32`** — OUT @220, corpo `08 01 || 80ac80bd80a380b180a680b2 || ts16le`,
   frame logico A0 = 24, submission fisica OUT = 64 (tail zero).
   ACK device→host @223: echo `0x32`, status `0x01`.
2. **IRQ finger-down** — device→host @225: control `0x32`, **valore IRQ `0x0002`**,
   wrapper `3f 00 d5 00 ee 00 c8 00 ba 00 c5 00 d2 00` (field aggiuntivo dopo il
   valore 16-bit little-endian `02 00`).
3. **Comando host post-IRQ `0x22`** — OUT @227, corpo esatto `01 00`,
   frame logico A0 = **10**, submission fisica OUT = **64**.
   ACK device→host @229: echo `0x22`, status `0x01`.
4. **Prima immagine** — device→host @231: outer `0xB0`, **transport TLS**
   (record prefix `17 03 03`), frame logico = **7726**, lunghezza fisica IN = 7726.

Sottoalbero immediatamente successivo (corrobora la chiusura del ciclo):
`0x34`(arm finger-up)@233 → ACK → IRQ `0x0200`(finger-up)@237 → `0x20 [01 00]`@238
→ ACK → seconda immagine B0/TLS@243 → `0x50`@244 → … → **final `0x32`@251** → ACK@253.

## MINIMUM_CAUSAL_REQUIREMENT

La capture prova l'**ordine** `0x32(arm,ACK) → IRQ0x0002 → 0x22[01 00](ACK) →
first image`. **Non** prova che `0x22` sia l'unico comando necessario, né che
l'IRQ finger-down richieda causalmente `0x22`: prova solo che, nella singola
lifecycle APP12509 catturata, questo è l'ordine esatto emesso dallo stack OEM.
La causalità non è stabilita da questo trace da solo (coerente con AGENTS §14:
osservato ≠ causale).

## Derivazioni meccaniche (richieste dal prompt)

- **Richiesta/ACK finale `0x32`:** OUT@220 / ACK@223 echo `32` status `01`
  (e, a chiudura, OUT@251 / ACK@253).
- **Wrapper/valore IRQ finger-down `0x0002`:** @225, valore `0x0002`,
  wrapper `3f00d500ee00c800ba00c500d200`.
- **`0x22` body `[01 00]`:** OUT@227.
- **Lunghezza logica A0:** 10. **Lunghezza fisica OUT:** 64.
- **Byte fuori dalla lunghezza dichiarata:** 54 byte (offset fisici 10–63);
  gli unici 6 non-zero sono a offset **40–45** = `cb f2 e2 be fb 7f`
  (staging/transport residue, identico a `0x36`/`0x20`).
- **ACK echo/status/order:** `0x22` echo `22`, status `01` (@229), subito dopo
  l'OUT@227 e prima della prima immagine.
- **Prima immagine:** outer `0xB0`, **TLS** (`17 03 03`), dimensione osservabile
  7726 byte. Nessun frame A0 "immagine" precede il B0: il comando `0x22` è
  seguito direttamente dal bulk-data B0/TLS.
- **Frame/eventi intermedi:** vedi sottoalbero `0x34 → IRQ0x0200 → 0x20 →
  seconda immagine` in `D263_01_post_arm_order.json`.
- **Numero occorrenze `0x22` nel primary corpus:** **1** OUT (`rilevamento.pcapng`,
  @227); 0 IN. (D255 zero-finger: 0. Issue #63 esterno: 21/21 — solo
  corroborazione, non autorità primaria APP12509.)

## Taxonomy `0x22`

**`PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY`**

Il post-arm order, ACK/echo/status e la policy fisica fixed-64 di `0x22` sono
**direttamente osservati** nella capture primaria APP12509. Il live proof D262
copre **solo** il percorso FDT-arm
`0x36,0x50,0x36,0x82,0x20,0x36,0x32` (STOP_AFTER_FDT_ARM_ACK); **non** raggiunge
il sottoalbero finger-down / `0x22` / immagine. Dunque `0x22` è
`PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY`, **non** live-proven/accepted.

## Modello Phase 2 `0x22`

**`logical exact A0 -> physical fixed64 -> deterministic zero-fill outside declared length`** — **CONFERMATO** sul primary:

- logical A0 = 10; physical OUT = 64; 54 byte fuori frame;
- determinismo: gli unici 6 byte non-zero (offset 40–45 = `cb f2 e2 be fb 7f`)
  sono staging residue costante, identica a `0x36`/`0x20`, non payload.

La conferma del modello Phase 2 è lecita perché derivata dalla stessa capture
primaria `rilevamento.pcapng` già hash-gated, non da inferenza esterna.

## Residui / blocker

- Causalità (IRQ2 ⇒ `0x22` necessario) non provata da questo trace.
- `0x22` non ancora live-proven (D262 si ferma a FDT arm).
- Restore/cancel device-side post-FDT e lifetimes dell'arm restano aperti
  (vedi D252/D253/D255): fuori scope di questo sottostep.

## Artefatti prodotti

- `analysis/D263/d263_01_0x22_evidence_audit.py` — hash-gate + metadati sanitizzati.
- `analysis/D263/D263_01_post_arm_order.json`
- `analysis/D263/D263_01_0x22_physical_policy.json`
- `analysis/D263/D263_01_report.md`
- `analysis/D263/D263_workflow_state.json`

Nessun ZIP (intermedio D263).
