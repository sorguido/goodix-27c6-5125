<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Operator kit inventory

## D268/01 first-image one-shot (offline-ready, live non autorizzato)

`./operator_kit/d268-first-image-once.sh --dry-run` è il Kit Operatore
corrente per il confine first-image. Il launcher e tutti i messaggi operatore
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

Non esiste un kit operativo corrente **autorizzato live**. D268 è il current
path revisionabile ma non incorpora né auto-approva il commit SHA richiesto e
non autorizza una run. I marker storici non devono essere cancellati o
riutilizzati.
