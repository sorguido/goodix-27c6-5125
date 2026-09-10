<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/02 Attempt 02 — review indipendente e closure

## Decisione

`PASS_LIVE_CLOSED`. L’Attempt 02 ha raggiunto il sensore ed eseguito il piano
fisso di un enrollment e quattro VERIFY. L’evidenza è integra, il cleanup è
completo e il vecchio entrypoint viene chiuso contro ulteriori rerun.

Il risultato chiude due ipotesi strette ma non la robustezza del matcher:

- il secondo VERIFY non è deterministicamente un no-match: A2 ha fatto match;
- un restart non produce degrado globale: B1 ha fatto match con lo score
  osservato più alto della run (`2739`);
- un falso non-match same-finger è però ricomparso in B2, con vettore completo
  `0,1,0,0,0,0,0,0` contro threshold `40`.

Non è lecito stimare FRR/FAR o concludere che il lifecycle sia escluso in
generale. È lecito concludere soltanto che né “sempre seconda posizione” né
“sempre dopo restart” spiegano i quattro risultati osservati.

## Provenance ed evidenza primaria

Directory importata:
`captures/D282_02/D28202_ATTEMPT_02_20260910T220312Z_f868ad127b30/sanitized/`.
Gli SHA-256 ricalcolati sono:

- `operator.log`: `8152304946f7d5d3ab4d8859d80970331c4505fb931644251fd320ba9eda3afb`;
- `summary.env`: `a1f84c32d23283966bf68e9f3944e676faf5e2b638f0fae78e7bb2e782cf028f`;
- `trials.tsv`: `ba115e1772e3d31d90a98bbd103526ee2fd377558664e4290cb7a72ee9ce87ab`;
- `terminal-transcript.log`: `cacc131befbd20ff5cbce56ad7dbf1d2a37eac28eb8ac42e22ab5112a2be69f5`.

La baseline live dichiarata e coerente è
`f868ad127b30467f4d0da9aedcaef6faea8b0caf`.

## Separazione dei livelli probatori

Evidenza raw macchina: due PID/InvocationID distinti per A e B; 6 epoch
(enroll, quattro verify, delete/NONE); 5 action consumate; 12 estrazioni SIGFM;
zero retry, reopen, reset, clear-halt e famiglie persistenti; tutti i context
drained/closed; rollback, servizio, libreria di sistema, staging e storage
preesistente invariati.

Evidenza normalizzata: A1 match (`0,941`), A2 match (`129`), B1 match (`2739`),
B2 no-match (`0,1,0,0,0,0,0,0`). Gli score dei match sono censurati
dall’early-return: descrivono solo i sample confrontati fino al primo match,
non una matrice completa di otto confronti. B2 è invece una scansione completa
degli otto sample.

Attestazione fisica: il launcher ha richiesto `INDICE DESTRO` per enrollment e
per ciascuna prova; la direzione umana allegata attesta che tutti i 12 contatti
sono stati eseguiti con l’indice destro. Il software non può verificare
biologicamente questa identità: la qualifica “same-finger” dipende da tale
attestazione.

Inferenze controllate: il no-match B2 non è marginale rispetto al threshold e
non coincide con un conteggio keypoint eccezionalmente basso. I probe match
hanno 137, 155 e 136 keypoint; B2 ne ha 123, vicino al minimo enrollment 126 e
non sufficiente, da solo, a spiegare uno score massimo pari a 1. Anche
`real_submit` (79–83 nelle quattro verify) e le coppie lifecycle 0/0 o 1/1 non
separano match e no-match. Non esistono ulteriori quality marker già esposti
dall’API SIGFM pubblica; non vengono inventate metriche surrogate.

## Riesame metodologico e next experiment

Le alternative considerate sono:

1. same/different bilanciato con lo stack invariato;
2. variazione controllata della copertura enrollment mantenendo otto campioni.

Si sceglie la prima. La run corrente contiene un solo no-match a copertura
completa; i match hanno vettori censurati, quindi non provano che una specifica
zona enrollment sia assente o insufficiente. Cambiare subito modalità o
copertura degli stage aggiungerebbe un confondente e richiederebbe un disegno
paired non supportato dai campioni effimeri correnti.

Il D282/03 mantiene enrollment 8, preprocessing, matcher e threshold `40`, e
usa sei VERIFY alternate: A = destro/sinistro/destro, B =
sinistro/destro/sinistro. Ogni identità compare tre volte, una volta in ciascuna
posizione interna ai blocchi, e in entrambi i processi. Questo produce la
minima separazione preliminare same/different senza dichiarare significanza
statistica.

Se il D282/03 fallisce per incoerenza operativa o safety, non viene ripetuto e
si analizza la fase esatta. Se completa ma non separa same/different, si ferma
la progressione PAM e si riprogetta l’acquisizione/copertura con un esperimento
controllato. Solo una separazione coerente autorizza la review successiva; non
autorizza automaticamente D283.

## Closure

```text
OUTCOME=PASS_LIVE_CLOSED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_LIVE_WITH_ROLLBACK
RESIDUAL_BLOCKER_OR_RISK=SAME_FINGER_FALSE_NON_MATCH_REPRODUCED_SINGLE_EVENT
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_PLUS_HASH_PINNED_PRIVATE_CAPTURE
NEXT_STEP=HUMAN_GATE_D282_03_BALANCED_SAME_DIFFERENT
D283_01_LIVE_STANDBY=true
```
