# Phase C — osservazione diagnostica zero-mask

Probe temporaneo per Goodix `27c6:5125`, APP12509, Fedora 44 x86_64.
Non corregge l'enrollment. La live è esclusivamente manuale: Codex prepara e
verifica offline, poi si ferma con `STATUS=HUMAN_REQUIRED`.

## Prerequisiti

- Branch `development`, sorgenti e dipendenze della [build pubblica](../../docs/INSTALLATION.md).
- Materiale runtime legittimo già installato e funzionante; il kit non lo
  legge per produrre log, non lo copia e non lo modifica.
- Sessione desktop aperta, password disponibile. Chiudere le impostazioni
  impronte KDE e altre applicazioni che potrebbero usare il lettore.
- Nessun altro client diretto del lettore. Il kit esclude fprintd con una mask
  **runtime**, che rimane fino al rollback. Non modificare questa mask durante
  il run. Se esiste già un override runtime, il kit si ferma.
- Non sospendere, riavviare o scollegare il dispositivo durante il run.

## Preparazione e primo run

Dalla root del repository, come utente normale, compilare in una directory
nuova. La compilazione e `--self-check` non enumerano USB. Non aggiungere
`sudo` alla build. I seguenti `sudo` sono azioni manuali dell'operatore.

```bash
python3 -B operator_kit/phase-c-zero-mask/build.py /tmp/goodix-phase-c-payload
sudo operator_kit/phase-c-zero-mask/install.sh /tmp/goodix-phase-c-payload
sudo operator_kit/phase-c-zero-mask/run.sh
```

L'installazione copia soltanto il payload verificato in
`/run/goodix-phase-c-zero-mask`, root-owned, privato, temporaneo. Non sostituisce
libfprint di sistema e non modifica PAM, KDE, firmware o configurazioni
persistenti. Il runner usa una libreria separata compilata con
`GOODIX_ENABLE_ZERO_MASK_PROBE`; richiede anche una chiamata esplicita alla
API di attivazione prima dell'apertura. Una variabile d'ambiente non basta.
La build production non contiene l'API e continua a rifiutare flags zero.

Durante il run appoggiare e sollevare lo stesso dito come in un enrollment.
Ogni avanzamento viene stampato in tempo reale. Dopo la riga
`classified=zero-mask` non iniziare un altro contatto: attendere lo STOP. L'eseguibile compie **una sola
ENROLL**, con deadline di 120 secondi, e non salva alcuna impronta. Un errore
riportato dal progresso cancella il tentativo. Se non compare uno zero-mask,
anche un enrollment completato viene scartato in memoria: non avviare un
altro tentativo automaticamente.

Verificare nel log:

```text
GOODIX_ZERO_MASK_PROBE_BUILD=1 ...        # installazione/self-check
GOODIX_ZERO_MASK_PROBE_ACTIVE=1 ...       # attivazione effettiva nella action
GOODIX_ZERO_MASK_PROBE event_index=0 ... classified=zero-mask ...
GOODIX_ZERO_MASK_PROBE event_index=1 ...
GOODIX_ZERO_MASK_PROBE_RESULT=closed zero_seen=1 ... new_out_after_zero=0 ... outstanding=0 drained=1 context_closed=1
GOODIX_PROBE_CLOSE success=1
GOODIX_PROBE_PROCESS_EXIT=0
```

La riga BUILD non dimostra l'ingresso nell'osservazione: servono ACTIVE e
`event_index=0`. Gli eventi successivi hanno indici 1–4. Il primary del
contatto zero non viene consegnato. L'aborto della action dopo osservazione è
atteso; `success=0` nella riga ACTION_DONE non è da solo un errore del probe.

## Budget e STOP

Ingresso solo durante ENROLL, attesa IRQ0100 del ramo ripetuto, nessun OUT
pendente, A0/checksum/body16 validi, control36, IRQ0100, flags0000. Tutti i sei
raw devono produrre `1 <= (word >> 1) <= 254`, senza troncamento/wrap. È una
politica diagnostica conservativa, non una nuova accettazione production.

