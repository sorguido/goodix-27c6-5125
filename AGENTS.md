# AGENTS.md — Goodix 27c6:5125

## 1. Repository e fonti canoniche

Repository operativo canonico: la root reale del clone Git privato corrente,
individuata con `git rev-parse --show-toplevel`. Non assumere path della
workstation dell’Utente.

Manuale tecnico canonico: `Goodix 27c6 5125 manuale tecnico.md` nella root.

Prima di modificare codice, stato tecnico o documentazione:

1. identifica la root reale del repository;
2. leggi questo `AGENTS.md`;
3. leggi le linee guida `Linee Guida di Progetto Goodix 27c6 5125 per AI.md`;
4. leggi le sezioni pertinenti del manuale tecnico;
5. leggi il prompt specifico dello step;
6. controlla `git status --short` e branch corrente;
7. esamina solo gli artefatti storici realmente pertinenti.

Il manuale tecnico è la fonte narrativa canonica dello stato del progetto. La conoscenza nuova non deve restare soltanto in chat, report isolati o artefatti di review.

---

## 2. Obiettivo e invarianti hardware

Target: stack Linux funzionante per Goodix USB `27c6:5125` sul PC target, preservando integralmente il percorso Windows.

Invarianti non negoziabili:

```text
factory_firmware_and_persistent_state_must_remain_untouched
```

Quindi, salvo autorizzazione esplicita e specifica dell'Utente:

- no flash / IAP;
- no provisioning;
- no modifica o sostituzione PSK;
- no scrittura OTP;
- no modifica factory data;
- no scrittura di configurazione persistente;
- no cambio persistente di modalità/VID:PID;
- no comando wire non compreso con possibile effetto persistente;
- no accesso USB reale durante task offline;
- no `sudo` da parte dell'AI;
- nessuna regressione intenzionale della compatibilità Windows.

Se un task richiede una vera eccezione, deve essere esplicita, limitata e autorizzata dall'Utente.

---

## 3. Metodo di lavoro

Principi:

1. **evidence-first**: distinguere osservato, verificato, inferito, ipotizzato e ignoto;
2. **scope minimo**: niente refactoring globale o nuove dipendenze senza necessità concreta;
3. **Design → Implementazione → Esecuzione**: evitare catene di artefatti design-only;
4. una sola patch locale post-implementazione quando possibile;
5. la numerazione Dxxx non è avanzamento.

Avanzamento reale significa almeno uno tra:

```text
REAL_EXECUTION_COMPLETED
NEW_TECHNICAL_EVIDENCE_PRODUCED
NEW_PROTOCOL_OR_HARDWARE_BOUNDARY_REACHED
```

Correzioni locali che non cambiano il confine tecnico restano nello stesso Dxxx.

---

## 4. Licenze, provenance e pubblicazione

- nuovo core userspace e tool collegati: `core/`, `tools/` = `GPL-2.0-or-later`;
- driver/glue upstream: `libfprint-driver/` = `LGPL-2.1-or-later`;
- riuso diretto di codice Rockytkg GPL è autorizzato solo nel dominio GPL, con
  commit/path/licenza/copyright/destinazione/modifiche registrati;
- Rocky è fonte implementativa, non prova target-specific per APP12509; safety
  e comportamento sensor-reaching richiedono sempre evidenza locale;
- nessuna espressione GPL entra nel dominio LGPL senza dual/alternative license
  valida o implementazione indipendente;
- il repository privato è il workspace canonico; il pubblico resta congelato
  fino a un export separato, sanitizzato e con audit della history privata.

Dettagli operativi e ledger: `docs/LICENSING_AND_PROVENANCE.md`.

Snapshot Rockytkg operativo canonico: `<git-root>/Rockytkg/`. Prima di audit,
adattamento o riuso leggere `Rockytkg/PROVENANCE.md`. Il repository online
Rockytkg non è una dipendenza del workflow ordinario; la Issue #1 resta una
fonte esterna distinta e non è incorporata nello snapshot.

---

## 5. Riesame metodologico pre-live

Prima di preparare o autorizzare una nuova run live dopo un fallimento, pubblica un blocco breve con queste tre risposte:

1. **Cosa cambia realmente nel metodo rispetto all'ultimo tentativo?**
2. **Quale nuova ipotesi tecnica viene testata?**
3. **Se il tentativo fallisce di nuovo nello stesso punto, quale azione diversa verrà intrapresa?**

Pacing, logging, packaging, hash, preflight o altre cautele host-side non costituiscono da soli una nuova ipotesi tecnica.

Se non esiste una risposta sostanziale alle prime due domande, non creare un nuovo step live per ripetere lo stesso esperimento.

La conclusione metodologica rilevante va integrata nel manuale tecnico. Non creare per default un secondo diario canonico `method_log.md`.

---

## 6. Prompt specifici

Il prompt Dxxx deve descrivere il **delta dello step**, non ricopiare questa costituzione operativa.

Ogni prompt deve indicare:

- reasoning level: `MEDIUM` oppure `HIGH`;
- obiettivo specifico;
- scope/file specifici;
- criteri di accettazione specifici;
- eventuali eccezioni autorizzate.

Le istruzioni specifiche possono restringere lo scope. Non devono rilassare implicitamente i vincoli permanenti.

Se prompt e regole permanenti sembrano contraddirsi, segnala il conflitto invece di reinterpretarlo silenziosamente. Una deroga vale solo se è esplicita e autorizzata dall'Utente.

---

## 7. Git e integrità

Per default:

- lavora solo sul branch corrente;
- non fare merge, PR, rebase, cherry-pick o switch di branch;
- non fare commit o push salvo richiesta esplicita;
- non fare reset/stash distruttivi;
- non cancellare modifiche preesistenti dell'Utente;
- non retro-modificare artefatti storici per adattarli al presente;
- non modificare file fuori scope.

