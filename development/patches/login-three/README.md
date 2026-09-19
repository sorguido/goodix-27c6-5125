# Prepared login: fino a tre contatti

Follow-up dell'overlay `login-early` attualmente presente sulla macchina.
Il vecchio overlay e la sua evidenza restano congelati. Questa patch usa il
codice canonico attuale, conservando soltanto i quattro loader storici necessari
al deployment D293. La candidate gestita usa invece i loader canonici: i due
workflow non vanno sovrapposti. Nessuna migrazione dei materiali in questa prova.

## Installazione (Utente)

Prerequisiti: Fedora 44 KDE già qualificata, overlay `login-early` ACTIVE e
integro, ramo `development` pulito con questo follow-up, SDK/RPM già previsti
in `production/README.md`. Non serve estrarre o fornire materiale del sensore.

```bash
cd "$(git rev-parse --show-toplevel)/development/patches/login-three"
./install.sh
```

Esegui come utente normale. Lo script compila senza privilegi, poi chiede `sudo`
per applicare il delta. Attendi `LOGIN_THREE_INSTALL=PASS`. Esci normalmente
dalla sessione per avere un nuovo greeter e una nuova preparazione.

Tocca solo tre file nel runtime `login-early` (libfprint, fprintd, PAM), i relativi
metadata, la regola PAM login (`max-tries=3 timeout=8`) e lo stato dell'overlay.
Salva il precedente stato in `/etc/goodix-27c6-5125/login-three-backup`.
Wrapper, drop-in, greeter, password-auth e altri consumer restano quelli presenti.
Ferma/ripristina fprintd durante la copia; non riavvia Plasma. La provenance della
candidate contiene lo SHA completo della ricetta e la base dei soli loader.

## Prova breve

Per ogni autenticazione: premi **Invio una sola volta**, appoggia e poi solleva
completamente il dito. Attendi l'esito prima del nuovo appoggio. **Massimo tre
contatti**; al riconoscimento riuscito fermati. Nessun quarto contatto o nuovo
Invio nella stessa autenticazione. Se manca un esito entro il timeout, usa la
password: non cercare di recuperare con altri appoggi.

In tre accessi separati, con nuova schermata di login:

1. Dito non registrato, poi dito registrato: deve riuscire al secondo contatto.
2. Due contatti con dito non registrato, poi quello registrato: deve riuscire al terzo.
3. Tre contatti con dito non registrato: deve terminare fingerprint e consentire la password.

Se il dito non registrato viene riconosciuto, interrompi la prova. Se una prova
fallisce, fermati e fai rollback. Un errore di acquisizione/protocollo può
terminare prima di tre contatti: non è un normale NO MATCH da ritentare.

**PASS_IF:** secondo/terzo contatto possono riuscire dopo NO MATCH; tre NO MATCH
lasciano la password; nessun quarto tentativo. Password e normale sudo non
mostrano regressioni. Il NO MATCH è notificato dopo il rilascio completo; il
MATCH resta immediato. Il limite resta 8 s per tentativo, senza timer riavviati
per errori o retry nascosti.

**FAIL_IF:** dopo un NO MATCH la sessione risulta indisponibile, il secondo/terzo
contatto non reagisce, oppure il fallback/password/sudo regredisce.

**STOP_IF:** errore di installazione/prerequisiti, timeout, errore USB/sessione,
riconoscimento inatteso, più di tre contatti richiesti o comportamento anomalo.
Non ripetere una serie fallita.

## Rollback

Da una sessione accessibile con password:

```bash
cd "$(git rev-parse --show-toplevel)/development/patches/login-three"
./rollback.sh
```

Chiede `sudo`; ripristina byte, permessi e contesti SELinux dei file precedenti,
lo stato originale dell'overlay e lo stato precedente del servizio. Attendi
`LOGIN_THREE_ROLLBACK=PASS`, poi verifica il normale login/password. Rimuove il
backup solo dopo il ripristino riuscito. Drift locale o backup alterato causano
STOP; un rollback interrotto resta ripetibile. Prima di usare il rollback
storico di `login-early`, rimuovi sempre questo delta. Dopo PASS conserva la patch.

Riporta solo quale prova hai fatto, gli esiti dei contatti 1/2/3, l'eventuale
messaggio e il punto di arresto. Nessun log richiesto se le prove passano.
