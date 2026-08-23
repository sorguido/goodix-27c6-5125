# D261 — corrective minimo del baseline approval record

**Reasoning level: MEDIUM**

## Natura dello step

Questo è un **micro-corrective documentale dello stesso D261**.

Non creare D262.

Non modificare la baseline live-critical approvata:

```text
e9073a171697bd68dd2debabb851f23d007bf718
```

Non eseguire hardware, operator kit, sudo, USB o secret reali.

## Contesto della review AI-PM

Il bundle:

```text
analysis/D261/D261_baseline_approval_record_bundle.zip
```

è sostanzialmente corretto:

- contiene soltanto il manuale canonico e `D261_readiness_decision.json`;
- registra correttamente la baseline approvata;
- promuove correttamente la readiness a review operativa/live;
- mantiene `READY_FOR_FDT_LIVE=false`;
- non introduce nuova evidenza hardware.

La review AI-PM ha però trovato una incoerenza residua nel machine-readable
`analysis/D261/D261_readiness_decision.json`.

Dopo aver cambiato:

```text
ADVANCEMENT=GOVERNANCE_BASELINE_APPROVAL_RECORDED
OUTCOME=READY
```

i campi:

```text
BUNDLE
BUNDLE_SHA256
```

puntano ancora al precedente:

```text
D261_import_purity_presecret_corrective_bundle.zip
```

anziché al bundle documentale corrente.

Inoltre il prompt richiedeva nella closure:

```text
LIVE_CRITICAL_FILE_MODIFICATION_COUNT=0
```

ma tale dato non è presente nel decision artifact corrente.

## Task A — correggere il decision artifact

Aggiornare esclusivamente quanto necessario in:

```text
analysis/D261/D261_readiness_decision.json
```

Richiesto:

```text
"BUNDLE": "analysis/D261/D261_baseline_approval_record_bundle.zip"
"BUNDLE_SHA256": "analysis/D261/D261_baseline_approval_record_bundle.zip.sha256"
"LIVE_CRITICAL_FILE_MODIFICATION_COUNT": 0
```

Non modificare altri campi salvo necessità strettamente derivata da questo corrective.

In particolare devono restare:

```text
D261_APPROVED_LIVE_BASELINE_SHA=e9073a171697bd68dd2debabb851f23d007bf718
EXACT_APPROVED_LIVE_BASELINE_PRESENT=true
OPERATIONAL_LIVE_CRITICAL_FILESET_APPROVAL=APPROVED_USER_AI_PM_FULL_SHA
READY_FOR_BASELINE_APPROVAL_REVIEW=false
OPERATIONAL_REVIEW_PENDING_APPROVED_BASELINE=false
READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=true
READY_FOR_FDT_LIVE_REVIEW=true
READY_FOR_FDT_LIVE=false
PRIMARY_FUTURE_LIVE_RISK=FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND
```

## Task B — micro-polish manuale, senza nuova conoscenza

Nel manuale canonico:

