<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# ROADMAP.md — Fixed-21 enrollment

## Obiettivo

Implementare una policy di enrollment **fixed-21** per il Goodix
`27c6:5125 / GF_ST411SEC_APP_12509`.

## Specifica vincolante

1. minimo **21 sample accettati**;
2. **nessuna early completion**: completion esattamente al **21° sample valido accettato**;
3. target normale **21**;
4. massimo sample accettati **21**; massimo contatti fisici **non definito**;
5. poor/unusable capture → **retry, non conta**;
6. duplicate/near-duplicate valido → **accettato e conta**;
7. duplicate/near-duplicate **non anticipa, non impedisce e non determina la completion**;
8. matcher SIGFM e threshold VERIFY **40 invariati**.

## Regola runtime

```text
capture
  |
  +-- poor / unusable --> RETRY
  |                      accepted_count invariato
  |
  +-- valid -----------> ACCEPT
                         accepted_count++
                         |
                         +-- accepted_count < 21 --> continua
                         |
                         +-- accepted_count = 21 --> SUCCESS
```

Conseguenze obbligatorie:

- 0..20 sample accettati non possono completare l'enrollment;
- il 21° sample valido è terminale;
- un 22° sample accettato non è raggiungibile;
- i retry non incrementano `accepted_count`;
- i contatti fisici possono superare 21;
- non deve esistere un `max_physical_attempts` policy-side.

## Poor/unusable

Mantenere un gate separato per impedire che una cattura realmente inutilizzabile
entri nel template.

Il gate poor/unusable non deve essere usato come criterio di diversity o di
completion. Riutilizzare le metriche di qualità già disponibili senza introdurre
nuove euristiche biometriche se non necessarie.

## Diversity

Le metriche di diversity già disponibili restano diagnostiche:

- SIGFM keypoints;
- SIGFM coverage / aggregate coverage;
- raster range / contrast;
- MAD;
- duplicate / near-duplicate.

Non devono governare acceptance o completion, salvo il distinto gate
poor/unusable.

In particolare:

- duplicate/near-duplicate valido → ACCEPT;
- aggregate coverage non determina SUCCESS;
- keypoint/contrast/MAD non possono produrre early completion.

## Invarianti del task

Non modificare:

- algoritmo SIGFM;
- logica VERIFY/IDENTIFY;
- threshold VERIFY = **40**;
- preprocessing SIGFM già qualificato.

Definire la policy fixed-21 con costanti semanticamente dedicate. Non riutilizzare
il vecchio `GOODIX_TARGET_LOCAL_ENROLL_STAGES 21u` come fonte normativa della
nuova policy.

## Verifica offline

Dimostrare almeno:

1. 20 sample validi consecutivi → nessuna completion;
2. 21° sample valido → completion;
3. nessun 22° sample accettabile;
4. poor/unusable intercalato → retry senza avanzamento;
5. contatti fisici >21 consentiti quando esistono retry;
6. duplicate valido → ACCEPT;
7. near-duplicate valido → ACCEPT;
8. duplicate/near-duplicate non anticipano la completion;
9. duplicate/near-duplicate non impediscono la completion al 21° accepted;
10. assenza di `max_physical_attempts` policy-side;
11. metriche diversity presenti ma non decisionali;
12. matcher SIGFM invariato;
13. threshold VERIFY = 40 invariata;
14. preprocessing invariato.

Eseguire inoltre i test offline e i profili sanitizer già pertinenti al driver.

## Verifica live

Dopo il PASS offline, validare sul target reale:

1. enrollment naturale → completion al 21° sample valido;
2. enrollment con pressioni molto simili → i sample validi continuano ad avanzare fino a 21;
3. enrollment con contatti poor/unusable → retry, con possibilità di superare 21 contatti fisici;
4. VERIFY same-finger su placement differenti;
5. VERIFY wrong-finger;
6. IDENTIFY;
7. raccolta dei punteggi SIGFM e degli eventuali `score=0`.

## Exit gate

`ENROLLMENT_FIXED_21=PASS` quando:

- la policy runtime implementa esattamente la specifica fixed-21;
- i test offline pertinenti sono PASS;
- la verifica live è completata;
- matcher SIGFM, threshold VERIFY=40 e preprocessing risultano invariati.

`MILESTONE_COMPLETE: ENROLLMENT_FIXED_21`
