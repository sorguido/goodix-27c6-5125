<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Phase C — installazione source-first gestita su Fedora 44 KDE

Guida canonica per installazione, update, rollback, uninstall e recovery. Il
modello source-first sostituisce l'RPM D294, che resta intatto come prototipo
storico e prova di packaging.

```text
PHASE_C_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL
RPM_OFFICIAL_DISTRIBUTION=false
TARGET=Fedora-44-KDE-x86_64
PROTECTED_MATERIAL_IN_REPOSITORY=false
```

## Stato validato — Phase C chiusa

La Human Gate nella VM Fedora 44 KDE pulita ha confermato build, candidate,
import dei materiali, install/idempotenza, reader, enrollment, template, MATCH
SIGFM, `pam_fprintd` e autenticazione `sudo`. Il solo failure è il login con
impronta di Plasma Login Manager: `plasmalogin` usa `password-auth`, mentre
`with-fingerprint` della profile `local` inserisce `pam_fprintd` soltanto in
`system-auth`. Il login password resta PASS.

Il correttivo D295/02 è poi PASS live: update gestito, PAM vendor byte-identico,
ordine dell'override, login password, login fingerprint Plasma e regressione
`sudo` sono tutti verdi. I due hotfix emersi durante la migrazione sono stati
riesaminati: la root runtime viene ora creata `0755` e il solo legacy `0700`
viene normalizzato dalla transazione privilegiata; `status` resta privilegiato
per verificare correttamente i materiali root-only.

D295/03 ha infine chiuso il lifecycle amministrativo reale: rollback
bidirezionale, uninstall e recovery/reinstall sono PASS con sensore scollegato.
Materiali protetti e conteggio dei template sono rimasti invariati, il PAM
vendor non è stato modificato e la root runtime finale è `0755`. La VM resta
sulla fresh reinstall gestita del commit `448f5c8...`.

Il gestore installa una runtime immutabile per commit sotto
`/usr/lib64/goodix-27c6-5125/`, un wrapper fprintd, un drop-in systemd e la guard
account-deletion B5 con policy SELinux. Non usa `/usr/local`, RPM D294, operator
kit Dxxx, firmware o configurazioni per singolo utente. Per `plasmalogin`
genera inoltre un override gestito in `/etc/pam.d` dalla copia vendor verificata:
non modifica mai `/usr/lib/pam.d/plasmalogin`.

Per KScreenLocker Fedora usa invece direttamente il file package-owned
`/etc/pam.d/kde-fingerprint` (`plasma-workspace`, `%config(noreplace)`), senza
una sorgente parallela in `/usr/lib/pam.d`. Il gestore ne salva quindi la copia
originale hash-pinned e genera una versione che sostituisce soltanto il
substack auth `fingerprint-auth` con `pam_fprintd.so max-tries=3 timeout=45`.
Rollback e uninstall ripristinano esattamente l'originale; drift, collisioni e
artefatti `.rpmnew`/`.rpmsave` bloccano la transazione. Authselect e il file
globale `fingerprint-auth` restano invariati.

## 1. Preparazione della VM

Installare Fedora 44 KDE x86_64, applicare gli aggiornamenti e creare uno
snapshot a macchina spenta. Non collegare ancora il sensore.

```bash
sudo dnf5 install git flatpak cpio patch binutils rpm-build dnf5-plugins \
  fprintd fprintd-pam libfprint libgusb selinux-policy-targeted checkpolicy \
  policycoreutils policycoreutils-devel
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.freedesktop.Sdk//25.08
git clone https://github.com/sorguido/goodix-27c6-5125-private.git
cd goodix-27c6-5125-private
git switch development
git pull --ff-only origin development
git status --short
```

`git status --short` deve essere vuoto. La build usa cinque RPM Fedora 44
OpenCV esatti e hash-pinned, scaricati ma non installati:

```bash
mkdir -p GoodixArtifacts/opencv-4.13-rpms
dnf5 download --destdir GoodixArtifacts/opencv-4.13-rpms \
  opencv-core-4.13.0-1.fc44.x86_64 opencv-devel-4.13.0-1.fc44.x86_64 \
  opencv-features2d-4.13.0-1.fc44.x86_64 opencv-flann-4.13.0-1.fc44.x86_64 \
  opencv-imgproc-4.13.0-1.fc44.x86_64
(cd GoodixArtifacts/opencv-4.13-rpms && \
  sha256sum -c ../../production/build-support/opencv-rpms.sha256)
```

