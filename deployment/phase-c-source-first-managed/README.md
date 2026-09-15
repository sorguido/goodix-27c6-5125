<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Phase C source-first managed install

Questo percorso sostituisce D294 come modello ufficiale. `prepare.sh` costruisce
la runtime dalla source-of-truth `production/`; `manage.sh` espone prepare,
install, update, status, rollback, uninstall e import separato dei materiali.

La runtime è versionata per commit e dispone di un solo slot di rollback. Lo
state e gli hash impediscono rimozioni ampie o non attribuibili. Il wrapper usa
fprintd Fedora, verifica metadata root-only dei cinque input protetti e non ne
stampa contenuto o digest. La guard account-deletion e la policy SELinux sono la
copia production del comportamento D293/B5 già provato sul target.

La root runtime è creata esplicitamente root-owned `0755`. La transazione
privilegiata normalizza soltanto installazioni legacy root-owned `0700` prima
della verifica; symlink, ownership o modi diversi falliscono chiuso. `status`
passa per la stessa transazione privilegiata perché la readiness dei materiali
`0700/0600` non è osservabile correttamente dal frontend non root.

Il correttivo Plasma Login Manager include soltanto la regola dichiarativa
`plasmalogin-pam.rule`. La transazione verifica il file PAM package-owned,
genera `/etc/pam.d/plasmalogin` preservando tutte le righe vendor e inserisce
`pam_fprintd.so` come `sufficient` immediatamente prima di `password-auth`.
Hash vendor/override, stato corrente e precedente rendono install, migrazione,
rollback e uninstall simmetrici. Un drift vendor blocca status/update/rollback;
uninstall può comunque rimuovere l'override integro ed esporre il nuovo vendor.

Il correttivo pre-Phase-F KScreenLocker mantiene separato il diverso modello
Fedora: `kde-fingerprint` è già `/etc/pam.d/kde-fingerprint`, posseduto da
`plasma-workspace` come `%config(noreplace)`, e non ha una copia sotto
`/usr/lib/pam.d`. La transazione verifica package owner, flag RPM, digest,
layout e metadata; salva l'originale e sostituisce soltanto la riga auth
`substack fingerprint-auth` con `pam_fprintd.so max-tries=3 timeout=45`.
Install/update/rollback/uninstall conservano copie root-owned hash-pinned e
ripristinano byte-per-byte il file precedente. Customizzazioni preesistenti,
drift RPM/PAM e `.rpmnew`/`.rpmsave` falliscono chiuso; `fingerprint-auth` e
authselect non vengono modificati.

Test offline:

```bash
python3 deployment/phase-c-source-first-managed/test_offline.py
```

Ogni candidate include inoltre `SBOM.spdx.json` (SPDX 2.3 JSON), i notice
terzi, i testi GPL-3.0/Apache-2.0 e il corpus licenze OpenCV estratto dai
cinque RPM hash-pinned. `MANIFEST` dichiara il regime del combined binary e
`SHA256SUMS` copre anche questi metadati di release; nessuno di essi contiene
materiale protetto o dati biometrici.

Guida utente: `docs/PHASE_C_SOURCE_FIRST_INSTALL.md`.

D295/02 è PASS live per update, vendor PAM invariato, password, login
fingerprint Plasma e `sudo`. D295/03 è PASS live con sensore scollegato per
rollback bidirezionale, uninstall, preservazione di materiali/template e
recovery/reinstall. Phase C è chiusa e la baseline finale nella VM è
`448f5c8cc6099032a23115a96e90428d75b74a7b`. Il correttivo KScreenLocker è
coperto offline ma richiede ancora la Human Gate sulla sessione KDE reale.
