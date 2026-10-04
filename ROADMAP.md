<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# ROADMAP.md — Enrollment robustness v2

## Task unico

Modificare la policy di enrollment del Goodix `27c6:5125 / GF_ST411SEC_APP_12509`
portando il comportamento attuale alla seguente candidate empirica.

| Parametro | Attuale | Candidate empirico |
| --- | --- | --- |
| Minimo utile | 3 distinti | **>=12 accettati** |
| Target normale | 4–8 | **16** |
| Massimo template | 8 | **20** |
| Contatti fisici max | 20 | **36, bounded** |
| Early convergence | 3 + 2 duplicati | **eliminata** |
| Diversità | MAD raster | **coverage + SIGFM + qualità** |
| Campione quasi duplicato | può concludere enrollment | **retry, non avanza** |
| Campione povero | può entrare | **retry, non avanza** |

## Comportamento atteso

- Un enrollment non può concludersi prima di avere almeno **12 sample accettati**.
- **16 sample accettati** è il target normale della candidate.
- La policy può proseguire oltre 16 quando necessario, fino a un massimo di
  **20 sample accettati** nel template.
- Il numero massimo di contatti fisici è **36** e resta un limite bounded.
- La vecchia early convergence basata su `3 distinti + 2 duplicati` deve essere
  eliminata.
- Un campione duplicate o near-duplicate deve produrre **retry** e non deve
  avanzare l'enrollment.
- Un campione povero deve produrre **retry** e non deve avanzare l'enrollment.
- La decisione di accettare un sample deve usare una combinazione semplice e
  osservabile di **coverage, informazioni SIGFM e qualità**, al posto del solo
  MAD raster.
- Il raggiungimento del massimo di 20 sample o 36 contatti fisici non deve
  trasformare automaticamente un enrollment insufficiente in successo.

## Implementazione

Partire dalla policy di enrollment esistente e modificarla solo quanto serve per
ottenere il comportamento sopra descritto.

La logica deve distinguere almeno:

- contatti fisici;
- sample accettati;
- retry per duplicate/near-duplicate;
- retry per campione povero;
- completion;
- esaurimento bounded.

Il matcher di verifica e la relativa threshold non fanno parte di questo task e
devono restare invariati.

## Verifica offline

Prima del test sul sensore reale, dimostrare almeno che:

- con meno di 12 sample accettati non può avvenire completion;
- duplicate e near-duplicate producono retry senza avanzamento;
- un campione povero produce retry senza avanzamento;
- la vecchia early convergence non esiste più;
- il target normale è 16;
- la policy può continuare oltre 16 fino a 20 sample;
- il template non supera 20 sample;
- i contatti fisici non superano 36;
- l'esaurimento dei limiti bounded non viene interpretato come successo;
- il matcher e la threshold VERIFY restano invariati.

## Verifica reale

Dopo il PASS offline, eseguire una prova empirica sul target reale confrontando
la candidate con il comportamento attuale, con particolare attenzione a:

- completamento dell'enrollment;
- numero di contatti fisici;
- numero di sample accettati;
- first-touch recognition;
- posizioni diverse dello stesso dito;
- incidenza di `score=0` / NO_MATCH legittimi;
- duplicate volontarie;
- campioni volutamente poveri;
- wrong-finger rejection;
- VERIFY e IDENTIFY.

## Exit gate

`ENROLLMENT_ROBUSTNESS_V2=PASS` quando la candidate sopra descritta è
implementata, passa i test offline e la prova reale mostra un miglioramento
sensibile della robustezza senza regressioni evidenti nella rejection di dita
errate.

`MILESTONE_COMPLETE: ENROLLMENT_ROBUSTNESS_V2`
