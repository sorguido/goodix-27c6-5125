# Goodix 27c6:5125 — Handoff tecnico sulla latenza di immissione impronta al login

**Data:** 16 settembre 2026  
**Repository privato:** `sorguido/goodix-27c6-5125-private`  
**Tema:** primo tentativo di login Plasma dopo cold boot; impronta appoggiata troppo presto rispetto al reale arm del sensore.

## 1. Problem statement

Il driver Goodix `27c6:5125` è ormai funzionante sul target Fedora 44 KDE per i principali casi d'uso: enrollment, verifica, `sudo`, login grafico e utilizzo ripetuto. È però emerso un problema specifico al **primo login grafico dopo cold boot**.

Sequenza osservata:

```text
cold boot
→ Plasma Login Manager
→ selezione utente / Invio
→ parte l'autenticazione fingerprint
→ se il dito viene appoggiato immediatamente:
     spesso il primo tentativo non acquisisce nulla
→ fallback password
→ un tentativo successivo o un tentativo con ~1–2 s di attesa funziona
```

La caratteristica importante è che il problema avviene **prima dell'acquisizione dell'immagine**. La race sospetta è fra inizio action libfprint/fprintd, bootstrap del protocollo Goodix, reale arm del sensore e momento in cui l'utente appoggia fisicamente il dito.

## 2. Evidenza iniziale

Le prove empiriche avevano mostrato:

```text
immediate finger: fallimento ripetibile
attesa ~10 s: successo
attesa ~5 s: successo
attesa ~2 s: successo
```

Questo orientava verso un problema di **readiness del sensore**, non di matcher o PAM.

Su Plasma Login Manager non compare necessariamente un messaggio esplicito “Appoggia il dito”. Per l'utente il vero segnale operativo è premere **Invio**, cioè “voglio fare login con impronta”. Il timing va quindi ragionato rispetto all'avvio reale dell'action.

## 3. D299 — diagnosi del failure boundary

D299 è stato costruito per capire dove morisse il primo tentativo.

Due cold-login immediate-finger hanno mostrato la stessa firma:

```text
capture_entry=1
post_tls_ack_consumed=8
post_tls_invalid_frame=0
first_irq2=0
first_cmd22=0
first_b0=0
first_decode=0
first_pipeline=0
cancel_count=1
cancel_phase=FIRST_IRQ2
```

Quindi:

- bootstrap completato;
- TLS completato;
- tre baseline FDT completate;
- FIRST_ARM `0x32` inviato;
- ACK del FIRST_ARM consumato;
- lifecycle entrato in `FIRST_IRQ2`;
- nessun nuovo IRQ `0x0002`;
- nessun `0x22`;
- nessuna immagine;
- nessun decode;
- nessuna pipeline biometrica;
- action poi cancellata/deattivata in `FIRST_IRQ2`.

Sintesi:

```text
PRIMARY_FAILURE=NO_FRESH_FINGER_DOWN_AFTER_FIRST_ARM
OBSERVED_TERMINAL_PHASE=FIRST_IRQ2
FIRST_IRQ2_COUNT=0
IMAGE_COMMAND_0X22_COUNT=0
BASELINE_DELTA_CAUSAL=false_for_observed_runs
```

Questa evidenza esclude come cause primarie matcher, template, SIGFM e qualità immagine: il failure è già **prima di `0x22`**.

## 4. Pista FDT baseline / touch flags

Sono state considerate differenze tra terza baseline, flags FDT, reverse IRQ e touch flags.

Nei due run D299:

```text
run 1: threshold 29, max delta 4
run 2: threshold 29, max delta 1
```

Quindi le baseline erano largamente entro soglia.

Una prova aveva reverse IRQ80, l'altra no. Una aveva touch flags `63`, l'altra `0`. Entrambe fallivano nello stesso punto `FIRST_IRQ2`.

Conclusione:

