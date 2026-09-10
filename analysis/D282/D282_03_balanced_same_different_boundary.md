<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/03 — boundary same/different bilanciato

## Ipotesi e metodo

Ipotesi: senza cambiare algoritmo o enrollment, sei probe fisici bilanciati
possono mostrare se la distribuzione osservata same-finger è distinguibile da
quella different-finger, riducendo i confondenti di ordine e processo.

Il disegno minimo è A `R-L-R`, restart, B `L-R-L`, dove R è l’indice destro
enrolled e L l’indice sinistro non enrolled. Ogni classe ha tre osservazioni,
occupa ogni posizione una volta ed è presente in entrambi i processi.

Non vengono modificati threshold (`40`), preprocessing, matcher, stage (`8`),
protocollo o persistenza. Le sole metriche sono quelle già osservabili:
risultato, score per sample effettivamente confrontato, sample di match,
conteggio keypoint, `real_submit`, ordine, processo ed epoch safety. I vettori
terminati da un match sono marcati come censurati dall’early-return.

## Guardrail

- 1 enrollment + 6 verify pianificate; massimo 14 contatti fisici;
- nessun retry automatico, implicito o condizionato dall’outcome;
- PID e InvocationID verificati prima di ogni action;
- conferma testuale Poka-Yoke del dito prima di ogni singolo contatto;
- fail-closed su retry client, mismatch telemetry/client o parametri drift;
- storage isolato, delete host-only, rollback e reseal via trap;
- export senza template e D283/PAM non eseguito.

## Criteri di lettura

Il completamento è evidence-producing anche con outcome misti. Tre campioni per
classe non consentono FRR/FAR, significanza statistica o readiness PAM. La
review successiva valuterà raw, attestazione fisica e censura degli score
separatamente.

Se un different-finger fa match o il same-finger continua a produrre no-match,
non si ritenta la run: si riesamina il metodo e, se supportato dall’evidenza, si
progetta un confronto controllato della copertura enrollment. Se la run fallisce
nello stesso confine host-side, si corregge quel confine senza cambiare il
disegno biometrico; se fallisce device-side, si ferma prima di una nuova live.

```text
OUTCOME=READY_OFFLINE_HUMAN_REQUIRED
ADVANCEMENT=MATERIAL_EXPERIMENTAL_REPLAN
EXECUTABLE_CLOSURE=PASS_OFFLINE_114_OF_114
RESIDUAL_BLOCKER_OR_RISK=LIVE_PHYSICAL_STIMULUS_REQUIRES_HUMAN
D283_01_LIVE_STANDBY=true
```
