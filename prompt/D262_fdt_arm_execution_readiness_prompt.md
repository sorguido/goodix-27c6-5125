# D262 — fresh-FDT arm execution-readiness review on approved D261 baseline

**Reasoning level: HIGH**

## 1. Natura dello step

Questo è il **primo step D262**, ma è ancora **OFFLINE_ONLY**.

D262 è giustificato perché prepara il nuovo confine hardware reale successivo:
il primo bounded fresh-FDT arm Linux.

IMPORTANTE: questo step NON deve eseguire hardware.
Non usare sudo, non aprire USB reale, non leggere secret reale e non eseguire
il ramo live dell'operator kit.

La baseline live-critical D261 già approvata da Utente + AI-PM è:

```text
e9073a171697bd68dd2debabb851f23d007bf718
```

Quella baseline è immutabile e resta l'autorità live-critical.

## 2. Branch di lavoro

Il lavoro corrente avviene intenzionalmente sul branch temporaneo:

```text
sandbox_free_model
```

Questo branch può contenere modifiche documentali/non-live-critical successive
alla baseline approvata.

Vincolo assoluto di questo step:

```text
D262_LIVE_CRITICAL_MODIFICATION_COUNT=0
```

Non modificare alcun file appartenente al live-critical set D261 approvato.

In particolare NON modificare:

```text
core/__init__.py
core/cold_start.py
core/fdt_lifecycle.py
core/fdt_seed.py
core/persistent_runtime.py
core/post_d4.py
core/protected_runtime.py
core/runtime_transport.py
core/tls_b0.py
core/usb_runtime.py
src/goodix5125_cleanroom.py
poc/goodix5125/tools/binding_reference/__init__.py
poc/goodix5125/tools/binding_reference/runtime.py
poc/goodix5125/tools/binding_reference/crypto_reference.py
poc/goodix5125/tools/binding_reference/pe_parser.py
tools/d261_live_fdt_arm_once.py
operator_kit/d261-live-fdt-arm-once.sh
```

Non creare un nuovo runtime/launcher D262 duplicato.

Il candidate live già revisionato è quello D261.
D262 deve verificare che sia realmente pronto per una successiva decisione
operatore, non riscriverlo.

Se per ottenere readiness fosse necessario modificare anche un solo file
live-critical, fermarsi con:

```text
OUTCOME=BLOCKED_LIVE_CRITICAL_CHANGE_REQUIRED
READY_FOR_D262_OPERATOR_EXECUTION_REVIEW=false
READY_FOR_D262_OPERATOR_EXECUTION=false
READY_FOR_FDT_LIVE=false
```

e NON applicare la modifica.

## 3. Obiettivo

Produrre una **final execution-readiness review offline** del bounded fresh-FDT
arm usando esclusivamente il candidate D261 già approvato.

Il futuro live path da validare è:

```text
A8
→ E4
→ exact cold-start pre-D1
→ D1
→ TLS 1.2 PSK handshake
→ D4 plaintext A0
→ AF / AE
→ fresh FDT:
   0x36 stage0
   → ACK
   → IRQ 0x0100
   → 0x50
   → ACK + response
   → 0x36 stage1
   → ACK
   → IRQ 0x0100
   → 0x82
   → ACK + response
   → 0x20
   → ACK
   → B0 baseline image on SAME retained TLS session
   → authenticate/decrypt/consume B0
   → 0x36 stage2
   → ACK
   → IRQ 0x0100
   → 0x32
   → ACK
→ STOP_AFTER_FDT_ARM_ACK
```

Nessuna fase successiva è autorizzata.

## 4. Boundary live futuro obbligatorio

Verificare meccanicamente che il candidate approvato abbia:

```text
D262_EXECUTION_TARGET=STOP_AFTER_FDT_ARM_ACK
FINGER_INTERACTION_REQUIRED=false
FINGER_INTERACTION_ALLOWED=false
IRQ_FINGER_DOWN_REQUIRED=false
COMMAND_0X22_REACHABLE=false
POST_FINGER_IMAGE_REACHABLE=false
ENROLLMENT_REACHABLE=false
MATCHING_REACHABLE=false
PERSISTENT_WRITE_FAMILY_COUNT=0
AUTOMATIC_RETRY_COUNT=0
AUTOMATIC_RECOVERY_COMMAND_COUNT=0
A2_0X70_RECOVERY_AFTER_FDT_FAILURE=forbidden
```

Un failure in qualunque fase deve:

```text
→ stop new traffic
→ no retry
→ no next command
→ cleanup/release
→ secret zeroization
→ fprintd/signal restore as applicable
→ durable redacted report
```

Non introdurre recovery device-side nuova.

## 5. Physical FDT policy da NON riaprire

La decisione corrente resta:

