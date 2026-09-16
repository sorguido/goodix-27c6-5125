<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/10 — analisi integrale metadata-only dell'enrollment OEM attempt 02

## Esito

L'attempt `D27910_20260905_ATTEMPT02`, preservato nel commit
`6c1564b6e7f58a5694113ffcb2e35f9ea0847c7e`, chiude con evidenza target-local
il workflow OEM completo osservabile. L'audit ha letto direttamente l'intero
`wire.pcapng` finalizzato e tutti i JSON sanitized, verificando l'hash
`3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab`.
Non ha modificato `captures/` e non esporta body A0, record TLS, immagine,
template, hash biometrico o materiale segreto.

```text
OUTCOME=PASS_COMPLETE_OEM_ENROLLMENT_RECONSTRUCTED
ADVANCEMENT=NEW_TARGET_LOCAL_FULL_ENROLLMENT_PROTOCOL_EVIDENCE
OEM_SUCCESSFUL_PRIMARY_ACQUISITION_STAGE_COUNT_THIS_RUN=21
OPERATOR_CONTACT_COUNT=22
OPERATOR_CONTACT_WITHOUT_COMPLETE_WIRE_ACQUISITION_LIFECYCLE_COUNT=1
SPECIFIC_UNMATCHED_CONTACT=NOT_TEMPORALLY_LOCALIZABLE
PROTOCOL_CONTRADICTION_COUNT_FINALIZED=0
AUTOMATIC_RETRY_COUNT=0
GOODIX_SENDER_PRESENT=false
LIVE_EXECUTED_BY_AI=false
```

## Integrità e fonti

Il parser stretto ricostruisce 924 pacchetti pcapng, 912 pacchetti del device
`1:2` e 442 frame target A0/B0 completi. L'identità
`GF_ST411SEC_APP_12509` è presente. `attempt_status.json`,
`operator_events.json`, `observer_result.json` e il risultato del finalizer
sono coerenti su PASS, 21 cicli, zero contraddizioni finali e zero retry.

Il journal contiene 11 snapshot transitori con
`protocol_contradiction_count=1`. Non sono anomalie definitive: ciascuno è
prodotto dalla lettura del pcap in crescita quando il prefisso
`IRQ2 → 0x22 → ACK → B0` non è ancora interamente visibile; lo snapshot
successivo e il parse finalizzato tornano a zero. Nessun errore viene quindi
riclassificato genericamente come pending.

## Timeline completa per fasi

I tempi relativi partono dal primo frame target, alle
`2026-09-05T06:13:33.323Z`.

| Fase | Frame | Tempo relativo | Sequenza metadata-only | Conclusione |
| --- | ---: | ---: | --- | --- |
| bootstrap cold | 25–181 | 0–952,631 ms | `F01,D5,F01,A8,F01,97,AF,F01,A8,E4,A2,82,A6,A2,70,80×4,90,D1,TLS,D4,AF,36,50/NAV,36,82,20/B0,36,32` | init, sessione TLS e FDT iniziale |
| re-entry 1 | 187–195 | 58.282,904–58.339,146 ms | `F01,D5,F01,AF` | nuova query di stato; nessun reset USB osservato |
| re-entry 2 / arm | 199–211 | 79.813,572–79.919,041 ms | `F01,D5,F01,AF,32/ACK` | arm accettato prima del primo contatto efficace |
| wizard pronto | host | 88.185,645 ms | evento operatore aggregato | nessun timestamp per singolo contatto |
| acquisizioni | 213–921 | 97.093,574–238.191,919 ms | 21 lifecycle primari e transizioni | completion wire osservata |
| finalizzazione UI | host | 249.562,364 ms circa | nessun nuovo frame target | conferma Windows 11,370 s dopo l'ultimo frame |
| tail | host | 5,167 s | zero frame e zero pacchetti target post-UI | silenzio target nel tail richiesto |

Il primo IRQ2 arriva 8.907,929 ms dopo `wizard_started_utc`. Le 21 latenze
`IRQ2 → primary B0` sono strette: minimo 47,958 ms, mediana 48,937 ms, massimo
59,622 ms.

### I 21 lifecycle primari

Ogni riga identifica l'intero stage primario
`IRQ2 → 0x22[01 00] → ACK 0x22/01 → B0 fingerprint-shape`; la colonna finale
classifica la transizione fino al successivo IRQ2 o alla chiusura.

