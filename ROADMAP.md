<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# ROADMAP.md — Enrollment robustness v2

## Obiettivo unico

Correggere in modo pragmatico il difetto di robustezza dell'enrollment del
Goodix `27c6:5125 / GF_ST411SEC_APP_12509`.

Il problema osservato è concreto: la release attuale può completare
l'enrollment con un template troppo povero e, in uso reale, contatti legittimi
dello stesso dito possono successivamente produrre `score=0` contro tutti i
sample memorizzati.

Questa iterazione NON deve progettare un nuovo sistema biometrico generale e
NON deve tentare di ricostruire l'algoritmo Windows/OEM. Deve realizzare una
candidate semplice, misurabile e reversibile, quindi verificarla empiricamente
sul target reale.

L'ipotesi di lavoro è:

> un template più ricco, ottenuto accettando più campioni utili e impedendo che
> duplicati o campioni poveri facciano avanzare/concludere l'enrollment, può
> ridurre sensibilmente i `score=0` legittimi senza modificare il matcher.

## Baseline attuale da sostituire

La policy corrente deriva da Rockytkg:

```text
GOODIX_ENROLLMENT_DIVERSITY_MIN_DISTINCT          3
GOODIX_ENROLLMENT_DIVERSITY_MAX_SAMPLES           8
GOODIX_ENROLLMENT_DIVERSITY_DUP_STREAK            2
GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS 20
```

Comportamento corrente:

- almeno 3 sample distinti;
- massimo 8 sample memorizzati;
- MAD raster come criterio principale di diversità;
- due duplicate-like consecutive possono causare early completion;
- massimo 20 contatti fisici.

Questa policy è una scelta host-side ereditata. Non è un limite dimostrato di
APP12509.

## Candidate da implementare

La prima candidate sperimentale deve seguire questi parametri:

| Parametro | Candidate |
| --- | ---: |
| Minimo utile | **12 sample accettati** |
| Target normale | **16 sample accettati** |
| Massimo template | **20 sample accettati** |
| Contatti fisici massimi | **36, hard bound** |
| Early convergence da duplicate streak | **eliminata** |
| Diversity | **coverage + SIGFM + qualità** |
| Quasi duplicato | **retry, non avanza** |
| Campione povero | **retry, non avanza** |

Il valore **21 non deve essere usato** come target, massimo template, criterio
di successo o parametro biometrico di questa candidate.

## Semantica richiesta

### 1. Sample accettati

Un contatto entra nel template solo se è considerato **utile** dalla nuova
policy leggera di diversity.

La valutazione deve usare, senza introdurre una nuova architettura complessa:

- informazioni SIGFM già disponibili o ottenibili con modifiche locali e
  limitate;
- qualità del sample;
- distribuzione/coverage delle feature;
- confronto con i sample già accettati per individuare duplicate o
  near-duplicate.

Il solo MAD raster non deve più decidere la sufficienza biometrica del template.

MAD può rimanere, se utile, come segnale ausiliario/fast-path per individuare
campioni chiaramente ripetuti, ma non deve essere il criterio principale di
coverage o completion.

### 2. Campione povero

Un campione biometricamente povero deve:

- produrre retry;
- incrementare soltanto il conteggio dei contatti fisici;
- non essere aggiunto al template;
- non aumentare il conteggio dei sample accettati;
- non contribuire alla completion.

La candidate deve utilizzare una metrica semplice e osservabile basata sui dati
SIGFM/qualità già disponibili. Eventuali nuove soglie introdotte in questa fase
sono **parametri sperimentali della candidate**, non verità biometriche
qualificate, e devono essere chiaramente identificabili nel codice/test.

### 3. Duplicate e near-duplicate

Un contatto duplicate o near-duplicate deve:

- produrre retry;
- non essere memorizzato;
- non avanzare il numero di sample accettati;
- non poter mai causare completion.

La logica:

```text
MIN_DISTINCT + DUP_STREAK => SUCCESS
```

deve scomparire completamente.

### 4. Minimo, target e massimo

La logica di enrollment deve distinguere chiaramente:

```text
MIN_ACCEPTED_SAMPLE = 12
NORMAL_TARGET       = 16
MAX_TEMPLATE        = 20
MAX_PHYSICAL        = 36
```

Semantica:

- **0–11 accettati:** completion vietata;
- **12–15 accettati:** completion ammessa solo se la nuova policy di
  coverage/SIGFM/qualità considera già sufficiente il template;
- **16 accettati:** target operativo normale della candidate;
- **17–20 accettati:** continuare solo quando la coverage/qualità non è ancora
  considerata sufficiente;
- **20 accettati:** hard cap del template; non memorizzare il sample 21;
- **36 contatti fisici:** hard bound dell'interazione, inclusi retry.

Il raggiungimento di 20 sample o 36 contatti non deve trasformare
automaticamente un template insufficiente in successo. Se il criterio di
sufficienza non è raggiunto al relativo hard bound, l'enrollment deve fallire
in modo esplicito e bounded.