```text
BASELINE_DELTA_CAUSAL=false_for_observed_runs
TOUCH_FLAGS_PRIMARY_CAUSE=NOT_SUPPORTED
REVERSE_IRQ_PRIMARY_CAUSE=NOT_SUPPORTED
```

Rimane noto un run D298 separato con terza baseline fuori soglia, ma non spiega il failure D299 osservato.

## 5. Audit Rockytkg / OEM e pista POV

È stata approfondita la semantica Rockytkg/OEM.

`gx_get_mcu_state()` usa:

```text
request 0xAF
response 0xAE
state 16 byte
```

State byte 1:

```text
bit0 = POV image valid
bit1 = TLS connected
bit3 = locked
```

Semantica Rocky:

```text
POV=0
→ normale FDT-down
→ 0x32
→ IRQ2
→ image

POV=1
→ 0xD2 WakeupMCU
→ cached POV image
```

Evidenze precedenti del progetto:

```text
D251:
AF live su APP12509
POV=false
TLS=true
```

Modello D249:

```text
fresh:
POST_D4 → AF_OK/FRESH_FDT → 0x32 → IRQ2 → 0x20 → image

cached:
POST_D4 → AF_OK/POV → 0xD2 → cached image
```

Ma:

```text
TARGET_D2_OCCURRENCE=NOT_ESTABLISHED
POV_RELEASE_UP_TABLE_SEMANTICS=UNRESOLVED
```

Windows D255 aveva inoltre mostrato una sequenza target-specifica:

```text
0xD5 → 0xAF → 0x32
```

senza interazione finger, suggerendo un AF vicino al normale arm `0x32`.

Da qui l'ipotesi: il dito potrebbe diventare current durante il bootstrap e il sensore potrebbe conservare una POV image non rilevata dal nostro driver.

## 6. D300 — AF pre-capture read-only

Per testare la pista POV senza introdurre `D2`, D300 ha aggiunto un secondo `AF/GetMcuState`:

```text
dopo la terza baseline
prima di FIRST_ARM
```

Regole:

```text
POV=0
→ procedere col vecchio FIRST_ARM

POV=1
→ stop diagnostico bounded
→ NO D2
→ NO 0x32

TLS clear / risposta invalida
→ fail closed
```

Nessun retry, reset, reconnect o persistent write.

## 7. Bug dell'installer D300

Il primo tentativo D300 fallì prima della live:

```text
D300_LOCAL_PATCH=FAIL reason=d293_not_effective
```

Il problema era:

```bash
systemctl show -p ExecStart --value fprintd.service |
  grep -Fx '/usr/local/sbin/goodix-d293-native-fprintd'
```

Su Fedora reale `systemctl show` restituisce una forma strutturata tipo:

```text
{ path=/usr/local/sbin/goodix-d293-native-fprintd ;
  argv[]=/usr/local/sbin/goodix-d293-native-fprintd ;
  ... }
```

Quindi `grep -Fx` false-negativava.

Sono stati corretti:

- preflight D293;
- verifica D300 post-install;
- verifica D293 post-rollback;
- mock test per simulare l'output strutturato Fedora.

Il tentativo fallito non aveva mutato il sistema, essendo terminato prima della prima operazione mutante.

## 8. Risultato live D300

Cold run D300 con dito immediato:

```text
GOODIX_D300_PRECAP_AUDIT
precap_af_count=1
precap_af_response_count=1
precap_state_byte0=1
precap_flags=0x02
precap_pov=0
precap_tls_connected=1
precap_locked=0
precap_unknown_flags=0x00
terminal_reason=NONE
d2_send_count=0
first_arm_send_count=1
image_command_send_count=0
retry_count=0
reopen_count=0
reset_count=0
persistent_write_count=0
```

Questa prova dimostra:

```text
prima di FIRST_ARM:
POV = 0

FIRST_ARM:
inviato

image command:
0
```

