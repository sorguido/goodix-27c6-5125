<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D293/B5 correttiva — account deletion con SELinux Enforcing

> Stato: `PASS_FULL_ON_TARGET` il 14 settembre 2026. La guard e il modulo
> SELinux sono rimasti installati come baseline validata. Le istruzioni sotto
> restano il riferimento auditabile per installazione e rollback; non ripetere
> la live senza un nuovo boundary concreto.

## Scopo della live

Questa patch conserva invariati driver, runtime e configurazione D293 e
corregge soltanto l'integrazione SELinux del pre-hook `userdel` già validato
offline. Installa un tipo eseguibile dedicato per l'esatto hook B5 e concede a
`useradd_t` i soli permessi necessari per eseguirlo e ispezionare nomi e
metadati sotto `/var/lib/fprint`; non concede lettura dei template né alcuna
scrittura.

La prova risponde a un unico boundary: con SELinux `Enforcing`, la cancellazione
di `d293b5live` viene bloccata quando resta una fingerprint e riesce dopo il
delete completo tramite KDE/fprintd. Non ripete gallery, reboot, verify/match o
gli altri lifecycle già attraversati. Non valida RPM, suspend/hotplug,
concorrenza, FAR/FRR, AD/LDAP, altri sensori o Windows.

```text
VERIFY_MATCH_IN_SCOPE=false
SENSOR_PERSISTENT_WRITE=0
FIRMWARE_CHANGE=0
PSK_ACCESS=0
```

## Prerequisiti e STOP

- branch `development`, HEAD pubblicato su `origin/development`, worktree pulito;
- D293 validata ancora installata e funzionante come baseline;
- Fedora 44 x86_64 con `shadow-utils-4.19.0-7.fc44.x86_64` e
  `selinux-policy-targeted-44.8-1.fc44.noarch`;
- SELinux `Enforcing` con policy `targeted`;
- comandi `checkmodule`, `semodule_package`, `semodule`, `matchpathcon` e
  `restorecon` presenti;
- nessuna UI biometrica o azione fprintd in corso durante installazione e
  rollback;
- account usa-e-getta `d293b5live` assente; non usare un account con dati da
  conservare.

`STOP_IF=` un prerequisito fallisce; esiste già il modulo SELinux
`goodix_fprint_account_delete`, il path del hook o lo state B5; la baseline D293
mostra drift; compare una richiesta di cancellare dati fuori dall'account di
prova; oppure cambia il principal Guido. Non usare `audit2allow`, non impostare
permissive, non disabilitare SELinux, non applicare `chcon` e non cancellare
manualmente `/var/lib/fprint`.

## Installazione

Dalla root del repository, come utente normale:

```bash
deployment/d293-phase-b-account-lifecycle/install.sh
```

Lo script invoca `sudo` una sola volta per installare:

- modulo locale SELinux `goodix_fprint_account_delete` a priorità `400`;
- `/etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete`, con tipo
  `goodix_fprint_account_delete_exec_t`;
- `/etc/goodix-27c6-5125/d293-phase-b-account-lifecycle.state`.

Compila la policy dai sorgenti versionati, verifica collisioni, checksum,
contesti e baseline D293 e termina con `D293_B5_INSTALL=PASS`. Non modifica
servizi, PAM, package, account, template o runtime D293.

## Workflow reale focalizzato

1. Da Impostazioni di sistema → Utenti creare l'account locale usa-e-getta
   `d293b5live` e aprirne una vera sessione Plasma.
2. Nel KCM Utenti registrare una sola impronta, verificare che sia elencata,
   quindi chiudere la sessione. Non eseguire `fprintd-verify`.
3. Dal principal Guido tentare di cancellare `d293b5live` dal KCM. La
   cancellazione deve essere rifiutata e l'account deve restare presente.
4. Rientrare in `d293b5live`, cancellare l'impronta dal KCM, verificare che non
   sia più elencata e chiudere la sessione.
5. Dal principal Guido cancellare di nuovo l'account. Questa volta deve
   riuscire.
