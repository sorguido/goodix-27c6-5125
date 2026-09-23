<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R5 removal commands

This patch adds `goodix-uninstall` and `goodix-force-remove` to `/usr/local/bin`,
plus `/usr/local/share/goodix-recovery/receipt.json`. Each command is a complete
copy of `remove.py`; emergency removal has no helper, repository, build, receipt
or vendor PAM dependency. Existing R3/R4 binaries remain unchanged.

**Human-only, VM-only deployment.** From the clean `development` repository root,
with the integrated reader continuously present, a working desktop and ordinary
sudo credentials (allow the stock fingerprint prompt to reach password):

```bash
./deployment/recovery/install.sh
```

The script asks for sudo itself. Expect `GOODIX_RECOVERY_INSTALL=PASS`, then
`command -v goodix-uninstall` and `command -v goodix-force-remove` must resolve
to `/usr/local/bin`. It does not inspect USB, stop services or change authentication.
It refuses collisions/drift and undoes newly created files on installation
failure. Repeat with identical files is harmless. Stop on any error.

To undo **only this tools patch**, keeping the installed R3/R4 baseline:

```bash
./deployment/recovery/uninstall.sh
```

This inverse checks its own receipt/hashes, removes only the two commands and
receipt directory, and reports `GOODIX_RECOVERY_ROLLBACK=PASS`. Keep successful
tools installed until the agreed full-removal test. This tooling inverse is
different from the full normal uninstall command, `goodix-uninstall`.

- [End-user removal and emergency instructions](../../../../../docs/UNINSTALL.md)
- [Exact end-user reinstall procedure](../../../../docs/R5_INSTALL.md)
- [R5 VM sequence, PASS/FAIL/STOP and evidence to return](../../../../deployment/recovery/R5_VM.md)

Offline checks, without privileges or host service operations:

```bash
python3 -B deployment/recovery/test_remove.py
python3 -B deployment/recovery/test_manage.py
python3 -B deployment/plasma-login-opt-in/test_manage.py
```

The removal tests cover normal complete/vendor-missing/drift refusal; emergency
complete/vendor-missing/missing-receipts/partial runtime/partial login;
active/inactive fprintd; missing repository/build; repeat; preserved material,
template and Fedora sentinels; redirected paths and incomplete cleanup.
The installer tests exercise executable standalone copies, cwd-independent
invocation, privilege dispatch, collisions and symmetric tools-only rollback.
Reader-presence fixtures, verified temporary activation masks and no automatic
service start are covered. Service, sudo, SELinux and root ownership are simulated. Real VM qualification
remains pending; these results do not assert host/runtime behavior.
