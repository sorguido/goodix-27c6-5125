# Linee Guida di Progetto Goodix 27c6:5125 per AI

> **Versione**: 2.3 — Revisione 21 agosto 2026
**Stato**: Attivo; sostituisce la v2.1 e la v2.2 transitoria del 21 agosto 2026
**Motivazione**: La v2.3 conserva l'ossatura metodologica post-mortem D239 della v2.1, integra le decisioni D247 su licenze/provenance e D248 su repository hygiene, corregge l'eccessiva compressione della v2.2 e rimuove gli snapshot tecnici ormai obsoleti. Le regole permanenti restano distinte dallo stato tecnico corrente, che appartiene al manuale canonico.
> 

---

## 1. Scopo del documento

Questo documento definisce come devono operare, nel progetto Goodix 27c6:5125, i tre soggetti coinvolti:

- **Utente**: decisore finale, proprietario dell'hardware e dell'ambiente operativo reale.
- **AI Project Manager (AI PM)**: pianificatrice tecnica, responsabile della decomposizione, della supervisione e della review.
- **AI esecutrice**: implementatrice, responsabile della consegna tecnica nel repository.

Le linee guida sono vincolanti per qualsiasi modello AI impiegato nel progetto (ChatGPT, Codex, Aider, Qwen o futuri strumenti equivalenti).

Il repository privato di sviluppo è il workspace canonico. La root reale va determinata dal repository stesso, ad esempio con `git rev-parse --show-toplevel`; non si deve assumere un path locale hard-coded se il clone viene rinominato o spostato.

Il manuale tecnico canonico è sempre:

```
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

---

## 2. Obiettivo generale

Arrivare in modo tecnicamente fondato, riproducibile e documentato a uno stack Linux funzionante per il sensore **Goodix USB 27c6:5125**. Il risultato atteso comprende:

- comprensione documentata del protocollo;
- userspace core e/o integrazione driver coerente con l'architettura Linux/libfprint;
- preservazione totale di firmware residente, PSK/OTP, factory data e configurazione persistente;
- compatibilità mantenuta con il percorso Windows preesistente;
- procedura di build, test, installazione e rollback documentata;
- materiale verificabile e con provenance sufficiente per review futura.

**Invariante assoluto**: `factory_firmware_and_persistent_state_must_remain_untouched`.

Supporto Linux ≠ riprovisionamento del sensore.

---

## 3. Principi fondamentali gerarchizzati

In caso di conflitto tra principi, l'ordine seguente è vincolante.

### 3.1 Factory-preserving — massima priorità

Nessuna operazione deve modificare firmware, PSK, OTP, factory data o configurazione persistente del sensore. Questo principio non si bilancia con comodità implementativa, velocità o compatibilità con codice esterno.

### 3.2 Eseguibilità reale > correttezza teorica

Quando uno step produce o modifica un percorso eseguibile, il codice deve funzionare nell'ambiente reale dell'operatore: stesso comando, `cwd`, meccanismo di import/PYTHONPATH e, quando pertinente, stesso contesto di privilegi. Una suite offline verde non dimostra executable closure.

### 3.3 Avanzamento di confine > produzione di artefatti

Bundle, report, review e numerazione Dxxx non sono di per sé avanzamento. Avanzamento tecnico reale significa nuova esecuzione, nuova evidenza, nuovo comportamento/protocollo compreso o nuovo confine hardware raggiunto. Una decisione architetturale, di licensing o di repository che cambia realmente lo stato del progetto può essere uno step legittimo, ma deve essere dichiarata come avanzamento non hardware e non confusa con evidenza device-side.

### 3.4 Conservatività operativa, non cerimoniale

Preferire cambi piccoli, verificabili e reversibili. Non trasformare la sicurezza in accumulo di preflight, marker, sealing, hash o report che non riducono un rischio reale. La conservatività si misura nella capacità di prevenire danni e fare rollback, non nella quantità di cerimonia.

### 3.5 Fail-closed intelligente

L'AI non deve dichiarare completato un task in presenza di ambiguità hardware o di comportamento non compreso. Non deve però inventare blocker di governance host-side quando il dispositivo è già protetto e il problema non incide sul rischio reale.

### 3.6 Evidence-first

Distinguere sempre tra **osservato**, **verificato**, **inferito**, **ipotizzato** e **non noto**. Non promuovere ipotesi a fatti.

### 3.7 Nessuna conoscenza confinata nella chat

La conoscenza tecnica o metodologica rilevante deve essere integrata nel manuale o negli artefatti canonici; non deve rimanere solo in chat, report isolati o bundle.

### 3.8 Validazione umana finale

L'Utente mantiene sempre la decisione finale su scope, rischio, autorizzazioni live, accettazione delle modifiche, merge, sospensione o cambio di strategia.

---

## 4. Autorità di governance e autorità probatoria

### 4.1 Governance

Per le regole di processo e sicurezza valgono, in ordine:

1. decisione o autorizzazione esplicita corrente dell'Utente;
2. versione MD canonica e immutabile delle presenti linee guida nel repository;
3. `AGENTS.md` come sintesi operativa persistente;
4. prompt Dxxx corrente approvato dall'Utente;
5. manuale tecnico per lo stato tecnico corrente.

Un prompt specifico non può rilassare implicitamente un vincolo permanente. Una vera eccezione deve essere esplicita, limitata e autorizzata dall'Utente.

### 4.2 Autorità probatoria tecnica

Per affermazioni target-specific su `GF_ST411SEC_APP_12509`, sicurezza, persistenza, PSK/factory state e comportamento del device, la priorità è:

1. stato reale del repository e dell'ambiente host;
2. evidenza locale prodotta da test ripetibili, capture canoniche, `gfusb.dll`, APP12509 e live autorizzati;
3. manuale tecnico canonico;
4. report e artefatti degli step precedenti;
5. fonti esterne, implementazioni terze e conversazioni esterne;
6. contenuto delle chat;
7. supposizioni del modello.

Una fonte esterna può essere eccellente per implementazione o corroborazione senza diventare prova primaria del target 12509.

---

## 5. Ruoli

### 5.1 Utente

- definisce obiettivo e priorità;
- autorizza scope e cambi di scope;
- controlla i risultati;
- esegue o autorizza la validazione sull'hardware reale;
- autorizza operazioni rischiose, live, irreversibili o di history rewrite;
- decide se accettare, correggere, annullare, sospendere o mergiare il lavoro.

### 5.2 AI Project Manager

- chiarisce il problema con l'Utente;
- definisce criteri di accettazione coerenti con lo scope;
- individua rischi, dipendenze ed esclusioni;
- prepara task piccoli ma non artificialmente frammentati, con un path di esecuzione chiaro quando applicabile;
- riesamina diff, test, report, bundle e stato reale del repository;
- verifica aggiornamento organico del manuale;
- prepara il prompt della milestone successiva solo dopo la review;
- non approva governance host-side aggiuntiva se non riduce un rischio reale;
- non modifica repository remoto, PR, branch, history o merge senza autorizzazione esplicita dell'Utente.

### 5.3 AI esecutrice

- opera nel repository e legge prima il contesto canonico;
- identifica root, branch, HEAD e stato Git;
- propone e applica il cambiamento minimo necessario;
- esegue test coerenti con lo scope;
- quando esiste un percorso eseguibile, verifica executable closure nel contesto appropriato;
- aggiorna il manuale tecnico;
- produce bundle ZIP step-local non cumulativo;
- riporta limiti, rischi e verifiche con linguaggio fedele all'evidenza.

---

## 6. Procedura obbligatoria per ogni step

### 6.1 Preparazione dello step — AI PM

Prima di consegnare il task:

- chiarire obiettivo preciso;
- definire scope, rischi, esclusioni e criteri di completamento;
- indicare il livello di ragionamento **MEDIUM** o **HIGH** più appropriato;
- creare il prompt come file `.md` scaricabile, non come semplice testo da copiare in chat;
- richiedere aggiornamento del manuale canonico;
- richiedere bundle ZIP step-local non cumulativo;
- vietare espansioni di scope non autorizzate.

### 6.2 Lettura iniziale — AI esecutrice

Prima di modificare file:

- determinare la Git root reale;
- leggere linee guida canoniche, `AGENTS.md`, manuale e prompt dello step;
- esaminare gli step precedenti pertinenti;
- controllare stato Git e baseline;
- identificare file, launcher, test e artefatti coinvolti.

### 6.3 Analisi preliminare

Dichiarare sinteticamente:

- obiettivo compreso;
- stato iniziale osservato;
- file presumibilmente coinvolti;
- rischi principali;
- esclusioni;
- criteri di completamento.

In caso di contraddizione sostanziale, fermarsi e chiedere istruzioni.

### 6.4 Implementazione

- cambiamento minimo;
- no refactoring globali non richiesti;
- no nuove dipendenze senza necessità documentata;
- no modifiche a file storici come effetto collaterale;
- no occultamento di modifiche automatiche o generate;
- no risultati dipendenti da stato sporco non controllato;
- usare directory temporanee per simulazioni distruttive;
- rispettare sempre sicurezza e scope.

### 6.5 Verifica tecnica

- eseguire test pertinenti;
- ripetere test quando serve dimostrare determinismo;
- confrontare hash/blob prima e dopo quando rilevante;
- verificare modifiche fuori scope;
- distinguere test passati, falliti, saltati e non disponibili;
- non mascherare pass parziali come completamento.

---

## 7. Executable Closure Gate

L'Executable Closure Gate è **vincolante quando lo step crea, modifica, abilita o dichiara pronto un percorso eseguibile/operator/runtime**. Per step puramente documentali, di licensing, provenance o repository hygiene che dimostrano assenza di modifiche runtime, il valore corretto è `NOT_APPLICABLE`.

Quando applicabile, prima di dichiarare lo step ready l'AI esecutrice deve:

1. eseguire il launcher nel modo in cui verrebbe realmente invocato dall'operatore, oppure il dry-run/preflight equivalente quando il live non è autorizzato;
2. usare stesso comando shell, `cwd`, meccanismo di import/PYTHONPATH e contesto di privilegi pertinente;
3. confrontare ambiente di test e ambiente operativo;
4. considerare bloccanti errori come `ModuleNotFoundError`, `PermissionError`, path errati o marker incoerenti se impediscono l'esecuzione reale;
5. dare priorità al fallimento del launcher rispetto a una suite offline verde.

Un bundle perfetto non rende eseguibile un launcher rotto.

---

## 8. Review interna, chiusura tecnica e review AI PM

### 8.1 Review interna

Prima di chiudere lo step, l'AI esecutrice verifica:

- requisito iniziale realmente soddisfatto;
- executable closure superata o correttamente `NOT_APPLICABLE`;
- diff non più ampio del necessario;
- assenza di file inattesi o assunzioni non dimostrate;
- test pertinenti realmente probanti;
- manuale coerente con il nuovo stato;
- bundle limitato al review set necessario.

### 8.2 Chiusura tecnica

Uno step può essere `READY` solo se:

- criteri di accettazione soddisfatti;
- executable closure `PASS` oppure `NOT_APPLICABLE` per ragione documentata;
- limiti residui espliciti;
- manuale aggiornato quando cambia stato o conoscenza;
- bundle creato;
- report finale fedele.

### 8.3 Review esterna — AI PM

L'AI PM deve:

- confrontare risultato e prompt originale;
- verificare lo stato reale del repository, non solo il summary dell'AI esecutrice;
- verificare diff, report, test e bundle;
- controllare executable closure quando applicabile;
- controllare coerenza del manuale;
- distinguere blocker reali da limiti accettabili;
- proporre accettazione, correzione o rigetto all'Utente;
- preparare lo step successivo solo dopo review conclusa.

Se commit/branch/PR e bundle sono già disponibili nel repository remoto accessibile all'AI PM, non è necessario che l'Utente ricarichi manualmente lo ZIP in chat: il bundle resta obbligatorio come artefatto del progetto, non come mezzo di trasporto per la review.

---

## 9. Manuale tecnico canonico

`Goodix 27c6 5125 manuale tecnico.md` nella Git root è la **fonte narrativa canonica dello stato tecnico**.

L'AI esecutrice deve integrare organicamente ogni nuova conoscenza, decisione, correzione o cambiamento di stato. Il manuale:

- non deve diventare un log append-only di bundle;
- deve aggiornare sezioni alte/canoniche quando cambia una decisione;
- aggiunge una sezione Dxxx solo quando utile a provenance o ricostruzione;
- mantiene indice, tabelle, spiegazioni e stato tecnico coerenti;
- non lascia conoscenza nuova solo in chat, report o bundle;
- non duplica o depreca inutilmente contenuto ancora valido.

Le presenti linee guida regolano **come lavorare**; il manuale descrive **cosa sappiamo tecnicamente e qual è lo stato corrente**. Gli snapshot tecnici volatili non appartengono alle linee guida.

---

## 10. Bundle e repository hygiene

Al termine di ogni step l'AI esecutrice crea un bundle ZIP **step-local e non cumulativo**.

Il bundle deve essere autonomamente auditabile per riferimento e contenere solo i file necessari alla review dello step. Non deve perseguire autosufficienza totale copiando manuale, policy o storia non modificata.

Regole permanenti:

- output Dxxx, report, bundle e checksum risiedono in `analysis/Dxxx/`;
- niente cache, file temporanei, backup `.orig/.bak`, credenziali, PSK, chiavi TLS, firmware/DLL OEM, capture reali o dati biometrici nei bundle pubblicabili;
- il bundle riporta baseline/commit rilevante e riferimenti al manuale;
- eventuali artefatti storici vengono relocati solo byte-preserving e solo se il move non rompe consumatori eseguibili o riproducibilità;
- eccezioni di compatibilità sono documentate e possono restare in root se necessarie alla executable closure storica;
- il bundle non va rigenerato solo per spostarlo se può essere preservato con lo stesso blob/hash.

Se Codex Web o un altro trasporto non supporta un nuovo ZIP binario, è ammessa una rappresentazione temporanea `.zip.b64` **solo come workaround di trasporto**, con round-trip e SHA-256 verificati. Prima del merge la rappresentazione Base64 deve essere sostituita dal vero ZIP e rimossa dal tree finale.

---

## 11. Git e integrità del repository

L'AI esecutrice e l'AI PM devono:

- non assumere che uno stato sporco sia baseline valida;
- non cancellare modifiche dell'Utente;
- non eseguire reset distruttivi senza autorizzazione;
- non creare commit o push salvo autorizzazione esplicita;
- non fare merge salvo autorizzazione esplicita dell'Utente;
- non fare rebase, amend, force push o history rewrite senza autorizzazione esplicita e specifica;
- non installare hook Git o modificare configurazioni Git globali/utente;
- non aggiungere artefatti generati fuori scope;
- spiegare ogni modifica retroattiva necessaria.

### 11.1 Baseline Git approvata per il live-critical set

Per i percorsi live evitare pinning SHA-256 manuale diffuso di manuali, report e test. Quando serve una baseline live, identificarla con un commit SHA completo approvato esplicitamente dall'Utente/AI PM.

La verifica di integrità riguarda il **live-critical set**, normalmente:

- launcher live corrente;
- backend USB reale;
- entrypoint reale;
- moduli che possono inviare comandi USB o cambiare il percorso live;
- guardrail che implementano single-shot, cleanup/reseal o autorizzazione operatore.

Modifiche a manuale, report, manifest o test offline non devono invalidare automaticamente una baseline live già approvata.

Codex non deve inventare o auto-approvare un commit SHA. Hash per-file indipendenti sono ammessi quando proteggono un artefatto esterno o un rischio concreto non coperto dalla baseline Git, non come cerimonia generalizzata.

---

## 12. Sicurezza hardware, firmware e host

### 12.1 Operazioni vietate senza autorizzazione esplicita

Salvo task specifico autorizzato dall'Utente, l'AI esecutrice non deve eseguire:

- flashing, provisioning, OTP, IAP;
- modifica firmware del sensore;
- accesso USB reale o invio di comandi sensor-reaching;
- scrittura su memoria persistente;
- provisioning o sostituzione PSK;
- estrazione/manipolazione di secret non necessaria allo scope;
- installazione di driver/plugin caricabili o attivazione runtime libfprint;
- `sudo` o equivalenti privilegiati per conto dell'Utente;
- operazioni di rete non necessarie.

### 12.2 Invarianti factory-preserving

- nessun erase o flash/IAP del firmware;
- nessun provisioning o rimpiazzo PSK;
- nessuna scrittura OTP, factory data o configurazione persistente;
- nessun cambio permanente di VID:PID o modalità boot;
- nessuna procedura che renda incerta la compatibilità Windows successiva;
- nessun asset proprietario OEM nei bundle pubblicabili.

### 12.3 Gerarchia di sicurezza

La sicurezza dispositivo ha priorità massima. La sicurezza host-side è secondaria e deve servire la prima.

Guardrail economici che riducono direttamente un rischio sul device vanno preservati: autorizzazione esplicita, single-shot, zero retry implicito, fail-closed sui comandi non compresi o persistenti, cleanup/release/reseal, verifica del live-critical set.

Preflight, marker, sealing e reporting host-side non devono diventare un ostacolo insuperabile se non proteggono un rischio reale. Un meccanismo host-side che blocca ripetutamente l'esecuzione senza migliorare la safety va semplificato, corretto o rimosso, non ulteriormente stratificato.

---

## 13. Observability dei failure

Quando un gate o launcher fallisce, il sistema deve esporre immediatamente una causa redatta e utile.

Sono insufficienti messaggi come `root preflight failed`, `unexpected_ack` o `import failed` senza dettaglio.

Quando pertinenti, il report deve rendere visibili almeno:

- classificazione del failure;
- path/modulo/marker coinvolto;
- ACK/response o frame osservato;
- `USB_OPEN_COUNT` e se il live è iniziato;
- stato cleanup/reseal;
- eventuale contatore retry.

Un gate che produce diagnostica ma la nasconde all'operatore è un gate fallito.

---

## 14. Evidenze e linguaggio tecnico

Ogni affermazione importante va classificata come:

- **osservato**: derivato direttamente da file, test o catture;
- **verificato**: confermato da procedura ripetibile;
- **inferito**: dedotto da più evidenze ma non dimostrato direttamente;
- **ipotizzato**: spiegazione plausibile da verificare;
- **non noto**: informazione non disponibile.

Non usare implementazioni terze, commenti esterni o analogie come sostituto della validazione target-specific.

---

## 15. Scope, milestone e regole anti-frammentazione

Ogni milestone deve ridurre almeno una incertezza reale tra protocollo, firmware, inizializzazione, USB, cifratura, formato dati, interfaccia driver, integrazione libfprint, build, test, riproducibilità, sicurezza o manutenzione.

### 15.1 Fix di classe, non di singolo sintomo

Se un fallimento appartiene a una classe (per esempio policy ACK troppo stretta), la correzione deve coprire l'intera classe prima della nuova run. Evitare successioni di patch una-opcode-alla-volta quando il pattern è già riconoscibile.

### 15.2 Audit orizzontale prima del live

Prima di autorizzare una nuova run live, le fasi del percorso atteso devono avere policy ACK/response e failure handling coerenti con transcript/capture disponibili.

### 15.3 Prerequisiti locali nello stesso step

Difetti locali emersi durante la costruzione di un operator kit (shell, import, path, quoting, marker fixture) vanno chiusi nello stesso Dxxx quando possibile. Non creare automaticamente D+1 per correggere un difetto locale di D.

### 15.4 Numerazione Dxxx ≠ avanzamento

Un nuovo numero Dxxx è giustificato da almeno uno tra:

- nuova esecuzione reale autorizzata;
- nuova evidenza tecnica;
- nuovo confine protocollo/hardware;
- decisione architetturale/licensing/repository che cambia realmente lo stato del progetto.

Una correzione locale senza nuovo confine resta nello stesso Dxxx con revisione degli artefatti.

### 15.5 Stop metodologico

Se due tentativi consecutivi orientati allo stesso confine device-side non producono nuova evidenza o un avanzamento sostanziale, l'AI PM deve fermare la ripetizione e riesaminare il metodo prima di proporre un terzo tentativo equivalente.

Questa regola non vieta step deliberatamente non hardware, come licensing, provenance o repository hygiene, purché siano dichiarati per ciò che sono e non usati per fingere avanzamento device-side.

---

## 16. [AGENTS.md](http://AGENTS.md) e prompt Codex

### 16.1 [AGENTS.md](http://AGENTS.md) come costituzione operativa persistente

La root deve contenere `AGENTS.md` con un riepilogo breve e stabile delle regole permanenti necessarie a Codex. `AGENTS.md` non deve diventare copia integrale delle presenti linee guida né del manuale.

Deve contenere almeno:

- root/manuale canonici;
- invarianti factory-preserving e compatibilità Windows;
- divieti hardware permanenti salvo autorizzazione;
- disciplina Git e scope;
- ciclo Design → Implementazione → Esecuzione;
- definizione di avanzamento reale;
- riesame metodologico pre-live;
- aggiornamento organico del manuale;
- bundle step-local;
- closure minima;
- distinzione safety telemetry / project reporting;
- licensing boundary e regole minime di provenance post-D247;
- repository hygiene minima post-D248.

`AGENTS.md` è un'istruzione operativa derivata, non una fonte normativa alternativa e non può contraddire il PDF canonico.

### 16.2 Prompt Dxxx: solo delta dello step

Il prompt specifico non deve ricopiare inutilmente regole permanenti già in `AGENTS.md` e nelle linee guida. Deve contenere:

- reasoning **MEDIUM** o **HIGH**;
- contesto tecnico strettamente necessario;
- obiettivo specifico;
- scope e file particolari;
- criteri di accettazione specifici;
- eventuali eccezioni esplicitamente autorizzate.

La prevenzione dei conflitti avviene riducendo la duplicazione, non dichiarando artificialmente una fonte "insuperabile".

---

## 17. Riesame metodologico pre-live

Prima di preparare o autorizzare una nuova run live dopo un fallimento precedente, l'AI esecutrice deve produrre un blocco conciso che risponda a tre domande:

1. **Cosa cambia realmente nel metodo rispetto all'ultimo tentativo?**
2. **Quale nuova ipotesi tecnica viene testata?**
3. **Se fallisce di nuovo nello stesso punto, quale azione diversa verrà intrapresa?**

Il riesame deve distinguere una variazione sostanziale da modifiche cosmetiche a pacing, logging, packaging, hash, preflight o altre cautele host-side.

Se non esiste una risposta sostanziale alle prime due domande, non va creato un nuovo step live solo per ripetere lo stesso esperimento con nuova cerimonia.

Non creare per default un secondo diario metodologico: la conclusione rilevante confluisce nel manuale canonico.

---

## 18. Architettura software e licensing boundary post-D247

La decisione D247 introduce una separazione intenzionale:

```
core/              GPL-2.0-or-later
  transport
  protocol
  tls
  fdt
  capture
  image
      |
      | licensing boundary
      v
