# AGENTS.md — Goodix 27c6:5125

> Sintesi operativa derivata da `Linee Guida di Progetto Goodix 27c6 5125 per AI.md` v2.7.
> In caso di conflitto prevalgono le linee guida canoniche e l'eventuale decisione/Human Gate corrente dell'Utente.

## 1. Repository e fonti canoniche

Repository operativo canonico: la root reale del clone Git privato corrente,
individuata con `git rev-parse --show-toplevel`. Non assumere path della
workstation dell'Utente.

Fonti canoniche:

- governance: `Linee Guida di Progetto Goodix 27c6 5125 per AI.md`;
- sintesi operativa: questo `AGENTS.md`;
- stato tecnico narrativo: `Goodix 27c6 5125 manuale tecnico.md`;
- provenance/licensing: `docs/LICENSING_AND_PROVENANCE.md` e file dedicati;
- evidenze raw private autentiche: `<git-root>/captures/` quando presenti.

Prima di modificare codice, stato tecnico o documentazione:

1. identifica la root reale del repository;
2. leggi questo `AGENTS.md`;
3. leggi le linee guida canoniche;
4. leggi le sezioni pertinenti del manuale tecnico;
5. leggi il task/prompt corrente;
6. controlla branch, baseline e `git status --short`;
7. esamina solo gli artefatti storici realmente pertinenti;
8. verifica quali capability sono effettivamente concesse al task.

La conoscenza nuova non deve restare soltanto in chat, sessioni agente, report isolati o artefatti temporanei.

---

## 2. Obiettivo e invarianti factory-preserving

Target: stack Linux funzionante per Goodix USB `27c6:5125` sul PC target, preservando integralmente firmware, identità, secure state, factory state e compatibilità Windows.

Invariante assoluto:

```text
factory_firmware_and_persistent_state_must_remain_untouched
```

Sono permanentemente fuori scope della governance v2.7:

- flash / erase / ClearApp / IAP;
- provisioning o riprovisionamento del sensore;
- provisioning, sostituzione o randomizzazione della PSK factory;
- scrittura OTP, factory data o configurazione persistente;
- cambio persistente di modalità o VID:PID;
- procedure che rendano incerta la compatibilità Windows successiva;
- introduzione intenzionale di persistent-write family incompatibili con lo scope factory-preserving.

Questi invarianti non possono essere superati da un normale Human Gate. Una loro eventuale revisione richiederebbe una nuova decisione di governance/progetto.

---

## 3. Governance v2.7: standing delegation e Human Authority

L'Utente resta l'autorità umana finale, ma **non è il relay ordinario** tra AI PM e AI esecutrice.

Entro la standing delegation sono autonomamente consentiti, se host-only e dentro lo scope già approvato:

- pianificazione AI PM;
- generazione e dispatch dei task;
- implementazione e test offline/host-only;
- review AI PM;
- corrective e replan nello stesso scope;
- aggiornamento del manuale;
- gestione di task branch/worktree;
- commit e push fast-forward sui branch autorizzati;
- avanzamento fast-forward del branch di integrazione dopo `ACCEPT` AI PM;
- apertura/aggiornamento di PR private;
- prosecuzione allo step host-only successivo.

Policy O003 autorizzata:

- orchestrazione local-first (`PC_OFF => ORCHESTRATION_OFF`) come servizio `systemd --user`;
- issue/commento GitHub privato come control plane macchina del Human Gate, con identità numerica, gate, commit/ref e azione esatta bound e replay-safe;
- re-probe periodico quota/modello e ripresa autonoma soltanto dopo disponibilità della route esatta e riconciliazione;
- latch locale persistente di emergency-stop e maintenance lock formale;
- `main` branch Human, `development` branch persistente di integrazione autonoma accettata, `task/<TASK_ID>` branch effimero;
- `MAX_CONCURRENT_TASKS=1`, corrective sullo stesso branch, cleanup soltanto dopo FF verificato, preservazione su failure/ambiguità.

Richiedono Human Gate specifico, salvo futura delega esplicita:

- accesso/claim USB reale e qualunque comando sensor-reaching;
- esecuzione live sul Goodix;
- uso di protected material/secret reali oltre un preflight già espressamente delegato;
- `sudo`, root o privilegi equivalenti;
- nuova raccolta Windows VM/OEM sul sensore;
- installazione/attivazione runtime libfprint/fprintd/PAM;
- merge in `main`;
- pubblicazione;
- rebase, amend, force push, reset distruttivi o history rewrite;
- cambi materiali di scope, safety boundary, licensing boundary o architettura canonica.

