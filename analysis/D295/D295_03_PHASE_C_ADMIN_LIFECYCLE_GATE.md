<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D295/03 — Phase C administrative lifecycle gate

**Data:** 2026-09-14

**Boundary:** rollback bidirezionale, uninstall e recovery/reinstall su Fedora
44 KDE pulita

**Stato:** READY OFFLINE; Human Gate richiesta

## Perché questo è il delta minimo

D295/01 ha provato live build, import, install e idempotenza. D295/02 ha poi
provato live update, PAM vendor invariato, login password, login fingerprint e
regressione `sudo`. Rollback, uninstall e recovery sono verdi su root sintetica
ma non sono ancora stati attraversati sul sistema Fedora reale. Sono l'unico
delta residuo esplicito della closure C.

La prova non ripete enrollment, MATCH, login o USB. Il sensore resta scollegato.
I materiali protetti e i template vengono verificati soltanto per presenza e
conteggio, senza leggerne o stamparne il contenuto.

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

## Sequenza e criteri

La sequenza canonica è in `docs/PHASE_C_SOURCE_FIRST_INSTALL.md`, sezione 8.
In sintesi:

1. rollback verso `4c9cd74...`: PAM gestito `ABSENT`, vendor invariato;
2. rollback inverso verso `b51b4c6...`: PAM gestito `ACTIVE`;
3. uninstall: baseline fprintd Fedora ripristinata, override PAM assente,
   materiali e template preservati;
4. fresh install della candidate finale: state `ACTIVE`, commit uguale al
   `SOURCE_COMMIT`, root runtime `0755`, PAM gestito attivo e materiali ready.

```text
PASS_IF=ALL_FOUR_TRANSACTIONS_PASS_AND_INVARIANTS_MATCH
FAIL_IF=ANY_TRANSACTION_OR_INVARIANT_FAILS
STOP_IF=FIRST_FAILURE
USB_REQUIRED=false
BIOMETRIC_ACTION_REQUIRED=false
PROTECTED_CONTENT_READ_REQUIRED=false
```

In caso di PASS questa evidenza soddisfa l'ultimo lifecycle richiesto dalla
closure C. Il passo seguente deve essere soltanto la formalizzazione della
closure Phase C in manuale/piano/report, commit e push su `development`, quindi
stop assoluto prima di Phase D secondo `PHASE_CLOSED => STOP`.

```text
CURRENT_TASK=D295_03_PHASE_C_ADMIN_LIFECYCLE_GATE
D295_03_OFFLINE_TESTS=10_PASS
D295_03_LIVE_EXECUTION=NOT_PERFORMED
PHASE_C_CLOSED=false
PM_DECISION=HUMAN_REQUIRED
```
