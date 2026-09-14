<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Publication Policy — documentazione pubblica Goodix 27c6:5125

## Scopo

Questa policy definisce come deve essere progettata, riscritta, revisionata e approvata la documentazione destinata alla pubblicazione del progetto Goodix `27c6:5125`.

È una policy editoriale e di pubblicazione, non un diario di sviluppo e non una descrizione della roadmap tecnica.

Il principio fondamentale è:

> La documentazione pubblica deve essere comprensibile a un utente esterno tecnicamente competente che scopre oggi il progetto e non conosce nulla della sua storia di sviluppo, delle milestone interne, dell'orchestrazione AI o della nomenclatura usata nel repository privato.

In forma normativa:

```text
PUBLIC_DOCUMENTATION_AUDIENCE=EXTERNAL_USER_WITH_ZERO_PROJECT_HISTORY
PUBLIC_DOCUMENTATION_MUST_BE_SELF_CONTAINED=true
PUBLIC_DOCUMENTATION_MUST_DESCRIBE_CURRENT_PRODUCT_STATE=true
PUBLIC_DOCUMENTATION_MUST_NOT_DESCRIBE_DEVELOPMENT_CHRONOLOGY=true
PUBLIC_DOCUMENTATION_LANGUAGE=ENGLISH
PUBLIC_DOCUMENTATION_REQUIRES_USER_EDITORIAL_APPROVAL=true
```

---

## 1. Regola editoriale principale

La documentazione interna esistente è **materiale sorgente**, non un template di pubblicazione.

```text
INTERNAL_DOCUMENTATION=SOURCE_MATERIAL_ONLY
INTERNAL_DOCUMENTATION_IS_NOT_A_PUBLICATION_TEMPLATE=true
```

La documentazione pubblica deve essere riscritta dal punto di vista del prodotto finale e dell'utente finale.

Non deve raccontare come il driver è stato costruito, quali tentativi sono falliti, quali milestone interne sono state attraversate, quali corrective sono stati necessari o quali alternative storiche sono state provate e poi abbandonate.

La domanda guida è sempre:

> Questa informazione serve a un utente esterno per capire, installare, usare, amministrare, aggiornare, disinstallare, recuperare o sviluppare il prodotto attuale?

Se la risposta è no, l'informazione non appartiene alla superficie pubblica.

---

## 2. Terminologia e concetti interni da non esporre

Salvo eccezione esplicita richiesta dall'Utente, la documentazione pubblica non deve contenere terminologia di orchestrazione o sviluppo interna, per esempio:

- milestone `Dxxx` (`D294`, `D295/02`, ecc.);
- `Human Gate`;
- `AI PM`, `AI Executor`, `AI Esecutrice`;
- `PM_DECISION`, `CURRENT_TASK`, `NEXT_BOUNDARY`, `PROJECT_STEP_COMPLETE`;
- stato di closure delle fasi come narrativa per l'utente;
- `PASS live`, `PASS_HUMAN_OBSERVED`, `corrective`, `boundary`, `gate` nel significato interno del progetto;
- commit SHA usati per raccontare la storia dello sviluppo;
- sequenze del tipo “prima abbiamo provato X, poi Y, poi abbiamo corretto Z”;
- alternative storiche non distribuite o non più rilevanti per il prodotto finale;
- riferimenti alla gestione interna del progetto, alla conversazione tra Utente e AI o alla roadmap A→F.

Questi contenuti possono restare nel repository privato come evidence, analysis, audit, provenance o storia tecnica, ma non devono essere trasferiti automaticamente nella documentazione destinata al pubblico.

Una parola o un concetto tecnico non è vietato in sé: può comparire se è realmente necessario per spiegare il funzionamento attuale del prodotto a un lettore esterno.

---

## 3. Cosa deve descrivere la documentazione pubblica

La superficie pubblica deve descrivere **lo stato corrente e supportato del prodotto**.

Esempi di contenuti appropriati:

- hardware supportato;
- distribuzioni e versioni supportate;
- prerequisiti;
- dipendenze;
- procedura di installazione;
- preparazione dei materiali specifici del dispositivo quando necessaria;
- enrollment delle impronte;
- login, `sudo` e integrazione KDE/fprintd;
- aggiornamento;
- rollback e recovery solo nella misura utile all'utente/amministratore;
- disinstallazione;
- troubleshooting;
- architettura corrente;
- modello di sicurezza;
- gestione dei dati biometrici;
- limiti noti;
- compatibilità e scope dichiarato;
- licensing e attribution;
- credits e acknowledgements.

