# Patch locale Polkit/Discover

Current handoff: the local patch is **not installed** and remains uninstalled
during the combined sudo/Polkit closure. Do not use the installation below to
validate clean-candidate sudo; follow
`deployment/managed-install/AUTHENTICATION-LIVE.md` and its D285 migration gate.
The standalone lifecycle remains available for its original, separate scope.


**HUMAN_REQUIRED — preparata offline, da installare e provare dall'Utente.**
Scopo: impronta nel dialogo KDE/Polkit, con password subito utilizzabile e
massimo tre scelte esplicite d'impronta. La patch usa il daemon già attivo sul
PC D285/D293/login-early. Non valida una migrazione alla candidate managed,
firmware, affidabilità statistica o nuovi utenti/hardware.

Prerequisiti: checkout pulito `development`, candidate
`POLKIT_INTERRUPTIBLE_SERVICE_LOCAL_V1`; SHA completo stampato e registrato in
`PROVENANCE` durante la preparazione. Il codice e gli hash sono nel medesimo
commit. Non serve una seconda approvazione dello SHA. Build non privilegiata;
header RPM già in `GoodixArtifacts/login-header-rpms`, compilatore e strumenti
già utilizzati offline. Il sudo biometrico corrente è PASS riferito dall'Utente
e resta quello del percorso D285.

Chiudere i dialoghi di autenticazione. Tenere aperto un terminale e disporre
della password. STOP se il controllo segnala drift, versione/configurazione non
supportata, file personalizzati, installazione managed o materiale di recovery
in conflitto: riportare il messaggio senza forzare o cancellare file.

## Installazione

```bash
cd /home/guido/Repository/goodix-27c6-5125_private
development/patches/polkit-fingerprint/install.sh
```

Lo script prepara la build e invoca `sudo` soltanto per la transazione locale.
Non avvia autenticazioni Polkit né riavvia fprintd/Plasma. Attendere
`POLKIT_INSTALL=PASS live_validation=HUMAN_REQUIRED`.

Installa un modulo locale, i due servizi PAM Polkit, una regola tmpfiles e un
drop-in limitato al percorso scrivibile dell'helper socket. Salva l'assenza
originaria (o la copia identica al vendor) del PAM in `/var/lib/goodix-polkit`.
Configura il contatore temporaneo `/run/polkit/goodix-fingerprint`. Il dettaglio
dei file è in `production/polkit/README.md`; nessuna modifica a sudoers,
sudo PAM, KScreenLocker, plasmalogin o al runtime Goodix già installato.

## Normale workflow da osservare

Usare una normale operazione Discover già desiderata che richieda realmente
autenticazione, attendendo una richiesta nuova quando Polkit conserva il risultato.
Non provocare ripetute operazioni privilegiate soltanto per ottenere un dialogo.

1. **Password:** scrivere e inviare la password nel dialogo. Deve funzionare
   subito, senza aspettare un timeout d'impronta e senza toccare il sensore.
2. **Impronta:** inviare una volta il campo vuoto, attendere l'indicazione del
   dito e appoggiare il dito una sola volta. Al MATCH fermarsi. Dopo NO MATCH,
   rilasciare completamente e, nel nuovo dialogo, scegliere esplicitamente
   un secondo tentativo; allo stesso modo un terzo se necessario. Mai un quarto.
3. **NO MATCH poi password:** dopo un esito negativo inviare la password.
   Anche durante l'attesa d'impronta si deve poterla scrivere e inviare: l'attesa
   viene interrotta. Un eventuale breve svuotamento/animazione del campo va
   riportato, senza ritrasmettere la password se l'autenticazione è già riuscita.
4. **Annullamento:** nella successiva richiesta normale, annullare il dialogo
   durante l'attesa. Non devono proseguire richieste d'impronta o nuove serie.
5. Nei successivi usi ordinari verificare che sudo, sblocco sessione e login
   conservino il comportamento precedente. Anche queste serie si fermano al
   primo MATCH e rispettano i limiti già previsti per il rispettivo consumer.

Il limite è per utente e attraversa riavvii del dialogo: anche cancellazioni,
timeout ed errori consumano una scelta. Dopo tre scelte è necessaria una password
valida per rendere nuovamente disponibile l'impronta. Un MATCH chiude la serie.
Non cambiare identità o riaprire dialoghi per tentare di aggirare il limite.

`PASS_IF`: impronta riuscita entro la serie ammessa, password pronta sia
all'inizio sia dopo NO MATCH/durante attesa, annullamento efficace e nessuna
regressione nei workflow già funzionanti. Conservare la patch dopo PASS.

`FAIL_IF`: password trattenuta dietro il timeout, impronta indisponibile con
prerequisiti validi, errori, attività che prosegue dopo cancel, regressioni o
instabilità. `STOP_IF`: quarto tentativo, riarmo inatteso, dialogo bloccato o
comportamento non compreso. In questi casi interrompere la prova e fare rollback.

## Rollback

Chiudere i dialoghi, quindi:

```bash
cd /home/guido/Repository/goodix-27c6-5125_private
development/patches/polkit-fingerprint/uninstall.sh
```

Usa sudo e deve concludere con `POLKIT_UNINSTALL=PASS previous_PAM=RESTORED`
(oppure `ALREADY_ABSENT`). Rimuove i file della patch e i contatori, ripristina
esattamente la presenza originaria del PAM e ricarica le definizioni systemd.
Non cambia il servizio attivo né il sensore. Il successivo normale dialogo
Polkit torna al comportamento precedente con password; sudo/unlock/login restano
sulle configurazioni precedenti. Un file modificato dopo l'installazione viene
preservato e segnalato, senza sovrascriverlo. Il rollback resta recuperabile dal
commit della patch; non eliminare quel checkout durante la prova.

Riportare all'AI: PASS/FAIL per comportamento osservato, testo dell'eventuale
errore e punto preciso del fallimento. Non servono raccolte di log preventive;
eventuali letture mirate verranno richieste solo per spiegare un failure reale.
