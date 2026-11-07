<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# CORROBORATIONS.md — Prior art ed evidenze esterne

Indice sintetico di fonti ed evidenze esterne per la roadmap. **Una fonte non prova da sola la compatibilità o una causa generale di failure del Goodix 27c6:5125.** I requisiti della nuova diagnostica appartengono a [diagnostic_statement.md](diagnostic_statement.md), non a questo indice. Caricare le fonti solo quando pertinenti.

## C1 | PRIMARY / UPSTREAM_SOURCE

- **Fonte:** [FreshHomie/goodix521d-fprintd](https://github.com/FreshHomie/goodix521d-fprintd).
- **Snapshot:** [v0.1.0-19](https://github.com/FreshHomie/goodix521d-fprintd/tree/v0.1.0-19), commit `4f48c482f35976ea4fac27d5e598730581c4f380`; dipendenza Milan pin `e68eb725b1a7845b401b1a3c9b0790921f12133e`.
- **Claim:** sorgenti C ispezionabili del motore Type 17 (preprocessing, feature, enrollment, recognition, template e study) con API utilizzabili offline senza USB/fprintd privato.
- **Limite:** algoritmi e configurazione qualificati sul 521d; compatibilità 5125 sconosciuta. Licenze prevalentemente LGPL/MIT con moduli terzi: provenienza e redistribuibilità dei **file effettivamente portati** da verificare.
- **Rilevanza:** M0–M4.

## C2 | PRIMARY / MAINTAINER_STATEMENT

- **Fonte:** [Issue #1](https://github.com/FreshHomie/goodix521d-fprintd/issues/1), [risposta tecnica di FreshHomie](https://github.com/FreshHomie/goodix521d-fprintd/issues/1#issuecomment-6250360099).
- **Claim:** ricostruzione dichiarata da `GoodixEngineAdapter.dll` Windows (`3.0.21.290`, SHA-256 DLL `5995d6565e602416cbe00f171ad4941203e345ccaddb490199274166adac4f5c`); confronti differenziali dichiarati su preprocessing, feature, template, enrollment, recognition e aggiornamenti per **riga parametri 12 / tipo algoritmo 17**.
- **Indicazione prioritaria:** identificare **prima** l'algorithm type effettivo dell'Engine Adapter Windows del **5125**. Poi confrontare stessi input e output completi (pixel, quality/coverage, feature, maschere, metadati), non solo dimensioni o numero di feature. `flags=0` è il punto di partenza senza learning; il voto 3/10 è policy del controller Linux, non Windows dimostrato; il daemon stock è plausibile per enrollment e verifica.
- **Limite:** testimonianza dell'**autore di C1**, non evidenza indipendente; oracle Windows e corpus della campagna non sono tutti pubblici. Nessuna certificazione di provenienza clean-room, compatibilità 5125, FAR o spoof resistance.
- **Rilevanza:** M0, M2–M6.

## C3 | PRIMARY / OPEN-SOURCE CHICAGO BACKEND

- **Fonte:** [berkekbgz/libfprint-goodix-spi](https://github.com/berkekbgz/libfprint-goodix-spi/tree/main); [architettura](https://github.com/berkekbgz/libfprint-goodix-spi/blob/main/docs/ARCHITECTURE.md), [dispositivi supportati](https://github.com/berkekbgz/libfprint-goodix-spi/blob/main/docs/SUPPORTED_DEVICES.md), [parity record](https://github.com/berkekbgz/libfprint-goodix-spi/blob/main/re/PARITY.md), [provenienza](https://github.com/berkekbgz/libfprint-goodix-spi/blob/main/PROVENANCE.md).
- **Snapshot di ricognizione:** branch `main`, commit `010a665f54089a1632b1ab7be588b316ace934e2` (19 ottobre 2026). Per qualsiasi esperimento fissare e verificare lo snapshot effettivamente utilizzato.
- **Claim del progetto:** backend biometrico ChicagoHS senza I/O in `lib/goodix/chicago/`, distinto dal trasporto SPI `drivers/gdix51c0/`; codice per calibrazione, preprocessing, feature, enrollment, template, identify e `templateStudy`, ricostruito con confronti dichiarati rispetto alla stack Windows `AlgoChicago.dll`.
- **Indizi di rilevanza per il 5125:** il GDIX51C0 documenta chip ID `0x2504`, sensor type 12 (ChicagoHS), geometria 80×64 e payload calibrazione `0x224b0`, valori sovrapponibili a quelli osservati sul Goodix 5125 del progetto. Il 5125 Windows carica `AlgoChicago.dll`.
- **Limiti:** il solo dispositivo hardware qualificato dall'autore è **GDIX51C0 su SPI**, non il Goodix **27c6:5125 USB**. Identità parziale di profilo/DLL/formati non prova equivalenza di frame, orientamento/regroup, OTP, ImageBase, preprocessing, template o accuratezza del matching sul 5125. I test di parità Windows sono dichiarati dall'autore e non sono un nostro risultato.
- **Licenza/provenienza:** README/LICENSE indicano LGPL-2.1-or-later per i sorgenti originali, salvo eccezioni. Verificare `PROVENANCE.md` e gli header/licenze **dei file effettivamente riusati** prima di eventuale import o pubblicazione; nessuna presunzione di compatibilità licenze.
- **Rilevanza:** M3 (audit Chicago, eventuale harness e confronto decisionale); M4–M6 soltanto se Chicago risulta il candidato selezionato. Nessuna installazione o provisioning SPI.

## C4 | USER_REPORT / ENVIRONMENT_INSTALL_BLOCK

- **Fonte:** [issue #55 — “The operation failed” on Fedora 45](https://github.com/sorguido/goodix-27c6-5125/issues/55), segnalazione dell'utente, output dei controlli e conclusione del maintainer (6–7 novembre 2026).
- **Claim osservato:** sull'host segnalato erano presenti un drop-in `fprintd.service.d/keepalive.conf` con `--no-timeout` e file essenziali mancanti nel pacchetto Fedora `libfprint`. L'override non riconosciuto è sufficiente a far rifiutare in sicurezza l'installazione dal preflight canonico; il Manager mostrava un errore generico.
- **Limite:** singolo caso reale, non stima di frequenza né prova che tutti i fallimenti di installazione abbiano questa causa. Il possibile rapporto fra file mancanti e precedente exit 127 di fprintd richiederebbe conferma dai journal; non assumere causalità ulteriore.
- **Dettaglio:** issue e allegati collegati nella conversazione GitHub; non copiarvi output sensibili. Desiderata e criteri di progettazione: `diagnostic_statement.md`.
- **Rilevanza:** DIAG0–DIAG4, soprattutto messaggi discriminanti e preflight read-only.