```text
0x32 zero-tail =
PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED

0x36 / 0x50 / 0x82 / 0x20 zero-tail =
EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE
UNPROVEN_LIVE_HYPOTHESIS
```

Il candidate Linux usa:

```text
physical USB OUT length = 64
logical frame unchanged
tail outside logical frame = deterministic zero-fill
residue replay = false
```

Non riaprire reverse engineering della residue tail senza nuova evidenza.

Il rischio live principale resta:

```text
PRIMARY_FUTURE_LIVE_RISK=
FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND
```

## 6. Baseline integrity review

Verificare sul repository reale che:

```text
D261_APPROVED_LIVE_BASELINE_SHA=
e9073a171697bd68dd2debabb851f23d007bf718
```

sia un full commit SHA valido.

Usare il verifier D261 esistente e/o controllo Git equivalente per dimostrare
che TUTTI i file live-critical del working tree corrente sono byte-identici ai
blob di quel commit.

Richiesto:

```text
D261_APPROVED_BASELINE_RESOLVES=true
D261_LIVE_CRITICAL_WORKTREE_MATCH=PASS
D261_LIVE_CRITICAL_MISMATCH_COUNT=0
D262_LIVE_CRITICAL_MODIFICATION_COUNT=0
```

Il branch può contenere documentazione e artefatti non-live-critical successivi:
questo non invalida la baseline.

## 7. Executable closure offline

Eseguire il percorso offline realmente previsto per l'operatore, senza sudo e
senza hardware.

Usare il launcher esistente:

```text
operator_kit/d261-live-fdt-arm-once.sh
```

con il suo ramo `--dry-run` e con cwd realistico.

Non usare il flag live.

Verificare almeno:

```text
D262_D261_OPERATOR_KIT_REUSED=true
D262_DRY_RUN=PASS
D262_DRY_RUN_REAL_USB_OPEN_COUNT=0
D262_DRY_RUN_REAL_SECRET_READ_COUNT=0
D262_DRY_RUN_REAL_COMMAND_SEND_COUNT=0
D262_DRY_RUN_REAL_MARKER_CREATE_COUNT=0
D262_DRY_RUN_FPRINTD_MUTATION_COUNT=0
```

Non alterare il launcher se il dry-run fallisce:
in quel caso riportare il failure e fermarsi.

## 8. Regression / evidence review

Senza creare nuove suite cerimoniali, rieseguire almeno:

1. targeted test D260 persistent runtime/FDT;
2. targeted test D261 operational readiness;
3. D261 import-safety test;
4. D261 live-critical baseline verifier contro
   `e9073a171697bd68dd2debabb851f23d007bf718`;
5. D261 operator `--dry-run`;
6. verifica `STOP_AFTER_FDT_ARM_ACK`;
7. verifica zero retry;
8. verifica `0x22` e post-finger path irraggiungibili;
9. verifica persistent-write families = 0;
10. `git diff --check`.

Se la full unittest suite è il regression gate canonico e ragionevolmente
eseguibile, rieseguirla; non introdurre nuove dipendenze.

## 9. Riesame metodologico pre-live

Produrre un breve blocco evidence-based con le tre risposte obbligatorie:

### 1. Cosa cambia realmente rispetto all'ultimo live boundary?

Il nuovo live test, se successivamente autorizzato dall'Utente, estenderebbe il
boundary da `STOP_AFTER_AF` al fresh-FDT arm completo fino all'ACK finale `0x32`.

### 2. Quale nuova ipotesi tecnica viene testata?

Accettazione device-side del physical fixed64/zero-tail candidate per:

```text
0x36
0x50
0x82
0x20
```

sul target APP12509, mentre `0x32` è già live-proven.

### 3. Se fallisce?

Nessun retry o patch cosmetica automatica.
Il failure specifico diventa nuova evidenza e viene revisionato prima di
qualunque nuova decisione.

## 10. Manuale canonico

Aggiornare organicamente:

```text
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

Solo per registrare:

- D261 baseline live-critical approvata:
  `e9073a171697bd68dd2debabb851f23d007bf718`;
- D262 execution-readiness review offline;
- riuso del kit D261 senza modifica live-critical;
- stato del dry-run e dei regression gate;
- rischio zero-tail invariato;
- nessuna autorizzazione hardware implicita;
- nessuna esecuzione live avvenuta;
- eventuale readiness soltanto per successiva review AI-PM/decisione Utente.

Non rendere il manuale append-only.

## 11. Readiness massima consentita

Se tutto passa:

```text
OUTCOME=READY
ADVANCEMENT=LIVE_EXECUTION_READINESS_REVIEW
EXECUTABLE_CLOSURE=PASS

D261_APPROVED_LIVE_BASELINE_SHA=e9073a171697bd68dd2debabb851f23d007bf718
D261_LIVE_CRITICAL_WORKTREE_MATCH=PASS
D262_LIVE_CRITICAL_MODIFICATION_COUNT=0