```text
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

correggere soltanto i piccoli difetti editoriali introdotti dal precedente
micro-step, se ancora presenti:

- rimuovere le indentazioni accidentali di due spazi all'inizio di righe
  narrative nuove;
- correggere `non-istanzia` in `non istanzia`;
- preferire una formulazione grammaticalmente neutra/coerente per
  `full SHA ... approvata`, ad esempio `full commit SHA ... approvato`.

Non riscrivere sezioni, non cambiare stato tecnico e non aggiungere nuove
affermazioni.

## Task C — verifica scope reale del branch

Prima della chiusura, verificare:

```bash
git rev-parse --abbrev-ref HEAD
git diff --check
git diff --name-only e9073a171697bd68dd2debabb851f23d007bf718
git status --short
```

Il branch atteso è:

```text
sandbox_free_model
```

La directory untracked:

```text
prompt/
```

è **user-managed transport material** usato per fornire prompt `.md` a Kilo Code.
È già stata osservata dall'AI-PM prima di questo corrective e NON è un output
D261. Non modificarla, non cancellarla, non aggiungerla al bundle e non
considerarla una modifica inattesa ai fini della closure.

Sono invece attesi come output dello step soltanto:

```text
Goodix 27c6 5125 manuale tecnico.md
analysis/D261/D261_readiness_decision.json
analysis/D261/D261_baseline_approval_record_bundle.zip
analysis/D261/D261_baseline_approval_record_bundle.zip.sha256
```

Nessun file live-critical deve risultare modificato.

I file live-critical vietati includono almeno:

```text
core/
src/goodix5125_cleanroom.py
poc/goodix5125/tools/binding_reference/
tools/d261_live_fdt_arm_once.py
operator_kit/d261-live-fdt-arm-once.sh
```

Non cancellare automaticamente eventuali file extra o modifiche dell'Utente:
se compaiono file inattesi, riportarli chiaramente e fermarsi prima di
dichiarare lo step clean.

## Task D — rigenerare esclusivamente il bundle documentale

Rigenerare:

```text
analysis/D261/D261_baseline_approval_record_bundle.zip
analysis/D261/D261_baseline_approval_record_bundle.zip.sha256
```

Bundle step-local, non cumulativo.

Deve contenere soltanto:

```text
Goodix 27c6 5125 manuale tecnico.md
analysis/D261/D261_readiness_decision.json
```

Verificare:

- archive test/CRC PASS;
- sidecar SHA-256 corrispondente allo ZIP;
- nessun raw/capture/cache/OTP/secret/DLL/firmware/biometria.

## Git

Non creare commit.
Non pushare.
Non fare merge/rebase/amend/reset.

La baseline live-critical approvata resta il commit storico immutabile:

```text
e9073a171697bd68dd2debabb851f23d007bf718
```

## Safety

Deve restare:

```text
REAL_USB_OPEN_COUNT=0
REAL_SECRET_READ_COUNT=0
REAL_COMMAND_SEND_COUNT=0
FPRINTD_MUTATION_COUNT=0
REAL_SINGLE_USE_MARKER_CREATE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
READY_FOR_FDT_LIVE=false
```

## Closure obbligatoria

Riportare:

```text
OUTCOME=READY
ADVANCEMENT=GOVERNANCE_BASELINE_APPROVAL_RECORDED
EXECUTABLE_CLOSURE=NOT_APPLICABLE_DOCUMENTATION_ONLY

D261_APPROVED_LIVE_BASELINE_SHA=e9073a171697bd68dd2debabb851f23d007bf718
EXACT_APPROVED_LIVE_BASELINE_PRESENT=true
OPERATIONAL_LIVE_CRITICAL_FILESET_APPROVAL=APPROVED_USER_AI_PM_FULL_SHA

READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=true
READY_FOR_FDT_LIVE_REVIEW=true
READY_FOR_FDT_LIVE=false

LIVE_CRITICAL_FILE_MODIFICATION_COUNT=0

BUNDLE=analysis/D261/D261_baseline_approval_record_bundle.zip
BUNDLE_SHA256=<actual sha256>

GIT_BRANCH=sandbox_free_model
GIT_DIFF_CHECK=PASS
UNEXPECTED_MODIFIED_FILE_COUNT=<integer>
```

Nel calcolo di `UNEXPECTED_MODIFIED_FILE_COUNT`, escludere soltanto la già
nota directory user-managed `prompt/`.

Se compaiono altri path oltre ai quattro output attesi e a `prompt/`, impostare
`UNEXPECTED_MODIFIED_FILE_COUNT` al relativo numero, non correggerli o
cancellarli automaticamente ed elencarli per review dell'Utente/AI-PM.

Aggiorna sempre organicamente il manuale tecnico canonico nella root repository
e produci il bundle ZIP step-local non cumulativo con sidecar SHA-256.
