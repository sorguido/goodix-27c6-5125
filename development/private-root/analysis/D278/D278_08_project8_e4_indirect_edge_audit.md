# D278/08 — risoluzione offline del percorso E4 project 8

## Closure

```text
OUTCOME=READY
ADVANCEMENT=NEW_STATIC_TARGET_SPECIFIC_DIRECT_E4_EDGE_AND_PERSISTENT_PROVISIONING_FAILURE_FALLBACK_RESOLVED
EXECUTABLE_CLOSURE=ANALYSIS_ONLY
RESIDUAL_BLOCKER_OR_RISK=OEM_E4_FAILURE_RECOVERY_IS_NOT_FACTORY_PRESERVING_BECAUSE_TWO_FAILED_PSK_VALIDATION_CHECKS_REACH_PRODUCTION_WRITE_KEY_AND_E0
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_4c73dcdaad5df9f9a429626109a4be2a3b1a8b19_ON_main_PLUS_WORKTREE_DIFF_PLUS_analysis/D278/D278_08_project8_e4_indirect_edge_audit.md_PLUS_analysis/D278/D278_08_project8_e4_failure_graph.md_PLUS_analysis/D278/D278_08_project8_e4_edges.csv_PLUS_analysis/D278/tools/verify_d278_08_static.py_PLUS_analysis/D278/D278_07_oem_pre_d1_recovery_audit.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md

D278_08_BASELINE=4c73dcdaad5df9f9a429626109a4be2a3b1a8b19
OEM_A8_FAILURE_POLICY=RESOLVED
OEM_USES_A2_SENSOR_ONLY_AS_PRE_A8_FAILURE_RECOVERY=false
A2_PRE_A8_RECOVERY_LIVE_JUSTIFIED=false
A8_RETRY_BOUND_RUNTIME_VALUE=UNKNOWN_CONFIG_BYTE_AT_OFFSET_0x45A
PROJECT8_E4_SENDER_RESOLVED=true
PROJECT8_E4_INDIRECT_EDGE_RESOLVED=true
PROJECT8_E4_FAILURE_RETURN_PROPAGATION_RESOLVED=true
PROJECT8_E4_RETRY_BOUND_RESOLVED=true
PROJECT8_E4_PRE_FAILURE_PERSISTENT_WRITE_REACHABLE=true
PROJECT8_E4_POST_FAILURE_PERSISTENT_WRITE_REACHABLE=true
PROJECT8_E4_FAILURE_PATH_FACTORY_PRESERVING=false
OEM_E4_FAILURE_POLICY=RESOLVED
OEM_PRE_D1_FAILURE_RECOVERY=RESOLVED
LINUX_SAFE_E4_RECOVERY_CANDIDATE=false
REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

`PROJECT8_E4_INDIRECT_EDGE_RESOLVED=true` significa che il boundary descritto
in D278/07 è stato chiuso. La classificazione finale non è una callback o una
tabella indiretta: è una continuazione post-return e una catena di `call`
dirette. Slot, tabella e assignment site sono quindi `N/A_DIRECT_CALL`.

```text
EDGE_CLASSIFICATION=DIRECT_CALL
```

## Baseline, scope e metodo

L'audit è iniziato su branch `main`, tree pulito, con `HEAD` e `origin/main`
coincidenti a `4c73dcdaad5df9f9a429626109a4be2a3b1a8b19`. È interamente
statico/offline. Non sono stati enumerati o aperti device, eseguiti launcher
live, inviati comandi USB, usati `sudo`, TLS o materiale protetto. Nessun file
runtime/production è stato modificato.

Fonte primaria: `analysis/D230/work/GoodixExport/gfusb.dll`, versione
1.1.125.14, SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`,
con il disassembly locale
`analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_disasm.txt`. I nomi
funzione derivano dalle stringhe di log e dagli audit D230/D231; indirizzi,
branch, argomenti e return sono stati verificati nel disassembly x86-64 PE.
La capture D255/D256 è usata solo come corroborazione wire del successo; non
contiene un failure E4.

## 1. Sender E4 esatto del project 8

Il boundary D278/07 derivava dall'aver fermato il grafo alla chiamata
`gfUpdatefirmware`. Il flusso effettivo continua dopo il suo ritorno:

```text
project selector 0x1805783c0 == 8       @ 0x18006abec
  -> gfUpdatefirmware 0x180064a18       @ 0x18006ac4c
  -> ritorno nonzero, != 0xffdffff3     @ 0x18006ac51..0x18006adc0
  -> production process 0x18003c348     @ 0x18006ae04
  -> production_check_psk_is_valid
       0x18003b514                      @ 0x18003c499
  -> selector literal 0xbb020003        @ 0x18003b77b
  -> production_read_specific_data
       0x18003cc90                      @ 0x18003b780
  -> production_read_mcu 0x18003c7f4   @ 0x18003ce0c
  -> generic sender 0x18005c148         @ 0x18003c94c
```

`production_read_mcu` configura body length 8, attesa ACK, ACK timeout 500 ms
e typed-response timeout 1000 ms. I registri di classificazione del comando
sono `r8=0x0e`, `r9=0x02`; la formula usata dal builder,
`(r8 << 4) | (r9 << 1)`, produce `0xE4`. Il body comincia con il literal
little-endian `03 00 02 bb`, seguito da quattro byte zero.

