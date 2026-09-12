<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D291/01 — re-enrollment diversificato e verifica di stabilità

```text
STATUS=HUMAN_GATE_READY
PURPOSE=VALIDATE_ROCKY_DERIVED_ENROLLMENT_DIVERSITY
FACTORY_PRESERVING=true
```

## Cosa fa

Con un solo comando il kit costruisce la candidate dal `development` già
pushato, aggiorna soltanto la `libfprint` del runtime D285, sostituisce il
template host dell'indice destro con un enrollment governato dalla policy
Rocky 3/8/2/MAD<8 e prova quattro serie VERIFY indipendenti.

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

## Prerequisiti e stop condition

- branch `development`, HEAD uguale a `origin/development`, worktree pulito;
- installazione persistente D285/D286 integra;
- directory RPM OpenCV già presente in `GoodixArtifacts/opencv-4.13-rpms`;
- un solo sensore `27c6:5125` collegato;
- nessun altro consumer fprintd attivo;
- indice destro disponibile per enrollment e VERIFY;
- nella serie 1 usare prima un dito diverso e poi l'indice destro;
- se compare la password durante una serie, premere `Ctrl-C` senza digitarla;
- non rilanciare automaticamente una run fallita.

## Comando operatore

Dalla root del repository:

```bash
operator_kit/d291-01-multi-verify/run-d291-01.sh --operator-run
```

Confermare nell'ordine `AGGIORNA D291`, `REENROLL DESTRO` e, prima di ogni
serie, `SERIE N PRONTA`. Il dialogo `pkexec` usa il percorso password separato
di `system-auth`, sul quale D285 mantiene fingerprint disabilitato.

Il risultato sanitizzato è scritto in una directory
`/tmp/goodix-d291-01-result.*` riportata come `RESULT_DIRECTORY`. Contiene
conteggi, outcome e audit di sicurezza, ma non template, raster, password,
PSK o materiale protetto. Il successo termina con:

```text
D291_01_LIVE_RESULT=PASS_REENROLL_AND_4_MATCHED_SERIES
```

Il nuovo runtime e il nuovo template restano attivi soltanto dopo il successo;
lo state root-only D285 viene aggiornato con i nuovi hash per mantenere audit e
uninstall readiness.