| Ciclo | IRQ2 | B0 primario | IRQ2 ms | B0 ms | ultimo frame transizione | classe |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 213 | 219 | 97093.574 | 97143.283 | 245 | NAV iniziale + re-arm |
| 2 | 247 | 253 | 105964.292 | 106013.742 | 279 | forma ripetuta + re-arm |
| 3 | 281 | 287 | 113950.581 | 113999.962 | 313 | forma ripetuta + re-arm |
| 4 | 315 | 321 | 120611.357 | 120659.327 | 347 | forma ripetuta + re-arm |
| 5 | 349 | 355 | 127752.708 | 127801.057 | 381 | forma ripetuta + re-arm |
| 6 | 383 | 389 | 134366.458 | 134414.453 | 415 | forma ripetuta + re-arm |
| 7 | 417 | 423 | 142655.640 | 142703.840 | 449 | forma ripetuta + re-arm |
| 8 | 451 | 457 | 152161.381 | 152209.612 | 483 | forma ripetuta + re-arm |
| 9 | 485 | 491 | 158815.498 | 158875.120 | 517 | forma ripetuta + re-arm |
| 10 | 519 | 525 | 175658.404 | 175709.314 | 551 | forma ripetuta + re-arm |
| 11 | 553 | 559 | 182742.982 | 182793.987 | 585 | forma ripetuta + re-arm |
| 12 | 587 | 593 | 188378.314 | 188427.251 | 619 | forma ripetuta + re-arm |
| 13 | 621 | 627 | 194145.300 | 194197.037 | 653 | forma ripetuta + re-arm |
| 14 | 655 | 661 | 199255.777 | 199305.918 | 687 | forma ripetuta + re-arm |
| 15 | 689 | 695 | 204643.065 | 204691.085 | 721 | forma ripetuta + re-arm |
| 16 | 723 | 729 | 209970.043 | 210018.001 | 755 | forma ripetuta + re-arm |
| 17 | 757 | 763 | 215301.229 | 215350.990 | 789 | forma ripetuta + re-arm |
| 18 | 791 | 797 | 220751.257 | 220803.204 | 823 | forma ripetuta + re-arm |
| 19 | 825 | 831 | 226139.119 | 226187.835 | 857 | forma ripetuta + re-arm |
| 20 | 859 | 865 | 231606.214 | 231654.259 | 891 | forma ripetuta + re-arm |
| 21 | 893 | 899 | 236968.629 | 237017.105 | 921 | forma terminale, nessun re-arm |

Il numero reale dimostrato per questa prima registrazione OEM è quindi **21
stage primari riusciti**, non il default libfprint di cinque. Il risultato non
prova che ogni versione driver/firmware o ogni condizione di qualità richieda
sempre 21 stage.

## Transizioni, finger-up, NAV e quality path

Tre forme spiegano l'intero enrollment:

1. ciclo 1:
   `IRQ2,C22,K22:01,B0,C34,K34:01,IRQ0200,C20,K20:01,B0,C32,K32:01,C50,K50:01,NAV,C32,K32:01`;
2. cicli 2–20:
   `IRQ2,C22,K22:01,B0,C34,K34:01,C36,K36:01,IRQ0100,C20,K20:01,B0,C34,K34:01,IRQ0200,C32,K32:01`;
3. ciclo 21:
   stessa forma ripetuta, ma termina a `IRQ0200` e omette `C32/K32`.

Ne derivano 20 re-arm inter-ciclo effettivi e 21 coppie terminali
`0x34/ACK → IRQ0200`, coerenti con la chiusura finger-up di ogni ciclo.
I 41 `0x34` si decompongono in 21 arm che sfociano in IRQ0200 e 20 comandi
pre-`0x36` nei cicli 2–21. In ciascuno di questi ultimi 20 cicli le due
occorrenze `0x34` riusano lo stesso body tabellare del ciclo; globalmente si
osservano 21 body distinti. Tutti i 23 `0x32` hanno body distinti, coerenti con
down-table aggiornate, ma solo 20 sono re-arm fra due stage primari.

