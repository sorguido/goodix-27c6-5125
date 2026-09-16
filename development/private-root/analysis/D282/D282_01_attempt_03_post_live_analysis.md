<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/01 attempt 03 — analisi post-live e correttivo pre-live

## Decisione AI-PM

```text
OUTCOME=CORRECTIVE
ADVANCEMENT=FPRINTD_TARGET_SIGFM_ENROLL_8_OF_8_AND_SAME_FINGER_VERIFY_MATCH_OBSERVED
EXECUTABLE_CLOSURE=ATTEMPT_03_PARTIAL_LIVE_PLUS_HASH_PINNED_EVIDENCE_AUDIT
RESIDUAL_BLOCKER_OR_RISK=DIFFERENT_FINGER_NO_MATCH_AND_DELETE_NOT_REACHED
CANONICAL_DOCUMENTATION=GOODIX_TECHNICAL_MANUAL_UPDATED
REVIEW_SET=GIT_NATIVE
```

L'attempt 03 ha eseguito la baseline
`42903b70c89b2399bef35f4a4c7eb8c9dc5d04e5`. I tre allegati sono importati
byte-identici e hash-pinned sotto
`captures/D282_01/D28201_ATTEMPT_03_42903b70/`. Il documento narrativo
operatore allegato è distinto dall'evidenza primaria e ne viene registrato il
digest nella provenance.

## Risultato osservato e limite probatorio

Il contesto operatore attesta otto `enroll-stage-passed`, un
`enroll-completed` e, dopo restart del daemon, un `verify-match` dello stesso
indice destro. Il raw audit indipendente è coerente: un epoch ENROLL con otto
stage, sette re-arm e terminale; un epoch VERIFY con una prima immagine. Le due
epoch hanno handshake TLS singolo, zero retry/reopen/reset/clear-halt/famiglie
persistenti note, backend drenato e context chiuso. I submit reali sono
203 + 76 = 279.

La Phase B non è iniziata. Il contatto successivo dell'indice sinistro è
avvenuto dopo il ritorno al prompt e non appartiene alla run. Different-finger,
delete e audit finale a quattro epoch restano non provati.

## Assert esatto fallito

La baseline richiedeva per VERIFY la sottostringa:

```text
first_image=1 release_tail=1 single_terminal=1 rearm32=0
```

L'evidenza autentica contiene invece:

```text
first_image=1 release_tail=0 single_terminal=0 rearm32=0
```

Numero righe e pattern ENROLL erano conformi; l'unico assert fallito fra
verify-match e `PHASE_B` è quindi quello VERIFY. Dopo il `VerifyStatus(done)`
il client chiama `VerifyStop` e poi `Release`; se l'action non ha ancora
terminato, il daemon attende per un intervallo limitato e può quindi
cancellarla prima della release tail, mentre il successivo close drena il
backend. I due contatori sono perciò una coppia coerente `0/0` (stop/close
prima della tail) o `1/1` (tail completata prima dello stop), non una
precondizione biometrica del match. In entrambi i casi devono restare
obbligatori prima immagine singola,
zero re-arm/retry/reopen/reset/clear-halt/persistenza, outstanding zero,
backend drenato e context chiuso.

Il correttivo sostituisce il grep rigido con un validatore di epoch tipizzato
che accetta soltanto le coppie coerenti `0/0` o `1/1` e conserva tutti gli
altri guardrail. Non modifica driver, protocollo, action budget o numero di
contatti.

## Riesame metodologico pre-live

1. **Cosa cambia realmente?** Il gate post-Phase-A valida la semantica reale
   del close fprintd, invece di pretendere sempre la tail completa prima che il
   client chiuda; inoltre il percorso corrente elimina grant/token/approvazione
   SHA e mantiene i limiti tecnici direttamente nel launcher.
2. **Quale nuova ipotesi viene testata?** Un nuovo open dopo il close VERIFY
   anticipato e drenato può completare la recovery già incorporata nel driver,
   eseguire una sola VERIFY different-finger e ottenere no-match senza retry.
3. **Se fallisce di nuovo allo stesso punto?** Non si ripete. Si conserva
   l'audit tipizzato e si torna al call-flow close/reentry offline; se invece
   la Phase B viene raggiunta ma fallisce altrove, la decisione successiva usa
   quel nuovo boundary senza retry automatico o implicito.

La nuova esecuzione resta una Human Gate: l'AI prepara e verifica il kit
offline, poi si ferma prima di USB e `sudo`.
