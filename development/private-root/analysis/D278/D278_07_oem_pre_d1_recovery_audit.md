# D278/07 — audit offline della recovery OEM pre-D1

> **Nota di supersessione D278/08.** Questo file conserva la conclusione
> storica raggiunta in D278/07. D278/08 ha poi risolto il boundary: dopo il
> ritorno di `gfUpdatefirmware`, `init_MCU` chiama direttamente il production
> process a `0x18006ae04`, che raggiunge l'E4 tramite
> `0x18003c348 -> 0x18003b514 -> 0x18003cc90 -> 0x18003c7f4`. Inoltre
> `0x18003cfd8` è `production_write_key`, non un wrapper E4: dopo due check
> falliti porta a `production_write_mcu`/E0. Lo stato canonico corrente è in
> `D278_08_project8_e4_indirect_edge_audit.md` e nel manuale tecnico.

## Closure

```text
OUTCOME=BLOCKED
ADVANCEMENT=NEW_STATIC_TARGET_SPECIFIC_A8_FAILURE_POLICY_CLOSED_AND_E4_TARGET_EDGE_ISOLATED_AS_THE_REMAINING_BOUNDARY
EXECUTABLE_CLOSURE=ANALYSIS_ONLY
RESIDUAL_BLOCKER_OR_RISK=THE_PROJECT_8_GFUPDATEFIRMWARE_PATH_REACHES_E4_BY_AN_UNRESOLVED_INDIRECT_OR_DATA_DRIVEN_EDGE_SO_ITS_EXACT_E4_FAILURE_BRANCH_RETRY_BOUND_AND_RETURN_PROPAGATION_ARE_NOT_CLOSED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_1682e01bcc2817f5a0b5028ab6bf4bcac32a61d0_ON_main_PLUS_WORKTREE_DIFF_PLUS_analysis/D278/D278_06_zero_out_precommand_observation.md_PLUS_analysis/D278/D278_07_oem_pre_d1_recovery_audit.md_PLUS_analysis/D278/D278_07_oem_pre_d1_recovery_matrix.csv_PLUS_Goodix_27c6_5125_manuale_tecnico.md

D278_06_LIVE_BASELINE=1682e01bcc2817f5a0b5028ab6bf4bcac32a61d0
D278_06_LIVE_OUTCOME=VALID_SINGLE_SHOT_TIMEOUT_NO_DATA
D278_06_RECEIVED_BYTE_COUNT=0
D278_06_GOODIX_BULK_OUT_SUBMIT_COUNT=0
D278_06_PHYSICAL_BULK_IN_SUBMIT_COUNT=1
D278_06_TIMEOUT_COUNT=1
D278_06_CLEANUP_COMPLETED=true
D278_06_RETRY_AUTHORIZED=false

IMMEDIATE_PRECOMMAND_BACKLOG_WITHIN_1000MS=NOT_OBSERVED
DEVICE_PROTOCOL_QUIESCENCE_PROVEN=false
APP12509_READY_FOR_A8_PROVEN=false

OEM_PRE_D1_FAILURE_RECOVERY=UNRESOLVED
OEM_A8_FAILURE_POLICY=RESOLVED
OEM_E4_FAILURE_POLICY=UNRESOLVED
OEM_USES_A2_SENSOR_ONLY_AS_PRE_A8_FAILURE_RECOVERY=false
A8_RETRY_BOUND_RUNTIME_VALUE=UNKNOWN_CONFIG_BYTE_AT_OFFSET_0x45A

A2_HOST_SEMANTICS=CONVERGED_SENSOR_ONLY_RESET
A2_PRE_A8_RECOVERY_LIVE_JUSTIFIED=false
D278_07_RECOVERY_CANDIDATE_IMPLEMENTED_HOST_ONLY=false

REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

## Baseline, metodo e limiti

L'audit è iniziato su branch `main`, tree pulito, con `HEAD` e `origin/main`
coincidenti a `1682e01bcc2817f5a0b5028ab6bf4bcac32a61d0`. È totalmente
offline. Non sono stati enumerati o aperti device, eseguiti launcher live,
inviati A8/E4/A2, letti store protetti o usati `sudo`, TLS, PSK, reset,
clear-halt, reopen o power-cycle. Il path D278/03 live-critical non è stato
modificato.

La fonte statica primaria è `analysis/D230/work/GoodixExport/gfusb.dll`,
versione 1.1.125.14, con il disassembly locale
`analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_disasm.txt`. Nomi
funzione usati qui provengono dalle stringhe/log e dagli audit D230/D231; gli
indirizzi virtuali e i branch sono invece verificati nel disassembly. Il grafo
di call dirette è usato solo come ausilio: l'assenza di un edge diretto non
esclude dispatch indiretti, callback o dataflow attraverso tabelle.

Il corpus dinamico considerato è D255/D256. Contiene una init OEM riuscita e
non una finestra A8/E4 fallita: il postprocess riporta
`OEM_LOG_STATUS=ABSENT` e `OEM_LOG_SOURCE_COUNT=0`. L'assenza di failure
capture è un limite, non prova dell'assenza di recovery OEM.

## Identificazione del target OEM

Il confronto della stringa `USB\\VID_27C6&PID_5125` a `0x1800141a2` porta il
ramo a `0x1800141b8`, che assegna `8` al project selector globale
`0x1805783c0`. Le conclusioni chiamate target-specifiche sotto richiedono
quindi un branch esplicito `project == 8`; i percorsi per altri project o i
builder E4 generici non vengono promossi a prova APP12509.

## Propagazione comune di init

`InitThread` (`0x1800148d0`) legge il byte configurabile a offset `0x45a` in
`N_CFG`. Dopo il setup iniziale e `_TlsInitAndHandShake` (`0x18001e258`), il
loop `0x180014e1e..0x180014f07` chiama `_DeviceInit` (`0x18001ded8`) al massimo
`N_CFG` volte. Un ritorno non zero viene registrato come
`!!!!Init: _DeviceInit failed in %d try` e normalmente fa ripartire l'intera
`_DeviceInit`; condizioni globali/fatal e `0xffdffff3` imboccano invece l'uscita
immediata. Il valore concreto di `N_CFG` nella configurazione target non è
presente nel corpus, perciò il limite è strutturalmente bounded ma il numero
runtime esatto resta unknown.

`_DeviceInit` chiama prima `init_MCU` (`0x18006a7b0`). Un suo errore viene
restituito al caller; solo dopo il successo passa a `init_FP` (`0x180069d30`).
Questo colloca gli errori A8 e l'E4 della init MCU nel tratto pre-D1.

## Policy A8: risolta

La catena A8 è chiusa fino alla policy di re-entry:

```text
InitThread 0x1800148d0
  -> _DeviceInit 0x18001ded8
    -> init_MCU 0x18006a7b0
      -> GetEvkVersionWithRetry 0x180059d00 (N_CFG)
        -> get-version 0x180059b38, timeout response 500 ms
        -> exact A8 builder/send 0x180059c18..0x180059c5e
      -> after N_CFG failures: HardResetMcu 0x18000f938
        -> project == 8 branch 0x18000fd4f..0x18000fdc5
          -> MCU software reset 0x18005a33c, exact payload {0x02,0x14}
      -> exactly one final get-version at 0x180059ecf
      -> false => init_MCU returns 0xffcffffd at 0x18006a968
    -> error bubbles from _DeviceInit
  -> normal error path retries whole _DeviceInit up to N_CFG
