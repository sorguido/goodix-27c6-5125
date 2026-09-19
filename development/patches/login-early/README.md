# Login Goodix: preparazione prima della schermata

Candidate **development**, ricetta identificata dallo SHA completo di `git rev-parse HEAD`,
registrato in `PROVENANCE` e nel journal. Scopo: Invio → dito immediato, senza
ricalibrazione dopo Invio. Prima prova con dito lontano fino alla schermata pronta.
Il dito già appoggiato prima della schermata è fuori da questa accettazione.
**HUMAN_REQUIRED: installazione, sudo e prova fisica spettano all'Utente.**

Dal desktop, con password funzionante, baseline D293 e nessuna autenticazione in corso,
apri un terminale nella root di questo clone su `development`:

```bash
cd "$(git rev-parse --show-toplevel)/development/patches/login-early"
./install.sh
```

Non anteporre sudo: lo script compila da utente e chiede sudo solo per applicare.
Servono gli strumenti di build già usati dal progetto, SDK Flatpak 25.08, RPM
OpenCV locali e rete per scaricare due RPM **di header**, senza installarli.
Per usare copie già scaricate: `GOODIX_LOGIN_HEADER_RPMS=/directory/rpm ./install.sh`.
Lo script rifiuta baseline diversa, override precedenti o worktree sporco.
Attendi `EARLY_LOGIN_INSTALL=PASS`; poi **spegni e riaccendi**.

1. Tieni il dito lontano. Attendi la schermata Plasma completa e il campo password usabile.
2. Entro due minuti, **premi Invio una sola volta e appoggia subito il dito registrato**,
   senza attendere deliberatamente: meno di un secondo va bene.
3. Fermati al primo riconoscimento. Se non riesce, usa la password e fai rollback;
   non premere nuovamente Invio per ripetere la prova fingerprint.
4. Dopo PASS, esci dalla sessione e prova il normale login con password, tenendo
   il dito lontano; l'eventuale attesa fingerprint è limitata a 8 s. Dal desktop,
   esegui `sudo -k`, poi `sudo true`: prova una sola autenticazione fingerprint;
   se fallisce, usa password e rollback.
5. Per questa prima candidate verifica anche il ripristino richiesto: esegui il
   rollback sotto, poi riavvia. Non ripetere il cold test per raccogliere altre prove.

**PASS_IF:** dito immediato → riconoscimento → desktop; funzionano anche password
 e successiva autenticazione sudo. L'assenza di seconda calibrazione è vincolata
 dal codice e coperta dai test offline; l'esito hardware resta da osservare.
**FAIL_IF:** nessun riconoscimento, serve ritardare il dito, attesa anomala,
 password o sudo regrediscono. Rollback.
**STOP_IF:** errori di installazione, schermata assente, impronta indisponibile,
 sospensione/rimozione del dispositivo, oppure più di due minuti di attesa prima
 di Invio. Usa la password e fai rollback, senza retry o riarmo manuale.

```bash
./rollback.sh
```

Da TTY, se necessario: accedi con password, raggiungi la stessa directory e
lancia `./rollback.sh`. Attendi `EARLY_LOGIN_ROLLBACK=PASS previous=D293 PAM=vendor`;
riavvia e verifica il normale accesso con password. Il rollback rimuove solo
l'overlay, ripristina ExecStart e stato del servizio precedenti e verifica gli
hash D293. Se rileva modifiche successive, si ferma senza sovrascriverle.

Effetti: directory `/usr/local/lib64/goodix-27c6-5125/login-early`, wrapper
`/usr/local/sbin/goodix-login-early-fprintd`, drop-in fprintd `96-goodix-login-early.conf`,
`/etc/pam.d/plasmalogin`, drop-in `/etc/systemd/user/plasma-login.service.d/96-goodix-login-early.conf`
e stato `/etc/goodix-27c6-5125/login-early.json`. Etichette SELinux dei soli nuovi
eseguibili copiate dagli originali; nessuna policy modificata. Il nuovo avvio del
greeter si applica al prossimo boot; nessuna sessione grafica viene riavviata dallo script.
Firmware, factory state, PAM sudo e file D293 non sono modificati.

Riporta soltanto: esito, comportamento dopo Invio, eventuale messaggio e punto
preciso del problema, risultati password/sudo/rollback. Log mirati solo se occorrono
dopo un failure. Un solo tentativo cold-login è l'eccezione esplicita richiesta
per questa prova; nessun retry automatico o nuova campagna.