Se una versione esatta non è disponibile o un hash non coincide, fermarsi: non
sostituire silenziosamente pacchetti più recenti.

## 2. Build unprivileged e review candidate

Usare un output assoluto nuovo o vuoto, esterno al repository:

```bash
mkdir -m 700 "$HOME/goodix-phase-c-candidate"
deployment/phase-c-source-first-managed/manage.sh prepare \
  "$HOME/goodix-phase-c-candidate"
```

Output atteso:

```text
PHASE_C_PREPARE=PASS
SOURCE_COMMIT=<40 caratteri hex>
CANDIDATE_DIRECTORY=.../candidate
PROTECTED_MATERIAL_INCLUDED=false
REAL_USB_ENUMERATION_ATTEMPTED=false
LIVE_EXECUTION_PERFORMED=false
```

```bash
(cd "$HOME/goodix-phase-c-candidate/candidate" && sha256sum -c SHA256SUMS)
grep -E '^(PHASE_C_DISTRIBUTION_MODEL|RPM_OFFICIAL_DISTRIBUTION|SOURCE_COMMIT|PROTECTED_MATERIAL_INCLUDED|PAM_FILES_INCLUDED|PAM_INTEGRATION)=' \
  "$HOME/goodix-phase-c-candidate/candidate/MANIFEST"
```

La candidate qualificata include anche `SBOM.spdx.json`,
`THIRD_PARTY_NOTICES.md`, i testi GPLv3/Apache-2.0 e il corpus notice OpenCV.
`SHA256SUMS` li copre insieme al payload. Il digest stampato come
`RELEASE_CANDIDATE_SHA256` identifica l'intero indice della candidate; lo
`SOURCE_COMMIT` identifica il corrispondente sorgente completo.

## 3. Materiale protetto: origine consentita

Il runtime richiede `target-material-manifest.json`, `transport-material.bin`,
`target-config-90.bin`, `gfusb.dll` e `fdt-cache.bin`, tutti root-only.
`transport-material.bin` contiene la PSK TLS usata dal runtime: non esiste un
file PSK separato da fornire oltre a questo set.

Il percorso empiricamente dimostrato nel progetto è una **VM Windows** a cui
viene passato lo stesso sensore Goodix, con installazione del driver OEM. Nel
test riuscito è stato sufficiente configurare Windows con PIN e installare il
driver OEM; non è stato necessario completare un enrollment fingerprint
Windows. Da quella VM è stato esportato il materiale protetto del dispositivo e
la PSK così recuperata è stata successivamente validata sul sensore dal percorso
Linux.

Per un utente Linux-only, quindi, la VM Windows + driver OEM è il percorso di
riferimento già provato per ottenere il proprio materiale. Un'installazione
Windows reale/dual boot sullo stesso computer e con lo stesso sensore viene
trattata come percorso operativo equivalente: cambia l'ambiente di esecuzione
di Windows, non il dispositivo né il ruolo del driver OEM. Il materiale resta
comunque specifico dello stesso sensore; il riuso cross-device non è supportato.

Questa guida non autorizza extractor improvvisati, provisioning alternativo o
la generazione/sostituzione della PSK. Le procedure di recupero/esportazione
devono restare aderenti alle evidenze Windows/VM già validate dal progetto e
non devono mai stampare o versionare secret.

Sono vietati PSK nulle, casuali o sostitutive, provisioning, riuso cross-device,
ClearApp, firmware/IAP e lettura OTP. Se non si possiede ancora il set legittimo,
va prima ottenuto dal proprio ambiente Windows/VM Windows con driver OEM per lo
stesso sensore.

```bash
deployment/phase-c-source-first-managed/manage.sh import-materials \
  /percorso/assoluto/del/set-legittimo
```

Output atteso: `PHASE_C_MATERIAL_IMPORT=PASS`. La sorgente non viene cancellata.

## 4. Installazione o migrazione gestita — Human Gate

