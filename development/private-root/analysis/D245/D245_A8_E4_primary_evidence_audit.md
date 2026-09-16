# D245 — audit primario/canonico A8→E4

## Scope e provenance

La root reale rilevata da `git rev-parse --show-toplevel` è
`/home/guido/Repository/goodix-27c6-5125_private`. Le directory D167–D179 e i
relativi runtime artifact primari non sono presenti nel repository corrente,
che conserva il corpus da D230 in avanti.

```text
D245_D179_PRIMARY_RUNTIME_ARTIFACTS_STATUS=PURGED_UNAVAILABLE_IN_CURRENT_REPOSITORY
D245_D179_HISTORICAL_RECORD_STATUS=CANONICAL_HISTORICAL_LIVE_RECORD_PRIMARY_RUNTIME_ARTIFACTS_PURGED
```

Il record storico canonico D179 conserva la sequenza target-live
`A8_OUT → A8_ACK_IN → A8_RESPONSE_IN → A8_COMPLETE → E4_OUT → E4_ACK_IN →
E4_RESPONSE_IN → E4_COMPLETE`, con 2 OUT, 4 IN, zero retry e cleanup unico.
Non viene riclassificato come evidenza primaria locale verificata.

La policy ACK non si deduce dal solo D179. I record storici canonici D43 e D175
mostrano rispettivamente `B0/A8/01 → A8/17 → GF_ST411SEC_APP_12509\0` e
`B0/A8/07 → A8/17 → GF_ST411SEC_APP_12509\0`. D175 falsifica quindi la
precedente reintroduzione D245 di ACK07 come stato terminale senza response.
Questa provenance resta storica: gli artifact primari D43/D175 non vengono
presentati come nuovamente verificati nel corpus locale corrente.

## Corroborazione locale corrente D230

Le fonti correnti forniscono una corroborazione indipendente sufficiente:

| Evidenza | Risultato |
| --- | --- |
| `D230_windows_capture_opcode_census.csv` | due A8, payload `0000`, framing A0, risposta seguente ACK B0 |
| `rilevamento.pcapng` | due occorrenze byte-exact `a00600a6a803000000ff`; ACK `a00600a6b00300a8014e`; risposta `a01a00baa81700…0047` |
| parser canonico locale | request valida come A0 control A8, body `0000`, lunghezza logica 10 |
| risposta capture | A0 control A8, body esatto `GF_ST411SEC_APP_12509\0` |
| `D230_gfusb_command_builder_inventory.csv` | `GetEvkVersion`, control A8, builder A0 generic |
| `D230_known_read_operations_boundary.csv` | query-only, metadato versione fisso, side effect `none` |
| `D230_definitive_arbitrary_resident_read_audit.md` | A8 fixed version metadata read, non flash/IAP/provisioning/OTP/config/biometria |
| transport audit D230 | bulk OUT `0x01`, bulk IN `0x81`, A0/B0 framing e checksum correnti |

La response canonica ha body di 22 byte: 21 byte ASCII più NUL. Il gate D245
richiede l'intero body, non una sottostringa o una versione “vicina”.

```text
D245_A8_CURRENT_LOCAL_CORPUS_CORROBORATION=PASS
D245_A8_READ_ONLY_CLASSIFICATION=CURRENT_LOCAL_CORPUS_CONFIRMED
D245_A8_WIRE_CONTRACT_CURRENT_CORPUS=CONFIRMED
D245_A8_E4_PRECONDITION_EVIDENCE=HISTORICAL_LIVE_RECORD_CANONICALLY_PRESERVED_AND_CURRENT_CORPUS_CORROBORATED
```

## Typed ACK e boundary

Il contratto è ristretto:

- `B0/A8/01` e `B0/A8/07`: classi ACK empiricamente distinte che autorizzano
  entrambe esattamente una bounded response read tipizzata A8;
- la semantica nominale interna di `0x01` e `0x07` resta ignota; `0x07` è
  `UNKNOWN_STATUS_CLASS_EMPIRICALLY_COMPATIBLE_WITH_RESPONSE`, non failure,
  busy, not-ready, terminal o response-not-authorized;
- altro status: stop fail-closed senza seconda response read;
- echo, wrapper, checksum, frame count o ordine invalido: stop fail-closed;
- `A8_COMPLETE` è obbligatorio prima di `E4_OUT`;
- per entrambi gli status, `A8_COMPLETE` richiede A0/A8 con body esatto
  `GF_ST411SEC_APP_12509\0`;
- qualunque byte residuo dopo ACK+response è un frame stale/unowned e blocca E4.

Il transport restituisce oggetti `bytes` separati e conserva il buffer di
riassemblaggio; D245 verifica che il buffer sia vuoto al boundary, evitando
aliasing e accettazione di un terzo frame coalesced.

## Classificazione epistemica

```text
D245_A8_SEMANTIC_CLASS=TARGET_LIVE_PROVEN_READ_ONLY_PRECONDITION_DISCRIMINATOR
D245_A8_INITIALIZER_STATUS=NOT_PROVEN
D245_A8_CAUSAL_ROLE=PRECONDITION_OBSERVED_BEFORE_SUCCESSFUL_E4_NOT_DEVICE_INITIALIZATION_PROVEN
```

A8 non viene descritto come inizializzazione, reset, wake o requisito firmware.

## Baseline sealed dopo rename

Gli expected hash sono recuperati dagli executable closure report locali
D243/D244 e confrontati con i file correnti.

| path | expected_sha256 | actual_sha256 | behavior_relevant | esito |
| --- | --- | --- | --- | --- |
| `src/goodix5125_d233_backend.py` | `e537f33d47d49d47b0fc451c80b08fbafdc185e884d519cb603e22baf458c982` | `e537f33d47d49d47b0fc451c80b08fbafdc185e884d519cb603e22baf458c982` | true | MATCH |
| `src/goodix5125_d235_entrypoint.py` | `d87b11d0f2de608f05c232fa83d4e03ce4d248fe37839808f42f6ea577143b69` | `d87b11d0f2de608f05c232fa83d4e03ce4d248fe37839808f42f6ea577143b69` | true | MATCH |

```text
D245_SEALED_BASELINE_AFTER_RENAME_STATUS=MATCH
```