```

Il singolo attempt `0x180059b38` usa un response timeout di 500 ms. Il builder
`0x180059c18..0x180059c5e` passa control `0xA8` al generic send e configura
l'ACK timeout a 100 ms; il loop interno `0x180059dc4..0x180059e12` ha
esattamente `N_CFG` attempt. Dopo l'esaurimento, salvo il flag speciale D0Exit,
il codice chiama `HardResetMcu` e compie una sola A8 aggiuntiva.

Per project 8 `HardResetMcu` non usa una linea hard-reset: il ramo
`0x18000fd4f..0x18000fdc5` registra che gli EC project non supportano quel
reset, azzera il flag di contesto e chiama `0x18005a33c`. Quest'ultima routine
costruisce A2 con body `{0x02,0x14}`, cioè reset MCU software. È un USB OUT
volatile ma non è il sensor-only A2 `{0x01,0x14}`. Non c'è evidenza di write
persistente in questa catena.

La policy A8 è quindi `RESOLVED` come call-flow target-specifico, bounded e
con propagazione d'errore. Ciò non la rende automaticamente una recovery sicura
da trapiantare: contiene retry annidati, un reset MCU e ripartenze dell'intera
`_DeviceInit`, ed il valore runtime di `N_CFG` non è chiuso.

## A2 sensor-only: non è recovery pre-A8

La semantica host dell'A2 sensor-only converge indipendentemente in D231/D233:
`gfresetMCUAndfingerprint` (`0x180069880`) riceve a `0x1800644a1` gli argomenti
`reset_mcu=false`, `reset_sensor=true`, delay 500 ms e costruisce il body esatto
`{0x01,0x14}`. Tuttavia quel call site non è raggiunto dal failure branch A8
sopra.

La capture OEM riuscita D255/D256 corrobora una diversa posizione: A8
request/ACK/typed ai frame 48/50/52, E4 request/ACK/typed ai frame 54/56/58 e
A2 sensor-only ai frame 60/62/64; un secondo A2 compare ai frame 78/80/82.
Questa è sequenza di successo post-E4, non recovery da A8 o E4 fallita.

Pertanto:

```text
OEM_USES_A2_SENSOR_ONLY_AS_PRE_A8_FAILURE_RECOVERY=false
A2_PRE_A8_RECOVERY_LIVE_JUSTIFIED=false
```

La conclusione `false` riguarda il software/corpus OEM auditato: il failure
branch A8 osservabile usa `{0x02,0x14}`, non `{0x01,0x14}`. Non afferma che
nessun altro software o build OEM possa mai usare l'A2 sensor-only in tale
ruolo.

## Policy E4: boundary non risolto

Sono stati separati tre livelli che non possono essere unificati senza un
edge target-specifico:

1. `production_read_mcu` (`0x18003c7f4`) costruisce E4 a `0x18003c94c`. Se il
   generic send ritorna zero, ripete immediatamente una volta a
   `0x18003c9a1`; due failure portano a `0xffdffffd`. Il wrapper
   `0x18003cfd8` è chiamato dal production process `0x18003c348`, che ha a sua
   volta due bounded invocation. È una policy statica verificata per quel
   percorso.
2. `init_MCU` chiama `0x18003c348` per alcuni gruppi di project a
   `0x18006aa72`/`0x18006ae04`, ma project 8 prende invece il branch
   `0x18006abec` e chiama `gfUpdatefirmware` (`0x180064a18`) a
   `0x18006ac4c` con il firmware incorporato.
3. La capture target mostra che project 8 invia davvero E4 dopo la seconda A8.
   Tuttavia il grafo di call dirette da `gfUpdatefirmware`/`0x1800656f4` non
   raggiunge `0x18003c7f4`, `0x18003cfd8`, `0x18003c348` o il builder generico
   E4 `0x18005b4bc`. Il dispatch che riconcilia il wire osservato con il ramo
   statico è quindi ancora indiretto o data-driven.

Il percorso firmware-update non è un candidato prudente: le stringhe e i
branch locali includono clear/update APP, erase e reset MCU; i path di cleanup
in `0x1800656f4` chiamano anche `HardResetMcu` e poi
`GetEvkVersionWithRetry`. Senza il preciso edge E4, il relativo branch di
errore e la propagazione del suo codice di ritorno, non è possibile stabilire
se project 8 ripeta solo E4, ripeta un blocco più ampio, resetti MCU, riavvii
firmware update o risalga al retry esterno `_DeviceInit`. Il rischio di effetto
persistente del wrapper firmware-update impedisce inoltre di trattarlo come
recovery Linux safe.

Per questo la policy E4 target-specifica e la recovery pre-D1 complessiva
restano `UNRESOLVED`, anche se una routine E4 generica con retry bounded è
stata verificata.

## Primitive alternative escluse

- `SetDriverState` (`0x18005c724`) invia il control `0x97` e ritenta una volta
  il medesimo send. Dopo il secondo failure, per project diverso da 4 chiama
  `HardResetMcu`; per project 8 ciò degrada ad A2 `{0x02,0x14}`. È una recovery
  generica di un'altra command family e non esiste un edge da failure A8/E4.
- `ResetUsbPort` (`0x180065fc4`) ferma le pipe, resetta la porta e le riavvia,
  ma il call site trovato è un dispatcher ampio (`0x180063d46`), non il ramo
  pre-D1 target A8/E4. Implica reset host/device ed è unsafe come candidato.
- D0Entry/D0Exit, close/reopen e cancellazione sono nomi/lifecycle generici;
  D256 mostra nel path osservato solo cancellazione host del pending IN e zero
  abort/reset/reconfiguration/descriptor/re-enumeration. Non chiudono una
  recovery A8/E4.
- Non è stato identificato un clear-halt target-specifico nel call-flow
  pre-D1. L'assenza di stringhe o edge non è prova che la DLL non possieda
  primitive equivalenti.

## Corroborazione dinamica e D278/06

La D278/06 autorizzata una sola volta sulla baseline
`1682e01bcc2817f5a0b5028ab6bf4bcac32a61d0` ha prodotto una completion
`TIMEOUT_NO_COMPLETE_DATA`: un physical IN submit/completion, zero byte, zero
OUT/comandi/TLS/retry/reopen/reset/clear-halt/write persistenti e cleanup
completo. Dimostra `IMMEDIATE_PRECOMMAND_BACKLOG_WITHIN_1000MS=NOT_OBSERVED`.
Non dimostra quiescenza o readiness per A8, e il discriminante non va ripetuto.

La D255/D256 successful path dimostra il wire target A8 -> E4 -> A2 e la
continuità USB del path osservato. Non contiene A8/E4 timeout, ACK non-success,
init abort, reset seguito da A8, A2 pre-A8, close/reopen o re-enumeration in una
failure window. Non può quindi scegliere tra le recovery E4 staticamente
possibili.

## Decisione e unico prossimo discriminante

Il Caso B del prompt si applica: nessuna recovery ipotetica viene
implementata. In particolare non sono autorizzati A2 esplorativo, A8, reset
USB, clear-halt, pacing, timeout più lungo o una seconda zero-OUT.

L'unico prossimo discriminante proposto è **offline sul DLL locale già
disponibile**: risolvere il dispatch indiretto/dataflow dal branch project 8
`init_MCU:0x18006abec -> gfUpdatefirmware:0x180064a18 -> 0x1800656f4` fino
all'esatto builder E4 osservato, quindi seguire entrambe le uscite del send fino
al return di `init_MCU`. L'audit deve produrre un edge verificabile (slot di
vtable/callback o tabella e relativa assegnazione), non una somiglianza tra
stringhe. Solo questo discriminante può chiudere numero di tentativi, reset,
wire effect e rischio persistente della failure E4 target-specifica senza
chiedere nuova live.

## Verifiche host-only dello step

Non essendoci modifiche a sorgenti o test, non sono state eseguite suite
runtime non pertinenti. Sono stati verificati offline lo schema CSV e tutte le
classificazioni ammesse, la presenza dei marker obbligatori, la corrispondenza
della telemetria JSON D278/06 e la pulizia whitespace del diff.

```text
D278_07_CSV_SCHEMA=PASS_13_REQUIRED_COLUMNS
D278_07_CSV_ROWS=12
D278_07_EVIDENCE_CLASS_DOMAIN=PASS
D278_06_EXACT_TELEMETRY_INTEGRATION=PASS
D278_07_REQUIRED_MARKERS=PASS
GIT_DIFF_CHECK=PASS
SOURCE_TESTS=NOT_RUN_DOCUMENTATION_AND_OFFLINE_STATIC_AUDIT_ONLY
REAL_USB_ACCESS=false
```
