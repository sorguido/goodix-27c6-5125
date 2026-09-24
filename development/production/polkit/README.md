<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Interruptible Polkit fingerprint conversation

This independent GPL-2.0-or-later PAM module is restricted to Fedora's
`polkit-agent-helper-1`, service `polkit-1`, local non-root identities and a
pipe/socket conversation. It leaves password verification to the existing PAM
stack and fingerprint verification to Fedora's unmodified `pam_fprintd.so`.
No KDE/Polkit code is copied or patched. No sensor protocol is implemented here.

The initial password request accepts a password immediately. An empty response
selects one fingerprint attempt. The child starts a separate PAM handle with
the fixed service `goodix-polkit-fingerprint`, `max-tries=1 timeout=45`, and an
information-only conversation callback. It neither inherits nor requests a
password. The parent observes input and child completion, with a 45-second
overall ceiling. Input, EOF, failure or expiry terminates/reaps the child and
allows the normal password stack to proceed. Parent death also kills the child.

The stdin check uses public stdio functions with temporary nonblocking mode:
the upstream helper can buffer a password while reading the cookie or the empty
response, so `poll(fd)` alone would miss it. A peek is returned to the stream;
password bytes are not copied to a log or retained by this module. PAM owns the
normal authentication token. Password cancellation may produce a second native
request and KDE's field-clear animation; its appearance remains a live check.

A root-owned runtime counter per local UID permits at most three explicit
fingerprint choices until successful PAM teardown. It spans helper restarts,
dialog cancellation and identity switching back to that UID. A nonblocking
exclusive lock prevents parallel conversations from opening another fingerprint
child. A choice is consumed before forking, including unavailable/error/cancel
cases. Three choices require password authentication; successful authentication
**and account checks** reset a valid count. A corrupt/foreign counter disables
fingerprint and is preserved even after password success. A MATCH ends
the series. This is a conservative limit on choices, not a measured physical
contact counter; existing driver action/fencing telemetry remains authoritative.
The counter is an operational limit, never an authorization credential. Reboot
clears it. Update/rollback preserve it; uninstall removes it with the integration.

The parent's return does not assert instant termination of all daemon I/O.
fprintd's owner-loss handler cancels a running Verify, drains the action, closes
the device and clears the session. Ordinary Claim opens with a NULL cancellable:
an already pending open completes and is then closed. Password processing does
not wait for that cleanup. Tests exercise these actual daemon handlers over a
private bus, with only device operations replaced by synthetic functions.
Target cleanup/reseal still needs the operator's real workflow observation.

## Supported deployment

`deploy.py` is the shared closed-set file transaction for local and managed
installation. It accepts only the audited Fedora local password auth stack,
Polkit 127-2.fc44.2, KDE Polkit 6.7.5-1.fc44, fprintd-pam 1.94.5-5.fc44 and
PAM 1.7.2-2.fc44. It checks stock component hashes and refuses custom Polkit
PAM, pending rpmnew/rpmsave, unsupported auth factors and global fingerprint.
A byte-identical vendor copy already in `/etc/pam.d/polkit-1` is preserved.
Account/password/session lines come from the verified vendor file. Required
environment/failure-delay modules precede the bridge; password fallback retains
the original system-auth include. A missing/unloadable bridge still falls through
to password authentication; it cannot grant authentication. Global authselect is unchanged.

The owned files are `/etc/pam.d/polkit-1`,
`/etc/pam.d/goodix-polkit-fingerprint`, `/etc/tmpfiles.d/goodix-polkit.conf`, and
`/etc/systemd/system/polkit-agent-helper@.service.d/50-goodix-polkit.conf`.
Recovery metadata lives in `/var/lib/goodix-polkit`, mode 0700. The local module
lives at `/usr/local/lib64/goodix-27c6-5125/polkit/pam_goodix_polkit.so`; the
managed module lives in the immutable candidate tree through `current`.

`/run/polkit/goodix-fingerprint` is root:root 0700. Each valid local non-root
UID counter is a regular root:root 0600 single-link file containing one byte
`0`–`3`. The setuid helper can retain the caller's egid; fresh O_EXCL counters
are explicitly fchown'ed to 0:0 and rechecked before use. Existing counters are
never silently repaired. A failed initialization removes only the fresh
O_EXCL inode after checking its identity, so a failed fchown cannot strand an
empty counter. Links, special files, wrong owners/groups/modes/links
or invalid contents disable fingerprint while preserving normal password PAM.
Uninstall qualifies the complete directory, locks every counter and checks
state/temporary collisions before its first write. Only the exact historical
module SHA `9de3aba169b78298e539df1320f9bb10d64d418b6dd3ece196dcc401f1b7e3c2`
may recover the authentic guido/1000 counter with primary GID 1000; every other
noncanonical group is rejected. Normal status/update reject that historical
GID until the qualified uninstall; a new runtime cannot inherit the old defect.
Canonical counters use the same local passwd
identity set as runtime. No NSS/network lookup or numeric-name wildcard.
Handled removal I/O errors restore the original Polkit/sudo PAM files, module,
counters and state with metadata, including labels and timestamps. Process kill,
power loss and concurrent root modification are not covered by this in-memory
rollback; retain saved recovery on any STOP.
Fedora's existing `policykit_var_run_t` label supplies the required SELinux
access; no new SELinux grants are added. The narrow socket-helper drop-in adds
only `ReadWritePaths` for that directory because the vendor unit uses
`ProtectSystem=strict`. It does not enable the socket or restart the agent.
Directory creation is recorded; uninstall restores the original PAM presence
and preserves any parent directory subsequently used by other software.
Close authentication dialogs before changing this integration. Remove it before
changing authselect/PAM factors or upgrading beyond the qualified versions.

