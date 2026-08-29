# D278/03 post-live corrective — riconciliazione policy ACK

## Esito e fatti durevoli della singola run

```text
OUTCOME=READY_FOR_AI_PM_REVIEW
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_AND_OFFLINE_LIVE_CRITICAL_CORRECTIVE_COMPLETED
LIVE_CRITICAL_BASELINE=843290e7790d7930bb136d91510a3db9d3a97027
REVIEWED_MAIN_AT_EXECUTION=a38fd26301069e4b2119e2d8cb342e0bcf8926a3
LAUNCHER_SHA256=a48488b0817256d896a77bf2ac037ff5bef10524dd9c018f31d1c2bb5d3a251a
D278_03_LIVE_RUN_COUNT=1
D278_03_LIVE_AUTHORIZATION_CONSUMED=true
CURRENT_LIVE_AUTHORIZED=false
A8_CURRENT_RUN=PASS
E4_OUT_CURRENT_RUN=SENT
E4_ACCEPTED_ACK_CURRENT_RUN=false
TLS_CURRENT_RUN=NOT_REACHED
```

La run autorizzata ha completato A8, inviato E4 e terminato sul primo frame IN
di E4. Lo provano `command_count=2`, `ack_count=1`,
`typed_response_count=1`, tre completion IN e due completion OUT. Il log
redatto non registra lo status dell'ACK E4: `0x07` è la spiegazione più
probabile, ma non un'osservazione diretta della run corrente. La telemetria
canonica, senza payload sensibili, è in
`D278_03_native_secure_session_live_result_20260829.json`.

Il cleanup ha chiuso correttamente l'unica sessione USB: open, claim, release e
close sono uno; max IN e OUT concorrenti sono uno; retry, reopen, reset e
scritture persistenti sono zero. TLS, D4, application data, finger e image non
sono stati raggiunti; il secret project-owned è stato azzerato e il backend è
stato drenato prima del cleanup terminale.

## Contraddizione e autorità ACK

D278/01 aveva implementato in C `0x01|0x07` per A8, ma soltanto `0x01` per
E4..CONFIG_90. Questa policy diverge dalla successiva autorità canonica D238 e
dal modello Python corrente. D236 fornisce la catena causale indipendente:

- run 1: E4 termina con `unexpected_ack`;
- dopo l'estensione storica di E4 a `0x01|0x07`, run 2 raggiunge `E4_MATCH` e
  termina poi su A2;
- run 3 osserva direttamente per A2_1 un frame A0, control `0xb0`, body di due
  byte, echo `0xa2` e status `0x07`.

D238 conserva `0x01` dalla capture Windows recuperata per tutte le fasi con
ACK e ammette come soli status di successo `0x01` e `0x07`. `0x07` è osservato
live direttamente soltanto per E4 e A2_1; sulle fasi successive è una bounded
transport/session inference, tranne A2_2 che riusa il control A2 live-provato.
Il contratto storico D232 con wording solo `0x01` resta immutato come evidenza
storica, ma è superato da D238 esclusivamente per la semantica della policy ACK.

| Fase | Control | Windows/capture | Linux live diretto | Inferenza bounded | Python corrente | C pre-corrective | D278/01 | Correttivo | Confidenza | Ragione |
|---|---:|---:|---:|---|---|---|---|---|---|---|
| A8 | `0xa8` | n/d in D238 | `0x07` (D245) | nessuna | fuori `PHASE_RESPONSE_POLICIES` D232 | `0x01|0x07` | `0x01|0x07` | `0x01|0x07` | alta | D245 live diretto; nessuna divergenza della policy C |
| E4 | `0xe4` | `0x01` | `0x07` | nessuna | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | alta | D236 live diretto e causalità run1→fix→MATCH |
| A2_1 | `0xa2` | `0x01` | `0x07` | nessuna | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | alta | diagnostica D236 run3 diretta |
| CHIP_82 | `0x82` | `0x01` | non osservato | `0x07` session/transport | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | medio-alta | modello bounded D238, forma tipata invariata |
| OTP_A6 | `0xa6` | `0x01` | non osservato | `0x07` session/transport | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | medio-alta | modello bounded D238, forma tipata invariata |
| A2_2 | `0xa2` | `0x01` | stesso control di A2_1 | `0x07` per control live-provato | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | alta | stesso control `0xa2` della prova live diretta |
| MODE_70 | `0x70` | `0x01` | non osservato | `0x07` session/transport | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | medio-alta | ACK-only, modello bounded D238 |
| DAC_220 | `0x80` | `0x01` | non osservato | `0x07` session/transport | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | medio-alta | ACK-only, modello bounded D238 |
| DAC_236 | `0x80` | `0x01` | non osservato | `0x07` session/transport | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | medio-alta | ACK-only, modello bounded D238 |
| DAC_238 | `0x80` | `0x01` | non osservato | `0x07` session/transport | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | medio-alta | ACK-only, modello bounded D238 |
| DAC_23A | `0x80` | `0x01` | non osservato | `0x07` session/transport | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | medio-alta | ACK-only, modello bounded D238 |
| CONFIG_90 | `0x90` | `0x01` | non osservato | `0x07` session/transport | `0x01|0x07` | `0x01` | `0x01` | `0x01|0x07` | medio-alta | modello bounded D238, forma tipata invariata |
| D1 | `0xd1` | nessun ACK A0 | non osservato | nessuna | B0/TLS diretto | B0/TLS diretto | B0/TLS diretto | invariato, B0/TLS diretto | alta | D238 e sequencer concordano: A0 terminale |

