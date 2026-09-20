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

Polkit/Discover has a service-local, interruptible fingerprint PAM bridge,
qualified offline and pending live acceptance. It preserves immediate password
submission, requires an explicit empty-field submission for each fingerprint
choice, and bounds choices across restarted dialogs. The installer owns its PAM
files, tmpfiles entry and narrow socket-helper drop-in; it enables no global
authselect feature. See `production/polkit/README.md` for supported versions,
file ownership, cancellation semantics and counter lifetime.

The clean candidate now establishes service-local sudo and sudo-i fingerprint
support, qualified offline and pending live validation. It uses a password-first
native prompt, explicit fingerprint choices, at most three per invocation and an
8-second overall ceiling per choice. It does not depend on D285 or modify
system-auth/authselect/sudoers. See `production/sudo/README.md` and the operator
handoff `AUTHENTICATION-LIVE.md`. Existing development overlays are refused.

Managed releases without either `POLKIT_INTEGRATION=INTERRUPTIBLE_SERVICE_LOCAL_V1`
or `SUDO_INTEGRATION=PASSWORD_FIRST_SERVICE_LOCAL_V1`
require uninstall using their original manager, then a fresh install. New
versions with this integration keep the same host rules and pair the bridge
binary through `current`; update and rollback preserve the attempt counters.
Uninstall restores original Polkit PAM presence and removes the new files.

The complete candidate includes libfprint, the paired fprintd/PAM extension,
greeter parent/drop-in, login/KScreenLocker/Polkit/sudo PAM integrations and account-delete protection.
Prepared login permits up to three explicit physical attempts (8 s each),
stopping on MATCH, error/timeout, or the third NO MATCH before password fallback; sudo uses its separate explicit-choice bridge and KScreenLocker retains its qualified service path. Runtime
versions switch together on update/rollback. The greeter integration applies
on its next normal startup; the manager never restarts Plasma.

Pre-early-login releases require uninstall followed by a fresh install, with
materials/templates preserved. Development overlays and custom unit overrides
are rejected. See the installation guide for exact prerequisites and recovery.

An existing combined managed installation with both integration fields and the same host rules uses
`prepare` then `update`; `rollback` restores its previous complete candidate.
A previous one-attempt managed installation must first be uninstalled using
its original version of `manage.sh`, then freshly installed with this version.
Updating it in place is rejected before host changes: the old manager has only
one saved PAM rule, so it cannot safely switch that rule on rollback. Materials
and templates are preserved by uninstall. A fresh managed install uses
`install`, with `uninstall` as its inverse. Existing
development overlays must use their separate follow-up; do not install this
managed candidate over them. The three-contact manual cases are one non-matching
finger then a matching finger, two non-matches then a match, and three non-matches
then password, each in a separate normal login. Stop at the first MATCH and never
make a fourth contact. FAIL/timeout/regression requires rollback; retain on PASS.

If a partial install reports `POLKIT_ROLLBACK_FAILED`, stop and report that
message. Runtime and recovery metadata are retained instead of deleting a
module still referenced by PAM. Close authentication dialogs and preserve the
checkout for targeted recovery; do not delete the retained files manually.