Quindi la pista “dito troppo precoce → cached POV image → serve D2” è stata falsificata per il run osservato.

Sintesi:

```text
D299:
NO_FRESH_IRQ2_AFTER_FIRST_ARM = PROVEN

D300:
PRECAP_POV = 0
POV_HYPOTHESIS = FALSIFIED

D2 = NOT_RELEVANT_TO_OBSERVED_BUG
```

## 9. Nuova interpretazione del bug

Dopo D300 la spiegazione più plausibile è:

```text
dito fisicamente già presente prima che 0x32 armi FDT-down
→ sensore non genera un nuovo evento finger-down
→ nessun IRQ 0x0002
→ nessuna immagine
```

Classe probabile:

```text
FINGER_ALREADY_PRESENT_BEFORE_FDT_DOWN_ARM
```

Il driver entra correttamente in attesa di un **nuovo** finger-down, ma l'utente ha già completato fisicamente la transizione prima che il sensore fosse pronto ad osservarla.

## 10. Discussione sul workaround da 1 secondo

È stato valutato un workaround:

```text
premi Invio
→ attendi 1 secondo
→ poi sensore/login
```

Ma un semplice:

```c
sleep(1);
submit_arm(...);
```

sarebbe probabilmente controproducente:

- allarga la finestra durante la quale l'utente può già appoggiare il dito;
- dopo 1 secondo il dito può essere ancora presente;
- il `0x32` arriverebbe comunque con finger già down;
- la race potrebbe restare identica.

Quindi: **nessun delay artificiale prima di FIRST_ARM**.

## 11. Pista migliore: readiness host-side

La soluzione migliore emersa è:

```text
VerifyStart / IdentifyStart
      ↓
driver resta ACTIVATING
      ↓
pre-session sync
      ↓
TLS
      ↓
D4
      ↓
AF
      ↓
FDT baselines
      ↓
FIRST_ARM 0x32
      ↓
ACK valido FIRST_ARM
      ↓
phase = FIRST_IRQ2
      ↓
SOLO ORA:
fpi_image_device_activate_complete()
      ↓
libfprint può entrare AWAIT_FINGER_ON
```

Obiettivo:

> non dire a libfprint/fprintd che il dispositivo è pronto prima che il sensore Goodix abbia realmente ACKato il primo arm.

È una modifica di **readiness framework-side**, non di protocollo sensore.

Non richiede nuovi comandi USB, nuovi timeout, sleep, retry, reconnect, reset, D2 o persistent write.

## 12. Perché il punto corretto è l'ACK di FIRST_ARM

Il submit di `0x32` significa solo “host ha inviato FIRST_ARM”.

L'ACK significa “firmware ha accettato FIRST_ARM”.

Quindi il boundary più forte disponibile è:

```text
FIRST_ARM ACK accepted
→ lifecycle FIRST_IRQ2
→ activation complete
```

## 13. Enrollment deve rimanere invariato

Il progetto ha un path ENROLL diverso, con `first_arm_handoff`.

Per evitare regressioni:

```text
VERIFY / IDENTIFY
→ readiness callback dopo FIRST_ARM ACK

ENROLL
→ comportamento storico invariato
→ first_arm_handoff invariato
```

## 14. Rollback della catena D297–D300

Dopo le indagini è stato deciso di non lasciare la candidate “sporcata” dai correttivi diagnostici.

Commit di ritorno:

```text
73dab22227909d3496672b0a47ddd4870f078b17
docs: close Phase E release qualification
```

Parent:

```text
3feabcfb7918375ce0e04def0605c2389f95d932
```

che era la release candidate D296 qualificata.

La catena D297–D300 è stata archiviata fuori da `development`, mentre `development` è stato riportato a `73dab222...`.

## 15. Primo tentativo manuale D301

È stato creato un branch sperimentale:

```text
exp/d301-first-arm-readiness
```

con callback readiness, patch production isolata, test host-only, build D301 separata e installer reversibile.

