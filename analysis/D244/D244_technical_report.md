# D244 — E4 timeout forensic e fresh-state control

## Decisione

`D244_FRESH_STATE_CAUSAL_CONTROL_READY_NOT_EXECUTED`

Non è emersa una regressione software pre-E4 concreta nel path D241↔D243. Il
logical E4 coincide, le semantiche A0 D241/D243 coincidono sul frame valido,
endpoint/timeout/open/claim/read assembly coincidono e il generic fixed-64 A0
D242 è completamente rimosso in D243. D244 non cambia quindi wire, timeout o
retry: prepara un controllo causale dello stato iniziale dopo shutdown completo
e riaccensione manuale.

## Evidenze live

Le copie locali D242 e D243 sono regular file, JSON validi e byte-exact rispetto
ai digest forniti. Tutti i campi richiesti coincidono. Non sono state lette
directory root-only e gli artefatti storici non sono stati modificati.

```text
D244_D242_LIVE_RESULT_INGESTED=true
D244_D242_LIVE_REPORT_STATUS=PRIMARY_LOCAL_EVIDENCE_VERIFIED
D244_D242_LIVE_REPORT_SHA256=1d9c2c736a2b8939855a184e350ea2ecaa914921536ae2a2d616130a166eb7e7
D244_D243_LIVE_RESULT_INGESTED=true
D244_D243_LIVE_REPORT_STATUS=PRIMARY_LOCAL_EVIDENCE_VERIFIED
D244_D243_LIVE_REPORT_SHA256=a82c43f4aba5c6f9dcfe072eee7b8b6ab0edc7f621961ea6a322dfe6ac45aa23
D244_D243_LIVE_FAILURE_CLASS=timeout
D244_D243_LIVE_ATTEMPTED_PHASE=E4
D244_D243_LIVE_COMMAND_COUNT=1
D244_D243_LIVE_USB_OPEN_COUNT=1
```

## Correzione epistemica A0/B0

```text
D243_A0_FIXED64_CAUSAL_STATUS=FALSIFIED_AS_SUFFICIENT_EXPLANATION_BY_D243_LIVE
D244_A0_FIXED64_DEVICE_EQUIVALENCE_STATUS=UNRESOLVED
D244_B0_FIXED64_DEVICE_EQUIVALENCE_STATUS=NOT_YET_LIVE_REACHED
```

La capture D175 prova submission host-side da 64 byte, non equivalenza
device-side della tail. D243 prova che il ripristino dell'OUT corto non basta a
recuperare E4. Nessuna delle run D242/D243 ha raggiunto B0/TLS.

## Direzione del timeout

Control flow verificato:

```text
exchange(E4)
  -> write_frame(E4)
     -> bulk OUT
     -> verifica completion full-length
     -> command_count += 1
  -> read_frame()
     -> bulk IN
     -> frame assembly
  -> UsbTimeout -> ReplayAbort(timeout) / usb_transport
```

Risposte alle domande bloccanti:

1. `command_count=1` significa comando completato in OUT, non solo tentato.
2. Sì: con E4 primo/unico comando prova completion bulk OUT full-length.
3. Un timeout può provenire da OUT, ma in tal caso `command_count` resta zero.
4. Un timeout può provenire da IN; è il caso compatibile con i due report.
5. `command_count`, insieme a `attempted_phase=E4` e alla sequenza single-shot,
   distingue già i casi. Non è servita nuova strumentazione.

```text
D244_E4_TIMEOUT_DIRECTION=IN_CONFIRMED_AFTER_OUT_COMPLETION
D244_TIMEOUT_DIRECTION_OBSERVABILITY_ADDED=false
```

## E4 byte-exact

Il core D241 è presente nello ZIP; D242 e D243 pin-nano lo stesso SHA-256 del
core. Tutti i runtime generano:

```text
hex=a00c00ace40900030002bb00000000fd
length=16
sha256=b6ada1adde00249e4e55f41bbf7c00443409c3752050520bc1a1874b0b63cf1a
match=true
```

Vale separatamente per D241, D242, D243 e D244.

## Differenziale D241↔D242↔D243

Gli ZIP storici e i sidecar coincidono. Hash backend: D241
`ffde5165...53b2cb5f`, D242 `c072db52...e90fcef`, D243
`e537f33d...458c982`. Gli hash AST di `write_frame` sono distinti, quindi il
codice D241/D243 non è byte-identico. Sul frame A0/E4 valido, però, validazione e
telemetria D243 non cambiano endpoint, byte, requested length, completion,
deadline o eccezioni. Il dettaglio completo è nel CSV differenziale.

```text
D244_D242_FIXED64_A0_FULLY_REMOVED_IN_D243=true
D244_D243_E4_CODE_BYTE_IDENTICAL_TO_D241=false
D244_D243_E4_RUNTIME_SEMANTICS_EQUIVALENT_TO_D241=true
D244_D241_D243_PRE_E4_DIFF_COUNT=8
D244_D241_D243_PRE_E4_BEHAVIOR_RELEVANT_DIFF_COUNT=5
D244_D241_D243_PRE_E4_UNRESOLVED_CANDIDATE_COUNT=0
```

Le cinque differenze behavior-relevant sono intenzionali e host-side
(namespace, integrity/closure gate e preflight); nessuna cambia wire o timing
E4. Le differenze di validazione/telemetria attraversano lo stesso ramo sul
frame canonico. B0 fixed-64 e pacing sono differenze non raggiunte al timeout.

## Stato iniziale e fresh-state control

D241 non eseguì alcun reset device/USB/A2, re-enumeration, power-cycle o
protocol close nel cleanup. Un boot host intervenne fra D241 e D242, mentre
D242 e D243 ricadono nello stesso boot. Questo indebolisce, senza falsificare,
il carryover e non prova un power-cycle elettrico del sensore.

```text
D244_POST_D241_DEVICE_STATE_RESET_OBSERVED=false
D244_INITIAL_STATE_CARRYOVER_STATUS=WEAKENED_BY_INTERVENING_BOOT
D244_FRESH_BOOT_DOCUMENTED=false
D244_FRESH_BOOT_EVIDENCE=combination
D244_FRESH_STATE_CONTROL_VALID=not_applicable_offline
```

Il launcher futuro richiede conferma esplicita di shutdown completo +
riaccensione e confronta boot-id/uptime/journal con la baseline D243. Stesso
boot o metadati insufficienti producono `VALID=false`, ma nessun metadato host
viene presentato come prova elettrica del sensore.

## Wire, durability e safety

```text
D244_RUNTIME_WIRE_CHANGED_FROM_D243=false
A0=ultimo OUT corto, nessuna tail artificiale
B0=chunk fisici 64 byte zero-initialized
TLS_RECORD_PACING_MS=10 per record server-side
retry=0
D4=0
application_data=0
persistent_write=0
```

La fixture timeout E4 conserva il modello esistente: abort runtime; cleanup e
zeroizzazione exactly-once; checkpoint atomico con `report_publish_count=1`
prima del restore; restore; report finale con `report_publish_count=2`. Release,
close ed exit sono ciascuno exactly-once.

## Stato finale

```text
D244_OPERATOR_KIT_CREATED=true
D244_EXECUTABLE_CLOSURE_GATE=PASS
D244_MANUAL_UPDATED=true
D244_REAL_USB_ACCESS_DURING_CODEX=0
D244_REAL_TLS_HANDSHAKE_DURING_CODEX=0
D244_BUNDLE_PATH=analysis/D244/D244_e4_timeout_forensic_fresh_state_control_bundle.zip
```

Il digest del bundle è pubblicato nel sidecar esterno dopo il packaging.
