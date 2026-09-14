# D294/01 — prima candidate RPM runtime Phase C

Data: 14 settembre 2026
Stato: `IMPLEMENTED_STATIC_REVIEW_PASS_RPM_BUILD_PENDING`
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
Il package espone il commit sorgente completo come
capability RPM. L'installazione conserva in uno state root-only il precedente
stato del servizio e la preesistenza delle due dipendenze aggiunte. Failure
post-mutazione attiva cleanup e ripristino del servizio; il rollback riattiva
D293 anche se fallisce la pulizia di una dipendenza.

## Verifica prima del build reale

```text
python3 packaging/d294-phase-c-runtime/test_offline.py = 8 PASS + 2 SKIP_RPM_NOT_BUILT
bash -n build/install/uninstall/wrapper = PASS
git diff --check = PASS
RPM_BUILD=NOT_YET_EXECUTED
RPM_INSTALL_ROOTFS=NOT_YET_EXECUTED
REAL_USB_ACCESS=0
SUDO_BY_AI=0
PAM_FILE_CHANGE_COUNT=0
```

Il build reale deve essere eseguito dopo il commit di questi sorgenti, perché
la provenance rifiuta worktree sporco o HEAD non pubblicato. Dopo build e test
del payload, la review PM decide eventuali corrective prima del Human Gate.

```text
CURRENT_PHASE=C
CURRENT_TASK=D294_01_PHASE_C_RUNTIME_PACKAGE
OUTCOME=IMPLEMENTED_STATIC_REVIEW_PASS_RPM_BUILD_PENDING
EXECUTABLE_CLOSURE=PARTIAL_RPM_BUILD_PENDING
RESIDUAL_BLOCKER_OR_RISK=REAL_RPM_BUILD_AND_ROOTFS_TRANSACTION_NOT_YET_PROVEN
NEXT_BOUNDARY=D294_01_RPM_BUILD_OFFLINE
PM_DECISION=ACCEPT_AND_CONTINUE
```