Il primo `run_offline.sh` è fallito per una **patch malformata**:

```text
patch: **** malformed patch
```

Era un errore del diff/hunk count preparato manualmente, non una smentita della soluzione tecnica.

Per evitare ulteriore consumo di tempo si è deciso di delegare l'implementazione pulita a Codex.

## 16. Prompt Codex D301

Codex ha ricevuto un task con vincoli stretti:

```text
branch = development
baseline = 73dab22227909d3496672b0a47ddd4870f078b17

NO:
- uso del branch sperimentale
- D297/D298/D299/D300 copy
- sleep
- retry
- D2
- reset
- reconnect
- persistent write
- wire protocol change

YES:
- defer successful activation completion per VERIFY/IDENTIFY
- FIRST_ARM ACK gates readiness
- ENROLL invariato
- test espliciti
- wire equivalence
- deployment locale reversibile
```

## 17. Implementazione Codex D301

Commit prodotto:

```text
5bda2ab4bf6d86a7188dbee600fcc1f3f004d554
fix: gate activation on first-arm readiness
```

È un singolo commit sopra:

```text
73dab22227909d3496672b0a47ddd4870f078b17
```

File principali:

```text
libfprint-driver/goodix_post_tls_lifecycle.c
libfprint-driver/goodix_post_tls_lifecycle.h
libfprint-driver/goodix_fpimage_device.c
libfprint-driver/goodix_fpimage_device.h

libfprint-driver/tests/test_goodix_post_tls_lifecycle.c
libfprint-driver/tests/test_goodix_fpimage_device.c
libfprint-driver/tests/test_goodix_d278_secure_session.c

production/source-files.sha256

deployment/d301-first-arm-readiness-local/*
analysis/D301/D301_FIRST_ARM_READINESS.md

Goodix 27c6 5125 manuale tecnico.md
analysis/PROJECT_NEXT_STEPS_PLAN.md
```

## 18. Struttura tecnica D301

Nel lifecycle è stato aggiunto un callback:

```text
first_arm_ready
```

registrabile una sola volta in `NOT_STARTED`.

Nel case:

```text
GOODIX_POST_TLS_PHASE_FIRST_ARM
```

l'ordine implementato è:

```text
accept_ack()
→ se enrollment handoff:
     eseguire handoff storico
→ altrimenti:
     phase = FIRST_IRQ2
     emit first_arm_ready exactly once
```

Questa scelta preserva ENROLL.

## 19. Device adapter D301

Per VERIFY/IDENTIFY:

```text
production_activation_start_secure_graph()
```

non chiama più immediatamente:

```c
goodix_device_context_emit_arm_complete(ctx, NULL);
```

ENROLL invece mantiene il comportamento storico.

Il callback `context_first_arm_ready()` controlla:

```text
ctx != NULL
terminal_fence == false
generation != 0
lifecycle == ctx->post_tls_lifecycle
state == ACTIVATING
activation_completed == false
operator_epoch == false
production_action == VERIFY || IDENTIFY
```

e solo allora usa:

```c
goodix_device_context_emit_arm_complete(ctx, NULL);
```

Quindi non duplica la logica di activation completion.

## 20. Evidenze offline dichiarate da D301

Il report D301 registra:

```text
POST_TLS_LIFECYCLE_NORMAL=17/17_PASS
POST_TLS_LIFECYCLE_ASAN_UBSAN=17/17_PASS

FPIMAGE_DEVICE_NORMAL=32/32_PASS
FPIMAGE_DEVICE_ASAN_UBSAN=32/32_PASS

SECURE_SESSION_INTEGRATION_NORMAL=34/34_PASS
SECURE_SESSION_INTEGRATION_ASAN_UBSAN=34/34_PASS

D301_DEPLOYMENT_OFFLINE=7/7_PASS

PRODUCTION_SOURCE_CHECK=PASS
PRODUCTION_BUILD_NORMAL=PASS
PRODUCTION_BUILD_ASAN_UBSAN=PASS

PRODUCTION_ABI_LIBFPRINT_2_0_0=PASS
PRODUCTION_HOST_TEST_ONLY_SYMBOL_COUNT=0
PRODUCTION_RPATH_PRESENT=false

REAL_USB_ENUMERATION_ATTEMPTED=false
LIVE_EXECUTION_PERFORMED=false
```

