<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# ROADMAP.md — Fixed-21 enrollment

## Scope

Implementare una policy di enrollment **fixed-21** per il Goodix
`27c6:5125 / GF_ST411SEC_APP_12509`.

Lavorare sul branch corrente senza switch, merge o rebase non richiesti.
Limitare le modifiche ai file strettamente necessari alla policy di enrollment,
alla relativa telemetria/test e alla documentazione tecnica direttamente
coinvolta.

Non modificare pairing, PSK, TLS, firmware, OTP, CONFIG90, FDT, VID:PID,
persistenza device-side o altri percorsi non necessari a questo task.

## Specifica vincolante

La policy finale deve rispettare esattamente questi punti:

1. minimo **21 sample accettati**;
2. **nessuna early completion**: la completion avviene esattamente al
   **21° sample valido accettato**;
3. target normale **21**;
4. massimo sample accettati **21**; massimo **contatti fisici non definito**;
5. poor/unusable capture → **retry, non conta**;
6. duplicate/near-duplicate → **accettato e conta**, se il sample è altrimenti
   valido;
7. duplicate/near-duplicate **non determina, non anticipa e non impedisce la
   completion**;
8. matcher SIGFM e threshold VERIFY **40 invariati**.

## Regola decisionale

La decisione runtime deve essere equivalente a:

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

Requisiti conseguenti:

- nessun percorso può concludere con successo a 0..20 sample accettati;
- il 21° sample valido accettato deve essere terminale;
- non deve essere possibile accettare un 22° sample nello stesso enrollment;
- i retry non avanzano il conteggio dei sample accettati;
- il numero totale di contatti fisici non deve avere un limite policy-side;
- duplicate e near-duplicate validi non devono produrre retry;
- duplicate e near-duplicate validi non devono avere alcun ruolo speciale
  nella decisione terminale.

## Poor/unusable gate

Conservare un gate esplicito per evitare che una cattura realmente inutilizzabile
entri nel template.

La classificazione poor/unusable deve essere deterministica, testabile e
separata dalla diversity. Non usare criteri di diversity come condizione di
completion.

Se l'implementazione corrente dispone già di metriche di qualità affidabili,
riutilizzarle senza allargare inutilmente lo scope. Non introdurre nuove euristiche
biometriche se non necessarie a distinguere una cattura utilizzabile da una
cattura inutilizzabile.

## Diversity e telemetria

Le metriche già disponibili possono rimanere attive a fini diagnostici, incluse:

- SIGFM keypoints;
- SIGFM coverage mask e aggregate coverage;
- raster range;
- raster contrast;
- MAD;
- classificazione duplicate / near-duplicate.

Per questa policy tali metriche devono essere **osservative** rispetto alla
diversity:

- non possono causare early completion;
- non possono richiedere più di 21 sample accettati;
- duplicate/near-duplicate non possono causare retry;
- aggregate coverage non può governare la completion.

Mantenere audit sufficienti a ricostruire almeno:

- indice del contatto fisico;
- numero di sample accettati;
- esito ACCEPT / RETRY / TERMINAL;
- motivo del retry;
- metriche diagnostiche già disponibili.

Non registrare immagini raw, template biometrici, PSK o altri segreti.

## Matcher e preprocessing

Non modificare:

- algoritmo SIGFM;
- logica di matching VERIFY/IDENTIFY;
- threshold VERIFY, che deve restare **40**;
- preprocessing SIGFM già qualificato;
- formato dei template, salvo modifiche strettamente necessarie a supportare
  esattamente 21 sample accettati.

Verificare esplicitamente nel diff finale che nessuna modifica accidentale
abbia alterato matcher, threshold o preprocessing.

## Costanti e limiti

Definire la nuova policy fixed-21 con nomi e commenti semanticamente corretti.

Non riutilizzare automaticamente costanti storiche solo perché contengono il
valore 21. Ogni costante usata dal percorso production deve descrivere la
semantica effettiva della nuova policy.

Eliminare dal percorso decisionale production:

- early completion;
- normal target diverso da 21;
- max accepted samples diverso da 21;
- max physical attempts;
- completion basata su coverage/keypoint/contrast;
- retry causato esclusivamente da duplicate/near-duplicate.

Codice o telemetria non più decisionale può essere mantenuto solo se resta
chiaro che è diagnostico e non influenza la policy.

## Test offline obbligatori

Aggiornare o aggiungere test che dimostrino almeno:

1. 20 sample validi consecutivi → nessuna completion;
2. 21° sample valido → completion;
3. impossibilità di accettare il 22° sample nello stesso enrollment;
4. uno o più poor/unusable intercalati → retry, accepted_count invariato;
5. numero di contatti fisici >21 consentito quando esistono retry;
6. duplicate validi → ACCEPT e avanzamento;
7. near-duplicate validi → ACCEPT e avanzamento;
8. duplicate/near-duplicate non anticipano la completion;
9. duplicate/near-duplicate non impediscono la completion al 21° accepted;
10. nessun max physical attempts policy-side;
11. metriche diversity disponibili ma non decisionali;
12. matcher SIGFM invariato;
13. threshold VERIFY = 40 invariata;
14. preprocessing invariato.

Eseguire tutti i test offline già applicabili al driver e i relativi profili
ASan/UBSan. Nessun test offline deve accedere al sensore USB reale.

## Gate prima del live

Dopo il PASS offline:

- mostrare il diff rilevante;
- mostrare i risultati dei test;
- confermare esplicitamente che matcher, threshold 40, preprocessing e percorsi
  pairing/TLS/firmware non sono cambiati;
- fermarsi in stato **HUMAN_REQUIRED**.

Non eseguire test live, installazioni, sudo o accesso USB reale senza
autorizzazione esplicita dell'utente.

## Test live dopo autorizzazione

Dopo autorizzazione esplicita, verificare almeno:

1. enrollment naturale: completion esattamente al 21° sample valido;
2. enrollment con pressioni volutamente molto simili: i sample validi devono
   continuare ad avanzare fino a 21;
3. enrollment con contatti volutamente poor/unusable: devono produrre retry e
   consentire un numero totale di contatti fisici superiore a 21;
4. VERIFY same-finger su più placement;
5. VERIFY wrong-finger;
6. IDENTIFY;
7. raccolta dei punteggi SIGFM e degli eventuali `score=0`;
8. assenza di regressioni evidenti nel normale lifecycle del device.

Non modificare la policy durante la prova live.

## Documentazione

`TECHNICAL_MANUAL.md` deve contenere solo conoscenza tecnica stabile e
qualificata del dispositivo e della sua integrazione Fedora; non deve diventare
un diario dei test o una cronaca operativa.

`TECHNICAL_MANUAL.md` deve contenere solo conoscenza tecnica stabile e
qualificata del dispositivo e della sua integrazione Fedora; non deve diventare
un diario dei test o una cronaca operativa.

`TECHNICAL_MANUAL.md` deve contenere solo conoscenza tecnica stabile e
qualificata del dispositivo e della sua integrazione Fedora; non deve diventare
un diario dei test o una cronaca operativa.

Cronologia sperimentale, prove, tentativi e risultati intermedi vanno in:

`development/Goodix 27c6 5125 manuale tecnico.md`

Aggiornare `TECHNICAL_MANUAL.md` solo se il task produce conoscenza tecnica
stabile effettivamente qualificata.

## Exit gate

Il task è completo solo quando:

- la policy runtime implementa esattamente fixed-21;
- i test offline e sanitizer applicabili sono PASS;
- il gate HUMAN_REQUIRED è stato rispettato;
- il test live autorizzato è stato completato;
- matcher SIGFM e threshold VERIFY=40 sono invariati;
- preprocessing è invariato;
- nessuna modifica non necessaria è entrata nei percorsi pairing/TLS/firmware;
- i risultati sono documentati nel file appropriato.

Segnale finale:

`ENROLLMENT_FIXED_21=PASS`

`MILESTONE_COMPLETE: ENROLLMENT_FIXED_21`
