# D293/05 — guard account lifecycle e candidate di closure Phase B

Data: 13 settembre 2026
Stato finale PM: `READY_OFFLINE_HUMAN_GATE_PENDING`
Live/USB/sudo eseguiti dall'AI: `false`

## Obiettivo

Chiudere il gap account deletion/name reuse rimasto dopo il PASS live D293,
senza chiamare fprintd dal lifecycle dell'account e senza accesso al sensore.
La candidate aggiunge un pre-hook `userdel` fail-closed: se il namespace
`/var/lib/fprint/<username>` contiene ancora dati, l'eliminazione dell'account
viene bloccata e l'operatore deve prima eliminare le impronte tramite il normale
workflow KDE/fprintd. Namespace assente o vuoto permette invece `userdel`.

Il hook non cancella template, non raggiunge USB, non usa segreti e non modifica
la baseline D293. Il rename di un account con impronte resta fuori dal percorso
supportato: eliminare prima le impronte; non viene installato un hook generico
su `usermod`.

## Evidenza del boundary host

Target osservato offline:

```text
shadow-utils=4.19.0-7.fc44.x86_64
accountsservice=23.13.9-16.fc44.x86_64
plasma-workspace-libs=6.7.5-1.fc44.x86_64
```

Hash del materiale host ispezionato:

```text
/usr/sbin/userdel
  e8a98ee1e6703b9e094b4f4f52803671f3bac1d7490361f930d047ab4b42fe9d
/usr/share/man/man8/userdel.8.gz
  b53c26eebcbb6d97303f5dfc06eae36a1ff14fb47fd0aef6fdf312f32b943195
/usr/libexec/accounts-daemon
  adea18e58b44442109b3ec9a3fb127d132c7ec4829230ebbe62b07d0ed9bb427
/usr/lib64/qt6/plugins/plasma/kcms/systemsettings/kcm_users.so
  764b86abb81f4be9ee38c836a558955bca192546dc77158e2ace72e8bb2cf2d9
```

La man page installata documenta i pre/post hook in
`/etc/shadow-maint/userdel-{pre,post}.d`, le variabili `ACTION=userdel` e
`SUBJECT=<username>` e l'abort su exit nonzero. Il sorgente upstream esatto
shadow 4.19.0 conferma che il pre-hook precede lookup e mutazione dell'account e
che anche `userdel --force` non ne ignora il fallimento. Le stringhe e la
disassembly locale di AccountsService mostrano che `DeleteUser` invoca
`/usr/sbin/userdel -f` e aggiunge `-r` quando richiesto; il KCM Users usa
AccountsService. Il pre-hook copre quindi sia la CLI sia il percorso KDE
osservato, senza una nuova integrazione UI.

Riferimenti upstream:

- <https://github.com/shadow-maint/shadow/releases/tag/4.19.0>
- <https://raw.githubusercontent.com/shadow-maint/shadow/4.19.0/src/userdel.c>

## Artefatti

```text
deployment/d293-phase-b-account-lifecycle/
  50-goodix-fprint-account-delete
  install.sh
  uninstall.sh
  test_offline.py
  README_TEST_LIVE.md
```

`install.sh` verifica branch/HEAD/origin/worktree, versione esatta
`shadow-utils`, baseline D293 e collisioni. Installa soltanto il hook e uno
state file root-only con hash e ownership logica delle directory create.
L'installazione è transazionale e ripulisce un fallimento intermedio prima
dello state commit. `uninstall.sh` è simmetrico, valida drift e rifiuta di rimuovere directory che
abbiano acquisito contenuto esterno. La live patch-first usa il workflow reale
KDE e combina multi-finger, replace/delete, logout/login, reboot e
delete/name-reuse; il VERIFY resta bounded a tre tentativi fisici con stop al
primo MATCH.

## Verifica Executor

```text
bash -n 50-goodix-fprint-account-delete install.sh uninstall.sh = PASS
python3 deployment/d293-phase-b-account-lifecycle/test_offline.py = 9/9 PASS
```

Copertura offline:

1. collision/drift;
2. preservazione di parent preesistenti;
3. blocco con dati e pass con namespace vuoto;
4. pass senza state root o namespace utente;
5. input e symlink unsafe rifiutati;
6. installazione e rollback esatti;
7. rollback rifiutato se una directory posseduta acquisisce entry esterne;
8. fault injection prima dello state commit con cleanup transazionale completo;
9. errore di lettura del namespace trattato fail-closed.

## Confine e criteri di closure

La candidate non prova ancora che KDE mostri correttamente il fallimento del
pre-hook né chiude da sola Phase B. Dopo review PM positiva, il prossimo
boundary è un unico Human Gate patch-first sul target reale. PASS richiede
l'intera sequenza documentata nel README e lascia installate sia la baseline
D293 sia la guard; FAIL richiede rollback della guard, non della baseline D293
salvo motivazione separata.

```text
OUTCOME=READY_OFFLINE_HUMAN_GATE_PENDING
ADVANCEMENT=HOST_ACCOUNT_DELETE_BOUNDARY_IMPLEMENTED
EXECUTABLE_CLOSURE=OFFLINE_PASS_LIVE_PENDING
RESIDUAL_BLOCKER_OR_RISK=REAL_KDE_ACCOUNT_LIFECYCLE_NOT_YET_EXECUTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
PM_DECISION=ACCEPT_AND_CONTINUE
PHASE_B_CLOSED=false
```