AI PM, AI esecutrice e orchestratore non possono auto-approvare un Human Gate né ampliare la standing delegation.

---

## 4. Ruoli e loop orchestrato

### AI PM

- definisce criteri di accettazione, scope, rischi ed esclusioni;
- sceglie classe di modello/ragionamento adeguata e vieta downgrade silenziosi;
- prepara task piccoli ma non artificialmente frammentati;
- reviewa stato Git reale, diff, test, report, executable closure e manuale;
- emette una sola disposition primaria:

```text
ACCEPT
CORRECTIVE
REPLAN
HUMAN_GATE
PAUSE
DONE
```

- dopo `ACCEPT` può produrre e dispatchare autonomamente il task successivo entro la standing delegation;
- non possiede authority per live, scope expansion, merge `main` o history rewrite.

### AI esecutrice

- opera nel worktree/branch assegnato;
- legge prima le fonti canoniche;
- applica il cambiamento minimo necessario;
- esegue test pertinenti;
- aggiorna ricorsivamente e organicamente il manuale tecnico;
- produce un review set Git-native;
- non amplia autonomamente scope o capability;
- non tenta di aggirare capability assenti.

### Orchestratore deterministico

Non è una quarta AI e non prende decisioni tecniche. Deve:

- trasferire task PM → Executor e risultati Executor → PM;
- persistere state machine, identificatori, baseline e gate;
- applicare allow-list, capability e policy Git;
- creare/assegnare worktree e task branch;
- mantenere, quando previsto, un branch di integrazione separato da `main`;
- mantenere `development` come branch di integrazione autonomo persistente e un solo `task/<TASK_ID>` attivo;
- avanzare tale branch solo fast-forward dopo `ACCEPT` AI PM;
- rimuovere worktree/branch task solo dopo verifica esatta dell'integrazione, preservandoli su outcome fallito o ambiguo;
- arrestarsi su Human Gate, quota, modello indisponibile, errore infrastrutturale o stato ambiguo;
- non trasformare mai `HUMAN_GATE` in `ACCEPT`.

Loop ordinario:

```text
AI PM -> AI esecutrice -> AI PM -> [next task | corrective | replan | Human Gate | pause | done]
```

L'Utente non è un hop di trasporto.

---

## 5. Task/prompt specifici e modello

Il task Dxxx descrive il **delta dello step**, senza ricopiare questa costituzione operativa.

Deve contenere almeno:

- modello/classe di ragionamento scelta dall'AI PM;
- obiettivo specifico;
- scope e file rilevanti;
- criteri di accettazione;
- `GATE_CLASS` e capability necessarie;
- eventuali eccezioni già autorizzate.

Il task deve essere persistibile/versionabile come `.md` e, in modalità orchestrata, viene passato direttamente all'AI esecutrice senza copia/incolla dell'Utente.

Un task host-only entro standing delegation **non richiede approvazione manuale separata dell'Utente**.

Nessun fallback silenzioso verso un modello non autorizzato o verso API/pay-as-you-go a consumo. Se quota o modello richiesto non sono disponibili: `PAUSE`, persistenza dello stato e ripresa successiva.

---

## 6. Git e separazione delle capability

Principio del minimo privilegio:

- AI esecutrice: modifica/commit solo nel task branch assegnato;
- AI PM: preferibilmente review-only;
- orchestratore: `task/<TASK_ID>`/worktree effimero, push fast-forward, PR private e `development` come branch di integrazione autonomo persistente;
- Utente: Human Gate per `main`, history rewrite e pubblicazione.

Regole:

- non assumere stato sporco come baseline valida;
- non cancellare modifiche dell'Utente;
- niente merge in `main` senza Human Gate;
- niente rebase/amend/force push/history rewrite senza Human Gate;
- niente update di ref non fast-forward salvo Human Gate dedicato;
- massimo un task branch/worktree operativo; `CORRECTIVE` riusa lo stesso branch;
- l'integrazione `development@A -> accepted B` richiede SHA reviewato esatto, CAS/FF, rilettura local/remote e prova di reachability;
- cleanup automatico solo per l'esatto task corrente dopo integrazione verificata; ogni failure/ambiguità preserva le evidenze;
- mai cancellare `main`, `development` o branch ignoti; mai creare `development` da codice non accettato;
- niente hook Git o modifiche globali/utente senza autorizzazione specifica;
- niente file fuori scope o retro-modifica gratuita di artefatti storici.