La documentazione può essere molto tecnica, ma deve essere tecnica **sul prodotto**, non tecnica **sulla storia del progetto**.

---

## 4. Architettura editoriale attesa

La struttura finale può evolvere, ma la documentazione pubblica dovrebbe essere organizzata secondo compiti e bisogni del lettore, non secondo milestone interne.

Una struttura tipica può includere:

1. Overview / What this driver supports
2. Supported hardware and software
3. Requirements
4. Installation
5. Device-specific setup
6. Fingerprint enrollment
7. Login and `sudo`
8. Updating
9. Uninstallation
10. Recovery
11. Troubleshooting
12. Technical architecture
13. Security and privacy
14. Known limitations
15. Licensing and attribution
16. Credits / acknowledgements

Non è obbligatorio usare esattamente questi titoli, ma il principio è vincolante: organizzare per uso e comprensione del prodotto, non per cronologia di sviluppo.

---

## 5. Manuale tecnico pubblico

Il manuale tecnico pubblico deve essere rieditato come **vera reference tecnica**, integralmente in inglese.

Non deve essere una traduzione letterale del manuale privato corrente.

Non deve conservare la struttura da diario del tipo:

- “in Dxxx abbiamo provato…”;
- “poi in Dyyy abbiamo scoperto…”;
- “il corrective successivo ha…”;
- “questa milestone ha chiuso…”

Deve invece estrarre e riorganizzare la conoscenza tecnica stabile, ad esempio:

- architettura driver;
- stack `libfprint -> fprintd -> PAM/KDE`;
- protocollo e sessione sicura;
- acquisizione immagine;
- pipeline biometrica;
- enrollment e matching;
- gestione template;
- materiali device-specific;
- integrazione systemd/SELinux/PAM;
- lifecycle supportato;
- modello di sicurezza;
- compatibilità;
- limiti noti.

In forma normativa:

```text
TECHNICAL_MANUAL_PUBLIC_LANGUAGE=ENGLISH
TECHNICAL_MANUAL_PUBLIC_STYLE=NON_CHRONOLOGICAL_TECHNICAL_REFERENCE
TECHNICAL_MANUAL_DXXX_DIARY_NARRATIVE_ALLOWED=false
```

---

## 6. Lingua della documentazione pubblica

Tutta la documentazione destinata al pubblico deve essere in inglese prima della pubblicazione.

Questo include almeno:

- README pubblici;
- guida installazione;
- guida aggiornamento/disinstallazione/recovery;
- troubleshooting;
- manuale tecnico pubblico;
- documentazione amministrativa pubblica;
- documentazione sviluppatori destinata al repository pubblico;
- licensing/attribution notes rivolte al pubblico;
- credits e acknowledgements.

Non rientrano in questo requisito, perché sono governance interna:

- `AGENTS.md`;
- `START_PROMPT.md`;
- `Linee Guida di Progetto Goodix 27c6 5125 per AI.md`;
- analysis/evidence/orchestration privati non destinati alla pubblicazione.

---

## 7. Separazione pubblico / privato e `red_tag/`

Prima della pubblicazione finale, ogni file o directory che non deve essere incluso nella superficie pubblica deve essere spostato sotto:

```text
red_tag/
```

La directory deve essere aggiunta a `.gitignore`.

Nessuna build, test, release o documentazione pubblica può dipendere da contenuti presenti in `red_tag/`.

Lo spostamento deve avvenire soltanto dopo audit di:

- import;
- build;
- test;
- script;
- riferimenti documentali;
- provenance;
- licensing;
- dipendenze runtime/production.

`red_tag/` non è un cestino e non autorizza cancellazioni casuali.

```text
PUBLIC_RELEASE_NONPUBLIC_MATERIAL_LOCATION=red_tag/
RED_TAG_MUST_BE_GITIGNORED=true
PUBLIC_BUILD_DEPENDS_ON_RED_TAG=false
PUBLIC_TESTS_DEPEND_ON_RED_TAG=false
PUBLIC_RELEASE_DEPENDS_ON_RED_TAG=false
```

---

## 8. Regola per README e guide operative

