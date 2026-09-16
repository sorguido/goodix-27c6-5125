<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/02 Attempt 01 — failure pre-sensor e correttivo staging/export

```text
DECISION=CORRECTIVE
OUTCOME=FAIL_PRE_SENSOR_STAGING_CLOSED
ADVANCEMENT=HOST_STAGING_ROOT_CAUSE_AND_EVIDENCE_SAFE_CORRECTIVE
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=MATCHER_EXPERIMENT_NOT_STARTED
CANONICAL_DOCUMENTATION=GOODIX_TECHNICAL_MANUAL_UPDATED
REVIEW_SET=GIT_NATIVE
```

## Evidenza e classificazione

La run operatore sulla baseline
`8490f41d2491ab1e1ce7f8922edce78d73edfc9c` si è fermata durante lo
staging delle librerie. Il transcript osserva la collisione sulla creazione di
`libfprint-2.so.2`; il summary osserva rollback completo, staging rimosso,
storage preesistente e libreria di sistema invariati e tutti i flag USB,
sensore e live a `false`.

Il control-flow della baseline conferma che la riga fallita precede
`systemctl stop`, `daemon-reload`, l'impostazione dei tre flag live e lo start
di fprintd. Non sono iniziati enrollment o trial: contatti fisici e action
biometriche sono zero. Attempt 01 non è evidenza sul matcher.

Gli originali sanitizzati operator-supplied sono preservati in
`captures/D282_02/D28202_ATTEMPT_01_20260910T214945Z_8490f41d_PRE_SENSOR/sanitized/`:

```text
summary.env SHA-256            = 12b9e43c447f925b6149df947041fc9c795c15008b52fae3412581bcb1172727
terminal-transcript.log SHA-256 = 5cad08c472151598367e360814ade757cc3d4566ef64383e0a898641556d0edf
```

## Root cause e correttivo

La candidate contiene il file reale `libfprint-2.so.2.0.0` e i symlink
`libfprint-2.so.2` e `libfprint-2.so`. Il wildcard `*.so.*` includeva il primo
symlink; `install` lo dereferenziava creando un file regolare SONAME, quindi il
successivo `ln -s` collideva deterministicamente.

Il correttivo riusa la semantica D282/01: copia per nome soltanto i sei file
runtime reali e crea poi la catena di symlink prevista. Il medesimo helper è
usato dal live path e dalla regressione offline sulla candidate realmente
compilata.

`operator.log` e `summary.env` vengono inizializzati prima dello staging
fallibile e `RISULTATI_PRIVATI` viene annunciato solo dopo tale inizializzazione.
L'export richiede i due file minimi ma tratta `trials.tsv` come opzionale,
indicando esplicitamente se è stato esportato. Un risultato pre-action senza
trial è copiato e verificato byte-identico senza un secondo errore
`sha256sum`.

Esperimento, matcher, threshold, preprocessing, protocollo e standby D283 non
cambiano. La nuova run resta Human Gate; l'AI non la esegue.
