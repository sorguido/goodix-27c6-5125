<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D285/01 — boundary persistente e reversibile per `sudo`

## Esito architetturale

Il semplice passaggio da staging transiente a installazione persistente è
respinto perché allargherebbe implicitamente lo scope. Il modulo Fedora
`pam_fprintd.so` parla sempre con il nome D-Bus globale
`net.reactivated.Fprint`; non accetta un daemon, un bus o uno storage scelto
dal servizio PAM. Sul target, `with-fingerprint` inserisce inoltre pam_fprintd
in `system-auth`, incluso da `kcheckpass` e `kscreensaver`.

Con un template persistente e la candidate globale, lasciare invariata questa
topologia renderebbe utilizzabile l'impronta anche da KScreenLocker e dagli
altri consumer di `system-auth`, mentre D284 ha provato soltanto sudo. La
configurazione D285 riduce quindi prima il perimetro PAM:

1. `authselect disable-feature with-fingerprint` con backup nominato;
2. verifica che `system-auth` non contenga pam_fprintd e che
   `fingerprint-auth` usi `pam_debug.so auth=authinfo_unavail`;
3. nuovo `goodix-d285-01-sudo`, con `max-tries=1` e fallback password;
4. override sudoers ristretto all'utente operatore.

Questo isola i consumer PAM osservati, non il servizio D-Bus in senso
assoluto: un programma autorizzato da polkit può invocare direttamente
fprintd. Questa limitazione è esplicita e rende vietata la riattivazione
manuale di `with-fingerprint` durante l'installazione D285.

## Runtime persistente e update safety

La candidate non sostituisce `/usr/lib64/libfprint-2.so.2.0.0`. I sei oggetti
runtime sono installati sotto un path `/usr/local/lib64` legato al full SHA.
Un wrapper `bin_t` sotto `/usr/local/sbin` verifica a ogni avvio:

- SHA-256 del vero `/usr/libexec/fprintd` Fedora;
- manifest dei sei oggetti;
- forma e destinazione dei symlink libfprint;
- allowlist del solo driver `goodix_27c6_5125`.

Solo dopo i gate esegue il daemon con `LD_LIBRARY_PATH` dedicato. Un update del
daemon o una modifica runtime fa fallire fprintd chiuso; sudo conserva il
fallback password. Il systemd drop-in cambia soltanto `ExecStart` verso questo
wrapper e mantiene sandbox, `StateDirectory=fprint` e gli altri guardrail
dell'unit Fedora.

## Installazione, prova e rollback

La singola installazione manuale parte soltanto da branch/baseline allineati,
versioni host esatte, authselect valido, un solo target USB, assenza di file
D285 e assenza completa di storage fprintd preesistente per l'utente. Dopo lo
staging persistente e la riduzione authselect:

- enrollment dell'indice destro, otto contatti;
- verifica che esista un solo FP3 sotto lo storage dell'utente;
- pin root-only di pathname relativo e hash del template;
- restart del daemon per provare ricaricamento da configurazione e storage
  persistenti;
- un solo `sudo -v`, accettato solo con epoch VERIFY e outcome SIGFM match;
- invalidazione finale del timestamp sudo.

Il budget della run d'installazione è due action e massimo nove contatti, con
zero retry automatico o implicito. Lo stato root-only conserva gli hash
necessari al rollback, inclusi quelli dei file authselect originari, ma non
viene esportato. Dopo l'export sanitizzato il result privato `/var/tmp` è
rimosso; in disinstallazione gli hash authselect, PAM sudo e libfprint di
sistema devono tornare esattamente ai valori pre-run.

La disinstallazione è fail-closed: prima di cancellare verifica authselect,
daemon, PAM, sudoers, wrapper, drop-in, manifest e l'esatto unico template.
Qualunque drift richiede review umana e non cancella dati. Se tutto coincide,
`fprintd-delete` rimuove il solo template ownership-pinned prima della
rimozione del runtime; authselect e lo stato iniziale del servizio vengono
ripristinati. Il failure trap d'installazione applica lo stesso vincolo: non
usa mai un delete ampio quando pathname/hash sono ambigui.

## Riesame metodologico pre-live

1. **Cosa cambia realmente rispetto a D284?** D284 usava `/run`, storage
   isolato e override transitori. D285 installa un runtime hash-pinned,
   conserva l'FP3 su storage normale, riduce esplicitamente lo scope globale
   authselect, prova un restart e fornisce uninstall ownership-pinned.
2. **Quale nuova ipotesi viene testata?** Che il percorso D284 resti valido
   dopo persistenza di runtime/configurazione/template e restart del daemon,
   senza rendere pam_fprintd disponibile ai consumer `system-auth`/KDE.
3. **Se fallisce nello stesso punto?** Nessun retry. Il failure export e il
   rollback vengono revisionati; un'ambiguità sul template lascia lo stack
   intatto e recuperabile con `RECOVERY_REQUIRED` invece di cancellare dati.

## Closure offline

Il primo avvio operatore dalla baseline `fd7f162024d0fb3ad33809456ed478d97133bd94`
si è fermato correttamente pre-live con `PARENT_PATH_UNSAFE`: sul target Fedora
`/usr/local/sbin` è il link distro-standard `bin`. Il correttivo non cambia il
percorso persistente: ammette soltanto quel link se risolve esattamente a
`/usr/local/bin` e il target è una directory reale non-symlink. Link diversi,
risoluzioni diverse e target ambigui restano rifiutati. La run fallita non ha
enumerato USB, raggiunto il sensore o richiesto rollback device-side.

Il preflight reale costruisce la candidate SIGFM, chiude l'ABI verso fprintd,
verifica il manifest persistente, genera wrapper e drop-in, valida sudoers e
il rendering authselect senza `with-fingerprint`. La matrice D285 è `27/27
PASS`; la matrice combinata D282–D285 è `177/177 PASS` fuori sandbox per i
test host-only PAM/systemd. La run offline dichiara esplicitamente zero USB,
zero accesso sensore e zero live.

```text
OUTCOME=READY_OFFLINE_HUMAN_REQUIRED_OPERATOR_INSTALL
ADVANCEMENT=MATERIAL_PERSISTENT_SINGLE_CONSUMER_ARCHITECTURE_AND_OPERATOR_PATH
EXECUTABLE_CLOSURE=PASS_OFFLINE
RESIDUAL_BLOCKER_OR_RISK=PRIVILEGED_PERSISTENT_HOST_CONFIGURATION_AND_SENSOR_REACHING_INSTALL
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
```