### Baseline live

Ogni live deve essere legato a un commit SHA completo reviewato dall'AI PM e al relativo Human Gate dell'Utente.

Il live-critical set comprende normalmente:

- launcher live;
- backend USB reale;
- entrypoint reale;
- moduli sensor-reaching;
- guardrail single-shot, cleanup/reseal e autorizzazione.

Né AI PM, né executor, né orchestratore possono inventare o auto-approvare una baseline live.

---

## 7. Capability separation e live runner

L'ambiente ordinario dell'AI esecutrice deve essere **host-only** e, quando tecnicamente praticabile, non deve avere:

- accesso al Goodix in `/dev/bus/usb`;
- `sudo`/root;
- secret/protected material reali;
- capability per aggiornare `main`;
- capability di pubblicazione.

Il live deve passare attraverso un **live runner deterministico separato**, che può eseguire soltanto azione e baseline autorizzate dal Human Gate.

Ogni gate live deve essere:

- legato a `GATE_ID` univoco;
- legato a commit/ref e azione precisa;
- one-shot salvo diversa autorizzazione esplicita;
- verificabile rispetto all'identità dell'Utente;
- non riutilizzabile implicitamente per un tentativo successivo.

Guardrail hardware da preservare quando applicabili:

- autorizzazione esplicita;
- single-shot;
- zero retry implicito;
- fail-closed su comandi non compresi/persistenti;
- cleanup/release/reseal;
- verifica live-critical set.

---

## 8. Metodo di lavoro e anti-frammentazione

Principi:

1. **evidence-first**: distinguere osservato, verificato, inferito, ipotizzato e non noto;
2. **scope minimo**: niente refactoring globale o nuove dipendenze senza necessità concreta;
3. **Design → Implementazione → Esecuzione**: evitare catene design-only;
4. correggere classi di failure, non un opcode/sintomo alla volta quando il pattern è già riconoscibile;
5. prerequisiti locali emersi durante uno step vanno chiusi nello stesso Dxxx quando possibile;
6. la numerazione Dxxx non è avanzamento.

Avanzamento reale significa nuova esecuzione, nuova evidenza, nuovo confine tecnico/hardware oppure decisione architetturale/licensing/repository/orchestrazione che cambia realmente lo stato.

Se due tentativi consecutivi sullo stesso boundary device-side non producono nuova evidenza, l'AI PM deve cambiare metodo prima di un terzo tentativo equivalente.

---

## 9. Riesame metodologico pre-live

Prima di preparare o autorizzare una nuova run live dopo un fallimento, rispondere concisamente:

1. **Cosa cambia realmente nel metodo rispetto all'ultimo tentativo?**
2. **Quale nuova ipotesi tecnica viene testata?**
3. **Se fallisce di nuovo nello stesso punto, quale azione diversa verrà intrapresa?**

Pacing, logging, packaging, hash, preflight o altre cautele host-side non costituiscono da soli una nuova ipotesi tecnica.

La conclusione metodologica rilevante va integrata nel manuale tecnico; non creare per default un secondo diario canonico.

---

## 10. Manuale tecnico

Ogni step che cambia conoscenza, decisioni o stato tecnico deve aggiornare ricorsivamente:

```text
Goodix 27c6 5125 manuale tecnico.md
```

Il manuale non è un log append-only.

Quando una decisione cambia stato:

- aggiorna le sezioni alte/canoniche interessate;
- aggiungi una sezione Dxxx solo se utile a provenance/ricostruzione;
- correggi formulazioni non più correnti;
- mantieni indice, tabelle, spiegazioni e stato tecnico coerenti;
- non lasciare conoscenza nuova soltanto nel report o nella sessione agente;
- non duplicare o degradare contenuto ancora valido.

---

## 11. Licenze, provenance e confine privato/pubblico

