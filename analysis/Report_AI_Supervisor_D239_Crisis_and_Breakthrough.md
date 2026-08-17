# Report AI Supervisor — Crisi Metodologica D234-D239 e Breakthrough su Goodix 27c6:5125

**Data:** 16 agosto 2026
**Autore:** AI Supervisor (Qwen) — ruolo di Red Teaming e filtro tecnico
**Destinatario principale:** AI Project Manager
**Destinatario operativo:** Utente (Guido)
**Repository canonico:** /home/guido/Repository/goodix-27c6-5125
**Stato al termine della sessione:** avanzamento storico su dispositivo reale

---

## Executive Summary

Questa sessione di supervisione tecnica è stata convocata dall'utente dopo il post-mortem D234-D239, che documentava sei passaggi formali con avanzamento reale quasi nullo sul sensore Goodix 27c6:5125. Il progetto era fermo al confine E4 → A2 #1 da tre step consecutivi (D236, D237, D238, D239), nonostante 74 test offline PASS e bundle formalmente completi.

### Risultato della sessione:

1. **Identificazione della vera causa radice del blocco di D239:** una directory host-side mancante (/var/lib/goodix-5125-poc/d238-results), NON un marker storico residuo come ipotizzato dal prompt D240.
2. **Fix applicato con 3 comandi manuali** (mkdir + chmod 0700 + chown), senza generazione di un nuovo bundle.
3. **Primo tentativo live che supera integralmente il confine storico:** 12 comandi eseguiti sul dispositivo reale, fino alla fase D1, con risposta TLS ricevuta (52 bytes, wrapper B0).
4. **Il progetto è passato da E4 → A2 #1 a E4 → A2 → 82 → A6 → A2 → 70 → 80x4 → 90 → D1 → [TLS response]** in una singola run.
5. **Revisione profonda delle Linee Guida per AI PM** per prevenire la ricorrenza del pattern disfunzionale.
6. **Dichiarazione di obsolescenza del prompt D240** nella sua forma attuale.

---

## 1. Contesto della convocazione

### 1.1 Il post-mortem D234-D239

Il report Report_post_mortem_Goodix_D234_D239.md documentava:

- 6 step formali prodotti (D234, D235, D236, D237, D238, D239)
- Solo 1 step con nuova evidenza device-side significativa (D236)
- Massimo confine reale raggiunto: E4 → A2 #1
- Milestone attesi mai raggiunti: 0x82, A6, A2 #2, 0x70, 0x80x4, 0x90, D1, TLS
- Cause dominanti: host-side e metodologiche, NON proprietà del sensore

### 1.2 La richiesta dell'utente

L'utente ha segnalato deragliamento metodologico: "Doveva essere una prova live. Si è trasformato in un incubo da 6 bundle... Avanti così non si può andare."

La richiesta esplicita:
- Intervenire come AI Supervisor con ruolo di Red Teaming
- Garantire solidità, sicurezza e coerenza tecnica del progetto
- Agire come filtro sulle proposte dell'AI PM

---

## 2. Diagnosi della crisi metodologica

### 2.1 Il pattern disfunzionale identificato

Il post-mortem ha evidenziato che il collo di bottiglia non era il sensore Goodix (che ha risposto coerentemente nelle poche run che lo hanno toccato), ma il "tappeto di casa nostra":

| Categoria di problemi | Frequenza | Impatto |
|----------------------|-----------|---------|
| Prerequisiti software mancanti scoperti troppo tardi | 6/6 step | Blocco sistematico |
| Test offline ≠ percorso operatore reale | 4/6 step | Falsi "READY" |
| Confine sudo/root trattato tardi | 3/6 step | Blocchi procedurali |
| Policy ACK modellata troppo strettamente | 2/6 step | Fix opcode-per-opcode |
| Observability insufficiente | 3/6 step | Nuovi step di diagnosi |
| Lifecycle marker non modellato come stato storico | 2/6 step | Blocchi ingiustificati |
| Bundle come proxy involontario dell'avanzamento | 6/6 step | Illusione di progresso |