La capture target D255/D256 corrobora questo risultato: la request E4 ai frame
54/56/58 ha body `03 00 02 bb 00 00 00 00`, subito dopo A8 e prima dell'A2
sensor-only. La capture prova il wire riuscito; gli edge statici sopra provano
la provenienza project 8.

## 2. Natura dell'edge precedentemente ritenuto indiretto

Non è stata trovata né richiesta alcuna dereferenziazione di function pointer.
Il project 8 chiama direttamente `gfUpdatefirmware`; se il suo return supera i
gate locali, `init_MCU` prosegue nello stesso basic block e chiama direttamente
`0x18003c348`. Da lì tutti gli edge fino al sender sono `call rel32` diretti.

La radice dell'errore di classificazione storico è dunque metodologica: il
grafo D278/07 trattava `gfUpdatefirmware` come un wrapper terminale, mentre il
sender E4 appartiene alla continuazione di `init_MCU`, non al sottografo
interno dell'updater. La risoluzione è riproducibile nel CSV e nel grafo
D278/08; `assignment_site` e `slot_or_table` sono marcati
`N/A_DIRECT_CALL`.

## 3. Policy di failure, retry e propagazione

### Retry E4 interno

Il primo invio è `0x18003c94c -> 0x18005c148`. Se il generic sender ritorna
zero, `production_read_mcu` esegue un solo retry immediato a `0x18003c9a1`.
Un secondo zero produce `0xffdffffd` a `0x18003c9ed`. Non è visibile alcun
sleep fra i due invii.

Dopo un trasporto accettato, il parser controlla forma, lunghezza e status
della typed response. Fra gli errori osservabili nel percorso ci sono
`0xffeffffa` per forma/lunghezza non valida e `0xffdffffc` per status di
esecuzione nonzero. Un esito sintatticamente valido passa inoltre al confronto
del valore letto in `production_check_psk_is_valid`; anche un mismatch resta
nonzero. I wrapper intermedi propagano il risultato.

### Retry della validazione e fallback persistente

`production process` invoca `production_check_psk_is_valid` al massimo due
volte. Un singolo successo termina la validazione. Dopo due esiti nonzero,
però, il codice non abortisce: entra in un secondo loop, anch'esso bounded a
due iterazioni, e chiama `0x18003cfd8`.

La provenance delle stringhe identifica `0x18003cfd8` come
`production_write_key`, non come wrapper E4. Questa funzione prepara materiale
di chiave e chiama direttamente `production_write_mcu` (`0x18003d8e0`) a
`0x18003d6fd`. Il sender in `production_write_mcu` usa `r8=0x0e`, `r9=0`,
quindi control `0xE0`, con primo invio a `0x18003da2a` e un solo retry a
`0x18003dabf` se il sender ritorna zero. È un percorso di provisioning/write,
non una recovery read-only.

La correlazione non dipende dal nome assegnato manualmente: nel PE le stringhe
UTF-16LE `production_write_key`, `production_write_mcu`,
`production_check_psk_is_valid`, `production_read_specific_data` e
`production_read_mcu` sono presenti rispettivamente agli offset file
`0x336df0`, `0x337568`, `0x337b68`, `0x337dc8` e `0x337240`, e sono
referenziate dai blocchi funzione corrispondenti.

Limiti esatti prima del fallback:

| Failure E4 | Invii E4 per check | Check esterni | Massimo invii E4 |
|---|---:|---:|---:|
| sender/timeout con ritorno zero | 2 | 2 | 4 |
| typed/status/hash failure dopo send accettato | 1 | 2 | 2 |

Il fallback può poi chiamare `production_write_key` due volte, ciascuna con
massimo due invii E0: fino a quattro invii E0 se ogni generic send fallisce.
Un write riuscito non basta però a far ritornare successo: a `0x18003c6fb` il
production process chiama di nuovo `production_check_psk_is_valid`. Solo se
questa verifica post-write riesce, l'init continua. Se fallisce, il secondo
tentativo di write resta raggiungibile e può essere seguito da una seconda
verifica post-write.

Nel worst case in cui entrambi i write sono accettati ma entrambe le verifiche
post-write falliscono per trasporto, il percorso contiene quindi altre quattro
E4 (due per verifica) oltre alle quattro E4 dei due check iniziali: massimo
otto E4 nel production process. Per failure semantici già dopo un send
accettato, il massimo corrispondente è quattro E4. Se il loop write/recheck si
esaurisce nonzero, l'ultimo errore risale a `init_MCU`, `_DeviceInit` e
`InitThread`.

### Retry esterno dell'intera init

`init_MCU` conserva il return di `production process` a `0x18006ae09`; sul
nonzero lo restituisce. `_DeviceInit` lo propaga senza chiamare `init_FP`.
`InitThread` normalmente ripete tutta `_DeviceInit` fino al byte configurabile
`N_CFG` a offset `0x45a`; flag fatal/globali o `0xffdffff3` escono prima. Il
valore target concreto di `N_CFG` resta ignoto, ma il loop è strutturalmente
bounded. La re-entry ripercorre A8 e l'eventuale updater prima di un nuovo E4.