Su una VM senza D295 installato usare `install`. Sulla VM che ha prodotto la
Human Gate descritta sopra, conservare prima l'hash vendor e usare `update` con
la nuova candidate:

```bash
sha256sum /usr/lib/pam.d/plasmalogin > "$HOME/plasmalogin.vendor.before.sha256"
```

VM senza alcuna installazione D295:

```bash
deployment/phase-c-source-first-managed/manage.sh install \
  "$HOME/goodix-phase-c-candidate/candidate"
```

VM con D295/01 già `ACTIVE`:

```bash
deployment/phase-c-source-first-managed/manage.sh update \
  "$HOME/goodix-phase-c-candidate/candidate"
```

In entrambi i casi:

```bash
deployment/phase-c-source-first-managed/manage.sh status
systemctl cat fprintd.service
sha256sum -c "$HOME/plasmalogin.vendor.before.sha256"
grep -nE 'pam_fprintd\.so|auth[[:space:]]+substack[[:space:]]+password-auth' \
  /etc/pam.d/plasmalogin
grep -nE 'pam_fprintd\.so|auth[[:space:]]+substack[[:space:]]+fingerprint-auth' \
  /etc/pam.d/kde-fingerprint
```

Attesi: `PHASE_C_INSTALL=PASS`, commit corrente,
`PROTECTED_MATERIAL_READY=true`, `PHASE_C_STATUS=ACTIVE`,
`MANAGED_PAM_INTEGRATION=true`, `MANAGED_PAM_STATUS=ACTIVE` e wrapper
`/usr/libexec/goodix-27c6-5125/fprintd-wrapper`, più
`KSCREENLOCKER_MANAGED_PAM_INTEGRATION=true` e
`KSCREENLOCKER_MANAGED_PAM_STATUS=ACTIVE`. Una seconda installazione della
stessa candidate risponde `PHASE_C_INSTALL=PASS_ALREADY_CURRENT`.

La regola `auth sufficient pam_fprintd.so` deve precedere il substack
`password-auth`; quest'ultimo e tutte le righe account/password/session/kwallet
restano presenti. Perciò un MATCH conclude l'auth, mentre mancata impronta,
timeout o utente non enrolled continuano verso la password. Un accesso solo
biometrico non fornisce la password a KWallet: l'eventuale richiesta separata
del wallet non è un failure del login PAM.

## 5. Validazione KDE/fprintd col sensore

Solo ora collegare il Goodix alla VM. Usare Impostazioni di sistema KDE → Utenti
per enrollment/delete e il normale Plasma Login Manager per il login. Non
eseguire operator kit Dxxx.

1. reader visibile nel KCM KDE;
2. enrollment di un normale utente locale;
3. logout e login Plasma con impronta;
4. blocco della sessione reale con `Meta+L` e sblocco con impronta;
5. password fallback;
6. delete dell'impronta dal KCM.

Per il login biometrico: massimo tre tentativi, stop al primo MATCH, nessun
quarto tentativo. Provare prima il login password e poi il login fingerprint.
Se quest'ultimo fallisce, fermarsi e raccogliere solo configurazione e journal
sanitizzati: non editare manualmente alcun PAM e non cambiare authselect.

## 6. Update, rollback, uninstall e recovery

```bash
deployment/phase-c-source-first-managed/manage.sh update /percorso/assoluto/candidate
deployment/phase-c-source-first-managed/manage.sh rollback
deployment/phase-c-source-first-managed/manage.sh uninstall
```

Il gestore conserva un solo commit precedente. Un secondo update fallisce con
`rollback_slot_occupied`, senza eliminare versioni. Rollback scambia i due
commit e anche entrambi gli stati PAM: il rollback della migrazione dal D295
precedente rimuove `/etc/pam.d/plasmalogin` e ripristina byte-per-byte il
`kde-fingerprint` package-owned; il rollback inverso ripristina entrambe le
integrazioni dagli oggetti root-owned e hash-pinned. Uninstall rimuove
l'override plasmalogin, ripristina il `kde-fingerprint` originale, espone il PAM
vendor Fedora, ripristina fprintd Fedora e preserva deliberatamente materiali
protetti e template fprintd; non esiste un purge implicito.