- `core/`, `tools/` = `GPL-2.0-or-later`;
- `libfprint-driver/` = `LGPL-2.1-or-later`;
- codice Rockytkg GPL può essere riusato nel dominio GPL con provenance completa;
- Rockytkg resta fonte implementativa, non prova target-specific APP12509;
- espressione GPL-only non entra nel dominio LGPL senza licenza compatibile;
- leggere `<git-root>/Rockytkg/PROVENANCE.md` prima di audit/adattamento/riuso;
- ledger operativo: `docs/LICENSING_AND_PROVENANCE.md`;
- repository privato = workspace canonico;
- repository pubblico congelato fino a sanitizzazione e audit di contenuto + history;
- nessuna sincronizzazione automatica privato → pubblico.

---

## 12. Review set Git-native, telemetry ed Executable Closure

Output ordinario: **review set step-local Git-native**, non ZIP/Base64.

Superficie di audit:

- baseline Git;
- HEAD/commit o branch/PR;
- diff;
- artefatti Dxxx in `analysis/Dxxx/`;
- file di codice, test e documentazione realmente modificati.

Non aggiungere a review set/pubblicazione:

- secret/PSK/chiavi TLS;
- dati biometrici reali;
- firmware/DLL OEM o materiale proprietario non redistribuibile;
- cache/temporanei;
- copie inutili di artefatti storici.

Le evidenze raw private autentiche restano in `<git-root>/captures/` e possono essere referenziate senza duplicazione.

### Executable Closure

Un task non è `READY` solo perché i test unitari passano. Quando esiste un launcher operativo, verificare nello scope consentito:

- cwd reale;
- import/PYTHONPATH reale;
- path resolution;
- modalità di invocazione;
- dry-run/offline path;
- failure reporting.

Un launcher rotto prevale su una suite offline verde.

### Closure standard

```text
OUTCOME
ADVANCEMENT
EXECUTABLE_CLOSURE
RESIDUAL_BLOCKER_OR_RISK
CANONICAL_DOCUMENTATION
REVIEW_SET
```

Safety telemetry resta più ricca quando necessaria (`usb_open_count`, `command_count`, `tls_count`, `retry_count`, claim/release, cleanup/reseal, ACK/response, persistent-write-family count, device state), senza duplicazioni inutili.

---

## 13. Bootstrap orchestrazione: freeze del progresso Goodix

Con la v2.7 il progresso funzionale Goodix è intenzionalmente sospeso durante la costruzione dell'orchestrazione, salvo riapertura esplicita dell'Utente.

Prima dell'autopilot Goodix devono essere dimostrati almeno:

- loop PM → Executor → PM senza relay umano;
- gestione corretta di `ACCEPT`, `CORRECTIVE`, `REPLAN`, `HUMAN_GATE`, `PAUSE`, `DONE`;
- crash recovery e idempotenza;
- isolamento dell'executor da USB Goodix e `sudo`;
- impossibilità di merge/main e history rewrite senza gate;
- branch di integrazione autonomo solo fast-forward dopo `ACCEPT`;
- stop reale su Human Gate e ripresa solo dopo approvazione valida;
- pausa pulita su quota/modello senza fallback a pagamento;
- review reale di diff/test/manuale da parte dell'AI PM;
- assenza di secret in log/stato/notifiche;
- servizio local-first con single-instance, operator pause/resume/status/stop, maintenance ed emergency latch;
- Human Gate GitHub esatto e replay-safe, con stop reale del dispatch;
- re-probe quota/modello senza fallback a pagamento;
- lifecycle `development`/task e cleanup/recovery verificati;
- almeno un ciclo sintetico completo e un ciclo reale host-only a basso rischio.

Durante maintenance o con emergency latch attivo non sono consentiti dispatch, integrazione o cleanup. `resume` normale non cancella il latch. I log devono essere redatti; SQLite e backup XDG non contengono token, email, secret, protected material o chain-of-thought.

Solo dopo questa closure l'AI PM può dichiarare:

```text
ORCHESTRATION_READY_FOR_GOODIX=true
```

e proporre la riapertura del boundary tecnico.

---

## 14. Principio finale

```text
sicurezza hardware forte + capability separation
+
AI PM ed Executor collegati direttamente
+
standing delegation host-only
+
Human Gate stretti per live/main/scope materiale
+
manuale e stato persistente come memoria
+
review Git-native + executable closure
+
pausa fail-closed su quota/modello
=
più autonomia delle AI senza cedere safety o autorità umana
```
