<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# ROADMAP.md — Enrollment robustness v2

## Obiettivo

Correggere il difetto di robustezza dell'enrollment emerso nell'uso reale del
Goodix `27c6:5125 / GF_ST411SEC_APP_12509`.

La release attuale può completare l'enrollment con un template troppo povero di
copertura: contatti biometricamente validi dello stesso dito possono poi
produrre `score=0` contro tutti i sample memorizzati. Il problema è stato
osservato sia su un dito adulto sia, con frequenza maggiore, su un dito piccolo.

La soluzione non deve abbassare la sicurezza del matching. Deve migliorare ciò
che viene appreso durante l'enrollment.

### Vincoli invariati

- nessun firmware flash, IAP o ClearApp;
- nessuna scrittura OTP o factory-data;
- nessun cambiamento persistente di VID:PID o modalità;
- nessun indebolimento intenzionale della rejection di un dito errato;
- nessun retry sensor-reaching nascosto o non limitato;
- pairing, TLS, state-v2 e convivenza Windows devono restare invariati salvo
  evidenza tecnica che richieda una modifica separata;
- qualunque prova sul sensore reale resta soggetta a Human Gate.

### Evidenza di partenza

- il driver attuale memorizza al massimo 8 sample SIGFM;
- la diversity policy corrente deriva esplicitamente dal selector Rockytkg:
  minimo 3, massimo 8, MAD raster < 8 e convergenza dopo due contatti
  duplicate-like;
- questi valori sono una scelta host-side e non costituiscono prova di un
  limite APP12509;
- Windows Biometric Framework supporta enrollment adattivo e può richiedere
  ulteriori campioni finché l'engine non ritiene il template sufficiente;
- sull'hardware reale Windows Hello può richiedere molte più di 8 acquisizioni,
  arrivando anche oltre 20 quando non è soddisfatto;
- il Goodix MOC driver di riferimento usa conteggi di enrollment
  device-dependent, inclusi 12 stage per numerosi PID Goodix;
- il progetto possiede già evidenza target-local di 21 primary stage riusciti,
  da riesaminare senza assumere che 21 sia un limite o un obiettivo biometrico.

---

## 1 — Preservare la severità della verifica

Non abbassare la threshold di matching per compensare i `score=0`.

Un punteggio zero non è un near-match fallito per pochi punti: indica che la
probe corrente non ha stabilito sovrapposizione SIGFM utile con i sample
enrollati. La correzione deve quindi avvenire nell'enrollment.

**PASS quando**

- threshold e logica di rejection restano invariate;
- nessun workaround trasforma uno `score=0` in match.

**NEXT:** 2.

---

## 2 — Eliminare la convergenza prematura derivata da Rockytkg

Rimuovere la policy che può concludere l'enrollment dopo pochi sample distinti
e una sequenza di contatti duplicate-like.

Una posizione ripetuta non dimostra che il dito sia stato coperto a sufficienza.
Un contatto uguale o quasi uguale a coverage già acquisita deve essere scartato
o richiesto nuovamente, non diventare un segnale di completamento.

**PASS quando**

- i duplicati non fanno avanzare artificialmente la coverage;
- due contatti ripetuti non possono provocare early completion;
- la policy non dipende più dai limiti host-side Rockytkg `3..8`.

**NEXT:** 3.

---

## 3 — Progettare Enrollment Diversity v2

Sostituire il solo confronto MAD del raster con una politica che valuti la
ricchezza biometrica del nuovo campione.

Valutare almeno:

- quantità/qualità dei keypoint SIGFM;
- distribuzione spaziale dei keypoint nell'immagine 80×64;
- coverage incrementale rispetto ai sample già accettati;
- duplicate e near-duplicate detection;
- sample poveri che devono produrre retry senza avanzamento;
- distinzione esplicita tra physical contacts, rejected contacts e accepted
  template samples.

La policy deve restare bounded e osservabile.

**PASS quando**

test offline dimostrano che:

