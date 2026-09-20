# Post-live Polkit recovery / Plasma VT corrective — 21 September 2026

Baseline: `development`, clean at
`d7de50585d555b1ca676e4fcf6c9ed77cc20d601`. No new D-number or policy change.
Review surface: Git diff, modified production/deployment/migration code, tests,
operator README, source hashes, licensing ledger and current manual section.

## Evidence and classification

The human reported PASS for install/status, sudo and sudo-i password/fingerprint,
Polkit password/fingerprint, sudo/Polkit NO-MATCH→password and cancel→password,
and KScreenLocker password/fingerprint. Those are real results for d7de505.

The Plasma logout attempt is **INVALID / PROCEDURE-INDUCED VT CONFLICT**:
recovery occupied tty1; Plasma Login exited 23. Candidate password/fingerprint
login remains **PENDING LIVE**, not FAIL. After complete restore and removal of
the old recovery console, the human restarted Plasma Login and obtained a
post-recovery password PASS. No offline check substitutes for either new login.

The observed counter was root:1000, regular 0600, nlink 1, one byte `0`, inside
root:root 0700. The first uninstall rejected its GID after changing PAM files.
The human's qualified GID-only repair allowed full restore. Local read-only
stat confirms the helper is root:root 4755, without setgid. The
[Polkit 127 helper](https://github.com/polkit-org/polkit/blob/127/src/polkitagent/polkitagenthelper-pam.c)
does not set egid before PAM. Inherited egid plus missing fchown explains the
inode. This reconstructs the mechanism; it is not a captured live helper trace.

Read-only host checks as guido found Plasma Login 6.7.5-1.fc44 active, recovery
inactive, logind NAutoVTs=6 and ReserveVT default 6, KDE tty2 and another session
tty3, no tty1/tty12 controlling processes and no tty12 getty. The vendor service
explicitly conflicts with getty tty1. The actual `vt_platform()` function passed
on this host without opening a VT or changing a service.

The matching [KDE v6.7.5 Display.cpp](https://github.com/KDE/plasma-login-manager/blob/v6.7.5/src/daemon/Display.cpp)
prefers the initial VT if not occupied in logind, allocates new session VTs with
VT_OPENQRY and exits 23 after repeated ttyFailed. Its
[UserSession.cpp](https://github.com/KDE/plasma-login-manager/blob/Plasma/6.7/src/helper/UserSession.cpp)
takes the controlling terminal with TIOCSCTTY. An openvt root shell is not a
logind session, explaining the old mismatch. An open tty12 is excluded from
free-VT allocation; the new console neither occupies nor switches to tty1.
Local openvt(1) confirms `-c`, no `-f`, no `-s`, and `-w` behavior.

## Implementation and PM review

- Fresh O_EXCL counters get fchown(0,0), checked again before initialization.
  Failed initialization removes only the newly created, identity-checked inode
  instead of stranding a zero-byte file. Existing foreign/corrupt counters stay untouched; fingerprint fails closed
  while password PAM remains available. Special files are rejected before open.
- Uninstall qualifies the complete runtime directory, local identity set,
  owner/group/mode/type/link count/content/attributes, state and temporary names
  before its first mutation. Counter locks remain held throughout removal.
- Historical GID compatibility requires the exact old module digest and
  guido/1000 with primary GID 1000. Status/update reject that noncanonical GID;
  uninstall is the bounded compatibility path. No general GID relaxation.
- Handled I/O failures restore the original owned file set, counters and state,
  including mode/owner/labels/mtime. Public PAM entries are restored last.
  This is not whole-host transactional recovery against kill, power loss,
  persistent storage failure or concurrent root writers.
- Review found an earlier mutation in managed `verify_active`: legacy 0700
  runtime directories were repaired before guard validation. Uninstall now
  refuses that drift without changing permissions; status behavior is retained.
- Recovery uses explicit tty12 without force/switch. Read-only `login-check`
  proves the root bash child is there, tty1 is unclaimed, logind/getty contract
  still matches, `/run/gx` metadata is intact, and Plasma Login is active.
  It reports the actual logout/greeter outcome as PENDING_LIVE.
- Authenticated rearm accepts complete pinned f97de44 and d7de505 snapshots,
  preserving originals/archives and the current saved recovery path.
- Operator review: preparation/install/rearm and normal recovery are Konsole
  copy-paste; tty12 is emergency only, with `/run/gx`. No old tty1 procedure
  remains in current instructions. A recovery console is retained through both
  candidate login attempts and the post-restore password login.

PM review was a separate read-only phase by the same agent, treating the work
as an external change and checking the actual diff/tests; no second agent was
used. The permission-repair and update-contract findings were corrected and
rechecked. Decision: **ACCEPT_AND_CONTINUE** to final candidate sealing, then
**HUMAN_REQUIRED / LIVE_RETEST**. No root/live authority follows from this review.

## Offline validation

All processes ran unprivileged. Actual libpam with synthetic leaf modules,
private D-Bus and synthetic devices are distinct from real authentication.

| Check | Result |
|---|---|
| Polkit real-libpam conversation suite | 19 PASS normal, 19 PASS ASan/UBSan |
| Polkit deployment suite | 19 PASS, no skipped required tests |
| Migration / full install-status-uninstall / historical restore | 26 PASS |
| Launcher / VT / real saved recovery in synthetic tree | 23 PASS |
| RPM metadata / rearm, including both historical snapshots | 14 PASS |
| Managed lifecycle | 31 PASS |
| Combined native sudo/Polkit PAM | 3 PASS |
| Protocol/lifecycle/private-bus daemon/greeter | PASS normal and sanitizer |
| Real host VT-platform read-only qualification as guido | PASS; no console created |
| Two independent Polkit production builds | Byte-identical; exports/RPATH/test-hook checks PASS |

The deployment suite includes production `open_guard()` with virtual root
metadata and inherited egid 1000, explicit canonicalization and fchown failure;
the real unprivileged result is then uninstalled. Historical compatibility uses
the preserved exact d7 module, not a mock digest. Wrong UID/GID tests virtualize
stat metadata because no root execution is permitted. Mode, symlink, hardlink,
FIFO, invalid bytes/size, unknown UID, extra entry and attributes are real
temporary filesystem fixtures. Every rejection checks zero file/action change.

The complete managed test injects a corrupt counter after candidate activation:
uninstall fails without changing any path, including the action log; after the
fixture is corrected, the saved manager removes the candidate and migration
rollback restores the historical state. sudo has no persistent runtime counter;
its PAM-handle state and cross-consumer isolation are covered by native PAM tests.
Handled failures at unlink, daemon-reload and final directory removal restore
the original active Polkit/sudo file set and counter before propagating failure.

Useful reproduction inputs (no root):

```bash
GOODIX_PAM_TEST_HEADERS=/tmp/goodix-combined-migration-ready/build/polkit/headers/usr/include \
GOODIX_HISTORICAL_POLKIT_MODULE=/tmp/goodix-polkit-historical-d7.so \
python3 -B production/polkit/test_deploy.py
GOODIX_MIGRATION_TEST_CANDIDATE=/tmp/goodix-combined-migration-ready/candidate \
python3 -B development/migration/patched-host-to-combined/test_migration.py
```

The old module is a public-software binary preserved privately in /tmp and
verified as SHA `9de3aba169b78298e539df1320f9bb10d64d418b6dd3ece196dcc401f1b7e3c2`.
The new module's two preliminary production builds both hash to
`e51b0fa8652d0f9ca94b6095320dcb9eb1aa7c49c262866165f6f7a4a93f11d0`.
Full final candidates must be regenerated after the clean commit in the two
canonical delivery directories and compared byte-for-byte; the receipt covers
the candidate, recovery policy and all tracked operator/deploy/PAM sources.
The final handoff reports those post-commit checks and full HEAD, avoiding a
circular commit hash inside its own source documentation.

## Remaining human boundary

Only: corrected install, Polkit password/fingerprint smoke, read-only VT check
before each logout, Plasma password and fingerprint, real recovery even on PASS,
then post-restore password login. No repetition of the full passed matrix.
If the same failure recurs, stop and inspect the actual counter or VT error;
do not broaden metadata exceptions or repeat an equivalent third attempt.
No agent root/sudo/pkexec, USB, sensor commands, protected-material reads,
template/enrollment changes, firmware changes or public-repository operation.
