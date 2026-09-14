<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D295/02 — Plasma Login Manager PAM corrective

**Data:** 2026-09-14

**Boundary:** Fedora 44 KDE clean-room Human Gate

**Esito offline:** READY; nuova esecuzione live richiesta all'Utente

## Evidenza ricevuta e diagnosi

La clean VM ha dato PASS per build/candidate D295, import, install e
idempotenza, USB `27c6:5125`, discovery fprintd, enrollment KDE, storage,
`sudo` via impronta e SIGFM MATCH attraverso `pam_fprintd`. Il login password
Plasma è PASS; soltanto il login fingerprint Plasma è FAIL.

`plasmalogin` include `password-auth`. Nel profilo authselect `local` osservato,
`with-fingerprint` aggiunge `pam_fprintd.so` a `system-auth`, non a
`password-auth`. Il journal del failure raggiunge `pam_unix(plasmalogin:auth)`
ma non `pam_fprintd`; subito dopo, `sudo` raggiunge il sensore e concede tramite
`pam_fprintd`. Ne consegue:

```text
D295_DRIVER_REGRESSION=false
D295_SENSOR_FAILURE=false
D295_FPRINTD_FAILURE=false
D295_MATCHER_FAILURE=false
D295_GENERIC_PAM_FPRINT=PASS
D295_PLASMALOGIN_FINGERPRINT=FAIL
D295_PLASMALOGIN_PAM_DOES_NOT_REACH_PAM_FPRINTD=true
```

## Review del meccanismo Fedora/PAM

Sono stati controllati il PAM `plasmalogin`, i link e template authselect
`password-auth`/`system-auth`, ownership RPM, modulo `fprintd-pam` e ricerca
configurazione nella libpam Fedora 44. La documentazione upstream Linux-PAM
stabilisce che un file omonimo in `/etc/pam.d` prevale sul vendor in
`/usr/lib/pam.d`: <https://github.com/linux-pam/linux-pam/blob/master/doc/man/pam.conf.5.xml>.
Il template upstream authselect conferma inoltre la regola Fedora-style
`auth sufficient pam_fprintd.so` condizionata da `with-fingerprint` in
`system-auth`: <https://github.com/authselect/authselect/blob/master/profiles/sssd/system-auth>.

Un profilo authselect custom non è il delta minimo: cambierebbe stack condivisi
e ownership della configurazione oltre il solo consumer guasto, mentre il
servizio package-owned `plasmalogin` non è uno dei file generati da authselect.
Il meccanismo scelto è quindi il normale override amministrativo omonimo:

```text
/usr/lib/pam.d/plasmalogin     package-owned, sempre intatto
/etc/pam.d/plasmalogin         override D295 gestito
```

L'override viene generato dalla copia vendor solo se Fedora è 44, il file è
regolare, appartiene a `plasma-login-manager`, passa la verifica RPM per quel
path, non contiene già `pam_fprintd` e contiene esattamente un confine
`auth substack password-auth`. Viene aggiunta una sola riga immediatamente
prima di tale confine:

```text
auth        sufficient                                   pam_fprintd.so
```

Rimuovendo quella riga, il risultato deve essere byte-identico al vendor.
Account, password, session, postlogin e moduli KWallet/keyring restano pertanto
identici. `sufficient` chiude l'auth sul MATCH; gli altri esiti continuano verso
`password-auth`, preservando il fallback. Nessuno username o path utente entra
nella configurazione. Un login biometrico non consegna la password a KWallet;
un eventuale prompt separato del wallet è comportamento atteso, non regressione
PAM.

## Transazione e lifecycle

La candidate include solo `plasmalogin-pam.rule` e dichiara:

```text
PAM_FILES_INCLUDED=true
PAM_INTEGRATION=MANAGED_ETC_OVERRIDE_FROM_VENDOR
```

Il manager registra hash vendor e override, una copia root-owned e non
scrivibile dagli utenti dell'override e stato PAM corrente/precedente. Install
è fail-closed su collisione. Update migra
anche lo state D295/01 già installato, dove PAM era assente. Rollback scambia
runtime e stato PAM; nel caso migrato rimuove l'override, e un rollback inverso
lo ripristina. Uninstall rimuove soltanto l'override di hash atteso e non tocca
mai il vendor. Drift del vendor dopo un update Fedora blocca status, update e
rollback; uninstall resta possibile se l'override D295 è integro, così viene
esposto il nuovo vendor package-owned.

## Evidenza offline

`python3 deployment/phase-c-source-first-managed/test_offline.py`:

```text
Ran 9 tests
OK
```

Copertura: pristine sintetico; install; install ripetuto; update; rollback;
uninstall; migrazione dallo state D295/01; vendor byte-identico; collisione;
drift vendor; password fallback strutturale; nessun dato user-specific; tamper
candidate; cleanup parziale; import/preservazione materiali; safety e sintassi.

Non sono stati eseguiti `sudo`, PAM live, fprintd live, USB, sensore, enrollment
o lettura di materiale protetto. Il repository pubblico non è stato modificato.

## Decisione e Human Gate

Il correttivo è pronto per il solo test manuale descritto in
`docs/PHASE_C_SOURCE_FIRST_INSTALL.md`: pull, nuova build, verifica hash, update
gestito, prova che il vendor è invariato, status/ordine PAM, password login,
fingerprint login e infine regressione `sudo`. In caso di failure si raccolgono
solo journal PAM/fprintd/plasmalogin sanitizzati; nessun operator kit o edit PAM.

```text
D295_PLASMALOGIN_PAM_CORRECTIVE=READY
PACKAGE_OWNED_PLASMALOGIN_MODIFIED=false
MANAGED_PAM_INTEGRATION=true
INSTALL_IDEMPOTENT=true
ROLLBACK_SUPPORTED=true
UNINSTALL_RESTORES_PREVIOUS_STATE=true
PASSWORD_FALLBACK_PRESERVED_BY_DESIGN=true
USER_SPECIFIC_CONFIGURATION=false
SENSOR_REACHING_EXECUTED_BY_AI=false
D295_02_OFFLINE_TESTS=9_PASS
D295_02_LIVE_EXECUTION=NOT_PERFORMED
PM_DECISION=HUMAN_REQUIRED
```
