# D246 — post-review correction del confine TLS→D4

## Decisione

```text
OUTCOME=D246_D4_FACTORY_PRESERVING_CONTINUATION_READY_NOT_EXECUTED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS
```

D246 complessivamente ha prodotto nuova evidenza host/wire/receiver e ha
classificato il D4 target-local. La sola correzione post-review è host-side e
non costituisce nuovo avanzamento scientifico. Nessuna parte di D246 è stata
eseguita sull'hardware durante questa closure.

La baseline candidata precedente
`ff4cc3b748dafbce681e6fa38a44936eca794d12` è
`SUPERSEDED_NOT_APPROVED_FOR_LIVE`. Il nuovo commit è soltanto candidato finché
l'Utente/AI PM non ne approva esplicitamente il full SHA.

## Tentativo operatore fermato nel preflight

Il tentativo successivo alla prima review non ha iniziato D246 live. Il
launcher D246 richiamava ancora preflight, renderer e report D245; il marker
D245 storico consumato ha quindi causato un hard stop prima di ogni accesso
hardware:

```text
D246 live attempt = NOT STARTED
failure = inherited D245 preflight namespace
real USB access = 0
Goodix command count = 0
real secret read count = 0
fprintd mutation count = 0
D4 attempt count = 0
device state unchanged by D246 attempt
```

Questo è un failure di live-enablement host-side, non un failure TLS o D4. Il
marker D245 non è stato cancellato, modificato o riutilizzato.

## Riesame metodologico pre-live

1. **Cosa cambia realmente:** il prossimo live non ripete un esperimento
   precedente. D245 ha già chiuso TLS; D246 aggiunge esattamente un D4 e stop.
2. **Quale ipotesi viene testata:** che l'exchange D4 correlato staticamente e
   nella capture come `VOLATILE_SESSION_INITIALIZATION` sia accettato live dal
   target con ACK esatto `d4/01`, senza richiedere alcuna azione successiva.
3. **Se il live D4 fallisce:** nessun retry e nessuna patch cosmetica. Il
   failure sarà classificato come pre-D4/TLS regression, D4 OUT
   ambiguous/timeout, ACK mismatch oppure disconnect/re-enumeration. Se D4 è
   tentato ma non chiude, AF resta irraggiungibile e vengono riesaminate
   ipotesi causale e precondizioni/stato device.

## Contratto D4 preservato

