<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/03 — confronto bilanciato stesso dito / dito diverso

> **CHIUSO — NON ESEGUIRE:** la seconda run valida è stata completata e
> riesaminata. Gli entrypoint live rifiutano fail-closed. Il next step corrente
> è il kit D283/01 indicato dal manuale tecnico.

## Scopo e differenza rispetto all’ultimo tentativo

D282/02 è chiuso e non deve essere ripetuto. D282/03 risponde a una domanda
diversa: con lo stack invariato, gli outcome e gli score osservati separano
preliminarmente lo stesso dito da un dito diverso?

Il kit mantiene invariati enrollment a 8 contatti, preprocessing, matcher,
threshold SIGFM `40`, driver e protocollo. Dopo l’enrollment dell’indice destro
esegue questa sequenza fissa:

```text
BLOCCO A: DESTRO, SINISTRO, DESTRO
BLOCCO B: SINISTRO, DESTRO, SINISTRO
```

I blocchi usano processi fprintd distinti verificati tramite PID e
`InvocationID`. Ogni classe fisica compare tre volte e occupa una volta
ciascuna posizione 1, 2 e 3. Gli outcome non modificano mai la sequenza.

Limiti tecnici: 7 action biometriche (1 enrollment + 6 verify), massimo 14
contatti, zero retry automatici o impliciti. Su retry, errore, drift del daemon
o telemetria incoerente il kit si ferma e fa rollback. D283/PAM resta in
standby. Il template rimane nello storage isolato e viene cancellato prima del
rollback; non entra nell’export.

Gli score delle prove che fanno match possono essere incompleti per
l’early-return del matcher. `trials.tsv` espone quindi
`score_vector_complete`, `comparison_count` e `observed_max_score`; non chiama
“massimo globale” un valore censurato.

## Prerequisiti

- branch `development`, HEAD uguale a `origin/development`, review set pulito;
- RPM OpenCV in `/tmp/goodix-opencv-4.13-rpms`;
- esattamente un Goodix USB `27c6:5125` collegato;
- nessun altro uso contemporaneo di fprintd;
- operatore pronto a usare soltanto gli indici destro e sinistro richiesti.

## Comando unico

Da utente normale, nella root del repository:

```bash
operator_kit/d282-03-balanced-same-different/run-d282-03.sh \
  --operator-run /tmp/goodix-opencv-4.13-rpms
```

Il launcher compila e verifica la candidate, poi richiede `ESEGUI`. Per
l’enrollment richiede `DESTRO`. Prima di ogni VERIFY mostra un solo dito e
richiede di digitare esattamente `DESTRO` oppure `SINISTRO`; una conferma errata
arresta la run prima dell’action. Appoggiare esclusivamente il dito mostrato.

Al termine allegare i file indicati da `EXPORT_DIRECTORY`:

- `operator.log`;
- `summary.env`;
- `trials.tsv`.

Allegare anche `TERMINAL_TRANSCRIPT`. Se la run si ferma prima dei trial,
`trials.tsv` può essere assente: allegare comunque tutti i file esportati. Non
ripetere autonomamente la run dopo alcun fallimento o risultato inatteso.

## Stop condition successiva

La run produce evidenza, non un verdetto statistico. Se same/different non si
separano coerentemente, D283 resta bloccato e il next step sarà un replan
controllato dell’acquisizione/copertura. Anche in caso di separazione coerente,
attendere la review AI-PM prima di qualunque prova PAM.

## Preflight offline facoltativo

```bash
operator_kit/d282-03-balanced-same-different/run-d282-03.sh \
  --offline-preflight /tmp/goodix-opencv-4.13-rpms
```

Non enumera USB, non avvia fprintd e non raggiunge il sensore.
