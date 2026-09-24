<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Standalone removal commands

The root [installer](../../docs/INSTALLATION.md) installs complete copies of
`remove.py` as `/usr/local/bin/goodix-uninstall` and
`/usr/local/bin/goodix-force-remove`, with a receipt under
`/usr/local/share/goodix-recovery/`. Neither command imports code from the clone
or needs a build directory after installation.

Normal removal verifies project-owned software. Emergency removal follows a
fixed inventory and tolerates missing receipts or partial installation. Both
remove authentication entry points before runtime files, quiesce fprintd during
runtime mutation and retain protected materials and fingerprint templates.
The reader remains connected. Fedora's current configuration is exposed without
restoring old vendor files.

Use [Uninstall and emergency recovery](../../docs/UNINSTALL.md) for the normal
command, console prompts, removal scope and final restart instruction.

The synthetic removal suite uses temporary fixtures and substitutes privileged
host operations:

```bash
python3 -B deployment/recovery/test_remove.py
```

It is an offline software check, not a hardware or Fedora authentication test.