## 4. Rischio persistente prima, durante e dopo E4

### Before E4 — prima di E4

Il ramo project 8 esegue `gfUpdatefirmware` prima della validazione E4. La
routine interna `0x1800656f4` contiene branch configurazione/versione che
possono bypassare l'update, ma anche un `Clear App` A4 a `0x180065bb7`, reset
MCU, nuova lettura versione e routine di firmware update a
`0x180065e3d`/`0x180065e93`. La capture successful D255/D256 non mostra A4 in
quella singola run, ma non rende impossibili gli altri branch statici.

Conclusione: un write/erase persistente è raggiungibile prima dell'E4 nel
programma OEM, anche se non è stato osservato nella capture riuscita.

### Durante E4

Il comando E4 risolto è una read di specific data (`0xbb020003`) e non è esso
stesso classificato come write persistente. ACK, typed response e confronto
locale non mutano da soli lo stato factory.

### On E4 success

Se typed response e confronto specific-data/hash riescono,
`production_check_psk_is_valid` ritorna zero. Nel loop iniziale questo porta
direttamente al successo del production process e alla continuazione di
`init_MCU` a `0x18006ae92`. In una revalidation post-write, lo stesso zero
termina il secondo loop. La capture D255/D256 osserva, per il successful path
target, l'A2 sensor-only dopo E4; non dimostra una policy di failure.

### On E4 failure — dopo un failure E4

Dopo due check falliti, il percorso diretto raggiunge
`production_write_key -> production_write_mcu -> E0`. Questo basta a negare la
proprietà factory-preserving, indipendentemente dal fatto che lo specifico
write riesca o fallisca. Se il fallback fallisce e il retry esterno riparte,
diventa nuovamente raggiungibile anche il path updater/erase pre-E4.

Non esiste nel segmento un A2 sensor-only immediato, un clear-halt, un reopen o
un semplice abort factory-preserving che separi il failure E4 dal fallback.

### Cleanup

I wrapper di read liberano i buffer locali e propagano il return; non esiste
un cleanup E4 isolato che fermi il percorso prima del fallback. Nel sottografo
updater eseguito prima di E4 restano invece raggiungibili A4 Clear App,
`HardResetMcu`, nuova `GetEvkVersionWithRetry` e firmware update. Dopo
l'esaurimento nonzero del loop write/recheck, il retry esterno `_DeviceInit`
può ripercorrere quel sottografo. Questi edge appartengono al surrounding
machinery e non trasformano E4 stesso in un comando persistente.

## 5. Decisione Linux e prossimo discriminante offline

La policy OEM E4 e la recovery OEM pre-D1 sono ora `RESOLVED`, ma la risposta
di safety è negativa:

```text
LINUX_SAFE_E4_RECOVERY_CANDIDATE=false
PROJECT8_E4_FAILURE_PATH_FACTORY_PRESERVING=false
```

Non va trapiantato né il retry annidato dell'intera init né il fallback
`production_write_key`. In particolare questo audit non autorizza E0, A4,
firmware update, reset, un nuovo E4 live o alcuna altra esecuzione USB.

Il discriminante offline successivo più informativo, se serve delimitare il
blast radius OEM, è una dataflow analysis di `production_write_key` fino al
payload E0: origine del materiale, tag/destinazione e store persistente
selezionato. Non è necessario per la decisione Linux, già negativa; serve solo
a classificare con maggiore precisione quale stato factory/provisioning il
fallback tenti di mutare. Una futura recovery Linux dovrà invece essere
progettata come abort fail-closed e nuova autorizzazione separata, senza
dedurla da questo comportamento OEM.

## Classificazione dell'evidenza e limiti

- `VERIFIED`: instruction bytes, branch, call target, literal, limiti dei loop
  e return nel disassembly canonico.
- `OBSERVED`: ordine e payload A8/E4/A2 nella capture D255/D256 successful.
- `INFERRED`: nomi semantici da stringhe/log, semantica ABI dei due timeout e
  classificazione factory/provisioning di `production_write_key`/E0.
- `UNKNOWN`: valore target di `N_CFG`, configurazione runtime che sceglie il
  ramo updater, contenuto/destinazione esatta del write E0 e comportamento
  device-side in un failure E4 reale.

L'assenza di una capture E4 fallita impedisce di promuovere il comportamento
device-side a `OBSERVED`, ma non indebolisce la raggiungibilità statica del
fallback persistente. Nessun secret o payload di chiave è stato estratto o
registrato.

## Riproducibilità

Il grafo annotato è in
`analysis/D278/D278_08_project8_e4_failure_graph.md`; la forma machine-readable
è in `analysis/D278/D278_08_project8_e4_edges.csv`. Il controllo offline:

```sh
python3 analysis/D278/tools/verify_d278_08_static.py
git diff --check
```

verifica schema CSV, indirizzi, unicità/consistenza degli edge, dominio delle
classi di evidenza, marker di closure e anchor xref/dataflow nel disassembly.
