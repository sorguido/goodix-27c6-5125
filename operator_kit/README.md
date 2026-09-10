<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Operator kit inventory

## D280/01 riuso FP3 effimero close/open (offline-ready, Human Gate)

`d280-01-ephemeral-template-reuse/` prepara una run a due action esplicite:
enrollment fixed-eight, FP3 root `0600` effimero, distruzione del print,
close/open, rimozione del file prima dell'action e una identify
single-acquisition. Secondo epoch, export e cleanup sono fail-closed; il grant
è single-use e non esiste retry. Il preflight production Fedora/SIGFM è PASS
senza USB. Nessuna baseline è approvata e nessuna run live è autorizzata. La
presenza anche breve del dato biometrico e il limite di `unlink` su SSD
richiedono accettazione esplicita nella nuova Human Gate.

## D279/57 enrollment SIGFM stage-8 (PASS finale; tutte le run consumate)

`d279-57-stage8-early-terminal/` prepara una sola action enrollment production
SIGFM a otto stage per verificare su APP12509 il terminale senza nono `0x32`.
Il cap fisso isola il boundary sensor-side; non implementa ancora la selezione
dinamica né prova la riutilizzabilità post-close. Le prime tre run sui full SHA
`1afe72e4...`, `d94c7af1...` e `4de9c342...` sono terminate fail-closed e i
relativi grant sono consumati. Il correttivo separa progresso
biometrico e finger-status fisico, differisce ogni consegna fino al
release-ready dopo l'ACK finale `0x34` e trattiene la sola completion riuscita
dello stage 8 fino all'IRQ `0x0200`; aggiunge inoltre telemetria mismatch
sanitizzata. D279/59 sostituisce i magic flags con una policy canale FDT
centralizzata e aggiunge al preflight il corpus autentico hash-gated. La run
successiva sul full SHA `38962cc0...` ha completato 8/8 stage, sette re-arm e
il terminale senza nono `0x32`; il grant è consumato e gli output sanitizzati
hash-pinned sono versionati in `captures/D279_57/`. D279 è chiuso. Il launcher
resta storico/live-capable ma non autorizzato: nessun retry o nuovo live è
implicito.

## D279/54 identify OEM passiva (pre-live, hard-gated)

`d279-54-oem-passive-identify-observe/` cattura con TShark/USBPcap una sola
verifica Windows Hello già configurata e non contiene sender Goodix. Authority,
baseline, snapshot, template esistente, rischio di aggiornamento adattivo e
live sono tutti chiusi nel template versionato. I test Linux hardware-free
passano; qualificazione PowerShell Desktop 5.1, full SHA e autorizzazione
one-shot restano Human Gate.

## D279/35 valutazione ATTEMPT02 offline protetta (in attesa di Human Gate)

`d279-35-offline-protected-evaluation/` costruisce da snapshot Git l'evaluator
aggregate-only D279/31–34. Il preflight è interamente sintetico e non legge il
layout protetto. La singola run futura richiede full SHA approvato, grant
single-use e `sudo` manuale per leggere una sola volta la PSK dal transport
production; non contiene USB, fprintd o sender e non persiste plaintext,
raster, template o conteggi per-frame. Nessuna analisi protetta è attualmente
autorizzata.

## D279/29 enrollment production one-shot (run conclusa, grant consumato)

`d279-29-one-shot-enrollment/` compila da snapshot Git la libreria production
Fedora 44/libfprint 1.94.100 con NBIS nativo e un client che esegue al massimo
una sola action enrollment, senza retry, seconda action, reopen o salvataggio
del template. Il preflight usa una baseline `UNAPPROVED_FOR_LIVE` e si arresta
prima di `FpContext`/USB. Preparazione e run live richiedono approvazione
esplicita del full SHA, grant deterministico single-use e avvio manuale con
`sudo`. La run approvata su `f4f0436acb887d9724a0ee77b51975fe3e072f44` è
conclusa e il grant è consumato; non è autorizzato alcun retry.

## D279/10 terza acquisizione OEM passiva (pre-live, hard-gated)

`d279-10-third-acquisition-observe/` osserva metadata USBPcap del lifecycle
dal secondo al terzo B0 senza sender Goodix. Il template authority e chiuso e
il live non e autorizzato. I test sintetici Linux sono 14/14; resta necessaria
la qualificazione nativa Windows con Goodix assente. Il terzo contatto ha un
rischio esplicito non risolto di commit enrollment host-side e non potra essere
autorizzato implicitamente.

## D279/07 layout privato production (gate concluso PASS)

