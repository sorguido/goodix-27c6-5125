# D243 — regressione E4 e split A0/B0

## Esito

D243 ha verificato la copia locale primaria del report live D242, chiuso il
gate di integrità del baseline, isolato un solo candidato causale pre-E4 e
implementato lo split minimo richiesto. Nessun hardware reale, secret reale o
handshake TLS reale è stato usato.

La run D242 è osservata come timeout al primo E4: un comando, un open USB,
nessun frame completo IN, nessun binding E4 e nessun TLS/pacing. Cleanup,
zeroizzazione, restore e reseal risultano riusciti. La directory root-only dei
risultati non era leggibile senza privilegi; la copia esportata dal workflow,
`analysis/D242/D242_operator_live_stdout.json`, è JSON valido, ha tutti i campi
vincolanti e SHA-256
`1d9c2c736a2b8939855a184e350ea2ecaa914921536ae2a2d616130a166eb7e7`.

## Baseline e patch

Prima della modifica D243 gli hash sealed erano:

| Path | Expected D242 | Actual | Stato |
| --- | --- | --- | --- |
| `src/goodix5125_d233_backend.py` | `c072db52c29a9e22dc597e53743820217077e5373bafb48cadc69cbb0e90fcef` | uguale | MATCH |
| `src/goodix5125_d235_entrypoint.py` | `6cd9fd3796ded831b0c70877282807c6a423d39f4ee42b8fd2593fe1b4908993` | uguale | MATCH |

Gli offset D242 `+1` e `-9` derivano dalle coordinate numeriche stale negli
hunk: il context trovava comunque l'unico blocco corretto. Hash pre-applicazione
e reverse byte-exact confermano che non fu usato un baseline diverso. La patch
D243 è costruita sul baseline sealed D243 corrente e il test apply/reverse
richiede esplicitamente assenza della parola `offset` nell'output di `patch`.

## Correzione e scope epistemico

- A0 usa chunk logici massimi da 64, ultimo OUT corto, completion esatta del
  chunk e nessuna tail aggiunta: semantica D241 live-proven.
- B0/TLS conserva staging fisico da 64, tail deterministicamente zero e
  completion esattamente 64.
- `B0TlsBridge` conserva 10 ms dopo ciascun record server-side e non introduce
  pacing nelle fasi A0.
- Wrapper, declared length o tag non classificabili falliscono chiusi; retry è
  zero.

La capture D175 osserva submit host-side A0/B0 da 64 byte, ma questo non prova
equivalenza device-side di una tail A0 zero-filled. Il suo contenuto rilevante
resta non noto. La claim comune D242 è ritirata:

```text
D242_FIXED64_SCOPE_A0=FALSIFIED_BY_LIVE_E4_REGRESSION
D242_FIXED64_SCOPE_B0=OFFLINE_VERIFIED_NOT_YET_LIVE_CONFIRMED
```

## Test e durability

Il test diretto prende il frame E4 da `expected_request_frames()`, preserva i
byte logici e il risultato di `parse_a0()`, e asserisce esplicitamente che la
submission sia identica al frame e abbia lunghezza diversa da 64. L'intera
sequenza `E4/A2/82/A6/A2/70/80x4/90/D1` usa la segmentazione A0 D241.

ServerHello produce `64|64`; ServerHelloDone produce `64`. Sono verificate tail
zero, completion corta fail-closed e due pause da 10 ms. La closure usa anche
un peer TLS OpenSSL esclusivamente sintetico per binding/ownership e safety.

Nel timeout sintetico al primo E4 il runtime abort completa cleanup e
zeroizzazione; il checkpoint atomico viene pubblicato con
`report_publish_count=1` prima del restore dei segnali. Dopo il restore viene
pubblicato il report finale con `report_publish_count=2`. Release, close ed exit
USB sintetici avvengono una volta ciascuno. Il framework durevole esistente è
stato riusato, senza crearne uno parallelo.

## Confine corrente

Il server flight B0 fixed-64 con pacing 10 ms non è ancora validato sul device:
D242 non lo ha raggiunto. D243 è pronto solo per review umana e una successiva
validazione live single-shot separatamente autorizzata. Il ramo live D243 è
`NOT_EXECUTED`.
