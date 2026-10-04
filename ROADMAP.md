<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# ROADMAP.md — Enrollment robustness v2

## Obiettivo

Correggere il difetto di robustezza dell'enrollment emerso nell'uso reale del
Goodix `27c6:5125 / GF_ST411SEC_APP_12509`.

La release attuale può completare l'enrollment con un template troppo povero di
copertura: contatti biometricamente validi dello stesso dito possono poi
produrre `score=0` contro tutti i sample memorizzati. Il problema è stato
osservato sia su un dito adulto sia, con frequenza maggiore, su un dito piccolo.

La soluzione deve migliorare ciò che viene appreso durante l'enrollment senza
compensare il problema abbassando la severità del matching.

## Evidenza di partenza

- il driver attuale memorizza al massimo 8 sample SIGFM;
- la diversity policy corrente deriva esplicitamente dal selector Rockytkg:
  minimo 3, massimo 8, MAD raster < 8 e convergenza dopo due contatti
  duplicate-like;
- questi valori sono una scelta host-side e non costituiscono un limite
  APP12509;
- Windows Biometric Framework supporta enrollment adattivo e può richiedere
  ulteriori campioni finché l'engine non ritiene il template sufficiente;
- sull'hardware reale Windows Hello può richiedere molte più di 8 acquisizioni,
  arrivando anche oltre 20 quando non è soddisfatto;
- il Goodix MOC driver di riferimento usa conteggi di enrollment
  device-dependent, inclusi 12 stage per numerosi PID Goodix;
- una precedente cattura passiva Windows Hello/OEM sul target reale registrò
  un enrollment completo con un numero elevato di cicli di acquisizione; quel
  conteggio appartiene esclusivamente a quella singola run e non costituisce
  minimo, massimo, target o limite progettuale.

## Assunzione di partenza sul numero di stage

Non assumere che APP12509 abbia un limite di 8 stage per enrollment.

L'evidenza osservata su Windows Hello/OEM sullo stesso target dimostra che il
sensore e il relativo protocollo possono proseguire oltre otto acquisizioni
all'interno di un singolo enrollment quando l'engine lo richiede. Il valore 8
appartiene alla precedente policy host-side derivata da Rockytkg e non deve
essere usato come limite hardware, limite protocollare, target biometrico o
criterio di convergenza.

Questa è una premessa di progetto, non un gate da riqualificare.

## PUNTI DA OSSERVARE IN FASE DI SVILUPPO

I punti seguenti appartengono allo stesso task e devono essere considerati
congiuntamente durante progettazione, implementazione e qualificazione. Non
rappresentano step sequenziali né milestone autonome.

1. **Preservare la severità della verifica.**  
   Non abbassare la threshold di matching per compensare i `score=0`. Un
   punteggio zero indica assenza di sovrapposizione SIGFM utile con i sample
   enrollati: la correzione deve quindi avvenire nell'enrollment, non rendendo
   più permissivo il matching.

2. **Eliminare la convergenza prematura derivata da Rockytkg.**  
   Una posizione ripetuta non dimostra che il dito sia stato coperto a
   sufficienza. Un contatto uguale o quasi uguale a coverage già acquisita deve
   essere scartato o richiesto nuovamente, non diventare un segnale di
   completamento. I duplicati non devono far avanzare artificialmente la
   coverage e la policy non deve dipendere dai limiti host-side Rockytkg
   `3..8`.

3. **Valutare la ricchezza biometrica dei campioni.**  
   Superare il solo confronto MAD del raster valutando almeno qualità e quantità
   dei keypoint SIGFM, distribuzione spaziale nell'immagine 80×64, coverage
   incrementale rispetto ai sample già accettati, duplicate/near-duplicate,
   sample poveri e distinzione esplicita fra physical contacts, rejected
   contacts e accepted template samples. Le metriche adottate devono essere
   misurabili e sostenute da evidenza sperimentale.

4. **Rendere adattiva la conclusione dell'enrollment.**  
   Non sostituire `8` con un altro numero fisso arbitrario. La conclusione
   dell'enrollment deve derivare da criteri biometrici misurabili di qualità,
   diversità e coverage, qualificati mediante evidenza sperimentale. Il numero
   finale di sample utili deve essere una conseguenza di tali criteri, non un
   obiettivo predefinito. Un eventuale limite massimo deve avere esclusivamente
   funzione di safety bound tecnico contro enrollment non terminanti o
   patologici e non deve costituire un criterio di successo biometrico. Gli
   eventuali limiti strutturali del contenitore SIGFM/libfprint vanno trattati
   separatamente come vincoli implementativi.

5. **Riqualificare il comportamento biometrico reale.**  
   La soluzione finale deve essere verificata sul target reale con
   posizionamenti deliberatamente vari e comprendere almeno: indice adulto,
   dito piccolo/bambino dove praticabile, pollice come riferimento a superficie
   maggiore, centro/sinistra/destra/alto/basso e rotazioni moderate, contatti
   volutamente quasi identici, first-touch recognition rate, frequenza di
   `score=0` legittimi, wrong-finger rejection / false-accept safety, VERIFY,
   IDENTIFY, Plasma Login, KScreenLocker, sudo, PolicyKit e convivenza Windows.
   Dove praticabile, il comportamento attuale a 8 sample va conservato come
   baseline misurabile di confronto.

## Criterio unico di chiusura

`ENROLLMENT_ROBUSTNESS_V2=PASS` solo quando l'intero task è qualificato come
un insieme e l'evidenza dimostra che:

- la convergenza prematura derivata da Rockytkg è eliminata;
- l'enrollment raccoglie una rappresentazione del dito più robusta secondo
  criteri biometrici misurabili e sperimentalmente qualificati;
- `score=0` e NO_MATCH legittimi diminuiscono in modo sostanziale nell'uso
  reale;
- la rejection di dita errate non peggiora;
- VERIFY, IDENTIFY e i consumer Fedora qualificati continuano a funzionare;
- Windows interoperability resta integra;
- non viene introdotto alcun nuovo rischio persistente sul reader.

`MILESTONE_COMPLETE: ENROLLMENT_ROBUSTNESS_V2`
