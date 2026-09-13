<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D293/B5 — account lifecycle e chiusura multi-user KDE

## Scopo

Questa patch aggiunge un solo pre-hook Fedora `shadow-utils` per impedire che
un account locale venga cancellato mentre `/var/lib/fprint/<username>` contiene
ancora dati. Il hook non cancella template, non chiama fprintd, non apre USB e
non modifica la candidate D293: chiede di eliminare prima le impronte tramite
il normale workflow KDE/fprintd. Dopo il cleanup fprintd, la cancellazione
account procede e il riuso futuro dello stesso nome non eredita template stale.

La live completa inoltre i lifecycle Phase B ancora non attraversati sulla
baseline D293: gallery a due dita, re-enrollment, delete singolo/completo,
logout/login, reboot e account deletion/name reuse. Non valida packaging RPM,
suspend/hotplug, concorrenza, FAR/FRR, AD/LDAP, altri sensori o regressione
Windows esaustiva.

## Prerequisiti e STOP

- branch `development`, HEAD pubblicato su `origin/development`, worktree pulito;
- D293 validata ancora installata come baseline software configurata;
- Fedora 44 x86_64 e `shadow-utils-4.19.0-7.fc44.x86_64`;
- nessuna UI biometrica o azione fprintd in corso durante install/rollback;
- nome account usa-e-getta `d293b5live` assente e disponibile per creazione, cancellazione e
  ricreazione; non usare un account con dati da conservare;
- due dita fisiche distinte disponibili per la prova.

`STOP_IF=` un prerequisito fallisce, esiste già il path del hook o lo state
B5, la baseline D293 mostra drift, compare una richiesta di cancellare dati
fuori dal solo account di prova, oppure il principal Guido cambia. Non
aggirare il hook e non cancellare manualmente `/var/lib/fprint`.

## Installazione

Dalla root del repository, come utente normale:

```bash
deployment/d293-phase-b-account-lifecycle/install.sh
```

Solo la copia del hook e dello state richiede `sudo`. La patch crea, se
assenti, `/etc/shadow-maint/userdel-pre.d/` e installa:

- `/etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete`;
- `/etc/goodix-27c6-5125/d293-phase-b-account-lifecycle.state`.

Non modifica servizi, PAM, package, account, template o runtime D293. È attiva
quando termina con `D293_B5_INSTALL=PASS`.

## Workflow reale

1. Da Impostazioni di sistema → Utenti creare il normale account locale
   `d293b5live` e aprirne una vera sessione Plasma.
2. Nel KCM Utenti registrare due dita distinte. Da terminale eseguire
   `fprintd-verify` usando la seconda: dopo `verify-no-match` ripetere fino a un
   massimo complessivo di tre tentativi fisici, fermandosi al primo MATCH o al
   terzo NO_MATCH. Nessun quarto tentativo.
3. Dal KCM eseguire re-enrollment di una delle due dita, quindi cancellare
   soltanto l'altra. Verificare che la re-enrolled resti elencata.
4. Fare logout/login dell'account di prova, quindi riavviare il laptop dal menu
   KDE. Dopo il reboot rientrare in `d293b5live` e ripetere una sola serie
   `fprintd-verify` max-3 stop-on-first-MATCH.
5. Chiudere la sessione di `d293b5live`. Dal principal Guido tentare di
   cancellare l'account dal KCM mentre la re-enrolled è ancora presente. La
   cancellazione deve essere rifiutata e l'account deve restare presente.
6. Rientrare in `d293b5live`, cancellare dal KCM tutte le impronte e chiudere
   la sessione. Dal principal Guido cancellare di nuovo l'account: ora deve
   riuscire.
7. Ricreare dal KCM lo stesso nome `d293b5live`, aprirne la sessione e
   verificare che il reader sia visibile ma non compaiano impronte già
   registrate. Chiudere la sessione e cancellare nuovamente l'account vuoto.
8. Confermare nel principal Guido che il proprio stato biometrico è invariato.

`PASS_IF=` due dita e re-enrollment funzionano; delete singolo preserva l'altra
impronta; logout/login e reboot preservano il MATCH; la prima cancellazione
account viene bloccata finché esiste una print; dopo delete completo l'account
si cancella; il nome ricreato non eredita print; Guido resta invariato.

`FAIL_IF=` uno dei lifecycle fallisce, il hook consente la cancellazione con
print presenti, la cancellazione resta bloccata dopo delete completo, il nome
ricreato eredita dati, compare un quarto tentativo/retry nascosto o cambia il
principal preesistente.

Al primo FAIL fermarsi e riportare punto e messaggio visibile. Non aggiungere
diagnostica improvvisata e non inviare template, dati biometrici, secret o
state root-only.

## Permanenza e rollback

```text
ROLLBACK_PATCH_REQUIRED=true
ROLLBACK_ON_FAIL=true
ROLLBACK_ON_PASS=false
KEEP_VALIDATED_ADVANCEMENT_BY_DEFAULT=true
```

Dopo PASS lasciare il hook installato. Dopo FAIL, instabilità o regressione,
chiudere le UI e dalla root del repository eseguire come lo stesso utente:

```bash
deployment/d293-phase-b-account-lifecycle/uninstall.sh
```

L'installazione è transazionale: un errore intermedio rimuove hook, state e le
sole directory appena create prima di terminare con
`reason=partial_install_rolled_back`. Il rollback verifica hash e baseline
D293, rimuove soltanto hook e state e
rimuove le directory parent solo se erano state create dalla patch e sono
ancora esattamente vuote. Non rimuove account, template o D293. È completo al
marker `D293_B5_ROLLBACK=PASS`.

## Cosa riportare

Riportare PASS oppure il primo step fallito e il messaggio visibile; indicare
il tentativo del MATCH post-reboot, se avvenuto; confermare esito delle due
cancellazioni account, assenza di print dopo name reuse, stato Guido invariato
e se la patch è rimasta installata oppure è stato necessario il rollback.
