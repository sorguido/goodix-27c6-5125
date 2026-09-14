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

La logica è chiusa offline, ma l'installazione privilegiata in una VM pulita non
è ancora stata eseguita. Tutti i comandi con `sudo`, l'import dei materiali e
l'accesso al sensore sono azioni dell'Utente dopo Human Gate. Il primo test va
fatto nella VM Fedora 44 KDE, non sul laptop già validato.

Il gestore installa una runtime immutabile per commit sotto
`/usr/lib64/goodix-27c6-5125/`, un wrapper fprintd, un drop-in systemd e la guard
account-deletion B5 con policy SELinux. Non usa `/usr/local`, RPM D294, operator
kit Dxxx, firmware o configurazioni per singolo utente. Non modifica PAM.

## 1. Preparazione della VM

Installare Fedora 44 KDE x86_64, applicare gli aggiornamenti e creare uno
snapshot a macchina spenta. Non collegare ancora il sensore.

```bash
sudo dnf5 install git flatpak cpio patch binutils rpm-build dnf5-plugins \
  fprintd libfprint libgusb selinux-policy-targeted policycoreutils-devel
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
grep -E '^(PHASE_C_DISTRIBUTION_MODEL|RPM_OFFICIAL_DISTRIBUTION|SOURCE_COMMIT|PROTECTED_MATERIAL_INCLUDED)=' \
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

## 4. Installazione gestita — Human Gate

Questo è il primo comando che modifica systemd/SELinux e richiede `sudo`:

```bash
deployment/phase-c-source-first-managed/manage.sh install \
  "$HOME/goodix-phase-c-candidate/candidate"
deployment/phase-c-source-first-managed/manage.sh status
systemctl cat fprintd.service
```

Attesi: `PHASE_C_INSTALL=PASS`, commit corrente,
`PROTECTED_MATERIAL_READY=true`, `PHASE_C_STATUS=ACTIVE` e wrapper
`/usr/libexec/goodix-27c6-5125/fprintd-wrapper`. Una seconda installazione della
stessa candidate risponde `PHASE_C_INSTALL=PASS_ALREADY_CURRENT`.

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
quarto tentativo. La configurazione PAM della Fedora pulita va prima osservata.
Se il login fingerprint non è offerto, fermarsi e raccogliere solo configurazione
e journal sanitizzati: non editare manualmente `/usr/lib/pam.d/plasmalogin` e
non abilitare authselect per tentativi.

## 6. Update, rollback, uninstall e recovery

```bash
deployment/phase-c-source-first-managed/manage.sh update /percorso/assoluto/candidate
deployment/phase-c-source-first-managed/manage.sh rollback
deployment/phase-c-source-first-managed/manage.sh uninstall
```

Il gestore conserva un solo commit precedente. Un secondo update fallisce con
`rollback_slot_occupied`, senza eliminare versioni. Rollback scambia i due
commit. Uninstall ripristina fprintd Fedora e preserva deliberatamente materiali
protetti e template fprintd; non esiste un purge implicito.

Se il login grafico non è raggiungibile, usare una console testuale o lo
snapshot e lanciare `manage.sh uninstall`. In caso di drift, il gestore fallisce
chiuso. Raccogliere soltanto `manage.sh status`, `systemctl status
fprintd.service --no-pager`, `journalctl -b -u fprintd.service --no-pager` e
`getenforce`. Non allegare `/var/lib/goodix-5125-poc`, `/var/lib/fprint`,
capture USB, template o secret.
