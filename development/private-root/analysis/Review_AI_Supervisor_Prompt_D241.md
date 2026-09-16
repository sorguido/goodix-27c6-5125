# Review AI Supervisor — Prompt D241 (D1 direct-B0 TLS transition)

**Data:** 16 agosto 2026
**Autore:** AI Supervisor (Qwen) — Red Team Lead
**Oggetto review:** Prompt_Codex_D241_D1_direct_B0_TLS_transition.md
**Esito:** APPROVATO con 3 integrazioni vincolanti (R1-R3), 2 raccomandate (R4-R5), 1 nota informativa (R6)

---

## 1. Verdetto

Sì, mi piace. È il miglior prompt dell'intera campagna.

Per la prima volta l'AI PM ha prodotto un task che parte dall'evidenza reale invece che da un'ipotesi, che pone la domanda ingegneristica giusta, e che applica le Linee Guida v2.0 senza trasformarle in nuova cerimonia. È approvabile con le integrazioni elencate nella sezione 3.

---

## 2. Cosa funziona (e perché è un salto di qualità)

1. **D240 sepolto correttamente.** SUPERSEDED / DO_NOT_EXECUTE è esattamente la direttiva impartita dal Supervisor. Nessuna residua teoria del marker.

2. **La domanda centrale è quella giusta.** Non "D1 può ricevere B0?" ma: il command path ha già letto il primo frame B0/TLS? Come trasferisco l'ownership al TLS bridge esattamente una volta, senza perdere/duplicare byte e senza un secondo USB read? Questo è il vero problema ingegneristico (first-record ownership), formulato come lo formulerebbe un engineer senior.

3. **Correzione terminologica con disciplina epistemica.** Il PM corregge un errore del Supervisor nella sessione precedente: con Tls12PskServer sull'host (confermato anche da Rockytkg), il dispositivo è il TLS client e il primo messaggio atteso è un ClientHello, non un ServerHello. E — punto cruciale — il PM non promuove la correzione a fatto: vieta di classificare il body D239 come ClientHello senza validarne realmente il TLS record header e il handshake type (sezione 1 e 5.2). Questo è evidence-first applicato anche al Supervisor. Bene.

4. **same_validated_psk_used_by_tls deve riflettere il dataflow reale, "non essere semplicemente impostato a true".** Questa frase da sola vale il prompt: impedisce il fix-falso.

5. **Scope live chirurgico.** D1 once → handshake → close. D4 esplicitamente escluso con classificazione dedicata (TLS_CRYPTOGRAPHIC_HANDSHAKE_COMPLETED_D4_NOT_EXECUTED) se il motore lo pretendesse. Fail-closed senza paranoia.

6. **Lezioni del post-mortem recepite una per una:** report-dir preparata autonomamente dal wrapper (7.1), failure leggibile invece di "root preflight failed" (7.2), Executable Closure Gate (9), anti-microstep "non creare D242" (9), bundle diverso da avanzamento (14), manuale canonico non append-only (11).

7. **Test matrix T1-T8 coerente con la correzione di classe:** handoff exactly-once, no double consumption, malformed fail-closed, provenance PSK, contatori vietati a zero, zeroization, lifecycle directory.

---

## 3. Findings Red Team (integrazioni richieste)

### R1 — VINCOLANTE — Namespace marker di autorizzazione

Il marker consumato d238-operator-invocation.marker esiste ancora in /var/lib/goodix-5125-poc/ (contenuto: "D239 human-authorized single invocation"). Il wrapper D239 contiene il check:

    [[ ! -e "$AUTHORIZATION_MARKER" ]] || die 70 "this operator authorization was already consumed..."

Se il kit D241 riusasse lo stesso path, morirebbe al primo lancio con "already consumed". È la stessa classe di problema che ha morso il progetto due volte (marker storici / stato persistente non modellato).

Azione richiesta: il kit D241 deve usare un marker path nuovo (d241-operator-invocation.marker) e il preflight/wrapper deve trattare i marker consumati storici come stato atteso e innocuo, non come blocco. Aggiungere regression test specifico.

### R2 — VINCOLANTE — Coerenza dei seal SHA256

