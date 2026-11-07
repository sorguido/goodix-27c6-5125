<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# ROADMAP.md — Goodix Manager: diagnostica (`diagnostic`)

## Obiettivo e ambito

Evolvere `Copy diagnostics` in un centro diagnostico on-demand per l'integrazione Goodix 27c6:5125 su Fedora KDE: controlli leggibili, identificazione di incompatibilità note e rapporti mirati ai problemi di installazione e uso quotidiano. Il desiderata completo, inclusi privacy, esclusioni e confine fra diagnosi e riparazione, appartiene a **[`diagnostic_statement.md`](development/diagnostic/diagnostic_statement.md)**. `AGENTS.md` rimane l'autorità per gli invarianti permanenti.

**Percorso primario:** riusare helper, stato e journal esistenti; introdurre la minima estensione read-only, deterministica e verificabile. Nessuna modifica preventiva al motore ChicagoHS, trasporto, pairing, PAM, installer fail-closed o configurazione stock. Eventuali alternative più invasive sono fallback da valutare solo dopo evidenza dell'insufficienza del percorso primario e decisione umana specifica.

La draft 3.0.1 e i risultati ChicagoHS appartengono alla milestone precedente: non sono oggetto di questo ramo. Non anticipare merge, pubblicazione, nuova release o modifiche host.

## State machine — fase diagnostica

### DIAG0 — Dichiarazione degli obiettivi e riferimenti GUI (DOCUMENTATION ONLY)
- **PURPOSE:** consolidare la visione, il caso motivante #55 e il concept GUI approvato, senza modificare il driver.
- **PRIMARY_ARTIFACT:** `development/diagnostic/diagnostic_statement.md` (locale, gitignored).
- **EXIT_GATE:** desiderata e riferimenti GUI collegati nel routing; presenza e leggibilità degli artefatti locali verificate dall'agente con accesso al checkout; `CORROBORATIONS.md` registra la sola evidenza esterna; nessuna modifica di codice o host.
- **NEXT:** DIAG1, solo dopo autorizzazione dell'utente.

### DIAG1 — Matrice diagnostica (DESIGN)
- **PURPOSE:** scegliere controlli pertinenti, profili di log, fonti, privilegi, costo, dati sensibili, limiti di interpretazione e comportamenti read-only; distinguere disponibilità delle prove da esito positivo.
- **PRIMARY_ARTIFACT:** un artefatto decisionale di fase, da creare soltanto all'avvio di DIAG1.
- **EXIT_GATE:** matrice completa per le aree prioritarie, copertura ragionata delle failure più significative, raccolte delimitate, profili A–E e decisione documentata sui rischi; approvazione umana del perimetro.
- **NEXT:** DIAG2.

### DIAG2 — Contratti e osservabilità (DESIGN / IMPLEMENTATION)
- **PURPOSE:** mappare il codice esistente e definire/aggiungere soltanto le sonde e i codici stabili indispensabili a localizzare la fase del fallimento; preservare helper ristretto, autorizzazioni e fail-closed.
- **PRIMARY_ARTIFACT:** contratto diagnostico verificabile e relativo codice/test.
- **EXIT_GATE:** casi noti (in particolare blocco override fprintd e integrità libfprint) classificabili senza falsi PASS; nessun segreto o dato protetto esportabile; regressioni pertinenti PASS.
- **NEXT:** DIAG3.

### DIAG3 — Centro diagnostico e rapporti (IMPLEMENTATION)
- **PURPOSE:** esporre controlli su richiesta, messaggi discriminanti e generatori di rapporti mirati senza fare del Manager un riparatore del sistema. Mantenere navigazione, linguaggio non tecnico e stile KDE/Goodix Manager del mockup approvato; modifiche motivate solo da fattibilità, sicurezza o qualità dell'esperienza utente.
- **PRIMARY_ARTIFACT:** Manager/helper con test UI e di sicurezza. Riferimenti visuali locali: [mockup HTML](development/diagnostic/Goodix_Diagnostic_Center_mockup.html), [diagramma di navigazione](development/diagnostic/Goodix_Diagnostic_navigation.png) e [tavola concept](development/diagnostic/mockup icon to be used.png). L'HTML è un **prototipo grafico**, non una specifica di backend né una prova che i controlli funzionino.
- **EXIT_GATE:** controlli statici utilizzabili anche prima dell'installazione; test dinamici solo espliciti; consenso preventivo per raccolte potenzialmente sensibili; anteprima locale; nessun upload/telemetria.
- **NEXT:** DIAG4.

### DIAG4 — Correlazione eventi e qualificazione (TEST / REVIEW)
- **PURPOSE:** qualificare install/update, runtime sano e degradato, login e casi intermittenti, con journal incompleti/non persistenti e rifiuti sicuri.
- **PRIMARY_ARTIFACT:** evidenze di test e review indipendente, non diario nel manuale.
- **EXIT_GATE:** distinzione dimostrata fra `NO_MATCH`, mancata acquisizione/FDT, trasporto e autenticazione; nessuna modifica non autorizzata al sistema; comportamento corretto con errori, dati mancanti e autorizzazioni negate; regressioni e recovery pertinenti PASS.
- **NEXT:** DIAG5.

### DIAG5 — Accettazione e release (HUMAN GATE)
- **PURPOSE:** ottenere approvazione del comportamento effettivo su Fedora KDE, della privacy e della compatibilità prima dell'integrazione.
- **PRIMARY_ARTIFACT:** decisione di accettazione basata sulle evidenze.
- **EXIT_GATE:** review finale e autorizzazione umana esplicita per test live, merge e pubblicazione, ciascuno secondo `AGENTS.md`.
- **NEXT:** milestone conclusa solo con prove sufficienti; altrimenti CORRECTIVE o BLOCKED.

## Disponibilità dei riferimenti progettuali

I materiali in `development/diagnostic/` sono **gitignored e locali**, non pubblicati né recuperabili da GitHub. Prima di iniziare DIAG1/DIAG3, l'agente che opera sul checkout deve verificarne la presenza e leggerli tramite `ARTIFACT_INDEX.json`. Un agente remoto privo di accesso a quella cartella deve segnalare l'assenza del contesto e **non inventare** i contenuti del mockup. La GUI approvata orienta la presentazione; comportamento, privilegi e diagnostica devono essere qualificati separatamente.

## Stato autorizzato alla data del documento

**Solo DIAG0 documentale.** Non iniziare DIAG1 né alcuna implementazione senza il relativo passaggio autorizzato. `PROJECT_STATE.json` è una cache non autoritativa: Git ed evidenze prevalgono. `TECHNICAL_MANUAL.md` resta reference tecnica durevole, non registro di test o di orchestrazione.