### 5. Completion

La completion non deve più dipendere da una streak di duplicati.

Deve dipendere dalla combinazione di:

- almeno 12 sample utili;
- qualità accettabile dei sample memorizzati;
- sufficiente diversità/coverage rispetto ai sample già accettati;
- assenza di una condizione evidente di template ancora povero.

Per questa candidate la policy deve rimanere **semplice**. Non costruire:

- atlanti geometrici finger-relative;
- graph registration complessi;
- concatenazioni di trasformazioni;
- nuovi modelli biometrici;
- modifiche profonde a SIGFM;
- nuovi formati template;
- una replica dell'algoritmo Windows/OEM.

Lo scopo è verificare empiricamente se una policy sensibilmente più ricca ma
ancora semplice risolve il problema osservato.

## Vincoli tecnici specifici della candidate

La candidate deve mantenere invariati:

- algoritmo e threshold di VERIFY;
- comportamento di matching SIGFM;
- formato/serializzazione dei template esistenti;
- lettura dei template già enrollati;
- VERIFY e IDENTIFY lato matcher.

La modifica deve restare concentrata sull'enrollment e sulla scelta dei sample
da memorizzare.

Non introdurre `21` come nuovo massimo. Il massimo template richiesto per
questa candidate è **20**.

Non introdurre un secondo sistema di template o una migrazione automatica delle
impronte esistenti.

## Implementazione mirata

Partire dall'implementazione esistente, non riscrivere il driver.

L'intervento deve concentrarsi sul percorso già esistente di enrollment,
principalmente:

```text
libfprint-driver/goodix_enrollment_diversity.*
libfprint-driver/goodix_fpimage_device.*
```

e su helper SIGFM strettamente necessari alla classificazione
quality/diversity.

Prima di modificare altro, verificare l'effettiva necessità.

Non introdurre nuovo plumbing libfprint, single-extraction handoff, atlas,
multi-epoch enrollment o altre architetture non necessarie a questa candidate.

## Test offline obbligatori prima del sensore reale

La candidate deve avere test deterministici che dimostrino almeno:

1. sotto 12 sample accettati non può completare;
2. duplicate e near-duplicate producono retry e non avanzano;
3. due duplicate consecutive non possono concludere l'enrollment;
4. un campione povero produce retry e non entra nel template;
5. un campione utile aumenta il numero degli accepted sample;
6. il target normale è 16;
7. la policy può proseguire oltre 16 fino a un massimo di 20;
8. il sample 21 non viene memorizzato;
9. 36 contatti fisici sono un hard bound;
10. esaurire un hard bound con template insufficiente produce failure, non
    success;
11. threshold e matcher VERIFY restano invariati;
12. template legacy continuano a essere letti;
13. cancellazione/release/error path restano bounded e deterministici.

L'obiettivo dei test offline è qualificare il comportamento della candidate,
non dimostrare teoricamente che 12/16/20 siano valori biometrici universali.

## Prova empirica successiva

Solo dopo il completamento dei test offline la candidate deve essere provata
sul sensore reale.

La prova deve confrontare il comportamento con la baseline attuale a 8 sample
e verificare soprattutto:

- enrollment completabile nell'uso reale;
- numero di contatti fisici e sample accettati;
- first-touch recognition;
- posizionamenti centro/sinistra/destra/alto/basso;
- moderate rotazioni;
- incidenza dei `score=0` legittimi;
- dito adulto;
- dito piccolo/bambino dove praticabile;
- pollice come riferimento a superficie maggiore;
- duplicate volontarie durante enrollment;
- campioni volutamente poveri;
- wrong-finger rejection;
- VERIFY e IDENTIFY;
- consumer Fedora già qualificati.

La domanda sperimentale è semplice:

> rispetto alla policy attuale a 8 sample, questa candidate riduce
> sensibilmente i NO_MATCH/`score=0` legittimi senza peggiorare la rejection
> di dita errate?

Se sì, si valuterà soltanto dopo l'evidenza reale se affinare i parametri.
Se no, solo allora sarà giustificato riaprire il design verso soluzioni più
sofisticate.

## Criterio unico di chiusura

`ENROLLMENT_ROBUSTNESS_V2=PASS` quando:

- la candidate 12/16/20/36 è implementata come sopra;
- la early convergence da duplicate streak è eliminata;
- duplicate/near-duplicate e campioni poveri non avanzano;
- matcher e threshold VERIFY restano invariati;
- i test offline passano;
- la prova reale mostra un miglioramento sensibile della robustezza rispetto
  alla baseline a 8 sample;
- la wrong-finger rejection non mostra regressioni;
- VERIFY, IDENTIFY e i consumer Fedora qualificati restano funzionanti.

Fino a quel momento non introdurre architetture biometriche più complesse.

`MILESTONE_COMPLETE: ENROLLMENT_ROBUSTNESS_V2`
