<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Service-local sudo fingerprint integration

The managed candidate owns the authentication prefix in `/etc/pam.d/sudo` and
the leaf `/etc/pam.d/goodix-sudo-fingerprint`. It leaves the vendor account,
password and session rules intact. Fedora's unchanged `/etc/pam.d/sudo-i`
includes `sudo`, so ordinary interactive sudo **and sudo -i** are in scope.
No sudoers file, global system-auth or authselect feature is changed. Existing
sudo authorization, timestamp caching, account checks and run-as policy remain
the application's responsibility; fingerprint is an authentication method only.
All local non-root PAM identities are eligible, with no installer-user binding.
Network identities and noninteractive/redirected-input fingerprint are outside
the supported claim. The production bridge requires `/usr/bin/sudo`, effective
root, service sudo/sudo-i and a terminal on stdin; otherwise password PAM remains.

## Conversation and bounds

The first native sudo prompt accepts the password immediately, or Enter to
select one fingerprint attempt. Each explicit selection has an **8-second total
ceiling**, including daemon startup, Claim and verification. Password input is
available at the initial prompt and between completed NO MATCH attempts. It is
not offered concurrently during the selected 8-second fingerprint interval:
wait for the next prompt before typing a password. Ctrl+C cancels authentication.
This is intentionally different from Polkit's pipe protocol, not a claim of
simultaneous terminal password/fingerprint input. No tty read, input peek,
terminal-mode change or replacement signal handler is added by the bridge.

Only a completed NO MATCH permits another explicit Enter. At most three choices
are possible in one sudo PAM handle; sudo reuses that handle across its own
password retries, so `passwd_tries` cannot multiply the fingerprint budget.
MATCH stops immediately. Error, timeout, missing enrollment, BUSY/Claim failure,
or selecting a password disables further fingerprint attempts for that handle.
The next sudo invocation has its own budget. No Polkit counter is opened,
consumed or reset. An account failure still denies the request after MATCH.

The child uses an information-only PAM conversation and never receives or asks
for a password. Parent cancellation/timeout kills and reaps it, triggering the
daemon's existing D-Bus owner-loss cleanup; parent death also kills the child.
sudo blocks SIGINT/SIGQUIT around authentication: the parent observes pending
signals without consuming them or altering sudo's mask/handlers. A kernel-stuck
child cannot stall password processing: reaping is bounded to 100 ms, retried
at PAM cleanup, and no further fingerprint child is then allowed. Daemon cleanup
is asynchronous; a concurrent consumer can receive BUSY until cleanup completes.
This does not assert that target USB cleanup is instantaneous.

`pam_sm_setcred` acknowledges a no-op because the bridge creates no credentials.
This preserves sudo's normal post-authentication PAM credential lifecycle when
it changes PAM_USER to the run-as identity. It does not authenticate a user.

## Module choice and shared daemon

The leaf uses the hash-pinned **Fedora `/usr/lib64/security/pam_fprintd.so`**,
`max-tries=1 timeout=8`, just like the ordinary-Claim consumer boundary used by
Polkit and KScreenLocker. Source inspection proves this module checks enrolled
prints before Claim and returns unavailable on empty enrollment/Claim failure.
Its single-try loop issues no second VerifyStart. The candidate PAM modification
adds ClaimLogin only for `plasmalogin`; sudo needs none of that private ABI.
Therefore pairing the sudo leaf to the candidate PAM would add a dependency
without changing sudo behavior. Stock PAM remains package/hash checked during
install/update/status; candidate bridge and daemon switch together through
`current`, while the fixed leaf and its stock dependency remain identical.

The candidate daemon is built for the sole Goodix production driver.
`production/login/fprintd-consumer-retry.patch` makes FP_DEVICE_RETRY terminal
for ordinary Verify/Identify too, extending the existing prepared-login rule.
This removes the daemon's implicit retry callback; the driver's existing
poison/fence and explicit-action checks remain unchanged. No sensor command or
enrollment behavior is added. Live cleanup and combined desktop UX remain pending.

