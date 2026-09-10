<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/02 — replan ordine/re-entry prima di D283 PAM

```text
DECISION=REPLAN
OUTCOME=READY_OFFLINE_HUMAN_REQUIRED
ADVANCEMENT=MATCHER_SCORE_TELEMETRY_AND_REPLICATED_POSITION_LIFECYCLE_DESIGN
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=SECOND_VERIFY_POSITIONAL_OR_LIFECYCLE_EFFECT_UNRESOLVED
CANONICAL_DOCUMENTATION=GOODIX_TECHNICAL_MANUAL_UPDATED
REVIEW_SET=GIT_NATIVE
```

## Riesame indipendente

Gli originali hash-pinned di Attempt 04 e 05 contengono entrambi la sequenza
client `MATCH`, poi `NO-MATCH`. In Attempt 04 l'operatore attesta lo stesso
indice destro per entrambe le VERIFY; in Attempt 05 attesta destro, poi
sinistro. Attempt 05 resta evidenza autentica del no-match different-finger,
ma identità e ordine sono sovrapposti.

Nessuno dei due export contiene gli score SIGFM. Attempt 04 mostra per la
seconda VERIFY un epoch coerente con 82 submit, `release_tail=1`, backend
drenato e context chiuso: un no-match non implica quindi da solo una chiusura
hardware incompleta. Attempt 05 mostra invece 76 submit e la coppia di close
coerente `0/0`. Questi dati non dimostrano un hardcode e non separano qualità,
ordine, stato del daemon e re-entry.

Il launcher D282 invoca davvero `fprintd-verify` e controlla l'outcome solo
dopo il ritorno. `fpi_print_sigfm_match()` confronta il probe con i sample
registrati e applica il threshold; non esiste un ramo Phase B hardcoded. Il
codice usava però `fp_dbg()` per gli score, non presenti negli export. Non
esiste dunque evidenza offline sufficiente per escludere il confondente.

## Esperimento minimo

Un enrollment invariato da 8 contatti è seguito da quattro VERIFY pianificate
dello stesso indice destro:

```text
processo/blocco A: posizione 1, posizione 2
restart fprintd
processo/blocco B: posizione 1, posizione 2
```

Il dito costante elimina l'identità come variabile. La replica della posizione
1/2 dopo il restart distingue un pattern di re-entry/posizione da un semplice
ordine globale: due peggioramenti in posizione 2 indicano il boundary
lifecycle; un recupero dopo restart indica stato process-local; un trend lungo
1→4 non azzerato dal restart indica un candidato temporale/qualitativo. Quattro
prove sono il minimo che replica entrambe le posizioni; non stimano FRR.

La candidate aggiunge soltanto marker `g_message()` per keypoint, score,
threshold, sample confrontato e outcome. La condizione
`score >= score_threshold`, l'early return sul primo match e il no-match dopo
tutti i sample restano invariati. Ogni trial ha raw e journal delimitati da un
cursor, metadati di blocco/posizione e un epoch VERIFY indipendente.
PID e `InvocationID` sono gated subito prima di ogni contatto: i due trial di
ciascun blocco devono condividere la stessa istanza e i blocchi devono avere
invocation differenti. Un auto-exit/riavvio inatteso ferma la run prima della
successiva action, invece di rendere ambiguo il disegno.

Se emerge un effetto sistematico della posizione o del restart, non si procede
alla caratterizzazione same/different né a D283: si investiga quel difetto. Se
non emerge, il risultato esclude solo un effetto deterministico nella run e
abilita il progetto successivo bilanciato same/different. Nessuna modifica del
matcher è autorizzata da questo step.

D283 resta tecnicamente valido e conservato al commit storico di preparazione,
ma i suoi entrypoint live rifiutano fail-closed finché D282/02 non è riesaminato.

Il preflight finale ha costruito la candidate Fedora 44 con SIGFM reale,
verificato l'ABI fprintd e i marker sintetici match/no-match. La matrice
congiunta D282/02 + regressioni D282/01 + D283 è `95/95 PASS`, inclusi i
controlli host reali del parser systemd e di `pam_start_confdir()` eseguiti
fuori sandbox. Nessun `sudo`, USB o sensore è stato usato.
