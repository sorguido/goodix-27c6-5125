# D288/01 — KScreenLocker active-user con PAM privato

## Scopo e rischio

Questo probe verifica il primo consumer desktop reale dopo D287: il greeter
Fedora `/usr/libexec/kscreenlocker_greet --testing` viene avviato direttamente
dalla sessione Plasma attiva. Una piccola libreria `LD_PRELOAD` intercetta
soltanto `pam_start("kde-fingerprint", ...)` e lo indirizza a un confdir
privato; i service PAM `kde` (password) e `kde-smartcard` restano invariati.
Nessun file sotto `/etc/pam.d` viene scritto o montato.

La finestra è lock-like fullscreen su Wayland e prende il focus. Non digitare
password, PIN o altre credenziali durante il probe. `MATCH` deve produrre
insieme telemetria SIGFM, marker `Unlocked` ed exit zero. Un `NO_MATCH` chiude
quel greeter e offre un nuovo processo solo dopo una conferma testuale; massimo
tre action/contatti totali. Qualunque altro esito termina fail-closed.

Il probe usa il runtime D285 già installato e due audit root-only D286 tramite
`pkexec`; non installa o aggiorna componenti. Non modifica firmware, PSK, OTP,
factory data o configurazione persistente del sensore. Telemetria
`persistent=0` riguarda soltanto le famiglie note.

## Prerequisiti

- branch `development`, HEAD uguale a `origin/development`, worktree critical
  pulito;
- sessione Plasma Wayland attiva e target `27c6:5125` disponibile;
- installazione persistente D285 integra e template ownership-pinned;
- indice destro registrato disponibile;
- nessun altro greeter KScreenLocker attivo.

## Esecuzione manuale

Dalla Konsole della sessione grafica attiva:

```bash
operator_kit/live_probe/run.sh d288-active-user-kscreenlocker --operator-run
```

Autenticare i soli audit `pkexec` quando richiesto, leggere i limiti e digitare
`INDICE DESTRO`. Quando compare il greeter, muovere il puntatore per mostrare
il form e appoggiare una sola volta l'indice destro. Non digitare credenziali.
Se viene osservato `NO_MATCH`, tornati al terminale digitare `TENTATIVO 2` o
`TENTATIVO 3` soltanto se si vuole consumare il successivo slot esplicito.

Su `MATCH` non eseguire altri contatti. Su errore, timeout, finestra inattesa,
prompt ambiguo o richiesta di credenziali interrompere con `Ctrl-C` e non
rilanciare: cleanup e post-audit vengono comunque tentati, poi la capture deve
essere sottoposta a review indipendente.

Gli output sanitizzati sono in
`captures/live_probe/d288-active-user-kscreenlocker_<timestamp>_<sha>/sanitized/`.
Non contengono template, pixel, PSK o risposte PAM. Una run, qualunque sia
l'esito, non autorizza un rerun automatico o implicito.
