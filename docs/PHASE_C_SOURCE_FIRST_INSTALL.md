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

## Confine attuale

La Human Gate nella VM Fedora 44 KDE pulita ha confermato build, candidate,
import dei materiali, install/idempotenza, reader, enrollment, template, MATCH
SIGFM, `pam_fprintd` e autenticazione `sudo`. Il solo failure è il login con
impronta di Plasma Login Manager: `plasmalogin` usa `password-auth`, mentre
`with-fingerprint` della profile `local` inserisce `pam_fprintd` soltanto in
`system-auth`. Il login password resta PASS.

Il correttivo è chiuso offline ma la sua mutazione privilegiata e il nuovo login
restano azioni dell'Utente dopo Human Gate. Nessun comando live di questa guida
è stato eseguito dall'AI.

Il gestore installa una runtime immutabile per commit sotto
`/usr/lib64/goodix-27c6-5125/`, un wrapper fprintd, un drop-in systemd e la guard
account-deletion B5 con policy SELinux. Non usa `/usr/local`, RPM D294, operator
kit Dxxx, firmware o configurazioni per singolo utente. Per `plasmalogin`
genera inoltre un override gestito in `/etc/pam.d` dalla copia vendor verificata:
non modifica mai `/usr/lib/pam.d/plasmalogin`.

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

## 3. Materiale protetto: origine consentita

Il runtime richiede `target-material-manifest.json`, `transport-material.bin`,
`target-config-90.bin`, `gfusb.dll` e `fdt-cache.bin`, tutti root-only.

La sola origine già provata è un export legittimo dall'installazione Windows
originale associata allo stesso dispositivo. Il plaintext DPAPI recuperato
alimenta direttamente la PSK TLS; la portabilità è provata soltanto per quel
dispositivo e quel materiale machine-bound legittimamente esportato.

La storia prova che una VM Windows con driver OEM può osservare il normale
bootstrap, ma non documenta una procedura generale per estrarre un set nuovo;
nella VM studiata l'enrollment Windows non era completato. Questa guida quindi
non inventa un extractor e non promette che installare il driver OEM in una VM
nuova produca materiale esportabile.

Sono vietati PSK nulle, casuali o sostitutive, provisioning, riuso cross-device,
ClearApp, firmware/IAP e lettura OTP. Se non si possiede già il set legittimo,
fermarsi con `HUMAN_REQUIRED_PROTECTED_MATERIAL`.

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
```

Attesi: `PHASE_C_INSTALL=PASS`, commit corrente,
`PROTECTED_MATERIAL_READY=true`, `PHASE_C_STATUS=ACTIVE`,
`MANAGED_PAM_INTEGRATION=true`, `MANAGED_PAM_STATUS=ACTIVE` e wrapper
`/usr/libexec/goodix-27c6-5125/fprintd-wrapper`. Una seconda installazione della
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
4. password fallback;
5. delete dell'impronta dal KCM.

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
commit e anche lo stato PAM: il rollback della migrazione dal D295 precedente
rimuove `/etc/pam.d/plasmalogin`; il rollback inverso lo ripristina dall'oggetto
root-owned e hash-pinned. Uninstall rimuove l'override, espone il PAM vendor Fedora,
ripristina fprintd Fedora e preserva deliberatamente materiali protetti e
template fprintd; non esiste un purge implicito.

Se un update Fedora cambia il PAM vendor, status/update/rollback falliscono con
`plasmalogin_vendor_pam_drift`: riesaminare il nuovo file e costruire una nuova
installazione. L'uninstall resta consentito solo se l'override gestito è ancora
byte-identico allo state e non modifica il nuovo vendor.

Se il login grafico non è raggiungibile, usare una console testuale o lo
snapshot e lanciare `manage.sh uninstall`. In caso di drift, il gestore fallisce
chiuso. Raccogliere soltanto `manage.sh status`, `systemctl status
fprintd.service --no-pager`, `journalctl -b -u fprintd.service --no-pager` e
`getenforce`. Non allegare `/var/lib/goodix-5125-poc`, `/var/lib/fprint`,
capture USB, template o secret.

## 7. Sequenza minima per la Human Gate correttiva

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
