<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Managed source installation

`manage.sh` is the supported lifecycle entry point:

```text
manage.sh prepare OUTPUT
manage.sh import-materials SOURCE_DIRECTORY
manage.sh install CANDIDATE
manage.sh update CANDIDATE
manage.sh status
manage.sh rollback
manage.sh uninstall
```

Run the entry point as the regular desktop user. It invokes `sudo` only for
the narrow host transactions that require root. `prepare` is always
unprivileged and requires a clean committed source checkout.

Runtime versions are immutable and named by source commit. The manager keeps a
single rollback slot, verifies every candidate file, and fails closed on PAM,
package, metadata, or state drift. It generates the Plasma Login override from
Fedora's verified vendor file and preserves a byte-exact recovery copy of KDE's
package-owned fingerprint PAM file.

Uninstall restores the Fedora runtime and PAM state. It deliberately preserves
device-specific protected material and fprintd templates. See
`docs/INSTALLATION.md` for prerequisites, safety conditions, and recovery.

Run the host-only transaction tests with:

```bash
python3 deployment/managed-install/test_offline.py
```