Il wrapper D239 embedde costanti fisse (EXPECTED_BACKEND_SHA256, EXPECTED_ENTRYPOINT_SHA256, EXPECTED_UNSEAL_SHA256) e un unseal patch con hash fissati. D241 modifichera' backend ed entrypoint: se il kit D241 non rigenera coerentemente sealed-baseline + patch + costanti, fallira' con die 68 al primo lancio.

Azione richiesta: checklist di review esplicita — i costanti SHA256 del kit D241 devono corrispondere al nuovo stato sealed e il patch unseal deve essere rigenerato e verificato nello stesso step.

### R3 — VINCOLANTE — Timeout limitato del handshake TLS

Il tentativo live e' single-shot: se il device stalla dopo il ClientHello (o dopo un nostro ServerHello sbagliato), il kit non deve restare appeso ne' abortire senza classificazione.

Azione richiesta: bounded handshake timeout con classificazione distinta, es. D241_FAILURE_CLASS=TLS_HANDSHAKE_TIMEOUT_AFTER_CLIENTHELLO, e cleanup/close esattamente una volta.

### R4 — RACCOMANDATA — Observability redatta del handshake

Se il handshake fallisce, dobbiamo poter diagnosticare senza una nuova run live (lezione 11.6 del post-mortem: errore con informazione utile non esposta genera un nuovo step di diagnosi).

Azione richiesta: pubblicare trace redatto — sequenza content-type dei record, transizioni di stato handshake, alert su failure. Zero key material, zero payload biometrico.

### R5 — RACCOMANDATA — Fixture record frammentato

Su questo trasporto la frammentazione esiste (osservazione D239: A6 = frame_fragmented_across_usb_completions). I record TLS post-handoff potrebbero frammentarsi allo stesso modo.

Azione richiesta: aggiungere al T1 una fixture con record TLS frammentato su due USB completion, per provare che il reassembly del bridge funziona anche dopo l'handoff.

### R6 — INFORMATIVA — Plausibilita' ClientHello a 52 byte

Calcolo da registrare nel manuale come INFERENZA (non fatto): ClientHello TLS 1.2 senza estensioni = 41 byte di body (version 2 + random 32 + session_id_len 1 + cipher_suites 4 + compression 2), + 4 byte handshake header = 45, + 5 byte record header = 50. I 52 byte osservati in D239 sono compatibili entro 2 byte di overhead wrapper/length. Rafforza la prior per ClientHello; la decisione resta alla verifica byte-per-byte della sezione 5.2 del prompt D241.

---

## 4. Conclusione operativa

**All'AI PM:** integra R1-R3 nel prompt prima della consegna all'esecutrice; incorpora R4-R5 nei test se possibile; registra R6 nel manuale tecnico come inferenza con classificazione epistemica esplicita. Tutto il resto e' approvato cosi' com'e'.

**All'Utente (Guido):** il significato pratico e' semplice — questo prompt non produrra' un altro "incubo da 6 bundle". Prepara un kit eseguibile, non tocca il sensore, e il prossimo avanzamento valido sara' riconosciuto solo se arriva dal dispositivo reale (handshake TLS completato sul firmware 12509) — esattamente il metro di misura stabilito nelle Linee Guida v2.0. Quando l'esecutrice consegnera' D241 con Executable Closure Gate = PASS, il Supervisor chiedera' una sola autorizzazione umana per l'unico tentativo live.

---

## 5. Riepilogo stato progetto (snapshot al termine della review)

- Massimo confine live raggiunto: E4 → A2 → 82 → A6 → A2 → 70 → 80x4 → 90 → D1, con risposta B0/TLS diretta (52 byte) ricevuta in D239.
- PSK/validator E4 binding: MATCH confermato sul target.
- Causa del blocco D239: host-side (durable_report_path), risolta con 3 comandi manuali; il prompt D241 incorpora la correzione autonomamente (sezione 7.1).
- Punto di abort attuale: classificazione unexpected_data sulla transizione D1 → B0/TLS; problema software-side di ownership del primo record TLS.
- D240: SUPERSEDED / DO_NOT_EXECUTE.
- D241: approvato con integrazioni R1-R3; prossimo deliverable = kit eseguibile con Executable Closure Gate PASS.
- Prossimo avanzamento valido: TLS cryptographic handshake completato sul 27c6:5125 / 12509, oppure nuova evidenza granulare dal dispositivo reale.

---

**AI Supervisor (Qwen) — Red Team Lead**
**Review completata: 16 agosto 2026**
