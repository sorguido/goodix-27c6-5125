# D294/01 — prima candidate RPM runtime Phase C

Data: 14 settembre 2026
Stato: `READY_FOR_HUMAN_GATE`
Live/USB/sudo eseguiti dall'AI: `false`

## Boundary

Il primo slice Phase C trasforma la sola selezione runtime D293 in un RPM
Fedora package-managed. Non tenta ancora di impacchettare ogni integrazione
host: D293 e la guard B5 restano installate e intatte come rollback già
validato. Il pacchetto aggiunge percorsi nuovi e una drop-in systemd `99` che
prevale sulla `95` D293; rimuovendolo, systemd torna alla baseline precedente.

Il package non contiene materiali protetti, template, firmware, PAM o file
vendor. La libreria privata viene costruita dalla source-of-truth `production/`
e deve restare byte-identica dentro l'RPM. Le dipendenze runtime Fedora sono
esplicite e pinned alle versioni del target: fprintd/libfprint, libgusb e i
quattro componenti OpenCV 4.13. Gli RPM locali `opencv-features2d` e
`opencv-flann`, assenti sul target ma già hash-pinned nel repository, vengono
installati solo se necessari e rimossi dal rollback solo se non preesistevano.

## Consumer e PAM

Questo slice attiva il medesimo fprintd D293 e non cambia la selezione dei
consumer. In particolare non modifica `/usr/lib/pam.d/plasmalogin`, authselect,
KScreenLocker, sudo, Polkit o timeout. Il ritardo di circa 30 secondi per
password fallback degli utenti enrolled resta il limite UX accettato e non è
oggetto di un corrective.

## Artefatti

```text
packaging/d294-phase-c-runtime/
  goodix-27c6-5125-runtime.spec.in
  goodix-27c6-5125-fprintd-wrapper
  99-goodix-27c6-5125-runtime.conf
  build-rpm.sh
  install.sh
  uninstall.sh
  test_offline.py
  README_TEST_LIVE.md
```

L'RPM possiede soltanto `/usr/lib64/goodix-27c6-5125`, il wrapper sotto
`/usr/libexec`, la drop-in sotto `/etc/systemd/system` e documenti/licenze.
Build e install entrypoint richiedono branch `development` pulito e allineato
a `origin/development`; l'installer usa la candidate ignorata `dist/` se
corrisponde all'HEAD oppure la ricostruisce quando `rpmbuild` è disponibile.
Il package espone il commit sorgente completo come capability RPM.
L'installazione conserva in uno state root-only il precedente stato del
servizio, l'hash della unit effettiva, gli hash D293/B5 e la preesistenza delle
due dipendenze aggiunte. La sezione privilegiata ricontrolla Git e provenance,
congela l'RPM in un file root-only e disabilita i repository nella transazione
locale. Failure post-mutazione attiva cleanup e ripristino del servizio; il
rollback usa una singola transazione `rpm -e` limitata ai package esatti e
prova il ripristino byte-identico della baseline D293/B5 e della unit.

## Build RPM e verifica offline

```text
FIRST_RPM_BUILD_SOURCE_COMMIT=c013f02d09c9e1c5625684b9880b9e389dae2248
D294_01_RPM_BUILD=PASS
D294_01_PACKAGED_LIBRARY_BYTE_IDENTICAL=true
D294_01_PAM_FILE_COUNT=0
D294_01_PROTECTED_MATERIAL_FILE_COUNT=0
python3 packaging/d294-phase-c-runtime/test_offline.py --rpm <rpm> = 12 PASS
bash -n build/install/uninstall/wrapper = PASS
git diff --check = PASS
RPM_DIGEST_VERIFY=PASS
RPM_PAYLOAD_QUERY=PASS
RPM_INSTALL_ROOTFS=NOT_EXECUTED_UNPRIVILEGED_CHROOT_DENIED
REAL_USB_ACCESS=0
SUDO_BY_AI=0
PAM_FILE_CHANGE_COUNT=0
```

La prima esecuzione RPM ha esposto soltanto un helper `rpmuncompress` assente
nel toolchain temporaneo estratto; completato il toolchain, la sandbox annidata
ha negato `bwrap`. La stessa build è quindi stata ripetuta offline nel contesto
consentito ed è PASS. Questi sono limiti dell'ambiente di build, non failure
del package o del runtime. Una transazione `rpm --root` non è eseguibile dal
namespace non privilegiato perché RPM richiede il cambio root; payload,
metadata, digest e byte identity sono invece verificati senza privilegi.

La review PM ha richiesto e riesaminato nello stesso D294/01 i controlli
privilegiati duplicati, il freeze root-only, le collision check, il pin delle
dipendenze preesistenti, il rollback atomico e l'hash della baseline. La live è
stata ridotta al normale login Plasma: una sola serie telemetrata e bounded di
massimo tre tentativi, stop al primo MATCH e nessun `fprintd-verify` aggiuntivo.
Non esiste altro avanzamento offline necessario prima dell'installazione reale.

```text
CURRENT_PHASE=C
CURRENT_TASK=D294_01_PHASE_C_RUNTIME_PACKAGE
OUTCOME=READY_FOR_FACTORY_PRESERVING_LIVE
EXECUTABLE_CLOSURE=PASS_OFFLINE_MAXIMUM
RESIDUAL_BLOCKER_OR_RISK=PACKAGE_INSTALLATION_AND_TARGET_WORKFLOW_REQUIRE_SUDO_AND_REAL_SENSOR
NEXT_BOUNDARY=D294_01_PACKAGE_LIVE_VALIDATION
PM_DECISION=HUMAN_REQUIRED
```