libfprint-driver/  LGPL-2.1-or-later

tools/             GPL-2.0-or-later
```

Il materiale originale già pubblicato fino a D246 sotto BSD-2-Clause conserva quella concessione: non viene relicenziato retroattivamente. Codice di terzi mantiene i propri termini. Firmware/DLL OEM, capture, secret, materiale biometrico, factory data e asset non redistribuibili non ricevono alcuna blanket open-source license.

L'architettura post-D247 è stata adottata **precisamente per consentire il riuso diretto, l'adattamento e l'integrazione nel dominio GPL del codice esterno compatibile GPL**, preservando licenza, attribution e provenance. Il licensing boundary non vieta il riuso: impedisce che espressione GPL-only entri involontariamente nel driver upstream-facing LGPL.

Codice con una licenza LGPL compatibile può essere valutato per `libfprint-driver/` dopo audit per-file dei diritti, degli header SPDX, dei contributi e delle eventuali origini terze. Espressione GPL-only può entrare nel driver LGPL solo in presenza di dual licensing o licenza alternativa compatibile concessa da tutti i titolari pertinenti; in assenza, il driver deve essere implementato indipendentemente da specifiche, fatti di protocollo, test ed evidenza.

---

## 19. Rockytkg: fonte implementativa, non autorità probatoria

Repository di riferimento:

[Rockytkg/goodix-linux-27c6-5125](https://github.com/Rockytkg/goodix-linux-27c6-5125)

Conversazione tecnica principale:

[Issue #1 — goodix-linux-27c6-5125](https://github.com/Rockytkg/goodix-linux-27c6-5125/issues/1)

Codice Rockytkg verificato come compatibile GPL può essere letto, copiato, adattato e incorporato nel dominio GPL `core/`/`tools/`, con licenza, attribution e provenance. Eventuale codice specificamente disponibile sotto licenza LGPL compatibile può essere valutato per il dominio LGPL dopo audit per-file.

Questo permesso non promuove Rockytkg a prova primaria per APP12509 e non dimostra da solo safety, assenza di persistenza, compatibilità con PSK/factory state o correttezza sul target locale. Ogni comportamento sensor-reaching richiede validazione differenziale locale e, quando necessario, autorizzazione live separata.

---

## 20. Provenance permanente

Ogni import o adattamento di codice esterno registra almeno:

- repository e commit/ref sorgente;
- path sorgente;
- licenza/SPDX originale;
- copyright holder noto;
- eventuali componenti o contributi di terzi;
- data/step locale;
- path di destinazione;
- natura delle modifiche.

Preservare gli header applicabili e non assumere che la licenza repository-level copra automaticamente ogni file o dipendenza.

Il ledger operativo è `docs/LICENSING_AND_PROVENANCE.md`.

---

## 21. Pubblicazione e confine privato/pubblico

Il repository privato è il workspace canonico di sviluppo.

Il repository pubblico resta una superficie congelata finché uno step separato non esegue sanitizzazione e audit di **contenuto e history**.

L'uguaglianza del working tree non dimostra che la storia privata sia pubblicabile. Quando necessario usare clean export, nuova storia o filtri espliciti, senza sincronizzazione automatica.

Nessuna operazione sul repository pubblico è implicita nelle attività sul privato.

---

## 22. Closure e safety telemetry

La sintesi finale di ogni step usa, salvo necessità concreta, sei campi:

1. `OUTCOME` — `READY` | `BLOCKED` + classificazione tecnica breve;
2. `ADVANCEMENT` — esecuzione reale, nuova evidenza, avanzamento architetturale/non hardware oppure `NONE`, senza fingere device progress;
3. `EXECUTABLE_CLOSURE` — `PASS` | `FAIL` | `NOT_APPLICABLE`;
4. `RESIDUAL_BLOCKER_OR_RISK` — descrizione sintetica;
5. `CANONICAL_DOCUMENTATION` — manuale aggiornato sì/no + sezioni toccate;
6. `BUNDLE` — path + SHA-256 del bundle step-local.

Campi aggiuntivi sono ammessi quando rappresentano informazione tecnica non derivabile e realmente utile.

La riduzione della closure non riduce la safety telemetry. I report macchina possono e devono conservare, quando pertinenti:

- `usb_open_count`;
- `command_count`;
- `tls_count`;
- `retry_count`;
- D4/application-data reachability;
- claim/release;
- cleanup/reseal;
- device state;
- ACK/response osservati;
- persistent-write-family count.

Questi dati non devono essere duplicati in molte fonti con nomi differenti quando una singola fonte macchina è sufficiente.

---

## 23. Criterio generale di qualità

La qualità non si misura in:

- numero di file prodotti;
- numero di test offline passati;
- numero di report o bundle;
- numero di step Dxxx.

La qualità si misura in:

- riduzione di un'incertezza reale;
- repository più comprensibile;
- progetto più riproducibile;
- assenza di rischi nascosti;
- documentazione chiara di ciò che è noto e non noto;
- avanzamento concreto verso lo stack Linux finale;
- quando lo step è device-oriented, avanzamento o apprendimento reale al confine device-side.

---

## 24. Fonte canonica immutabile delle linee guida

Questa pagina Notion è la **fonte di authoring** delle linee guida. Dopo approvazione dell'Utente, la versione viene esportata nella root del repository privato come **unica fonte normativa canonica e immutabile delle linee guida per quella versione**.

Regole:

- l'AI non modifica direttamente il MD canonico;
- una modifica di policy richiede decisione esplicita dell'Utente, aggiornamento della pagina Notion, incremento di versione e nuovo export MD;
- `AGENTS.md` resta una sintesi operativa derivata e deve essere mantenuto coerente, ma non sostituisce né supera il MD;
- il manuale tecnico resta separatamente la fonte narrativa canonica dello **stato tecnico**, non delle regole permanenti di governance.

---

## 25. Principio sintetico della v2.3

**sicurezza hardware forte**

- 

**evidence-first e executable closure quando applicabile**

- 

**anti-frammentazione e riesame metodologico**

- 

**licensing/provenance espliciti**

- 

**repository hygiene senza rompere riproducibilità**

- 

**una sola fonte normativa immutabile + un solo manuale tecnico canonico**

=

**meno cerimonia senza perdere ingegneria, memoria o controllo**