### 2.2 Il paradosso della "governance contro noi stessi"

L'osservazione chiave: "Siamo caduti nella trappola dell'ingegneria difensiva contro noi stessi: abbiamo costruito così tanti strati di sicurezza, wrapper, preflight, source-sealing e marker single-use che il codice non riesce più a raggiungere il dispositivo."

Il progetto era tecnicamente pronto ma operativamente paralizzato da layer di protezione host-side che proteggevano un dispositivo già al sicuro (invarianti factory-preserving attive).

---

## 3. Errore diagnostico iniziale dell'AI Supervisor

Per trasparenza intellettuale, devo documentare un errore commesso in questa sessione.

Inizialmente ho diagnosticato che "il repository non esiste" basandomi sull'output del mio ambiente code_interpreter isolato.

**Verifica successiva** (eseguita dall'utente con ls -la reale) ha confermato che il repository esiste ed è integro, con tutti i file sorgente presenti.

**Lezione appresa:** ho violato il principio "Evidenza prima delle conclusioni" delle nostre linee guida. Il mio ambiente sandbox isolato non aveva accesso al filesystem reale dell'utente.

**Correzione applicata:** diagnosi affidata ai comandi eseguiti direttamente dall'utente sul sistema reale.

---

## 4. Revisione delle Linee Guida per AI PM

### 4.1 Perché era necessaria la revisione

Le Linee Guida originali (versione 1.0) erano ben scritte, ben intenzionate, ma profondamente disfunzionali nell'applicazione pratica. Il documento Notion originale:

https://app.notion.com/p/Linee_guida_di_progetto_Goodix_27c6-5125_per_AI-3b3ad4a33b8380ca9825f23319d9767b

conteneva principi corretti ma era stato interpretato operativamente in modo da produrre paralisi:

| Principio originale | Interpretazione disfunzionale |
|--------------------|--------------------------------|
| "Conservatività" | "Non fare mai nulla senza 10 layer di preflight" |
| "Fail-closed" | "Inventare fallimenti di governance anche quando il codice è corretto" |
| "Validazione umana finale" | "Produrre bundle e report senza mai verificare l'esecuzione reale" |
| "Nessuna conoscenza confinata nella chat" | "Documentare tutto ma non testare il launcher" |

### 4.2 Cosa è cambiato nella versione 2.0

Le nuove linee guida sono state pubblicate su Notion qui:

https://app.notion.com/p/Linee-Guida-di-Progetto-Goodix-27c6-5125-per-AI-Revisione-Post-Mortem-D239-3b3ad4a33b8380ca9825f23319d9767b

### 4.3 Principi fondamentali gerarchizzati

In caso di conflitto tra principi, l'ordine di priorità è vincolante:

1. **Factory-preserving** (massima priorità) — Nessuna operazione deve modificare firmware, PSK, OTP, factory data. Su questo principio non si transige.
2. **Eseguibilità reale > Correttezza teorica** — Il codice deve essere eseguibile nell'ambiente reale dell'operatore, con lo stesso comando, cwd, PYTHONPATH e privilegi.
3. **Avanzamento di confine > Produzione di artefatti** — Un bundle/report/review hanno valore solo se spostano il confine reale del progetto.
4. **Conservatività operativa (non cerimoniale)** — La conservatività si misura nel rollback, non nella paralisi.
5. **Fail-closed intelligente** — Non inventare fallimenti di governance host-side quando il codice è tecnicamente corretto.
6. **Evidence-first** — Distinguere sempre osservato / verificato / inferito / ipotizzato / non noto.
7. **Nessuna conoscenza confinata nella chat** — Nel manuale tecnico o artefatti canonici.
8. **Validazione umana finale** — Decisione finale all'utente.

### 4.4 Il nuovo Executable Closure Gate (vincolante)

Nuova sezione 6.6 che sostituisce ogni precedente checklist di readiness. Prima di dichiarare qualsiasi step "ready", l'AI esecutrice deve:

1. Eseguire il launcher esattamente come lo eseguirebbe l'operatore umano (stesso comando, cwd, PYTHONPATH, privilegi)
2. Confrontare l'ambiente di test con l'ambiente di lancio reale
3. Se il launcher fallisce anche solo per ModuleNotFoundError, PermissionError o marker assente, lo step non è ready, indipendentemente dai test offline
4. Il fallimento del launcher è prioritario rispetto ai test offline

Questo gate è stato la vera innovazione: un bundle perfetto con launcher non eseguibile è bundle fallito.

### 4.5 Gerarchia di sicurezza (nuova)

Nuova sezione 10.3 che distingue due domini:

| Dominio | Priorità | Tipo di misure |
|---------|----------|----------------|
| Sicurezza dispositivo (hardware) | Massima | Factory-preserving, no-flash, no-OTP |
| Sicurezza esecuzione (host) | Secondaria | Preflight, marker, sealing, dry-run |

Regola operativa: le misure host-side non devono mai diventare ostacolo insuperabile quando il dispositivo è già al sicuro. Se un meccanismo host-side blocca ripetutamente senza proteggere l'hardware, va semplificato, archiviato manualmente o rimosso.

### 4.6 Regole anti-frammentazione (nuove)

Per evitare il pattern D234-D239:

1. **Fix di classe, non di opcode** — Le correzioni devono coprire l'intera classe di problemi
2. **Audit orizzontale prima del live** — Tutte le fasi del protocollo atteso devono avere policy completa
3. **Chiusura dei prerequisiti nello stesso step** — No D+1 per difetti locali
4. **Avanzamento roadmap ≠ numero D incrementato** — Avanzamento = nuova evidenza tecnica
5. **Limite di 2 step consecutivi senza nuovo confine** — Riesaminare il metodo, non produrre un terzo step

---

## 5. Il prompt D240 e la sua obsolescenza

### 5.1 Il prompt D240 prodotto da AI PM

Il prompt D240 era strutturato attorno all'ipotesi primaria: "Esiste una forte ipotesi causale già supportata dalla storia operativa: il failure reale D239 è failures == [single_use_marker]".

D240 proponeva:
- 8 artefatti obbligatori
- Audit del lifecycle dei marker
- Separazione namespace marker
- Migrazione/archiviazione marker con fsync
- 10 test di regressione per marker storici
- Bundle ZIP con SHA256

### 5.2 Perché D240 è definitivamente obsoleto

L'AI Supervisor ha richiesto all'utente di leggere il report reale del preflight D239 (analysis/D236/D236_preflight_report.json). Il report diceva:

    {
        "failures": ["durable_report_path"],
        "single_use_marker_absent": true,
        "durable_report_path_ready": false
    }

La diagnosi di D240 era falsa. Il failure non era single_use_marker (che era correttamente assente), ma durable_report_path.

Questo è l'esempio perfetto del pattern disfunzionale del post-mortem: costruire un intero bundle attorno a un'ipotesi quando bastava leggere il report già prodotto per scoprire la causa reale.

### 5.3 Cosa si salva di D240

- Sezione 1 (leggere il report reale) — già fatto, ed è ciò che ha risolto il mistero
- Sezione 5.1 (osservabilità del wrapper) — resta un miglioramento valido: il wrapper deve esporre la sintesi redatta del failure invece del generico "root preflight failed"

Tutto il resto va cancellato.

---

## 6. Fix applicato: mkdir d238-results

### 6.1 Causa radice identificata

Dal report reale, il path del durable report era:

    "runtime_paths": {
        "final_report": "/var/lib/goodix-5125-poc/d238-results/d238-live-result.json",
        "report_directory": "/var/lib/goodix-5125-poc/d238-results"
    }

La directory /var/lib/goodix-5125-poc/d238-results/ non esisteva. Nel listing di /var/lib/goodix-5125-poc/ c'era solo d236-results.

### 6.2 Semantica esatta di report_path_ready

Dal backend (src/goodix5125_d233_backend.py, righe 823-837):

    def report_path_ready(self, path: Path) -> bool:
        if not path.is_absolute() or os.path.lexists(path):
            return False
        parent = path.parent
        try:
            status = os.lstat(parent)
        except OSError:
            return False
        return (
            stat.S_ISDIR(status.st_mode)          # deve essere directory
            and not stat.S_ISLNK(status.st_mode)  # NON symlink
            and status.st_uid == 0                # owner = root
            and stat.S_IMODE(status.st_mode) == 0o700  # permessi ESATTAMENTE 0700
            and os.access(parent, os.W_OK)        # scrivibile
        )

### 6.3 Fix manuale applicato (3 comandi)

    sudo mkdir -p /var/lib/goodix-5125-poc/d238-results
    sudo chmod 0700 /var/lib/goodix-5125-poc/d238-results
    sudo chown root:root /var/lib/goodix-5125-poc/d238-results

### 6.4 Verifica post-fix

    status = pass
    failures = []
    durable_report_path_ready = True
    single_use_marker_absent = True
    no_libusb_init = True
    usb_open_count = 0
    exit_code = 0

Nessun nuovo bundle generato. 3 comandi hanno risolto il problema.

---

## 7. Tentativo live: progresso storico

### 7.1 Esecuzione del wrapper

    sudo ./operator_kit/d239-live-pre-d1-tls-once.sh --i-authorize-one-d239-live-attempt

Output wrapper:

    patching file src/goodix5125_d233_backend.py
    patching file src/goodix5125_d235_entrypoint.py
    D239 operator kit: one-shot attempt stopped with exit 1; source resealed; no retry authorized

### 7.2 Tutti i gate superati

Per la prima volta in sei step:

| Gate | Stato |
|------|-------|
| Verifica SHA256 sorgenti sealed | PASS |
| Verifica dry-run pre-USB | PASS |
| Verifica EUID root + SUDO_UID | PASS |
| Root preflight | PASS |
| Unseal sorgenti | APPLICATO |
| Esecuzione entrypoint live | INVOCATO |
| Reseal sorgenti | COMPLETATO |

### 7.3 Sequenza completa eseguita sul dispositivo

Il report JSON mostra command_count: 12 e tutta la sequenza pre-D1 eseguita:

| # | Fase | Request | ACK | Response | Stato |
|---|------|---------|-----|----------|-------|
| 1 | E4 | 0xe4 | B0/E4/07 | 41 bytes | OK |
| 2 | A2_1 | 0xa2 | B0/A2/07 | 3 bytes | OK |
| 3 | CHIP_82 | 0x82 | B0/82/07 | 4 bytes | OK |
| 4 | OTP_A6 | 0xa6 | B0/A6/07 | 64 bytes (frammentato) | OK |
| 5 | A2_2 | 0xa2 | B0/A2/07 | 3 bytes | OK |
| 6 | MODE_70 | 0x70 | B0/70/07 | ack_only | OK |
| 7 | DAC_220 | 0x80 | B0/80/07 | ack_only | OK |
| 8 | DAC_236 | 0x80 | B0/80/07 | ack_only | OK |
| 9 | DAC_238 | 0x80 | B0/80/07 | ack_only | OK |
| 10 | DAC_23A | 0x80 | B0/80/07 | ack_only | OK |
| 11 | CONFIG_90 | 0x90 | B0/90/07 | 2 bytes | OK |
| 12 | D1 | 0xd1 | B0/TLS | 52 bytes | RICEVUTO |

### 7.4 Confronto quantitativo

| Metrica | D236 (prima) | D239 (adesso) |
|---------|--------------|---------------|
| Massimo comando raggiunto | A2 #1 | D1 (risposta ricevuta) |
| Comandi eseguiti | 2 | 12 |
| Fasi completate | E4, A2 | E4, A2, 82, A6, A2, 70, 80x4, 90, D1 |
| Risposta TLS ricevuta | No | Sì (52 bytes) |
| PSK/validator E4 | MATCH | MATCH (confermato) |
| persistent_write_family_count | 0 | 0 |
| d4_count | 0 | 0 |
| application_data_count | 0 | 0 |
| retry_count | 0 | 0 |
| secret_zeroized | true | true |
| source_seal_state | sealed | sealed |

Tutte le invarianti factory-preserving sono state rispettate. Il dispositivo non ha subito alcuna scrittura persistente.

### 7.5 Il punto di abort: unexpected_data su D1

L'ultima osservazione è la chiave:

    {
        "phase": "D1",
        "request_control": "0xd1",
        "first_in_wrapper": "B0",
        "ordering_classification": "direct_b0_tls",
        "ack_echo": "none",
        "ack_status": "none",
        "response_body_length": 52,
        "response_control": "B0/TLS"
    }

Cosa significa: il dispositivo ha risposto a D1 direttamente con un frame TLS (wrapper B0, non un ACK A0). Questo è esattamente il comportamento atteso per l'inizio dell'handshake TLS: il dispositivo invia il suo primo messaggio TLS (probabilmente ServerHello o equivalente) come risposta diretta a D1.

Perché il codice ha abortito: il campo abort_class: "unexpected_data" indica che la policy del codice non ha riconosciuto questo frame come l'inizio del TLS handshake. Si aspettava probabilmente un ACK A0/B0/D1/xx seguito da un response, e invece ha ricevuto direttamente un frame TLS B0.

La prova definitiva: same_validated_psk_used_by_tls: false. Il codice ha una flag esplicita per tracciare se la PSK validata in E4 viene usata nel TLS. È false perché il TLS non è mai partito.

---

## 8. Next steps consigliati

### 8.1 Fix di classe D1/TLS (non nuovo bundle)

Il problema è esattamente il tipo di "fix di classe" prescritto dal post-mortem: "Un failure di classe deve produrre una correzione di classe, non una patch del solo opcode appena fallito."

Il frame D1 ha struttura:
- Wrapper: B0 (TLS wrapper, non A0 command wrapper)
- Nessun ACK separato (risposta diretta TLS)
- Body: 52 bytes (dati TLS)

### 8.2 Cosa deve fare il codice

1. Riconoscere che la risposta a D1 è un frame TLS diretto (direct_b0_tls)
2. Non cercare un ACK A0/B0/D1/xx separato
3. Passare il frame da 52 bytes al B0TlsBridge per iniziare l'handshake TLS
4. Usare la PSK validata in E4 per il TLS handshake (deve diventare same_validated_psk_used_by_tls: true)

### 8.3 Procedura consigliata

1. Analizzare il codice che gestisce la risposta D1 nel backend/entrypoint
2. Identificare perché il frame B0/TLS da 52 bytes viene classificato come unexpected_data
3. Correggere la response policy della fase D1 per riconoscere il frame TLS diretto
4. Aggiungere test offline con un mock che risponde a D1 con un frame B0/TLS da 52 bytes
5. Verificare che same_validated_psk_used_by_tls diventi true nel test
6. Solo allora preparare un nuovo tentativo live

### 8.4 Comandi di indagine iniziali

    grep -n -A10 -B5 "0xd1\|D1\|direct_b0_tls\|unexpected_data" src/goodix5125_d233_backend.py
    grep -n -A10 -B5 "0xd1\|D1\|direct_b0_tls\|unexpected_data" src/goodix5125_d235_entrypoint.py
    grep -n -A10 -B5 "B0TlsBridge\|TlsBridge\|tls" src/goodix5125_d233_backend.py

---

## 9. Stato attuale e vincoli operativi

### 9.1 Stato dei marker

- /var/lib/goodix-5125-poc/d238-operator-invocation.marker: CREATO e CONSUMATO dal wrapper (contenuto: "D239 human-authorized single invocation")
- /var/lib/goodix-5125-poc/d236-live-single-use.marker: Storico, NON rilevante (non viene guardato dal preflight)
- /var/lib/goodix-5125-poc/d238-results/: CREATO manualmente con permessi 0700 root-only

### 9.2 Stato dei sorgenti

- src/goodix5125_d233_backend.py SHA256: 7727128ee27337b70ba48eac31b8640c888b76560387363e4eff0c167d993f5b (sealed)
- src/goodix5125_d235_entrypoint.py SHA256: 38e857a14bd416808b9ae2df7c4101809879e4732b6e001ce29d11bd731dd555 (sealed)

### 9.3 Nuove autorizzazioni necessarie

- Marker consumato: serve nuova autorizzazione umana per nuovo tentativo live
- Nuovo tentativo: richiede fix della response policy D1 prima di rilanciare

---

## 10. Raccomandazioni finali per AI PM

### 10.1 Cosa ci aspettiamo dalla coppia AI PM / AI Esecutrice da ora in poi

1. Applicazione integrale delle Linee Guida versione 2.0 pubblicate su Notion:
   https://app.notion.com/p/Linee-Guida-di-Progetto-Goodix-27c6-5125-per-AI-Revisione-Post-Mortem-D239-3b3ad4a33b8380ca9825f23319d9767b

2. Executable Closure Gate sempre verificato prima di dichiarare qualsiasi step "ready"

3. Nessun nuovo bundle costruito attorno a ipotesi non verificate — leggere sempre il report reale prima di definire lo scope

4. Fix di classe invece di fix di opcode — quando un failure appartiene a una classe, la correzione deve coprire l'intera classe

5. Observability obbligatoria — i wrapper devono esporre la classificazione redatta del failure, non messaggi generici

6. Gerarchia di sicurezza rispettata — la sicurezza dispositivo (factory-preserving) è prioritaria rispetto alla sicurezza esecuzione (host)

7. Anti-frammentazione — chiudere i prerequisiti nello stesso step, non produrre step incrementali per difetti locali

### 10.2 Cosa NON ci aspettiamo

- Generazione di D240 nella sua forma attuale (obsoleto)
- Accumulo di artefatti senza avanzamento reale
- Bundle costruiti attorno a ipotesi non verificate
- Run live senza Executable Closure Gate verificato

---

## 11. Invito esplicito all'AI PM

AI PM, sei invitata a:

1. Leggere integralmente le nuove Linee Guida versione 2.0 qui:
   https://app.notion.com/p/Linee-Guida-di-Progetto-Goodix-27c6-5125-per-AI-Revisione-Post-Mortem-D239-3b3ad4a33b8380ca9825f23319d9767b

2. Rileggere questo report come documento di handoff dalla sessione di crisi

3. Non generare D240 nella sua forma attuale

4. Preparare un nuovo task che implementi il fix di classe D1/TLS secondo la procedura della sezione 8.3 di questo report

5. Applicare l'Executable Closure Gate al nuovo task prima di dichiararlo ready

---

## 12. Conclusione

Questa sessione di supervisione ha dimostrato tre punti fondamentali:

1. Il progetto non era bloccato dal sensore Goodix. Era bloccato da una directory host-side mancante (/var/lib/goodix-5125-poc/d238-results/), risolvibile con 3 comandi manuali.

2. Il prompt D240 era obsoleto prima ancora di essere lanciato. Era costruito attorno a un'ipotesi smentita dal report reale del preflight.

3. Quando il codice raggiunge il dispositivo, funziona. Il tentativo live ha eseguito 12 comandi e ricevuto una risposta TLS dal sensore. Il progetto è avanzato in una singola run più di quanto avesse fatto in 6 step precedenti.

Il confine storico E4 → A2 #1 è stato superato. Ora si tratta di riconoscere il frame B0/TLS diretto nella fase D1 e completare il TLS handshake.

Il metodo è stato corretto. Il codice ha raggiunto il dispositivo. Il sensore risponde.

La strada è aperta. Procedere con il fix di classe D1/TLS.

---

**AI Supervisor (Qwen) — Red Team Lead**
**Sessione completata: 16 agosto 2026**
