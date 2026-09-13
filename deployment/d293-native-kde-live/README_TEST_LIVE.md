<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D293 — patch minimale per validazione KDE nativa

## Scopo

Questa patch installa la corrente production candidate D293 di `libfprint`
costruita da `production/`, inclusi i correttivi offline D293 e R9. Serve a
osservare sul target Fedora KDE reale se un nuovo utente locale può vedere il
lettore Goodix, registrare un dito, verificarlo e cancellarlo tramite il flusso
nativo KDE/fprintd, senza contaminare il principal preesistente.

Non valida login, lock screen, `sudo`, firmware o scritture persistenti sul
sensore. Non installa, adatta né usa l'Operator Kit D293/04; non contiene
collector, classifier, orchestratore o logica di conteggio delle azioni.

## Prerequisiti e STOP

- branch `development`, HEAD pubblicato su `origin/development` e worktree
  completamente pulito;
- Fedora 44 x86_64 con `fprintd-1.94.5-5.fc44.x86_64` e
  `libfprint-1.94.100-1.fc44.x86_64`;
- Flatpak SDK `org.freedesktop.Sdk//25.08` e gli RPM OpenCV locali già usati
  dalla build production;
- installazione D285 persistente integra e servizio `fprintd.service` in stato
  leggibile `active` oppure `inactive`;
- nessuna enrollment/verify in corso e tutte le UI biometriche chiuse prima di
  avviare l'installazione;
- nessuna altra patch D293 nativa già presente.

`STOP_IF=` uno dei prerequisiti fallisce, lo script segnala drift/collisione,
il servizio è in uno stato diverso da `active`/`inactive`, compare una richiesta
inattesa di modificare il sensore, oppure il principal preesistente cambia. Non
aggirare i controlli e non ripetere automaticamente un'operazione biometrica
fallita.

Commit/candidate attesa: il commit `development` corrente al momento
dell'installazione. Lo script ne registra lo SHA completo nello stato root-only
e costruisce la libreria esclusivamente con `production/build.sh`.

## Installazione

Dalla root del repository, come utente normale:

```bash
deployment/d293-native-kde-live/install.sh
```

La build è unprivileged e offline. Solo la copia/attivazione finale richiede
`sudo`. La patch aggiunge:

- `/usr/local/lib64/goodix-27c6-5125/d293-native-<SHA>/`;
- `/usr/local/sbin/goodix-d293-native-fprintd`;
- `/etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf`;
- `/etc/goodix-27c6-5125/d293-native.state`.

Non sostituisce file RPM, PAM, sudoers, template o file D285. Lo stato registra
hash della candidate e della definizione/D285 precedenti; il wrapper verifica
daemon e runtime a ogni avvio. L'installazione è effettiva quando termina con
`D293_NATIVE_INSTALL=PASS`. Lo stato `active`/`inactive` precedente del servizio
viene preservato; se era attivo, l'installazione lo riavvia sulla candidate, e
se era inattivo partirà normalmente su richiesta di KDE. Da quel momento il
driver può enumerare il target e le azioni KDE/fprintd raggiungono il sensore:
questa è la ragione del Human Gate.

Se la validazione termina con PASS, la candidate resta installata per default e
diventa la baseline software corrente del target. Il rollback resta disponibile
come antidoto e non è una cerimonia obbligatoria dopo un successo.

## Validazione live nativa

1. Nel principal preesistente osservare soltanto lo stato biometrico mostrato
   da Impostazioni di sistema → Utenti, quindi creare da lì un nuovo normale
   utente locale.
2. Aprire una vera sessione Plasma di quel nuovo utente.
3. In Impostazioni di sistema → Utenti verificare che compaia il lettore di
   impronte e registrare un dito con il normale flusso KDE.
4. Da un terminale della sessione del nuovo utente eseguire:

   ```bash
   fprintd-verify
   ```

   Dopo `verify-no-match` si può ripetere lo stesso comando fino a un massimo
   complessivo di tre tentativi fisici. Fermarsi al primo `verify-match` o al
   terzo `verify-no-match`; nessun quarto tentativo. Cancellare poi l'impronta
   dall'interfaccia KDE nativa.
5. Chiudere la sessione del nuovo utente. Nel principal preesistente verificare
   che il suo stato biometrico sia invariato.

`PASS_IF=` il nuovo utente vede il reader, enrollment, verify e delete nativi
completano correttamente e il principal preesistente resta invariato.

`FAIL_IF=` il reader non compare, una delle tre operazioni fallisce o si
blocca, KDE/fprintd mostra un errore, oppure cambia il principal preesistente.

Al primo FAIL fermarsi: non aggiungere tentativi o comandi diagnostici
improvvisati. Non includere nei messaggi template, dati biometrici, secret o
file root-only.

## Permanenza dopo PASS e rollback

La rollback patch è sempre fornita e mantenuta come rete di sicurezza, ma non
viene eseguita automaticamente dopo un PASS.

```text
ROLLBACK_PATCH_REQUIRED=true
ROLLBACK_ON_FAIL=true
ROLLBACK_ON_PASS=false
KEEP_VALIDATED_ADVANCEMENT_BY_DEFAULT=true
```

Se la live termina con PASS, lasciare la candidate installata: essa diventa la
baseline software corrente del target per i boundary successivi.

Eseguire il rollback quando ricorre almeno una delle seguenti condizioni:

- FAIL funzionale del boundary appena provato;
- instabilità o regressione osservata dopo l'installazione;
- rollback esplicitamente richiesto dal test corrente;
- necessità motivata di tornare alla baseline precedente per confronto o
  recovery.

In tali casi, chiudere le UI biometriche e dalla root del repository eseguire
come lo stesso utente che ha installato:

```bash
deployment/d293-native-kde-live/uninstall.sh
```

Il rollback verifica prima l'integrità di candidate, script corrente e D285,
ferma fprintd, rimuove soltanto i quattro effetti della patch, ricarica systemd
e controlla che la definizione precedente sia byte-identica. Lo stato finale
atteso è:
D285 nuovamente effettivo e integro, stato `active`/`inactive` precedente del
servizio ripristinato, nessuna directory/wrapper/drop-in/state D293 nativa. La
libreria Fedora, PAM, sudoers e i template non vengono toccati.

Il rollback è completo soltanto quando termina con
`D293_NATIVE_ROLLBACK=PASS`.

Il nuovo account è stato creato manualmente, non dalla patch: dopo avere
cancellato l'impronta in KDE può essere rimosso separatamente da Impostazioni
di sistema → Utenti, se desiderato.

Se il rollback segnala drift dello script o della definizione systemd, non
aggirare il controllo e non cancellare file a mano: riportare il messaggio
all'AI. Conservare sempre nel repository/versionamento la possibilità di
ricostruire l'antidoto corrispondente alla baseline installata.

## Cosa riportare all'AI

Riportare `PASS` oppure il primo punto preciso di failure, il comportamento e
il messaggio visibile, se presente; confermare inoltre l'isolamento del
principal preesistente e indicare se la candidate è rimasta installata oppure
se è stato necessario il rollback. Journal o query read-only mirate saranno
richiesti soltanto dopo un failure reale. Non inviare lo state root-only né
contenuti sotto `/var/lib/fprint`.
