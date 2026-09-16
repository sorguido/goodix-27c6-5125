# D293/04 — gate KDE/new-user nativo

## Stato

```text
D293_04_OPERATOR_KIT=READY_OFFLINE_HUMAN_GATE_PENDING
D293_04_LIVE_CAPABLE=true
R7_METHOD_DECISION=USER_APPROVED_NATIVE_GUI_OPERATOR_PROTOCOL
GUI_OPERATION_COUNT_CONTROL=OPERATOR_PROTOCOL
GUI_SESSION_HARD_CAP_REQUIRED=false
PER_ACTION_TECHNICAL_FENCES=UNCHANGED
VERIFY_SERIES_CONTROL=SCRIPT_BOUNDED
RUN_TOTALS_CHECK=OBSERVED_PROTOCOL_BOUNDS
EXTRA_MANUAL_UI_ACTION=PROTOCOL_DEVIATION_STOP
```

Il kit è chiuso offline, ma non è ancora stato eseguito sul laptop reale. La
live, l’accesso USB, il deployment transiente, l’account e i mount sono un
Human Gate: li esegue soltanto l’Utente seguendo questa procedura.

La decisione R7 non introduce un freno artificiale nel driver. Una sola
enrollment è una regola esplicita del collaudo nativo KDE. I limiti tecnici
della singola operazione restano invariati; le VERIFY sono avviate dallo script
al massimo tre volte e terminano al primo MATCH. I totali 5 action e 24
contatti sono limiti di accettazione osservati della sequenza pianificata, non
un hard-cap impenetrabile su ogni clic della GUI. Il campo legacy del common
harness `MAX_ACTIONS_ENFORCED=5` va letto insieme a
`MAX_ACTIONS_ENFORCEMENT_SCOPE=OBSERVED_PROTOCOL_ACCEPTANCE`.

## Prerequisiti e rischio

- Fedora KDE target con un solo Goodix `27c6:5125`, branch `development`
  pulito e allineato a `origin/development`.
- Nessun altro client fingerprint attivo; non cambiare branch o worktree
  durante la run.
- La sessione Plasma dell’utente originale può restare aperta, ma va chiuso
  System Settings e non devono restare consumer fingerprint.
- Scegliere un dito fisico non registrato da alcun account. Il nome scelto
  nella GUI non prova che il dito sia libero: il duplicate-check resta attivo.
- Nessuna password viene digitata nei log o nel terminale del payload. Le
  richieste KDE/PolicyKit previste vanno soddisfatte soltanto nella finestra
  grafica di autenticazione.
- Non cancellare un’impronta preesistente per far riuscire il test; non avviare
  un secondo enrollment per “riprovare”.

Il runtime è transiente e factory-preserving, ma raggiunge il sensore durante
enrollment e VERIFY. Nessun flash, IAP, provisioning, OTP o PSK è previsto.

## 1. Predisposizione — sessione dell’utente originale

Dalla root pulita del repository eseguire manualmente:

```bash
operator_kit/live_probe/experiments/d293-kde-new-user/prepare.sh
```

`prepare.sh` verifica branch/HEAD, pacchetti target, critical set, assenza di
runtime concorrenti, cardinalità USB e candidate hash; poi la richiesta
PolicyKit installa soltanto il runtime transiente. Il supervisore root, non
fprintd sotto `ProtectSystem=strict`, pubblica il marker sanitizzato legato al
wrapper realmente avviato soltanto dopo avere verificato `MainPID`, executable
di fprintd e mapping esclusivo della candidate `libfprint-2.so*`. PID, maps,
environment e journal raw restano privati. La base capture storica viene
creata o validata `root:root` `0711` prima della nuova directory per-run; le run
precedenti non vengono cancellate.

Solo dopo il PASS di preparazione aprire **Impostazioni di sistema → Utenti** e
creare il normale account locale `d293-phase-b-test`, senza enrollment
dall’utente originale. Attendere il valore esatto, non la sola esistenza del
file:

```bash
grep -Fx D293_04_PHASE=READY_FOR_NEW_USER /run/goodix-d293-04-public/public.env
```

## 2. Gate — vera sessione Plasma del nuovo utente

Entrare in una sessione Plasma del nuovo account. Leggere il capture root
pubblico e avviare una sola volta il common launcher dal mount read-only:

```bash
capture_root=$(sed -n 's/^D293_04_CAPTURE_ROOT=//p' /run/goodix-d293-04-public/public.env)
/run/goodix-d293-04-public/repo/operator_kit/live_probe/run.sh \
  d293-kde-new-user --operator-run --capture-root "$capture_root"
```

Quando richiesto, digitare `AVVIA D293 KDE`. Nel KCM Users:

1. verificare che il lettore sia visibile;
2. avviare **una sola enrollment** con il dito fisico scelto;
3. se compare un duplicato, dichiararlo al prompt, chiudere normalmente il KCM
   e fermarsi: non cambiare dito e non ritentare;
4. dopo il completamento usare il pulsante finale e chiudere l’intera finestra
   System Settings;
5. seguire fino a tre VERIFY fisiche indipendenti; il kit si ferma al primo
   MATCH e non offre una quarta prova;
6. quando il KCM viene riaperto, cancellare soltanto l’impronta appena creata,
   completare e chiudere normalmente la finestra.

Una action GUI ulteriore, un conteggio ambiguo, un errore tecnico o un prompt
interrotto è una deviazione terminale: non proseguire con altre acquisizioni.
Conservare l’output e passare alla recovery.

La capture sanitizzata è per-run:

```text
/var/tmp/goodix-d293-04-captures/<run-id>/capture/
```

`run.env` e la storia di rollback restano root-only; capture e report non
contengono password, immagini, template o materiale protetto.

## 3. Recovery — di nuovo dall’utente originale

Uscire completamente dalla sessione del test user. Dalla sessione originale:

```bash
operator_kit/live_probe/experiments/d293-kde-new-user/recover.sh
```

La recovery arresta il supervisore, ripristina il runtime, verifica digest e
stato, smonta il repository, trasferisce la capture e rimuove l’account solo
con identità UID/GID/home attribuita. Se restano template, processi o mount,
fallisce chiusa e conserva la run: correggere esclusivamente la condizione
indicata e rilanciare `recover.sh`. Un FAIL precedente resta nella history;
un’incoerenza del principal è sticky e non viene cancellata da un retry.

La seconda recovery dopo un PASS è idempotente. `FINAL_RECOVERY=PASS` viene
pubblicato soltanto dopo cleanup finale; la capture resta disponibile.

## Limiti delle prove offline

Le regressioni attraversano gli script e le funzioni reali con soli effetti
esterni simulati in directory temporanee, inclusi PID/executable/maps e failure
sticky di digest/GID recovery. Non provano la sandbox systemd,
PolicyKit/KDE, ACL, mount, account, journal o USB reali. Sul target è stato
osservato read-only `ProtectSystem=strict` senza write exception per il path
pubblico; il nuovo wrapper non vi scrive. La prima esecuzione resta quindi un
Human Gate e potrà produrre nuova evidenza target, non un PASS anticipato.
