<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# ROADMAP.md — Enrollment fixed-21 candidate

## Obiettivo unico

Sostituire la current enrollment-v2 candidate del Goodix
`27c6:5125 / GF_ST411SEC_APP_12509` con una candidate sperimentale
**fixed-21 valid captures**, derivata dall'osservazione empirica ripetuta del
comportamento Windows sullo stesso sensore.

Questa roadmap riguarda esclusivamente la policy di enrollment. Non modifica
matcher, threshold VERIFY, pairing, secure session, firmware, CONFIG90, FDT o
persistenza.

## Specifica vincolante

1. minimo **21 sample accettati**;
2. **nessuna early completion**: la completion avviene esattamente al
   **21° sample valido accettato**;
3. target normale **21**;
4. massimo sample accettati **21**; massimo **contatti fisici non definito**;
5. poor capture → **retry, non conta**;
6. duplicate/near-duplicate → **accettato e conta**, se il sample è altrimenti
   valido;
7. duplicate/near-duplicate **non determina, non anticipa e non impedisce la
   completion**;
8. matcher SIGFM e threshold **40 invariati**.

## Regola decisionale

La decisione production-candidate deve essere concettualmente:

```text
capture
  |
  +-- unusable / poor --> RETRY, accepted_count invariato
  |
  +-- valid -----------> ACCEPT, accepted_count++
                          |
                          +-- accepted_count < 21 --> continua
                          |
                          +-- accepted_count = 21 --> SUCCESS
```

Non deve esistere alcun percorso di successo prima del 21° sample accettato.

Non deve esistere alcun percorso che richieda più di 21 sample **accettati**.
I contatti fisici possono invece superare 21 quando uno o più contatti producono
retry.

## Diversity e telemetria

Le metriche già disponibili possono continuare a essere calcolate e registrate,
incluse almeno:

- SIGFM keypoints;
- SIGFM coverage mask / aggregate coverage;
- raster range e contrast;
- MAD;
- duplicate / near-duplicate classification.

Per questa candidate tali metriche sono **osservative** rispetto alla diversity:
non devono decidere la completion e duplicate/near-duplicate non devono causare
retry.

Resta invece consentito usare i criteri strettamente necessari a stabilire che
una cattura sia realmente **poor/unusable** e quindi non idonea a diventare un
sample SIGFM valido.

## Vincoli

- Nessuna early completion basata su coverage, keypoint, contrasto, MAD,
  duplicate streak o altre metriche di sufficienza.
- Nessun limite artificiale al numero totale di contatti fisici introdotto da
  questa policy.
- Nessun riuso del vecchio `GOODIX_TARGET_LOCAL_ENROLL_STAGES 21u` come
  giustificazione della nuova policy: il nuovo 21 deriva da evidenza empirica
  indipendente sul comportamento Windows.
- Nessuna modifica al matcher SIGFM.
- Nessuna modifica alla threshold VERIFY, che resta **40**.
- Nessuna modifica alla pipeline di preprocessing già qualificata.
- Nessuna modifica a pairing, PSK, TLS, firmware, OTP, CONFIG90, FDT o altri
  percorsi persistenti/device-state.

## Verifica offline obbligatoria

Dimostrare almeno che:

- 0..20 sample validi accettati non possono produrre completion;
- il 21° sample valido produce completion;
- il 22° sample accettato non è raggiungibile perché l'enrollment è già
  terminato;
- poor/unusable capture produce retry e non incrementa `accepted_count`;
- duplicate e near-duplicate validi vengono accettati e incrementano
  `accepted_count`;
- duplicate e near-duplicate non possono né anticipare né bloccare la
  completion;
- non esiste più alcun `max_physical_attempts` policy-bound per questa
  candidate;
- le metriche di diversity restano disponibili come telemetria ma non
  governano la completion;
- matcher SIGFM e threshold VERIFY=40 risultano invariati.

Eseguire i test offline normali e ASan/UBSan applicabili, senza accesso USB al
sensore reale.

## Verifica live

Solo dopo PASS offline, eseguire sul target reale almeno:

1. enrollment naturale fino a 21 sample validi;
2. enrollment volutamente quasi a posizione costante, verificando che
   duplicate/near-duplicate validi continuino ad avanzare fino a 21;
3. contatti volutamente poor/unusable, verificando che producano retry e che il
   numero di contatti fisici possa superare 21 senza alterare il target di 21
   sample accettati;
4. VERIFY same-finger su più placement, con raccolta dei punteggi SIGFM;
5. VERIFY wrong-finger;
6. IDENTIFY;
7. confronto con i risultati enrollment-v2 precedenti, con particolare
   attenzione a first-touch recognition e incidenza di `score=0`.

## Interpretazione dell'esperimento

Questa candidate non assume che Windows memorizzi 21 sample indipendenti né che
il suo Engine Adapter costruisca il template nello stesso modo del nostro
SIGFM. Verifica una sola ipotesi:

> se la nostra architettura host-side conserva 21 acquisizioni valide senza
> early completion e senza scartare sample per sola ridondanza, la robustezza
> same-finger migliora sensibilmente rispetto alla candidate enrollment-v2?

Se il problema degli `score=0` si riduce nettamente, la ridondanza fixed-21
diventa una spiegazione plausibile del miglioramento. Se persiste, la quantità
da sola non basta e il passo successivo sarà studiare più a fondo la costruzione
del template nel percorso Windows/Goodix.

## Exit gate

`ENROLLMENT_FIXED_21=PASS` quando:

- la specifica fixed-21 è implementata esattamente;
- i test offline e sanitizer applicabili passano;
- la prova live completa è stata eseguita;
- matcher e threshold VERIFY risultano invariati;
- i risultati same-finger e wrong-finger sono documentati senza alterare la
  policy durante il test.

`MILESTONE_COMPLETE: ENROLLMENT_FIXED_21`