Dopo ingresso: **zero OUT**, inclusi20/32, nessun aux B0, consegna primary,
nuovo contatto, avanzamento stage, retry o rearm. Il backend blocca qualsiasi
OUT e il riuso della generation per tutta la vita dell'istanza. Solo nuovi
trasferimenti USB **IN** mantengono aperta l'osservazione: non sono rearm FDT.

Hard stop al primo tra quattro A0 successivi e tre secondi. Quattro consente
anche di vedere un secondo0200, mantenendo piccolo il budget. Solo0200 con
shape/raw/flags compatibili continua entro il budget; altro IRQ, malformed,
unknown, B0 inatteso, errore trasporto o cancel chiudono fail-closed. Il
silenzio e il timeout **non provano una barriera firmware**. Eventi dopo la
chiusura non vengono osservati e non si deduce che non esistano.

Fermarsi dopo ogni run. Se zero-mask, sequenza leggibile e cleanup corretto
sono già presenti, la prima prova basta. Non insistere se manca ACTIVE, se
l'apertura fallisce o se la sequenza è ambigua. Ctrl+C richiede cancel/drain.
Un watchdog esterno interviene a140s, chiede cancel e concede10s; un eventuale
`GOODIX_PROBE_FORCED_STOP=1 CLEANUP_UNPROVEN=1` significa STOP e review, senza
secondo run. Anche l'assenza del risultato finale/close richiede STOP.

## Raccolta e rollback

I log restano in `/run/goodix-phase-c-zero-mask/run-1.log` (eventuale run-2).
Sono metadata; non includono immagini, template, raw words, frame, plaintext,
PSK o materiale protetto. Non impostare debug libfprint/USB/TLS esterni.
Raccogliere prima di rollback o riavvio, perché `/run` è volatile.

```bash
sudo operator_kit/phase-c-zero-mask/collect.sh > /tmp/goodix-phase-c-evidence.tar.gz
sudo operator_kit/phase-c-zero-mask/rollback.sh
```

La raccolta include solo i log dei due run e il manifest degli hash del
payload. Condividere l'archivio per review. Il rollback rimuove solo la mask
creata dal kit e la sua directory temporanea. Deve stampare
`ROLLBACK_VERIFIED=1 TEMPORARY_PAYLOAD_REMOVED=1 SYSTEM_LIBRARY_REPLACED=0`.
Non avvia il sensore: fprintd torna attivabile normalmente tramite D-Bus.
Il payload di build in `/tmp/goodix-phase-c-payload` resta una copia inerte.

## Eventuale secondo run

Al massimo **due run manuali** per questa preparazione; anche un run fallito
consuma un tentativo. Nessun retry automatico. Il secondo richiede una
**decisione umana dopo review del primo log**, solo se utile a distinguere un
pattern deterministico da una variante reale. Prima del rollback:

```bash
sudo operator_kit/phase-c-zero-mask/run.sh --reviewed-run-1
```

Poi raccogliere e fare rollback. Non reinstallare il kit per aggirare il
limite; reboot/rollback elimina il contatore volatile e non autorizza nuove
prove. Una nuova preparazione richiede una decisione umana esplicita.

## Verifica offline e limiti

[Il contratto](../../docs/ENROLLMENT_ZERO_MASK_CONTRACT.md) resta aperto.
I test sintetici coprono parser/graph, blocco di tutti256 control OUT,
zero/uno/due0200, budget4 anche concatenato, timeout, altroIRQ, malformed,
unknown, B0, cancel, drain e close. Normal e ASan/UBSan usano esclusivamente
USB simulata. La suite TLS verifica VERIFY, IDENTIFY, duplicate detection e
enrollment ordinario. Nessuna prova offline dimostra il comportamento
spontaneo firmware, la latenza reale di cancel USB o un correlatore late0200.

I sorgenti del probe/kit sono implementazioni originali di questo progetto;
licenza GPL-2.0-or-later per il runner/kit, LGPL-2.1-or-later per le modifiche
al driver. Il payload porta licenze e manifest; non contiene materiale OEM.
