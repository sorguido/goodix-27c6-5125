# D293/05 — guard account lifecycle e candidate di closure Phase B

Data: 13 settembre 2026
Data correttiva SELinux: 14 settembre 2026
Stato live: `FAIL_HOST_SELINUX_EXEC_ROLLED_BACK`
Stato correttiva: `READY_OFFLINE_HUMAN_GATE_PENDING`
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

## Confine e criteri pre-live

La candidate non prova ancora che KDE mostri correttamente il fallimento del
pre-hook né chiude da sola Phase B. Dopo review PM positiva, il prossimo
boundary è un unico Human Gate patch-first sul target reale. PASS richiede
l'intera sequenza documentata nel README e lascia installate sia la baseline
D293 sia la guard; FAIL richiede rollback della guard, non della baseline D293
salvo motivazione separata.

```text
PRE_LIVE_OUTCOME=READY_OFFLINE_HUMAN_GATE_PENDING
ADVANCEMENT=HOST_ACCOUNT_DELETE_BOUNDARY_IMPLEMENTED
EXECUTABLE_CLOSURE=OFFLINE_PASS_LIVE_PENDING
RESIDUAL_BLOCKER_OR_RISK=REAL_KDE_ACCOUNT_LIFECYCLE_NOT_YET_EXECUTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
PRE_LIVE_PM_DECISION=ACCEPT_AND_CONTINUE
PHASE_B_CLOSED=false
```

## Esito live reale e recovery

L'Utente ha eseguito sul target Fedora 44 KDE la candidate
`a8d274a22a5b43b4eaf2aeba4a42bf4a617422c3`. L'installazione D293/05 è
riuscita e la live ha attraversato i lifecycle precedenti fino alla seconda
cancellazione account, dopo il delete completo delle impronte tramite KDE/
fprintd. In quel punto KDE Users non ha cancellato `d293b5live`.

L'alert SELinux fornito dall'Utente attribuisce il failure all'esecuzione del
pre-hook, prima della logica namespace vuoto/non vuoto:

```text
SELINUX_ENABLED=true
SELINUX_MODE=Enforcing
SELINUX_POLICY=targeted
SELINUX_POLICY_RPM=selinux-policy-targeted-44.8-1.fc44.noarch
SOURCE_DOMAIN=useradd_t
TARGET_TYPE=shadow_t
DENIED_PERMISSION=execute
D293_05_FAILURE_POINT=USERDEL_PRE_HOOK_EXEC
```

Il rollback D293/05 è PASS. Subito dopo il rollback la cancellazione di
`d293b5live` è PASS. Questo isola il blocker nella nuova integrazione host
SELinux D293/05; non prova un difetto del driver, del sensore o del delete
KDE/fprintd, né prova che fossero rimasti template stale. D293 non è stata
rimossa e resta la baseline validata.

```text
D293_05_INSTALL=PASS
D293_05_LIVE=FAIL
D293_05_FAILURE_CLASS=HOST_SELINUX_EXECUTION_POLICY
D293_05_FAILURE_POINT=USERDEL_PRE_HOOK_EXEC
D293_05_DRIVER_REGRESSION=false
D293_05_SENSOR_FAILURE=false
D293_05_ROLLBACK=PASS
D293_05_ACCOUNT_DELETE_AFTER_ROLLBACK=PASS
D293_BASELINE=STILL_ACTIVE_AND_VALIDATED
D293_05_GUARD=REMOVED_AFTER_FAIL
TEST_ACCOUNT_d293b5live=DELETED
PHASE_B_CLOSED=false
```

## Studio SELinux Fedora 44 correttivo

Lo studio è stato eseguito sul package esatto del target
`selinux-policy-targeted-44.8-1.fc44.noarch`, senza generare policy da AVC. Il
SRPM corrispondente è stato scaricato ed estratto in una directory temporanea
read-only per l'analisi:

```text
selinux-policy-44.8-1.fc44.src.rpm
SHA256=1dc1633434f6a35d56d06fe4ccd8881b9d01afe0703543da36dc3dde8ad576bd
UPSTREAM_SOURCE_COMMIT=890df55eae6df1456266c3efeae4f230df978300
/etc/selinux/targeted/contexts/files/file_contexts
SHA256=ea167e05c7116094ddf8fb2bf483710938405b577c55d2494e385f3997a2ef5d
/etc/selinux/targeted/policy/policy.35
SHA256=189ea8b37e35ceab1aa1bf6e8d8dc26236269a30e0ffae511d07c7ad6c488582
```

La source policy esatta non contiene un tipo o un mapping per
`shadow-maint/userdel-pre.d`. La regex Fedora
`/etc/shadow.* -- shadow_t` cattura quindi anche il nuovo path del hook. La
policy compilata concede a `useradd_t` varie operazioni su `shadow_t`, ma non
`execute`: l'AVC live è coerente con il design effettivamente installato, non
con label drift. La stessa source policy assegna
`fprintd_var_lib_t` a `/var/lib/fprint(/.*)?`; non contiene alcuna relazione
fra `useradd_t` e quel tipo. `usermanage.te` concede già a `useradd_t`
l'esecuzione di shell e binari standard, sufficiente per l'interprete e
`/usr/bin/find` usati dal hook.

L'ambiente terminale dell'AI, al momento dello studio, riporta SELinux
`Disabled`, mentre la live documentata era `Enforcing`. È una discrepanza di
boot/runtime esplicitamente preservata: impedisce una prova enforcing da parte
dell'AI, ma non altera l'evidenza live né la source/compiled policy Fedora
ispezionabile offline. `selinux-policy-devel` e `setools-console` non sono
installati; sono invece disponibili `checkmodule`, `semodule_package`,
`semodule_unpackage` e `sedismod`. La candidate usa questi tool già presenti e
non introduce package permanenti.

Sono state escluse le seguenti alternative:

1. `audit2allow`, permissive o disabilitazione SELinux: troppo ampi e non
   rappresentano un'integrazione production;
2. `chcon`: label non dichiarata e non stabile rispetto a relabel;
3. mapping a `bin_t`/`shell_exec_t`: allargherebbe l'identità del file senza
   risolvere l'accesso a `fprintd_var_lib_t`;
4. allow `useradd_t shadow_t:file execute`: renderebbe eseguibile l'intera
   classe di file shadow catturata dalla regex Fedora;
5. permessi di lettura o modifica dei file template: non richiesti dal hook,
   che osserva soltanto esistenza di entry e metadata.

La soluzione selezionata è un modulo locale dichiarativo con:

- tipo `goodix_fprint_account_delete_exec_t` applicato soltanto all'esatto
  `/etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete`;
- esecuzione senza transition del solo hook da `useradd_t`;
- `getattr/open/read/search` sulle directory `fprintd_var_lib_t`;
- solo `getattr` su file e symlink `fprintd_var_lib_t`;
- nessun `write`, `create`, `unlink`, `rename`, `setattr`, accesso al contenuto
  dei file, dominio permissive, boolean o modifica della policy Fedora base.

Il modulo viene installato con priorità locale `400`. `semodule -l -m`
espone il checksum SHA-256 della rappresentazione CIL installata: installer e
rollback lo usano per rifiutare collisioni o drift. Il file-context è incluso
nel package `.pp`; `restorecon` applica il mapping dichiarativo al hook e la
rimozione del modulo ripristina il mapping Fedora precedente `shadow_t`.

Riferimenti upstream:

- <https://github.com/fedora-selinux/selinux-policy>
- <https://man7.org/linux/man-pages/man8/semodule.8.html>

## Riesame metodologico pre-live

1. **Cosa cambia realmente?** La prima candidate copiava un hook che ricadeva
   accidentalmente in `shadow_t`; la correttiva installa un tipo dedicato e la
   policy minima richiesta dal suo comportamento, con verifica di checksum e
   rollback simmetrico.
2. **Quale nuova ipotesi viene testata?** Che sotto SELinux Enforcing il hook
   dedicato venga eseguito da `useradd_t`, possa distinguere namespace con dati
   da namespace vuoto e non richieda altri permessi.
