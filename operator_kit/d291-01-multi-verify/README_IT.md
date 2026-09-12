<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D291/01 — evidenza storica del re-enrollment diversificato

```text
STATUS=HISTORICAL_CLOSED_DO_NOT_RERUN
EXECUTION_DISABLED=true
LIVE_RESULT=PASS_REENROLL_AND_4_MATCHED_SERIES
PURPOSE=AUDIT_ROCKY_DERIVED_ENROLLMENT_DIVERSITY
FACTORY_PRESERVING=true
```

La live è stata completata con successo dall'Utente sulla candidate
`cbf582f4dcdb7eeb6c8381223c84d37363386870`. Il launcher rifiuta ora sia
`--operator-run` sia `--root-run` prima di qualsiasi azione. Il contenuto
sottostante descrive il percorso eseguito ed è conservato esclusivamente per
audit; non costituisce un'istruzione a ripetere la live.

## Cosa fa

Il kit ha costruito la candidate dal `development` già pushato, aggiornato
soltanto la `libfprint` del runtime D285, sostituito il template host
dell'indice destro con un enrollment governato dalla policy Rocky 3/8/2/MAD<8
e provato quattro serie VERIFY indipendenti.

La prima serie richiede deliberatamente un dito non registrato (`NO_MATCH`) e poi l'indice
destro. Le altre tre usano l'indice destro in normali posizioni quotidiane.
Ogni serie conserva il controllo PAM `max-tries=3`, termina al primo MATCH e
non consente una quarta acquisizione. Il successo richiede il rigetto del dito
errato e un MATCH entro tre tentativi in tutte e quattro le serie: non basta
un singolo MATCH fortunato.

Il preprocessing R2, il formato FP3, il matcher e la soglia 40 non cambiano.
Il vecchio template è quindi strutturalmente compatibile, ma non può provare
la qualità della nuova policy: il re-enrollment è necessario per questo gate.

## Rischio e rollback

La run raggiunge il sensore reale, usa `pkexec`, sostituisce temporaneamente
il driver attivo e modifica il template biometrico host in `/var/lib/fprint`.
Non esegue flash, IAP, ClearApp, provisioning, scrittura PSK/OTP, modifica di
configurazione persistente del sensore o comandi wire nuovi.

Prima della prima modifica root, il kit verifica repository, candidate,
runtime D285, PAM, unico target e unico template ownership-pinned. Driver,
manifest, state e vecchio template sono copiati in una directory root-only.
Qualunque errore successivo arresta fprintd e ripristina tutti e quattro. Il
backup temporaneo viene eliminato dopo successo o rollback; l'unlink non è
garanzia di cancellazione fisica su SSD, CoW, journal o snapshot.

## Enrollment

Usare sempre l'indice destro, spostandolo deliberatamente fra centro, lati e
punta. Il template finale contiene da 3 a 8 campioni. Un contatto troppo
simile a un campione già accettato produce un retry esplicito della stessa
operazione e non entra nel template; il numero totale di contatti fisici è
limitato tecnicamente a 20. Due duplicati consecutivi dopo almeno tre campioni
chiudono la copertura accettando il contatto finale, come nel riferimento
Rocky. Un errore o il superamento del limite attiva il rollback.

## Prerequisiti e stop condition della live chiusa

- branch `development`, HEAD uguale a `origin/development`, worktree pulito;
- installazione persistente D285/D286 integra;
- directory RPM OpenCV già presente in `GoodixArtifacts/opencv-4.13-rpms`;
- un solo sensore `27c6:5125` collegato;
- nessun altro consumer fprintd attivo;
- indice destro disponibile per enrollment e VERIFY;
- nella serie 1 usare prima un dito diverso e poi l'indice destro;
- se compare la password durante una serie, premere `Ctrl-C` senza digitarla;
- non rilanciare automaticamente una run fallita.

## Esecuzione disabilitata

Il comando storico era:

```bash
operator_kit/d291-01-multi-verify/run-d291-01.sh --operator-run
```

Non deve essere rilanciato: termina con
`D291_01_STATUS=HISTORICAL_CLOSED_DO_NOT_RERUN` prima di build, `pkexec`, sudo,
USB o modifica del runtime. Durante la live chiusa le conferme erano, in ordine,
`AGGIORNA D291`, `REENROLL DESTRO` e `SERIE N PRONTA`.

Il risultato sanitizzato è scritto in una directory
`/tmp/goodix-d291-01-result.*` riportata come `RESULT_DIRECTORY`. Contiene
conteggi, outcome e audit di sicurezza, ma non template, raster, password,
PSK o materiale protetto. Il successo termina con:

```text
D291_01_LIVE_RESULT=PASS_REENROLL_AND_4_MATCHED_SERIES
```

Il nuovo runtime e il nuovo template sono rimasti attivi dopo il successo; lo
state root-only D285 è stato aggiornato con i nuovi hash e il backup temporaneo
è stato eliminato. Non è stato eseguito rollback.