6. Ricreare una sola volta `d293b5live`, aprirne la sessione e verificare che il
   reader sia visibile ma che non compaiano impronte già registrate. Chiudere
   la sessione e cancellare l'account vuoto.
7. Confermare nel principal Guido che il proprio stato biometrico è invariato.

`PASS_IF=` la prima cancellazione è bloccata con l'impronta presente; il delete
KDE/fprintd riesce; la seconda cancellazione riesce con namespace vuoto; il
nome ricreato non eredita impronte; Guido e la baseline D293 restano invariati;
non compare alcun alert SELinux.

`FAIL_IF=` il hook non viene eseguito; una cancellazione passa con l'impronta
presente; resta bloccata dopo il delete completo; il nome ricreato eredita
dati; compare un alert SELinux; oppure si osserva una regressione D293 o del
principal Guido.

`STOP_IF=` al primo FAIL, instabilità, richiesta inattesa o comportamento fuori
scope. Annotare soltanto step e messaggio visibile. Se il failure è ancora
SELinux, dopo il rollback riportare l'alert/AVC esatto; non generare una policy
con `audit2allow` e non ripetere una terza live equivalente.

## Permanenza e rollback

```text
ROLLBACK_PATCH_REQUIRED=true
ROLLBACK_ON_FAIL=true
ROLLBACK_ON_PASS=false
KEEP_VALIDATED_ADVANCEMENT_BY_DEFAULT=true
```

Dopo PASS lasciare la patch installata: diventa parte della baseline per il
passo successivo. Dopo FAIL, instabilità o regressione, chiudere le UI e dalla
root del repository eseguire come lo stesso utente:

```bash
deployment/d293-phase-b-account-lifecycle/uninstall.sh
```

Il rollback verifica state, hash, modulo, label e baseline D293; rimuove
soltanto modulo SELinux B5, hook e state, e rimuove le directory parent solo se
erano state create dalla patch e non hanno acquisito contenuto esterno. La
rimozione del modulo ripristina per quel path il mapping Fedora precedente
`shadow_t`. Non rimuove account, template, package o D293. È completo soltanto
ai marker:

```text
D293_B5_ROLLBACK=PASS
D293_B5_SELINUX_POLICY_REMOVED=true
D293_B5_D293_BASELINE=PRESERVED
```

Anche l'installazione è transazionale: dopo un errore rimuove modulo, hook,
state e le sole directory create dalla patch. Dichiara
`reason=partial_install_rolled_back` soltanto se il cleanup è completo; con
`reason=partial_install_cleanup_incomplete` fermarsi e riportare il marker
senza tentare la live.

## Cosa riportare

Riportare `PASS` oppure il primo step fallito e il messaggio visibile;
confermare gli esiti delle due cancellazioni, l'assenza di impronte dopo il
name reuse, lo stato Guido invariato e se la patch è rimasta installata oppure
è stato eseguito il rollback.

## Esito registrato

```text
D293_B5_OFFLINE_TESTS=12/12_PASS
D293_B5_INSTALL=PASS
D293_B5_DELETE_WITH_PRINT=BLOCKED
D293_B5_DELETE_WITHOUT_PRINT=PASS
D293_B5_SELINUX_ALERTS=0
D293_B5_SELINUX_ENFORCING=PASS
D293_B5_ACCOUNT_LIFECYCLE=PASS
D293_B5_FUNCTIONAL_LIVE=PASS
D293_B5_SELINUX_CLEAN_LIVE=PASS
D293_B5_PRINCIPAL_GUIDO_UNCHANGED=true
ROLLBACK_ON_PASS=false
PATCH_LEFT_INSTALLED=true
```

I failure precedenti su esecuzione `shadow_t`, sintassi `.fc`, confronto del
checksum e AVC `TCGETS2` restano documentati nel report D293/05 e non cambiano
questo esito finale. L'eventuale rollback resta riservato a failure,
instabilità, regressione, recovery o richiesta esplicita dell'Utente.
