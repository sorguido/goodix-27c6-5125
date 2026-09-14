<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D295/03 — Phase C administrative lifecycle gate

**Data:** 2026-09-14

**Boundary:** rollback bidirezionale, uninstall e recovery/reinstall su Fedora
44 KDE pulita

**Stato:** PASS live osservato dall'Utente; Phase C chiusa

## Perché questo è il delta minimo

D295/01 ha provato live build, import, install e idempotenza. D295/02 ha poi
provato live update, PAM vendor invariato, login password, login fingerprint e
regressione `sudo`. D295/03 ha ora attraversato sul sistema Fedora reale anche
rollback, uninstall e recovery, completando l'ultimo delta della closure C.

La prova non ha ripetuto enrollment, MATCH o login e non ha usato USB: il
sensore è rimasto scollegato. I materiali protetti sono stati verificati
soltanto per presenza e i template soltanto per conteggio, senza leggerne o
stamparne il contenuto.

## Stato di ingresso atteso

```text
CURRENT_COMMIT=b51b4c6f6141e0651e251291745d9b48b08d8da6
PREVIOUS_COMMIT=4c9cd74cc02890080851c1dca0a5889c58981f77
MANAGED_PAM_STATUS=ACTIVE
PROTECTED_MATERIAL_READY=true
```

Prima della transazione si costruisce una candidate dal nuovo HEAD finale e si
verificano `SHA256SUMS` e `SOURCE_COMMIT`. La candidate resta fuori dal
repository.

## Evidenza live ricevuta

La candidate finale è stata costruita dal commit
`448f5c8cc6099032a23115a96e90428d75b74a7b`; verifica `SHA256SUMS` e
`SOURCE_COMMIT` sono PASS.

### 1. Rollback verso il precedente

```text
D295_03_ROLLBACK_TO_PREVIOUS=PASS
CURRENT_COMMIT=4c9cd74cc02890080851c1dca0a5889c58981f77
MANAGED_PAM_STATUS=ABSENT
PLASMALOGIN_VENDOR_MODIFIED=false
PLASMALOGIN_VENDOR_HASH_UNCHANGED=true
```

L'override `/etc/pam.d/plasmalogin` era assente come previsto.

### 2. Rollback inverso

```text
D295_03_ROLLBACK_BACK_TO_CURRENT=PASS
CURRENT_COMMIT=b51b4c6f6141e0651e251291745d9b48b08d8da6
MANAGED_PAM_STATUS=ACTIVE
PLASMALOGIN_VENDOR_MODIFIED=false
PLASMALOGIN_VENDOR_HASH_UNCHANGED=true
```

L'override PAM gestito è stato ripristinato come previsto.

### 3. Uninstall

```text
D295_03_UNINSTALL=PASS
MANAGED_PAM_REMOVED=true
RUNTIME_REMOVED=true
WRAPPER_REMOVED=true
PLASMALOGIN_VENDOR_HASH_UNCHANGED=true
PROTECTED_MATERIAL_DIR_PRESERVED=true
PROTECTED_MATERIAL_FILES_PRESERVED=true
TEMPLATE_COUNT_PRESERVED=true
STATUS_AFTER_UNINSTALL=EXPECTED_FAILURE
```

### 4. Recovery mediante fresh reinstall

```text
D295_03_FRESH_REINSTALL=PASS
CURRENT_COMMIT=448f5c8cc6099032a23115a96e90428d75b74a7b
PHASE_C_STATUS=ACTIVE
PROTECTED_MATERIAL_READY=true
MANAGED_PAM_INTEGRATION=true
MANAGED_PAM_STATUS=ACTIVE
PLASMALOGIN_VENDOR_MODIFIED=false
RUNTIME_ROOT_MODE=0755
PLASMALOGIN_VENDOR_HASH_UNCHANGED=true
```

La VM resta intenzionalmente sulla nuova baseline gestita `448f5c8...`.

## Review PM e closure

La sequenza ha provato sul target reale:

- rollback simmetrico in entrambe le direzioni;
- uninstall completo del runtime gestito e dell'override PAM;
- preservazione di materiali protetti e template fprintd;
- recovery con reinstallazione fresca della candidate finale;
- PAM vendor Fedora invariato e root runtime `0755`.

```text
PASS_IF=ALL_FOUR_TRANSACTIONS_PASS_AND_INVARIANTS_MATCH
RESULT=PASS
USB_USED=false
BIOMETRIC_ACTION_USED=false
PROTECTED_CONTENT_READ=false
TEMPLATE_CONTENT_READ=false
```

L'evidenza soddisfa l'ultimo lifecycle richiesto dalla closure C. Phase C è
formalmente chiusa; dopo documentazione, commit e push il progetto si arresta
prima di qualunque preparazione di Phase D.

```text
D295_03_OFFLINE_TESTS=10_PASS
D295_03_LIVE_EXECUTION=PASS_HUMAN_OBSERVED
D295_03_ROLLBACK_BIDIRECTIONAL=PASS
D295_03_UNINSTALL=PASS
D295_03_PROTECTED_MATERIAL_PRESERVATION=PASS
D295_03_TEMPLATE_PRESERVATION=PASS
D295_03_RECOVERY_REINSTALL=PASS
D295_03_FINAL_BASELINE_COMMIT=448f5c8cc6099032a23115a96e90428d75b74a7b
PHASE_C_CLOSURE_CRITERIA=PASS
PHASE_C_CLOSED=true
NEXT_PHASE=D
PM_DECISION=PROJECT_STEP_COMPLETE
PHASE_CLOSED => STOP
```