READY_FOR_D262_OPERATOR_EXECUTION_REVIEW=true
READY_FOR_D262_OPERATOR_EXECUTION=false

READY_FOR_FDT_LIVE_REVIEW=true
READY_FOR_FDT_LIVE=false
```

`READY_FOR_D262_OPERATOR_EXECUTION=false` deve restare false perché serve ancora:

1. review AI-PM del bundle;
2. decisione/autorizzazione live esplicita dell'Utente;
3. comando terminale eseguito manualmente dall'Utente.

Non auto-autorizzare hardware.

## 12. Safety

Questo step deve produrre:

```text
REAL_USB_OPEN_COUNT=0
REAL_SECRET_READ_COUNT=0
REAL_COMMAND_SEND_COUNT=0
FPRINTD_MUTATION_COUNT=0
REAL_SINGLE_USE_MARKER_CREATE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
```

Non usare sudo.
Non fermare fprintd reale.
Non leggere `/var/lib/goodix-5125-poc` per secret.
Non aprire libusb reale.
Non eseguire il ramo live.
Non creare marker reale.

## 13. Git

Non creare commit.
Non pushare.
Non fare merge, rebase, amend o reset.

Non modificare o cancellare materiale user-managed già presente, inclusa
eventuale directory:

```text
prompt/
```

Il branch atteso è:

```text
sandbox_free_model
```

Se il branch è diverso, riportarlo e fermarsi prima di modificare file.

## 14. Output D262

Creare sotto:

```text
analysis/D262/
```

almeno:

```text
D262_execution_readiness_report.md
D262_execution_readiness.json
D262_baseline_integrity_evidence.json
D262_operator_dry_run_evidence.json
D262_final_risk_boundary.json
D262_test_results.json
```

più gli eventuali piccoli artifact strettamente necessari.

Bundle finale:

```text
analysis/D262/D262_fdt_arm_execution_readiness_bundle.zip
analysis/D262/D262_fdt_arm_execution_readiness_bundle.zip.sha256
```

ZIP step-local, non cumulativo.

Includere:

- tutti gli artifact D262 modificati/prodotti necessari alla review;
- la versione aggiornata di
  `Goodix 27c6 5125 manuale tecnico.md`.

Escludere:

- raw capture;
- raw cache/OTP;
- secret;
- DLL/firmware OEM;
- plaintext image/B0;
- dati biometrici;
- materiale user-managed `prompt/`.

## 15. Closure obbligatoria

Riportare almeno:

```text
OUTCOME
ADVANCEMENT
EXECUTABLE_CLOSURE
BUNDLE
BUNDLE_SHA256

GIT_BRANCH
D261_APPROVED_LIVE_BASELINE_SHA
D261_APPROVED_BASELINE_RESOLVES
D261_LIVE_CRITICAL_WORKTREE_MATCH
D261_LIVE_CRITICAL_MISMATCH_COUNT
D262_LIVE_CRITICAL_MODIFICATION_COUNT

D262_D261_OPERATOR_KIT_REUSED
D262_DRY_RUN
D262_EXECUTION_TARGET
FINGER_INTERACTION_REQUIRED
FINGER_INTERACTION_ALLOWED
COMMAND_0X22_REACHABLE
POST_FINGER_IMAGE_REACHABLE
AUTOMATIC_RETRY_COUNT
PERSISTENT_WRITE_FAMILY_COUNT

PRIMARY_FUTURE_LIVE_RISK

READY_FOR_D262_OPERATOR_EXECUTION_REVIEW
READY_FOR_D262_OPERATOR_EXECUTION
READY_FOR_FDT_LIVE_REVIEW
READY_FOR_FDT_LIVE

CANONICAL_MANUAL_UPDATED

REAL_USB_OPEN_COUNT
REAL_SECRET_READ_COUNT
REAL_COMMAND_SEND_COUNT
FPRINTD_MUTATION_COUNT
REAL_SINGLE_USE_MARKER_CREATE_COUNT
REAL_HARDWARE_ACTION_COUNT
LIVE_EXECUTION
```

## 16. Regola finale

Se PASS, fermarsi a:

```text
READY_FOR_D262_OPERATOR_EXECUTION_REVIEW=true
READY_FOR_D262_OPERATOR_EXECUTION=false
READY_FOR_FDT_LIVE=false
```

Non eseguire il kit live.

Il passo successivo sarà esclusivamente:

1. AI-PM review del bundle D262;
2. decisione esplicita dell'Utente;
3. solo se autorizzato, comando live eseguito manualmente dall'Utente da terminale.

Aggiorna sempre organicamente il manuale tecnico canonico nella root repository
e produci il bundle ZIP step-local non cumulativo con sidecar SHA-256.