Si osservano 43 B0 della forma fingerprint: uno nel bootstrap FDT, 21 primari
dopo `0x22` e 21 ausiliari dopo `0x20`. I B0 ausiliari sono parte stabile del
workflow, non contatti operatore aggiuntivi. Cifratura e sola forma wire non
permettono di chiamarli punteggi di qualità, immagini accettate o template.

NAV appare soltanto due volte: una nel bootstrap e una nella transizione del
primo ciclo. Non è quindi una fase per ogni contatto. Non appare alcun branch
wire alternativo, status ACK non-`01`, lifecycle primario ripetuto
automaticamente o comando recovery. Le 21 ripetizioni sono stage del workflow,
non retry automatici. Un eventuale giudizio OEM di qualità dentro TLS o lato
host resta non osservabile.

## Rapporto 22 contatti / 21 lifecycle

`operator_events.json` registra i timestamp di avvio capture, avvio wizard,
conferma finale e stop, ma **non** registra il timestamp di ciascun contatto.
Il raw esaurisce tutti gli IRQ2, `0x22` e ACK `0x22` in 21 lifecycle completi;
non contiene un 22º prefisso parziale che localizzi il contatto extra.

Il gap più lungo fra un B0 primario e l'IRQ2 successivo è 16.783,284 ms dopo
il ciclo 9, contro una mediana di 6.141,725 ms. È compatibile con un contatto
inefficace o mal posizionato in quella finestra, ma non lo dimostra: l'operatore
può avere impiegato più tempo anche senza contatto extra. La sola conclusione
probatoria è quindi:

```text
1 operator contact without complete wire acquisition lifecycle
SPECIFIC_CONTACT=UNKNOWN
```

Non è un'anomalia di protocollo e non va attribuito a un ciclo specifico.

## Tratto terminale e finalizzazione OEM

La sequenza visibile finale è:

```text
IRQ2@893 → 0x22@894 → ACK@897 → primary B0@899
→ 0x34@900 → ACK@903
→ 0x36@905 → ACK@907 → IRQ0100@909
→ 0x20@910 → ACK@913 → auxiliary B0@915
→ 0x34@916 → ACK@919 → IRQ0200@921
→ no 0x32 re-arm
```

`IRQ0200@921` alle `06:17:31.515Z` è l'ultimo frame di protocollo. Una lettura
bulk-IN già pendente termina a zero byte al packet 923, 8,998 s dopo; non è un
frame né un comando. La UI conferma l'enrollment 2,372 s dopo quel completamento
vuoto e 11,370 s dopo l'ultimo frame. Nei successivi 5,167 s fino allo stop non
si osservano né frame né pacchetti target.

Non compare un distinto comando A0 di “commit”. La **finalizzazione wire
osservabile** è pertanto l'ultimo ciclo completo, il suo B0 ausiliario e il
finger-up terminale senza re-arm; la conferma successiva è host/UI. Non si può
dedurre se il commit logico avvenga nel B0 cifrato, implicitamente nel sensore,
nel database host o in più luoghi.

## Interpretazione dei conteggi per famiglia

| Famiglia | Conteggio | Interpretazione bounded per questa run |
| --- | ---: | --- |
| `0x20` | 22 | richiesta image-mode esatta: una baseline FDT e una acquisizione ausiliaria per ciascuno dei 21 cicli |
| `0x22` | 21 | acquisizione primaria dopo IRQ2; body esatto e ACK `01` in tutti i cicli |
| `0x32` | 23 | arm/down-table: bootstrap, re-entry, transizioni del primo ciclo e 20 re-arm inter-ciclo; non sono 23 stage |
| `0x34` | 41 | FDT-up/finger-up family: 21 conducono a IRQ0200, 20 preparano il ramo `0x36/0x20` |
| `0x36` | 23 | FDT scan: tre nel bootstrap e venti nei cicli 2–21, sempre con ACK e IRQ0100 |
| `0x50` | 2 | NAV mode con ACK e risposta NAV: bootstrap e sola transizione ciclo 1 |
| `0x70` | 1 | transizione idle prima delle quattro write DAC |
| `0x80` | 4 | quattro ChipRegWrite/DAC già classificate come configurazione volatile per le istanze osservate |
| `0x82` | 2 | ChipRegRead bounded: una query init e una fase FDT |
| `0x90` | 1 | download della configurazione device, staticamente classificato volatile per questo path |
| `0x97` | 1 | wire coordinate di SetDriverState nel pre-TLS |
| `0xA2` | 2 | entrambe le forme sensor-only reset già ricostruite, nel cold-start OEM; non retry enrollment |
| `0xA6` | 1 | lettura OTP/fixed-production bounded; nessuna scrittura |
| `0xA8` | 2 | query versione firmware; risposta APP12509 osservata |
| `0xAF` | 4 | wire coordinate GetMcuState: due cold-start e due re-entry pre-enrollment |
| `0xD1` | 1 | inizializzazione/transizione TLS server |
| `0xD4` | 1 | transizione D-family post-TLS che precede AF/FDT |
| `0xD5` | 3 | wire coordinate D4-family/state request: cold-start e due re-entry |
| `0xE4` | 1 | production read specific-data/PSK validation; il comando osservato è read, non il fallback persistente `0xE0` |

