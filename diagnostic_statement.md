<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Diagnostic statement — Goodix Manager

**Stato:** desiderata funzionale approvato nel brainstorming del 7 novembre 2026; non è una specifica UI né un'autorizzazione a implementare.  
**Ambito:** integrazione del driver Goodix USB 27c6:5125 con Fedora KDE, inclusi i prerequisiti e i percorsi di autenticazione.  
**Evidenza motivante:** [issue #55](https://github.com/sorguido/goodix-27c6-5125/issues/55).  
**Routing:** `ROADMAP.md` definisce fasi ed EXIT_GATE; `AGENTS.md` governa i limiti permanenti. Questo file possiede il **desiderata diagnostico**, non i gate.

## Visione

Goodix Manager deve evolvere da gestore di installazione e aggiornamento a strumento di diagnosi dell'intera integrazione del nostro driver con Fedora. Il pulsante oggi denominato **Copy diagnostics** è il punto di ingresso a un centro diagnostico interattivo: verifiche richieste dall'utente, stato attuale leggibile e rapporti differenziati in base al problema. Non progettare ora la disposizione grafica dei controlli.

Un driver correttamente installato **non equivale** a un sistema di autenticazione biometrica necessariamente funzionante: libfprint, fprintd, systemd, D-Bus, PAM/Plasma, sudo, polkit, SELinux, USB e il sistema ospite sono possibili punti di errore esterni al solo payload.

Obiettivo misurabile in termini qualitativi: **ridurre il tempo necessario a individuare oppure escludere una causa**, producendo messaggi comprensibili all'utente ed evidenze utili al maintainer, senza indebolire installazione, FTC, autenticazione o sicurezza. Non tentare di coprire il 100% delle casistiche e non attribuire frequenze statistiche agli eventi senza dati. Evitare un cruscotto spettacolare di indicatori cromatici privi di valore diagnostico.

## 1. Lezione dell'issue #55

Il caso della [issue #55](https://github.com/sorguido/goodix-27c6-5125/issues/55) mostra un rifiuto giustificato dell'installazione accompagnato da un messaggio poco discriminante: `operation_failed`. L'ambiente Fedora 45 presentava almeno due anomalie documentate:

- un override `fprintd.service.d/keepalive.conf` lasciato da una precedente installazione di un altro driver, con `ExecStart=/usr/libexec/fprintd --no-timeout`; l'override è sufficiente a far scattare la protezione dell'installer contro configurazioni non riconosciute;
- file essenziali mancanti dal pacchetto Fedora `libfprint`, rilevati con verifica RPM, incluse librerie condivise. La loro assenza è compatibile con il precedente errore di avvio di fprintd, ma il nesso con lo status 127 non è stato dimostrato senza il relativo journal.

Il driver ha fatto la cosa corretta fermandosi davanti a uno stato incompatibile. Il problema da risolvere non è renderlo più permissivo, ma **rendere intelligibile quale verifica ha fallito e perché**. Una segnalazione contestuale dovrebbe distinguere il controllo bloccante, il possibile problema concorrente, lo stato finale e le azioni **non** eseguite.

## 2. Aree di copertura diagnostica

La scelta deve essere guidata da dipendenze tecniche, capacità discriminante e impatto sulla sicurezza, non da stime immotivate sulla frequenza dei bug.

| Area | Oggetto dei controlli |
| --- | --- |
| Installazione e integrità | Versioni driver/Manager, provenienza RPM, file mancanti o modificati, inventario e payload, installazioni parziali, residui di precedenti driver, blocchi di install/update, stato di rollback |
| Componenti Fedora | Integrità `libfprint`/`fprintd`, dipendenze, servizi systemd, unità e override effettivi, disponibilità librerie, comunicazione D-Bus |
| Autenticazione e sicurezza | Integrazione PAM Plasma, sudo e polkit; configurazioni effettive; SELinux enforcing, contesti, permessi e proprietà dei file pertinenti |
| Dispositivo e trasporto | Rilevamento USB 27c6:5125, identità e compatibilità, inizializzazione, percorso di comunicazione TLS/USB, timeout, disconnessioni ed errori di protocollo |
| Uso quotidiano | Enrollment, verify/identify, `NO_MATCH`, mancata acquisizione, FDT, conclusione dei tentativi, recupero e possibilità di ripetere senza bloccare il workflow |
| Eventi e cronologia | Cold login, ripresa da sospensione, aggiornamenti, timestamp correlati tra driver, libfprint, fprintd, PAM, login manager e componenti di sistema |

La diagnostica deve rispondere a **due domande diverse**:
1. «Il sistema è configurato correttamente adesso?» — verifiche dello stato corrente.
2. «Che cosa è successo quando l'impronta non ha funzionato?» — ricostruzione degli eventi, anche dopo che l'errore è terminato.

Una fotografia positiva del presente non dimostra che un precedente cold login non abbia fallito. Inoltre non bisogna confondere esito corretto di fprintd con garanzia sul successivo login.

## 3. Controlli statici e controlli dinamici

### Statici, read-only e senza interazione col sensore

Sono la base utile **anche prima dell'installazione**. Verificano ambiente Fedora, dipendenze, integrità RPM, PAM, override systemd, SELinux, servizi e presenza USB senza claim/inizializzazione del dispositivo, acquisizione, pairing, installazione o correzioni. Le verifiche più approfondite, potenzialmente costose, si eseguono su richiesta, non obbligatoriamente a ogni apertura del Manager. Una verifica non possibile va riportata come **non eseguita / dato indisponibile**, mai come PASS.

### Dinamici, espliciti e con perimetro controllato

Solo dopo azione consapevole dell'utente, possono verificare l'interazione con fprintd e un normale percorso biometrico. Il test deve utilizzare l'architettura ordinaria del driver: **nessun comando USB sperimentale, nessun aggiramento delle protezioni, nessuna manipolazione speciale dello stato**. Spiegare quando una normale prima azione biometrica può avviare il pairing qualificato già previsto. Separare sempre test di funzionamento ordinario da garanzie che esso non può fornire.

## 4. Rapporti diagnostici mirati

Non produrre un unico archivio indiscriminato. Ogni rapporto contiene una base comune (ambiente, versioni, timestamp, classificazione del problema), più la raccolta specifica necessaria alla domanda. I profili iniziali desiderati sono:

**A — Stato del sistema.** Stato Fedora/kernel, componenti e versioni, dipendenze, integrità e configurazioni necessarie alla compatibilità. Prevalentemente metadati; non per questo garantiti anonimi.

**B — Installazione o aggiornamento fallito.** Preflight, dipendenze, configurazioni incompatibili o residuali, fase precisa del blocco, errore, eventuale rollback e stato verificato dopo l'operazione. Deve essere utile anche con driver mai installato.

**C — Riconoscimento o acquisizione.** Eventi libfprint/fprintd e del driver per un intervallo richiesto; distinzione tra `NO_MATCH`, errore FDT, acquisizione incompleta, errore di comunicazione, timeout e recupero della sessione.

**D — Login e autenticazione.** Correlazione degli eventi di Plasma Login/SDDM, PAM, fprintd e, secondo il contesto, sudo o polkit; opzione di selezionare boot, intervallo temporale o avvio precedente, nei limiti del journal disponibile.

**E — Diagnostica approfondita.** Journal, errori SELinux, configurazioni effettive, stato di sistema e metadati del driver in un perimetro limitato e motivato. Da usare quando i rapporti mirati non sono sufficienti.

Ogni rapporto deve distinguere almeno:
- **PASS / anomalia osservata / controllo non eseguito / dati non disponibili**;
- **evidenza osservata / interpretazione deterministica / possibile causa non dimostrata**;
- tempo e ambito della verifica, incluse le verifiche escluse;
- esito e fase dell'operazione, quando applicabile.

Quando possibile, il backend dovrebbe esporre **codici di errore strutturati e stabili associati alla fase dell'operazione** (ad esempio controllo di override fprintd), anziché restituire solo `operation_failed` o perdere il motivo originale e tentare di ricostruirlo in seguito interpretando testo libero. La raccolta da sola non può recuperare informazioni già scartate a monte.

## 5. Dati potenzialmente sensibili e consenso

È accettabile che un rapporto esteso, se pertinente e richiesto esplicitamente, raccolga dati **potenzialmente sensibili**: nomi utente, percorsi, identificativi hardware, timestamp, processi, configurazioni PAM, metadati biometrici nei journal e altre informazioni contestuali. L'utente va avvisato **prima della raccolta o generazione pertinente**, con indicazione chiara delle categorie e delle conseguenze della condivisione. Deve poter esaminare il rapporto prima di salvarlo o diffonderlo. Una redazione automatica può aiutare, senza promettere anonimizzazione completa.

Restano **sempre esclusi** dall'esportazione: PSK, password e credenziali, template biometrici, immagini dell'impronta, contenuti del pairing, file dello stato segreto e dump grezzi del sensore/USB che possano incorporare dati protetti. L'accettazione di un avviso non autorizza a estrarre segreti o biometria protetta.

I file diagnostici devono restare locali, con permessi restrittivi e raccolta minima necessaria. **Nessun upload automatico e nessuna telemetria.** L'utente sceglie se e dove pubblicarli; il software mantiene la responsabilità della minimizzazione e della chiarezza del rischio.

## 6. Errori intermittenti e cronologia

I fallimenti FDT, `NO_MATCH`, TLS/USB e i cold login occasionali possono essere conclusi quando l'utente apre il Manager. Occorre perciò sfruttare i journal già presenti e consentire una selezione temporale circoscritta, eventualmente anche sul boot precedente se i dati sono stati conservati. Se i journal non sono persistenti o l'intervallo non è recuperabile, segnalarlo esplicitamente; non trasformare l'assenza di dati in assenza di problemi.

La ricostruzione dovrebbe distinguere almeno:
- acquisizione non completata;
- acquisizione completata ma esito `NO_MATCH`;
- errore di trasporto o inizializzazione;
- risultato valido restituito dal driver, ma percorso di autenticazione che non lo gestisce correttamente.

Prima soluzione: raccolta on-demand e correlazione di eventi esistenti. **Non introdurre automaticamente servizi diagnostici residenti, nuovi retry, raccolta permanente o logging globale più verboso**. Un'eventuale strumentazione aggiuntiva richiederebbe evidenza della lacuna diagnostica, un perimetro e una decisione specifica.

## 7. Diagnosi non significa riparazione

Il centro diagnostico **non** è un centro di riparazione automatica. Può identificare un override incompatibile, mostrare il file coinvolto, spiegare il motivo del blocco e orientare verso la documentazione. Non deve eliminare file, reinstallare pacchetti o modificare automaticamente PAM, fprintd, systemd o SELinux.

Un file RPM mancante è un'evidenza osservabile; un timeout non identifica automaticamente la causa. Messaggi e rapporti devono evitare diagnosi più assertive di quanto le prove consentano. Non cambiare la logica FTC, i controlli fail-closed o le protezioni dell'installer per far passare casi non qualificati. Password login e recovery rimangono essenziali.

## 8. Metodo di progettazione e criteri di successo

Prima di qualunque implementazione costruire una **matrice diagnostica**: per ogni controllo, problema che permette di individuare/escludere, fonte dati, costo, privilegi necessari, accesso USB sì/no, classificazione privacy, interpretazione sostenibile e limite dell'inferenza. Questa matrice è la base per selezionare una gamma **sufficiente** di controlli, non una copertura enciclopedica.

Poi classificare cosa è già disponibile nel Manager/helper e cosa richiede estensioni minime. La proposta è una diagnostica modulare, locale, on-demand e progressiva, con interpretazioni **deterministiche, documentabili e testabili** per anomalie conosciute. Non simulare capacità diagnostiche inesistenti; non prevedere risoluzioni o attribuzioni causali probabilistiche non corroborate.

Il caso-obiettivo della #55: invece di «The operation failed», il Manager potrebbe indicare che l'installazione è stata rifiutata per un override fprintd non riconosciuto, precisare che il driver **non è stato attivato**, riportare il percorso del file e distinguere eventuali altri difetti Fedora rilevati. Nessun intervento correttivo implicito.

**Risultato desiderato:** non «ecco centinaia di righe di log», ma «ecco quale controllo è fallito, che cosa è osservabile, quali cause sono plausibili e quale rapporto pertinente possiamo consegnare al maintainer», sempre entro i limiti della prova.

## Confine di questa fase

Questa versione è **solo dichiarazione di obiettivi e vincoli**. Non stabilisce design UI, layout, API definitive, implementazione, nuove autorizzazioni per modifiche host, packaging o calendario di release. La prossima attività da autorizzare è la matrice diagnostica e il confronto puntuale con ciò che il codice attuale già permette.