`target_compatibility/d279_07_fprintd_layout/` contiene il provisioning
fail-closed dei cinque input in `/var/lib/goodix-5125-poc` e un probe
read-only a due fasi per identità root, sandbox systemd, metadata e policy
SELinux. Il corrective successivo al primo probe salta integralmente le
operazioni SELinux quando `getenforce=Disabled`; mapping e label sono
condizionali a Enforcing/Permissive. L'Utente ha poi eseguito provisioning e
probe full autorizzati con SELinux `Enforcing`: layout, policy e label sono
`PASS`. fprintd, USB e live non sono stati eseguiti.

## D272/01 validazione SIGFM (solo preflight offline)

`./operator_kit/d272-sigfm-validation.sh --dry-run` verifica il surface
operatore senza USB, secret, fprintd o acquisizione. Il flag riservato
`--future-live` è hard-disabled: non esiste un backend live D272 e nessuna
baseline è approvata.

## D268/01 first-image one-shot (offline-ready, live non autorizzato)

`./operator_kit/d268-first-image-once.sh --dry-run` è il Kit Operatore
storico per il confine first-image. Il launcher e tutti i messaggi operatore
sono in italiano; flag, capability, marker, report e authority appartengono al
namespace D268 e non riusano D267. Il percorso live resta bloccato senza flag
D268 esatto e full commit SHA approvato. In D268/01 la baseline non è
approvata, il live non è autorizzato e l'hardware non è stato eseguito.

## D264/02 first-image rehearsal (offline only)

`./operator_kit/d264-first-image-offline.sh` is a synthetic-only operator
rehearsal. With no argument it preserves `STOP_AFTER_FDT_ARM_ACK`; the
first-image candidate requires `--stop-after-first-image`. The launcher has no
live mode and rejects unknown or multiple selections before Python starts.

Questa directory conserva launcher storici per riproducibilità. **Nessun
launcher qui presente autorizza automaticamente una nuova run live**: le
single-shot già eseguite o consumate non sono riutilizzabili e ogni nuovo live
richiede review, baseline e autorizzazione esplicite.

| Launcher | Classificazione canonica |
| --- | --- |
| `d238-live-pre-d1-tls-once.sh` | storico, superseded e consumato |
| `d239-live-pre-d1-tls-once.sh` | storico, superseded e consumato |
| `d241-live-tls-once.sh` | storico, superseded e consumato |
| `d242-live-tls-once.sh` | storico, superseded e consumato |
| `d243-live-tls-once.sh` | storico, superseded e consumato |
| `d244-live-tls-once.sh` | storico, superseded e consumato |
| `d245-live-tls-once.sh` | storico, superseded e consumato |
| `d246-live-d4-once.sh` | ultimo launcher eseguito, single-shot consumato; non autorizza AF |
| `d250-live-af-once.sh` | storico, single-shot eseguito e marker consumato; non riutilizzabile |
| `d251-live-af-once.sh` | candidate corretto live-capable hard-gated; executable closure solo offline, review baseline AI PM e autorizzazione Utente pendenti |
| `d255-windows-evidence-capture.ps1` | storico, single-shot consumato; capture completata e recuperata offline, nessuna nuova run richiesta o autorizzata |
| `d279-29-one-shot-enrollment/` | enrollment production one-shot concluso su `f4f0436…`; grant consumato, nessun retry autorizzato |
| `d279-35-offline-protected-evaluation/` | current path offline aggregate-only; Human Gate per singola lettura protected pendente |
| `d279-54-oem-passive-identify-observe/` | candidate passivo OEM identify hard-gated; authority chiusa, qualificazione Windows/full SHA/autorizzazione one-shot pendenti |
| `d279-57-stage8-early-terminal/` | tre attempt fail-closed consumati; run finale `38962cc…` PASS 8/8 e consumata; D279 chiuso, nessun retry o test di reusability incluso |
| `d280-01-ephemeral-template-reuse/` | current boundary offline-ready; due action in due epoch, FP3 root 0600 rimosso prima di identify; full SHA e nuova Human Gate non ancora concessi |

Non esiste un kit operativo corrente **autorizzato live**. D280/01 è il kit
corrente ma ha soltanto executable closure offline. La run D279/29 è
consumata; tutte le run D279/57 sono consumate e la finale ha chiuso PASS il
boundary stage-8. D279/35 e D279/56 sono percorsi offline
protetti e la loro presenza non autorizza operazioni live. I marker storici
non devono essere cancellati o riutilizzati.
