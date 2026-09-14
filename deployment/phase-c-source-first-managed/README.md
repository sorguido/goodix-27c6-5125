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

Test offline:

```bash
python3 deployment/phase-c-source-first-managed/test_offline.py
```

Guida utente: `docs/PHASE_C_SOURCE_FIRST_INSTALL.md`.