Le fonti primarie restano la capture D230 `rilevamento.pcapng`, SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`,
e `gfusb.dll`, SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.

```text
D4 semantic class       VOLATILE_SESSION_INITIALIZATION
scope                    EXACT_APP12509_D4_RECEIVER_PATH_ONLY
logical request          a00600a6d403000000d3
physical OUT             fixed 64 byte, zero tail
post-TLS pacing          20 ms
timeout                  200 ms
accepted ACK             exact d4/01
typed D4 response        none
terminal                 STOP_AFTER_D4
AF                       unreachable
persistent-write family  unreachable
```

`PROVEN`: callsite host, serializer, frame/ACK nella capture e receiver
APP12509 esatto sono correlati; il branch subtype 2 modifica soltanto SRAM e
non raggiunge flash/IAP, OTP, factory data, configurazione persistente,
provisioning o enrollment. `UNVERIFIED`: esito live D4 sul target. Nessuna
ipotesi è stata promossa per chiudere la correzione.

## Correzione A — preflight D246

`analysis/D246/d246_preflight.py` e
`analysis/D246/d246_preflight_observability.py` implementano namespace e
failure renderer esclusivamente D246:

```text
marker             /var/lib/goodix-5125-poc/d246-operator-invocation.marker
result directory   /var/lib/goodix-5125-poc/d246-results
preflight report   analysis/D246/D246_preflight_report.json
```

Il marker D245 presente è storico e benigno; il marker D246 presente blocca.
Un failure dei gate iniziali termina prima di protected material inspection,
enumerazione target, osservazione/mutazione fprintd, signal handling, marker
live o USB. I fixture provano zero libusb init, USB open, comando Goodix,
secret read, mutazione fprintd e marker create.

## Correzione B — latch D4 exactly-once

Il backend patchato distingue:

```text
d4_attempt_count  punto di submit D4 raggiunto, latched prima di write_frame()
d4_send_count     ritorno full-length del submit confermato dal transport
d4_failure_class  classe terminale senza deduzione device-side
```

La guardia di ingresso usa `d4_attempt_count != 0`. Nel failure sintetico di
completion ambigua il risultato è `attempt_count=1`, `send_count=0`,
`d4_failure_class=ambiguous_usb_completion`, retry zero. La re-entry
intenzionale sullo stesso backend termina prima del transport: secondo write
zero, latch invariato a uno e terminal abort.

## Correzione C — live-critical dependency closure

Il launcher confronta i file direttamente con i blob del commit Git approvato,
senza dipendere da `.git/index` e senza hash SHA-256 hardcoded generalizzati.
Il set behavior-affecting finale è:

| File | Motivo live-critical |
| --- | --- |
| `operator_kit/d246-live-d4-once.sh` | autorizzazione, single-shot, patching, cleanup e reseal |
| `analysis/D245/D245_live_unseal.patch` | abilita il predecessore revisionato A8→TLS usato da D246 |
| `analysis/D246/D246_d4_continuation.patch` | aggiunge l'unico D4 raggiungibile e lo stop terminale |
| `analysis/D246/d246_preflight.py` | namespace D246 e policy safety pre-USB |
| `analysis/D246/d246_preflight_observability.py` | rendering fail-closed del preflight D246 |
| `analysis/D246/d246_live_critical.py` | definizione e verifica della closure Git completa |
| `src/goodix5125_d232_offline.py` | framing, replay policy, protected inputs e durable report |
| `src/goodix5125_d233_backend.py` | USB reale, binding PSK↔E4, TLS e percorso D4 |
| `src/goodix5125_d235_entrypoint.py` | entrypoint, runtime paths, autorizzazione e mapping risultato |
| `analysis/D230/work/GoodixExport/gfusb.dll` | input PE canonico hash-gated da cui deriva il validator E4 runtime; referenziato ma non redistribuito nel bundle |
| `poc/goodix5125/tools/binding_reference/__init__.py` | initializer eseguito prima del runtime binding |
| `poc/goodix5125/tools/binding_reference/runtime.py` | derivazione validator PSK→E4 e gate PE canonico |
| `poc/goodix5125/tools/binding_reference/crypto_reference.py` | implementazione crittografica del binding |
| `poc/goodix5125/tools/binding_reference/pe_parser.py` | validazione PE ed estrazione bounded dei seed |

Documenti, report e test non influenzano il live e non sono inclusi nel set.
Un fixture Git temporaneo modifica soltanto `binding_reference/runtime.py` e
prova la transizione baseline `APPROVED→STALE`; il tree canonico resta intatto.

## Verifica offline

| Test richiesto | Esito |
| --- | --- |
| T1 marker D245 storico, D246 assente | PASS, D245 benigno e non modificato |
| T2 marker D246 presente | PASS, hard stop modellato pre-USB |
| T3 report/renderer D246 | PASS, path e prefissi solo D246 |
| T4 completion ambigua + re-entry | PASS, latch pre-submit e secondo write zero |
| T5 helper live-critical modificato | PASS, baseline `STALE` in tree temporaneo |
| T6 regressione D245 A8→E4→pre-D1→D1→TLS | PASS, stop prima di D4 |
| T7 D4 synthetic happy/negative | PASS, ACK esatto; timeout/ACK/trailing fail-closed |
| T8 launcher `--offline-dry-run` da repo e `/tmp` | PASS, zero USB/TLS/D4 reali |
| T9 full regression | PASS, 135 test |
| `bash -n` e patch D245→D246 round-trip | PASS |
| source reseal/hash pre-post | PASS byte-exact |

La closure non ha aperto USB, eseguito handshake TLS reale o tentato D4 reale.
AF e tutte le famiglie di scrittura persistente restano irraggiungibili.

## Residui

- nuovo commit candidato in attesa di approvazione esplicita Utente/AI PM;
- D4 non eseguito live;
- AF non classificato e non raggiungibile;
- esclusione device-side limitata al receiver D4 APP12509 esatto;
- `.git/index` locale è illeggibile all'utente del workspace, ma la verifica
  live-critical usa blob Git diretti e il commit candidato viene costruito con
  indice alternativo senza modificare quello preesistente.