## Offline checks and provenance

```bash
production/polkit/build.sh /tmp/goodix-polkit-check-build
python3 production/polkit/test_pam.py /tmp/goodix-polkit-check-build/headers/usr/include
GOODIX_PAM_TEST_HEADERS=/tmp/goodix-polkit-check-build/headers/usr/include \
GOODIX_HISTORICAL_POLKIT_MODULE=/tmp/goodix-polkit-historical-d7.so \
python3 production/polkit/test_deploy.py
python3 deployment/managed-install/test_offline.py
```

The build extracts hash-pinned PAM headers without installing packages, links
host libpam, enables RELRO/NOW and stack protection, and checks exports, RPATH
and absence of test hooks. `source.sha256` identifies this separate source set.
The candidate has its own module, manifest field, source hashes and SBOM entry.

PAM tests dispatch through real libpam and real pipes/socket/fork; only password
and fingerprint leaf modules are synthetic. The offline runner substitutes an
unavailable audit socket because the sandbox rejects NETLINK_AUDIT with EPERM,
which real libpam otherwise converts to PAM_SYSTEM_ERR. The production module
retains Fedora auditing unchanged, contains no test environment hooks, and
refuses the test runner. These checks do not establish live authentication.
The complete socket test requires a normal user environment that permits local
socketpair traffic. The Codex sandbox blocks `sendall` on that socket; run the
suite outside that sandbox without root. With the compiler's ASan/UBSan runtime
available, `GOODIX_POLKIT_SANITIZE=1` enables instrumented builds;
`GOODIX_POLKIT_SANITIZER_LIBDIR` can point at temporary extracted runtime
libraries (also add that directory to `LD_LIBRARY_PATH`). The recorded run uses
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1` and `UBSAN_OPTIONS=halt_on_error=1`.

Source review used upstream Polkit 127, Linux-PAM 1.7.2, the repository's pinned
fprintd source and Fedora's exact KDE source RPM:
`polkit-kde-6.7.5-1.fc44.src.rpm`, SHA-256
`2ba0e271420c91623e7ad36c881f70f317f793d99e6ec07301128e556acef616`.
The spec has no downstream patch directives. KDE retries failed conversations
and can recreate a session on identity selection, which does not advance its
retry counter. Hence a per-PAM `max-tries` is insufficient by itself.

## Combined candidate boundary

The clean managed candidate also owns service-local sudo/sudo-i authentication;
see `production/sudo/README.md`. Its password-only system-auth baseline remains
unchanged. The counter metadata corrective below retains the conversation and retry design.
The shared deploy transaction adds sudo ownership in managed schema 2 and fixes
recovery after an interrupted removal has already deleted a parent directory.
Managed pre-sudo states require their original uninstall before a fresh install.
The standalone local Polkit patch stays schema 1 and does not alter sudo.

The candidate daemon now makes ordinary consumer retry errors terminal too.
Independent PAM tests and real-daemon private-bus tests cover budget separation,
BUSY, owner cancellation and no implicit reopen. The development PC's D285 path
remains untouched and is not a candidate prerequisite. The local Polkit patch
remains uninstalled. Follow the combined operator handoff for the later live gate.

## Post-live counter corrective

The d7de505 host run passed password/fingerprint, NO-MATCH fallback and cancel
for Polkit. Its first uninstall failed on root:1000 runtime metadata after
removing some PAM files; a human-qualified GID-only repair allowed complete
restore. The corrected runtime/uninstall contract above addresses that defect.
`test_guard.c` executes production `open_guard()` with syscall metadata doubles
(euid contract 0, inherited group 1000), while the actual process and files
remain unprivileged in /tmp. It checks fchown(0,0), reopened metadata and failure
to normalize; its resulting synthetic counter is consumed by real deploy tests.
Supply the preserved exact historical module for the compatibility test; it
verifies the digest before use. No real root helper is executed by tests.
Upstream [Polkit 127 helper](https://github.com/polkit-org/polkit/blob/127/src/polkitagent/polkitagenthelper-pam.c)
is a behavioral reference: it requires euid 0 but does not change egid before PAM.
The local 4755 root:root executable and the human-observed root:1000 inode
corroborate this creation path; no root-helper credentials were sampled live.
