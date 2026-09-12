<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D291/01 — aggiornamento runtime e prova multi-VERIFY

Questo è il solo Human Gate residuo di D291. L'agente AI non deve eseguirlo:
il comando usa `pkexec`, aggiorna il runtime D285 e raggiunge il sensore durante
un unico `sudo ls` con PAM bounded a tre tentativi.

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

## Unico comando operatore

Dalla root del repository, come utente normale:

```bash
operator_kit/d291-01-multi-verify/run-d291-01.sh --operator-run
```

Il primo dialogo `pkexec` usa il percorso password di `system-auth`, dove D285
mantiene fingerprint disabilitato. Confermare `AGGIORNA D291`, poi
`D291 PRONTO` soltanto quando si è pronti ai due contatti.

Successo:

```text
tentativo 1 NO_MATCH
→ secondo prompt resta realmente in attesa
→ tentativo 2 MATCH
→ sudo autorizzato senza password
```

Il kit richiede esattamente due epoch VERIFY negli audit, ciascuna con una sola
acquisizione, e ammette sul secondo audit soltanto
`reopen=1 explicit_verify_reopen=1`. Retry transport/post-TLS, reset,
clear-halt, famiglie persistenti, outstanding o una terza/quarta epoch fanno
fallire e attivano il rollback. L'output sanitizzato viene scritto in una
directory `/tmp/goodix-d291-01-result.*` stampata come `RESULT_DIRECTORY`.
