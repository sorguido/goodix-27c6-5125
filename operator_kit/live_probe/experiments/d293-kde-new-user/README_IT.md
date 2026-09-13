# D293/04 — nuovo utente KDE e fprintd standard

Questo kit prepara il vero Human Gate della Phase B. Non modifica PAM o file
package-owned e non installa un package. Costruisce la candidate con
production/build.sh, la espone transitoriamente a fprintd sotto /run, richiede
la creazione successiva di un normale utente locale e usa soltanto
**Impostazioni di sistema → Utenti** per enrollment e cancellazione.

Il test live è eseguito fisicamente dall'Utente. L'AI non deve eseguire questi
comandi.

## Riesame metodologico

1. D291 verificava più serie sul principal già installato tramite un kit CLI.
   D293/04 costruisce la source-of-truth corrente, la attiva senza persistenza,
   crea un account dopo il deployment e attraversa il KCM Users in una vera
   sessione Plasma di quel nuovo account.
2. La nuova ipotesi è che il driver resti device-wide mentre fprintd/KDE
   risolvono correttamente il nuovo principal, mantengono separato il template
   preesistente e usano VerifyStart(any) senza configurazione per-utente.
3. Se il test fallisce, non si ripete automaticamente: il kit ripristina il
   runtime, conserva la capture sanitizzata e il passo successivo dipende dalla
   fase precisa (discovery/KCM, PolicyKit, IDENTIFY→ENROLL, storage, verify o
   cleanup). Un fallimento ripetuto nello stesso punto richiede replan.

## Scope deliberatamente minimo

- un nuovo utente locale standard: d293-phase-b-test;
- una sola impronta gestita esclusivamente dal KCM;
- enrollment con fino a 20 contatti biometrici più l'eventuale contatto
  IDENTIFY di duplicate-check;
- VerifyStart(any) con massimo tre invocazioni/contatti, stop al primo MATCH;
- cancellazione della sola impronta dal KCM;
- confronto root-only aggregato di contenuto e metadata del namespace fprintd
  dell'utente preesistente; viene esportato soltanto il booleano;
- rollback del runtime anche su signal, failure o timeout.

Due dita, delete singolo/re-enroll, rename/name-reuse e reboot restano B5.

## Prerequisiti e stop immediati

- Fedora 44 KDE/Plasma 6.7.5, branch development;
- HEAD uguale a origin/development e live-critical set pulito;
- esattamente un Goodix 27c6:5125 in sysfs;
- runtime D285/D286 integro e nessun consumer fprintd concorrente;
- sessione Plasma/Wayland dell'utente preesistente per la preparazione;
- possibilità per l'operatore di autorizzare pkexec;
- nessun account o storage preesistente chiamato d293-phase-b-test.

Fermarsi su drift, password/template mostrati nel terminale, quarto tentativo,
consumer concorrente, timeout o cleanup non PASS. Il kit non legge né esporta
PSK/materiali runtime; il daemon usa il set protetto già installato.

## Procedura

### 1. Preparazione dall'utente preesistente

Dalla root del repository:

    operator_kit/live_probe/experiments/d293-kde-new-user/prepare.sh

La build è unprivileged e network-unshared. pkexec serve soltanto a creare
runtime/drop-in transitori sotto /run e ad avviare un supervisore bounded. Il
preflight D285/D286 avviene prima dell'override.

Solo dopo D293_04_PREPARE=PASS, aprire **Impostazioni di sistema → Utenti** e
creare il normale utente d293-phase-b-test. La password viene inserita nella
UI KDE e non nel kit. Non registrare ancora impronte; chiudere completamente
System Settings dopo la creazione. Il supervisore arresta l'eventuale fprintd
socket-attivato e pubblica READY solo a daemon inattivo. Attendere che esista:

    /run/goodix-d293-04-public/public.env

Entrare quindi in una vera sessione Plasma/Wayland del nuovo utente. La
sessione precedente può restare aperta; non avviare altri consumer fingerprint.

### 2. Unico operator-run dal nuovo utente

Aprire Konsole nella nuova sessione ed eseguire:

    GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=safe.directory \
    GIT_CONFIG_VALUE_0=/run/goodix-d293-04-public/repo \
    /run/goodix-d293-04-public/repo/operator_kit/live_probe/run.sh \
      d293-kde-new-user --operator-run \
      --capture-root "$HOME/D293-04-captures"

La configurazione Git è solo nell'environment del comando e non scrive
~/.gitconfig; evita dubious ownership sul bind mount read-only. Il common
harness verifica branch, HEAD/origin, critical set, budget e conferma. Il kit
apre il KCM, mentre enrollment e delete restano operazioni manuali della UI.
fprintd-list viene usato soltanto per contare e fprintd-verify soltanto per
VerifyStart(any); non sono usati CLI di enrollment/delete.

Budget tecnici:

    MAX_ACTIONS=5
    MAX_CONTACTS=24
    MAX_RETRIES_TRANSPORT=0
    MAX_VERIFY_START=3
    STOP_ON_FIRST_MATCH=true
    FOURTH_ATTEMPT_ALLOWED=false
    ENROLLMENT_BIOMETRIC_REPEAT_BUDGET_MAX=20

Le ripetizioni biometriche richieste esplicitamente dalla UI durante
enrollment rientrano nel limite dichiarato; non sono retry automatici di
transport. I contatti sono derivati dalla telemetria production: un first-image
IDENTIFY, enroll_contacts fino a 20 e fino a tre epoch VERIFY. Nessun conteggio
viene delegato all'operatore.

Il cleanup invia sempre release al supervisore. Il runtime D285 viene
ripristinato e l'integrità byte+metadata del principal preesistente viene
confrontata internamente. Bind mount e account restano fino al logout per non
togliere il codice sotto il processo del common harness.

### 3. Cleanup account dopo il logout

Uscire completamente dalla sessione d293-phase-b-test, tornare all'utente
preesistente ed eseguire:

    operator_kit/live_probe/experiments/d293-kde-new-user/recover.sh

La recovery rifiuta account ancora attivi o template residui: in quel caso
rientrare nel nuovo utente, cancellare l'impronta dal KCM e ripetere la sola
recovery. Su successo smonta il repository read-only, elimina esattamente
l'account/home di test e riesegue l'audit D285/D286.

## Recovery d'emergenza

Se il terminale o la sessione si chiudono, il supervisore ripristina comunque
il runtime su signal o al timeout e termina il proprio loop. Un reboot rimuove
runtime, drop-in e mount sotto /run, ma non elimina l'account: recover.sh resta
necessario e ricava dall'invocazione pkexec l'utente originale per l'audit
finale.

La capture sanitizzata è salvata sotto:

    $HOME/D293-04-captures/d293-kde-new-user_<timestamp>_<sha>/sanitized/

Non contiene password, immagini, template o hash dei template; conserva
provenance candidate, contatori, telemetria e soli booleani di isolamento.