## 21. Wire-equivalence

D301 dichiara di avere preservato la sequenza dei 15 OUT fisici della traccia completa.

Golden digest:

```text
fe1544bab663e8997db2b81d475f2bfbf2ea11a602b90c1e53a27320ae05950a
```

Report:

```text
OUT_COMMAND_COUNT=15
WIRE_SEQUENCE_CHANGED=false
```

L'obiettivo D301 è quindi un **framework ordering change**, non un sensor protocol change.

## 22. Deployment D301

È stato aggiunto:

```text
deployment/d301-first-arm-readiness-local/
```

Il kit dovrebbe:

- richiedere D293 integra ed effettiva;
- installare D301 in runtime parallela;
- usare wrapper/drop-in/state propri;
- non sovrascrivere D293;
- non modificare Phase-C managed deployment;
- preservare stato active/inactive di fprintd;
- fare rollback deterministico a D293;
- verificare `ExecStart` strutturato Fedora.

Questo recepisce direttamente la lezione del bug D300 su `grep -Fx`.

## 23. Stato attuale

Il commit D301:

```text
5bda2ab4bf6d86a7188dbee600fcc1f3f004d554
```

è stato prodotto e sottoposto a una prima review del codice.

La struttura implementativa osservata è coerente con il design richiesto:

```text
FIRST_ARM valid ACK
→ enrollment handoff preserva il vecchio path
→ altrimenti phase FIRST_IRQ2
→ first_arm_ready exactly once
→ VERIFY/IDENTIFY activation complete
```

Il report resta però:

```text
OUTCOME=READY_OFFLINE_PENDING_HUMAN_LIVE
PRODUCTION_READY=false
D301_FIRST_COLD_LOGIN_RESULT=NOT_OBSERVED
```

Quindi manca ancora la prova fondamentale:

> un singolo cold login reale con dito appoggiato immediatamente dopo Invio.

## 24. Piste da NON riaprire senza nuova evidenza

```text
1. matcher / SIGFM come causa primaria
   → escluso: failure avviene prima di 0x22

2. baseline delta come causa primaria dei run D299
   → escluso per i run osservati

3. reverse IRQ / touch flags come causa primaria
   → non supportato dalle evidenze D299

4. POV cached image come spiegazione del failure
   → falsificata da D300: precap_pov=0

5. D2 come fix del failure osservato
   → non giustificato

6. sleep arbitrario prima di FIRST_ARM
   → semanticamente sbagliato e potenzialmente peggiorativo

7. nuovi retry/reopen/reset
   → non necessari per testare D301

8. ripetere D297–D300 solo per maggiore confidenza
   → non utile
```

## 25. Ipotesi tecnica corrente

Ipotesi più forte:

```text
libfprint/fprintd considera l'action pronta
prima che il Goodix abbia realmente ACKato FIRST_ARM

utente appoggia il dito
→ transizione fisica avviene troppo presto

poi il Goodix entra FIRST_IRQ2
→ aspetta una nuova transizione
→ nessun IRQ2
```

D301 cerca di correggere precisamente l'ordine:

```text
PRIMA:
activation complete
→ user finger
→ FIRST_ARM

DOPO D301:
FIRST_ARM ACK
→ activation complete
→ user finger
```

## 26. Prossimo test consigliato

Una sola live iniziale è sufficiente perché il fenomeno da misurare è il **primo tentativo cold-login**.

Procedura concettuale:

