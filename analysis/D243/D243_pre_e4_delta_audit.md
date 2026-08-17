# D243 — audit esaustivo D241→D242 fino al timeout E4

## Metodo e conteggi

Baseline storico D241: commit `436f8bc`. Chiusura D242: commit `d880ce1` e
patch live `analysis/D242/D242_live_unseal.patch`. Sono stati confrontati il
diff sorgente completo e le due patch live, seguendo il control flow da unseal
ed entrypoint fino al primo `bulk_in` E4 terminato in timeout.

`D243_PRE_E4_DELTA_COUNT=6` conta i gruppi di modifica D241→D242 effettivamente
raggiunti prima o al timeout E4. `D243_PRE_E4_CAUSAL_CANDIDATE_COUNT=1` conta i
gruppi che cambiano il contratto USB osservabile dal device in quella finestra.

| ID | Path/funzione | D241 | D242 | Raggiunto prima/al timeout E4 | Behavior-relevant | Candidato causale |
| --- | --- | --- | --- | --- | --- | --- |
| Δ1 | patch live, seal e costanti `D235_*` | unseal D233/D235, schema D241, live single-shot | stesso unseal/autorizzazione; solo schema D242 | true | false | false |
| Δ2 | `ProductionRuntimePaths.system_default()` / composizione entrypoint | marker e report directory D241 | marker e report directory D242 | true | false per il protocollo USB; rilevante solo per publication | false |
| Δ3 | `ProductionUsbTransport.__init__()` | contatori lifecycle essenziali | aggiunti contatori e liste bulk IN/OUT | true | false: inizializzazione di telemetria | false |
| Δ4 | `ProductionUsbTransport.write_frame()` | chunk logici `<=64`; ultimo OUT corto; completion `len(chunk)` | ogni ultimo chunk padded zero a 64; completion richiesta 64 | true | true | **true** |
| Δ5 | `ProductionUsbTransport.read_frame()` / `_bulk_in()` | chiamata diretta `bulk_in` | wrapper con contatori timeout/error/nonzero; stessi endpoint, maximum, deadline ed eccezioni rilanciate | true | false: osservabilità soltanto | false |
| Δ6 | `ProductionReplayBackend.__init__()` | stato replay/TLS D241 | aggiunti campi di telemetria server-flight/OpenSSL e callback pacer memorizzata | true | false: il pacer non viene invocato prima di TLS | false |

## Censimento delle superfici richieste

| Superficie | D241 | D242 | Raggiunto prima/al timeout E4 | Behavior-relevant delta | Candidato causale |
| --- | --- | --- | --- | --- | --- |
| source unseal effect | i due seal diventano no-op | identico; cambia soltanto label schema | true | false | false |
| entrypoint composition | stessa composizione production | stessa composizione, namespace D242 | true | false per wire | false |
| target identity / claim | exact VID/PID, identity revalidation, interface 0 | invariato | true | false | false |
| transport constructor | stato D241 | Δ3: telemetria aggiunta | true | false | false |
| endpoint OUT/IN | `0x01` / `0x81` | invariati | true | false | false |
| timeout values | E4 1000 ms; deadline monotonic | invariati | true | false | false |
| `write_frame()` | final short | Δ4: generic fixed-64 | true | true | true |
| chunking | slice logico massimo 64 | slice logico invariato | true | false in sé | false |
| bulk OUT requested length | `len(chunk)` | sempre 64 | true | true, parte di Δ4 | true |
| bulk OUT completion requirement | `len(chunk)` | 64 | true | true, parte di Δ4 | true |
| bulk IN requested length | 64 per header, poi residuo bounded | invariato | true | false | false |
| bulk IN timeout | budget E4 residuo | invariato; solo contatore Δ5 | true | false | false |
| E4 serializer | `expected_request_frames()` | invariato | true | false | false |
| logical E4 bytes | frame A0 corto, byte-exact | invariato prima del transport | true | false | false |
| A0 declared length | lunghezza logica | invariata | true | false | false |
| A0 header/checksum | builder e seed invariati | invariati | true | false | false |
| response frame assembly | buffer per declared length e completion IDs | invariato; `_bulk_in` strumentato | true | false | false |
| ACK/response parser | ACK allowlist e risposta E4 tipizzata | invariati, ma non raggiunti nella run | false | false | false |
| exception mapping | `UsbTimeout`→abort timeout, zero retry | invariato; Δ5 rilancia la stessa eccezione | true | false | false |
| cleanup trigger | `finally`, exactly once | invariato | true, dopo timeout | false | false |
| H5 `B0TlsBridge` pacing | nessuna pausa | 10 ms dopo record server-side | false | true fuori dalla finestra E4 | false per E4 |
| OpenSSL/server-flight telemetry | minima | contatori aggiunti | false | false nella finestra | false |
| report mapping finale | schema/label D241 | schema/label D242 e campi H4/H5 | false prima del timeout; raggiunto dopo l'abort | false per causalità E4 | false |

## Conclusione del gate

L'unico delta raggiunto che cambia i byte e la lunghezza richiesti al controller
USB prima del timeout è Δ4, il generic fixed-64 zero-filled A0. La forza
dell'inferenza deriva dalla regressione live singola D242 e dai due path live
D239/D241 già riusciti; non identifica il contenuto corretto della tail Windows
e non prova una root cause device-side.

```text
D243_A0_FIXED64_CAUSAL_STATUS=STRONG_CAUSAL_REGRESSION_CANDIDATE_SINGLE_LIVE_OBSERVATION
D243_DECISION_GATE=PASS_FOR_MINIMAL_A0_B0_SPLIT
```