- contatti quasi identici non aumentano la coverage;
- contatti realmente spostati aggiungono coverage;
- sample biometricamente poveri non entrano silenziosamente nel template.

**NEXT:** 4.

---

## 4 — Rendere adattiva la ricchezza del template

Non sostituire semplicemente `8` con un altro numero fisso arbitrario.

La conclusione dell'enrollment deve dipendere da qualità e coverage sufficienti,
con un minimo prudenziale e un limite di sicurezza bounded.

Qualificare almeno template nell'ordine di:

- 12 sample utili;
- 16 sample utili;
- 20 sample utili;
- oltre 20, se l'evidenza mostra che è necessario.

Il limite strutturale attuale del contenitore SIGFM/libfprint va investigato
separatamente: non assumere che 21 sample siano automaticamente sufficienti,
né che debbano costituire il massimo definitivo.

**PASS quando**

il criterio di completamento è giustificato da robustezza misurata e non
dall'eredità Rockytkg.

**NEXT:** 5.

---

## 5 — Determinare il vero boundary APP12509

Non assumere che APP12509 abbia un limite di 8 stage per enrollment.

Verificare sul target reale quanti contatti puliti il protocollo attuale può
gestire in una singola azione di enrollment e riconciliare il risultato con
l'evidenza storica delle 21 primary stage.

La prova deve essere preparata e validata offline prima di qualsiasi accesso
al sensore.

**HUMAN_REQUIRED prima di ogni esperimento live.**

**PASS quando**

il boundary reale è OBSERVED/PROVEN sul target e non inferito da Rockytkg,
Windows o altri dispositivi Goodix.

**NEXT:** 6.

---

## 6 — Multi-epoch solo se realmente necessario

Il multi-epoch non è la soluzione primaria.

Implementarlo soltanto se il punto 5 dimostra un vero limite per singola epoch
inferiore alla ricchezza necessaria del template host-side.

In quel caso una singola enrollment action fprintd potrà, se tecnicamente
corretto:

1. raccogliere una epoch bounded;
2. completare release/STOP/drain;
3. aprire una nuova epoch pulita;
4. continuare ad accumulare coverage SIGFM host-side;
5. serializzare un unico template finale.

Non devono essere introdotte nuove scritture persistenti o nuovi pairing.

**PASS quando**

o la singola epoch è sufficiente, oppure necessità e sicurezza del multi-epoch
sono dimostrate.

**NEXT:** 7.

---

## 7 — Riqualificazione biometrica reale

Dopo la chiusura offline, ripetere enrollment e verifica sul target reale con
posizionamenti deliberatamente vari.

Copertura minima:

- indice adulto;
- dito piccolo/bambino dove praticabile;
- pollice come riferimento a superficie maggiore;
- centro, sinistra, destra, alto, basso e rotazioni moderate;
- contatti volontariamente quasi identici durante enrollment;
- first-touch recognition rate;
- frequenza di `score=0` legittimi;
- wrong-finger rejection / false-accept safety;
- VERIFY e IDENTIFY;
- Plasma Login, KScreenLocker, sudo e PolicyKit;
- convivenza Windows;
- pairing/TLS/state-v2 invariati;
- zero scritture persistenti inattese.

Dove praticabile, confrontare i risultati con il comportamento attuale a
8 sample come baseline misurabile.

**EXIT_GATE**

`ENROLLMENT_ROBUSTNESS_V2=PASS` solo se:

- la convergenza prematura derivata da Rockytkg è eliminata;
- l'enrollment raccoglie coverage significativamente più ricca;
- `score=0` e NO_MATCH legittimi diminuiscono in modo sostanziale;
- la rejection di dita errate non peggiora;
- tutti i consumer Fedora continuano a funzionare;
- il boundary reale APP12509 è documentato da evidenza;
- Windows interoperability resta integra;
- non viene introdotto alcun nuovo rischio persistente sul reader.

**NEXT**

`MILESTONE_COMPLETE: ENROLLMENT_ROBUSTNESS_V2`
