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
cases. Three choices, or a corrupt count, require password authentication;
successful authentication **and account checks** reset the count. A MATCH ends
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

`/run/polkit/goodix-fingerprint` is root:root 0700, with numeric files 0600.
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
unchanged. The Polkit C bridge/counter design does not require modification.
The shared deploy transaction adds sudo ownership in managed schema 2 and fixes
recovery after an interrupted removal has already deleted a parent directory.
Managed pre-sudo states require their original uninstall before a fresh install.
The standalone local Polkit patch stays schema 1 and does not alter sudo.

The candidate daemon now makes ordinary consumer retry errors terminal too.
Independent PAM tests and real-daemon private-bus tests cover budget separation,
BUSY, owner cancellation and no implicit reopen. The development PC's D285 path
remains untouched and is not a candidate prerequisite. The local Polkit patch
remains uninstalled. Follow the combined operator handoff for the later live gate.
