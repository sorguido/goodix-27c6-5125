<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D289/01 — review indipendente della live KDE realmente bloccata

## Decisione

```text
D289_01_LIVE_REVIEW=PASS
D289_01_REAL_KDE_LOCKED_SESSION_UNLOCK=PROVEN
PM_DECISION=ACCEPT_AND_CONTINUE
OUTCOME=PASS_MATCH
ADVANCEMENT=REAL_KDE_LOCKED_SESSION_FINGERPRINT_MATCH_TO_UNLOCKED_PROVEN
EXECUTABLE_CLOSURE=PASS_LIVE_PLUS_HASH_PINNED_EVIDENCE_AUDIT
RESIDUAL_BLOCKER_OR_RISK=SDDM_LOGIN_WITH_FINGERPRINT_NOT_PROVEN
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_PLUS_HASH_PINNED_PRIVATE_CAPTURE
D289_RERUN_REQUIRED=false
```

## Integrità e provenance

La capture
`captures/live_probe/d289-real-locked-session_20260912T065056Z_74d8e5d8fc7e/sanitized/`
dichiara la baseline completa
`74d8e5d8fc7e0c91904c92725d3e5660def9ee72`, che esiste e contiene il
payload live eseguito. I sedici file elencati da `capture.sha256` coincidono
con il file set della capture e hanno tutti il digest atteso; il manifest ha
SHA-256
`2130514674733dff6227e9aa23584c62baf0dfeda2d21e9bfdc96308e08de158`.

L'auditor fail-closed `d289_01_live_evidence_audit.py` verifica manifest,
baseline, stati, journal, telemetria, classificazioni, audit e cleanup. Legge
inoltre il payload direttamente dal commit baseline e ne controlla l'ordine
causale lock → stato attivo → identità greeter → MATCH → stato non attivo →
release overlay.

## Evidenza verificata

- `summary.env` è `PASS`; pre/post audit, acquisizione cursor, payload,
  sanitizer, tee, cleanup, journal e classifier terminano tutti con return
  code zero. Esiste una sola invocazione e non è stata interrotta.
- Lo stato osservato compie `false → true → false`. Il greeter PID 103382 è
  figlio del KWin reale e si trova nel cgroup utente
  `user@1000.service/session.slice/plasma-kwin_wayland.service`; pre e post
  audit provano owner D-Bus/PID, UID 1000, `comm=kwin_wayland`, cmdline e
  cgroup coerenti. L'exe non leggibile è accettato soltanto insieme a questi
  segnali compositi indipendenti.
- È consumato esattamente un ciclo: tentativi/contatti/matched attempt
  `1/1/1`, una epoch VERIFY, nessun secondo slot e zero retry automatici o
  impliciti.
- SIGFM estrae 129 keypoint, dichiara otto sample e confronta i sample 1, 2 e
  3 con score `9`, `14` e `376` alla soglia 40. L'unico outcome è MATCH sul
  sample 3.
- L'epoch osserva attempts/rejected/consumed `1/0/1`, TLS/first-image `1/1` e
  76 submit USB reali. Retry/reopen/reset/clear-halt/famiglie persistenti note
  sono zero; outstanding è zero, drained e context-closed sono uno.
- L'overlay è nello stesso mount namespace di KWin, read-only e limitato al
  service fingerprint. I marker confermano unmount, PAM host ripristinato e
  runtime rimosso. `cleanup.log` conferma zero residui.
- Gli audit root pre/post, nello stesso boot, confermano runtime D286,
  provenance wrapper, scope authselect, fallback password, template, libfprint
  di sistema e uninstall readiness integri; gli audit stessi contano zero
  action sensore.

## Causalità e limiti del claim

Il classifier della baseline accetta MATCH soltanto con una epoch valida,
SIGFM MATCH e la transizione finale a `GetActive=false`. Il payload baseline
conta action e contatto solo dopo aver provato il vero lock e l'identità del
greeter; sul ramo MATCH attende poi lo stato non attivo prima di registrare
`REAL_LOCK_MATCH`. Non contiene `unlock-session`. La congiunzione chiude il
percorso esercitato:

```text
KWin org.freedesktop.ScreenSaver.Lock
→ vero KScreenLocker attivo
→ kde-fingerprint
→ pam_fprintd
→ fprintd
→ Goodix VERIFY
→ SIGFM MATCH
→ GetActive=false
```

La capture non registra eventi tastiera. L'assenza di password/PIN è quindi
coerente con l'istruzione operatore catturata, con
`D289_NON_FINGERPRINT_RECOVERY_AFTER_NO_MATCH=false` e col percorso causale
completo, ma non viene promossa a telemetria macchina autonoma.
`persistent=0` significa zero famiglie persistenti note osservate, non prova
assoluta dell'assenza di effetti NVM sconosciuti. D289 non attraversa il login
manager e non prova `SDDM_LOGIN_WITH_FINGERPRINT`.

## Correttivo teardown offline

`payload.log` contiene, dopo i tre marker di cleanup e prima del marker finale,
`"$root_out_fd": Descrittore di file errato`. Summary, root log e cleanup
provano che non ha alterato esito, classificazione o ripristino: è rumore di
osservabilità. La causa è il lifecycle Bash dei descriptor originali del
`coproc`, che possono essere chiusi automaticamente quando l'helper termina
subito dopo `RELEASE`.

Il correttivo duplica immediatamente entrambi i descriptor del coprocessore.
Una regressione forza l'uscita rapida dell'helper e verifica che tutti i marker
siano drenati senza diagnostica FD. È una correzione host-only/offline; non
richiede e non autorizza un rerun D289.

Il vecchio entrypoint live D289 è chiuso con `LIVE_CAPABLE=false`, mentre il
percorso `--offline-test` resta disponibile per regressione.
