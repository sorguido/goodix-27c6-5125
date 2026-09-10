<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/02 — caratterizzazione ordine e re-entry del matcher

> **Attempt 01 chiuso pre-sensor:** la baseline `8490f41` si è fermata nello
> staging prima di fprintd e di qualsiasi contatto. Il launcher corrente copia
> ora esplicitamente i file runtime, crea i symlink senza collisione e rende
> esportabili anche i risultati senza trial. Non riutilizzare script storici.

## Scopo e rischio

Il kit verifica se il risultato o gli score SIGFM cambiano sistematicamente
fra la prima e la seconda VERIFY. D283/PAM resta preservato ma bloccato in
standby: questa run non usa PAM, login o sudo come fattore biometrico.

La sequenza è fissa e non dipende dagli outcome:

1. enrollment dell'indice destro con 8 contatti;
2. restart del daemon, poi due VERIFY dell'indice destro — blocco A;
3. secondo restart, poi altre due VERIFY dell'indice destro — blocco B;
4. delete host-only e rollback.

Il disegno tiene costante il dito e replica le posizioni 1/2 in due processi
fprintd distinti, verificati tramite PID e `InvocationID`. Se il daemon termina
o viene riattivato mentre si attende un contatto, il kit si ferma prima della
relativa action. Raccoglie per ogni VERIFY risultato, score per sample
enrollment effettivamente confrontato, threshold, keypoint del probe, epoch e
contatori safety. Logging e analisi non cambiano threshold, numero degli stage,
preprocessing, matcher, driver o protocollo.

Limiti tecnici: 5 action biometriche, 12 contatti, nessun retry automatico o
implicito. Le quattro VERIFY sono campioni pianificati, non retry condizionali.
Su `RETRY`, errore o telemetria incoerente il kit si ferma e fa rollback.

## Prerequisiti

- branch `development`, `HEAD` allineato a `origin/development` e worktree
  live-critical pulito;
- RPM OpenCV presenti in `/tmp/goodix-opencv-4.13-rpms`;
- esattamente un Goodix USB `27c6:5125` collegato;
- nessun altro utilizzo contemporaneo di fprintd.

## Comando unico

Eseguire dalla root del repository come utente normale:

```bash
operator_kit/d282-02-matcher-order/run-d282-02.sh \
  --operator-run /tmp/goodix-opencv-4.13-rpms
```

Il launcher costruisce e verifica la candidate, poi chiede `ESEGUI`. Durante
l'enrollment digitare `DESTRO`. Per ciascuna VERIFY mostra autonomamente:

```text
TEST 01/04 — BLOCCO A, POSIZIONE 1/2

PROSSIMO CONTATTO:
>>> INDICE DESTRO <<<
```

Premere INVIO e appoggiare esclusivamente l'indice destro. Non interpretare la
stringa tecnica `Verifying: right-index-finger`: il launcher la nasconde dalla
console e la conserva soltanto nell'evidenza raw.

Al termine allegare dalla `EXPORT_DIRECTORY`:

- `operator.log`;
- `summary.env`;
- `trials.tsv`.

Se la run si ferma prima dei trial, `trials.tsv` è correttamente assente e
l'export riporta `D282_02_TRIALS_TSV_EXPORTED=false`; allegare i file prodotti.

Allegare anche il file indicato da `TERMINAL_TRANSCRIPT`. In caso di fallimento
non ripetere la run: conservare tutti gli output e attendere la review AI-PM.
Staging, servizio e storage isolato vengono ripristinati dal trap di cleanup;
il template non entra nell'export.

## Cosa succede dopo

Se la posizione 2 peggiora in entrambi i blocchi, la caratterizzazione
biometrica si ferma e si investiga il lifecycle. Se il confondente non emerge,
AI-PM progetterà separatamente un confronto same-finger/different-finger
bilanciato; questa singola run non autorizza generalizzazioni statistiche.

## Preflight offline facoltativo

```bash
operator_kit/d282-02-matcher-order/run-d282-02.sh \
  --offline-preflight /tmp/goodix-opencv-4.13-rpms
```

Il preflight compila e verifica la candidate e la telemetria con dati
sintetici; non enumera USB, non avvia fprintd e non raggiunge il sensore.
