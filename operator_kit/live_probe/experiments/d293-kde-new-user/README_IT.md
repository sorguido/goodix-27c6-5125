# D293/04 — corrective KDE/new-user, live bloccata su R7

## Stato corrente

```text
D293_04_OPERATOR_KIT=BLOCKED_OFFLINE
D293_04_LIVE_CAPABLE=false
D293_04_BLOCKER=R7_GUI_SESSION_BUDGET_NOT_ENFORCED_BEFORE_EXTRA_ENROLLSTART
```

**Non eseguire `prepare.sh` né tentare l’operator-run.** Il launcher e lo
stesso `prepare.sh` rifiutano la live prima di build, `pkexec`, deployment,
account, mount o accesso al sensore.

Il corrective ha chiuso offline i difetti R1–R6 e la parte fail-closed di R7,
ma ha confermato un limite strutturale: il KCM Users standard non offre al kit
un hook con cui autorizzare esattamente un solo `EnrollStart` prima che
l’action raggiunga libfprint. Chiudere il KCM dopo la prima enrollment e
contare le epoch nel journal rileva un’action UI extra soltanto dopo il suo
avvio. Questo è accounting retrospettivo, non un fence tecnico preventivo.
Non viene mascherato come enforcement.

Non si introducono un proxy fprintd, una policy driver specifica del test, un
monitor race-based o un contatore globale del daemon: cambierebbero metodo e
profilo di rischio e interferirebbero con le normali action native che D293
deve supportare. Serve una decisione separata prima di riabilitare la live.

## Correttivi chiusi offline

- R1: il flusso richiede un dito fisico consapevolmente non registrato su altri
  account; il nome del dito nella GUI non prova l’identità fisica. Un duplicato
  è classificato separatamente, chiude il KCM, conserva IDENTIFY e arresta senza
  retry o enrollment nascosta.
- R2: il nuovo account resta standard. Non esegue `journalctl` o `systemctl`.
  Il supervisore root raccoglie soltanto marker `GOODIX_PRODUCTION_EPOCH_AUDIT`
  per step fissi e pubblica record normalizzati; stato e materiali privati
  restano non leggibili dal test user.
- R3: il formato macchina è una riga MESSAGE normalizzata e univoca. La capture
  contiene `runtime-audit.env` e `runtime-provenance.env`; il classifier non
  legge `/run` e continua a funzionare dopo recovery o reboot.
- R4: ogni domanda termina con newline ed è flushata dal sanitizer prima del
  `read`. Errori e telemetria parziale riportano fase, motivo, codice e cleanup
  pending senza password o materiale protetto.
- R5: dopo enrollment l’operatore preme il controllo finale della UI, chiude
  normalmente System Settings e il payload attende l’uscita del processo prima
  di VERIFY. Per il delete il KCM viene aperto di nuovo e chiuso di nuovo. Non
  si usa restart del daemon come scorciatoia.
- R6: rollback serializzato con lock e risultato atomico; la recovery propaga
  il fallimento, aspetta la fine reale del supervisore, verifica l’identità
  UID/GID/home attribuita alla run, non rimuove un contenitore montato, conserva
  capture per-run ed è idempotente dopo successo.
- R7 parziale: output `fprintd-list`, marker e campi audit sono validati con
  cardinalità e tipo; errore comando non equivale a zero; la telemetria parziale
  contiene solo conteggi osservati e dichiara `OBSERVATION_COMPLETE=false`.
  Ogni VERIFY è precontrollata contro action/contact budget e non esiste un
  quarto tentativo. Rimane il blocker preventivo sull’action UI extra.

## Sequenza progettata, non autorizzata alla live

La sequenza corretta resta documentata per review e test comportamentale:

1. l’utente preesistente predisporrebbe il runtime transiente e solo dopo
   creerebbe il normale account `d293-phase-b-test` tramite KDE;
2. si attenderebbe il valore esatto
   `D293_04_PHASE=READY_FOR_NEW_USER`, non la sola presenza di `public.env`;
3. il nuovo utente sceglierebbe un solo dito fisico non già registrato;
4. il duplicate-check IDENTIFY resterebbe abilitato; un duplicato causerebbe
   stop distinto e nessun retry;
5. dopo una enrollment riuscita si userebbe il pulsante finale e si chiuderebbe
   il KCM; solo dopo si avvierebbero fino a tre VERIFY, stop al primo MATCH;
6. il KCM sarebbe riaperto solo per cancellare l’impronta e poi richiuso;
7. dopo logout, `recover.sh` trasferirebbe la sola capture per-run all’utente
   originale e rimuoverebbe l’account soltanto con identità, storage, processi e
   mount verificati.

Budget rimasti invariati come limite di progetto del gate:

```text
MAX_ACTIONS=5
MAX_CONTACTS=24
MAX_RETRIES_TRANSPORT=0
MAX_VERIFY_START=3
STOP_ON_FIRST_MATCH=true
FOURTH_ATTEMPT_ALLOWED=false
ENROLLMENT_BIOMETRIC_REPEAT_BUDGET_MAX=20
```

Questi valori non rendono la live pronta finché manca il fence pre-action R7.

## Capture e recovery

Il design usa una directory distinta per ogni run:

```text
/var/tmp/goodix-d293-04-captures/<run-id>/capture/
```

`run.env` resta root-only perché contiene il digest interno usato per provare
la conservazione del principal; non fa parte della capture consegnabile. La
capture sanitizzata contiene solo provenance pubblica, contatori, marker
whitelistati e booleani di isolamento, mai password, immagini o template.

`recover.sh` resta disponibile esclusivamente per recuperare una precedente
run già predisposta prima del blocco o una recovery interrotta. Va avviato
dall’utente originale dopo il logout del test user:

```bash
operator_kit/live_probe/experiments/d293-kde-new-user/recover.sh
```

Non indovina l’identità dal solo nome: richiede un unico metadata record
root-owned attribuito al chiamante. Una seconda recovery dopo successo
restituisce PASS idempotente e non cancella la capture.

## Scope delle prove offline

I test comportamentali usano directory temporanee e comandi mock isolati per
attraversare gli script reali: prompt prima dell’input, duplicate stop,
MATCH/NO_MATCH, parser di `fprintd-list`, marker, telemetria parziale e recovery
failure/idempotenza. Non creano account, non montano filesystem, non avviano
systemd/fprintd, non leggono journal o template autentici e non raggiungono USB.
Non provano ACL/SELinux o comportamento KDE/PolicyKit del laptop reale.