Il frame OEM fisso control `0x01` compare otto volte ma è escluso, per scelta
del finalizer, da `command_family_counts` perché ha una forma control-specific.

## Persistenza e significato del tail

Nessuna delle famiglie note persistenti/manutentive
`0xE0/0xA4/0xF0/0xF4` appare come comando visibile. Ciò prova soltanto
l'assenza di quelle famiglie A0 nella capture riuscita. Non prova assenza di
persistenza template sensor-side: i B0 sono cifrati, un effetto può essere
implicito e la DLL contiene capacità statiche di gestione template. Analogamente,
il tail silenzioso esclude un comando target **post-conferma UI**, ma non un
commit precedente all'ultimo IRQ0200 o dentro il traffico cifrato.

La run non mostra retry automatici, sender Goodix aggiuntivi, flash/IAP,
ClearApp, provisioning PSK, OTP/factory write o cambi VID:PID/mode. Questo non
trasforma l'assenza osservata in una prova universale di irraggiungibilità.

## Prossimo passo più economico e informativo

Prima di un nuovo live, il passo minimo è un'estensione **offline** del modello
enrollment Linux/libfprint, non un replay OEM cieco:

1. rendere `GoodixPostTlsLifecycle` iterativo e target-configurato per 21 stage
   primari, senza hard-code del precedente secondo B0;
2. consumare il B0 `0x20` e le tabelle FDT come transizione interna, riportando
   a libfprint come avanzamento soltanto il B0 primario `0x22`;
3. modellare esplicitamente le tre forme osservate: primo ciclo con NAV,
   cicli 2–20 ripetuti, ciclo 21 terminale senza re-arm;
4. portare `nr_enroll_stages` a 21 per questo target e verificare con fixture
   sintetiche che NBIS riceva 21 sample, che identify/match resti host-side e
   che cancellation/failure chiuda senza retry o comandi persistenti;
5. usare il presente audit come oracle metadata-only e mantenere il raw fuori
   dalle fixture redistribuibili.

Questo riduce insieme l'incertezza di protocollo e quella di integrazione
libfprint. Solo dopo test normali/sanitizer, executable closure e review del
live-critical set avrebbe senso preparare una singola enrollment Linux live;
quella futura run resta un Human Gate separato.

## Riproducibilità

```text
python3 -m unittest -v analysis.D279.test_d279_10_attempt02_full_enrollment_audit
python3 analysis/D279/d279_10_attempt02_full_enrollment_audit.py \
  --output /tmp/D279_10_attempt02_full_enrollment_audit.json
```

Il report macchina canonico è
`analysis/D279/D279_10_attempt02_full_enrollment_audit.json`.

La regressione specifica passa 3/3; la matrice combinata D274+D279 passa
112/112. `git diff --quiet HEAD -- captures` e il ricalcolo SHA-256 confermano
che l'evidenza autentica è rimasta invariata.

```text
EXECUTABLE_CLOSURE=PASS_HASH_GATED_METADATA_ONLY_AUDIT
CAPTURES_UNCHANGED=true
D279_10_ATTEMPT02_AUDIT_TESTS=3/3_PASS
D274_D279_COMBINED_REGRESSION=112/112_PASS
RESIDUAL_BLOCKER_OR_RISK=LINUX_LIFECYCLE_STILL_TWO_ACQUISITIONS;OEM_AUXILIARY_B0_SEMANTICS_ENCRYPTED;NEW_LIVE_NOT_AUTHORIZED
CANONICAL_DOCUMENTATION=UPDATED
```
