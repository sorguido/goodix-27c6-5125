# Prova temporanea: sollevare e riappoggiare nella stessa verifica

**STORICO — esperimento eseguito il 19 settembre 2026. Non reinstallare per
ripeterlo: lift/recontact nella prima action non ha prodotto IRQ2 o immagine
per il matcher. Non è una candidate production.** Il manuale tecnico e la
sezione post-live di `RESOLUTION_REVIEW_2026-09-19.md` descrivono la decisione
corrente. Le istruzioni originarie e il rollback restano preservati qui sotto.

**HUMAN_REQUIRED — installazione, sudo e prova sul sensore spettano all'Utente.**
Questa patch prepara un singolo esperimento; non è la soluzione del login.
Serve a osservare se un nuovo contatto riattiva la rilevazione nella stessa
action, senza nuovo Invio, riarmo, retry, reset/reopen/reconnect o D2.

## Prima di iniziare

Target: questo host Fedora 44 KDE, runtime D293
`e61fce313794922a2dab156a1b38a8ddc5837f19`, fprintd 1.94.5-5.fc44.
Usare il clone privato sul branch `development`, pulito, contenente questa
directory. Il preparatore usa sorgenti fissate a
`c0e13ff5f78ac32403a753446dcbc44aa7f30556` più la patch accanto; conserva i
quattro file del loader materiali D293. Non migra materiali, firmware o template.
Il commit completo della ricetta, le sorgenti e gli hash della build sono
registrati nel runtime installato e nel journal: provenance, non autorizzazione.

Devono essere già disponibili SDK Freedesktop 25.08, tool di build e i cinque
RPM OpenCV pin in `GoodixArtifacts/opencv-4.13-rpms/`, come nella build production.
Conoscere la password e avere accesso al terminale dopo login con password.
Nessun aggiornamento di pacchetti/configurazione tra installazione e rollback.
Non eseguire enrollment o altre prove fingerprint durante questo test.

## Installazione

Dal terminale aperto nel clone:

```bash
cd "$(git rev-parse --show-toplevel)"
./development/patches/login-same-action/install.sh
```

Lo script compila senza privilegi e poi chiede `sudo` per installare. Attendere
`SAME_ACTION_INSTALL=PASS` (oppure `ALREADY_ACTIVE`). Se fallisce, **STOP**:
non avviare la prova; riportare l'errore. La transazione tenta il ripristino.

Effetti limitati: nuovo runtime e wrapper `login-same-action`, drop-in systemd
`96-goodix-login-same-action.conf`, stato di rollback e override
`/etc/pam.d/plasmalogin`. Il runtime D293 e il PAM vendor restano intatti.
L'override mantiene il fallback password e imposta **una sola verifica, 20 s**.
Il servizio viene fermato per il cambio e torna allo stato attivo/inattivo
precedente. Lo script verifica l'ExecStart effettivo prima di dichiarare PASS.

## Prova al login — una sola volta

1. Spegni completamente il computer e riaccendilo. Tieni il dito lontano
   fino alla schermata di login.
2. Premi **Invio una sola volta** e appoggia subito il dito registrato.
3. Se il login riesce, fermati: non fare altri contatti.
4. Se dopo circa **3 secondi** la stessa verifica è ancora in attesa,
   solleva completamente il dito per circa **1 secondo**, poi riappoggialo.
   **Non premere di nuovo Invio.**
5. Attendi il risultato, entro 20 secondi dall'avvio. Non fare un terzo contatto.
   Se durante il sollevamento compare un risultato o torna la password,
   fermati subito: non riappoggiare il dito su una verifica già terminata.
6. Se necessario entra con la password, poi esegui il rollback qui sotto.

**PASS_IF:** arriva MATCH dopo il riappoggio, nella stessa verifica. Un MATCH
già al primo contatto è un esito positivo del controllo immediato: fermarsi e
riportarlo, senza ripetere la prova per cercare un timeout.

**FAIL_IF:** dopo il riappoggio la stessa verifica continua ad attendere fino
al timeout. Il journal dovrà confermare che era arrivata a `waiting_irq2`:
solo allora il risultato smentisce il semplice evento iniziale perso.

**STOP_IF:** errore, mancato riconoscimento, ritorno alla password, risposta
durante il sollevamento, comportamento anomalo o raggiungimento del timeout.
Niente nuovo Invio per avviare un altro tentativo. Un errore prima di
`waiting_irq2` rende la prova **inconclusiva**, non prova un problema firmware.

Riporta soltanto: risultato/messaggio esatto e se la reazione è avvenuta al
primo contatto, durante il sollevamento o dopo il riappoggio. Un mancato match
può comunque indicare acquisizione; sarà verificato sui log già prodotti.
Non servono nuove capture, screenshot o raccolte automatiche.

## Rollback obbligatorio anche dopo PASS

È un deployment espressamente temporaneo. Dal terminale del clone:

```bash
./development/patches/login-same-action/rollback.sh
```

Richiede `sudo`; usare la password e non fare ulteriori prove fingerprint.
Attendere `SAME_ACTION_ROLLBACK=PASS` (oppure `ALREADY_ABSENT`). Vengono rimossi
soltanto i file/symlink creati dalla patch, incluso l'override PAM; tornano
ExecStart D293, PAM vendor (`max-tries=3 timeout=45`) e stato del servizio
precedente. L'integrità del precedente runtime e la definizione del servizio
sono verificate. Firmware, materiali protetti, template e Windows non sono
modificati dal deployment. In caso di file cambiati, il rollback si ferma
senza cancellarli: riportare l'errore, non rimuoverli manualmente.

## Confine tecnico e limiti dell'evidenza

La patch viene applicata solo a una copia temporanea dei sorgenti: il driver
production nel repository non cambia. Nei profili VERIFY/IDENTIFY accetta
solo il flag baseline aggiuntivo osservato `0x003f`, mantiene soglie e numero
di sample, attende sia risposta 82 sia ACK anche nell'ordine inverso, e
consuma al massimo due eventi `32/IRQ0080/flags0` durante il primo arm/wait.
Non invia alcun comando aggiuntivo per questi eventi. Gli altri frame restano
fail-closed. ENROLL conserva il comportamento precedente.

Una sola action PAM, massimo una acquisizione da IRQ2, zero riarmo/retry;
i due contatti fisici sono quelli espressamente richiesti dall'Utente per
questo esperimento (§8.2), non una serie di tre verifiche. Un contatto senza
IRQ non può essere contato dal software: non si pretende di misurarlo.
I marker `GOODIX_SAME_ACTION` correlano generazione, fase, flag ed eventi;
non registrano immagini o valori grezzi dei canali.

Se manca ancora IRQ2 dopo il nuovo contatto, non si ripete cambiando pacing:
si riesamina calibrazione/arming. Anche un PASS supporta la spiegazione della
transizione persa senza provarla in esclusiva: sollevare il dito potrebbe
modificare uno stato interno non osservato. Questa prova non misura FAR/FRR,
non qualifica PRE-HELD e non implementa inizializzazione prima di Invio.
