<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D297/01 — KScreenLocker sul runtime storico D293

Questa patch transitoria applica al solo service PAM `kde-fingerprint` il
collegamento a `pam_fprintd` già provato dal percorso D289. Non installa la
candidate managed, non cambia driver/libfprint/fprintd, non modifica authselect
o `fingerprint-auth` e non sostituisce il runtime storico D293.

Il probe read-only ha determinato:

```text
ACTIVE_HOST_DEPLOYMENT_MODE=HISTORICAL_D293_RUNTIME
MANAGED_PHASE_C_STATE=ABSENT
KDE_FINGERPRINT_PACKAGE_OWNER=plasma-workspace-6.7.5-1.fc44.x86_64
KDE_FINGERPRINT_PACKAGE_POLICY=CONFIG_NOREPLACE
```

La patch sostituisce in modo gestito la sola riga auth
`substack fingerprint-auth` di `/etc/pam.d/kde-fingerprint` con
`pam_fprintd.so max-tries=3 timeout=45`, preserva tutte le altre righe e salva
l'originale root-only. Nessun servizio viene riavviato e nessun comando dello
script raggiunge il sensore.

## Prerequisiti e STOP dell'applicazione iniziale

Dalla root del clone, sul branch `development`, eseguire prima:

```bash
git pull --ff-only origin development
git status --short
operator_kit/d297-01-kscreenlocker-historical-runtime/install.sh --check
```

Lo status Git deve essere vuoto e il check deve terminare con `PASS`. Fermarsi
se il deployment non è `HISTORICAL_D293_RUNTIME`, se esiste già lo state Phase
C, se un hash/NEVRA differisce, se compaiono `.rpmnew`/`.rpmsave`, o se PAM è
già personalizzato. Non correggere manualmente i gate.

## Installazione — Human Gate già eseguita

I comandi restano documentati per provenance e recovery. Non rieseguire
l'installazione mentre lo status è `TRANSIENT_CORRECTIVE_ACTIVE`.

```bash
sudo operator_kit/d297-01-kscreenlocker-historical-runtime/install.sh
operator_kit/d297-01-kscreenlocker-historical-runtime/status.sh
```

Attesi `D297_01_KSCREENLOCKER_INSTALL=PASS`, deployment storico invariato e
`KSCREENLOCKER_PAM_STATUS=TRANSIENT_CORRECTIVE_ACTIVE`.

## Esito KScreenLocker registrato

L'Utente ha eseguito il workflow reale `Meta+L`; KScreenLocker ha raggiunto il
sensore, Goodix ha prodotto MATCH e la sessione reale è stata sbloccata.

```text
D297_KSCREENLOCKER_LIVE_GATE=PASS
REAL_KDE_LOCKED_SESSION_UNLOCK=PROVEN
HISTORICAL_RUNTIME_KSCREENLOCKER_LIVE_UNLOCK=PROVEN
KSCREENLOCKER_LIVE_RESULT=PASS_MATCH
```

Non ripetere questa prova per sola maggiore confidenza e non reinstallare o
modificare ulteriormente PAM. La patch resta attiva sul runtime storico.

## Verifiche residue minimali — Human Gate

Restano soltanto questi tre controlli nel normale workflow del sistema:

1. eseguire `sudo -k true` e completare con impronta, con massimo tre contatti
   e stop immediato al primo MATCH;
2. eseguire un normale logout/login Plasma con password;
3. eseguire un normale logout/login Plasma con fingerprint, con massimo tre
   contatti e stop immediato al primo MATCH.

Non eseguire installazioni, modifiche PAM o una migrazione alla candidate
durante questi controlli.

```text
PASS_IF=sudo, login Plasma password e login Plasma fingerprint completano normalmente
FAIL_IF=uno dei tre workflow non completa o mostra una regressione PAM/fingerprint
STOP_IF=quarto contatto richiesto, retry non osservabile, instabilità o richiesta di modifica host
```

Riportare soltanto PASS/FAIL per ciascuno dei tre controlli ed eventuale
messaggio e punto preciso del failure. Log e journal verranno richiesti solo
dopo un failure reale, se necessari.

## Rollback

Eseguire il rollback dopo FAIL, instabilità/regressione o prima della futura
migrazione al deployment managed ufficiale. Dopo un PASS stabile la patch può
restare attiva fino a tale migrazione.

```bash
sudo operator_kit/d297-01-kscreenlocker-historical-runtime/uninstall.sh
operator_kit/d297-01-kscreenlocker-historical-runtime/status.sh
```

Atteso: `KSCREENLOCKER_PAM_STATUS=VENDOR_UNPATCHED`; runtime D293, authselect,
`fingerprint-auth`, materiali e template restano invariati. Prima della futura
migrazione ufficiale eseguire prima questo rollback e poi la procedura storica
già documentata per rimuovere il deployment D293 e ripristinare il
`plasmalogin` package-owned; solo dopo il managed installer può prendere
ownership, evitando doppia ownership dello stesso PAM.
