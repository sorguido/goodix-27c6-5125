<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D287/01 — pilot KScreenLocker in modalità di test

> **HUMAN REQUIRED:** questo kit usa Polkit/root, avvia il greeter KDE reale e
> può raggiungere il sensore Goodix. L’agente AI non deve eseguire
> `--operator-run`.

## Scopo e rischio

Il pilot verifica il primo consumer desktop reale dopo la closure D286:
`/usr/libexec/kscreenlocker_greet --testing`. La modalità di test è un processo
standalone e non blocca la sessione. Usa però il vero binario KScreenLocker, il
tema lockscreen installato e il servizio PAM hard-coded `kde-fingerprint`.

La prima invocazione operatore sul commit `69b81c3f6fc4bdbfb86044581324637fd86df9ee`
si è fermata nel gate pre-live, prima di Polkit, greeter, USB e sensore: nessun
contatto biometrico D287 è stato consumato. Questo correttivo ripara il pathspec
multilinea del gate Git e aggiorna il contract dopo un audit target-specific
dell'aggiornamento Fedora a `kscreenlocker-6.7.5-1.fc44.x86_64` e
`plasma-workspace-6.7.5-1.fc44.x86_64`. Il QML e i due PAM pertinenti sono
rimasti byte-identici; i sorgenti greeter rilevanti sono invariati fra i tag
upstream 6.7.4 e 6.7.5.

La seconda invocazione sulla baseline `dc09bad49913fd51529ad5d4cbe399bf2f04f04c`
ha superato `pkexec` e il pre-audit D285, poi si è fermata prima di namespace,
greeter e VERIFY perché il journal filtrato per `fprintd.service` non aveva
entry pregresse e non restituiva un cursor. Anche questa run ha consumato zero
contatti. Il kit corretto usa un cursor globale della coda del boot e continua
a raccogliere soltanto eventi `fprintd.service` successivi a quel boundary.
Prima di ripresentare il kit è stato simulato orizzontalmente l'intero percorso
host, inclusi failure di greeter, journal, cleanup, parsing, pipeline e summary.

Il rischio residuo è un processo grafico in primo piano che può catturare
temporaneamente input e una VERIFY reale sul sensore. Non digitare la password
nel form. Se la finestra non appare, non risponde o il sensore mostra un
comportamento inatteso, non tentare comandi alternativi: attendere lo stop
fail-closed del kit e consegnare la capture alla review.

## Isolamento host

Il file `/etc/pam.d/kde-fingerprint` non viene modificato. Per ogni tentativo il
helper root crea un mount namespace privato, monta un piccolo tmpfs privato su
`/tmp`, vi copia il PAM D287, ne
replica il contesto SELinux del file Fedora e applica un bind mount read-only
visibile soltanto al greeter figlio. Alla morte del namespace l’overlay sparisce
insieme al tmpfs anche se il processo viene terminato. Prima e dopo ogni tentativo il kit
richiede gli hash originali di `kde`, `kde-fingerprint`, binario e QML e ripete
l’audit root-only completo dell’installazione D285.

Il PAM isolato contiene una sola regola:

```text
auth required pam_fprintd.so max-tries=1 timeout=45
```

Il servizio password `kde` resta quello Fedora originale e separato. La prova
non abilita `with-fingerprint`, non modifica `system-auth`, non installa o
riavvia nulla e non tocca runtime, template o libfprint di sistema.

## Metodo e limiti

- massimo tre finestre/tentativi, ciascuna con una sola epoch VERIFY;
- un solo contatto fisico esplicito per finestra;
- dopo `NO_MATCH`, il tentativo successivo richiede una nuova frase di conferma;
- `MATCH` arresta subito la serie;
- `PAM_ERROR`, anomalia host o telemetria safety terminano senza retry;
- zero retry/reopen/reset/clear-halt/famiglie persistenti note;
- niente quarto tentativo e nessuna inferenza FAR/FRR.

Il greeter installato non riporta in modo affidabile il `NO_MATCH`
non-interattivo nell’interfaccia e mantiene lo stato aggregato in
autenticazione. Perciò ogni retry è un nuovo processo `--testing`, non una
riattivazione automatica dentro la stessa finestra. Il supervisore legge il
journal dal cursor della singola prova e chiude esattamente il process group del
greeter dopo un `NO_MATCH`; non invia nuovi comandi al sensore.

## Prerequisiti e stop condition

- sessione Plasma Wayland corrente dell’utente operatore;
- branch `development`, HEAD uguale a `origin/development`, review set pulito;
- installazione D285 ancora attiva e integralmente hash-pinned;
- esattamente un target USB `27c6:5125`;
- nessun altro `kscreenlocker_greet`, blocco schermo, sudo biometrico o consumer
  fprintd concorrente;
- poter usare Polkit con la password. L’autenticazione Polkit passa da
  `system-auth`, dove D285 ha disabilitato pam_fprintd, quindi non è un contatto
  sensore.

Premere `Ctrl-C` prima del primo contatto se un prerequisito non è vero. Dopo
un’anomalia non rilanciare automaticamente il kit.

## Preflight offline

Questo comando non usa privilegi, USB o sensore:

```bash
operator_kit/d287-01-kscreenlocker-testing/run-d287-01.sh --offline-preflight
```

Il preflight verifica anche che il journal del boot corrente fornisca un cursor
globale valido, senza creare entry fprintd né avviare il servizio.

## Esecuzione manuale

Dalla root del repository, nella sessione Plasma Wayland dell’utente:

```bash
operator_kit/d287-01-kscreenlocker-testing/run-d287-01.sh --operator-run
```

Autenticare Polkit con la password. Digitare `INDICE DESTRO` per il primo
tentativo. Quando appare il greeter di test, muovere il puntatore per mostrare
il form e appoggiare una sola volta l’indice destro. Non scrivere la password
nel form KDE.

Solo dopo un `NO_MATCH` il kit propone rispettivamente `TENTATIVO 2` e
`TENTATIVO 3`. Accettare soltanto quando si è pronti a un nuovo contatto.
`MATCH` chiude la finestra e impedisce gli slot rimanenti. Dopo tre `NO_MATCH`
la serie termina senza un quarto contatto.

Il comando stampa `D287_01_CAPTURE_DIRECTORY`. Consegnare l’intera directory
`sanitized/`; non copiare state root-only o file sotto `/var/lib/fprint`.