README e guide operative devono partire dal presupposto che il lettore:

- non ha seguito lo sviluppo;
- non conosce le milestone Dxxx;
- non conosce la roadmap A→F;
- non sa quali prototype o strategie precedenti siano esistiti;
- non conosce AI PM o AI Executor;
- vuole sapere se il proprio hardware è supportato e come usare il driver.

Pertanto non devono includere dettagli storici irrilevanti come:

- formati di packaging abbandonati;
- corrective interni;
- test gate già superati;
- commit storici;
- motivazioni di orchestrazione;
- failure intermedi ormai risolti.

Se una decisione storica ha conseguenze ancora rilevanti per l'utente, documentare **la conseguenza attuale**, non il percorso storico che l'ha prodotta.

Esempio:

- corretto: “The installer configures Plasma fingerprint authentication using a managed PAM override and does not modify Fedora's package-owned PAM file.”
- non corretto: “D295/02 fixed the plasmalogin PAM failure found during the Human Gate.”

---

## 9. Documentazione interna ed evidence

La policy non impone di cancellare la storia tecnica privata.

La cronologia Dxxx, i test falliti, i corrective, le decisioni PM, gli operator kit storici e le evidence possono rimanere disponibili nel repository privato finché utili per:

- audit;
- regressione;
- provenance;
- debugging;
- manutenzione;
- ricostruzione storica;
- verifica di safety e licensing.

Il requisito è la **separazione editoriale** fra conoscenza interna e superficie pubblica.

---

## 10. Gate editoriale di Phase F

La Phase F non può essere dichiarata chiusa soltanto perché la documentazione è tecnicamente corretta o tradotta in inglese.

Prima della pubblicazione deve essere eseguita una review editoriale specifica.

Criteri minimi:

```text
PUBLIC_DOCS_LANGUAGE=ENGLISH
PUBLIC_DOCS_SELF_CONTAINED=true
PUBLIC_DOCS_ZERO_PROJECT_HISTORY_DEPENDENCY=true
PUBLIC_DOCS_ZERO_DXXX_NARRATIVE=true
PUBLIC_DOCS_ZERO_AI_ORCHESTRATION_TERMINOLOGY=true
PUBLIC_DOCS_DESCRIBE_CURRENT_PRODUCT_STATE=true
TECHNICAL_MANUAL_NON_CHRONOLOGICAL=true
RED_TAG_AUDIT=PASS
PUBLIC_BUILD_TEST_RELEASE_DEPENDENCY_ON_RED_TAG=false
USER_EDITORIAL_APPROVAL=REQUIRED
```

Test mentale obbligatorio:

> Could this document be handed to a Fedora user who found the project today, without explaining any project history first?

Se la risposta è no, il documento non è pronto per la pubblicazione.

---

## 11. Autorità editoriale dell'Utente

La classificazione finale di ciò che è pubblico, privato, storico, troppo interno, troppo verboso o editorialmente inadatto appartiene all'Utente.

L'AI può proporre struttura, riscrittura, classificazione e cleanup, ma non può dichiarare conclusa la documentazione pubblica senza approvazione editoriale esplicita dell'Utente.

```text
PHASE_F_PUBLIC_DOCUMENTATION_REQUIRES_USER_EDITORIAL_APPROVAL=true
```

Questa approvazione è distinta dalla correttezza tecnica: un documento può essere tecnicamente vero e comunque essere editorialmente inadatto alla pubblicazione.

---

## 12. Sintesi normativa

```text
PUBLIC_DOCS_AUDIENCE=EXTERNAL_USER_WITH_ZERO_PROJECT_HISTORY
PUBLIC_DOCS_SOURCE_OF_TRUTH=CURRENT_SUPPORTED_PRODUCT_STATE
PRIVATE_HISTORY_IS_PUBLICATION_TEMPLATE=false
PUBLIC_DOCS_LANGUAGE=ENGLISH
PUBLIC_DOCS_DXXX_HISTORY_ALLOWED=false
PUBLIC_DOCS_AI_ORCHESTRATION_TERMS_ALLOWED=false
PUBLIC_TECHNICAL_MANUAL=NON_CHRONOLOGICAL_REFERENCE
PUBLICATION_REQUIRES_RED_TAG_AUDIT=true
PUBLICATION_REQUIRES_USER_EDITORIAL_APPROVAL=true
```