### Baseline live approvata

Per un percorso live, la baseline revisionata è identificata da un **commit SHA completo approvato esplicitamente dall'Utente/AI PM**.

Codex non deve inventare o auto-approvare tale SHA.

La verifica deve concentrarsi sul **live-critical set**, normalmente:

- launcher live corrente;
- backend USB reale;
- entrypoint reale;
- moduli che possono inviare comandi USB;
- guardrail software che implementano autorizzazione, single-shot, cleanup/reseal.

Modifiche a manuale, report, manifest o test offline non devono invalidare automaticamente la baseline live.

Evitare pin SHA-256 manuali generalizzati per artefatti non live-critical. Mantenerli solo quando proteggono un rischio concreto non coperto in modo equivalente dalla baseline Git.

---

## 8. Guardrail live da non semplificare

Quando applicabili, preservare:

- verifica del contesto operatore/privilegi coerente col launcher;
- autorizzazione esplicita della run;
- single-shot / un solo tentativo live per autorizzazione;
- fail-closed su comandi non compresi o potenzialmente persistenti;
- cleanup/release/reseal garantiti anche su uscita anomala;
- zero retry salvo task esplicitamente autorizzato;
- verifica del live-critical set contro baseline approvata.

Questi sono guardrail hardware. Non sostituirli con sola prosa.

---

## 9. Manuale tecnico

Ogni step che cambia conoscenza, decisioni o stato tecnico deve aggiornare ricorsivamente:

```text
Goodix 27c6 5125 manuale tecnico.md
```

Il manuale non è un log append-only.

Quando una decisione cambia stato:

- aggiorna le sezioni alte/canoniche interessate;
- aggiungi una sezione Dxxx solo se utile alla provenance;
- correggi o marca come superate le formulazioni non più correnti;
- mantieni indice, tabelle e stato tecnico coerenti;
- non duplicare inutilmente informazioni già canoniche.

---

## 10. Review set Git-native

Output finale standard di Codex: un **review set step-local Git-native**, non un archivio ZIP separato.

Il review set è l'insieme verificabile delle modifiche, evidenze e documentazione versionate nel repository e necessarie alla review dello step. La superficie di audit standard comprende:

- baseline Git rilevante;
- HEAD/commit finale, oppure branch/PR quando il commit finale non è ancora integrato;
- diff rispetto alla baseline;
- artefatti Dxxx in `analysis/Dxxx/`;
- file di codice, test e documentazione realmente modificati dallo step.

Ogni output Dxxx futuro vive in `analysis/Dxxx/`. La root non è una destinazione per output di step, salvo eccezione esplicita e documentata. Gli artefatti storici ancora in root sono relocati soltanto con un'operazione meccanica che ne preservi i blob e non rompa consumatori eseguibili o riproducibilità; ogni eccezione resta in sede ed è documentata.

Il review set deve essere auditabile tramite Git e riferimenti canonici, senza duplicare manuale, policy, history o file non modificati per renderlo autosufficiente.

Non aggiungere al review set o agli artefatti destinati alla pubblicazione:

- secret;
- PSK;
- chiavi TLS;
- dati biometrici reali;
- materiale proprietario non destinato alla distribuzione;
- cache o temporanei;
- artefatti storici non modificati.

Le evidenze raw private autentiche vivono canonicamente in `<git-root>/captures/` e possono essere versionate nel repository privato. Il review set può riferirle quando necessario, senza duplicarle in `analysis/Dxxx/`; futuri export pubblici devono escluderle. Non esiste sincronizzazione automatica dal privato al pubblico e la pubblicazione richiede uno step esplicito di sanitizzazione.

ZIP, `.zip.b64` e packaging equivalenti **non sono requisiti di closure né mezzi di trasporto standard**. Possono essere creati solo quando una piattaforma, un destinatario o un'attività di export li richiede esplicitamente. I bundle ZIP storici già versionati restano evidenza storica e non devono essere cancellati o rigenerati senza una ragione tecnica specifica.

Indicare baseline e commit/HEAD di riferimento quando rilevanti.

---

## 11. Safety telemetry e project reporting

Non confondere telemetria di sicurezza con sintesi di progetto.

I report macchina possono mantenere tutti i campi necessari, ad esempio:

```text
usb_open_count
command_count
tls_count
retry_count
claim/release
cleanup/reseal
ACK/response
persistent_write_family_count
device_state
```

Non duplicare però gli stessi dati in più JSON/manifest/report senza necessità.

La chiusura di progetto usa normalmente solo:

```text
OUTCOME
ADVANCEMENT
EXECUTABLE_CLOSURE
RESIDUAL_BLOCKER_OR_RISK
CANONICAL_DOCUMENTATION
REVIEW_SET
```

`REVIEW_SET` indica baseline + HEAD/commit (o branch/PR) e i path/file rilevanti che compongono il review set step-local.

Campi aggiuntivi solo se contengono informazione tecnica realmente utile e non derivabile.

---

## 12. Executable Closure

Un task non è `READY` solo perché i test unitari passano.

Quando esiste un launcher operativo, verificare nello scope consentito:

- cwd reale;
- import/PYTHONPATH reale;
- path resolution reale;
- modalità di invocazione reale;
- dry-run/offline path reale;
- failure reporting leggibile.

Non eseguire USB reale o hardware se il prompt non lo autorizza esplicitamente.

---

## 13. Principio finale

```text
sicurezza hardware forte
+
manuale canonico aggiornato
+
contesto persistente breve
+
prompt specifici corti
+
telemetria completa ma non duplicata
=
meno cerimonia, stessa o maggiore qualità ingegneristica
```
