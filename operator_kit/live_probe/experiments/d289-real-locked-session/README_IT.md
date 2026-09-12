# D289/01 — unlock di una sessione KDE realmente bloccata

## Scopo, differenza e rischio

D288 ha provato `kscreenlocker_greet --testing`; D289 invoca invece il metodo
D-Bus `org.freedesktop.ScreenSaver.Lock` del KWin reale e richiede la
transizione osservabile `false → true → false`. Il greeter deve essere l'unico
figlio `/usr/libexec/kscreenlocker_greet` del processo KWin che possiede il
servizio D-Bus. L'ipotesi nuova è che il MATCH già provato raggiunga lo sblocco
di una sessione davvero bloccata, non soltanto l'uscita del greeter standalone.

KWin è già in esecuzione e non può ereditare il preload D288. Un helper
`pkexec`, limitato a questo probe, sovrappone temporaneamente e read-only il PAM
privato al solo `/etc/pam.d/kde-fingerprint` nel medesimo mount namespace di
KWin. Prima del mount verifica PID/UID, `comm`, `cmdline`, cgroup utente e
namespace. Se `/proc/<pid>/exe` è leggibile deve coincidere esattamente con
`/usr/bin/kwin_wayland`; sul target può non esserlo, nel qual caso sono
obbligatori tutti gli altri segnali indipendenti. Su release, EOF,
segnale o errore smonta, verifica l'hash originale e rimuove `/run`.
`/etc/pam.d/kde` e il fallback password non vengono modificati. Non viene
scritto alcun file PAM persistente e un reboot elimina comunque il bind mount.

Durante la breve finestra dell'overlay, qualunque altro processo che invocasse
esattamente il service `kde-fingerprint` vedrebbe il PAM candidato. Il gate
richiede quindi nessun greeter preesistente, un'unica sessione target attiva e
chiude l'overlay dopo ogni singolo ciclo, prima di offrire il successivo.
Questa è una modifica runtime host e il vero lock è una Human Gate: l'AI non
esegue il comando operatore.

Il probe usa massimo tre cicli di lock e altrettanti overlay non sovrapposti,
ciascuno con un solo `pam_fprintd.so max-tries=1`, una action e un contatto.
Non esiste retry
automatico o implicito sensor-reaching. MATCH arresta subito. Dopo NO_MATCH il
solo modo sicuro per chiudere il lock reale è usare la password; soltanto dopo
il recupero e una nuova conferma testuale il kit può creare un nuovo ciclo.
Password e risposte PAM non sono acquisite o esportate.

## Prerequisiti

- branch `development`, HEAD uguale a `origin/development`, critical set
  pulito;
- sessione Plasma Wayland attiva, non bloccata, con KWin 6.7.5 target;
- installazione D285 e template dell'indice destro integri;
- target `27c6:5125` presente e nessun greeter già attivo;
- conoscere la password dell'utente e poter usare una TTY di recovery.

Prima di iniziare, salvare il lavoro aperto. Tenere presente la recovery:
`Ctrl+Alt+F3`, login dell'utente e poi, soltanto se il desktop non torna dopo la
password, `loginctl unlock-session <ID>`; questo comando forza lo sblocco e
invalida l'esito del probe, ma non modifica il sensore.

Se il report indica `D289_ROOT_OVERLAY_UNMOUNTED=false` o il post-audit segnala
un mount residuo, dopo avere recuperato la sessione eseguire una sola volta:

```bash
pkexec operator_kit/live_probe/experiments/d289-real-locked-session/root-overlay.sh --recover
```

La recovery rifiuta un contenuto montato diverso dal PAM candidato, smonta
soltanto quel mount atteso, verifica l'hash PAM host originale e rimuove il
runtime posseduto. Non rilanciare la live.

## Esecuzione manuale

Dalla Konsole della sessione grafica attiva:

```bash
operator_kit/live_probe/run.sh d289-real-locked-session --operator-run
```

Autenticare gli audit e l'helper `pkexec`, leggere limiti e rischi, quindi
digitare `BLOCCA SESSIONE`. Il kit annuncia le istruzioni prima che il terminale
diventi invisibile. Quando compare il lock reale, appoggiare una sola volta
l'indice destro e non digitare password/PIN mentre la verifica è in corso.

Se l'impronta sblocca, non fare altro. Se viene rifiutata o dopo 70 secondi lo
schermo è ancora bloccato, usare la password solo per recuperare la sessione.
Tornati in Konsole, un ulteriore ciclo è possibile soltanto digitando
`TENTATIVO 2` o `TENTATIVO 3`. Dopo errore, stato inatteso, timeout o recovery
forzata non rilanciare: conservare la capture e sottoporla a review.

Gli output sanitizzati sono in
`captures/live_probe/d289-real-locked-session_<timestamp>_<sha>/sanitized/`.
Non includono password, risposte PAM, template, pixel, PSK o protected
material. Qualunque esito non autorizza un rerun implicito.

La prima invocazione del 12 settembre 2026 sul baseline `0568742e...` è
abortita nel pre-audit prima di lock, overlay PAM, VERIFY o contatto. Il difetto
host-side del cursor journal e il gate identità KWin sono stati corretti
offline; quella invocazione non ha consumato alcun tentativo live.