## Deployment and recovery

`production/polkit/deploy.py` owns both integrations in one managed transaction
(managed schema 2; the standalone local Polkit schema remains 1). It checks the
password-only system-auth baseline plus exact sudo package/components and policy.
`cvtsudoers` parses local includes and all scoped Defaults; any pam_service,
pam_login_service or pam_askpass_service customization is refused. A nonlocal
sudoers NSS source, modified sudo.conf, custom sudo/sudo-i PAM, or pending PAM
rpmnew/rpmsave is refused. Parsing is read-only and is performed by the operator's
root transaction, never by autonomous authentication. The policy digest is kept,
not its contents. Changes require original uninstall then fresh qualification.

The transaction installs leaves before enabling public PAM entries, records
recovery ownership first and restores both services on a caught failure. On
uninstall it verifies all owned content before restoring the exact stock sudo
file and original Polkit override presence. Interrupted removal tolerates already
absent owned files/directories. Drift is preserved for review. If rollback itself
fails, the outer manager retains referenced runtime and recovery metadata and
reports RECOVERY_REQUIRED. Abrupt process/power loss is not filesystem-wide
atomic: retain the checkout and state for recovery, never delete them manually.

Older managed releases lacking `SUDO_INTEGRATION=PASSWORD_FIRST_SERVICE_LOCAL_V1`
cannot be updated or rolled back using this manager. Use their original manager
to uninstall, then fresh install. Existing D285/local development overlays are
collisions, not prerequisites or migration inputs. See
`deployment/managed-install/AUTHENTICATION-LIVE.md` before any installation.

## Evidence and offline tests

Exact Fedora sudo SRPM `sudo-1.9.17-8.p2.fc44.src.rpm`, SHA-256
`fec9a39a47b4e91f4225b21a317dcaace317347636642918b83e9498f8df0f4e`, retrieved from
[Fedora Koji](https://kojipkgs.fedoraproject.org/packages/sudo/1.9.17/8.p2.fc44/src/sudo-1.9.17-8.p2.fc44.src.rpm).
Its spec enables `--with-pam-login`; defaults.c chooses sudo / sudo-i;
auth/pam.c starts PAM once, uses the native conversation and calls setcred;
auth/sudo_auth.c repeats authentication on that handle and blocks INT/QUIT;
src/tgetpass.c owns terminal input and restores terminal settings. The only
Fedora patch concerns mailer privileges, not these paths. Both PAM files are
RPM `%config(noreplace)`, not `/usr/lib/pam.d` vendor overlays.

Exact Fedora PAM SRPM `pam-1.7.2-2.fc44.src.rpm`, SHA-256
`7fc17d339337dda1afa8df8deb9c78fcbf706d4bb8306957f72a610d195e077d`, from
[Fedora Koji](https://kojipkgs.fedoraproject.org/packages/pam/1.7.2/2.fc44/src/pam-1.7.2-2.fc44.src.rpm).
`pam_unix_auth.c` calls `pam_get_authtok`; `libpam/pam_get_authtok.c` returns an
existing PAM_AUTHTOK before prompting. These files match upstream 1.7.2 exactly;
Fedora's three patches do not change that behavior. Thus both bridges' nonempty
passwords flow to the real audited pam_unix path without a duplicate prompt.
Actual credential verification remains a live test; no password/shadow data was read.

Run `test_pam.py PAM_HEADER_DIRECTORY`, `test_cross_pam.py PAM_HEADER_DIRECTORY`,
Polkit's tests, managed tests, and `production/login/check-offline.sh` against
normal/sanitized builds. Test PAM leaves are synthetic, while libpam/fork/pipes
are real. The daemon test runs its real handlers on a private bus and replaces
only device operations/print loading: all 12 ordered pairs among sudo, Polkit,
KScreenLocker and login must reject a competing Claim/VerifyStop without another
open/verify, preserve the owner, then cleanly release on owner loss. Separate
PAM tests establish password fallback and independent budgets. These are
compositional offline tests, not simultaneous real application validation.