Se un update Fedora cambia il PAM vendor, status/update/rollback falliscono con
`plasmalogin_vendor_pam_drift`: riesaminare il nuovo file e costruire una nuova
installazione. L'uninstall resta consentito solo se l'override gestito è ancora
byte-identico allo state e non modifica il nuovo vendor.

Per `kde-fingerprint`, un cambio del digest RPM o la presenza di `.rpmnew` o
`.rpmsave` fa fallire chiuso status/update/rollback/uninstall: non ripristinare
alla cieca una configurazione precedente sopra un nuovo package. Riesaminare il
nuovo layout Fedora e produrre un correttivo compatibile prima di procedere.

Se il login grafico non è raggiungibile, usare una console testuale o lo
snapshot e lanciare `manage.sh uninstall`. In caso di drift, il gestore fallisce
chiuso. Raccogliere soltanto `manage.sh status`, `systemctl status
fprintd.service --no-pager`, `journalctl -b -u fprintd.service --no-pager` e
`getenforce`. Non allegare `/var/lib/goodix-5125-poc`, `/var/lib/fprint`,
capture USB, template o secret.

## 7. Sequenza D295/02 già eseguita — evidenza storica

```bash
cd "$HOME/goodix-27c6-5125-private"
git switch development
git pull --ff-only origin development
git status --short
mkdir -m 700 "$HOME/goodix-d295-pam-corrective"
deployment/phase-c-source-first-managed/manage.sh prepare \
  "$HOME/goodix-d295-pam-corrective"
(cd "$HOME/goodix-d295-pam-corrective/candidate" && sha256sum -c SHA256SUMS)
sha256sum /usr/lib/pam.d/plasmalogin > "$HOME/plasmalogin.vendor.before.sha256"
deployment/phase-c-source-first-managed/manage.sh update \
  "$HOME/goodix-d295-pam-corrective/candidate"
deployment/phase-c-source-first-managed/manage.sh status
sha256sum -c "$HOME/plasmalogin.vendor.before.sha256"
grep -nE 'pam_fprintd\.so|auth[[:space:]]+substack[[:space:]]+password-auth' \
  /etc/pam.d/plasmalogin
```

Poi, dal normale greeter Plasma: password PASS, logout, fingerprint PASS entro
tre tentativi; solo dopo il PASS verificare che `sudo` continui a usare
l'impronta. Se il login fingerprint fallisce, non fare altre modifiche:
conservare l'output sanitizzato di `manage.sh status`, le due sole righe PAM
mostrate sopra e il journal del boot filtrato a `plasmalogin`, `pam_fprintd` e
`fprintd`, redigendo username, seriali e qualsiasi dato non necessario.

Questa sequenza ha prodotto PASS e non va ripetuta per maggiore confidenza.

## 8. D295/03 — lifecycle amministrativo eseguito con PASS

La sequenza seguente è stata eseguita dall'Utente con il sensore Goodix
scollegato, senza enrollment, verify, login fingerprint o altre azioni
biometriche. Lo stato iniziale era:

```text
CURRENT_COMMIT=b51b4c6f6141e0651e251291745d9b48b08d8da6
PREVIOUS_COMMIT=4c9cd74cc02890080851c1dca0a5889c58981f77
MANAGED_PAM_STATUS=ACTIVE
PROTECTED_MATERIAL_READY=true
```

Aggiornare il clone e costruire prima la candidate finale, perché l'uninstall
rimuoverà lo state gestito:

```bash
cd "$HOME/goodix-27c6-5125-private"
git switch development
git pull --ff-only origin development
git status --short
candidate_root=$(mktemp -d "$HOME/goodix-d295-phase-c-closure.XXXXXX")
deployment/phase-c-source-first-managed/manage.sh prepare \
  "$candidate_root"
(cd "$candidate_root/candidate" && sha256sum -c SHA256SUMS)
grep '^SOURCE_COMMIT=' "$candidate_root/candidate/MANIFEST"
```

`git status --short` deve essere vuoto. Prima del rollback registrare solo
metadata non sensibili:

```bash
deployment/phase-c-source-first-managed/manage.sh status
sha256sum /usr/lib/pam.d/plasmalogin > "$HOME/plasmalogin.vendor.lifecycle.sha256"
template_count_before=$(sudo find /var/lib/fprint -xdev -type f -printf . | wc -c)
printf 'TEMPLATE_FILE_COUNT_BEFORE=%s\n' "$template_count_before"
```

Eseguire rollback andata/ritorno e fermarsi al primo errore:

```bash
deployment/phase-c-source-first-managed/manage.sh rollback
deployment/phase-c-source-first-managed/manage.sh status
test ! -e /etc/pam.d/plasmalogin
sha256sum -c "$HOME/plasmalogin.vendor.lifecycle.sha256"

deployment/phase-c-source-first-managed/manage.sh rollback
deployment/phase-c-source-first-managed/manage.sh status
test -f /etc/pam.d/plasmalogin
sha256sum -c "$HOME/plasmalogin.vendor.lifecycle.sha256"
```

Il primo rollback deve riportare `CURRENT_COMMIT=4c9cd74...` e
`MANAGED_PAM_STATUS=ABSENT`; il secondo `CURRENT_COMMIT=b51b4c6...` e
`MANAGED_PAM_STATUS=ACTIVE`.

Eseguire uninstall e verificare la baseline senza leggere materiali o template:

```bash
deployment/phase-c-source-first-managed/manage.sh uninstall
test ! -e /etc/pam.d/plasmalogin
test ! -e /usr/lib64/goodix-27c6-5125
test ! -e /usr/libexec/goodix-27c6-5125/fprintd-wrapper
sha256sum -c "$HOME/plasmalogin.vendor.lifecycle.sha256"
sudo test -d /var/lib/goodix-5125-poc
for name in target-material-manifest.json transport-material.bin \
  target-config-90.bin gfusb.dll fdt-cache.bin; do
  sudo test -f "/var/lib/goodix-5125-poc/$name" || exit 1
done
template_count_after=$(sudo find /var/lib/fprint -xdev -type f -printf . | wc -c)
printf 'TEMPLATE_FILE_COUNT_AFTER=%s\n' "$template_count_after"
test "$template_count_after" = "$template_count_before"
if deployment/phase-c-source-first-managed/manage.sh status; then
  echo 'UNEXPECTED_STATUS_SUCCESS_AFTER_UNINSTALL' >&2
  false
else
  echo 'EXPECTED_STATUS_FAILURE_AFTER_UNINSTALL'
fi
```

Infine reinstallare la candidate finale e lasciare la VM sul nuovo baseline:

```bash
deployment/phase-c-source-first-managed/manage.sh install \
  "$candidate_root/candidate"
deployment/phase-c-source-first-managed/manage.sh status
test "$(stat -c '%a' /usr/lib64/goodix-27c6-5125)" = 755
test -f /etc/pam.d/plasmalogin
sha256sum -c "$HOME/plasmalogin.vendor.lifecycle.sha256"
```

Il commit corrente finale deve coincidere con `SOURCE_COMMIT` della candidate;
attesi inoltre `PROTECTED_MATERIAL_READY=true`,
`MANAGED_PAM_INTEGRATION=true` e `MANAGED_PAM_STATUS=ACTIVE`. Il conteggio dei
template deve essere invariato. Non allegare contenuti o hash dei materiali e
dei template.

```text
PASS_IF=ROLLBACK_OUT_PASS_AND_ROLLBACK_BACK_PASS_AND_UNINSTALL_PASS_AND_REINSTALL_PASS
FAIL_IF=ANY_COMMAND_OR_INVARIANT_FAILS
STOP_IF=FIRST_FAILURE
```

Risultato osservato:

```text
D295_03_LIVE_EXECUTION=PASS_HUMAN_OBSERVED
D295_03_ROLLBACK_BIDIRECTIONAL=PASS
D295_03_UNINSTALL=PASS
D295_03_PROTECTED_MATERIAL_PRESERVATION=PASS
D295_03_TEMPLATE_PRESERVATION=PASS
D295_03_RECOVERY_REINSTALL=PASS
D295_03_FINAL_BASELINE_COMMIT=448f5c8cc6099032a23115a96e90428d75b74a7b
PHASE_C_CLOSURE_CRITERIA=PASS
PHASE_C_CLOSED=true
```
