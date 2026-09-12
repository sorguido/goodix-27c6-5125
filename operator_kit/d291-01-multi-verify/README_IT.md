<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D291/01 — aggiornamento runtime e prova multi-VERIFY

```text
STATUS=HISTORICAL_ONLY_DO_NOT_RERUN
D291_BIOMETRIC_ROOT_CAUSE=NOT_IDENTIFIED
NEW_LIVE_REQUIRED_NOW=false
```

Questo kit non è più un Human Gate corrente. Il launcher si ferma subito,
prima di build, `pkexec`, modifica runtime, PAM, fprintd, USB o sensore, con
exit code 4 e il marker `HISTORICAL_ONLY_DO_NOT_RERUN`. Le evidenze aggregate
successive hanno mostrato che il transport multi-VERIFY funziona ma la
stabilità biometrica non è chiusa; ripetere la stessa live senza una nuova
causa tecnica violerebbe il riesame metodologico pre-live.

Quanto segue conserva il design storico per audit e provenance; non costituisce
un'istruzione operativa.

## Scopo e rischio

Il kit costruisce dal commit `development` già pushato una nuova
`libfprint-2.so.2.0.0`, verifica che le altre cinque librerie del runtime siano
byte-identiche, sostituisce soltanto libfprint e il suo manifest, aggiorna lo
state D285 root-only e riavvia fprintd. PAM D285 deve essere già hash-pinned a:

```text
pam_fprintd.so max-tries=3 timeout=45
```

Non modifica `plasmalogin`, authselect, sudoers, template, PSK o configurazione
del sensore. Ogni errore dopo l'inizio del deployment ripristina driver,
manifest e state precedenti e riavvia il runtime precedente.

## Prerequisiti e stop condition

- branch `development`, HEAD uguale a `origin/development`, worktree pulito;
- installazione D285 attiva e integra, con un solo target `27c6:5125`;
- nessun altro consumer fprintd in uso;
- dito indice destro registrato disponibile;
- al primo prompt usare deliberatamente un dito errato;
- al secondo prompt usare l'indice destro registrato;
- se compare una richiesta password, premere `Ctrl-C` senza digitarla;
- non ripetere automaticamente una run fallita.

Lo stato host dopo la precedente run fallita non è assunto: prima di qualunque
deployment il percorso root esegue il root-audit D285, verifica state, runtime,
manifest e PAM correnti e stampa `D291_01_HOST_RUNTIME_PREFLIGHT=PASS`. Ogni
drift ferma il kit prima della sostituzione.

## Comando storico disabilitato

Dalla root del repository, una eventuale invocazione termina immediatamente:

```bash
operator_kit/d291-01-multi-verify/run-d291-01.sh --operator-run
```

Nessun dialogo `pkexec` viene aperto nello stato corrente. Storicamente il
primo dialogo usava il percorso password di `system-auth`, dove D285
mantiene fingerprint disabilitato. Confermare `AGGIORNA D291`, poi
`D291 PRONTO` soltanto quando si è pronti ai due contatti.

Successo:

```text
tentativo 1 NO_MATCH
→ secondo prompt resta realmente in attesa
→ tentativo 2 MATCH
→ sudo autorizzato senza password
```

Il kit richiede due epoch se il secondo contatto fa MATCH. Se il secondo
contatto è NO_MATCH, la policy PAM può offrire la terza e ultima acquisizione;
solo un MATCH al terzo contatto è accettato. Ogni epoch ha una sola
acquisizione; dalla seconda in poi l'audit deve riportare
`reopen=1 explicit_verify_reopen=1` e riuso della baseline SIGFM del primo
open logico. Retry transport/post-TLS, reset, clear-halt, famiglie persistenti,
outstanding, un esito senza MATCH o una quarta epoch fanno fallire e attivano
il rollback. L'output sanitizzato viene scritto in una directory
`/tmp/goodix-d291-01-result.*` stampata come `RESULT_DIRECTORY`.
