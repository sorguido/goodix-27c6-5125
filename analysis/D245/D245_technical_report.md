# D245 — report tecnico

## Decisione

```text
D245_A8_E4_PRECONDITION_TLS_CONTINUATION_READY_NOT_EXECUTED
```

Nessun USB reale, TLS reale, secret reale o ramo live è stato eseguito durante
D245. Il risultato riguarda esclusivamente audit, implementazione source-sealed,
fixture sintetiche e closure offline.

## Gate bloccanti

La root reale è `/home/guido/Repository/goodix-27c6-5125_private`. Gli hash
sealed behavior-relevant recuperati dalle closure locali D243/D244 coincidono:

| path | expected / actual SHA-256 | stato |
| --- | --- | --- |
| `src/goodix5125_d233_backend.py` | `e537f33d47d49d47b0fc451c80b08fbafdc185e884d519cb603e22baf458c982` | MATCH |
| `src/goodix5125_d235_entrypoint.py` | `d87b11d0f2de608f05c232fa83d4e03ce4d248fe37839808f42f6ea577143b69` | MATCH |

Il record live storico D179 è preservato canonicamente, ma gli artifact runtime
primari sono purged e non vengono ricostruiti. Il corpus locale D230 corrobora
indipendentemente request, ACK, response 12509, framing/checksum/endpoints e
classificazione read-only A8. P1, P3 e P4 sono quindi PASS.

## Composizione minima

La patch D245 non introduce un secondo backend né una seconda state machine.
Estende `ProductionReplayBackend` con una sola precondizione interna
`A8_FIRMWARE_QUERY` eseguita prima della prima E4 richiesta dal core invariato.
La request è una costante byte-pinned, non un builder o input configurabile.

Il gate accetta ACK echo A8 status `0x01` oppure `0x07`; entrambe le classi
autorizzano esattamente una bounded response read tipizzata. `A8_COMPLETE`
richiede poi A0/A8 con body esatto `GF_ST411SEC_APP_12509\0`. D43 documenta il
path ACK01 e D175 il path ACK07; quest'ultimo falsifica la precedente policy
D245 ACK07-terminale. La semantica nominale dei due status resta ignota e ACK07
è `UNKNOWN_STATUS_CLASS_EMPIRICALLY_COMPATIBLE_WITH_RESPONSE`. Altri status
fermano senza seconda IN; mismatch, timeout, ordine, wrapper, checksum e stale
buffered frame fermano con E4 non inviato. Il boundary
`A8_COMPLETE → E4_OUT` è verificato dalla phase trace. A8 resta un
discriminatore/precondizione read-only e non è interpretato come initializer,
reset o wake.

Con A8 completo, il core esistente invia E4 canonico, verifica il binding D190
e continua `A2→82→A6→A2→70→80x4→90→D1→TLS`. A0 conserva la submission corta
D241; B0 conserva fixed-64, staging tail a zero, pacing 10 ms per record e
timeout TLS 3000 ms. D4, application data, persistent write e retry restano
zero/irraggiungibili.

## Osservabilità e durability

Il candidate report distingue OUT/IN A8 ed E4, lunghezze richieste/completate,
risultati, ACK status, presenza response, match firmware e failure class. Per
TLS pubblica ClientHello osservato, ClientKeyExchange osservato, handshake
completato, record/chunk/pacing server flight e prima ricezione post-flight.
Non conserva response A8 raw, validator E4, config90, TLS payload, secret o dati
biometrici.

Ogni terminale della matrice (A8 OUT/IN timeout; ACK07 seguito da timeout,
malformed, wrong control, FW12508/FW12510 o extra frame; ACK01 con firmware
mismatch; altro status; stale/order; E4 IN timeout; TLS timeout e TLS success)
passa cleanup exactly-once, zeroizzazione, checkpoint pre-restore, restore
esatto di `fprintd`/signal mask e report finale. Il caso `fprintd` inizialmente
inactive verifica che non venga avviato artificialmente.

## Root rename e launcher

`d245-live-tls-once.sh` risolve la root dal proprio path e da Git, poi verifica i
guardrail correnti; non dipende dal basename. Il dry-run usa identici cwd,
`PYTHONPATH`, patch e composition chain della futura branch live, ma soltanto in
una copia temporanea con fake USB. I launcher storici D239–D244 sono stati
ripristinati byte-per-byte dai rispettivi bundle canonici. Le loro location
assumption storiche non sono state adattate alla root `_private`; la suite
corrente gestisce quella sola incompatibilità nel test harness.

## Source sealing e governance v2.1

Lo stato per un eventuale live resta
`LIVE_BASELINE_APPROVAL_PENDING_USER_REVIEW`: nessun commit SHA è stato
inventato o auto-approvato. I pin correnti di core, backend, entrypoint, patch
unseal e preflight sono safety-critical per il percorso live/source-sealing. I
pin di audit, contratto, runtime matrix, closure runner, report storico e test
servono alla governance/closure offline. La correzione aggiorna solo i pin
preesistenti divenuti stale, senza estendere il pinning né rimuovere guardrail.

```text
D245_HISTORICAL_LAUNCHER_INTEGRITY=RESTORED
D245_HISTORICAL_LAUNCHER_MUTATION_COUNT=0
```

## Closure

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
Ran 131 tests — OK

./operator_kit/d245-live-tls-once.sh --offline-dry-run
D245_RESULT=PASS
D245_LIVE_USB_EXECUTION=NOT_PERFORMED
```

La patch applica e inverte senza offset/fuzz in una tree temporanea. Gli hash
finali delle sorgenti sealed coincidono byte-per-byte con il baseline. La
matrice prova entrambi i path completi A8 ACK01/ACK07, 13 comandi logici (A8
più i 12 pre-D1), E4 ACK01/07, B0 fisici `64|64|64`, due pacing e stop prima di
D4. Prova inoltre che uno status A8 diverso non genera la seconda IN.