```text
ACK_AUTHORITY_RECONCILIATION=PASS
NATIVE_C_ACK_POLICY_DIVERGENCE=PROVEN
PRIMARY_HYPOTHESIS=CURRENT_NATIVE_C_REJECTED_A_PROVEN_SUCCESS_ACK_CLASS_AT_E4
LIKELY_CURRENT_E4_ACK_STATUS=0x07
CURRENT_RUN_E4_ACK_07_NOT_DIRECTLY_TELEMETRIZED=true
ROOT_CAUSE_CONFIDENCE=HIGH_CAUSAL_HISTORICAL_CORROBORATION_BUT_CURRENT_STATUS_NOT_TELEMETRIZED
```

## Correttivo e osservabilità

Il sequencer C esistente usa ora una tabella phase-aware unica: ogni fase con
ACK ammette esclusivamente `0x01|0x07`; echo esatto e body ACK di esattamente
due byte restano obbligatori. Le fasi ACK+typed richiedono ancora la risposta
tipata valida, quelle ACK-only rifiutano una risposta tipata e D1 continua ad
accettare soltanto B0/TLS. Non sono stati introdotti comandi, retry, reopen o
reset e non sono cambiati PSK, binder/validator E4, CONFIG90, D1 o TLS.

La prima failure protocollare causale viene ora preservata, senza essere
sovrascritta dal cleanup, con fase, classe stabile, outer type, control A0,
echo/status ACK e lunghezza body. Il test sintetico E4 status `0x02` produce
`E4`, `ACK_STATUS_REJECTED`, `0xa0`, `0xb0`, `0xe4`, `0x02`, lunghezza 2.
Questa telemetria è solo strutturale: non contiene PSK, validator E4, OTP,
CONFIG90, materiale biometrico o segreti TLS.

Il diff live-critical è limitato a
`libfprint-driver/goodix_secure_session.{c,h}` per policy e first-failure audit,
`tools/goodix_d278_harness.{c,h}` per propagazione/JSON redatto e ai due test
esistenti `test_goodix_d278_secure_session.c` e `test_goodix_d278_02.c`. Non è
stato creato un secondo sequencer o launcher.

## Verifica host-only

Tutte le suite sono state eseguite senza sensore, store protetto o `sudo`:

- secure-session focalizzata: 11/11 normal e 11/11 ASAN/UBSAN, inclusi E4 e
  A2_1 `0x07`, tutte le fasi `0x01`, status `0x02`, echo/shape/typed errati,
  duplicate, ACK-only e D1/B0;
- D278/02: 62/62 normal e 62/62 ASAN/UBSAN, build live-capable e solo
  `--self-test`; la telemetria sintetica E4 `0x02` è redatta;
- regressioni D276/02: 15/15 normal e sanitizer; D276/03: 8/8 normal e
  sanitizer; D276/04: 5/5 normal e sanitizer; D277: 15/15 normal e sanitizer.

I primi tentativi dei runner Flatpak nel sandbox sono terminati prima della
build per l'indisponibilità ambientale `NETLINK_ROUTE`; gli stessi comandi
host-only sono stati ripetuti fuori sandbox, senza `sudo`, e sono passati. Non
è stato usato `--material-preflight-only` né `--live-exact-secure-session`;
accessi e submit USB reali di questo correttivo sono zero.

## Incertezza residua e gate metodologico futuro

Il correttivo elimina una divergenza provata, ma non trasforma la run fallita
in prova target del secure-session C: E4 accettato e TLS nativo restano non
provati. In particolare, lo status E4 corrente non è recuperabile dalla
telemetria disponibile.

1. **Cosa cambia realmente.** La policy C è riconciliata a D238: uno status di
   successo provato `0x07` non può più essere rifiutato a E4/A2 e la policy
   bounded per fase coincide col modello canonico. La telemetria aggiunta non
   è, da sola, il cambiamento metodologico.
2. **Nuova ipotesi.** D278/03 si è fermato per la divergenza ACK nativa, non per
   un binding E4 autentico errato; col correttivo lo stesso E4 factory-backed
   dovrebbe raggiungere la risposta tipata MATCH e continuare.
3. **Se fallisce ancora a E4.** `NO THIRD EQUIVALENT FULL RUN`: riesaminare
   offline la nuova telemetria strutturale. Qualunque diagnostica successiva
   deve essere progettata, revisionata e autorizzata separatamente.

```text
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
factory_firmware_and_persistent_state_must_remain_untouched
```
