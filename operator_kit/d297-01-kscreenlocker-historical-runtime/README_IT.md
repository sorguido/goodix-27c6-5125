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

## Prerequisiti e STOP

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

## Installazione — Human Gate

```bash
sudo operator_kit/d297-01-kscreenlocker-historical-runtime/install.sh
operator_kit/d297-01-kscreenlocker-historical-runtime/status.sh
```

Attesi `D297_01_KSCREENLOCKER_INSTALL=PASS`, deployment storico invariato e
`KSCREENLOCKER_PAM_STATUS=TRANSIENT_CORRECTIVE_ACTIVE`.

## Workflow reale

1. Nella normale sessione Plasma premere `Meta+L`.
2. Non digitare password o PIN. Presentare l'impronta.
3. Fermarsi immediatamente al primo unlock/MATCH.
4. Dopo un NO_MATCH sono ammessi al massimo altri due contatti; dopo il terzo
   NO_MATCH non presentare più il dito e recuperare con la password.
5. Dopo il PASS KScreenLocker verificare che `sudo -k true` continui a
   completare con impronta, sempre massimo tre contatti e stop al primo MATCH.
6. Eseguire un normale logout/login Plasma, prima con password e poi con
   impronta, senza modificare PAM. Questa prova controlla che il percorso login
   storico preesistente non sia regredito.

```text
PASS_IF=Meta+L raggiunge il sensore e la sessione reale passa locked->unlocked con MATCH
FAIL_IF=il sensore non parte, tre contatti producono NO_MATCH, compare errore PAM o login/sudo regrediscono
STOP_IF=quarto contatto richiesto, retry non osservabile, instabilità, drift o richiesta di modifica ulteriore
```

Riportare: esito `status.sh`, unlock osservato sì/no, numero del contatto che ha
prodotto MATCH (1–3), ed eventuale messaggio e punto preciso del failure. Log e
journal verranno richiesti solo dopo un failure reale, se necessari.

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