3. **Se fallisce nello stesso punto?** Si esegue subito il rollback B5 e si
   acquisisce soltanto il nuovo alert/AVC esatto. Non si prepara un terzo
   tentativo equivalente: si riesamina il dominio/target/permesso realmente
   negato prima di qualunque nuova policy.

La live successiva è quindi focalizzata sul solo boundary fallito. Non ripete
multi-finger, VERIFY/MATCH, logout/login o reboot già attraversati nella prima
run D293/05. Registra una sola print, prova il blocco, esegue delete KDE/fprintd,
prova la cancellazione e chiude il name-reuse.

## Implementazione e verifica correttiva

Artefatti aggiornati:

```text
deployment/d293-phase-b-account-lifecycle/
  50-goodix-fprint-account-delete
  goodix_fprint_account_delete.te
  goodix_fprint_account_delete.fc
  install.sh
  uninstall.sh
  test_offline.py
  README_TEST_LIVE.md
```

`install.sh` ora richiede SELinux Enforcing e le versioni target esatte,
compila il modulo dai sorgenti versionati, verifica assenza di collisioni,
installa a priorità 400, applica e verifica il tipo dedicato e registra nello
state hash di source, file-context, package e CIL. Un failure intermedio
rimuove anche il modulo. `uninstall.sh` passa dallo stesso percorso interno,
verifica checksum e label e rimuove modulo, hook e state senza toccare D293 o
`/var/lib/fprint`.

La prima review PM della correttiva ha inoltre eliminato un bypass ambientale
preesistente nel hook: in produzione viene invocato sempre `/usr/bin/find` e
il test mode viene rifiutato quando l'EUID è root. L'override del comando resta
disponibile solo a un test non privilegiato, sotto la sua root temporanea e con
file regolare, eseguibile, non symlink e posseduto dal tester. Il test negativo
per un override esterno (`/bin/true`) passa fail-closed.

La prova `sedismod` sul modulo compilato trova esattamente quattro allow:

```text
useradd_t -> goodix_fprint_account_delete_exec_t:file
  { execute execute_no_trans getattr open read }
useradd_t -> fprintd_var_lib_t:dir
  { getattr open read search }
useradd_t -> fprintd_var_lib_t:file
  { getattr }
useradd_t -> fprintd_var_lib_t:lnk_file
  { getattr }
```

Due build indipendenti producono byte identici:

```text
goodix_fprint_account_delete.mod
SHA256=0bb839480ec48ba82a2bfe36db454b105efc7df0d10a0dc425ddf586ed0665b3
goodix_fprint_account_delete.pp
SHA256=622c1928b53d47fe9c45fb855b00c274c0c64d8651f540d3f778a966c3ec327b
translated CIL stream
SHA256=067ea90981642cb5f822aebe4ec108c935269416732789b2c3d1569e1c95c788
```

Esito offline:

```text
bash -n hook install.sh uninstall.sh = PASS
python3 deployment/d293-phase-b-account-lifecycle/test_offline.py = 12/12 PASS
checkmodule + semodule_package + semodule_unpackage = PASS
sedismod exact allow surface = PASS
git diff --check = PASS
shellcheck = NOT_AVAILABLE
SELINUX_ENFORCING_EXECUTION = HUMAN_GATE_PENDING
USB_OR_SENSOR_ACCESS_BY_AI = 0
SUDO_BY_AI = 0
```

```text
OUTCOME=READY_OFFLINE_HUMAN_GATE_PENDING
ADVANCEMENT=FEDORA_44_SELINUX_BOUNDARY_STUDIED_AND_CORRECTED
EXECUTABLE_CLOSURE=OFFLINE_PASS_ENFORCING_LIVE_PENDING
RESIDUAL_BLOCKER_OR_RISK=REAL_USERADD_T_EXECUTION_UNDER_ENFORCING_NOT_YET_RETESTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
PM_DECISION=ACCEPT_AND_CONTINUE
PHASE_B_CLOSED=false
```