```text
1. partire dalla baseline reale D293
2. installare D301 local patch
3. power-off completo
4. power-on
5. Plasma Login
6. premere Invio
7. appoggiare immediatamente il dito, come normalmente farebbe l'utente
8. osservare il primo tentativo
9. raccogliere journal
10. rollback a D293 dopo raccolta evidenza
```

## 27. Interpretazione dei possibili esiti

### Caso A — primo login funziona

Interpretazione:

```text
D301 hypothesis strongly supported
```

La race era verosimilmente nell'activation readiness host-side.

Passi successivi:

- piccolo numero di cold-run di conferma;
- regressione sudo/login normale;
- verifica ENROLL non regredito;
- integrare D301 nella candidate;
- riqualificare il delta minimo;
- aggiornare release candidate e poi Phase F.

### Caso B — failure identico: FIRST_IRQ2 senza IRQ2

Se D301 fallisce ancora nello stesso modo:

```text
FIRST_ARM ACK
→ FIRST_IRQ2
→ no IRQ2
```

allora la race non dipende soltanto da `activate_complete()`.

La nuova domanda diventerebbe:

> il dito può essere fisicamente appoggiato prima che l'ACK di FIRST_ARM venga processato, indipendentemente da ciò che libfprint comunica?

In quel caso servirebbe studiare un boundary device-side / finger-presence più profondo. Non aggiungere automaticamente sleep o retry.

### Caso C — failure in punto diverso

Sarebbe comunque progresso.

Il journal va usato per vedere se D301 ha spostato la failure:

```text
FIRST_IRQ2 presente?
0x22 presente?
immagine presente?
decode?
pipeline?
```

La nuova failure boundary determinerebbe il passo successivo.

## 28. Informazioni operative da conservare

Baseline pre-D301:

```text
development clean:
73dab22227909d3496672b0a47ddd4870f078b17

D296 release candidate:
3feabcfb7918375ce0e04def0605c2389f95d932
```

D301:

```text
5bda2ab4bf6d86a7188dbee600fcc1f3f004d554
fix: gate activation on first-arm readiness
```

Known-good target runtime prima del corrective:

```text
D293
/usr/local/lib64/goodix-27c6-5125/d293-native-e61fce313794922a2dab156a1b38a8ddc5837f19

wrapper:
/usr/local/sbin/goodix-d293-native-fprintd

drop-in:
95-goodix-d293-native.conf
```

## 29. Sintesi ultra-compatta per ripresa futura

```text
BUG:
primo cold login fallisce se dito troppo precoce

D299:
FIRST_ARM ACKato
ma nessun IRQ2
→ nessuna immagine

D300:
AF immediatamente pre-capture
POV=0
→ pista cached POV / D2 falsificata

INTERPRETAZIONE:
dito già fisicamente presente prima del vero arm
→ nessun nuovo finger-down event

WORKAROUND DA EVITARE:
sleep arbitrario prima di 0x32

D301:
non cambiare protocollo
non cambiare timing USB
non aggiungere retry

spostare activation_complete:
da "secure graph started"
a "FIRST_ARM ACK accepted / FIRST_IRQ2"

ENROLL:
invariato

STATO:
offline PASS dichiarato
wire sequence dichiarata identica
manca ancora live target cold-login
```

## 30. Boundary corretto per una futura ripresa

```text
CURRENT_CORRECTIVE=D301_FIRST_ARM_READINESS
CURRENT_COMMIT=5bda2ab4bf6d86a7188dbee600fcc1f3f004d554

NEXT_REAL_QUESTION:
"Il primo cold login con dito immediato funziona quando activation_complete
viene emesso solo dopo l'ACK di FIRST_ARM?"

NEXT_ACTION_CLASS:
HUMAN_REQUIRED_TARGET_LIVE
```

Tutto ciò che precede serve ormai come evidenza storica e soprattutto per evitare di riaprire piste già falsificate.
