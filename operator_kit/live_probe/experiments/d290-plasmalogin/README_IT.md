# D290/01 — login Plasma reale con fingerprint one-shot

> **HISTORICAL_ONLY — DO_NOT_RERUN.** Questo esperimento è preservato per
> audit e test offline, ma `LIVE_CAPABLE=false`. Anche il successivo micro-kit
> persistente è ora storico: D290/01 è chiuso dalla prova manuale diretta
> riuscita del 12 settembre 2026 e non richiede ulteriori test.

## Cosa prova e cosa cambia

D289 ha provato il MATCH fino allo sblocco di una sessione KDE già esistente.
D290 attraversa il consumer successivo: il daemon reale Plasma Login Manager
6.7.5, il service PAM `plasmalogin` e la creazione di una nuova sessione
Wayland. Non è SDDM classico: sul target il display manager attivo è il fork
KDE `plasmalogin.service`.

Rispetto all'ultimo tentativo cambia realmente il consumer e il lifecycle:
il kit parte da una TTY separata, che sopravvive al logout della sessione
grafica, e sovrappone temporaneamente il solo
`/usr/lib/pam.d/plasmalogin`. La nuova ipotesi è che una VERIFY Goodix con
SIGFM MATCH, avviata dal greeter di login reale, consenta a plasmalogin di
creare una nuova sessione utente. Se fallisce con NO_MATCH, D290 non offre un
secondo tentativo: rilascia prima l'overlay, conclude gli audit e solo allora
consente il recupero password. Un errore diverso arresta la run e richiede
review della capture, non un rerun.

Il PAM candidato conserva integralmente account/password/session e il fallback
`password-auth` del file Fedora, aggiungendo una sola riga fingerprint
`sufficient` con `max-tries=1 timeout=45`. Il login non parte passivamente:
il sorgente upstream v6.7.5 mostra che il greeter invia username e contenuto
del campo password soltanto quando si preme il pulsante/Invio; per avviare il
fingerprint si usa quindi un solo Invio col campo vuoto.

## Rischio e limiti

Questa è una Human Gate: logout, overlay PAM runtime, `pkexec`, greeter reale e
VERIFY raggiungono host e sensore. L'AI ha preparato e verificato soltanto il
percorso offline e non esegue il comando.

La run consente esattamente:

- una pressione Invio che avvia una sola transazione PAM;
- una action VERIFY e un solo contatto fisico;
- zero retry automatici o impliciti;
- un solo bind mount read-only sul service `plasmalogin`;
- nessuna scrittura PAM persistente, nessuna modifica authselect e nessun
  comando sensore persistente noto.

Il terminale TTY deve restare aperto. Non chiuderlo, non spegnere e non
riavviare durante la run. La password resta il recovery, ma non va digitata
finché il terminale non mostra che overlay, PAM host e runtime sono stati
ripristinati e il post-audit è concluso. Password, PIN, template, immagini e
protected material non vengono acquisiti nella capture.

## Prerequisiti

- branch `development`, HEAD uguale a `origin/development` e live-critical set
  pulito;
- installazione D285/D286 integra e indice destro già registrato;
- una sola sessione Plasma Wayland dell'utente su `tty2`;
- display manager `plasmalogin.service` 6.7.5 attivo;
- target Goodix `27c6:5125` presente una sola volta;
- password dell'utente conosciuta e salvato tutto il lavoro aperto.

## Procedura storica — non eseguire

1. Dalla sessione grafica premere `Ctrl+Alt+F3` ed eseguire il login testuale
   dello stesso utente. Verificare che il prompt sia sulla TTY 3.
2. Dalla root del repository eseguire un solo comando:

```bash
operator_kit/live_probe/run.sh d290-plasmalogin --operator-run
```

3. Autenticare i prompt `pkexec`, leggere i limiti e digitare esattamente
   `PREPARA LOGIN D290`.

L'autenticazione privilegiata successiva usa la controlling TTY in foreground;
la password non deve comparire a schermo e non passa nel log o nella FIFO di
controllo. Se appare in chiaro, interrompere e non proseguire al logout.

Prima della conferma, il pre-audit identifica la sessione tty2 anche quando
logind la marca `online` perché la TTY 3 è foreground. Mostra count, ID, TTY,
service, type, class e state; cardinalità diversa da uno è uno stop.
4. Quando compaiono le istruzioni numerate, premere `Ctrl+Alt+F2`, fare logout
   dal menu Plasma e attendere il login manager.
5. Selezionare l'utente, cancellare completamente il campo password, premere
   Invio una sola volta e appoggiare una sola volta l'indice destro. Non
   digitare password/PIN e non ripetere il contatto.
6. Dopo l'ingresso nel nuovo desktop oppure dopo il messaggio `Login Failed`,
   tornare subito alla TTY 3 con `Ctrl+Alt+F3`.
7. Verificare i marker
   `D290_ROOT_OVERLAY_UNMOUNTED=true`,
   `D290_ROOT_HOST_PAM_RESTORED=true` e
   `D290_ROOT_RUNTIME_REMOVED=true`; quindi digitare `CHIUDI D290` e
   autenticare l'eventuale post-audit `pkexec`.
8. Attendere `LIVE_PROBE_RESULT=PASS`. Se l'esito fingerprint era NO_MATCH,
   soltanto ora tornare con `Ctrl+Alt+F2` e usare la password. Non ripetere il
   fingerprint.

Qualunque errore, timeout, marker false, cardinalità inattesa o risultato
diverso da PASS è uno stop: recuperare la sessione con password solo dopo il
rilascio dell'overlay, conservare la capture e non rilanciare.

`Ctrl+C`, EOF o morte del processo parent fanno chiudere il canale e attivano
il cleanup del helper. Se i tre marker di ripristino non sono visibili, non
usare il login grafico: applicare la recovery seguente dalla TTY.

Gli output sanitizzati saranno in
`captures/live_probe/d290-plasmalogin_<timestamp>_<sha>/sanitized/`.

## Recovery overlay

Se il terminale è stato perso e `/usr/lib/pam.d/plasmalogin` risulta ancora un
mountpoint, passare a una TTY, fare login e dalla root del repository eseguire
una sola volta:

```bash
pkexec operator_kit/live_probe/experiments/d290-plasmalogin/root-overlay.sh --recover
```

La recovery rifiuta contenuti diversi dal candidato hash-pinned, smonta solo
il mount atteso, verifica il file host originale e rimuove il runtime D290.
Dopo la recovery usare la password e sottoporre gli output a review; non
rilanciare la live.
